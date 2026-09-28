from __future__ import annotations

from pydantic import BaseModel


class ProposeWorkOrderRequest(BaseModel):
    vehicle_id: str
    alert_id: str | None = None


class BookDepotRequest(BaseModel):
    vehicle_lat: float
    vehicle_lon: float
    hours: int = 4
