"""Tests for core/config_manager.py"""
import json
import pytest

from core.config_manager import ConfigManager


class TestConfigManager:
    def test_loads_from_file(self, sample_config):
        cm = ConfigManager(config_path=sample_config)
        assert cm.get("blast_path") == "blastp"
        assert cm.get("mmseqs_available") is True

    def test_defaults_when_no_file(self, tmp_path):
        cm = ConfigManager(config_path=str(tmp_path / "nonexistent.json"))
        assert cm.get("blast_path") == "blastp"
        assert cm.get("mmseqs_available") is False

    def test_get_with_default(self, tmp_path):
        cm = ConfigManager(config_path=str(tmp_path / "nonexistent.json"))
        assert cm.get("missing_key", "fallback") == "fallback"

    def test_set_and_save(self, tmp_path):
        config_path = str(tmp_path / "test_config.json")
        cm = ConfigManager(config_path=config_path)
        cm.set("blast_path", "/custom/blastp")
        assert cm.save() is True

        cm2 = ConfigManager(config_path=config_path)
        assert cm2.get("blast_path") == "/custom/blastp"

    def test_get_blast_path(self, sample_config):
        cm = ConfigManager(config_path=sample_config)
        assert cm.get_blast_path() == "blastp"

    def test_get_blastn_path_derived(self, tmp_path):
        config = {"blast_path": "/opt/ncbi/bin/blastp"}
        config_path = str(tmp_path / "config.json")
        with open(config_path, "w") as f:
            json.dump(config, f)

        cm = ConfigManager(config_path=config_path)
        assert cm.get_blastn_path() == "/opt/ncbi/bin/blastn"

    def test_get_blastn_path_bare_command(self, tmp_path):
        config = {"blast_path": "blastp"}
        config_path = str(tmp_path / "config.json")
        with open(config_path, "w") as f:
            json.dump(config, f)

        cm = ConfigManager(config_path=config_path)
        assert cm.get_blastn_path() == "blastn"

    def test_get_mmseqs_path(self, sample_config):
        cm = ConfigManager(config_path=sample_config)
        assert cm.get_mmseqs_path() == "mmseqs"

    def test_get_blast_db_dir(self, sample_config):
        cm = ConfigManager(config_path=sample_config)
        db_dir = cm.get_blast_db_dir()
        assert db_dir.endswith("blast_databases")

    def test_get_mmseqs_db_dir(self, sample_config):
        cm = ConfigManager(config_path=sample_config)
        db_dir = cm.get_mmseqs_db_dir()
        assert db_dir.endswith("mmseqs_databases")

    def test_handles_corrupt_json(self, tmp_path):
        config_path = tmp_path / "bad.json"
        config_path.write_text("{invalid json!!")
        cm = ConfigManager(config_path=str(config_path))
        assert cm.get("blast_path") == "blastp"
