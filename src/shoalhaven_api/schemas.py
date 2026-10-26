from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


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


class MeterPowerRow(BaseModel):
    """A timestamp with one dynamic numeric field per meter."""

    date: datetime

    __pydantic_extra__: dict[str, float] = Field(init=False)
    model_config = ConfigDict(extra="allow")

class MeterTotal(BaseModel):
    """Total kWh used by one meter over a date range"""

    name: str
    KWH: float


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
    model_config = ConfigDict(populate_by_name=True)


class MeterMapPoint(BaseModel):
    """One meter as a map marker, with its total usage over the chosen range"""

    id: str
    type: str
    fullAddress: str
    place: str
    coordinates: tuple[float, float]
    totalKwh: float | None
    inShoalhaven: bool


class MeterResponse(BaseModel):
    meterObject: Meter


class Reading(BaseModel):
    meterId: str = Field(alias="_meterId")
    kwh: float
    timestamp: datetime
    model_config = ConfigDict(populate_by_name=True)


class ForecastPoint(BaseModel):
    x: datetime
    p10: float
    p50: float
    p90: float


class ForecastBacktest(BaseModel):
    """Error on the held-out final horizon, for the model and the seasonal-naive baseline"""

    horizon: int
    modelMae: float | None
    baselineMae: float | None
    modelMape: float | None
    baselineMape: float | None


class ForecastResponse(BaseModel):
    meterId: str
    granularity: str
    model: str
    generatedAt: datetime
    anchor: datetime
    points: list[ForecastPoint]
    backtest: ForecastBacktest | None = None


class MarketRow(BaseModel):
    """One time bucket with a numeric field per market series, e.g. price, solar_rooftop"""

    date: datetime

    __pydantic_extra__: dict[str, float] = Field(init=False)
    model_config = ConfigDict(extra="allow")


class MarketProfileRow(BaseModel):
    """Average market values for one half hour of the day, e.g. time "12:30" """

    time: str

    __pydantic_extra__: dict[str, float] = Field(init=False)
    model_config = ConfigDict(extra="allow")


class MarketStats(BaseModel):
    """NSW spot price summary in $/MWh"""

    start: datetime
    end: datetime
    count: int
    average: float | None
    max: float | None
    min: float | None
    negativeShare: float | None
    middayAverage: float | None
    eveningAverage: float | None


class BusiestDay(BaseModel):
    date: date
    kwh: float


class MonthSummary(BaseModel):
    """All meters added together for one month"""

    month: datetime
    totalKwh: float
    busiestDay: BusiestDay | None
    # Each half hour's kWh x that half hour's NSW spot price, in AUD. None without market data
    wholesaleCost: float | None
    # Share of the month's kWh that had a matching spot price (1.0 = fully priced)
    pricedShare: float


class PowerSummary(BaseModel):
    current: MonthSummary
    previous: MonthSummary
