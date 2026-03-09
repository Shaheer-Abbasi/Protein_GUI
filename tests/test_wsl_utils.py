"""Tests for core/wsl_utils.py -- the cross-platform abstraction layer"""
import sys
import subprocess
from unittest.mock import patch, MagicMock
import pytest

from core.wsl_utils import (
    is_windows,
    warmup_wsl,
    is_wsl_available,
    check_wsl_command,
    run_wsl_command,
    convert_path_for_tool,
    windows_path_to_wsl,
    wsl_path_to_windows,
    check_mmseqs_installation,
    check_blastdbcmd_installation,
    get_disk_space_wsl,
    get_platform_tool_install_hint,
    get_platform_name,
    run_command_live,
    WSLError,
)


# ── Platform detection ──────────────────────────────────────────────

class TestIsWindows:
    def test_returns_bool(self):
        assert isinstance(is_windows(), bool)

    @patch("core.wsl_utils.sys")
    def test_true_on_win32(self, mock_sys):
        mock_sys.platform = "win32"
        # Re-import to pick up patched value
        from core import wsl_utils
        assert wsl_utils.is_windows() is True

    @patch("core.wsl_utils.sys")
    def test_false_on_darwin(self, mock_sys):
        mock_sys.platform = "darwin"
        from core import wsl_utils
        assert wsl_utils.is_windows() is False


# ── warmup_wsl ──────────────────────────────────────────────────────

class TestWarmupWsl:
    @patch("core.wsl_utils.is_windows", return_value=False)
    @patch("core.wsl_utils.subprocess.run")
    def test_noop_on_non_windows(self, mock_run, _):
        warmup_wsl()
        mock_run.assert_not_called()

    @patch("core.wsl_utils.is_windows", return_value=True)
    @patch("core.wsl_utils.subprocess.run")
    def test_calls_wsl_on_windows(self, mock_run, _):
        warmup_wsl()
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == "wsl"


# ── is_wsl_available ────────────────────────────────────────────────

class TestIsWslAvailable:
    @patch("core.wsl_utils.is_windows", return_value=False)
    def test_always_true_on_non_windows(self, _):
        assert is_wsl_available() is True

    @patch("core.wsl_utils.is_windows", return_value=True)
    @patch("core.wsl_utils.subprocess.run")
    def test_true_when_wsl_status_succeeds(self, mock_run, _):
        mock_run.return_value = MagicMock(returncode=0)
        assert is_wsl_available() is True

    @patch("core.wsl_utils.is_windows", return_value=True)
    @patch("core.wsl_utils.subprocess.run", side_effect=FileNotFoundError)
    def test_false_when_wsl_not_found(self, mock_run, _):
        assert is_wsl_available() is False


# ── check_wsl_command ───────────────────────────────────────────────

class TestCheckWslCommand:
    @patch("core.wsl_utils.is_windows", return_value=False)
    @patch("core.wsl_utils.shutil.which", return_value="/usr/local/bin/mmseqs")
    def test_native_found(self, mock_which, _):
        exists, path = check_wsl_command("mmseqs")
        assert exists is True
        assert path == "/usr/local/bin/mmseqs"

    @patch("core.wsl_utils.is_windows", return_value=False)
    @patch("core.wsl_utils.shutil.which", return_value=None)
    def test_native_not_found(self, mock_which, _):
        exists, path = check_wsl_command("nonexistent_tool")
        assert exists is False
        assert path is None

    @patch("core.wsl_utils.is_windows", return_value=True)
    @patch("core.wsl_utils.subprocess.run")
    def test_wsl_found(self, mock_run, _):
        mock_run.return_value = MagicMock(returncode=0, stdout="/usr/bin/mmseqs\n")
        exists, path = check_wsl_command("mmseqs")
        assert exists is True
        assert path == "/usr/bin/mmseqs"

    @patch("core.wsl_utils.is_windows", return_value=True)
    @patch("core.wsl_utils.subprocess.run")
    def test_wsl_not_found(self, mock_run, _):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        exists, path = check_wsl_command("mmseqs")
        assert exists is False
        assert path is None


# ── run_wsl_command ─────────────────────────────────────────────────

