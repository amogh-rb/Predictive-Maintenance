import json
import threading
import time
from datetime import datetime, timezone

from fleetcore.algorithms import vin as vin_algo
from fleetcore.algorithms.sharding import shard_for_vin
from ingest_gateway.app.gateway import Gateway

N_SHARDS = 32
VALID_VIN = vin_algo.with_check_digit("1HGCM82633A00000A")


class FakeProducer:
    def __init__(self):
        self.telemetry: list[tuple[str, dict]] = []
        self.dlq: list[tuple[str, bytes, str, str]] = []

    def send_telemetry(self, vin, message):
        self.telemetry.append((vin, message))

    def send_dlq(self, topic, raw_payload, reason, detail):
        self.dlq.append((topic, raw_payload, reason, detail))

    def poll(self, timeout=0.0):
        pass

    def flush(self, timeout=10.0):
        pass


def _raw_fast(seq=1, vin=VALID_VIN):
    return {
        "vin": vin, "msg_type": "FAST", "seq": seq, "ts": datetime.now(timezone.utc).isoformat(),
        "fw_version": "1.0.0",
        "payload": {
            "lat": 1.0, "lon": 2.0, "heading": 10, "gps_hdop": 1.0, "speed_kmh": 50,
            "odo_km": 100, "accel_long_g": 0, "accel_lat_g": 0, "ambient_c": 30,
        },
    }


def _topic(vin=VALID_VIN, tenant="demo"):
    return f"fleet/{tenant}/shard-{shard_for_vin(vin, N_SHARDS)}/{vin}/telemetry"


def test_valid_message_is_forwarded_to_telemetry():
    producer = FakeProducer()
    gw = Gateway(producer=producer, n_shards=N_SHARDS)
    gw._process_one(_topic(), json.dumps(_raw_fast()).encode())
    assert gw.stats.forwarded == 1
    assert len(producer.telemetry) == 1
    assert producer.telemetry[0][0] == VALID_VIN


def test_invalid_message_goes_to_dlq_not_telemetry():
    producer = FakeProducer()
    gw = Gateway(producer=producer, n_shards=N_SHARDS)
    gw._process_one("bad/topic", b"{}")
    assert gw.stats.forwarded == 0
    assert len(producer.dlq) == 1
    assert producer.telemetry == []


def test_duplicate_vin_seq_is_dropped_not_forwarded_twice():
    producer = FakeProducer()
    gw = Gateway(producer=producer, n_shards=N_SHARDS)
    raw = json.dumps(_raw_fast(seq=7)).encode()
    gw._process_one(_topic(), raw)
    gw._process_one(_topic(), raw)  # exact duplicate (retry)
    assert gw.stats.forwarded == 1
    assert gw.stats.duplicates_dropped == 1
    assert len(producer.telemetry) == 1


def test_different_seq_same_vin_both_forwarded():
    producer = FakeProducer()
    gw = Gateway(producer=producer, n_shards=N_SHARDS)
    gw._process_one(_topic(), json.dumps(_raw_fast(seq=1)).encode())
    gw._process_one(_topic(), json.dumps(_raw_fast(seq=2)).encode())
    assert gw.stats.forwarded == 2


def test_sink_backpressure_blocks_when_queue_full():
    producer = FakeProducer()
    gw = Gateway(producer=producer, n_shards=N_SHARDS, queue_maxsize=1)
    gw.sink(_topic(), json.dumps(_raw_fast(seq=1)).encode())  # fills the queue

    blocked = threading.Event()

    def _offer_second():
        gw.sink(_topic(), json.dumps(_raw_fast(seq=2)).encode())
        blocked.set()

    t = threading.Thread(target=_offer_second, daemon=True)
    t.start()
    time.sleep(0.1)
    assert not blocked.is_set()  # still blocked: queue was full

    gw._queue.get()  # drain one slot, as the worker loop would
    t.join(timeout=1.0)
    assert blocked.is_set()


def test_run_forever_processes_queued_messages_then_stops():
    producer = FakeProducer()
    gw = Gateway(producer=producer, n_shards=N_SHARDS)
    gw.sink(_topic(), json.dumps(_raw_fast(seq=1)).encode())

    t = threading.Thread(target=gw.run_forever, daemon=True)
    t.start()
    time.sleep(0.2)
    gw.stop()
    t.join(timeout=2.0)

    assert gw.stats.forwarded == 1
