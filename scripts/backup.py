"""Create a verified, point-in-time SQLite backup of OpsPilot's durable stores."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
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


def restore_backup(backup_dir: Path, target_dir: Path) -> Path:
    backup_dir = backup_dir.resolve()
    target_dir = Path(target_dir).absolute()
    if backup_dir == target_dir or backup_dir in target_dir.parents:
        raise ValueError("Choose a restore directory outside the backup being restored.")
    if target_dir.exists() or target_dir.is_symlink():
        raise FileExistsError("Restore target already exists; preserve it and choose a new data directory.")
    target_dir = target_dir.resolve()
    manifest_path = backup_dir / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("Backup manifest is missing or invalid.")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise ValueError("Backup manifest is missing or invalid.")
    files = manifest.get("files") if isinstance(manifest, dict) and manifest.get("format_version") == 1 else None
    allowed = {"opspilot.db", "workflow-checkpoints.sqlite"}
    if not isinstance(files, list) or not 1 <= len(files) <= len(allowed):
        raise ValueError("Backup manifest has an unsupported format.")
    names = [item.get("name") for item in files if isinstance(item, dict)]
    if len(names) != len(files) or len(set(names)) != len(names) or "opspilot.db" not in names or any(name not in allowed for name in names):
        raise ValueError("Backup manifest contains an invalid file list.")
    for item in files:
        name, size, expected_hash = item["name"], item.get("size_bytes"), item.get("sha256")
        source = backup_dir / name
        if source.is_symlink() or not source.is_file() or not isinstance(size, int) or isinstance(size, bool) or size != source.stat().st_size:
            raise ValueError("Backup file is missing or its size does not match the manifest.")
        if not isinstance(expected_hash, str) or len(expected_hash) != 64 or any(char not in "0123456789abcdef" for char in expected_hash):
            raise ValueError("Backup manifest contains an invalid checksum.")
        digest = hashlib.sha256()
        with source.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != expected_hash:
            raise ValueError("Backup checksum does not match: " + name)
        uri = "file:" + quote(source.as_posix(), safe="/:\\") + "?mode=ro"
        try:
            with closing(sqlite3.connect(uri, uri=True, timeout=15)) as con:
                if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Backup database failed its integrity check: " + name)
        except sqlite3.DatabaseError as error:
            raise ValueError("Backup database is unreadable: " + name) from error

    target_dir.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(dir=target_dir.parent, prefix=".opspilot-restore-"))
    try:
        for item in files:
            source, destination = backup_dir / item["name"], stage / item["name"]
            shutil.copyfile(source, destination)
            if os.name != "nt":
                destination.chmod(0o600)
        os.rename(stage, target_dir)
        return target_dir
    except Exception:
        if stage.exists():
            shutil.rmtree(stage)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path(os.environ.get("OPSPILOT_DATA_DIR", ROOT / "data")))
    parser.add_argument("--output-dir", type=Path, default=ROOT / "backups")
    parser.add_argument("--restore-from", type=Path, help="Restore a verified backup into a new, nonexistent data directory.")
    args = parser.parse_args()
    print(restore_backup(args.restore_from, args.data_dir) if args.restore_from else create_backup(args.data_dir, args.output_dir))


if __name__ == "__main__":
    main()
