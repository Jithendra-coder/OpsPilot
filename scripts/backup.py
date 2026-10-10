"""Create a verified, point-in-time SQLite backup of OpsPilot's durable stores."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import tempfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]


def _copy_database(source: Path, destination: Path) -> None:
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".backup-", suffix=".sqlite", delete=False) as temp:
            temp_name = Path(temp.name)
        uri = "file:" + quote(source.as_posix(), safe="/:\\") + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=15)) as origin, closing(sqlite3.connect(temp_name)) as backup:
            origin.backup(backup, pages=256, sleep=0.05)
            if backup.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("SQLite integrity check failed for " + source.name)
        os.replace(temp_name, destination)
        if os.name != "nt":
            destination.chmod(0o600)
    finally:
        if temp_name and temp_name.exists():
            temp_name.unlink()


def create_backup(data_dir: Path, output_dir: Path) -> Path:
    data_dir, output_dir = data_dir.resolve(), output_dir.resolve()
    if output_dir == data_dir or data_dir in output_dir.parents:
        raise ValueError("Choose a backup directory outside the live data directory.")
    sources = [data_dir / "opspilot.db", data_dir / "workflow-checkpoints.sqlite"]
    sources = [source for source in sources if source.is_file()]
    if not (data_dir / "opspilot.db").is_file():
        raise FileNotFoundError("The incident database does not exist: " + str(data_dir / "opspilot.db"))
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc)
    destination = output_dir / ("opspilot-" + stamp.strftime("%Y%m%dT%H%M%S%fZ"))
    destination.mkdir()
    files = []
    try:
        for source in sources:
            target = destination / source.name
            _copy_database(source, target)
            digest = hashlib.sha256()
            with target.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            files.append({"name": target.name, "size_bytes": target.stat().st_size, "sha256": digest.hexdigest()})
        manifest = {"format_version": 1, "created_at": stamp.isoformat(timespec="microseconds").replace("+00:00", "Z"), "files": files}
        manifest_path = destination / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        if os.name != "nt":
            manifest_path.chmod(0o600)
        return destination
    except Exception:
        for item in destination.iterdir():
            item.unlink()
        destination.rmdir()
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path(os.environ.get("OPSPILOT_DATA_DIR", ROOT / "data")))
    parser.add_argument("--output-dir", type=Path, default=ROOT / "backups")
    args = parser.parse_args()
    print(create_backup(args.data_dir, args.output_dir))


if __name__ == "__main__":
    main()
