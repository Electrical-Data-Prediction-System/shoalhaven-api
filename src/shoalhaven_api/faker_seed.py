import os
from datetime import datetime, timedelta, timezone

from rich.console import Console

from shoalhaven_api import db
from shoalhaven_api.faker_utils import (
    generate_meters_direct,
    generate_readings_dataframe,
    write_readings_csv,
)
from shoalhaven_api import reading

console = Console()


def seed_demo(
    meter_count: int = 10,
    years: float = 2.0,
    granularity_minutes: int = 30,
    seed: int = 12345,
    replace_readings: bool = True,
    push_to_db: bool = True,
    csv_dir: str = "./csv/fake",
):
    os.makedirs(csv_dir, exist_ok=True)

    # Generate meters directly (bypass geocoding API calls)
    meters = generate_meters_direct(count=meter_count, seed=seed)
    meter_ids = [m.id for m in meters]

    console.print(f"[green]Generated {len(meters)} fake meters[/green]")

    if push_to_db:
        console.print("[cyan]Pushing meters to DB...[/cyan]")
        for m in meters:
            db.meterUpsert({"_id": m.id}, m.to_dict())
        console.print("[green]Meters pushed[/green]")

    # Generate readings for last N years
    end_date = datetime.now(timezone.utc).replace(tzinfo=None)  # naive for CSV format matching
    start_date = end_date - timedelta(days=int(years * 365.25))
    console.print(f"[cyan]Generating {granularity_minutes}min readings from {start_date} to {end_date}[/cyan]")

    df = generate_readings_dataframe(meter_ids, start_date, end_date, granularity_minutes, seed)
    readings_csv = os.path.join(csv_dir, "readings.csv")
    write_readings_csv(df, readings_csv)
    console.print(f"[green]Wrote readings CSV to {readings_csv} ({len(df)} rows)[/green]")

    if push_to_db:
        console.print("[cyan]Pushing readings via CLI logic (granularity filter applied)...[/cyan]")
        reading.pushReadings(readings_csv, granularity_minutes, replace_readings)
        console.print("[green]Readings pushed[/green]")

    console.print("[bold green]Done seeding demo data![/bold green]")
    return meter_ids
