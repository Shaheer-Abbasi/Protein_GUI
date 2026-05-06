"""
Matplotlib figures mirroring pySCA tutorial sections II–IV (generic plots).

Theme colors are passed as a dict compatible with ``ThemeManager.get(key)``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy.stats import scoreatpercentile

from core.pysca_io import get_array, ic_list_from_dsect
from core.pysca_sector_model import MergedSector


def _theme_style(
    theme: Dict[str, str],
) -> Tuple[str, str, str, str, str]:
    bg = theme.get("bg_primary", "#0F1117")
    text_c = theme.get("text_primary", "#E5E8EB")
    muted = theme.get("text_muted", "#6C7A89")
    border = theme.get("border", "#2A2D3E")
    accent = theme.get("accent", "#5DADE2")
    return bg, text_c, muted, border, accent


def _style_axis(ax, title: str, theme: Dict[str, str], bg: str, text_c: str, muted: str, border: str) -> None:
    ax.set_facecolor(bg)
    if title:
        ax.set_title(title, fontsize=11, fontweight="bold", color=text_c, pad=8)
    ax.tick_params(colors=muted, labelsize=9)
    for spine in ax.spines.values():
        spine.set_color(border)
    ax.xaxis.label.set_color(muted)
    ax.yaxis.label.set_color(muted)


def draw_conservation_figure(
    Dseq: dict,
    Dsca: dict,
    Dsect: dict,
    theme: Dict[str, str],
    figsize: Tuple[float, float] = (10.0, 4.5),
):
    """§II: Bar chart of D_i with aa labels on selected ticks (notebook style)."""
    import matplotlib.pyplot as plt

    Di = get_array(Dsca, Dsect, "Di")
    if Di is None:
        fig, ax = plt.subplots(figsize=figsize)
        bg, text_c, muted, border, _ = _theme_style(theme)
        _style_axis(ax, "Positional conservation (Di)", theme, bg, text_c, muted, border)
        ax.text(0.5, 0.5, "Di not found in database", ha="center", va="center", color=muted, transform=ax.transAxes)
        fig.patch.set_facecolor(bg)
        return fig

    vec = np.asarray(Di).flatten()
    n = len(vec)
    xvals = np.arange(1, n + 1)
    ats: List = list(Dseq.get("ats", [])) if Dseq.get("ats") is not None else []
    npos = Dseq.get("Npos", n)

    bg, text_c, muted, border, accent = _theme_style(theme)
    fig, ax = plt.subplots(figsize=figsize)
    fig.patch.set_facecolor(bg)
    ax.bar(xvals, vec, color=text_c, width=1.0, edgecolor="none")
    _style_axis(ax, "Positional conservation (D_i)", theme, bg, text_c, muted, border)
    ax.set_xlabel("Amino acid position (alignment index)", fontsize=10)
    ax.set_ylabel("D_i", fontsize=10)
    if len(ats) >= n and n > 0:
        step = max(1, n // 5)
        ticks = list(range(1, n + 1, step))[:6]
        if n not in ticks and n > 0:
            ticks.append(n)
        tick_idx = [t - 1 for t in ticks if 0 <= t - 1 < len(ats)]
        if tick_idx:
            ax.set_xticks([i + 1 for i in tick_idx])
            ax.set_xticklabels([str(ats[i]) for i in tick_idx])
    ax.grid(True, alpha=0.2, color=border)
    return fig


def draw_csca_heatmap_figure(
    Dsca: dict,
    Dsect: dict,
    theme: Dict[str, str],
    figsize: Tuple[float, float] = (9.0, 7.5),
    vmin: float = 0.0,
    vmax: float = 1.4,
):
    """§III: Full C_sca matrix."""
    import matplotlib.pyplot as plt

    C = get_array(Dsca, Dsect, "Csca")
    bg, text_c, muted, border, _ = _theme_style(theme)
    fig, ax = plt.subplots(figsize=figsize)
    fig.patch.set_facecolor(bg)
    if C is None or C.size == 0:
        _style_axis(ax, "C_sca (SCA correlation)", theme, bg, text_c, muted, border)
        ax.text(0.5, 0.5, "C_sca not found", ha="center", va="center", color=muted, transform=ax.transAxes)
        return fig
    C = np.asarray(C, dtype=np.float64)
    im = ax.imshow(C, vmin=vmin, vmax=vmax, aspect="equal", interpolation="nearest", cmap="inferno")
    _style_axis(ax, r"$\tilde{C}_{ij}$ (SCA)", theme, bg, text_c, muted, border)
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.ax.yaxis.set_tick_params(color=muted)
    cbar.set_label("covariance (scaled)", color=muted, fontsize=9)
    return fig


def draw_eigen_spectrum_figure(
    Dsca: dict,
    Dsect: dict,
    theme: Dict[str, str],
    figsize: Tuple[float, float] = (10.0, 4.5),
):
    """
    Histogram of eigenvalues: observed L_sca (black) vs L_rand distribution (red curve).
    """
    import matplotlib.pyplot as plt

    bg, text_c, muted, border, accent = _theme_style(theme)
    Lrand = Dsca.get("Lrand")
    Lsca = get_array(Dsca, Dsect, "Lsca", prefer_sector=True)
    if Lsca is None:
        Lsca = Dsca.get("Lsca")
    Ntrials = int(Dsca.get("Ntrials", 0) or 0)

    Dsect_L = Dsect.get("Lsca")
    if Dsect_L is not None and Lsca is None:
        Lsca = np.asarray(Dsect_L, dtype=np.float64)

    fig, ax = plt.subplots(figsize=figsize)
    fig.patch.set_facecolor(bg)
    if Lsca is None or (getattr(Lsca, "size", 0) or 0) == 0:
        _style_axis(ax, "Eigenspectrum", theme, bg, text_c, muted, border)
        ax.text(0.5, 0.5, "Eigenvalue data not found", ha="center", va="center", color=muted, transform=ax.transAxes)
        return fig

    Lsca = np.asarray(Lsca, dtype=np.float64).flatten()
    npos = int(Dsca.get("Npos", len(Lsca)))
    # notebook uses Dseq['Npos'] for bin count; fallback
    n_bins = min(max(4, npos if npos else len(Lsca)), len(Lsca) * 2)
    lmax = float(Lsca.max()) if Lsca.size else 1.0
    if Lrand is not None and Ntrials > 0 and np.asarray(Lrand).size:
        Lrand = np.asarray(Lrand, dtype=np.float64)
        hist0, bins = np.histogram(Lrand.flatten(), bins=npos if npos else n_bins, range=(0, lmax * 1.01))
    else:
        hist0, bins = None, None

    hist1, bins1 = np.histogram(Lsca, bins=npos if npos else n_bins, range=(0, lmax * 1.01))
    ax.bar(bins1[:-1], hist1, width=np.diff(bins1), align="edge", color=text_c, edgecolor=border, linewidth=0.3, label="Observed L_sca")
    if hist0 is not None and bins is not None and len(bins) > 1:
        ax.plot(
            bins[:-1],
            hist0 / max(Ntrials, 1),
            color=accent,
            linewidth=2,
            label="L_rand / Ntrials" if Ntrials else "L_rand",
        )
    _style_axis(ax, "Eigenspectrum of coevolution matrix", theme, bg, text_c, muted, border)
    ax.set_xlabel("Eigenvalues", fontsize=10)
    ax.set_ylabel("Count", fontsize=10)
    if Dsect.get("kpos") is not None:
        kpos = int(Dsect["kpos"])
        ax.text(
            0.99,
            0.95,
            f"k* = {kpos}",
            transform=ax.transAxes,
            ha="right",
            va="top",
            color=muted,
            fontsize=10,
        )
    ax.legend(loc="upper right", framealpha=0.5, fontsize=8)
    return fig


def draw_ev_ic_pairs_figure(
    Dsect: dict,
    theme: Dict[str, str],
    figsize: Tuple[float, float] = (10.5, 6.0),
):
    """§III: EV vs EV (top) and IC vs IC (bottom) pairwise scatter."""
    import matplotlib.pyplot as plt

    bg, text_c, muted, border, accent = _theme_style(theme)
    EVs = get_array({}, Dsect, "Vsca", prefer_sector=True)
    if EVs is None:
        EVs = Dsect.get("Vsca")
    ICs = get_array({}, Dsect, "Vpica", prefer_sector=True)
    if ICs is None:
        ICs = Dsect.get("Vpica")
    kpos = int(Dsect.get("kpos", 0) or 0)

    fig = plt.figure(figsize=figsize)
    fig.patch.set_facecolor(bg)
    if EVs is None or ICs is None or kpos < 2:
        ax = fig.add_subplot(1, 1, 1)
        _style_axis(ax, "EV / IC pairs", theme, bg, text_c, muted, border)
        ax.text(0.5, 0.5, "Vsca / Vpica not found or kpos < 2", ha="center", va="center", color=muted, transform=ax.transAxes)
        return fig

    EVs = np.asarray(EVs, dtype=np.float64)
    ICs = np.asarray(ICs, dtype=np.float64)
    pairs = [[x, x + 1] for x in range(0, kpos - 1, 2)]
    ncols = max(1, len(pairs))
    if not pairs:
        ax = fig.add_subplot(1, 1, 1)
        ax.set_facecolor(bg)
        ax.text(0.5, 0.5, "Need at least two eigenmodes for EV/IC pairs.", ha="center", va="center", color=muted, transform=ax.transAxes)
        return fig

    for idx, (k1, k2) in enumerate(pairs):
        if k2 >= EVs.shape[1] or k2 >= ICs.shape[1]:
            break
        ax_t = fig.add_subplot(2, ncols, idx + 1)
        ax_t.set_facecolor(bg)
        ax_t.plot(EVs[:, k1], EVs[:, k2], "o", color=text_c, markersize=2, alpha=0.6)
        ax_t.set_xlabel(f"EV{k1 + 1}", color=muted)
        ax_t.set_ylabel(f"EV{k2 + 1}", color=muted)
        ax_t.tick_params(colors=muted, labelsize=8)
        for s in ax_t.spines.values():
            s.set_color(border)

        ax_b = fig.add_subplot(2, ncols, idx + 1 + ncols)
        ax_b.set_facecolor(bg)
        ax_b.plot(ICs[:, k1], ICs[:, k2], "o", color=accent, markersize=2, alpha=0.6)
        ax_b.set_xlabel(f"IC{k1 + 1}", color=muted)
        ax_b.set_ylabel(f"IC{k2 + 1}", color=muted)
        ax_b.tick_params(colors=muted, labelsize=8)
        for s in ax_b.spines.values():
            s.set_color(border)

    fig.suptitle("Top eigenvectors (EV) and independent components (IC)", color=text_c, fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.96], pad=1.2)
    return fig


def draw_ic_distribution_figures(
    Dsect: dict,
    theme: Dict[str, str],
    max_rows: int = 12,
):
    """§IV: Histograms of V^p for each IC with optional t-fit and cutoff."""
    import matplotlib.pyplot as plt

    bg, text_c, muted, border, accent = _theme_style(theme)
    Vp = Dsect.get("Vpica")
    if Vp is None:
        fig, ax = plt.subplots()
        fig.patch.set_facecolor(bg)
        _style_axis(ax, "IC distributions", theme, bg, text_c, muted, border)
        ax.text(0.5, 0.5, "Vpica not found", ha="center", va="center", color=muted, transform=ax.transAxes)
        return fig

    Vp = np.asarray(Vp, dtype=np.float64)
    kpos = int(Dsect.get("kpos", Vp.shape[1]))
    kpos = min(kpos, Vp.shape[1], max_rows)
    scaled_pd = Dsect.get("scaled_pd")
    cutoff = Dsect.get("cutoff")
    line_color = accent

    nrows = kpos
    h_fig = min(0.55 * nrows, 20)
    fig, axes = plt.subplots(nrows, 1, figsize=(8, h_fig), sharex=False)
    fig.patch.set_facecolor(bg)
    if nrows == 1:
        axes = [axes]

    for k in range(kpos):
        ax = axes[k]
        ax.set_facecolor(bg)
        data = Vp[:, k]
        if len(data) < 1:
            continue
        iqr = scoreatpercentile(data, 75) - scoreatpercentile(data, 25)
        binw = 2 * iqr * (len(data) ** (-0.33)) if iqr > 0 else max((data.max() - data.min()) / 10.0, 1e-9)
        dr = data.max() - data.min()
        nbins = max(4, int(round(dr / max(binw, 1e-9))))
        h_p = ax.hist(data, nbins, color=text_c, alpha=0.75, edgecolor=border, linewidth=0.3)
        if scaled_pd is not None:
            sp = np.asarray(scaled_pd[k]) if k < len(scaled_pd) else None
            if sp is not None and sp.size:
                x_dist = np.linspace(
                    float(np.min(h_p[1])),
                    float(np.max(h_p[1])),
                    num=min(200, max(20, sp.size)),
                )
                if sp.ndim == 1 and len(x_dist) == len(sp):
                    ax.plot(x_dist, sp, color=line_color, linewidth=1.5)
        if cutoff is not None:
            co = np.asarray(cutoff, dtype=np.float64)
            if k < co.size:
                cval = float(co[k])
                ymax = max(h_p[0]) if len(h_p[0]) else 1.0
                ax.plot([cval, cval], [0, ymax * 1.05], color=muted, linestyle="--", linewidth=1)
        ax.set_xlabel(r"$V^p_{" + str(k + 1) + "}$", fontsize=9, color=muted)
        ax.set_ylabel("Count", fontsize=9, color=muted)
        ax.tick_params(colors=muted, labelsize=8)
        for s in ax.spines.values():
            s.set_color(border)

    fig.suptitle("IC loading distributions", color=text_c, fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.99], h_pad=0.8, pad=1.0)
    return fig


def draw_two_panel_sector_matrices(
    Dsca: dict,
    Dsect: dict,
    theme: Dict[str, str],
    user_sortpos: List[int],
    user_sectors: List[MergedSector],
    figsize: Tuple[float, float] = (11.0, 5.5),
    vmin: float = 0.0,
    vmax: float = 2.2,
):
    """
    Left: C_sca ordered by ``Dsect['sortedpos']`` with IC boundary lines.
    Right: C_sca ordered by *user_sortpos* with sector boundary lines.
    """
    import matplotlib.pyplot as plt

    bg, text_c, muted, border, accent = _theme_style(theme)
    C = get_array(Dsca, Dsect, "Csca")
    line = "#ffffff"

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=figsize)
    fig.patch.set_facecolor(bg)
    for ax in (ax1, ax2):
        ax.set_facecolor(bg)
        ax.tick_params(colors=muted, labelsize=7)
        for s in ax.spines.values():
            s.set_color(border)

    if C is None or C.size == 0:
        ax1.text(0.5, 0.5, "C_sca missing", ha="center", va="center", color=muted, transform=ax1.transAxes)
        ax2.text(0.5, 0.5, "C_sca missing", ha="center", va="center", color=muted, transform=ax2.transAxes)
        return fig

    C = np.asarray(C, dtype=np.float64)
    n = C.shape[0]

    def _draw_reordered(
        ax,
        pos_idx: List[int],
        block_sizes: List[int] | None,
        title: str,
    ) -> None:
        ok = [int(p) for p in pos_idx if 0 <= int(p) < n]
        if len(ok) < 2:
            ax.text(0.5, 0.5, "Invalid indices", ha="center", va="center", color=muted, transform=ax.transAxes)
            ax.set_title(title, color=text_c, fontsize=10)
            return
        sub = C[np.ix_(ok, ok)]
        m = sub.shape[0]
        im = ax.imshow(
            sub,
            vmin=vmin,
            vmax=vmax,
            interpolation="nearest",
            aspect="equal",
            origin="upper",
            extent=[0, m, 0, m],
        )
        if block_sizes:
            line_idx = 0
            for sz in block_sizes:
                if sz <= 0:
                    continue
                x = line_idx + int(sz)
                if 0 < x < m:
                    ax.plot([x, x], [0, m], color=line, linewidth=1.2)
                    ax.plot([0, m], [m - x, m - x], color=line, linewidth=1.2)
                line_idx += int(sz)
        ax.set_xlim(0, m)
        ax.set_ylim(0, m)
        _style_axis(ax, title, theme, bg, text_c, muted, border)
        fig.colorbar(im, ax=ax, fraction=0.04, pad=0.04)

    sortedpos = Dsect.get("sortedpos")
    icsize = Dsect.get("icsize")
    if sortedpos is not None:
        sp0 = [int(x) for x in np.asarray(sortedpos).flatten() if 0 <= int(x) < n]
        if not sp0:
            sp0 = list(range(n))
    else:
        sp0 = list(range(n))
    b_left = [int(x) for x in np.asarray(icsize).flatten()] if icsize is not None else None
    if b_left is None and Dsect.get("kpos") is not None and ic_list_from_dsect(Dsect):
        nics = len(ic_list_from_dsect(Dsect))
        if nics > 0 and len(sp0) == n and n % nics == 0:
            chunk = n // nics
            b_left = [chunk] * nics

    _draw_reordered(ax1, sp0, b_left, "C_sca (IC order)")

    if user_sortpos and user_sectors:
        b_right = [len(s.items) for s in user_sectors if s.items]
        _draw_reordered(ax2, user_sortpos, b_right, "C_sca (custom sectors)")
    else:
        _draw_reordered(ax2, sp0, b_left, "C_sca (custom sectors)")

    fig.suptitle("Sector-ordered coevolution matrix", color=text_c, fontsize=11)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    return fig


def format_ic_pymol_lines(Dseq: dict, Dsect: dict) -> str:
    """Text block: one line per IC with PyMOL position lists (1-based if ats are aligned labels)."""
    ics = ic_list_from_dsect(Dsect)
    ats = Dseq.get("ats")
    lines: List[str] = []
    for n, u in enumerate(ics):
        items: List[int] = []
        if u is not None:
            raw = getattr(u, "items", None) or (u.get("items") if isinstance(u, dict) else None)  # type: ignore[union-attr]  # noqa: E501
            if raw is not None:
                items = [int(x) for x in (raw.tolist() if hasattr(raw, "tolist") else list(raw))]  # type: ignore[arg-type]  # noqa: E501
        if ats is not None and len(ats) and items:
            ats = list(ats)
            at_str = [str(ats[i]) for i in items if 0 <= i < len(ats)]
            pym = "+".join(at_str) if at_str else "+".join(str(i + 1) for i in items)
        else:
            pym = "+".join(str(i + 1) for i in items)
        lines.append(f"IC {n + 1} ({len(items)} pos): {pym}\n")
    return "".join(lines) if lines else "(no IC data)\n"
