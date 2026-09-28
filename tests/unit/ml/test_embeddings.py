import math

from ml.domain.embeddings import DIM, embed_text


def test_dimension():
    assert len(embed_text("coolant temperature over threshold")) == DIM


def test_unit_norm():
    vec = embed_text("oil pressure sensor circuit malfunction")
    norm = math.sqrt(sum(x * x for x in vec))
    assert math.isclose(norm, 1.0, rel_tol=1e-9)


def test_deterministic():
    a = embed_text("brake pad wear rate")
    b = embed_text("brake pad wear rate")
    assert a == b


def test_empty_text_is_zero_vector():
    vec = embed_text("")
    assert vec == [0.0] * DIM


def test_different_text_differs():
    a = embed_text("cooling system leak")
    b = embed_text("transmission slip")
    assert a != b


def test_similar_text_more_similar_than_unrelated():
    base = embed_text("coolant temperature creeps up over days")
    similar = embed_text("coolant temperature rises over several days")
    unrelated = embed_text("brake pad wear rate projects legal minimum")

    def dot(x, y):
        return sum(a * b for a, b in zip(x, y))

    assert dot(base, similar) > dot(base, unrelated)
