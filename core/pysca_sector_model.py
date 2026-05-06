"""
Build sector orderings for pySCA correlation matrix views (notebook §IV).

Merges independent components (ICs) per user ``sec_groups`` (list of list of
0-based IC indices), matching the Ranganathan-lab S1A tutorial pattern.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any, List, Optional, Sequence, Tuple

import numpy as np

from core.pysca_io import ic_list_from_dsect


@dataclass
class MergedSector:
    """One output sector: sorted indices into alignment positions and display color index."""

    index: int
    ic_indices: List[int]  # source ICs merged
    items: List[int]  # alignment positions, sorted
    col: float = 0.4


def _ic_items(ics: Any) -> List[int]:
    if ics is None:
        return []
    items = getattr(ics, "items", None)
    if items is not None and not isinstance(items, (list, tuple, np.ndarray)):
        items = list(items) if items else []
    if items is None:
        if isinstance(ics, dict) and "items" in ics:
            items = ics["items"]
        else:
            return []
    if isinstance(items, np.ndarray):
        return [int(x) for x in items.tolist()]
    return [int(x) for x in list(items)]


def _ic_vect(ics: Any) -> List[float]:
    v = getattr(ics, "vect", None)
    if v is None:
        v = getattr(ics, "vec", None)
    if v is None and isinstance(ics, dict):
        v = ics.get("vect") or ics.get("vec")
    if v is None:
        return []
    if isinstance(v, np.ndarray):
        return [float(x) for x in v.flatten().tolist()]
    return [float(x) for x in list(v)]


def merge_ics_to_sectors(
    Dsect: dict,
    sec_groups: Sequence[Sequence[int]],
) -> Tuple[List[MergedSector], List[int]]:
    """
    Merge ``Dsect['ics']`` entries according to *sec_groups*.

    *sec_groups* is e.g. ``[[0,1], [2], [3,4,5]]`` meaning: sector 0 = IC0+IC1, etc.
    Within each sector, position indices are merged, then sorted by the
    concatenated *vect* values (loadings) ascending — same as the S1A notebook.

    Returns ``(merged_sectors, sortpos)`` where *sortpos* is the full reordering
    of positions (column order for the right-hand ``Csca`` imshow).
    """
    ics = ic_list_from_dsect(Dsect)
    n_ic = len(ics)
    if n_ic == 0:
        return [], []

    c_cycle = [0.4, 0.0, 0.7, 0.15, 0.9, 0.5, 0.2, 0.65, 0.35, 0.55]

    merged: List[MergedSector] = []
    for si, group in enumerate(sec_groups):
        glist = [int(x) for x in group if int(x) >= 0]
        if not glist:
            continue
        all_items: List[int] = []
        all_Vp: List[float] = []
        for j in glist:
            if j < 0 or j >= n_ic:
                continue
            unit = ics[j]
            items_u = _ic_items(unit)
            ve = _ic_vect(unit)
            if not items_u:
                continue
            if not ve or len(ve) < len(items_u):
                ve = (list(ve) if ve else []) + [0.0] * (len(items_u) - len(ve or []))
            elif len(ve) > len(items_u):
                ve = list(ve)[: len(items_u)]
            all_items = all_items + items_u
            all_Vp = all_Vp + [float(ve[i]) for i in range(len(items_u))]

        if not all_items:
            continue
        if not all_Vp or len(all_Vp) != len(all_items):
            all_Vp = [float(i) for i in range(len(all_items))]
        svals = np.argsort(np.asarray(all_Vp, dtype=np.float64))
        sorted_items = [all_items[i] for i in svals.tolist()]

        col = c_cycle[si % len(c_cycle)]
        merged.append(
            MergedSector(
                index=si,
                ic_indices=[j for j in glist if 0 <= j < n_ic],
                items=sorted_items,
                col=col,
            )
        )

    sortpos: List[int] = []
    seen: set = set()
    for m in merged:
        for p in m.items:
            if p not in seen:
                seen.add(p)
                sortpos.append(p)

    return merged, sortpos


def default_sec_groups(n_ic: int) -> List[List[int]]:
    """One IC per sector (identity mapping), length *n_ic*."""
    if n_ic <= 0:
        return []
    return [[i] for i in range(n_ic)]


def format_sec_groups_display(sec_groups: Sequence[Sequence[int]]) -> str:
    """
    Pretty text like the tutorial: ``([0], [1], [2], ...)``.

    *sec_groups* is a list of groups; each group is a list of IC indices.
    """
    if not sec_groups:
        return "()"
    inner = [list(g) for g in sec_groups]
    return repr(tuple(inner))


def parse_sec_groups_literal(text: str) -> List[List[int]]:
    """
    Parse ``([0], [1], [2])``-style input using :func:`ast.literal_eval` only.
    """
    t = (text or "").strip()
    if not t:
        return []
    try:
        node = ast.literal_eval(t)
    except (SyntaxError, ValueError, TypeError) as exc:
        raise ValueError(f"Invalid sector groups syntax: {exc}") from exc
    if not isinstance(node, (list, tuple)):
        raise ValueError("Sector groups must be a list or tuple, e.g. ([0], [1])")
    out: List[List[int]] = []
    for item in node:
        if not isinstance(item, (list, tuple)):
            raise ValueError("Each sector must be a list/tuple of IC indices, e.g. [0, 1]")
        nums: List[int] = []
        for x in item:
            if isinstance(x, bool):
                raise ValueError("IC indices must be integers, not bool")
            if isinstance(x, int):
                nums.append(x)
            elif isinstance(x, float) and float(x).is_integer():
                nums.append(int(x))
            else:
                raise ValueError("IC indices must be integers")
        out.append(nums)
    return out


def validate_sec_groups(
    n_ic: int, sec_groups: Sequence[Sequence[int]]
) -> Optional[str]:
    """
    Return an error string if *sec_groups* is invalid, else ``None``.

    Every IC index must appear in at most one group; indices must be in range.
    """
    if n_ic <= 0:
        return "No independent components (ICs) in this database."
    used: set = set()
    for group in sec_groups:
        for x in group:
            j = int(x)
            if j < 0 or j >= n_ic:
                return f"IC index {j} is out of range (0..{n_ic - 1})."
            if j in used:
                return f"IC index {j} appears in more than one sector group."
            used.add(j)
    return None
