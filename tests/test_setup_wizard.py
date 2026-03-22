"""Tests for setup_wizard.py tool discovery"""
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
