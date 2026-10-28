"""Copy a quiescent OpsPilot SQLite operational store into an empty PostgreSQL store."""

from __future__ import annotations

import argparse
import os
import sqlite3
from contextlib import closing
from pathlib import Path

import app

TABLES = (
    "schema_migrations", "services", "scenarios", "users", "incidents", "sessions", "investigations",
    "incident_events", "comments", "alerts", "evaluations", "run_events", "evidence",
    "incident_observations", "lab_runs", "remediation_proposals", "approval_requests",
    "action_executions", "verification_results", "audit_events",
)
EMPTY_TARGET_TABLES = tuple(table for table in TABLES if table not in {"schema_migrations", "services", "scenarios"})


def migrate(source_dir: Path, target_url: str) -> dict[str, int]:
    source_dir = source_dir.expanduser().resolve()
    source_path = source_dir / "opspilot.db"
    if not target_url.startswith(("postgresql://", "postgres://")):
        raise ValueError("Set OPSPILOT_DATABASE_URL to a PostgreSQL connection URL.")
    if not source_path.is_file():
        raise FileNotFoundError(f"SQLite operational database not found: {source_path}")

    previous_url = os.environ.pop("OPSPILOT_DATABASE_URL", None)
    previous_data, previous_db = app.DATA, app.DB_PATH
    try:
        app.DATA = source_dir
        app.DB_PATH = source_path
        app.initialize()
        with closing(sqlite3.connect(source_path)) as source:
            source.row_factory = sqlite3.Row
            pending = source.execute("SELECT COUNT(*) FROM investigations WHERE status IN ('running','failed')").fetchone()[0]
            if pending:
                raise ValueError("Complete or resolve every running/failed investigation before migrating its workflow state.")

            os.environ["OPSPILOT_DATABASE_URL"] = target_url
            app.initialize()
            counts = {}
            with app.db() as target:
                occupied = {table: target.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in EMPTY_TARGET_TABLES}
                if any(occupied.values()):
                    raise ValueError("The PostgreSQL target contains application records; migrate only into a fresh target.")
                for table in TABLES:
                    columns = [row["name"] for row in source.execute(f"PRAGMA table_info({table})")]
                    if not columns:
                        raise ValueError(f"The SQLite source is missing the {table} table.")
                    column_list = ",".join(columns)
                    conflict = " ON CONFLICT DO NOTHING" if table == "schema_migrations" else ""
                    if table in {"services", "scenarios"}:
                        updates = ",".join(f"{column}=EXCLUDED.{column}" for column in columns if column != "id")
                        conflict = f" ON CONFLICT(id) DO UPDATE SET {updates}"
                    statement = f"INSERT INTO {table} ({column_list}) VALUES ({','.join('?' for _ in columns)}){conflict}"
                    cursor = source.execute(f"SELECT {column_list} FROM {table}")
                    count = 0
                    while rows := cursor.fetchmany(1000):
                        target.executemany(statement, [tuple(row) for row in rows])
                        count += len(rows)
                    counts[table] = count
            return counts
    finally:
        if previous_url is not None:
            os.environ["OPSPILOT_DATABASE_URL"] = previous_url
        else:
            os.environ.pop("OPSPILOT_DATABASE_URL", None)
        app.DATA, app.DB_PATH = previous_data, previous_db


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=app.DATA,
        help="SQLite data directory (default: %(default)s)")
    args = parser.parse_args(argv)
    target_url = os.environ.get("OPSPILOT_DATABASE_URL", "")
    try:
        counts = migrate(args.source_dir, target_url)
    except (FileNotFoundError, ValueError, OSError) as error:
        parser.error(str(error))
    print("Migrated SQLite operational records to PostgreSQL:")
    for table, count in counts.items():
        if count:
            print(f"  {table}: {count}")
    print("The SQLite source was preserved. Configure the same PostgreSQL URL for LangGraph checkpoints or set an explicit checkpoint URL.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
