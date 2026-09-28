from state_writer.app.writer import StateWriter


class FakeConsumer:
    def poll(self, timeout=1.0):
        return None


class FakeLatestStore:
    def __init__(self):
        self.data = {}

    def set_latest(self, vin, doc):
        self.data[vin] = doc


class FakeTwinStore:
    def __init__(self):
        self.twins = {}
        self.raw = []

    def upsert_twin(self, vin, doc):
        self.twins[vin] = dict(doc)

    def archive_raw(self, message):
        self.raw.append(message)


class FakeAlertStore:
    def __init__(self, known_vins):
        self.known_vins = known_vins
        self.inserted = []

    def insert_alert(self, alert):
        if alert["vin"] not in self.known_vins:
            return False
        self.inserted.append(alert)
        return True


def _fast(vin="VIN1", seq=1, coolant_c=90):
    return {
        "vin": vin, "tenant": "demo", "msg_type": "FAST", "seq": seq,
        "ts": "2026-09-28T12:00:00Z", "payload": {"coolant_c": coolant_c},
    }


def _alert(vin="VIN1"):
    return {
        "vin": vin, "tenant": "demo", "failure_type": "cooling", "severity": "critical",
        "source": "realtime", "dtc_codes": ["P0128"], "detected_at": "2026-09-28T12:00:30Z",
    }


def _make_writer(known_vins=frozenset({"VIN1"})):
    latest, twin, alert = FakeLatestStore(), FakeTwinStore(), FakeAlertStore(known_vins)
    writer = StateWriter(FakeConsumer(), latest, twin, alert, "telemetry", "alerts")
    return writer, latest, twin, alert


def test_telemetry_message_writes_redis_and_mongo_twin_and_archive():
    writer, latest, twin, _ = _make_writer()
    writer._handle_telemetry(_fast())
    assert latest.data["VIN1"]["coolant_c"] == 90
    assert twin.twins["VIN1"]["coolant_c"] == 90
    assert len(twin.raw) == 1
    assert writer.stats.telemetry_processed == 1


def test_stale_telemetry_is_dropped_and_not_archived():
    writer, _, twin, _ = _make_writer()
    writer._handle_telemetry(_fast(seq=5))
    writer._handle_telemetry(_fast(seq=5))  # exact retry
    assert writer.stats.telemetry_processed == 1
    assert writer.stats.telemetry_stale_dropped == 1
    assert len(twin.raw) == 1  # the dropped retry is never archived


def test_alert_for_known_vin_is_inserted():
    writer, *_, alert = _make_writer(known_vins={"VIN1"})
    writer._handle_alert(_alert())
    assert len(alert.inserted) == 1
    assert writer.stats.alerts_processed == 1


def test_alert_for_unseeded_vin_is_counted_not_inserted():
    writer, *_, alert = _make_writer(known_vins=set())
    writer._handle_alert(_alert(vin="UNKNOWN"))
    assert alert.inserted == []
    assert writer.stats.alerts_unknown_vin == 1
