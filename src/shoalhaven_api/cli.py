import typer
from typing import Annotated, Optional
from rich.console import Console
from rich.table import Table
import shoalhaven_api.db as db
import shoalhaven_api.meter as meter
import shoalhaven_api.reading as reading
from shoalhaven_api import faker_seed

# Init Typer and Rich console output
app = typer.Typer(
    help="Shoalhaven API CLI ~ manage meter sites, test connectivity, and run the API server."
)
console = Console()


@app.command()
def pushMeters(
    file: Annotated[
        str, typer.Argument(help="Path to the CSV file containing meter site data")
    ] = "./csv/meters.csv",
):
    """Pushes and updates all meters from CSV to MongoDB

    Reads the CSV, creates Meter objects, and upserts each one into
    the MongoDB collection."""
    meter.pushSites(file)


@app.command()
def allMeters():
    """Get all meters in MongoDB"""
    meters = db.meterFindAll({})

    table = Table(title="All Meters")
    table.add_column("Location")
    table.add_column("Class")
    table.add_column("Unit")

    for row in meters:
        table.add_row(row["location"]["fullAddress"], row["type"], row["unit"])
    console.print(table)


@app.command()
def queryMeters(
    type: Annotated[
        Optional[str], typer.Option(help="Filter by meter type (e.g. 'Admin Centre')")
    ] = None,
    unit: Annotated[
        Optional[str], typer.Option(help="Filter by unit/category (e.g. 'Council')")
    ] = None,
    location: Annotated[
        Optional[str], typer.Option(help="Partial location search")
    ] = None,
):
    """Queries MongoDB for Meters"""
    query = {}
    if type:
        query["type"] = type
    if unit:
        query["unit"] = unit
    if location:
        query["location.fullAddress"] = {"$regex": location, "$options": "i"}
    try:
        query = dict(query)
        meters = db.meterFindAll(query)

        table = Table(title=f"Queried Meters [{query}]")
        table.add_column("Location")
        table.add_column("Class")
        table.add_column("Unit")

        for row in meters:
            table.add_row(row["location"]["fullAddress"], row["type"], row["unit"])
        console.print(table)
    except TypeError:
        console.out("Query is not in a dict format!")


@app.command()
def pushReadings(
    file: Annotated[
        str, typer.Argument(help="Path to the CSV file containing readings data")
    ] = "./csv/readings.csv",
    granularity_minutes: Annotated[
        int,
        typer.Argument(
            help="Granularity of minutes to push. 60: hourly, 240: 4-hourly, 1440: daily"
        ),
    ] = 60,
    replace: Annotated[
        bool,
        typer.Argument(help="Replace all readings in cloud without upsert."),
    ] = False,
):
    """Pushes and updates all readings from CSV to MongoDB

    Reads the CSV, creates Reader objects, and upserts each one into
    the MongoDB collection."""
    reading.pushReadings(file, granularity_minutes, replace)


@app.command()
def ping():
    """Pings MongoDB cloud instance"""
    db.testPing()


@app.command()
def serve(
    host: Annotated[str, typer.Option(help="Bind address for the server")] = "0.0.0.0",
    port: Annotated[int, typer.Option(help="Port to listen on")] = 8000,
    reload: Annotated[
        bool, typer.Option(help="Enable auto-reload on file changes")
    ] = True,
):
    """Starts the FastAPI dev server"""
    import uvicorn

    uvicorn.run("shoalhaven_api.api:app", host=host, port=port, reload=reload)


@app.command()
def seedFake(
    meter_count: Annotated[int, typer.Option(help="Number of fake meters to generate")] = 10,
    years: Annotated[float, typer.Option(help="Years of data to generate")] = 2.0,
    granularity_minutes: Annotated[int, typer.Option(help="Granularity in minutes (e.g. 30)")] = 30,
    seed: Annotated[int, typer.Option(help="Random seed for reproducibility")] = 12345,
    replace_readings: Annotated[bool, typer.Option(help="Replace all readings collection")] = True,
    push_to_db: Annotated[bool, typer.Option(help="Push to MongoDB")] = True,
    csv_dir: Annotated[str, typer.Option(help="Directory to write CSVs")] = "./csv/fake",
):
    """Generate fake but geographically plausible Shoalhaven demo data using Faker.
    
    Creates meters with locations in Shoalhaven, generates 30-min readings over 2 years,
    writes CSVs in the expected format, and uses the same CLI ingestion logic (pushReadings)
    with the same granular filtering as CSV uploads."""
    faker_seed.seed_demo(
        meter_count=meter_count,
        years=years,
        granularity_minutes=granularity_minutes,
        seed=seed,
        replace_readings=replace_readings,
        push_to_db=push_to_db,
        csv_dir=csv_dir,
    )


