"""Build a CLI and API source bundle without the browser UI or project docs."""

from __future__ import annotations

import argparse
import shutil
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "opspilot-cli"
SCRIPT_FILES = tuple(Path("scripts") / name for name in (
    "__init__.py", "accounts.py", "backup.py", "cli.py", "evaluate.py", "migrate_to_postgres.py", "smoke_load.py"))
FIXED_FILES = (Path("app.py"), Path("requirements.txt")) + SCRIPT_FILES


def source_files() -> tuple[Path, ...]:
    backend = tuple(sorted(Path("backend").glob("*.py")))
    return FIXED_FILES + backend


def build(output: Path) -> Path:
    output = output.expanduser().resolve()
    archive = Path(str(output) + ".zip")
    if output.exists() or archive.exists():
        raise FileExistsError(f"Output already exists; remove it first: {output} or {archive}")

    files = source_files()
    missing = [path.as_posix() for path in files if not (ROOT / path).is_file()]
    if missing:
        raise FileNotFoundError("Required package sources are missing: " + ", ".join(missing))

    output.mkdir(parents=True)
    try:
        for relative in files:
            target = output / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)

        included = {path.relative_to(output).as_posix() for path in output.rglob("*") if path.is_file()}
        expected = {path.as_posix() for path in files}
        if included != expected:
            raise RuntimeError(f"Package file set mismatch: missing={expected - included}, extra={included - expected}")

        with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as package_zip:
            for relative in sorted(files):
                package_zip.write(output / relative, (Path(PACKAGE_NAME) / relative).as_posix())
        with zipfile.ZipFile(archive) as package_zip:
            archived = set(package_zip.namelist())
        expected_archived = {(Path(PACKAGE_NAME) / relative).as_posix() for relative in files}
        if archived != expected_archived:
            raise RuntimeError("The generated ZIP does not match the source bundle.")
    except Exception:
        shutil.rmtree(output)
        archive.unlink(missing_ok=True)
        raise
    return archive


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "opspilot-cli",
        help="new package directory (the matching .zip is written beside it)")
    args = parser.parse_args(argv)
    try:
        archive = build(args.output)
    except (FileExistsError, FileNotFoundError, OSError, RuntimeError) as exc:
        parser.error(str(exc))
    print(f"Package folder: {Path(args.output).expanduser().resolve()}")
    print(f"Package archive: {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
