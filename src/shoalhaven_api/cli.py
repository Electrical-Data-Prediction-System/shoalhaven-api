import typer
from rich.console import Console
from rich.table import Table
import shoalhaven_api.db as db
import shoalhaven_api.meter as meter

# Init Typer and Rich console output
app = typer.Typer()
console = Console()


@app.command()
def pushMeters(file: str = "flow-site-details.csv"):
    """Pushes and updates all meters in file"""
    meter.pushSites(file)


@app.command()
def ping():
    """Pings MongoDB cloud instance"""
    db.testPing()


@app.command()
def serve(
    host: str = "0.0.0.0",
    port: int = 8000,
    reload: bool = True,
):
    """Starts the FastAPI dev server"""
    import uvicorn

    uvicorn.run("shoalhaven_api.api:app", host=host, port=port, reload=reload)


def main():
    app()


if __name__ == "__main__":
    main()
