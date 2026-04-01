"""
Manager for the Ranganathan-lab pySCA package (Tier 2).

Handles detection, installation from GitHub, running the 3-step pipeline
(scaProcessMSA -> scaCore -> scaSectorID), and exporting results.
"""

from __future__ import annotations

import os
import pickle
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import numpy as np

PYSCA_GIT_URL = "git+https://github.com/ranganathanlab/pySCA.git"


@dataclass
class PySCAParams:
    """Configuration for a full pySCA run."""
    pdb_id: str = ""
    chain: str = ""
    max_gap_frac_pos: float = 0.2
    max_gap_frac_seq: float = 0.2
    min_seq_id: float = 0.2
    max_seq_id: float = 0.8
    norm: str = "frob"
    lbda: float = 0.03
    n_trials: int = 10


@dataclass
class PySCAOutputs:
    """Result container for a full pySCA pipeline run."""
    db_path: str = ""
    log_path: str = ""
    processed_alignment_path: str = ""
    output_dir: str = ""
    success: bool = False
    error_msg: str = ""
    exported_files: list[str] = field(default_factory=list)


def is_pysca_installed() -> bool:
    """Check whether the pySCA package can be imported."""
    try:
        import pysca  # noqa: F401
        return True
    except ImportError:
        pass
    # Also check if the CLI script is on PATH
    return shutil.which("scaProcessMSA") is not None or shutil.which("sca-process-msa") is not None


def check_pairwise_aligner() -> Optional[str]:
    """Return the name of a usable pairwise aligner, or None."""
    for name in ("ggsearch36", "needle"):
        if shutil.which(name):
            return name
    return None


def install_pysca(
    progress_cb: Optional[Callable[[str], None]] = None,
) -> bool:
    """
    Install pySCA from GitHub into the current Python environment.

    Returns True on success.
    """
    cmd = [sys.executable, "-m", "pip", "install", PYSCA_GIT_URL]
    if progress_cb:
        progress_cb(f"Running: {' '.join(cmd)}")
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip()
            if progress_cb:
                progress_cb(line)
        proc.wait()
        return proc.returncode == 0
    except Exception as exc:
        if progress_cb:
            progress_cb(f"Install failed: {exc}")
        return False


def _run_subprocess(
    cmd: list[str],
    progress_cb: Optional[Callable[[str], None]] = None,
    label: str = "",
) -> tuple[int, str]:
    """Run a command, streaming output to progress_cb. Returns (returncode, full_output)."""
    if progress_cb:
        progress_cb(f"[{label}] Running: {' '.join(cmd)}")
    lines: list[str] = []
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip()
            lines.append(line)
            if progress_cb:
                progress_cb(f"[{label}] {line}")
        proc.wait()
        return proc.returncode, "\n".join(lines)
    except Exception as exc:
        msg = f"[{label}] Failed: {exc}"
        if progress_cb:
            progress_cb(msg)
        return -1, msg