class TestRunWslCommand:
    @patch("core.wsl_utils.is_windows", return_value=False)
    @patch("core.wsl_utils.subprocess.run")
    def test_native_string_command(self, mock_run, _):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok\n", stderr="")
        result = run_wsl_command("echo ok", timeout=5)
        cmd = mock_run.call_args[0][0]
        assert cmd == ["bash", "-c", "echo ok"]
        assert result.returncode == 0

    @patch("core.wsl_utils.is_windows", return_value=False)
    @patch("core.wsl_utils.subprocess.run")
    def test_native_list_command(self, mock_run, _):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok\n", stderr="")
        result = run_wsl_command(["echo", "ok"], timeout=5)
        cmd = mock_run.call_args[0][0]
        assert cmd == ["echo", "ok"]

    @patch("core.wsl_utils.is_windows", return_value=True)
    @patch("core.wsl_utils.is_wsl_available", return_value=True)
    @patch("core.wsl_utils.subprocess.run")
    def test_windows_string_command(self, mock_run, *_):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok\n", stderr="")
        run_wsl_command("echo ok", timeout=5)
        cmd = mock_run.call_args[0][0]
        assert cmd == ["wsl", "bash", "-c", "echo ok"]

    @patch("core.wsl_utils.is_windows", return_value=True)
    @patch("core.wsl_utils.is_wsl_available", return_value=False)
    def test_windows_raises_when_no_wsl(self, *_):
        with pytest.raises(WSLError, match="WSL is not available"):
            run_wsl_command("echo ok")

    @patch("core.wsl_utils.is_windows", return_value=False)
    @patch("core.wsl_utils.subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 5))
    def test_timeout_raises_wsl_error(self, *_):
        with pytest.raises(WSLError, match="timed out"):
            run_wsl_command("sleep 100", timeout=5)


# ── Path conversion ─────────────────────────────────────────────────

class TestPathConversion:
    @patch("core.wsl_utils.is_windows", return_value=False)
    def test_convert_path_identity_on_non_windows(self, _):
        p = "/Users/me/data/file.fasta"
        assert convert_path_for_tool(p) == p

    @patch("core.wsl_utils.is_windows", return_value=True)
    def test_convert_path_to_wsl_on_windows(self, _):
        assert convert_path_for_tool(r"E:\Projects\file.txt") == "/mnt/e/Projects/file.txt"

    @patch("core.wsl_utils.is_windows", return_value=True)
    def test_windows_path_to_wsl_drive(self, _):
        assert windows_path_to_wsl(r"C:\Users\test\file.txt") == "/mnt/c/Users/test/file.txt"

    @patch("core.wsl_utils.is_windows", return_value=True)
    def test_windows_path_to_wsl_forward_slashes(self, _):
        assert windows_path_to_wsl("D:/data/db") == "/mnt/d/data/db"

    @patch("core.wsl_utils.is_windows", return_value=False)
    def test_windows_path_to_wsl_noop_on_mac(self, _):
        p = "/some/native/path"
        assert windows_path_to_wsl(p) == p

    @patch("core.wsl_utils.is_windows", return_value=True)
    def test_wsl_path_to_windows(self, _):
        assert wsl_path_to_windows("/mnt/e/Projects/file.txt") == r"E:\Projects\file.txt"

    @patch("core.wsl_utils.is_windows", return_value=True)
    def test_wsl_path_to_windows_no_remaining(self, _):
        assert wsl_path_to_windows("/mnt/c/") == "C:\\"

    @patch("core.wsl_utils.is_windows", return_value=False)
    def test_wsl_path_to_windows_noop_on_mac(self, _):
        p = "/some/native/path"
        assert wsl_path_to_windows(p) == p


# ── Tool installation checks ────────────────────────────────────────

class TestToolChecks:
    @patch("core.wsl_utils.is_windows", return_value=False)
    @patch("core.wsl_utils.check_wsl_command", return_value=(True, "/usr/local/bin/mmseqs"))
    @patch("core.wsl_utils.run_wsl_command")
    def test_check_mmseqs_installed(self, mock_run, *_):
        mock_run.return_value = MagicMock(returncode=0, stdout="15.6f452\n")
        installed, version, path = check_mmseqs_installation()
        assert installed is True
        assert version == "15.6f452"
        assert path == "/usr/local/bin/mmseqs"

    @patch("core.wsl_utils.is_windows", return_value=False)
    @patch("core.wsl_utils.check_wsl_command", return_value=(False, None))
    def test_check_mmseqs_not_installed(self, *_):
        installed, version, path = check_mmseqs_installation()
        assert installed is False
        assert version is None

    @patch("core.wsl_utils.is_windows", return_value=False)
    @patch("core.wsl_utils.check_wsl_command", return_value=(True, "/usr/local/bin/blastdbcmd"))
    @patch("core.wsl_utils.run_wsl_command")
    def test_check_blastdbcmd_installed(self, mock_run, *_):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="blastdbcmd: 2.17.0+\nPackage: blast 2.17.0\n"
        )
        installed, version, path = check_blastdbcmd_installation()
        assert installed is True
        assert "2.17.0" in version


# ── get_disk_space_wsl ───────────────────────────────────────────────

class TestGetDiskSpace:
    @patch("core.wsl_utils.is_windows", return_value=False)
    def test_native_disk_space(self, _):
        import tempfile
        avail, total = get_disk_space_wsl(tempfile.gettempdir())
        assert avail is not None
        assert total is not None
        assert avail > 0
        assert total > avail


# ── get_platform_tool_install_hint ──────────────────────────────────

class TestInstallHints:
    @patch("core.wsl_utils.is_windows", return_value=False)
    @patch("core.wsl_utils.sys")
    def test_macos_mmseqs_hint(self, mock_sys, _):
        mock_sys.platform = "darwin"
        hint = get_platform_tool_install_hint("mmseqs")
        assert "brew" in hint.lower() or "conda" in hint.lower()

    @patch("core.wsl_utils.is_windows", return_value=True)
    def test_windows_clustalo_hint(self, _):
        hint = get_platform_tool_install_hint("clustalo")
        assert "wsl" in hint.lower()

    def test_unknown_tool_fallback(self):
        hint = get_platform_tool_install_hint("some_unknown_tool_xyz")
        assert "some_unknown_tool_xyz" in hint


# ── get_platform_name ────────────────────────────────────────────────

class TestGetPlatformName:
    @patch("core.wsl_utils.is_windows", return_value=True)
    def test_windows(self, _):
        assert "Windows" in get_platform_name()

    @patch("core.wsl_utils.is_windows", return_value=False)
    @patch("core.wsl_utils.sys")
    def test_macos(self, mock_sys, _):
        mock_sys.platform = "darwin"
        assert get_platform_name() == "macOS"


# ── run_command_live ─────────────────────────────────────────────────

class TestRunCommandLive:
    @patch("core.wsl_utils.is_windows", return_value=False)
    def test_returns_popen(self, _):
        proc = run_command_live("echo hello")
        assert proc is not None
        output = proc.stdout.read()
        proc.wait()
        assert "hello" in output