@app.command()
def forecast(
    granularity: Annotated[
        str, typer.Option(help="Bucket size to forecast: hour (7 days ahead), day (30 days ahead) or both")
    ] = "both",
    size: Annotated[
        str, typer.Option(help="Timestral model size: 5M, 28M, 123M or 209M")
    ] = "5M",
    meter_id: Annotated[
        Optional[list[str]], typer.Option(help="Only forecast these meters (repeatable)")
    ] = None,
    backtest: Annotated[
        bool, typer.Option(help="Score the model against a seasonal-naive baseline")
    ] = True,
):
    """Forecasts meter usage with Timestral and saves it to MongoDB

    Needs the optional dependencies: uv sync --group forecast"""
    from shoalhaven_api import forecast as fc

    if granularity not in ("hour", "day", "both"):
        raise typer.BadParameter("granularity must be hour, day or both")

    model = fc.TimestralForecaster(size)
    granularities = ["hour", "day"] if granularity == "both" else [granularity]

    for g in granularities:
        docs = fc.run_forecasts(g, meter_id, model, backtest)

        table = Table(title=f"{model.name} | {g} forecast ({fc.GRANULARITY_CONFIG[g]['horizon']} {g}s)")
        table.add_column("Meter")
        table.add_column("Model MAE (kWh)", justify="right")
        table.add_column("Baseline MAE (kWh)", justify="right")
        table.add_column("Model MAPE", justify="right")
        table.add_column("Beats baseline", justify="center")

        wins = 0
        for doc in docs:
            score = doc["backtest"]
            if not score or score["modelMae"] is None:
                table.add_row(doc["meterId"], "-", "-", "-", "-")
                continue
            win = score["modelMae"] < score["baselineMae"]
            wins += win
            mape = f"{score['modelMape']:.1f}%" if score["modelMape"] is not None else "-"
            table.add_row(
                doc["meterId"],
                f"{score['modelMae']:.3f}",
                f"{score['baselineMae']:.3f}",
                mape,
                "[green]✓[/green]" if win else "[red]✗[/red]",
            )

        console.print(table)
        console.print(f"Saved {len(docs)} {g} forecasts" + (f", model wins on {wins}" if backtest else ""))


@app.command()
def generateFakeCsv(
    meter_count: Annotated[int, typer.Option(help="Number of fake meters to generate")] = 10,
    years: Annotated[float, typer.Option(help="Years of data to generate")] = 2.0,
    granularity_minutes: Annotated[int, typer.Option(help="Granularity in minutes (e.g. 30)")] = 30,
    seed: Annotated[int, typer.Option(help="Random seed")] = 12345,
    csv_dir: Annotated[str, typer.Option(help="Directory to write CSVs")] = "./csv/fake",
):
    """Generate fake CSVs only (meters and readings) without pushing to DB."""
    import os
    from datetime import datetime, timedelta, timezone

    from shoalhaven_api.faker_utils import (
        generate_meters_direct,
        generate_readings_dataframe,
        write_readings_csv,
    )

    os.makedirs(csv_dir, exist_ok=True)
    meters = generate_meters_direct(count=meter_count, seed=seed)
    meter_ids = [m.id for m in meters]

    # Write meters CSV in format compatible with loadSites: id,address,type,unit
    meters_csv = os.path.join(csv_dir, "meters.csv")
    with open(meters_csv, "w") as f:
        for m in meters:
            # For compatibility with existing loadSites which geocodes, we write address
            # But better to also provide pre-geocoded style - loadSites will call geocode
            # To truly bypass geocoding, users can use seedFake which pushes directly
            f.write(f"{m.id},{m.location.fullAddress},{m.type},{m.unit}\n")
    console.print(f"[green]Wrote meters CSV to {meters_csv}[/green]")

    end_date = datetime.now(timezone.utc).replace(tzinfo=None)
    start_date = end_date - timedelta(days=int(years * 365.25))
    df = generate_readings_dataframe(meter_ids, start_date, end_date, granularity_minutes, seed)
    readings_csv = os.path.join(csv_dir, "readings.csv")
    write_readings_csv(df, readings_csv)
    console.print(f"[green]Wrote readings CSV to {readings_csv}[/green]")


def main():
    app()


if __name__ == "__main__":
    main()