def run_pysca_pipeline(
    fasta_path: str,
    output_dir: str,
    params: PySCAParams | None = None,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> PySCAOutputs:
    """
    Run the 3-step pySCA pipeline.

    The FASTA file is copied into *output_dir* before processing.
    """
    if params is None:
        params = PySCAParams()

    result = PySCAOutputs(output_dir=output_dir)
    os.makedirs(output_dir, exist_ok=True)

    # Copy FASTA into output dir
    dst_fasta = os.path.join(output_dir, os.path.basename(fasta_path))
    if os.path.abspath(fasta_path) != os.path.abspath(dst_fasta):
        shutil.copy2(fasta_path, dst_fasta)

    # Derive expected .db name (pySCA uses alignment stem)
    stem = Path(dst_fasta).stem
    db_path = os.path.join(output_dir, f"{stem}.db")

    # ── Step 1: scaProcessMSA ────────────────────────────────────
    cmd1 = [
        sys.executable, "-m", "pysca.scaProcessMSA",
        "-a", dst_fasta,
        "-d", output_dir,
        "-p", (
            f"{params.max_gap_frac_pos},{params.max_gap_frac_seq},"
            f"{params.min_seq_id},{params.max_seq_id}"
        ),
    ]
    if params.pdb_id:
        cmd1.extend(["-s", params.pdb_id])
    if params.chain:
        cmd1.extend(["-c", params.chain])

    rc, out = _run_subprocess(cmd1, progress_cb, "scaProcessMSA")
    if rc != 0:
        # Try the script name directly
        cmd1[0:3] = ["scaProcessMSA"]
        cmd1 = ["scaProcessMSA", "-a", dst_fasta, "-d", output_dir,
                 "-p", f"{params.max_gap_frac_pos},{params.max_gap_frac_seq},{params.min_seq_id},{params.max_seq_id}"]
        if params.pdb_id:
            cmd1.extend(["-s", params.pdb_id])
        if params.chain:
            cmd1.extend(["-c", params.chain])
        rc, out = _run_subprocess(cmd1, progress_cb, "scaProcessMSA (fallback)")
        if rc != 0:
            result.error_msg = f"scaProcessMSA failed (exit {rc}):\n{out}"
            return result

    if not os.path.isfile(db_path):
        candidates = list(Path(output_dir).glob("*.db"))
        if candidates:
            db_path = str(candidates[0])
        else:
            result.error_msg = "scaProcessMSA completed but no .db file was created."
            return result

    result.db_path = db_path

    # ── Step 2: scaCore ──────────────────────────────────────────
    cmd2 = [
        sys.executable, "-m", "pysca.scaCore",
        "-i", db_path,
        "-n", params.norm,
        "-l", str(params.lbda),
        "-t", str(params.n_trials),
    ]
    rc, out = _run_subprocess(cmd2, progress_cb, "scaCore")
    if rc != 0:
        cmd2_fb = ["scaCore", "-i", db_path, "-n", params.norm,
                    "-l", str(params.lbda), "-t", str(params.n_trials)]
        rc, out = _run_subprocess(cmd2_fb, progress_cb, "scaCore (fallback)")
        if rc != 0:
            result.error_msg = f"scaCore failed (exit {rc}):\n{out}"
            return result

    # ── Step 3: scaSectorID ──────────────────────────────────────
    cmd3 = [
        sys.executable, "-m", "pysca.scaSectorID",
        "-i", db_path,
    ]
    rc, out = _run_subprocess(cmd3, progress_cb, "scaSectorID")
    if rc != 0:
        cmd3_fb = ["scaSectorID", "-i", db_path]
        rc, out = _run_subprocess(cmd3_fb, progress_cb, "scaSectorID (fallback)")
        if rc != 0:
            result.error_msg = f"scaSectorID failed (exit {rc}):\n{out}"
            return result

    result.success = True
    result.processed_alignment_path = dst_fasta

    # Look for log files
    for ext in (".log",):
        log = os.path.join(output_dir, stem + ext)
        if os.path.isfile(log):
            result.log_path = log
            break

    return result


def export_results(
    db_path: str,
    export_dir: str,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> list[str]:
    """
    Open a pySCA .db pickle file and export key arrays as CSV.

    Also copies the raw .db file. Returns list of exported file paths.
    """
    os.makedirs(export_dir, exist_ok=True)
    exported: list[str] = []

    # Copy raw .db
    dst_db = os.path.join(export_dir, os.path.basename(db_path))
    shutil.copy2(db_path, dst_db)
    exported.append(dst_db)
    if progress_cb:
        progress_cb(f"Copied .db file to {dst_db}")

    # Try to load and extract arrays
    try:
        with open(db_path, "rb") as f:
            data = pickle.load(f)
    except Exception as exc:
        if progress_cb:
            progress_cb(f"Could not read .db as pickle: {exc}")
        return exported

    array_keys = {
        "Csca": "sca_matrix",
        "Dsca": "sca_matrix_raw",
        "Di": "positional_conservation",
        "Lsca": "eigenvalues",
        "Vsca": "eigenvectors",
        "simMat": "sequence_similarity",
    }

    for key, filename_base in array_keys.items():
        if key not in data:
            continue
        arr = data[key]
        if not isinstance(arr, np.ndarray):
            try:
                arr = np.array(arr)
            except Exception:
                continue
        csv_path = os.path.join(export_dir, f"{filename_base}.csv")
        try:
            if arr.ndim <= 2:
                np.savetxt(csv_path, arr, delimiter=",")
                exported.append(csv_path)
                if progress_cb:
                    progress_cb(f"Exported {key} -> {csv_path}")
        except Exception as exc:
            if progress_cb:
                progress_cb(f"Failed to export {key}: {exc}")

    # Export sector lists if present
    for key in ("ics", "icList"):
        if key in data:
            try:
                ic_data = data[key]
                txt_path = os.path.join(export_dir, "sectors.txt")
                with open(txt_path, "w") as f:
                    for i, sector in enumerate(ic_data):
                        positions = ",".join(str(p) for p in sector)
                        f.write(f"Sector {i + 1}: {positions}\n")
                exported.append(txt_path)
                if progress_cb:
                    progress_cb(f"Exported sectors -> {txt_path}")
                break
            except Exception:
                pass

    return exported
