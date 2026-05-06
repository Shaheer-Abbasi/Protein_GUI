"""Registry for managed bioinformatics tools.

Managed micromamba installs target macOS and Linux. Windows currently falls
back to WSL/system tooling because the relevant bioconda packages are not
consistently available there, especially for MMseqs2.
"""

from dataclasses import dataclass
import platform
import sys
from typing import Dict, Tuple


@dataclass(frozen=True)
class ToolSpec:
    """Static metadata describing a tool and how the app should manage it."""

    id: str
    display_name: str
    package_name: str
    channels: Tuple[str, ...]
    executables: Tuple[str, ...]
    feature_labels: Tuple[str, ...]
    version_args: Tuple[str, ...]
    managed_platforms: Tuple[str, ...] = ("darwin", "linux")
    windows_fallback: str | None = "wsl"


TOOLS: Dict[str, ToolSpec] = {
    "blastp": ToolSpec(
        id="blastp",
        display_name="BLASTP",
        package_name="blast",
        channels=("bioconda",),
        executables=("blastp",),
        feature_labels=("protein_blast",),
        version_args=("-version",),
    ),
    "blastn": ToolSpec(
        id="blastn",
        display_name="BLASTN",
        package_name="blast",
        channels=("bioconda",),
        executables=("blastn",),
        feature_labels=("blastn",),
        version_args=("-version",),
    ),
    "blastdbcmd": ToolSpec(
        id="blastdbcmd",
        display_name="blastdbcmd",
        package_name="blast",
        channels=("bioconda",),
        executables=("blastdbcmd",),
        feature_labels=("database_conversion", "protein_mmseqs"),
        version_args=("-version",),
    ),
    "mmseqs": ToolSpec(
        id="mmseqs",
        display_name="MMseqs2",
        package_name="mmseqs2",
        channels=("conda-forge", "bioconda"),
        executables=("mmseqs",),
        feature_labels=("protein_mmseqs", "clustering", "database_conversion"),
        version_args=("version",),
    ),
    "clustalo": ToolSpec(
        id="clustalo",
        display_name="Clustal Omega",
        package_name="clustalo",
        channels=("bioconda",),
        executables=("clustalo",),
        feature_labels=("alignment", "alignment_clustalo"),
        version_args=("--version",),
    ),
    "mafft": ToolSpec(
        id="mafft",
        display_name="MAFFT",
        package_name="mafft",
        channels=("bioconda",),
        executables=("mafft",),
        feature_labels=("alignment", "alignment_mafft"),
        version_args=("--version",),
    ),
    "muscle": ToolSpec(
        id="muscle",
        display_name="MUSCLE",
        package_name="muscle",
        channels=("bioconda",),
        executables=("muscle",),
        feature_labels=("alignment", "alignment_muscle"),
        version_args=("-version",),
    ),
    "famsa": ToolSpec(
        id="famsa",
        display_name="FAMSA",
        package_name="famsa",
        channels=("bioconda",),
        executables=("famsa",),
        feature_labels=("alignment", "alignment_famsa"),
        version_args=("--version",),
    ),
    "diamond": ToolSpec(
        id="diamond",
        display_name="DIAMOND",
        package_name="diamond",
        channels=("bioconda",),
        executables=("diamond",),
        feature_labels=("protein_diamond",),
        version_args=("version",),
    ),
    "famsa_gpu": ToolSpec(
        id="famsa_gpu",
        display_name="FAMSA (GPU)",
        package_name="famsa",
        channels=("bioconda",),
        executables=("famsa-gpu", "famsa"),
        feature_labels=("alignment", "alignment_famsa_gpu"),
        version_args=("--version",),
        managed_platforms=(),
    ),
    "twilight": ToolSpec(
        id="twilight",
        display_name="TWILIGHT",
        package_name="twilight",
        channels=(),
        executables=("twilight",),
        feature_labels=("alignment", "alignment_twilight"),
        version_args=("--version",),
        managed_platforms=(),
    ),
}


FEATURE_TOOLS: Dict[str, Tuple[str, ...]] = {
    "protein_blast": ("blastp",),
    "protein_mmseqs": ("mmseqs", "blastdbcmd"),
    "protein_mmseqs_existing_db": ("mmseqs",),
    "blastn": ("blastn",),
    # Alignment: one tool per feature id so installs/checks are per selected aligner.
    "alignment": ("clustalo",),
    "alignment_clustalo": ("clustalo",),
    "alignment_mafft": ("mafft",),
    "alignment_muscle": ("muscle",),
    "alignment_famsa": ("famsa",),
    "alignment_famsa_gpu": ("famsa_gpu",),
    "alignment_twilight": ("twilight",),
    "protein_diamond": ("diamond",),
    "clustering": ("mmseqs",),
    "database_conversion": ("blastdbcmd", "mmseqs"),
}


ALIGNMENT_TOOL_IDS: Tuple[str, ...] = ("clustalo", "mafft", "muscle", "famsa", "famsa_gpu", "twilight")


def alignment_feature_id_for_tool(tool_id: str) -> str:
    """Feature key for ToolRuntime.get_missing_tools_for_feature on the alignment tab."""
    if tool_id not in ALIGNMENT_TOOL_IDS:
        raise KeyError(f"Not an alignment tool id: {tool_id}")
    return f"alignment_{tool_id}"


def get_tool_spec(tool_id: str) -> ToolSpec:
    """Return the static metadata for a known tool."""

    if tool_id not in TOOLS:
        raise KeyError(f"Unknown tool id: {tool_id}")
    return TOOLS[tool_id]


def get_tools_for_feature(feature_id: str) -> Tuple[str, ...]:
    """Return the tools required by a higher-level feature."""

    return FEATURE_TOOLS.get(feature_id, ())


def current_platform_key() -> str:
    """Return a normalized platform key used by runtime policy."""

    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "darwin"
    return "linux"


def is_managed_install_supported(tool_id: str) -> bool:
    """Whether the current platform supports app-managed micromamba installs."""

    spec = get_tool_spec(tool_id)
    platform_key = current_platform_key()
    if platform_key == "windows":
        return False
    return platform_key in spec.managed_platforms


def get_windows_backend_policy() -> Dict[str, str]:
    """Return the current Windows policy for managed/runtime backends."""

    return {
        "blastp": "wsl",
        "blastn": "wsl",
        "blastdbcmd": "wsl",
        "mmseqs": "wsl",
        "clustalo": "wsl",
        "mafft": "wsl",
        "muscle": "wsl",
        "famsa": "wsl",
        "diamond": "wsl",
        "famsa_gpu": "wsl",
        "twilight": "wsl",
    }


def micromamba_platform_subdir() -> str:
    """Return the micromamba platform tag for this machine."""

    machine = platform.machine().lower()
    if sys.platform == "darwin":
        return "osx-arm64" if machine in {"arm64", "aarch64"} else "osx-64"
    if sys.platform == "win32":
        return "win-64"
    return "linux-aarch64" if machine in {"arm64", "aarch64"} else "linux-64"
