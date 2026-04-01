"""Helpers for bootstrapping and managing a private micromamba runtime."""

from __future__ import annotations

import os
import stat
import subprocess
import tarfile
import urllib.request

from core.config_manager import get_config
from core.tool_registry import micromamba_platform_subdir


class MicromambaError(Exception):
    """Raised when the managed micromamba runtime cannot be prepared."""


def default_tools_root() -> str:
    """Return the default per-user directory for managed tools."""

    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
        return os.path.join(base, "SenLab", "ProteinGUI", "tools")
    return os.path.join(os.path.expanduser("~"), ".senlab", "protein_gui", "tools")


class MicromambaManager:
    """Bootstrap and maintain the app-owned micromamba environment."""

    def __init__(self, tools_root: str | None = None, env_name: str | None = None):
        config = get_config()
        self.tools_root = tools_root or config.get("managed_tools_root", default_tools_root())
        self.env_name = env_name or config.get("managed_env_name", "bio-tools")
        self.root_prefix = self.tools_root
        self.download_dir = os.path.join(self.tools_root, "downloads")
        self.binary_root = os.path.join(self.tools_root, "micromamba")
        self._process: subprocess.Popen | None = None

    def get_env_path(self) -> str:
        return os.path.join(self.root_prefix, "envs", self.env_name)

    def get_env_bin_dir(self) -> str:
        if os.name == "nt":
            return os.path.join(self.get_env_path(), "Library", "bin")
        return os.path.join(self.get_env_path(), "bin")

    def get_managed_executable(self, executable_name: str) -> str | None:
        exe_name = executable_name + ".exe" if os.name == "nt" and not executable_name.endswith(".exe") else executable_name
        candidate = os.path.join(self.get_env_bin_dir(), exe_name)
        if os.path.exists(candidate):
            return candidate
        return None

    def get_micromamba_executable(self) -> str | None:
        exe_name = "micromamba.exe" if os.name == "nt" else "micromamba"
        direct = os.path.join(self.binary_root, "bin", exe_name)
        if os.path.exists(direct):
            return direct
        for root, _, files in os.walk(self.binary_root):
            if exe_name in files:
                return os.path.join(root, exe_name)
        return None

    def bootstrap(self, progress_cb=None, log_cb=None) -> str:
        """Download and unpack micromamba if needed, returning its executable."""

        existing = self.get_micromamba_executable()
        if existing:
            return existing

        os.makedirs(self.download_dir, exist_ok=True)
        os.makedirs(self.binary_root, exist_ok=True)

        platform_tag = micromamba_platform_subdir()
        archive_path = os.path.join(self.download_dir, f"micromamba-{platform_tag}.tar.bz2")
        url = f"https://micro.mamba.pm/api/micromamba/{platform_tag}/latest"

        if progress_cb:
            progress_cb(0, 100, "Downloading micromamba bootstrap...")
        if log_cb:
            log_cb(f"Downloading micromamba from {url}")

        try:
            with urllib.request.urlopen(url) as response, open(archive_path, "wb") as output:
                while True:
                    chunk = response.read(1024 * 256)
                    if not chunk:
                        break
                    output.write(chunk)
        except Exception as exc:
            raise MicromambaError(f"Failed to download micromamba: {exc}") from exc

        if progress_cb:
            progress_cb(40, 100, "Extracting micromamba...")

        try:
            with tarfile.open(archive_path, "r:*") as archive:
                archive.extractall(self.binary_root)
        except Exception as exc:
            raise MicromambaError(f"Failed to extract micromamba: {exc}") from exc

        exe_path = self.get_micromamba_executable()
        if not exe_path:
            raise MicromambaError("Micromamba bootstrap completed but executable was not found.")

        if os.name != "nt":
            current = os.stat(exe_path).st_mode
            os.chmod(exe_path, current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        if log_cb:
            log_cb(f"Micromamba ready at {exe_path}")
        if progress_cb:
            progress_cb(50, 100, "Micromamba bootstrap complete")
        return exe_path

    def env_exists(self) -> bool:
        return os.path.isdir(self.get_env_path())

    def cancel(self):
        """Cancel the active micromamba subprocess if one is running."""

        if self._process and self._process.poll() is None:
            self._process.terminate()

    def install_packages(self, packages, progress_cb=None, log_cb=None, cancel_check=None):
        """Create or update the shared env with the requested packages."""

        if not packages:
            return self.get_env_path()

        micromamba = self.bootstrap(progress_cb=progress_cb, log_cb=log_cb)
        os.makedirs(self.root_prefix, exist_ok=True)

        action = "install" if self.env_exists() else "create"
        cmd = [
            micromamba,
            action,
            "-y",
            "-r",
            self.root_prefix,
            "-n",
            self.env_name,
            "-c",
            "conda-forge",
            "-c",
            "bioconda",
            *packages,
        ]

        if progress_cb:
            progress_cb(55, 100, f"{'Updating' if action == 'install' else 'Creating'} managed tool environment...")
        if log_cb:
            log_cb("Running: " + " ".join(cmd))

        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        if self._process.stdout is not None:
            for line in self._process.stdout:
                if cancel_check and cancel_check():
                    self.cancel()
                    raise MicromambaError("Tool installation cancelled by user.")
                if log_cb:
                    log_cb(line.rstrip())

        return_code = self._process.wait()
        self._process = None
        if return_code != 0:
            raise MicromambaError(f"micromamba {action} failed with exit code {return_code}")

        if progress_cb:
            progress_cb(100, 100, "Managed tools installed")
        return self.get_env_path()


_micromamba_manager: MicromambaManager | None = None


def get_micromamba_manager() -> MicromambaManager:
    """Return the shared micromamba manager."""

    global _micromamba_manager
    if _micromamba_manager is None:
        _micromamba_manager = MicromambaManager()
    return _micromamba_manager
