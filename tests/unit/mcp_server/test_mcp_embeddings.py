import math

from mcp_server.domain.embeddings import DIM, embed_text
from ml.domain.embeddings import embed_text as ml_embed_text


def test_dimension():
    assert len(embed_text("coolant temperature over threshold")) == DIM


def test_unit_norm():
    vec = embed_text("oil pressure sensor circuit malfunction")
    norm = math.sqrt(sum(x * x for x in vec))
    assert math.isclose(norm, 1.0, rel_tol=1e-9)


def test_matches_ml_service_embedding():
    # search_dtc_kb embeds a live query with this copy; build_kb.py (session 5)
    # wrote dtc_kb's vectors with ml's copy. They must stay numerically
    # identical or nearest-neighbour search silently degrades.
    text = "P0128 coolant thermostat stuck open"
    assert embed_text(text) == ml_embed_text(text)
