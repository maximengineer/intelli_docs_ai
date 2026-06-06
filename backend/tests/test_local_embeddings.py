"""Local sentence-transformers backend.

Skipped unless the optional 'local-embeddings' extra is installed
(`uv sync --extra local-embeddings`). The model is downloaded on first run.
"""

import math

import pytest

pytest.importorskip("sentence_transformers")

from app.rag.embeddings import SentenceTransformerEmbeddingModel, cosine_similarity

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def test_local_embeddings_are_normalized_and_semantic() -> None:
    model = SentenceTransformerEmbeddingModel(MODEL_NAME)
    docs = model.embed_batch(
        [
            "The invoice total amount is EUR 12,450.",
            "Employees may work remotely up to three days per week.",
        ]
    )

    assert len(docs) == 2
    for vector in docs:
        norm = math.sqrt(sum(value * value for value in vector))
        assert abs(norm - 1.0) < 1e-3  # normalised to unit length

    # A semantic paraphrase of doc 0 should be closer to doc 0 than doc 1,
    # even though it shares no salient keywords with either ("amount"/"cost").
    query = model.embed("what is the billed cost on the bill")
    assert cosine_similarity(query, docs[0]) > cosine_similarity(query, docs[1])
