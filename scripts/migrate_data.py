"""Explicit, non-destructive SQLite migration between renamed installations."""
import argparse
from contextlib import closing
from pathlib import Path
import shutil
import sqlite3


def migrate(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not source.is_file() or source == destination or destination.exists():
        raise ValueError("Source must exist and destination must not exist")
    settings = source.with_suffix(".settings.json")
    target_settings = destination.with_suffix(".settings.json")
    if settings.exists() and target_settings.exists():
        raise ValueError("Destination settings already exist")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation avoids silently overwriting a concurrently created database.
    with destination.open("xb"):
        pass
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as src:
        with closing(sqlite3.connect(str(destination))) as dst:
            src.backup(dst)
            if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Database integrity check failed")
    if settings.exists():
        with settings.open("rb") as src, target_settings.open("xb") as dst:
            shutil.copyfileobj(src, dst)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source")
    parser.add_argument("destination")
    args = parser.parse_args()
    migrate(args.source, args.destination)
    print("Copied database and settings. Original files were preserved.")
