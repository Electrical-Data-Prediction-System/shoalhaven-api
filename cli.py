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
    meter.pushSites(file)


@app.command()
def ping():
    db.testPing()


if __name__ == "__main__":
    app()
