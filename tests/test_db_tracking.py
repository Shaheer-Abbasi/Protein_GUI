"""Tests for core/db_conversion_manager.py and core/installed_databases.py"""
import json
import os
import pytest

from core.db_conversion_manager import DatabaseConversionManager
from core.installed_databases import InstalledDatabase, InstalledDatabasesTracker


# ── DatabaseConversionManager ────────────────────────────────────────

class TestDatabaseConversionManager:
    def test_fresh_state(self, tmp_path):
        status_file = str(tmp_path / "status.json")
        mgr = DatabaseConversionManager(status_file=status_file)
        status = mgr.get_database_status("swissprot")
        assert status["status"] == "not_converted"

    def test_mark_converting(self, tmp_path):
        status_file = str(tmp_path / "status.json")
        mgr = DatabaseConversionManager(status_file=status_file)
        mgr.mark_converting("swissprot", "/src/path", "/tgt/path")
        assert mgr.is_converting("swissprot")
        assert not mgr.is_converted("swissprot")

    def test_mark_converted(self, tmp_path):
        status_file = str(tmp_path / "status.json")
        # Create a fake DB file so is_converted() can verify it exists
        fake_db = tmp_path / "swissprot_db"
        fake_db.write_text("fake")

        mgr = DatabaseConversionManager(status_file=status_file)
        mgr.mark_converting("swissprot", "/src", str(fake_db))
        mgr.mark_converted("swissprot", str(fake_db))
        assert mgr.is_converted("swissprot")
        assert not mgr.is_converting("swissprot")

    def test_mark_failed(self, tmp_path):
        status_file = str(tmp_path / "status.json")
        mgr = DatabaseConversionManager(status_file=status_file)
        mgr.mark_converting("testdb", "/src", "/tgt")
        mgr.mark_failed("testdb", "disk full")
        status = mgr.get_database_status("testdb")
        assert status["status"] == "failed"
        assert "disk full" in status["error"]

    def test_reset_status(self, tmp_path):
        status_file = str(tmp_path / "status.json")
        mgr = DatabaseConversionManager(status_file=status_file)
        mgr.mark_converting("testdb", "/src", "/tgt")
        mgr.mark_failed("testdb", "error")
        mgr.reset_status("testdb")
        assert mgr.get_database_status("testdb")["status"] == "not_converted"

    def test_get_converted_databases(self, tmp_path):
        status_file = str(tmp_path / "status.json")
        fake_db = tmp_path / "db1"
        fake_db.write_text("fake")

        mgr = DatabaseConversionManager(status_file=status_file)
        mgr.mark_converting("db1", "/src", str(fake_db))
        mgr.mark_converted("db1", str(fake_db))
        assert "db1" in mgr.get_converted_databases()

    def test_persistence(self, tmp_path):
        status_file = str(tmp_path / "status.json")
        fake_db = tmp_path / "mydb"
        fake_db.write_text("fake")

        mgr1 = DatabaseConversionManager(status_file=status_file)
        mgr1.mark_converting("mydb", "/src", str(fake_db))
        mgr1.mark_converted("mydb", str(fake_db))

        mgr2 = DatabaseConversionManager(status_file=status_file)
        assert mgr2.is_converted("mydb")


# ── InstalledDatabase ────────────────────────────────────────────────

class TestInstalledDatabase:
    def test_to_dict_roundtrip(self):
        db = InstalledDatabase(
            id="swissprot",
            display_name="SwissProt",
            version="2024.1",
            install_path="/data/swissprot",
            installed_date="2024-01-01T00:00:00",
            tool_formats=["blast", "mmseqs"],
            size_gb=1.5,
            source_type="s3",
        )
        d = db.to_dict()
        restored = InstalledDatabase.from_dict(d)
        assert restored.id == "swissprot"
        assert restored.size_gb == 1.5
        assert "blast" in restored.tool_formats

    def test_is_valid_checks_path(self, tmp_path):
        existing = tmp_path / "db"
        existing.write_text("data")
        db = InstalledDatabase(
            id="t", display_name="t", version="1", install_path=str(existing),
            installed_date="", tool_formats=[], size_gb=0, source_type="s3"
        )
        assert db.is_valid() is True

        db2 = InstalledDatabase(
            id="t", display_name="t", version="1", install_path="/no/such/path",
            installed_date="", tool_formats=[], size_gb=0, source_type="s3"
        )
        assert db2.is_valid() is False


# ── InstalledDatabasesTracker ────────────────────────────────────────

class TestInstalledDatabasesTracker:
    def test_add_and_get(self, tmp_path):
        tracker = InstalledDatabasesTracker(config_dir=str(tmp_path))
        db_path = str(tmp_path / "swissprot")
        os.makedirs(db_path)

        tracker.add("swissprot", "SwissProt", "2024.1", db_path,
                     ["blast"], 1.5, "s3")
        assert tracker.is_installed("swissprot")
        db = tracker.get("swissprot")
        assert db.display_name == "SwissProt"

    def test_remove(self, tmp_path):
        tracker = InstalledDatabasesTracker(config_dir=str(tmp_path))
        db_path = str(tmp_path / "testdb")
        os.makedirs(db_path)
        tracker.add("testdb", "Test", "1.0", db_path, ["blast"], 0.5, "s3")
        assert tracker.remove("testdb") is True
        assert not tracker.is_installed("testdb")

    def test_remove_nonexistent(self, tmp_path):
        tracker = InstalledDatabasesTracker(config_dir=str(tmp_path))
        assert tracker.remove("nope") is False

    def test_get_all(self, tmp_path):
        tracker = InstalledDatabasesTracker(config_dir=str(tmp_path))
        for name in ["db1", "db2"]:
            p = str(tmp_path / name)
            os.makedirs(p)
            tracker.add(name, name, "1.0", p, ["blast"], 0.1, "s3")
        assert len(tracker.get_all()) == 2

    def test_get_blast_databases(self, tmp_path):
        tracker = InstalledDatabasesTracker(config_dir=str(tmp_path))
        p1 = str(tmp_path / "blastdb")
        p2 = str(tmp_path / "mmdb")
        os.makedirs(p1)
        os.makedirs(p2)
        tracker.add("blastdb", "B", "1", p1, ["blast"], 1, "s3")
        tracker.add("mmdb", "M", "1", p2, ["mmseqs"], 1, "s3")
        assert len(tracker.get_blast_databases()) == 1
        assert len(tracker.get_mmseqs_databases()) == 1

    def test_cleanup_invalid(self, tmp_path):
        tracker = InstalledDatabasesTracker(config_dir=str(tmp_path))
        tracker.add("gone", "Gone", "1", "/no/such/path", ["blast"], 1, "s3")
        removed = tracker.cleanup_invalid()
        assert removed == 1
        assert not tracker.is_installed("gone")

    def test_persistence(self, tmp_path):
        p = str(tmp_path / "persist_db")
        os.makedirs(p)
        t1 = InstalledDatabasesTracker(config_dir=str(tmp_path))
        t1.add("persist", "P", "1", p, ["blast"], 0.5, "s3")

        t2 = InstalledDatabasesTracker(config_dir=str(tmp_path))
        assert t2.is_installed("persist")
