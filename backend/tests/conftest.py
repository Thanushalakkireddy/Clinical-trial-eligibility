"""Pytest configuration: explicit test-mode environment.

Automated tests opt out of the strict production startup validation and never
make real external service calls:

- ``ENVIRONMENT=test`` disables the runtime check that requires GEMINI_API_KEY
  and a PostgreSQL DATABASE_URL for normal development/production runs.
- ``GEMINI_API_KEY`` and ``DATABASE_URL`` are blanked here so tests use only the
  isolated SQLite databases and mocked/monkey-patched Gemini services they
  configure explicitly per test.

This does not weaken production validation: the same process started with
ENVIRONMENT=development/production still fails fast when those variables are
missing. Tests explicitly configure exactly what they need.
"""

import os

os.environ["ENVIRONMENT"] = "test"
os.environ["GEMINI_API_KEY"] = ""
os.environ["DATABASE_URL"] = ""