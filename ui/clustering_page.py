import os
import time
import shutil
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QLineEdit, QComboBox, QGroupBox,
    QTextEdit, QProgressBar, QMessageBox, QTabWidget, QTableWidget,
    QTableWidgetItem, QDoubleSpinBox, QCheckBox, QScrollArea, QSplitter,
    QFrame, QSpinBox, QSizePolicy
)
from PyQt5.QtCore import pyqtSignal, Qt, QTimer, QSettings
from PyQt5.QtGui import QPixmap

from ui.theme import get_theme
from ui.icons import feather_icon, set_button_icon
from core.clustering_worker import ClusteringWorker
from core.clustering_manager import validate_fasta_file, export_clustering_tsv, get_cluster_table_data
from core.clustering_visualizer import create_distribution_chart, create_text_summary, export_chart_html
from core.tool_install_worker import ToolInstallWorker
from core.tool_runtime import get_tool_runtime
from ui.dialogs.chart_maximize_dialog import ChartMaximizeDialog


class ClusteringPage(QWidget):
    back_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.clustering_worker = None
        self.fasta_path = None
        self.clustering_results = None
        self.rep_fasta_path = None
        self.tsv_path = None
        self.chart_path = None
        self.temp_dir = None
        self.search_start_time = None
        self.is_temp_fasta = False
        self.loaded_from_search = False
        self.tool_install_worker = None
        self._pending_tool_action = None
        self._init_ui()
        QTimer.singleShot(2000, self.check_system_requirements)

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Vertical)

        # ── Top: input controls ──────────────────────────────────
        input_scroll = QScrollArea()
        input_scroll.setWidgetResizable(True)
        input_scroll.setFrameShape(QFrame.NoFrame)

        input_widget = QWidget()
        form = QVBoxLayout(input_widget)
        form.setContentsMargins(28, 24, 28, 16)
        form.setSpacing(16)

        title = QLabel("MMseqs2 Clustering")
        title.setProperty("class", "title")
        form.addWidget(title)

        # System requirements warning
        self.warning_label = QLabel()
        self.warning_label.setWordWrap(True)
        self.warning_label.hide()
        form.addWidget(self.warning_label)

        # ── File selection ───────────────────────────────────────
        file_group = QGroupBox("Select FASTA File")
        fl = QVBoxLayout()

        upload_row = QHBoxLayout()
        self.file_path_input = QLineEdit()
        self.file_path_input.setPlaceholderText("No file selected...")
        self.file_path_input.setReadOnly(True)
        browse_btn = QPushButton("Browse")
        set_button_icon(browse_btn, "folder", 14, "#FFFFFF")
        browse_btn.clicked.connect(self.browse_fasta_file)
        upload_row.addWidget(self.file_path_input)
        upload_row.addWidget(browse_btn)

        self.file_info_label = QLabel()
        self.file_info_label.setProperty("class", "muted")

        fl.addLayout(upload_row)
        fl.addWidget(self.file_info_label)
        file_group.setLayout(fl)
        form.addWidget(file_group)

        # ── Parameters ───────────────────────────────────────────
        params_group = QGroupBox("Clustering Parameters")
        pl = QVBoxLayout()

        r_mode = QHBoxLayout()
        r_mode.addWidget(QLabel("Clustering Mode:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Cluster (Cascaded - Accurate, slower)", "cluster")
        self.mode_combo.addItem("Cluster (Single-step - Faster)", "cluster_single")
        self.mode_combo.addItem("Linclust (Linear time, >=50% identity only)", "linclust")
        self.mode_combo.currentIndexChanged.connect(self.on_mode_changed)
        r_mode.addWidget(self.mode_combo)
        r_mode.addStretch()
        pl.addLayout(r_mode)

        r_id = QHBoxLayout()
        r_id.addWidget(QLabel("Min Sequence Identity:"))
        self.identity_spin = QDoubleSpinBox()
        self.identity_spin.setRange(0.0, 1.0)
        self.identity_spin.setSingleStep(0.05)
        self.identity_spin.setValue(0.5)
        self.identity_spin.setDecimals(2)
        self.identity_spin.valueChanged.connect(self.validate_parameters)
        r_id.addWidget(self.identity_spin)
        r_id.addSpacing(16)
        r_id.addWidget(QLabel("Coverage:"))
        self.coverage_spin = QDoubleSpinBox()
        self.coverage_spin.setRange(0.0, 1.0)
        self.coverage_spin.setSingleStep(0.05)
        self.coverage_spin.setValue(0.8)
        self.coverage_spin.setDecimals(2)
        r_id.addWidget(self.coverage_spin)
        r_id.addStretch()
        pl.addLayout(r_id)

        r_cov = QHBoxLayout()
        r_cov.addWidget(QLabel("Coverage Mode:"))
        self.covmode_combo = QComboBox()
        self.covmode_combo.addItem("Bidirectional (max of query/target)", 0)
        self.covmode_combo.addItem("Target coverage", 1)
        self.covmode_combo.addItem("Query coverage", 2)
        r_cov.addWidget(self.covmode_combo)
        r_cov.addSpacing(16)
        r_cov.addWidget(QLabel("E-value:"))
        self.evalue_spin = QDoubleSpinBox()
        self.evalue_spin.setRange(1e-100, 100)
        self.evalue_spin.setDecimals(6)
        self.evalue_spin.setValue(0.001)
        r_cov.addWidget(self.evalue_spin)
        r_cov.addStretch()
        pl.addLayout(r_cov)

        # Advanced options
        self.advanced_checkbox = QCheckBox("Show Advanced Options")
        self.advanced_checkbox.stateChanged.connect(self.toggle_advanced_options)

        self.advanced_widget = QWidget()
        aw = QVBoxLayout(self.advanced_widget)
        aw.setContentsMargins(0, 8, 0, 0)

        r_sens = QHBoxLayout()
        r_sens.addWidget(QLabel("Sensitivity:"))
        self.sens_spin = QDoubleSpinBox()
        self.sens_spin.setRange(1.0, 7.5)
        self.sens_spin.setSingleStep(0.5)
        self.sens_spin.setValue(7.5)
        self.sens_spin.setDecimals(1)
        self.sens_auto_checkbox = QCheckBox("Auto (recommended)")
        self.sens_auto_checkbox.setChecked(True)
        self.sens_auto_checkbox.stateChanged.connect(
            lambda: self.sens_spin.setEnabled(not self.sens_auto_checkbox.isChecked()))
        self.sens_spin.setEnabled(False)
        r_sens.addWidget(self.sens_spin)
        r_sens.addWidget(self.sens_auto_checkbox)
        r_sens.addStretch()
        aw.addLayout(r_sens)

        r_kmer = QHBoxLayout()
        self.kmer_label_widget = QLabel("K-mers per Sequence:")
        r_kmer.addWidget(self.kmer_label_widget)
        self.kmer_spin = QDoubleSpinBox()
        self.kmer_spin.setRange(10, 100)
        self.kmer_spin.setSingleStep(5)
        self.kmer_spin.setValue(20)
        self.kmer_spin.setDecimals(0)
        self.kmer_spin.setEnabled(False)
        r_kmer.addWidget(self.kmer_spin)
        r_kmer.addStretch()
        aw.addLayout(r_kmer)

        self.advanced_widget.hide()
        pl.addWidget(self.advanced_checkbox)
        pl.addWidget(self.advanced_widget)
        params_group.setLayout(pl)
        form.addWidget(params_group)

        # Parameter validation
        self.param_warning_label = QLabel()
        self.param_warning_label.setWordWrap(True)
        self.param_warning_label.hide()
        form.addWidget(self.param_warning_label)

        # Control buttons
        ctrl_row = QHBoxLayout()

        self.save_fasta_button = QPushButton("Save FASTA Permanently")
        self.save_fasta_button.setProperty("class", "secondary")
        set_button_icon(self.save_fasta_button, "save", 14)
        self.save_fasta_button.clicked.connect(self._save_fasta_permanently)
        self.save_fasta_button.setVisible(False)

        self.run_button = QPushButton("Run Clustering")
        self.run_button.setProperty("class", "success")
        set_button_icon(self.run_button, "play", 16, "#FFFFFF")
        self.run_button.setMinimumHeight(40)
        self.run_button.clicked.connect(self.run_clustering)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setProperty("class", "danger")
        set_button_icon(self.cancel_button, "x", 14, "#FFFFFF")
        self.cancel_button.setMinimumHeight(40)
        self.cancel_button.clicked.connect(self.cancel_clustering)
        self.cancel_button.setEnabled(False)

        ctrl_row.addStretch()
        ctrl_row.addWidget(self.save_fasta_button)
        ctrl_row.addWidget(self.run_button)
        ctrl_row.addWidget(self.cancel_button)
        form.addLayout(ctrl_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.hide()
        form.addWidget(self.progress_bar)

        self.status_label = QLabel("Ready")
        self.status_label.setProperty("class", "muted")
        form.addWidget(self.status_label)

        input_scroll.setWidget(input_widget)
        splitter.addWidget(input_scroll)

        # ── Bottom: results tabs ─────────────────────────────────
        self.results_tabs = QTabWidget()
        self.results_tabs.hide()

        # Tab 1: Overview
        overview_tab = QWidget()
        ov = QVBoxLayout(overview_tab)
        ov.setContentsMargins(12, 12, 12, 12)
        ov.setSpacing(10)

        ov.addWidget(QLabel("Summary Statistics:"))
        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        ov.addWidget(self.summary_text, 1)

        chart_hdr = QHBoxLayout()
        chart_hdr.addWidget(QLabel("Cluster Distribution:"))
        chart_hdr.addStretch()
        self.maximize_chart_button = QPushButton("Maximize Chart")
        self.maximize_chart_button.setProperty("class", "secondary")
        set_button_icon(self.maximize_chart_button, "maximize-2", 14)
        self.maximize_chart_button.clicked.connect(self._maximize_chart)
        self.maximize_chart_button.setEnabled(False)
        chart_hdr.addWidget(self.maximize_chart_button)
        ov.addLayout(chart_hdr)

        self.chart_label = QLabel()
        self.chart_label.setAlignment(Qt.AlignCenter)
        chart_scroll = QScrollArea()
        chart_scroll.setWidget(self.chart_label)
        chart_scroll.setWidgetResizable(True)
        ov.addWidget(chart_scroll, 2)

        self.results_tabs.addTab(overview_tab, feather_icon("bar-chart-2", 16), "Overview")

        # Tab 2: Clusters table
        clusters_tab = QWidget()
        ct = QVBoxLayout(clusters_tab)
        ct.setContentsMargins(12, 12, 12, 12)
        self.clusters_table = QTableWidget()
        self.clusters_table.setColumnCount(4)
        self.clusters_table.setHorizontalHeaderLabels(
            ["Cluster ID", "Representative", "Size", "Members (preview)"])
        self.clusters_table.horizontalHeader().setStretchLastSection(True)
        self.clusters_table.setAlternatingRowColors(True)
        ct.addWidget(self.clusters_table)
        self.results_tabs.addTab(clusters_tab, feather_icon("grid", 16), "Clusters")

        # Tab 3: Export
        export_tab = QWidget()
        et = QVBoxLayout(export_tab)
        et.setContentsMargins(12, 12, 12, 12)
        et.setSpacing(12)

        et.addWidget(QLabel("Export clustering results in various formats:"))

        export_tsv_btn = QPushButton("Export as TSV (Cluster Assignments)")
        export_tsv_btn.setProperty("class", "success")
        set_button_icon(export_tsv_btn, "download", 14, "#FFFFFF")
        export_tsv_btn.clicked.connect(self.export_tsv)
        et.addWidget(export_tsv_btn)

        export_fasta_btn = QPushButton("Export Representatives as FASTA")
        export_fasta_btn.setProperty("class", "success")
        set_button_icon(export_fasta_btn, "download", 14, "#FFFFFF")
        export_fasta_btn.clicked.connect(self.export_fasta)
        et.addWidget(export_fasta_btn)

        et.addStretch()
        self.results_tabs.addTab(export_tab, feather_icon("download", 16), "Export")

        splitter.addWidget(self.results_tabs)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        settings = QSettings("SenLab", "ProteinGUI")
        if settings.contains("clustering_splitter"):
            splitter.restoreState(settings.value("clustering_splitter"))
        else:
            splitter.setSizes([400, 300])

        self.splitter = splitter
        splitter.splitterMoved.connect(self._save_splitter_state)

        root.addWidget(splitter)

    # ── System checks ─────────────────────────────────────────────

    def check_system_requirements(self):
        t = get_theme()
        runtime = get_tool_runtime()

        status = runtime.get_tool_status("mmseqs")
        ok = status.installed
        if not ok:
            self.warning_label.setText(
                "MMseqs2 is not currently available. Use the Tools tab to install it, "
                "or click Run and the app will prompt to install it."
            )
            self.warning_label.setStyleSheet(
                f"padding:10px; background-color:{t.get('warning_bg')}; "
                f"border:1px solid {t.get('warning')}; border-radius:5px; "
                f"color:{t.get('text_primary')};")
            self.warning_label.show()
            self.run_button.setEnabled(bool(runtime.get_installable_tools(["mmseqs"])))
            return

        self.warning_label.hide()
        self.run_button.setEnabled(bool(self.fasta_path))

    def _ensure_clustering_tools(self):
        runtime = get_tool_runtime()
        missing = runtime.get_missing_tools_for_feature("clustering")
        if not missing:
            return True

        installable = runtime.get_installable_tools(missing)
        if installable:
            reply = QMessageBox.question(
                self,
                "Install Required Tools",
                "Clustering requires MMseqs2.\n\nInstall it now?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return False
            self._pending_tool_action = self.run_clustering
            self.run_button.setEnabled(False)
            self.status_label.setText("Installing required tools...")
            self.tool_install_worker = ToolInstallWorker(installable)
            self.tool_install_worker.progress.connect(
                lambda current, total, status: self.status_label.setText(status)
            )
            self.tool_install_worker.finished.connect(self._on_tool_install_finished)
            self.tool_install_worker.error.connect(self._on_tool_install_error)
            self.tool_install_worker.start()
            return False

        QMessageBox.warning(
            self,
            "Tool Missing",
            "MMseqs2 is not available on this system and cannot be installed automatically here.",
        )
        return False

    def _on_tool_install_finished(self, _result):
        self.tool_install_worker = None
        self.run_button.setEnabled(True)
        self.check_system_requirements()
        self.status_label.setText("Required tools installed.")
        pending = self._pending_tool_action
        self._pending_tool_action = None
        if pending is not None:
            pending()

    def _on_tool_install_error(self, error_msg):
        self.tool_install_worker = None
        self.run_button.setEnabled(True)
        self._pending_tool_action = None
        self.status_label.setText("Tool installation failed.")
        QMessageBox.critical(self, "Tool Install Error", error_msg)

    # ── File selection ────────────────────────────────────────────

    def browse_fasta_file(self):
        fp, _ = QFileDialog.getOpenFileName(
            self, "Select FASTA File", "",
            "FASTA Files (*.fasta *.fa *.faa);;All Files (*.*)")
        if not fp:
            return
        self.fasta_path = fp
        self.file_path_input.setText(fp)
        t = get_theme()

        is_valid, error_msg, seq_count, file_size_mb = validate_fasta_file(fp)
        if is_valid:
            self.file_info_label.setText(
                f"Valid FASTA file: {seq_count:,} sequences, {file_size_mb:.1f} MB")
            self.file_info_label.setStyleSheet(f"color:{t.get('success')}; font-weight:600;")
        else:
            self.file_info_label.setText(error_msg)
            self.file_info_label.setStyleSheet(f"color:{t.get('error')}; font-weight:600;")
            self.fasta_path = None

    # ── Parameter handling ────────────────────────────────────────

    def on_mode_changed(self):
        mode = self.mode_combo.currentData()
        is_linclust = mode == "linclust"
        self.kmer_spin.setEnabled(is_linclust)
        self.kmer_label_widget.setEnabled(is_linclust)
        self.validate_parameters()

    def validate_parameters(self):
        mode = self.mode_combo.currentData()
        min_seq_id = self.identity_spin.value()
        t = get_theme()

        if mode == "linclust" and min_seq_id < 0.5:
            self.param_warning_label.setText(
                "Linclust requires minimum sequence identity >= 0.5 (50%). "
                "Please increase the identity threshold or use regular clustering.")
            self.param_warning_label.setStyleSheet(
                f"padding:8px; background-color:{t.get('error_bg')}; "
                f"border:1px solid {t.get('error')}; border-radius:5px; "
                f"color:{t.get('text_primary')};")
            self.param_warning_label.show()
            self.run_button.setEnabled(False)
            return False
        else:
            self.param_warning_label.hide()
            self.run_button.setEnabled(bool(self.fasta_path))
            return True

    def toggle_advanced_options(self):
        self.advanced_widget.setVisible(self.advanced_checkbox.isChecked())

    # ── Run clustering ────────────────────────────────────────────

    def run_clustering(self):
        if not self._ensure_clustering_tools():
            return
        if not self.fasta_path:
            QMessageBox.warning(self, "No File", "Please select a FASTA file first.")
            return
        if not self.validate_parameters():
            return

        mode = self.mode_combo.currentData()
        min_seq_id = self.identity_spin.value()
        coverage = self.coverage_spin.value()
        cov_mode = self.covmode_combo.currentData()
        evalue = self.evalue_spin.value()
        sensitivity = self.sens_spin.value() if not self.sens_auto_checkbox.isChecked() else None
        kmer_per_seq = int(self.kmer_spin.value()) if mode == "linclust" else None
        single_step = (mode == "cluster_single")
        actual_mode = "linclust" if mode == "linclust" else "cluster"

        self.run_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.results_tabs.hide()

        self.search_start_time = time.time()
        self.clustering_worker = ClusteringWorker(
            self.fasta_path, actual_mode, min_seq_id, coverage, cov_mode,
            evalue, sensitivity, kmer_per_seq, single_step)
        self.clustering_worker.progress.connect(self.on_progress)
        self.clustering_worker.finished.connect(self.on_clustering_finished)
        self.clustering_worker.error.connect(self.on_clustering_error)
        self.clustering_worker.start()

    def cancel_clustering(self):
        if self.clustering_worker:
            self.clustering_worker.cancel()
            self.clustering_worker.terminate()
            self.clustering_worker.wait()
        self.status_label.setText("Clustering cancelled")
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress_bar.hide()

    def on_progress(self, percent, message):
        self.progress_bar.setValue(percent)
        self.status_label.setText(message)

    def on_clustering_finished(self, stats, rep_fasta_path, tsv_path):
        elapsed = time.time() - self.search_start_time if self.search_start_time else 0
        self.clustering_results = stats
        self.rep_fasta_path = rep_fasta_path
        self.tsv_path = tsv_path

        self.display_results(stats, elapsed)

        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress_bar.hide()
        self.status_label.setText(f"Clustering complete! ({elapsed:.1f}s)")
        self.results_tabs.show()

    def on_clustering_error(self, error_msg):
        QMessageBox.critical(self, "Clustering Error", f"An error occurred:\n\n{error_msg}")
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress_bar.hide()
        self.status_label.setText("Error occurred")

    def display_results(self, stats, search_time):
        summary = create_text_summary(stats)
        summary += f"\n\nClustering Time: {search_time:.2f} seconds"
        self.summary_text.setPlainText(summary)

        import tempfile
        self.chart_path = os.path.join(tempfile.gettempdir(), 'clustering_chart.png')
        success, result = create_distribution_chart(stats, self.chart_path)

        if success:
            pixmap = QPixmap(self.chart_path)
            self.chart_label.setPixmap(
                pixmap.scaled(1000, 600, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.maximize_chart_button.setEnabled(True)
        else:
            self.chart_label.setText(f"Chart generation failed: {result}")
            self.maximize_chart_button.setEnabled(False)

        table_data = get_cluster_table_data(stats, max_rows=1000)
        self.clusters_table.setRowCount(len(table_data))
        for row, (cluster_id, rep_id, size, members) in enumerate(table_data):
            self.clusters_table.setItem(row, 0, QTableWidgetItem(str(cluster_id)))
            self.clusters_table.setItem(row, 1, QTableWidgetItem(rep_id))
            self.clusters_table.setItem(row, 2, QTableWidgetItem(str(size)))
            self.clusters_table.setItem(row, 3, QTableWidgetItem(members))
        self.clusters_table.resizeColumnsToContents()

    # ── Export ────────────────────────────────────────────────────

    def export_tsv(self):
        if not self.clustering_results:
            QMessageBox.warning(self, "No Results", "No clustering results to export.")
            return
        fp, _ = QFileDialog.getSaveFileName(self, "Export Clustering TSV",
            "clustering_results.tsv", "TSV Files (*.tsv);;All Files (*.*)")
        if fp:
            try:
                export_clustering_tsv(self.clustering_results, fp)
                QMessageBox.information(self, "Export Successful", f"Results exported to:\n{fp}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to export:\n{e}")

    def export_fasta(self):
        if not self.rep_fasta_path or not os.path.exists(self.rep_fasta_path):
            QMessageBox.warning(self, "No Results", "No representative sequences available.")
            return
        fp, _ = QFileDialog.getSaveFileName(self, "Export Representatives FASTA",
            "cluster_representatives.fasta", "FASTA Files (*.fasta *.fa);;All Files (*.*)")
        if fp:
            try:
                shutil.copy2(self.rep_fasta_path, fp)
                QMessageBox.information(self, "Export Successful", f"Representatives exported to:\n{fp}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to export:\n{e}")

    # ── Helpers ───────────────────────────────────────────────────

    def _save_splitter_state(self):
        settings = QSettings("SenLab", "ProteinGUI")
        settings.setValue("clustering_splitter", self.splitter.saveState())

    def _maximize_chart(self):
        if not self.chart_path or not os.path.exists(self.chart_path):
            QMessageBox.warning(self, "No Chart Available", "No chart is currently available.")
            return
        pixmap = QPixmap(self.chart_path)
        if pixmap.isNull():
            QMessageBox.warning(self, "Chart Load Error", "Failed to load the chart image.")
            return
        dialog = ChartMaximizeDialog(pixmap, "Cluster Distribution Chart", self)
        dialog.exec_()

    def load_fasta_from_search(self, fasta_path: str, clustering_params: dict):
        if not os.path.exists(fasta_path):
            QMessageBox.warning(self, "File Not Found",
                f"The temporary FASTA file was not found:\n{fasta_path}")
            return

        self.fasta_path = fasta_path
        self.file_path_input.setText(fasta_path)
        self.is_temp_fasta = True
        self.loaded_from_search = True

        if 'min_seq_id' in clustering_params:
            self.identity_spin.setValue(clustering_params['min_seq_id'])
        if 'coverage' in clustering_params:
            self.coverage_spin.setValue(clustering_params['coverage'])
        if 'sensitivity' in clustering_params and clustering_params['sensitivity'] is not None:
            self.sens_spin.setValue(clustering_params['sensitivity'])

        self.save_fasta_button.setVisible(True)
        QMessageBox.information(self, "FASTA Loaded from Search",
            "The selected sequences have been loaded for clustering.\n\n"
            "This is a temporary file that will be deleted when you close the application.\n"
            "Click 'Save FASTA Permanently' to save a copy.\n"
            "Clustering parameters have been pre-filled.\n\n"
            "You can adjust parameters and click 'Run Clustering' when ready.")

    def _save_fasta_permanently(self):
        if not self.fasta_path or not os.path.exists(self.fasta_path):
            QMessageBox.warning(self, "No FASTA Loaded",
                "No temporary FASTA file is currently loaded.")
            return
        fp, _ = QFileDialog.getSaveFileName(self, "Save FASTA File",
            "selected_sequences.fasta", "FASTA Files (*.fasta *.fa);;All Files (*.*)")
        if fp:
            try:
                shutil.copy2(self.fasta_path, fp)
                QMessageBox.information(self, "Save Successful",
                    f"FASTA file saved to:\n{fp}\n\nYou can now use this file for other analyses.")
                self.fasta_path = fp
                self.file_path_input.setText(fp)
                self.is_temp_fasta = False
                self.save_fasta_button.setVisible(False)
            except Exception as e:
                QMessageBox.critical(self, "Save Error", f"Failed to save FASTA file:\n\n{e}")
