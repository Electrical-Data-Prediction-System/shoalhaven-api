from datetime import datetime, timedelta
from os import getenv
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from openelectricity import OEClient
from openelectricity.types import DataMetric, UnitFueltechType

from shoalhaven_api.schemas import ChartPoint, ChartResponse, ChartSeries

load_dotenv()

api_key = getenv("OPENELECTRICITY_API_KEY")

# OpenElectricity only accepts timezone-NAIVE datetimes, interpreted as network
# local time. NEM runs on Australia/Sydney time, so build the window there and
# drop the tzinfo before sending (aware datetimes are rejected with a 400).
NETWORK_TZ = ZoneInfo("Australia/Sydney")


def test() -> dict:
    """Chart the last full day of both solar fueltechs (utility + rooftop).

    Returns the standard chart payload used across the API:
    {"series": [{"name": <fueltech>, "data": [{"x": <time>, "y": <MW>}]}]}

    Swap DataMetric.POWER for DataMetric.ENERGY if you want MWh instead of MW.
    """
    # Naive network-local window: yesterday 00:00 -> today 00:00.
    today = datetime.now(NETWORK_TZ).replace(
        hour=0, minute=0, second=0, microsecond=0, tzinfo=None
    )
    yesterday = today - timedelta(days=1)

    with OEClient(api_key) as client:
        response = client.get_network_data(
            network_code="NEM",
            metrics=[DataMetric.POWER],
            interval="1h",
            date_start=yesterday,
            date_end=today,
            # Both kinds of solar generation.
            fueltech=[
                UnitFueltechType.SOLAR_UTILITY,
                UnitFueltechType.SOLAR_ROOFTOP,
            ],
            # Split the results into one series per fueltech.
            secondary_grouping="fueltech",
        )

    series = [
        ChartSeries(
            name=result.columns.fueltech or result.name,
            data=[
                ChartPoint(x=point.timestamp, y=point.value or 0.0)
                for point in result.data
            ],
        )
        for network_series in response.data
        for result in network_series.results
    ]

    return ChartResponse(series=series).model_dump(mode="json")


if __name__ == "__main__":
    print(test())
