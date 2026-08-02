import typer
from typing import Annotated, Optional
from rich.console import Console
from rich.table import Table
import shoalhaven_api.db as db
import shoalhaven_api.meter as meter
import shoalhaven_api.reading as reading

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
):
    """Pushes and updates all readings from CSV to MongoDB

    Reads the CSV, creates Reader objects, and upserts each one into
    the MongoDB collection."""
    reading.pushReadings(file)


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


def main():
    app()


if __name__ == "__main__":
    main()
