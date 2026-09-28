"""The one universal telemetry message format every truck publishes (PLAN §1).

No per-OEM formats, no schema versioning beyond the `schema_ver` envelope
field (bumped only if the format changes later). Vehicle make/model live in
Postgres, not in the message. Three payload shapes share one envelope:
FAST (1 Hz driving telemetry), HEALTH (60 s wear/state snapshot), and EVENT
(discrete occurrences like a DTC being set).
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, field_validator, model_validator

from fleetcore.algorithms import dtc as dtc_algo
from fleetcore.algorithms import vin as vin_algo

SCHEMA_VERSION = 1


class MsgType(str, Enum):
    FAST = "FAST"
    HEALTH = "HEALTH"
    EVENT = "EVENT"


class EventType(str, Enum):
    DTC_SET = "DTC_SET"
    DTC_CLEARED = "DTC_CLEARED"
    HARSH_BRAKE = "HARSH_BRAKE"
    HARSH_ACCEL = "HARSH_ACCEL"
    HARSH_CORNER = "HARSH_CORNER"
    IGNITION_ON = "IGNITION_ON"
    IGNITION_OFF = "IGNITION_OFF"
    CHARGE_START = "CHARGE_START"
    CHARGE_END = "CHARGE_END"
    OVERSPEED = "OVERSPEED"


def _validate_vin(v: str) -> str:
    if not vin_algo.is_valid(v):
        raise ValueError(f"{v!r} is not a structurally valid VIN (bad check digit)")
    return v


def _validate_dtc(v: str) -> str:
    if not dtc_algo.is_valid(v):
        raise ValueError(f"{v!r} is not a valid DTC code")
    return v


class Envelope(BaseModel):
    """Fields present on every message, regardless of msg_type."""

    vin: Annotated[str, Field(min_length=17, max_length=17)]
    msg_type: MsgType
    seq: Annotated[int, Field(ge=0)]
    ts: datetime
    fw_version: str
    schema_ver: int = SCHEMA_VERSION
    driver_token: str | None = None

    @field_validator("vin")
    @classmethod
    def _check_vin(cls, v: str) -> str:
        return _validate_vin(v)

    @field_validator("ts")
    @classmethod
    def _ts_is_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("ts must be timezone-aware (ISO-8601 UTC)")
        return v.astimezone(timezone.utc)


class FastPayload(BaseModel):
    """1 Hz driving telemetry. Engine-specific fields are optional by drivetrain."""

    lat: Annotated[float, Field(ge=-90, le=90)]
    lon: Annotated[float, Field(ge=-180, le=180)]
    heading: Annotated[float, Field(ge=0, lt=360)]
    gps_hdop: Annotated[float, Field(ge=0)]
    speed_kmh: Annotated[float, Field(ge=0)]
    odo_km: Annotated[float, Field(ge=0)]
    accel_long_g: float
    accel_lat_g: float
    ambient_c: float

    # ICE / general powertrain
    rpm: Annotated[float, Field(ge=0)] | None = None
    load_pct: Annotated[float, Field(ge=0, le=100)] | None = None
    throttle_pct: Annotated[float, Field(ge=0, le=100)] | None = None
    coolant_c: float | None = None
    oil_c: float | None = None
    oil_kpa: Annotated[float, Field(ge=0)] | None = None
    trans_c: float | None = None
    gear: int | None = None
    fuel_pct: Annotated[float, Field(ge=0, le=100)] | None = None
    fuel_rate_lph: Annotated[float, Field(ge=0)] | None = None

    # EV / hybrid HV system
    soc_pct: Annotated[float, Field(ge=0, le=100)] | None = None
    hv_v: float | None = None
    hv_a: float | None = None


class HealthPayload(BaseModel):
    """60 s wear/state snapshot, plus at ignition on/off."""

    tire_kpa: list[float]
    tire_c: list[float]
    brake_pad_pct: list[Annotated[float, Field(ge=0, le=100)]]
    batt_12v_rest_v: float
    crank_min_v: float
    charge_v: float
    engine_hours: Annotated[float, Field(ge=0)]
    idle_s: Annotated[int, Field(ge=0)]
    mil_on: bool
    active_dtc: list[str] = Field(default_factory=list)

    # EV / hybrid HV battery
    cell_v_delta_mv: float | None = None
    cell_temp_max_c: float | None = None
    cell_temp_min_c: float | None = None
    soh_pct: Annotated[float, Field(ge=0, le=100)] | None = None

    @field_validator("active_dtc")
    @classmethod
    def _validate_dtcs(cls, codes: list[str]) -> list[str]:
        return [_validate_dtc(c) for c in codes]


class EventPayload(BaseModel):
    event_type: EventType
    dtc: str | None = None
    freeze_frame: dict[str, float] | None = None
    value: float | None = None

    @field_validator("dtc")
    @classmethod
    def _validate_dtc_field(cls, v: str | None) -> str | None:
        return _validate_dtc(v) if v is not None else v

    @model_validator(mode="after")
    def _dtc_required_for_dtc_events(self) -> "EventPayload":
        if self.event_type in (EventType.DTC_SET, EventType.DTC_CLEARED) and self.dtc is None:
            raise ValueError(f"{self.event_type} requires a dtc code")
        return self


class FastMessage(Envelope):
    msg_type: Literal[MsgType.FAST]
    payload: FastPayload


class HealthMessage(Envelope):
    msg_type: Literal[MsgType.HEALTH]
    payload: HealthPayload


class EventMessage(Envelope):
    msg_type: Literal[MsgType.EVENT]
    payload: EventPayload


TelemetryMessage = Annotated[
    Union[FastMessage, HealthMessage, EventMessage],
    Field(discriminator="msg_type"),
]

_MESSAGE_BY_TYPE: dict[str, type[BaseModel]] = {
    MsgType.FAST.value: FastMessage,
    MsgType.HEALTH.value: HealthMessage,
    MsgType.EVENT.value: EventMessage,
}


def parse_message(raw: dict) -> FastMessage | HealthMessage | EventMessage:
    """Validate a raw decoded-JSON dict against the envelope + the right payload shape.

    Raises `pydantic.ValidationError` (schema/VIN/DTC problems) or `KeyError`
    (missing/unknown msg_type) — callers such as the ingest-gateway catch
    both and route the raw message to the DLQ.
    """
    msg_type = raw["msg_type"]
    model = _MESSAGE_BY_TYPE[msg_type]
    return model.model_validate(raw)
