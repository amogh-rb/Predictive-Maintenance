import pytest

from api.app import erasure


def test_erase_driver_pseudonymizes_and_purges_mongo(monkeypatch):
    driver = {"id": "d1", "driver_token": "drv-token-1", "full_name": "Real Name"}
    monkeypatch.setattr("api.infra.repositories.get_driver", lambda session, did: driver)
    pseudonymize_calls = []
    monkeypatch.setattr(
        "api.infra.repositories.pseudonymize_driver",
        lambda session, did: pseudonymize_calls.append(did),
    )
    monkeypatch.setattr("api.infra.mongo_client.erase_driver_archive", lambda token: 7)

    result = erasure.erase_driver(session=object(), driver_id="d1")

    assert pseudonymize_calls == ["d1"]
    assert result["mongo_raw_archive_deleted"] == 7
    assert result["postgres_pii_pseudonymized"] is True


def test_erase_driver_not_found_raises(monkeypatch):
    monkeypatch.setattr("api.infra.repositories.get_driver", lambda session, did: None)

    with pytest.raises(erasure.DriverNotFound):
        erasure.erase_driver(session=object(), driver_id="missing")
