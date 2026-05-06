"""
Phylogenetic analysis: pairwise identity, hierarchical clustering, reference branch tools.
"""

from __future__ import annotations

import os
import time
from typing import List, Optional

import numpy as np
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QFileDialog,
    QGroupBox,
    QComboBox,
    QMessageBox,
    QProgressBar,
    QSplitter,
    QTabWidget,
    QDoubleSpinBox,
    QSlider,
    QScrollArea,
    QFrame,
    QCheckBox,
)
from PyQt5.QtCore import Qt, pyqtSignal, QSettings, QTimer

from ui.theme import get_theme
from ui.icons import feather_icon, set_button_icon
from ui.widgets.searchable_combobox import SearchableComboBox
from ui.widgets.phylo_dendrogram_widget import PhyloDendrogramWidget
from ui.widgets.phylo_branch_profile_widget import PhyloBranchProfileWidget
from ui.widgets.phylo_overview_widgets import (
    PhyloClusterSizesWidget,
    PhyloIdentityHeatmapWidget,
)
from core.phylo_worker import PhyloResult, PhyloWorker
from core.phylo_engine import (
    extract_cluster_members,
    fasta_subset,
    max_merge_height,
    reference_branch_events,
)
from core.temp_fasta_manager import get_temp_fasta_manager
from scipy.cluster.hierarchy import fcluster

from utils.fasta_parser import FastaParser, FastaParseError


def _theme_dict() -> dict:
    t = get_theme()
    return {k: t.get(k) for k in (
        "bg_primary", "text_primary", "text_muted", "border", "accent", "error",
    )}


