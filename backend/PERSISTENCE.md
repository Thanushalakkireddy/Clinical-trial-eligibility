# Assessment Persistence (Optional PostgreSQL Layer)

The eligibility API can persist the full audit trail of every assessment run —
protocol, normalized patient profile, final decision and per-stage traces — in
a PostgreSQL database. Persistence is **entirely optional** and **off by
default**.

## Enabling persistence

1. Set `DATABASE_URL` (postgres `postgresql+asyncpg://USER:PASSWORD@HOST:PORT/DATABASE`),
   e.g. in `.env`:

   ```env
   DATABASE_URL=postgresql+asyncpg://eligibility:s3cret@localhost:5432/eligibility
   ```

2. Run the migration:

   ```powershell
   cd backend
   $env:DATABASE_URL="postgresql+asyncpg://eligibility:s3cret@localhost:5432/eligibility"
   alembic upgrade head
   ```

3. Start the API as usual. The first `POST /api/v1/workflow/evaluate` request
   will create the engine lazily; every run is persisted.

No destructive auto-creation happens at runtime against a configured database —
schema changes always go through Alembic. `create_schema()` (drop-in only for
isolated local/test databases) is never called from the application.

## Disabled mode (default)

With `DATABASE_URL` empty or unset:

- no engine is created,
- no database connection is ever attempted,
- the workflow runs exactly as before (deterministic in-memory),
- `POST /api/v1/workflow/evaluate` returns `"assessment_id": null`,
- `GET /api/v1/assessments*` returns `503` with instructions.

## What is stored

| Table                  | Contents                                                              |
| ---------------------- | --------------------------------------------------------------------- |
| `clinical_trial_protocols` | One row per trial; protocol metadata, criteria evidence, source info |
| `patient_profiles`      | Normalized patient profile snapshot (JSON) per profile id             |
| `assessment_runs`       | One row per workflow execution: status, decision, warnings, errors, snapshot |
| `assessment_traces`     | Ordered per-stage audit lines: start, inclusion, exclusion, contradiction, decision, complete |

JSON payloads are stored in `TEXT` columns, encoded/decoded by the
serialization layer, so the same schema works on PostgreSQL and the isolated
SQLite databases used in tests.

## API

- `POST /api/v1/workflow/evaluate` — returns `assessment_id` when configured.
- `GET /api/v1/assessments?trial_id=&patient_profile_id=&limit=&offset=` — list
  runs newest-first.
- `GET /api/v1/assessments/{assessment_id}` — full record + ordered traces +
  reproducible snapshot.

## Failure safety

- Persistence failures are logged and surfaced as **non-fatal warnings** on the
  workflow response; they never change an eligibility decision and never
  fabricate an `assessment_id` (it is only returned after the record is
  created).
- A crashed/missing database fails fast (5s connect timeout, `pool_pre_ping`)
  and the API keeps serving eligibility decisions without persistence.
- Credentials are never logged: `redact_database_url()` masks passwords in logs
  and the API never returns connection strings.

## Local development without PostgreSQL

Use SQLite so the whole persistence flow runs locally:

```powershell
$env:DATABASE_URL="sqlite+aiosqlite:///C:/tmp/eligibility.db"
alembic upgrade head
```

The test suite uses its own isolated SQLite files and requires no database.

## Workflow checkpointing (LangGraph persistent state)

Every evaluation can also persist the **LangGraph workflow state itself** the same
database, so an interrupted run can be resumed. This is enabled automatically
whenever persistence is enabled (`DATABASE_URL` set); it uses the
`DATABASE_URL` of the app — there is no second database.

| Backend (`DATABASE_URL`)  | Checkpointer                   | Tables created by saver `setup()` |
| ------------------------- | ------------------------------ | --------------------------------- |
| `postgresql(+asyncpg)://` | `AsyncPostgresSaver` (psycopg) | `checkpoints`, `writes`, `checkpoint_migrations` |
| `sqlite(+aiosqlite)://`   | `AsyncSqliteSaver`             | `checkpoints`, `writes`           |

### How it works

- `app/checkpoint/provider.py` lazily builds one checkpointer per database URL on
  the **first call** (no connections at import time). Unsupported or unset URLs
  return `None` — checkpointing disabled, workflow stays deterministic.
- `POST /api/v1/workflow/evaluate` uses the persisted `assessment_id` as the
  LangGraph **thread_id**, so each assessment is a distinct, replayable thread.
- State is stored through LangGraph's default `JsonPlusSerializer`, which
  restores workflow Pydantic models as typed objects on resume. Checkpoint
  tables are managed by the checkpointer itself (not Alembic).
- If the checkpointer cannot be set up (missing/unreachable database), the API
  logs a warning and degrades to the classic deterministic run — the decision is
  never changed.

### Failure safety

- Checkpoint **write** failure mid-run aborts the run: the assessment record is
  marked `FAILED`, no eligibility decision is fabricated, and the API returns an
  error response.
- Checkpoint **setup** failure at request time is non-fatal: the request completes
  with a warning and the decision is computed deterministically.
- The workflow API is async end-to-end (psycopg / aiosqlite); no blocking calls
  are introduced.

### Resuming an interrupted run

```python
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver  # or sqlite
from app.checkpoint import make_checkpoint_serializer
from app.graph.workflow import build_workflow

saver = AsyncPostgresSaver(async_pg_conn, serde=make_checkpoint_serializer())
await saver.setup()
graph = build_workflow(checkpointer=saver)
config = {"configurable": {"thread_id": "<assessment_id>"}}

snapshot = await graph.aget_state(config)       # pending nodes, saved state
# resume the same thread to completion:
final = await graph.ainvoke(None, config)
```