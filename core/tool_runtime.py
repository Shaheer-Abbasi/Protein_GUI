"""Unified runtime for resolving and executing external bioinformatics tools."""

from __future__ import annotations

from dataclasses import dataclass
import os
import shutil
import subprocess

from core.config_manager import get_config
from core.micromamba_manager import get_micromamba_manager
from core.tool_registry import (
    ToolSpec,
    current_platform_key,
    get_tool_spec,
    get_tools_for_feature,
    is_managed_install_supported,
)
from core.tool_state import ToolStatus, get_tool_state_store
from core.wsl_utils import (
    WSLError,
    check_wsl_command,
    convert_path_for_tool,
    run_wsl_command,
)


@dataclass(frozen=True)
class ToolResolution:
    """Concrete resolution for launching a tool."""

    tool_id: str
    source: str
    executable: str | None
    backend: str


class ToolRuntimeError(Exception):
    """Raised when a requested tool cannot be resolved or executed."""


class ToolRuntime:
    """Resolve tools across managed, configured, system, and WSL sources."""

    def __init__(self):
        self.config = get_config()
        self.manager = get_micromamba_manager()
        self.state_store = get_tool_state_store()

    def _get_configured_command(self, tool_id: str) -> str | None:
        if tool_id == "blastp":
            return self.config.get_blast_path()
        if tool_id == "blastn":
            return self.config.get_blastn_path()
        if tool_id == "mmseqs":
            return self.config.get_mmseqs_path()
        if tool_id == "blastdbcmd":
            return self.config.get_blastdbcmd_path()
        if tool_id == "clustalo":
            return self.config.get_clustalo_path()
        if tool_id == "mafft":
            return self.config.get_mafft_path()
        if tool_id == "muscle":
            return self.config.get_muscle_path()
        if tool_id == "famsa":
            return self.config.get_famsa_path()
        return None

    def _resolve_managed(self, tool_id: str, spec: ToolSpec) -> ToolResolution | None:
        if not is_managed_install_supported(tool_id):
            return None
        for executable in spec.executables:
            candidate = self.manager.get_managed_executable(executable)
            if candidate:
                return ToolResolution(tool_id, "managed", candidate, "native")
        return None

    def _resolve_configured(self, tool_id: str, spec: ToolSpec) -> ToolResolution | None:
        configured = self._get_configured_command(tool_id)
        if not configured:
            return None

        # Treat explicit paths as configured. Bare command names fall back to system discovery.
        has_path_part = os.path.sep in configured or (os.path.altsep and os.path.altsep in configured)
        if has_path_part:
            if os.path.exists(configured):
                return ToolResolution(tool_id, "configured", configured, "native")
            return None

        resolved = shutil.which(configured)
        if resolved:
            return ToolResolution(tool_id, "configured", resolved, "native")
        return None

    def _resolve_system(self, tool_id: str, spec: ToolSpec) -> ToolResolution | None:
        if current_platform_key() == "windows":
            return None
        for executable in spec.executables:
            resolved = shutil.which(executable)
            if resolved:
                return ToolResolution(tool_id, "system", resolved, "native")
        return None

    def _resolve_wsl(self, tool_id: str, spec: ToolSpec) -> ToolResolution | None:
        if current_platform_key() != "windows":
            return None
        for executable in spec.executables:
            exists, path = check_wsl_command(executable)
            if exists:
                return ToolResolution(tool_id, "wsl", executable, "wsl")
        return None

    def resolve_tool(self, tool_id: str) -> ToolResolution:
        """Resolve a tool according to the configured source preference order."""

        spec = get_tool_spec(tool_id)
        resolvers = {
            "managed": self._resolve_managed,
            "configured": self._resolve_configured,
            "system": self._resolve_system,
            "wsl": self._resolve_wsl,
        }
        overrides = self.config.get_tool_source_overrides()
        source_order = []
        override = overrides.get(tool_id)
        if override in resolvers:
            source_order.append(override)
        for source in self.config.get_preferred_tool_sources():
            if source in resolvers and source not in source_order:
                source_order.append(source)

        for source in source_order:
            resolver = resolvers[source]
            resolved = resolver(tool_id, spec)
            if resolved:
                return resolved
        return ToolResolution(tool_id, "missing", None, "missing")

    def prepare_path(self, resolution: ToolResolution, path: str) -> str:
        """Translate file paths for the selected backend."""

        if resolution.backend == "wsl":
            return convert_path_for_tool(path)
        return path

    def run_resolved(
        self,
        resolution: ToolResolution,
        args,
        *,
        timeout=None,
        check=False,
        capture_output=True,
        text=True,
    ):
        """Execute a previously resolved tool command."""

        if not resolution.executable:
            raise ToolRuntimeError(f"Tool '{resolution.tool_id}' is not available")

        if resolution.backend == "wsl":
            result = run_wsl_command([resolution.executable, *args], timeout=timeout)
        else:
            result = subprocess.run(
                [resolution.executable, *args],
                timeout=timeout,
                capture_output=capture_output,
                text=text,
            )

        if check and result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode,
                [resolution.executable, *args],
                getattr(result, "stdout", None),
                getattr(result, "stderr", None),
            )
        return result

    def run_tool(self, tool_id: str, args, **kwargs):
        """Resolve and execute a tool in one step."""

        return self.run_resolved(self.resolve_tool(tool_id), args, **kwargs)

    def _read_version(self, resolution: ToolResolution, spec: ToolSpec) -> str | None:
        if not resolution.executable:
            return None
        try:
            result = self.run_resolved(resolution, list(spec.version_args), timeout=30)
            if result.returncode == 0:
                output = (result.stdout or result.stderr or "").strip()
                if output:
                    return output.splitlines()[0]
        except (ToolRuntimeError, subprocess.SubprocessError, WSLError):
            return None
        return None

    def get_tool_status(self, tool_id: str) -> ToolStatus:
        """Return the live status for a tool and persist it."""

        spec = get_tool_spec(tool_id)
        resolution = self.resolve_tool(tool_id)
        if resolution.source == "missing":
            status = ToolStatus(installed=False, source="missing", executable_path=None)
            self.state_store.update(
                tool_id,
                installed=False,
                version=None,
                source="missing",
                executable_path=None,
                error_message=f"{spec.display_name} is not available",
            )
            return status

        version = self._read_version(resolution, spec)
        status = ToolStatus(
            installed=True,
            version=version,
            source=resolution.source,
            executable_path=resolution.executable,
            error_message=None,
        )
        self.state_store.update(
            tool_id,
            installed=True,
            version=version,
            source=resolution.source,
            executable_path=resolution.executable,
        )
        return status

    def is_tool_available(self, tool_id: str) -> bool:
        return self.resolve_tool(tool_id).source != "missing"

    def get_missing_tools_for_feature(self, feature_id: str):
        """Return the subset of tools for a feature that are currently missing."""

        missing = []
        for tool_id in get_tools_for_feature(feature_id):
            if not self.is_tool_available(tool_id):
                missing.append(tool_id)
        return missing

    def get_feature_status(self, feature_id: str):
        """Return status objects keyed by tool id for a feature."""

        return {tool_id: self.get_tool_status(tool_id) for tool_id in get_tools_for_feature(feature_id)}

    def get_installable_tools(self, tool_ids):
        """Return the tool ids that can be installed through the managed runtime."""

        return [tool_id for tool_id in tool_ids if is_managed_install_supported(tool_id)]

    def install_tools(self, tool_ids, progress_cb=None, log_cb=None, cancel_check=None):
        """Install the package set that corresponds to the provided tools."""

        installable = self.get_installable_tools(tool_ids)
        if not installable:
            raise ToolRuntimeError(
                "Managed installs are not available for the requested tools on this platform."
            )
        packages = []
        for tool_id in installable:
            spec = get_tool_spec(tool_id)
            if spec.package_name not in packages:
                packages.append(spec.package_name)
        try:
            env_path = self.manager.install_packages(
                packages,
                progress_cb=progress_cb,
                log_cb=log_cb,
                cancel_check=cancel_check,
            )
        except Exception as exc:
            raise ToolRuntimeError(str(exc)) from exc
        for tool_id in tool_ids:
            self.get_tool_status(tool_id)
        return env_path


_tool_runtime: ToolRuntime | None = None


def get_tool_runtime() -> ToolRuntime:
    """Return the shared tool runtime."""

    global _tool_runtime
    if _tool_runtime is None:
        _tool_runtime = ToolRuntime()
    return _tool_runtime
