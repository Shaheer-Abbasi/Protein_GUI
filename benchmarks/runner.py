"""Subprocess timing + peak RSS sampling for benchmark drivers."""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from typing import Any

from core.tool_registry import get_tool_spec
from core.tool_runtime import ToolResolution, ToolRuntimeError, get_tool_runtime


_STDER_SNIPPET_LEN = 500


def resolve_executable(tool_id: str) -> tuple[ToolResolution, str]:
    """Resolve *tool_id* and return ``(resolution, absolute_executable_path_or_name)``."""
    rt = get_tool_runtime()
    resolution = rt.resolve_tool(tool_id)
    if not resolution.executable:
        raise ToolRuntimeError(f"Tool '{tool_id}' is not available")
    exe = resolution.executable
    return resolution, exe


def try_resolve_executable(tool_id: str) -> tuple[ToolResolution | None, str | None]:
    try:
        res, exe = resolve_executable(tool_id)
        return res, exe
    except ToolRuntimeError:
        return None, None


def argv_for_resolution(resolution: ToolResolution, cmd_parts: list[str]) -> list[str]:
    """Mirror GUI workers: native exec + args; WSL prepends ``wsl``."""
    if resolution.backend == "wsl":
        return ["wsl", resolution.executable or "", *cmd_parts]
    return [resolution.executable or "", *cmd_parts]


def _read_linux_vm_hwm_kib(pid: int) -> int:
    path = f"/proc/{pid}/status"
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.startswith("VmHWM:"):
                    # VmHWM:	  123456 kB
                    parts = line.split()
                    if len(parts) >= 2:
                        return int(parts[1])
    except OSError:
        pass
    return 0


def _read_linux_rss_kib(pid: int) -> int:
    """Fallback: VmRSS from /proc/pid/status."""
    path = f"/proc/{pid}/status"
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        return int(parts[1])
    except OSError:
        pass
    return 0


def _read_ps_rss_kib(pid: int) -> int:
    """macOS / BSD: ``ps`` RSS column is KiB."""
    try:
        out = subprocess.run(
            ["ps", "-p", str(pid), "-o", "rss="],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        tok = (out.stdout or "").strip().split()
        if tok:
            return int(tok[0])
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    return 0


def sample_peak_rss_kib(pid: int) -> int:
    """Best-effort RSS high-water or current RSS for *pid* (KiB)."""
    if pid <= 0:
        return 0
    sysname = platform.system()
    if sysname == "Linux":
        hwm = _read_linux_vm_hwm_kib(pid)
        if hwm > 0:
            return hwm
        return _read_linux_rss_kib(pid)
    # Darwin / others
    return _read_ps_rss_kib(pid)


def kib_to_mib(kib: float) -> float:
    return kib / 1024.0


def tool_version_line(tool_id: str) -> str | None:
    """First line of ``--version`` / vendor-specific version args."""
    try:
        spec = get_tool_spec(tool_id)
        resolution = get_tool_runtime().resolve_tool(tool_id)
        if not resolution.executable:
            return None
        argv = argv_for_resolution(resolution, list(spec.version_args))
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=30,
            errors="replace",
        )
        out = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
        if proc.returncode != 0 or not out:
            return None
        return out.splitlines()[0].strip()
    except (OSError, subprocess.TimeoutExpired, KeyError):
        return None


def collect_system_metadata(tool_versions: dict[str, str | None] | None = None) -> dict[str, Any]:
    """Host + interpreter metadata recorded once per benchmark session."""
    uname = platform.uname()
    meta: dict[str, Any] = {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "node": uname.node,
        "python": sys.version.split()[0],
        "cpu_count": os.cpu_count(),
    }
    if tool_versions:
        meta["tool_versions"] = {k: v for k, v in tool_versions.items() if v}
    return meta


@dataclass
class TimedRunResult:
    wall_seconds: float
    peak_rss_mib: float | None
    exit_code: int | None
    stderr_snippet: str
    stdout_path: str | None = None
    timed_out: bool = False


def timed_run(
    argv: list[str],
    *,
    timeout: float | None,
    stdout_path: str | None = None,
    stdin_devnull: bool = True,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> TimedRunResult:
    """Run *argv*[0] with arguments; optionally capture stdout to *stdout_path*.

    Peak RSS is sampled periodically via ``/proc`` (Linux) or ``ps`` (macOS).
    """
    fd, stderr_path = tempfile.mkstemp(prefix="bench_stderr_", suffix=".txt")
    os.close(fd)

    stdout_target: Any = subprocess.DEVNULL
    fh_out = None
    if stdout_path:
        fh_out = open(stdout_path, "w", encoding="utf-8", errors="replace")
        stdout_target = fh_out

    stdin_target = subprocess.DEVNULL if stdin_devnull else None

    peak_kib = 0
    stop_poller = threading.Event()
    pid_holder: list[int] = [0]

    def poller():
        nonlocal peak_kib
        while not stop_poller.wait(0.08):
            pid = pid_holder[0]
            if pid > 0:
                peak_kib = max(peak_kib, sample_peak_rss_kib(pid))

    poll_t = threading.Thread(target=poller, daemon=True)
    poll_t.start()

    t0 = time.monotonic()
    proc: subprocess.Popen[str] | None = None
    timed_out = False
    exit_code: int | None = None

    stderr_f = open(stderr_path, "w", encoding="utf-8", errors="replace")
    try:
        proc = subprocess.Popen(
            argv,
            stdin=stdin_target,
            stdout=stdout_target,
            stderr=stderr_f,
            text=True,
            cwd=cwd,
            env=env,
        )
        pid_holder[0] = proc.pid
        peak_kib = max(peak_kib, sample_peak_rss_kib(proc.pid))

        if timeout is None:
            exit_code = proc.wait()
        else:
            try:
                exit_code = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                proc.kill()
                try:
                    exit_code = proc.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    exit_code = None
    except OSError as exc:
        exit_code = 127
        try:
            stderr_f.write(f"Popen failed: {exc}\n")
        except OSError:
            pass
    finally:
        try:
            stderr_f.close()
        except OSError:
            pass
        stop_poller.set()
        poll_t.join(timeout=2)
        pid_holder[0] = 0
        if proc and proc.poll() is None:
            try:
                proc.kill()
            except OSError:
                pass
        if fh_out:
            try:
                fh_out.flush()
                fh_out.close()
            except OSError:
                pass

    wall = time.monotonic() - t0

    snippet = ""
    try:
        with open(stderr_path, encoding="utf-8", errors="replace") as sf:
            snippet = sf.read()[:_STDER_SNIPPET_LEN]
    except OSError:
        pass
    try:
        os.unlink(stderr_path)
    except OSError:
        pass

    peak_mib = kib_to_mib(float(peak_kib)) if peak_kib > 0 else None

    return TimedRunResult(
        wall_seconds=wall,
        peak_rss_mib=peak_mib,
        exit_code=exit_code if exit_code is not None else -1,
        stderr_snippet=snippet,
        stdout_path=stdout_path,
        timed_out=timed_out,
    )


def dump_metadata_json(path: str, meta: dict[str, Any]) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)


def collect_alignment_tool_versions(tool_ids: list[str]) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for tid in tool_ids:
        out[tid] = tool_version_line(tid)
    return out


def collect_search_tool_versions() -> dict[str, str | None]:
    keys = ["blastp", "mmseqs", "diamond"]
    return {k: tool_version_line(k) for k in keys}