class PhyloPage(QWidget):
    """Hierarchical clustering on pairwise identity + reference branch extraction."""

    navigate_to_alignment = pyqtSignal(str)
    navigate_to_clustering = pyqtSignal(str, dict)

    def __init__(self):
        super().__init__()
        self.phylo_worker: Optional[PhyloWorker] = None
        self._result: Optional[PhyloResult] = None
        self._ref_idx: int = 0
        self._threshold: float = 0.35
        self._max_h: float = 1.0  # max merge height; slider maps to [0, max_h]
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(500)
        self._elapsed_timer.timeout.connect(self._tick_elapsed)
        self._run_t0: Optional[float] = None
        self._init_ui()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Vertical)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        top = QWidget()
        form = QVBoxLayout(top)
        form.setContentsMargins(28, 24, 28, 16)
        form.setSpacing(16)

        title = QLabel("Phylogenetic Analysis")
        title.setProperty("class", "title")
        form.addWidget(title)

        hint = QLabel(
            "Hierarchical clustering on a pairwise identity matrix. "
            "Choose a reference sequence to profile branch sizes across merge thresholds."
        )
        hint.setWordWrap(True)
        hint.setProperty("class", "muted")
        form.addWidget(hint)

        input_grp = QGroupBox("Input (aligned FASTA / MSA)")
        ig = QVBoxLayout()
        row = QHBoxLayout()
        self._browse_btn = QPushButton("Open FASTA file…")
        set_button_icon(self._browse_btn, "folder", 14, "#FFFFFF")
        self._browse_btn.clicked.connect(self._browse_file)
        self._use_alignment_btn = QPushButton("Use current alignment")
        self._use_alignment_btn.setProperty("class", "secondary")
        self._use_alignment_btn.clicked.connect(self._use_alignment_from_main)
        row.addWidget(self._browse_btn)
        row.addWidget(self._use_alignment_btn)
        row.addStretch()
        ig.addLayout(row)
        self._input_status = QLabel("No sequences loaded.")
        self._input_status.setProperty("class", "muted")
        ig.addWidget(self._input_status)
        self._fasta_text: str = ""
        input_grp.setLayout(ig)
        form.addWidget(input_grp)

        param_grp = QGroupBox("Parameters")
        pg = QVBoxLayout()
        mrow = QHBoxLayout()
        mrow.addWidget(QLabel("Linkage:"))
        self._link_combo = QComboBox()
        self._link_combo.addItem("Average (UPGMA)", "average")
        self._link_combo.addItem("Complete", "complete")
        self._link_combo.addItem("Single", "single")
        mrow.addWidget(self._link_combo)
        mrow.addStretch()
        pg.addLayout(mrow)

        rrow = QHBoxLayout()
        rrow.addWidget(QLabel("Reference sequence:"))
        self._ref_combo = SearchableComboBox()
        self._ref_combo.setMinimumWidth(280)
        rrow.addWidget(self._ref_combo, 1)
        pg.addLayout(rrow)

        th_row = QHBoxLayout()
        th_row.addWidget(QLabel("Distance threshold:"))
        self._thr_spin = QDoubleSpinBox()
        self._thr_spin.setRange(0.0, 1.0)
        self._thr_spin.setDecimals(4)
        self._thr_spin.setSingleStep(0.01)
        self._thr_spin.setValue(self._threshold)
        self._thr_spin.valueChanged.connect(self._on_threshold_spin)
        self._thr_slider = QSlider(Qt.Horizontal)
        self._thr_slider.setRange(0, 10000)
        self._thr_slider.setValue(int(self._threshold * 10000))
        self._thr_slider.valueChanged.connect(self._on_threshold_slider)
        th_row.addWidget(self._thr_spin)
        th_row.addWidget(self._thr_slider, 1)
        pg.addLayout(th_row)

        run_row = QHBoxLayout()
        self._run_btn = QPushButton("Run analysis")
        self._run_btn.setProperty("class", "success")
        set_button_icon(self._run_btn, "play", 14, "#FFFFFF")
        self._run_btn.clicked.connect(self._run_analysis)
        self._progress = QProgressBar()
        self._progress.setTextVisible(False)
        self._progress.setRange(0, 0)
        self._progress.hide()
        self._elapsed_lbl = QLabel("")
        self._elapsed_lbl.setProperty("class", "muted")
        run_row.addWidget(self._run_btn)
        run_row.addWidget(self._progress)
        run_row.addWidget(self._elapsed_lbl)
        run_row.addStretch()
        pg.addLayout(run_row)
        param_grp.setLayout(pg)
        form.addWidget(param_grp)

        scroll.setWidget(top)
        splitter.addWidget(scroll)

        # Results
        self._results_panel = QWidget()
        rp = QVBoxLayout(self._results_panel)
        rp.setContentsMargins(8, 8, 8, 8)
        self._status_lbl = QLabel()
        self._status_lbl.setProperty("class", "muted")
        self._status_lbl.setWordWrap(True)
        rp.addWidget(self._status_lbl)

        self._tabs = QTabWidget()
        thm = _theme_dict()
        self._dendro = PhyloDendrogramWidget()
        self._dendro.set_theme(thm)
        self._branch = PhyloBranchProfileWidget()
        self._branch.set_theme(thm)
        self._clusters = PhyloClusterSizesWidget()
        self._clusters.set_theme(thm)
        self._heatmap = PhyloIdentityHeatmapWidget()
        self._heatmap.set_theme(thm)

        self._tabs.addTab(self._dendro, feather_icon("layers", 14), "Dendrogram")
        self._tabs.addTab(self._branch, feather_icon("circle", 14), "Reference branch")
        self._tabs.addTab(self._clusters, feather_icon("bar-chart-2", 14), "Cluster sizes")
        self._tabs.addTab(self._heatmap, feather_icon("grid", 14), "Identity matrix")

        rp.addWidget(self._tabs, 1)

        act = QHBoxLayout()
        self._keep_gaps_cb = QCheckBox("Keep gaps in exported FASTA")
        self._keep_gaps_cb.setChecked(True)
        self._extract_btn = QPushButton("Extract reference branch…")
        set_button_icon(self._extract_btn, "download", 14, "#FFFFFF")
        self._extract_btn.setEnabled(False)
        self._extract_btn.clicked.connect(self._extract_branch)
        self._to_align_btn = QPushButton("Open in Alignment")
        self._to_align_btn.setProperty("class", "secondary")
        self._to_align_btn.setEnabled(False)
        self._to_align_btn.clicked.connect(self._goto_alignment)
        self._to_cluster_btn = QPushButton("Open in Clustering")
        self._to_cluster_btn.setProperty("class", "secondary")
        self._to_cluster_btn.setEnabled(False)
        self._to_cluster_btn.clicked.connect(self._goto_clustering)
        act.addWidget(self._keep_gaps_cb)
        act.addWidget(self._extract_btn)
        act.addWidget(self._to_align_btn)
        act.addWidget(self._to_cluster_btn)
        act.addStretch()
        rp.addLayout(act)

        self._last_extract_path: Optional[str] = None

        splitter.addWidget(self._results_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        settings = QSettings("SenLab", "ProteinGUI")
        key = "phylo_splitter"
        if settings.contains(key):
            splitter.restoreState(settings.value(key))
        else:
            splitter.setSizes([280, 520])
        splitter.splitterMoved.connect(
            lambda: settings.setValue(key, splitter.saveState())
        )
        self._splitter = splitter
        root.addWidget(splitter)

        self._results_panel.hide()

        self._dendro.threshold_changed.connect(self._on_threshold_from_plot)
        self._branch.threshold_changed.connect(self._on_threshold_from_plot)
        self._ref_combo.currentIndexChanged.connect(self._on_ref_changed)

    def _tick_elapsed(self):
        if self._run_t0 is None:
            return
        secs = int(time.monotonic() - self._run_t0)
        self._elapsed_lbl.setText(f"Running… {secs}s")

    def load_fasta_text(self, text: str, *, show_error: bool = True) -> bool:
        text = text or ""
        if not text.strip():
            if show_error:
                QMessageBox.information(self, "Phylogenetic", "No FASTA content.")
            return False
        try:
            p = FastaParser()
            seqs = p.parse_string(text)
        except FastaParseError as e:
            if show_error:
                QMessageBox.warning(self, "FASTA", str(e))
            return False
        if len(seqs) < 2:
            if show_error:
                QMessageBox.information(
                    self, "Phylogenetic", "Need at least two sequences in the alignment."
                )
            return False
        self._fasta_text = text
        self._input_status.setText(f"{len(seqs)} sequences loaded.")
        self._populate_ref_combo([s.id for s in seqs])
        return True

    def _populate_ref_combo(self, labels: List[str]):
        self._ref_combo.blockSignals(True)
        if not labels:
            self._ref_combo.clear()
            self._ref_combo.all_items = []
            self._ref_combo.all_data = {}
        else:
            items = {lb: i for i, lb in enumerate(labels)}
            self._ref_combo.setItems(items)
        self._ref_combo.blockSignals(False)
        self._ref_idx = 0

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open MSA (FASTA)",
            "",
            "FASTA (*.fasta *.fa *.faa);;All Files (*.*)",
        )
        if not path:
            return
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                self.load_fasta_text(f.read(), show_error=True)
        except OSError as e:
            QMessageBox.warning(self, "File", str(e))

    def _use_alignment_from_main(self):
        win = self.window()
        ac = getattr(getattr(win, "alignment_page", None), "aligned_content", None)
        if not ac:
            QMessageBox.information(
                self,
                "Alignment",
                "No alignment available yet. Run an alignment on the Alignment tab first.",
            )
            return
        if not self.load_fasta_text(ac, show_error=True):
            return

    def _current_ref_idx(self) -> int:
        data = self._ref_combo.getCurrentData()
        if isinstance(data, int):
            return data
        txt = self._ref_combo.currentText()
        if txt in self._ref_combo.all_data and isinstance(
            self._ref_combo.all_data[txt], int
        ):
            return self._ref_combo.all_data[txt]
        return 0

    def _on_ref_changed(self, *_):
        self._ref_idx = self._current_ref_idx()
        if self._result is not None:
            self._refresh_views()

    def _on_threshold_spin(self, v: float):
        self._threshold = float(v)
        self._sync_slider_from_threshold()
        self._dendro.set_threshold(self._threshold)
        self._branch.set_threshold(self._threshold)
        if self._result is not None:
            self._clusters.set_data(self._result.Z, self._threshold)
        self._update_status()

    def _on_threshold_slider(self, vi: int):
        mh = max(self._max_h, 1e-12)
        v = (vi / 10000.0) * mh
        self._thr_spin.blockSignals(True)
        self._thr_spin.setValue(v)
        self._thr_spin.blockSignals(False)
        self._threshold = v
        self._dendro.set_threshold(v)
        self._branch.set_threshold(v)
        if self._result is not None:
            self._clusters.set_data(self._result.Z, self._threshold)
        self._update_status()

    def _on_threshold_from_plot(self, v: float):
        mh = max(self._max_h, 1e-12)
        v = float(min(max(v, 0.0), mh))
        self._thr_spin.blockSignals(True)
        self._thr_spin.setValue(v)
        self._thr_spin.blockSignals(False)
        self._sync_slider_from_threshold()
        self._threshold = v
        self._dendro.set_threshold(v)
        self._branch.set_threshold(v)
        if self._result is not None:
            self._clusters.set_data(self._result.Z, self._threshold)
        self._update_status()

    def _sync_slider_from_threshold(self) -> None:
        mh = max(self._max_h, 1e-12)
        self._thr_slider.blockSignals(True)
        self._thr_slider.setValue(int(self._threshold / mh * 10000))
        self._thr_slider.blockSignals(False)

    def _run_analysis(self):
        if not self._fasta_text.strip():
            QMessageBox.information(self, "Phylogenetic", "Load a FASTA MSA first.")
            return
        if self.phylo_worker and self.phylo_worker.isRunning():
            QMessageBox.information(self, "Phylogenetic", "A run is already in progress.")
            return
        method = self._link_combo.currentData() or "average"
        self._run_btn.setEnabled(False)
        self._progress.show()
        self._run_t0 = time.monotonic()
        self._elapsed_timer.start()
        self._elapsed_lbl.setText("Running…")
        self.phylo_worker = PhyloWorker(self._fasta_text, method=method)
        self.phylo_worker.progress.connect(self._on_worker_progress)
        self.phylo_worker.finished.connect(self._on_worker_done)
        self.phylo_worker.error.connect(self._on_worker_error)
        self.phylo_worker.start()

    def _on_worker_progress(self, msg: str):
        self._status_lbl.setText(msg)

    def _on_worker_error(self, msg: str):
        self._stop_run_ui()
        QMessageBox.warning(self, "Phylogenetic", msg)

    def _on_worker_done(self, result: PhyloResult):
        self._stop_run_ui()
        self._result = result
        self._populate_ref_combo(result.labels)
        mh = max_merge_height(result.Z)
        self._max_h = float(mh) if mh > 0 else 1.0
        self._thr_spin.setRange(0.0, max(1e-12, self._max_h))
        self._thr_spin.setSingleStep(max(1e-6, self._max_h / 500))
        # default cut ~ third of max height if unchanged
        if self._threshold > self._max_h:
            self._threshold = self._max_h * 0.35
        self._thr_spin.setValue(self._threshold)
        self._thr_slider.setRange(0, 10000)
        self._on_threshold_spin(self._threshold)
        self._ref_idx = self._current_ref_idx()
        self._refresh_views()
        self._results_panel.show()
        self._extract_btn.setEnabled(True)
        tot = (
            f"Done in {result.elapsed_s:.2f}s — {result.n} sequences, "
            f"linkage={result.method}."
        )
        self._input_status.setText(tot)
        self._update_status()

    def _stop_run_ui(self):
        self._elapsed_timer.stop()
        self._run_t0 = None
        self._elapsed_lbl.setText("")
        self._progress.hide()
        self._run_btn.setEnabled(True)

    def _refresh_views(self):
        if self._result is None:
            return
        r = self._result
        self._ref_idx = self._current_ref_idx()
        thm = _theme_dict()
        self._dendro.set_theme(thm)
        self._branch.set_theme(thm)
        self._clusters.set_theme(thm)
        self._heatmap.set_theme(thm)
        self._dendro.set_data(r.Z, r.labels, self._ref_idx, self._threshold)
        ev = reference_branch_events(r.Z, r.n, self._ref_idx)
        self._branch.set_events(ev)
        self._branch.set_threshold(self._threshold)
        self._clusters.set_data(r.Z, self._threshold)
        self._heatmap.set_data(r.identity, r.labels, r.Z)
        self._update_status()

    def _update_status(self):
        if self._result is None:
            self._status_lbl.setText("")
            return
        r = self._result
        try:
            memb = extract_cluster_members(r.Z, self._threshold, self._ref_idx)
            labs = fcluster(r.Z, t=self._threshold, criterion="distance")
            k = len(set(labs.tolist()))
        except Exception:
            memb = []
            k = 0
        self._status_lbl.setText(
            f"Reference branch at current threshold: {len(memb)} sequence(s). "
            f"{k} cluster(s) total at this cut."
        )

    def _extract_branch(self):
        if self._result is None:
            return
        r = self._result
        idx = extract_cluster_members(r.Z, self._threshold, self._ref_idx)
        if idx.size == 0:
            QMessageBox.information(self, "Extract", "No sequences in this branch.")
            return
        text = fasta_subset(
            r.headers,
            r.sequences,
            idx.tolist(),
            keep_gaps=self._keep_gaps_cb.isChecked(),
        )
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save reference branch as FASTA",
            "reference_branch.fasta",
            "FASTA (*.fasta *.fa);;All Files (*.*)",
        )
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
            except OSError as e:
                QMessageBox.warning(self, "Save", str(e))
                return
        # Always register temp for downstream tools
        tpm = get_temp_fasta_manager()
        tpath = tpm.write_temp_fasta_string(text, prefix="phylo_branch_")
        self._last_extract_path = tpath
        self._to_align_btn.setEnabled(True)
        self._to_cluster_btn.setEnabled(True)
        if path:
            QMessageBox.information(
                self,
                "Saved",
                f"Wrote {len(idx)} sequence(s) to:\n{path}\n\n"
                f"A temporary copy was registered for Open in Alignment / Clustering.",
            )

    def _goto_alignment(self):
        if self._last_extract_path and os.path.isfile(self._last_extract_path):
            self.navigate_to_alignment.emit(self._last_extract_path)

    def _goto_clustering(self):
        if self._last_extract_path and os.path.isfile(self._last_extract_path):
            self.navigate_to_clustering.emit(self._last_extract_path, {})
