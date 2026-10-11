import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from backend.asgi import web_file
from scripts.package_cli import PACKAGE_NAME, build, source_files


class CliPackageTests(unittest.TestCase):
    def test_bundle_contains_runtime_sources_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "opspilot-cli"
            archive = build(output)
            expected = {path.as_posix() for path in source_files()}
            actual = {path.relative_to(output).as_posix() for path in output.rglob("*") if path.is_file()}
            self.assertEqual(actual, expected)
            with zipfile.ZipFile(archive) as package:
                self.assertEqual(set(package.namelist()), {f"{PACKAGE_NAME}/{path}" for path in expected})
            self.assertFalse(any(path.lower().endswith(("readme.md", ".html", ".css", ".js")) for path in expected))

    def test_builder_refuses_to_overwrite_existing_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "opspilot-cli"
            output.mkdir()
            marker = output / "keep.txt"
            marker.write_text("keep", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                build(output)
            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")

    def test_api_reports_missing_browser_ui_cleanly(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch("backend.asgi.core.WEB", Path(temp_dir)):
            response = web_file("intro.html")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.body, b'{"error":{"code":"ui_not_installed","message":"The browser UI is not included in this package."}}')


if __name__ == "__main__":
    unittest.main()
