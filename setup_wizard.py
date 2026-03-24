"""Diagnostics tool for the current Protein-GUI runtime configuration."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

import core.config_manager as config_manager_module
import core.micromamba_manager as micromamba_manager_module
from core.config_manager import ConfigManager
from core.tool_registry import TOOLS, current_platform_key, is_managed_install_supported
from core.tool_runtime import ToolRuntime


def is_windows():
    return sys.platform == "win32"


def is_macos():
    return sys.platform == "darwin"


def check_command(cmd):
    """Check if a command is available."""
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def find_blast():
    """Try to find BLAST installation (cross-platform)."""
    if is_windows():
        common_paths = [
            r"C:\Program Files\NCBI\blast-2.17.0+\bin\blastp.exe",
            r"C:\Program Files\NCBI\blast-2.16.0+\bin\blastp.exe",
            r"C:\Program Files\NCBI\blast-2.15.0+\bin\blastp.exe",
            r"C:\blast\bin\blastp.exe",
        ]
    elif is_macos():
        common_paths = [
            "/usr/local/bin/blastp",
            "/opt/homebrew/bin/blastp",
            os.path.expanduser("~/miniconda3/bin/blastp"),
            os.path.expanduser("~/anaconda3/bin/blastp"),
        ]
    else:
        common_paths = [
            "/usr/bin/blastp",
            "/usr/local/bin/blastp",
            os.path.expanduser("~/miniconda3/bin/blastp"),
            os.path.expanduser("~/anaconda3/bin/blastp"),
        ]

    for path in common_paths:
        if os.path.exists(path):
            return path

    found = shutil.which("blastp")
    if found:
        return found

    if check_command(["blastp", "-version"]):
        return "blastp"

    return None


def find_mmseqs():
    """Try to find MMseqs2 installation (cross-platform)."""
    if is_windows():
        common_paths = [
            r"C:\Program Files\MMSeqs2\mmseqs.exe",
            r"C:\MMSeqs2\mmseqs.exe",
            r"C:\mmseqs\bin\mmseqs.exe",
        ]
    elif is_macos():
        common_paths = [
            "/usr/local/bin/mmseqs",
            "/opt/homebrew/bin/mmseqs",
            os.path.expanduser("~/miniconda3/bin/mmseqs"),
            os.path.expanduser("~/anaconda3/bin/mmseqs"),
        ]
    else:
        common_paths = [
            "/usr/local/bin/mmseqs",
            "/usr/bin/mmseqs",
            os.path.expanduser("~/miniconda3/bin/mmseqs"),
            os.path.expanduser("~/anaconda3/bin/mmseqs"),
        ]

    for path in common_paths:
        if os.path.exists(path):
            return path

    found = shutil.which("mmseqs")
    if found:
        return found

    if check_command(["mmseqs", "--help"]):
        return "mmseqs"

    return None


def find_clustalo():
    """Try to find Clustal Omega installation."""
    found = shutil.which("clustalo")
    if found:
        return found

    if is_macos():
        for path in ["/usr/local/bin/clustalo", "/opt/homebrew/bin/clustalo"]:
            if os.path.exists(path):
                return path

    if check_command(["clustalo", "--version"]):
        return "clustalo"

    return None


def find_blastdbcmd():
    """Try to find blastdbcmd."""
    found = shutil.which("blastdbcmd")
    if found:
        return found

    if check_command(["blastdbcmd", "-version"]):
        return "blastdbcmd"

    return None


def check_wsl():
    """Check if WSL is available (Windows only)."""
    if not is_windows():
        return False
    try:
        result = subprocess.run(["wsl", "--status"], capture_output=True, timeout=15)
        return result.returncode == 0
    except Exception:
        return False


def get_install_hint(tool):
    """Get platform-appropriate installation guidance."""
    if is_windows():
        hints = {
            "blast": "Use the app's Tools tab when available, or install BLAST+ inside WSL/system tooling.",
            "mmseqs": "Windows currently uses WSL/system-backed MMseqs2 rather than managed installs.",
            "mmseqs_wsl": (
                "Install in WSL:\n"
                "        wsl\n"
                "        wget https://mmseqs.com/latest/mmseqs-linux-avx2.tar.gz\n"
                "        tar xvfz mmseqs-linux-avx2.tar.gz\n"
                "        sudo cp mmseqs/bin/mmseqs /usr/local/bin/"
            ),
            "blastdbcmd": "Install BLAST+ inside WSL so blastdbcmd is available to the GUI.",
            "blastdbcmd_wsl": (
                "Install in WSL:\n"
                "        wsl\n"
                "        sudo apt update\n"
                "        sudo apt install ncbi-blast+"
            ),
            "clustalo": "Install Clustal Omega in WSL: sudo apt install clustalo",
        }
    elif is_macos():
        hints = {
            "blast": (
                "Install from the app's Tools tab or let a BLAST feature prompt for install.\n"
                "      Manual fallback: brew install blast"
            ),
            "mmseqs": (
                "Install from the app's Tools tab or let MMseqs2 features prompt for install.\n"
                "      Manual fallback: brew install mmseqs2"
            ),
            "blastdbcmd": (
                "Install from the app's Tools tab; blastdbcmd ships with the BLAST+ package.\n"
                "      Manual fallback: brew install blast"
            ),
            "clustalo": (
                "Install from the app's Tools tab or let Alignment prompt for install.\n"
                "      Manual fallback: brew install clustal-omega"
            ),
        }
    else:
        hints = {
            "blast": (
                "Install from the app's Tools tab or via your package manager.\n"
                "      Manual fallback: sudo apt update && sudo apt install ncbi-blast+"
            ),
            "mmseqs": (
                "Install from the app's Tools tab or via your package manager.\n"
                "      Manual fallback: conda install -c conda-forge -c bioconda mmseqs2"
            ),
            "blastdbcmd": (
                "Install from the app's Tools tab; blastdbcmd ships with BLAST+.\n"
                "      Manual fallback: sudo apt update && sudo apt install ncbi-blast+"
            ),
            "clustalo": (
                "Install from the app's Tools tab or via your package manager.\n"
                "      Manual fallback: sudo apt update && sudo apt install clustalo"
            ),
        }
    return hints.get(tool, f"Please install {tool}")


def _check_python_dependency(module_name: str):
    try:
        __import__(module_name)
        return True
    except Exception:
        return False


def _platform_name() -> str:
    return "Windows" if is_windows() else ("macOS" if is_macos() else "Linux")


def _database_diagnostics(config: ConfigManager):
    blast_db_dir = config.get_blast_db_dir()
    if os.path.isdir(blast_db_dir):
        databases = sorted(
            entry for entry in os.listdir(blast_db_dir)
            if os.path.isdir(os.path.join(blast_db_dir, entry))
        )
    else:
        databases = []

    return {
        "path": blast_db_dir,
        "exists": os.path.isdir(blast_db_dir),
        "databases": databases,
    }


def collect_diagnostics(config_path="config.json"):
    """Collect runtime-aligned diagnostics without mutating config."""
    config = ConfigManager(config_path=config_path)
    config_manager_module._config_instance = config
    micromamba_manager_module._micromamba_manager = None
    runtime = ToolRuntime()

    python_dependencies = {
        "PyQt5": _check_python_dependency("PyQt5"),
        "Biopython": _check_python_dependency("Bio"),
    }

    tool_diagnostics = {}
    for tool_id, spec in TOOLS.items():
        status = runtime.get_tool_status(tool_id)
        tool_diagnostics[tool_id] = {
            "display_name": spec.display_name,
            "installed": status.installed,
            "source": status.source,
            "version": status.version,
            "executable_path": status.executable_path,
            "error_message": status.error_message,
            "managed_supported": is_managed_install_supported(tool_id),
            "install_hint": get_install_hint("blast" if tool_id in {"blastp", "blastn"} else tool_id),
        }

    return {
        "platform": _platform_name(),
        "platform_key": current_platform_key(),
        "python_version": sys.version.split()[0],
        "python_dependencies": python_dependencies,
        "managed_tools_root": config.get_managed_tools_root(),
        "managed_env_name": config.get_managed_env_name(),
        "preferred_tool_sources": config.get_preferred_tool_sources(),
        "tool_source_overrides": config.get_tool_source_overrides(),
        "wsl_available": check_wsl() if is_windows() else None,
        "tools": tool_diagnostics,
        "databases": _database_diagnostics(config),
        "config_path": os.path.abspath(config_path),
    }


def _print_tool_section(diagnostics):
    print("Tool Runtime")
    print("-" * 60)
    for tool_id, tool in diagnostics["tools"].items():
        status = "OK" if tool["installed"] else "MISSING"
        line = f"[{status}] {tool['display_name']}: source={tool['source']}"
        if tool["version"]:
            line += f" | version={tool['version']}"
        print(line)
        if tool["executable_path"]:
            print(f"      executable: {tool['executable_path']}")
        if tool["managed_supported"]:
            print("      managed install: supported")
        else:
            print("      managed install: unavailable on this platform")
        if tool["error_message"]:
            print(f"      detail: {tool['error_message']}")
        if not tool["installed"]:
            print(f"      next step: {tool['install_hint']}")
    print()


def _print_summary(diagnostics):
    print("=" * 60)
    print("Protein-GUI Runtime Diagnostics")
    print("=" * 60)
    print(f"Platform: {diagnostics['platform']}")
    print(f"Python: {diagnostics['python_version']}")
    print(f"Config path: {diagnostics['config_path']}")
    print()

    print("Python Dependencies")
    print("-" * 60)
    for name, installed in diagnostics["python_dependencies"].items():
        status = "OK" if installed else "MISSING"
        print(f"[{status}] {name}")
    print()

    print("Managed Runtime")
    print("-" * 60)
    print(f"Tools root: {diagnostics['managed_tools_root']}")
    print(f"Environment: {diagnostics['managed_env_name']}")
    print(f"Preferred source order: {', '.join(diagnostics['preferred_tool_sources'])}")
    overrides = diagnostics["tool_source_overrides"]
    print(f"Source overrides: {overrides if overrides else 'none'}")
    if diagnostics["platform_key"] == "windows":
        print(f"WSL available: {'yes' if diagnostics['wsl_available'] else 'no'}")
        print("Windows note: BLAST+, MMseqs2, blastdbcmd, and Clustal Omega currently rely on WSL/system sources.")
    else:
        print("Managed native installs are supported on this platform.")
    print()

    _print_tool_section(diagnostics)

    print("Databases")
    print("-" * 60)
    print(f"BLAST database directory: {diagnostics['databases']['path']}")
    if diagnostics["databases"]["exists"]:
        if diagnostics["databases"]["databases"]:
            print(f"Installed databases: {', '.join(diagnostics['databases']['databases'])}")
        else:
            print("Installed databases: none found in the directory yet")
    else:
        print("BLAST database directory does not exist yet")
    print()

    print("Notes")
    print("-" * 60)
    print("This tool is diagnostics-only. It does not write or repair config.json.")
    print("Use the GUI Tools tab or feature prompts to install tools.")
    print("Advanced users can still edit config.json to change configured paths or source overrides.")
    print()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Inspect the current Protein-GUI runtime without changing configuration."
    )
    parser.add_argument(
        "--config",
        default="config.json",
        help="Path to the config file to inspect (default: config.json).",
    )
    parser.add_argument(
        "--pause",
        action="store_true",
        help="Pause before exiting (useful for double-click launches).",
    )
    args = parser.parse_args(argv)

    diagnostics = collect_diagnostics(config_path=args.config)
    _print_summary(diagnostics)

    if args.pause and sys.stdin.isatty():
        input("Press Enter to exit...")


if __name__ == "__main__":
    main()
