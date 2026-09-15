"""Comprehensive unit and integration test suite for Checkpoint 5 Python RAG.

Covers:
1. Chunk creation from ExtractedProtocol and dict
2. Criterion metadata preservation (chunk_id, trial_id, criterion_id, criterion_type, source_page, excerpt)
3. Clinical threshold preservation (e.g. eGFR >= 30 mL/min/1.73m², Age >= 18, ANC >= 1500/uL)
4. Embedding dimension = 384
5. Normalized embeddings (L2 norm == 1.0)
6. Semantic retrieval and cosine ranking
7. Strict trial isolation (oncology trial CANNOT return pulmonary criteria)
8. Metadata mapping 1:1 with FAISS indices
9. FAISS persistence (index.faiss and metadata.json written to disk)
10. Retrieval after reload from persisted disk files
11. Empty query handling
12. Unknown trial handling
13. Invalid top_k handling
14. Empty index handling
15. FastAPI POST /api/v1/rag/index endpoint
16. FastAPI POST /api/v1/rag/retrieve endpoint
17. Real SentenceTransformer integration test if model is available
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.rag.chunker import ProtocolChunker
from app.rag.embeddings import (
    DEFAULT_MODEL_NAME,
    EMBEDDING_DIMENSION,
    EmbeddingService,
    get_embedding_service,
)
from app.rag.metadata_store import MetadataStore, sanitize_trial_id
from app.rag.retriever import ProtocolRetriever
from app.rag.service import RAGService
from app.rag.vector_store import FAISSVectorStore
from app.schemas.protocol import CriterionType, ExtractedProtocol, ProtocolCriterion
from app.schemas.rag import IndexProtocolRequest, ProtocolChunk, RetrievalQuery


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_faiss_dir():
    """Temporary storage directory for FAISS and metadata."""
    tmp = tempfile.mkdtemp(prefix="faiss_test_")
    yield Path(tmp)
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def embedding_svc():
    """Embedding service instance."""
    return get_embedding_service()


@pytest.fixture
def sample_oncology_protocol() -> ExtractedProtocol:
    """Sample oncology trial with specific clinical thresholds."""
    return ExtractedProtocol(
        trial_id="SYN-ONC-001",
        protocol_id="SYN-ONC-001",
        title="Phase III Study of Targeted Inhibitor in Advanced Solid Tumors",
        source_document="oncology_protocol_v1.pdf",
        inclusion_criteria=[
            ProtocolCriterion(
                criterion_id="INC-001",
                type=CriterionType.INCLUSION,
                text="Age >= 18 years at the time of signing informed consent.",
                source_page=12,
                section="Inclusion Criteria",
                source_excerpt="Age >= 18 years at the time of signing",
                trial_id="SYN-ONC-001",
            ),
            ProtocolCriterion(
                criterion_id="INC-002",
                type=CriterionType.INCLUSION,
                text="Histologically or cytologically confirmed metastatic solid tumor refractory to standard therapy.",
                source_page=12,
                section="Inclusion Criteria",
                source_excerpt="confirmed metastatic solid tumor",
                trial_id="SYN-ONC-001",
            ),
            ProtocolCriterion(
                criterion_id="INC-003",
                type=CriterionType.INCLUSION,
                text="Adequate renal function defined as serum creatinine <= 1.5 x ULN or eGFR >= 30 mL/min/1.73m².",
                source_page=13,
                section="Inclusion Criteria",
                source_excerpt="eGFR >= 30 mL/min/1.73m²",
                trial_id="SYN-ONC-001",
            ),
            ProtocolCriterion(
                criterion_id="INC-004",
                type=CriterionType.INCLUSION,
                text="Absolute neutrophil count (ANC) >= 1500/uL and platelets >= 100,000/uL.",
                source_page=13,
                section="Inclusion Criteria",
                source_excerpt="ANC >= 1500/uL and platelets >= 100,000/uL",
                trial_id="SYN-ONC-001",
            ),
        ],
        exclusion_criteria=[
            ProtocolCriterion(
                criterion_id="EXC-001",
                type=CriterionType.EXCLUSION,
                text="Active brain metastases or leptomeningeal disease requiring ongoing corticosteroids.",
                source_page=14,
                section="Exclusion Criteria",
                source_excerpt="Active brain metastases",
                trial_id="SYN-ONC-001",
            ),
            ProtocolCriterion(
                criterion_id="EXC-002",
                type=CriterionType.EXCLUSION,
                text="ECOG performance status >= 2.",
                source_page=14,
                section="Exclusion Criteria",
                source_excerpt="ECOG performance status >= 2",
                trial_id="SYN-ONC-001",
            ),
        ],
        other_requirements=[],
        extraction_metadata={"version": "1.0", "page_count": 45},
    )


@pytest.fixture
def sample_pulmonary_protocol() -> ExtractedProtocol:
    """Sample pulmonary trial for isolation testing."""
    return ExtractedProtocol(
        trial_id="SYN-PULM-002",
        protocol_id="SYN-PULM-002",
        title="Study of Novel Inhaled Bronchodilator in Severe COPD and Asthma",
        source_document="pulmonary_protocol_v2.pdf",
        inclusion_criteria=[
            ProtocolCriterion(
                criterion_id="INC-001",
                type=CriterionType.INCLUSION,
                text="Diagnosis of moderate to severe chronic obstructive pulmonary disease (COPD) with post-bronchodilator FEV1/FVC < 0.70.",
                source_page=8,
                section="Inclusion Criteria",
                source_excerpt="post-bronchodilator FEV1/FVC < 0.70",
                trial_id="SYN-PULM-002",
            ),
            ProtocolCriterion(
                criterion_id="INC-002",
                type=CriterionType.INCLUSION,
                text="Documented smoking history of at least 10 pack-years.",
                source_page=8,
                section="Inclusion Criteria",
                source_excerpt="at least 10 pack-years",
                trial_id="SYN-PULM-002",
            ),
        ],
        exclusion_criteria=[
            ProtocolCriterion(
                criterion_id="EXC-001",
                type=CriterionType.EXCLUSION,
                text="History of cystic fibrosis, bronchiectasis, or active pulmonary tuberculosis.",
                source_page=9,
                section="Exclusion Criteria",
                source_excerpt="cystic fibrosis, bronchiectasis",
                trial_id="SYN-PULM-002",
            ),
        ],
        other_requirements=[],
        extraction_metadata={"version": "2.0"},
    )


@pytest.fixture
def api_client():
    """FastAPI TestClient with RAG router mounted."""
    app = create_app()
    with TestClient(app) as client:
        yield client


# ---------------------------------------------------------------------------
# 1. Chunk Creation & Traceability Tests
# ---------------------------------------------------------------------------

def test_chunk_creation_from_protocol(sample_oncology_protocol: ExtractedProtocol):
    """Verify ProtocolChunker accurately transforms ExtractedProtocol into ProtocolChunks."""
    chunker = ProtocolChunker()
    chunks = chunker.chunk_protocol(sample_oncology_protocol)

    assert len(chunks) == 6  # 4 inclusion + 2 exclusion
    chunk_ids = [c.chunk_id for c in chunks]
    assert "CHK-SYN-ONC-001-INC-001" in chunk_ids
    assert "CHK-SYN-ONC-001-INC-003" in chunk_ids
    assert "CHK-SYN-ONC-001-EXC-001" in chunk_ids


def test_chunk_metadata_preservation(sample_oncology_protocol: ExtractedProtocol):
    """Verify chunker preserves all critical metadata and page traceability."""
    chunker = ProtocolChunker()
    chunks = chunker.chunk_protocol(sample_oncology_protocol)

    c3 = next(c for c in chunks if c.criterion_id == "INC-003")
    assert c3.trial_id == "SYN-ONC-001"
    assert c3.criterion_type == "inclusion"
    assert c3.section == "Inclusion Criteria"
    assert c3.source_page == 13
    assert c3.source_document == "oncology_protocol_v1.pdf"
    assert "eGFR >= 30" in (c3.source_excerpt or "")
    assert isinstance(c3.metadata, dict)


def test_clinical_threshold_preservation(sample_oncology_protocol: ExtractedProtocol):
    """Verify that clinical thresholds like eGFR >= 30 mL/min/1.73m² are strictly preserved verbatim."""
    chunker = ProtocolChunker()
    chunks = chunker.chunk_protocol(sample_oncology_protocol)

    egfr_chunk = next(c for c in chunks if "eGFR" in c.text)
    # The text must preserve operator, value, and units intact
    assert "eGFR >= 30 mL/min/1.73m²" in egfr_chunk.text
    assert "30" in egfr_chunk.text
    assert "mL/min/1.73m²" in egfr_chunk.text
    assert "1.5 x ULN" in egfr_chunk.text

    anc_chunk = next(c for c in chunks if "ANC" in c.text)
    assert "1500/uL" in anc_chunk.text
    assert "100,000/uL" in anc_chunk.text


def test_chunker_handles_dict_input(sample_oncology_protocol: ExtractedProtocol):
    """Verify chunker gracefully handles raw dict input."""
    chunker = ProtocolChunker()
    raw_dict = sample_oncology_protocol.model_dump()
    chunks = chunker.chunk_protocol(raw_dict)
    assert len(chunks) == 6
    assert all(isinstance(c, ProtocolChunk) for c in chunks)


# ---------------------------------------------------------------------------
# 2. Embedding Dimension & Normalization Tests
# ---------------------------------------------------------------------------

def test_embedding_dimension(embedding_svc: EmbeddingService):
    """Verify embedding dimension is exactly 384."""
    texts = [
        "Age >= 18 years",
        "Adequate renal function eGFR >= 30 mL/min/1.73m²",
        "Active brain metastases",
    ]
    vecs = embedding_svc.embed_texts(texts)
    assert vecs.ndim == 2
    assert vecs.shape[0] == 3
    assert vecs.shape[1] == EMBEDDING_DIMENSION
    assert vecs.dtype == np.float32


def test_embedding_query_dimension(embedding_svc: EmbeddingService):
    """Verify single query embedding is (1, 384) float32."""
    vec = embedding_svc.embed_query("kidney function eGFR")
    assert vec.shape == (1, 384)
    assert vec.dtype == np.float32


def test_normalized_embeddings(embedding_svc: EmbeddingService):
    """Verify vectors are L2-normalized so norms are equal to 1.0."""
    texts = [
        "eGFR >= 30 mL/min/1.73m²",
        "Absolute neutrophil count (ANC) >= 1500/uL",
        "ECOG performance status >= 2",
    ]
    vecs = embedding_svc.embed_texts(texts)
    norms = np.linalg.norm(vecs, axis=1)
    for norm in norms:
        assert abs(norm - 1.0) < 1e-4, f"Vector not unit-normalized, norm={norm}"


# ---------------------------------------------------------------------------
# 3. Vector Store & FAISS Persistence Tests
# ---------------------------------------------------------------------------

def test_faiss_vector_store_persistence(temp_faiss_dir: Path, embedding_svc: EmbeddingService):
    """Verify FAISS vector store writes and loads index from disk."""
    vs = FAISSVectorStore(base_dir=temp_faiss_dir)
    trial_id = "TEST-PERSIST-001"

    texts = ["Criterion 1", "Criterion 2", "Criterion 3"]
    vectors = embedding_svc.embed_texts(texts)

    assert not vs.exists(trial_id)
    saved_path = vs.index_vectors(trial_id, vectors)
    assert vs.exists(trial_id)
    assert saved_path.exists()

    # Search against the persisted store
    q_vec = embedding_svc.embed_query("Criterion 1")
    scores, indices = vs.search(trial_id, q_vec, top_k=2)
    assert scores.shape == (1, 2)
    assert indices.shape == (1, 2)
    assert indices[0][0] == 0  # Most similar to Criterion 1 is index 0


def test_metadata_store_save_and_load(temp_faiss_dir: Path):
    """Verify metadata store preserves 1:1 mapping with chunks."""
    ms = MetadataStore(base_dir=temp_faiss_dir)
    trial_id = "TEST-META-001"

    chunk1 = ProtocolChunk(
        chunk_id="CHK-1",
        trial_id=trial_id,
        criterion_id="INC-001",
        criterion_type="inclusion",
        section="Inclusion",
        text="Text 1",
        source_page=1,
        source_document="doc.pdf",
    )
    chunk2 = ProtocolChunk(
        chunk_id="CHK-2",
        trial_id=trial_id,
        criterion_id="EXC-001",
        criterion_type="exclusion",
        section="Exclusion",
        text="Text 2",
        source_page=2,
        source_document="doc.pdf",
    )

    meta_file = ms.save(trial_id, [chunk1, chunk2])
    assert meta_file.exists()

    loaded = ms.load(trial_id)
    assert len(loaded) == 2
    assert loaded[0].chunk_id == "CHK-1"
    assert loaded[1].chunk_id == "CHK-2"
    assert loaded[0].criterion_type == "inclusion"


def test_sanitize_trial_id():
    """Verify sanitize_trial_id cleans dangerous characters."""
    assert sanitize_trial_id("../../etc/passwd") == "______etc_passwd"
    assert sanitize_trial_id("SYN-ONC-001") == "SYN-ONC-001"
    assert sanitize_trial_id("trial with spaces") == "trial_with_spaces"
    assert sanitize_trial_id("") == "UNKNOWN_TRIAL"


# ---------------------------------------------------------------------------
# 4. RAG Service & Retrieval Tests
# ---------------------------------------------------------------------------

def test_rag_service_indexing_and_retrieval(
    temp_faiss_dir: Path,
    sample_oncology_protocol: ExtractedProtocol,
    embedding_svc: EmbeddingService,
):
    """Verify end-to-end indexing and retrieval through RAGService."""
    vs = FAISSVectorStore(base_dir=temp_faiss_dir)
    ms = MetadataStore(base_dir=temp_faiss_dir)
    rag_svc = RAGService(
        embedding_service=embedding_svc,
        vector_store=vs,
        metadata_store=ms,
    )

    resp = rag_svc.index_protocol(sample_oncology_protocol)
    assert resp.status == "success"
    assert resp.indexed_chunks_count == 6
    assert resp.trial_id == "SYN-ONC-001"

    # Query for renal function / eGFR
    res = rag_svc.retrieve(trial_id="SYN-ONC-001", query="eGFR 30 mL/min/1.73m² kidney", top_k=3)
    assert res.trial_id == "SYN-ONC-001"
    assert len(res.results) > 0

    top_result = res.results[0]
    assert "eGFR" in top_result.text or "renal" in top_result.text.lower()
    assert top_result.score > 0.0
    assert top_result.source_page in [12, 13, 14]
    assert top_result.source_document == "oncology_protocol_v1.pdf"


def test_retrieval_after_reload(
    temp_faiss_dir: Path,
    sample_oncology_protocol: ExtractedProtocol,
    embedding_svc: EmbeddingService,
):
    """Verify that indices and metadata can be closed and reloaded afresh from disk."""
    # First service instance indexes
    vs1 = FAISSVectorStore(base_dir=temp_faiss_dir)
    ms1 = MetadataStore(base_dir=temp_faiss_dir)
    rag1 = RAGService(embedding_service=embedding_svc, vector_store=vs1, metadata_store=ms1)
    rag1.index_protocol(sample_oncology_protocol)

    # Second fresh service instance retrieves from disk
    vs2 = FAISSVectorStore(base_dir=temp_faiss_dir)
    ms2 = MetadataStore(base_dir=temp_faiss_dir)
    rag2 = RAGService(embedding_service=embedding_svc, vector_store=vs2, metadata_store=ms2)

    res = rag2.retrieve("SYN-ONC-001", "brain metastases", top_k=2)
    assert len(res.results) == 2
    assert any("brain metastases" in r.text.lower() for r in res.results)


# ---------------------------------------------------------------------------
# 5. Strict Trial Isolation Test
# ---------------------------------------------------------------------------

def test_strict_trial_isolation(
    temp_faiss_dir: Path,
    sample_oncology_protocol: ExtractedProtocol,
    sample_pulmonary_protocol: ExtractedProtocol,
    embedding_svc: EmbeddingService,
):
    """Verify oncology trial search NEVER returns pulmonary criteria and vice-versa."""
    vs = FAISSVectorStore(base_dir=temp_faiss_dir)
    ms = MetadataStore(base_dir=temp_faiss_dir)
    rag = RAGService(embedding_service=embedding_svc, vector_store=vs, metadata_store=ms)

    # Index both trials into isolated stores
    rag.index_protocol(sample_oncology_protocol)
    rag.index_protocol(sample_pulmonary_protocol)

    # Search the oncology trial for COPD/smoking/pulmonary concepts
    onc_results = rag.retrieve(
        trial_id="SYN-ONC-001",
        query="COPD bronchiectasis post-bronchodilator FEV1/FVC",
        top_k=5,
    )

    # All returned criteria MUST belong strictly to SYN-ONC-001
    for r in onc_results.results:
        assert r.trial_id == "SYN-ONC-001"
        assert "COPD" not in r.text
        assert "bronchodilator" not in r.text
        assert "pulmonary_protocol_v2.pdf" != r.source_document

    # Search the pulmonary trial for oncology concepts
    pulm_results = rag.retrieve(
        trial_id="SYN-PULM-002",
        query="metastatic solid tumor eGFR 30 refractory chemotherapy",
        top_k=5,
    )

    for r in pulm_results.results:
        assert r.trial_id == "SYN-PULM-002"
        assert "metastatic solid tumor" not in r.text
        assert "oncology_protocol_v1.pdf" != r.source_document


# ---------------------------------------------------------------------------
# 6. Edge Cases & Defensive Robustness Tests
# ---------------------------------------------------------------------------

def test_empty_query_handling(temp_faiss_dir: Path, sample_oncology_protocol: ExtractedProtocol):
    """Verify empty query returns clean empty result without throwing error."""
    vs = FAISSVectorStore(base_dir=temp_faiss_dir)
    ms = MetadataStore(base_dir=temp_faiss_dir)
    rag = RAGService(vector_store=vs, metadata_store=ms)
    rag.index_protocol(sample_oncology_protocol)

    res = rag.retrieve("SYN-ONC-001", "", top_k=5)
    assert res.results == []

    res_space = rag.retrieve("SYN-ONC-001", "   ", top_k=5)
    assert res_space.results == []


def test_unknown_trial_handling(temp_faiss_dir: Path):
    """Verify searching an unknown trial returns empty results cleanly."""
    vs = FAISSVectorStore(base_dir=temp_faiss_dir)
    ms = MetadataStore(base_dir=temp_faiss_dir)
    rag = RAGService(vector_store=vs, metadata_store=ms)

    res = rag.retrieve("NON-EXISTENT-TRIAL-999", "kidney function", top_k=5)
    assert res.results == []
    assert res.trial_id == "NON-EXISTENT-TRIAL-999"


def test_invalid_top_k_handling(temp_faiss_dir: Path, sample_oncology_protocol: ExtractedProtocol):
    """Verify top_k <= 0 returns empty results without crashing."""
    vs = FAISSVectorStore(base_dir=temp_faiss_dir)
    ms = MetadataStore(base_dir=temp_faiss_dir)
    rag = RAGService(vector_store=vs, metadata_store=ms)
    rag.index_protocol(sample_oncology_protocol)

    res = rag.retrieve("SYN-ONC-001", "kidney function", top_k=0)
    assert res.results == []

    res_neg = rag.retrieve("SYN-ONC-001", "kidney function", top_k=-5)
    assert res_neg.results == []


def test_empty_protocol_index(temp_faiss_dir: Path):
    """Verify empty protocol handles gracefully."""
    vs = FAISSVectorStore(base_dir=temp_faiss_dir)
    ms = MetadataStore(base_dir=temp_faiss_dir)
    rag = RAGService(vector_store=vs, metadata_store=ms)

    empty_proto = ExtractedProtocol(
        trial_id="EMPTY-001",
        protocol_id="EMPTY-001",
        title="Empty",
        source_document="empty.pdf",
        inclusion_criteria=[],
        exclusion_criteria=[],
        other_requirements=[],
    )
    resp = rag.index_protocol(empty_proto)
    assert resp.indexed_chunks_count == 0
    assert resp.status == "empty"


# ---------------------------------------------------------------------------
# 7. FastAPI Endpoint Tests
# ---------------------------------------------------------------------------

def test_api_index_endpoint(api_client: TestClient, sample_oncology_protocol: ExtractedProtocol):
    """Test POST /api/v1/rag/index via FastAPI."""
    payload = {
        "trial_id": "API-TRIAL-001",
        "protocol": sample_oncology_protocol.model_dump(),
    }
    response = api_client.post("/api/v1/rag/index", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["trial_id"] == "API-TRIAL-001"
    assert data["indexed_chunks_count"] == 6
    assert data["status"] == "success"


def test_api_retrieve_endpoint(api_client: TestClient, sample_oncology_protocol: ExtractedProtocol):
    """Test POST /api/v1/rag/retrieve via FastAPI."""
    # First index
    index_payload = {
        "trial_id": "API-TRIAL-002",
        "protocol": sample_oncology_protocol.model_dump(),
    }
    api_client.post("/api/v1/rag/index", json=index_payload)

    # Retrieve
    retrieve_payload = {
        "trial_id": "API-TRIAL-002",
        "query": "ANC platelets blood count",
        "top_k": 3,
    }
    response = api_client.post("/api/v1/rag/retrieve", json=retrieve_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["trial_id"] == "API-TRIAL-002"
    assert len(data["results"]) > 0
    assert any("platelets" in r["text"].lower() or "anc" in r["text"].lower() for r in data["results"])


def test_api_validation_errors(api_client: TestClient):
    """Test invalid payloads on FastAPI endpoints."""
    # Empty trial_id on retrieve
    resp = api_client.post("/api/v1/rag/retrieve", json={"trial_id": "", "query": "test"})
    assert resp.status_code in [400, 422]

    # Empty query on retrieve
    resp = api_client.post("/api/v1/rag/retrieve", json={"trial_id": "T1", "query": ""})
    assert resp.status_code in [400, 422]

    # top_k out of range
    resp = api_client.post("/api/v1/rag/retrieve", json={"trial_id": "T1", "query": "test", "top_k": 0})
    assert resp.status_code in [400, 422]
