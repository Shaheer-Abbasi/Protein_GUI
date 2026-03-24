"""Tests for setup_wizard diagnostics behavior and helper discovery."""
import json
import sys
from unittest.mock import patch, MagicMock
import pytest

from setup_wizard import (
    is_windows,
    is_macos,
    find_blast,
    find_mmseqs,
    find_clustalo,
    find_blastdbcmd,
    check_command,
    collect_diagnostics,
    main,
    get_install_hint,
)


class TestPlatformDetection:
    def test_is_windows(self):
        assert isinstance(is_windows(), bool)

    def test_is_macos(self):
        assert isinstance(is_macos(), bool)

    def test_consistent_with_sys(self):
        assert is_windows() == (sys.platform == "win32")
        assert is_macos() == (sys.platform == "darwin")


class TestCheckCommand:
    @patch("setup_wizard.subprocess.run")
    def test_returns_true_on_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        assert check_command(["echo", "test"]) is True

    @patch("setup_wizard.subprocess.run", side_effect=FileNotFoundError)
    def test_returns_false_on_missing(self, mock_run):
        assert check_command(["nonexistent"]) is False


class TestFindBlast:
    @patch("setup_wizard.is_windows", return_value=False)
    @patch("setup_wizard.is_macos", return_value=True)
    @patch("setup_wizard.shutil.which", return_value="/opt/homebrew/bin/blastp")
    def test_found_in_path_macos(self, *_):
        result = find_blast()
        assert result is not None
        assert "blastp" in result

    @patch("setup_wizard.is_windows", return_value=False)
    @patch("setup_wizard.is_macos", return_value=True)
    @patch("setup_wizard.os.path.exists", return_value=False)
    @patch("setup_wizard.shutil.which", return_value=None)
    @patch("setup_wizard.check_command", return_value=False)
    def test_not_found(self, *_):
        result = find_blast()
        assert result is None


class TestFindMmseqs:
    @patch("setup_wizard.is_windows", return_value=False)
    @patch("setup_wizard.is_macos", return_value=True)
    @patch("setup_wizard.shutil.which", return_value="/opt/homebrew/bin/mmseqs")
    def test_found_in_path(self, *_):
        result = find_mmseqs()
        assert result is not None
        assert "mmseqs" in result


class TestFindClustalo:
    @patch("setup_wizard.shutil.which", return_value="/usr/local/bin/clustalo")
    def test_found(self, _):
        result = find_clustalo()
        assert result == "/usr/local/bin/clustalo"

    @patch("setup_wizard.shutil.which", return_value=None)
    @patch("setup_wizard.is_macos", return_value=False)
    @patch("setup_wizard.check_command", return_value=False)
    def test_not_found(self, *_):
        result = find_clustalo()
        assert result is None


class TestFindBlastdbcmd:
    @patch("setup_wizard.shutil.which", return_value="/usr/local/bin/blastdbcmd")
    def test_found(self, _):
        assert find_blastdbcmd() == "/usr/local/bin/blastdbcmd"

    @patch("setup_wizard.shutil.which", return_value=None)
    @patch("setup_wizard.check_command", return_value=False)
    def test_not_found(self, *_):
        assert find_blastdbcmd() is None


class TestGetInstallHint:
    @patch("setup_wizard.is_windows", return_value=False)
    @patch("setup_wizard.is_macos", return_value=True)
    def test_macos_blast(self, *_):
        hint = get_install_hint("blast")
        assert "brew" in hint.lower()

    @patch("setup_wizard.is_windows", return_value=True)
    @patch("setup_wizard.is_macos", return_value=False)
    def test_windows_mmseqs_wsl(self, *_):
        hint = get_install_hint("mmseqs_wsl")
        assert "wsl" in hint.lower()

    @patch("setup_wizard.is_windows", return_value=False)
    @patch("setup_wizard.is_macos", return_value=False)
    def test_linux_clustalo(self, *_):
        hint = get_install_hint("clustalo")
        assert "apt" in hint.lower()


class TestDiagnosticsMode:
    @patch("setup_wizard.ToolRuntime")
    def test_collect_diagnostics_uses_runtime_without_mutating_config(self, mock_runtime_cls, tmp_path):
        config_path = tmp_path / "config.json"
        original = {
            "tool_source_overrides": {"blastp": "system"},
            "preferred_tool_sources": ["managed", "system"],
        }
        config_path.write_text(json.dumps(original))

        runtime = MagicMock()
        runtime.get_tool_status.side_effect = lambda tool_id: MagicMock(
            installed=(tool_id == "blastp"),
            source="managed" if tool_id == "blastp" else "missing",
            version="1.0" if tool_id == "blastp" else None,
            executable_path=f"/managed/{tool_id}" if tool_id == "blastp" else None,
            error_message=None if tool_id == "blastp" else f"{tool_id} unavailable",
        )
        mock_runtime_cls.return_value = runtime

        diagnostics = collect_diagnostics(config_path=str(config_path))

        assert diagnostics["tool_source_overrides"] == {"blastp": "system"}
        assert diagnostics["preferred_tool_sources"] == ["managed", "system"]
        assert diagnostics["tools"]["blastp"]["installed"] is True
        assert diagnostics["tools"]["mmseqs"]["installed"] is False
        assert json.loads(config_path.read_text()) == original

    @patch("setup_wizard.input")
    @patch("setup_wizard.collect_diagnostics")
    def test_main_does_not_pause_by_default(self, mock_collect, mock_input, capsys):
        mock_collect.return_value = {
            "platform": "macOS",
            "platform_key": "darwin",
            "python_version": "3.11.0",
            "config_path": "/tmp/config.json",
            "python_dependencies": {"PyQt5": True, "Biopython": True},
            "managed_tools_root": "/tmp/tools",
            "managed_env_name": "bio-tools",
            "preferred_tool_sources": ["managed", "configured", "system", "wsl"],
            "tool_source_overrides": {},
            "wsl_available": None,
            "tools": {
                "blastp": {
                    "display_name": "BLASTP",
                    "installed": True,
                    "source": "managed",
                    "version": "blastp: 2.17.0+",
                    "executable_path": "/tmp/tools/envs/bio-tools/bin/blastp",
                    "error_message": None,
                    "managed_supported": True,
                    "install_hint": "Install from the app's Tools tab.",
                }
            },
            "databases": {
                "path": "/tmp/blast_databases",
                "exists": False,
                "databases": [],
            },
        }

        main([])

        mock_input.assert_not_called()
        captured = capsys.readouterr()
        assert "Runtime Diagnostics" in captured.out
