import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from scripts.backup import create_backup, restore_backup


class BackupTests(unittest.TestCase):
    def test_online_backup_preserves_both_stores_and_manifest_hashes(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            data, output = base / "data", base / "backups"
            data.mkdir()
            for name in ("opspilot.db", "workflow-checkpoints.sqlite"):
                with closing(sqlite3.connect(data / name)) as con:
                    con.execute("CREATE TABLE marker(value TEXT NOT NULL)")
                    con.execute("INSERT INTO marker VALUES(?)", (name,))
                    con.commit()
            backup_dir = create_backup(data, output)
            manifest = json.loads((backup_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual({item["name"] for item in manifest["files"]}, {"opspilot.db", "workflow-checkpoints.sqlite"})
            for item in manifest["files"]:
                with closing(sqlite3.connect(backup_dir / item["name"])) as con:
                    self.assertEqual(con.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                    self.assertEqual(con.execute("SELECT value FROM marker").fetchone()[0], item["name"])

    def test_backup_cannot_be_written_under_the_live_data_directory(self):
        with tempfile.TemporaryDirectory() as root:
            data = Path(root) / "data"
            data.mkdir()
            con = sqlite3.connect(data / "opspilot.db")
            con.close()
            with self.assertRaises(ValueError):
                create_backup(data, data / "backups")

    def test_restore_verifies_and_recovers_both_stores_into_a_new_directory(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            data, output, restored = base / "data", base / "backups", base / "restored"
            data.mkdir()
            for name in ("opspilot.db", "workflow-checkpoints.sqlite"):
                with closing(sqlite3.connect(data / name)) as con:
                    con.execute("CREATE TABLE marker(value TEXT NOT NULL)")
                    con.execute("INSERT INTO marker VALUES(?)", (name,))
                    con.commit()
            backup_dir = create_backup(data, output)
            self.assertEqual(restore_backup(backup_dir, restored), restored)
            for name in ("opspilot.db", "workflow-checkpoints.sqlite"):
                with closing(sqlite3.connect(restored / name)) as con:
                    self.assertEqual(con.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                    self.assertEqual(con.execute("SELECT value FROM marker").fetchone()[0], name)

    def test_restore_rejects_tampering_and_never_overwrites_an_existing_target(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            data, output, restored = base / "data", base / "backups", base / "restored"
            data.mkdir()
            with closing(sqlite3.connect(data / "opspilot.db")):
                pass
            backup_dir = create_backup(data, output)
            path = backup_dir / "opspilot.db"
            contents = path.read_bytes()
            path.write_bytes((b"0" if contents[:1] != b"0" else b"1") + contents[1:])
            with self.assertRaisesRegex(ValueError, "checksum"):
                restore_backup(backup_dir, restored)
            self.assertFalse(restored.exists())

            restored.mkdir()
            marker = restored / "keep.txt"
            marker.write_text("preserve", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                restore_backup(backup_dir, restored)
            self.assertEqual(marker.read_text(encoding="utf-8"), "preserve")


if __name__ == "__main__":
    unittest.main()
