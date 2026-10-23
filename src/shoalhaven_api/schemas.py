from datetime import datetime

from pydantic import BaseModel, Field


class ChartPoint(BaseModel):
    """x: cateogry/time label. y: value"""

    x: str | datetime
    y: float


class ChartSeries(BaseModel):
    """Single named series; One line or one bar group"""

    name: str
    data: list[ChartPoint]


class ChartResponse(BaseModel):
    """Standard payload returned from every aggregation endpoint."""

    series: list[ChartSeries]


class Location(BaseModel):
    fullAddress: str
    street: str
    postcode: str | None = None
    place: str
    region: str | None = None
    country: str
    coordinates: tuple[float, float]


class Meter(BaseModel):
    id: str = Field(alias="_id")
    location: Location
    type: str
    unit: str
    model_config = {"populate_by_name": True}


class MeterResponse(BaseModel):
    meterObject: Meter


class Reading(BaseModel):
    meterId: str = Field(alias="_meterId")
    kwh: float
    timestamp: datetime
    model_config = {"populate_by_name": True}
