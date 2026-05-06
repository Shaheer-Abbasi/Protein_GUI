"""
Load and normalize pySCA 6.x `.db` pickle files (Dseq, Dsca, Dsect structure).
"""

from __future__ import annotations

import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np


@dataclass
class PySCAData:
    """In-memory view of a pySCA result database."""

    Dseq: Dict[str, Any]
    Dsca: Dict[str, Any]
    Dsect: Dict[str, Any]
    raw: Dict[str, Any] = field(repr=False, default_factory=dict)
    path: str = ""


def _get_nested(data: Any, *keys, default: Any = None) -> Any:
    cur: Any = data
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def load_pysca_db(path: str | Path) -> PySCAData:
    """
    Load a pySCA `.db` file written by the official pipeline.

    Standard layout: ``db['sequence']``, ``db['sca']``, ``db['sector']``.
    Falls back to flat top-level keys if those are missing (older experiments).
    """
    path = str(path)
    with open(path, "rb") as f:
        raw: Dict[str, Any] = pickle.load(f)

    if not isinstance(raw, dict):
        raise ValueError("pySCA .db root must be a dict")

    # --- sequence block ---
    Dseq = raw.get("sequence")
    if not isinstance(Dseq, dict):
        Dseq = {}
        for key in ("Nseq", "Npos", "ats", "hd", "effseqs"):
            if key in raw:
                Dseq[key] = raw[key]

    # --- sca block: prefer nested, else top-level array keys map into a synthetic Dsca ---
    Dsca = raw.get("sca")
    if not isinstance(Dsca, dict):
        Dsca = {}
    if not Dsca:
        for key in (
            "Csca",
            "Dsca",
            "Di",
            "Lsca",
            "Lrand",
            "Ntrials",
            "simMat",
            "Uica",
        ):
            if key in raw and key not in Dsca:
                Dsca[key] = raw[key]

    # --- sector block ---
    Dsect = raw.get("sector")
    if not isinstance(Dsect, dict):
        Dsect = {}
    if not Dsect:
        for key in (
            "kpos",
            "Lsca",
            "Vsca",
            "Vpica",
            "ics",
            "sortedpos",
            "icsize",
            "scaled_pd",
            "cutoff",
        ):
            if key in raw and key not in Dsect:
                Dsect[key] = raw[key]

    return PySCAData(Dseq=Dseq, Dsca=Dsca, Dsect=Dsect, raw=raw, path=path)


def ic_list_from_dsect(Dsect: Dict[str, Any]) -> List[Any]:
    """Return ``Dsect['ics']`` as a list (may be empty)."""
    ics = Dsect.get("ics")
    if ics is None:
        return []
    if isinstance(ics, (list, tuple)):
        return list(ics)
    return [ics]


def get_array(
    Dsca: Dict[str, Any],
    Dsect: Dict[str, Any],
    key: str,
    prefer_sector: bool = False,
) -> Optional[np.ndarray]:
    """
    Get an array, checking ``Dsect`` or ``Dsca`` in sensible order.
    """
    if prefer_sector:
        if key in Dsect:
            arr = Dsect.get(key)
        else:
            arr = Dsca.get(key) if Dsca else None
    else:
        if key in Dsca:
            arr = Dsca.get(key)
        else:
            arr = Dsect.get(key)
    if arr is None:
        return None
    if isinstance(arr, np.ndarray):
        return arr
    return np.asarray(arr)
