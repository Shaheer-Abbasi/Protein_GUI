"""Download PDB/mmCIF from RCSB into a simple on-disk cache."""

from __future__ import annotations

import re
from pathlib import Path

import requests
from PyQt5.QtCore import QThread, pyqtSignal


def validate_pdb_id(s: str) -> str:
    """
    Normalize a PDB id (4 alphanumeric characters).

    Raises ValueError if invalid.
    """
    t = (s or "").strip().upper().replace("_", "").replace("-", "").replace(" ", "")
    # Allow PDB entry formats like 8ABC (alphanumeric extension)
    if not re.fullmatch(r"[A-Z0-9]{4}", t):
        raise ValueError(f"Invalid PDB id (expected four letters/digits): {s!r}")
    return t


def pdb_cache_dir() -> Path:
    d = Path.home() / ".cache" / "sen_lab_protein_gui" / "pdb"
    d.mkdir(parents=True, exist_ok=True)
    return d


RCSB_DOWNLOAD = "https://files.rcsb.org/download"


def cached_structure_path(pdb_id: str) -> tuple[Path, str]:
    """Return ``(local_path, fmt)`` where ``fmt`` is ``pdb`` or ``cif`` if cached."""
    pid = validate_pdb_id(pdb_id)
    base = pdb_cache_dir()
    p_pdb = base / f"{pid}.pdb"
    if p_pdb.is_file() and p_pdb.stat().st_size > 0:
        return p_pdb, "pdb"
    p_cif = base / f"{pid}.cif"
    if p_cif.is_file() and p_cif.stat().st_size > 0:
        return p_cif, "cif"
    raise FileNotFoundError(pid)


class PdbFetchWorker(QThread):
    """Fetch ``https://files.rcsb.org/download/<ID>.pdb`` with ``.cif`` fallback."""

    progress = pyqtSignal(str)
    finished = pyqtSignal(str, str)  # path, fmt ('pdb' | 'cif')
    error = pyqtSignal(str)

    def __init__(self, pdb_id: str, timeout: float = 60.0, parent=None):
        super().__init__(parent)
        self._pid = pdb_id.strip()
        self._timeout = timeout
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            pid = validate_pdb_id(self._pid)
        except ValueError as e:
            self.error.emit(str(e))
            return

        base = pdb_cache_dir()
        p_pdb = base / f"{pid}.pdb"
        p_cif = base / f"{pid}.cif"

        if self._cancelled:
            return

        try:
            pexist, fmt = cached_structure_path(pid)
            self.progress.emit(f"Using cached {fmt.upper()} for {pid}.")
            self.finished.emit(str(pexist), fmt)
            return
        except FileNotFoundError:
            pass

        urls = [(f"{RCSB_DOWNLOAD}/{pid}.pdb", "pdb", p_pdb), (f"{RCSB_DOWNLOAD}/{pid}.cif", "cif", p_cif)]
        sess = requests.Session()
        headers = {"User-Agent": "SenLab-ProteinGUI/1.0 (structure-fetch)"}

        for url, fmt, out_path in urls:
            if self._cancelled:
                return
            self.progress.emit(f"Fetching {pid} ({fmt.upper()}) from RCSB…")
            try:
                resp = sess.get(url, headers=headers, timeout=self._timeout)
                if resp.status_code != 200 or not resp.text or len(resp.text) < 80:
                    continue
                if fmt == "pdb" and resp.text.lstrip().upper().startswith("<!DOCTYPE"):
                    continue
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(resp.text, encoding="utf-8", errors="replace")
                self.finished.emit(str(out_path.resolve()), fmt)
                return
            except requests.RequestException:
                continue

        self.error.emit(
            f"Could not download {pid} (.pdb or .cif) from RCSB. "
            "Check the id or try again later."
        )
