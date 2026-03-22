"""
Motif Search Page - Glycosylation motif finding with visualization.

This page provides:
- FASTA file input (upload)
- Configurable motif pattern input
- Motif search with progress reporting
- Matplotlib visualization of results by phylogeny category
- Export functionality (CSV)
"""

import os
from typing import List
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QLineEdit, QGroupBox, QTextEdit, QProgressBar,
    QMessageBox, QTabWidget, QFrame,
    QSpinBox, QFormLayout, QScrollArea, QSplitter, QTableWidget,
    QTableWidgetItem, QHeaderView, QSizePolicy
)
from PyQt5.QtCore import pyqtSignal, Qt, QSettings

from ui.theme import get_theme
from ui.icons import feather_icon, set_button_icon

try:
    import matplotlib
    matplotlib.use('Qt5Agg')
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

from core.motif_worker import MotifSearchWorker


class MotifInputWidget(QWidget):
    """Widget for configuring motif pattern with dynamic position inputs."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.position_inputs: List[QLineEdit] = []
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        length_layout = QHBoxLayout()
        length_layout.addWidget(QLabel("Motif Length:"))
        self.length_spin = QSpinBox()
        self.length_spin.setRange(1, 20)
        self.length_spin.setValue(3)
        self.length_spin.valueChanged.connect(self._update_position_inputs)
        length_layout.addWidget(self.length_spin)
        length_layout.addStretch()

        self.positions_widget = QWidget()
        self.positions_layout = QFormLayout(self.positions_widget)
        self.positions_layout.setContentsMargins(0, 10, 0, 10)

        t = get_theme()
        help_text = QLabel(
            "Enter residue(s) for each position:\n"
            "  Single residue: N (matches N)\n"
            "  Multiple residues: ST (matches S or T)\n"
            "  Exclude: ~P (matches anything except P)\n"
            "  Exclude multiple: ~NP (matches anything except N or P)"
        )
        help_text.setWordWrap(True)
        help_text.setProperty("class", "muted")

        preset_layout = QHBoxLayout()
        preset_label = QLabel("Quick preset:")
        self.nglyc_preset_btn = QPushButton("N-X-S/T (N-glycosylation)")
        self.nglyc_preset_btn.setProperty("class", "secondary")
        set_button_icon(self.nglyc_preset_btn, "zap", 14)
        self.nglyc_preset_btn.clicked.connect(self._apply_nglyc_preset)
        preset_layout.addWidget(preset_label)
        preset_layout.addWidget(self.nglyc_preset_btn)
        preset_layout.addStretch()

        layout.addLayout(length_layout)
        layout.addWidget(self.positions_widget)
        layout.addWidget(help_text)
        layout.addLayout(preset_layout)

        self._update_position_inputs()

    def _update_position_inputs(self):
        while self.positions_layout.count():
            item = self.positions_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.position_inputs.clear()

        length = self.length_spin.value()
        for i in range(length):
            line_edit = QLineEdit()
            line_edit.setPlaceholderText(f"e.g., N, ST, ~P")
            line_edit.setMaximumWidth(150)
            self.position_inputs.append(line_edit)
            self.positions_layout.addRow(f"Position {i + 1}:", line_edit)

    def _apply_nglyc_preset(self):
        self.length_spin.setValue(3)
        self._update_position_inputs()
        if len(self.position_inputs) >= 3:
            self.position_inputs[0].setText("N")
            self.position_inputs[1].setText("~P")
            self.position_inputs[2].setText("ST")

    def get_motif(self) -> List[str]:
        return [inp.text().strip().upper() for inp in self.position_inputs]

    def validate(self) -> tuple:
        motif = self.get_motif()
        for i, pattern in enumerate(motif):
            if not pattern:
                return False, f"Position {i + 1} is empty. Please enter a residue pattern."

            valid_chars = set("ACDEFGHIKLMNPQRSTVWY~")
            invalid = set(pattern) - valid_chars
            if invalid:
                return False, f"Position {i + 1} contains invalid characters: {invalid}"

            if '~' in pattern and not pattern.startswith('~'):
                return False, f"Position {i + 1}: '~' must be at the start (e.g., ~P)"

        return True, ""


class MatplotlibCanvas(FigureCanvas if MATPLOTLIB_AVAILABLE else QWidget):
    """Matplotlib canvas widget for embedding plots in PyQt5."""

    def __init__(self, parent=None):
        if MATPLOTLIB_AVAILABLE:
            self.figure = Figure(figsize=(12, 8), dpi=100)
            t = get_theme()
            bg = t.get("bg_primary")
            self.figure.set_facecolor(bg)
            super().__init__(self.figure)
        else:
            super().__init__(parent)
            layout = QVBoxLayout(self)
            label = QLabel("Matplotlib is not installed.\nPlease install it: pip install matplotlib")
            label.setAlignment(Qt.AlignCenter)
            layout.addWidget(label)

        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def plot_results(self, categories: dict):
        if not MATPLOTLIB_AVAILABLE:
            return

        self.figure.clear()

        t = get_theme()
        bg = t.get("bg_primary")
        text_color = t.get("text_primary")
        muted_color = t.get("text_muted")

        self.figure.set_facecolor(bg)

        colors = {
            'Actinopterygii': 'green',
            'Mammalia': 'blue',
            'Aves': 'red',
            'Amphibia': 'cyan',
            'Other': 'magenta'
        }

        axes = []
        for i, (name, color) in enumerate(colors.items()):
            ax = self.figure.add_subplot(2, 3, i + 1)
            ax.set_facecolor(bg)
            axes.append((ax, name, color))

        for ax, name, color in axes:
            records = categories.get(name, [])

            ax.set_title(name, fontsize=10, fontweight='bold', pad=8, color=text_color)
            ax.set_xlabel("Motif Location", fontsize=8, labelpad=5, color=muted_color)
            ax.set_ylabel("Sequence Index", fontsize=8, labelpad=5, color=muted_color)
            ax.tick_params(axis='both', which='major', labelsize=7, colors=muted_color)

            for spine in ax.spines.values():
                spine.set_color(t.get("border"))

            if not records:
                ax.text(0.5, 0.5, "No sequences", ha='center', va='center',
                        transform=ax.transAxes, fontsize=9, color=muted_color)
                continue

            has_motifs = any(len(r.indices) > 0 for r in records)

            if not has_motifs:
                ax.text(0.5, 0.5, "No motifs found", ha='center', va='center',
                        transform=ax.transAxes, fontsize=9, color=muted_color)
                continue

            for seq_idx, record in enumerate(records):
                for motif_pos in record.indices:
                    ax.scatter(motif_pos, seq_idx + 1, c=color, s=15,
                               edgecolors=color, alpha=0.7)

        self.figure.tight_layout(pad=2.0, h_pad=3.0, w_pad=2.0)
        self.draw()

    def clear_plot(self):
        if MATPLOTLIB_AVAILABLE:
            self.figure.clear()
            self.draw()


class MotifSearchPage(QWidget):
    """Glycosylation Motif Search page."""

    back_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.search_worker = None
        self.current_fasta_path = None
        self.results = None
        self._init_ui()

    def _init_ui(self):
        t = get_theme()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Vertical)

        # ── Top: input controls in a scroll area ─────────────────
        input_scroll = QScrollArea()
        input_scroll.setWidgetResizable(True)
        input_scroll.setFrameShape(QFrame.NoFrame)

        input_widget = QWidget()
        form = QVBoxLayout(input_widget)
        form.setContentsMargins(28, 24, 28, 16)
        form.setSpacing(16)

        title = QLabel("Glycosylation Motif Search")
        title.setProperty("class", "title")
        form.addWidget(title)

        # Matplotlib warning
        self.matplotlib_warning = QLabel()
        self.matplotlib_warning.setWordWrap(True)
        if not MATPLOTLIB_AVAILABLE:
            self.matplotlib_warning.setText(
                "Matplotlib is not installed. Visualization is disabled.\n"
                "Install it with: pip install matplotlib"
            )
        else:
            self.matplotlib_warning.hide()
        form.addWidget(self.matplotlib_warning)

        # ── Input section ────────────────────────────────────────
        input_group = QGroupBox("Input FASTA File")
        ig_layout = QVBoxLayout()

        upload_row = QHBoxLayout()
        self.file_path_input = QLineEdit()
        self.file_path_input.setPlaceholderText("No file selected...")
        self.file_path_input.setReadOnly(True)

        browse_btn = QPushButton("Browse")
        set_button_icon(browse_btn, "folder", 14, "#FFFFFF")
        browse_btn.clicked.connect(self.browse_fasta_file)

        upload_row.addWidget(self.file_path_input)
        upload_row.addWidget(browse_btn)
        ig_layout.addLayout(upload_row)

        self.file_info_label = QLabel()
        self.file_info_label.setProperty("class", "muted")
        ig_layout.addWidget(self.file_info_label)

        input_group.setLayout(ig_layout)
        form.addWidget(input_group)

        # ── Motif configuration ──────────────────────────────────
        motif_group = QGroupBox("Configure Motif Pattern")
        ml = QVBoxLayout()
        self.motif_widget = MotifInputWidget()
        ml.addWidget(self.motif_widget)
        motif_group.setLayout(ml)
        form.addWidget(motif_group)

        # ── Control buttons ──────────────────────────────────────
        ctrl_row = QHBoxLayout()

        self.run_button = QPushButton("Run Motif Search")
        self.run_button.setProperty("class", "success")
        set_button_icon(self.run_button, "search", 16, "#FFFFFF")
        self.run_button.setMinimumHeight(40)
        self.run_button.clicked.connect(self.run_search)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setProperty("class", "danger")
        set_button_icon(self.cancel_button, "x", 14, "#FFFFFF")
        self.cancel_button.setMinimumHeight(40)
        self.cancel_button.clicked.connect(self.cancel_search)
        self.cancel_button.setEnabled(False)

        ctrl_row.addStretch()
        ctrl_row.addWidget(self.run_button)
        ctrl_row.addWidget(self.cancel_button)
        form.addLayout(ctrl_row)

        # Progress
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

        # Tab 1: Plots
        plots_tab = QWidget()
        pl = QVBoxLayout(plots_tab)
        pl.setContentsMargins(0, 0, 0, 0)
        self.canvas = MatplotlibCanvas()
        pl.addWidget(self.canvas)
        self.results_tabs.addTab(plots_tab, feather_icon("bar-chart-2", 16), "Plots")

        # Tab 2: Summary
        summary_tab = QWidget()
        sl = QVBoxLayout(summary_tab)
        sl.setContentsMargins(12, 12, 12, 12)
        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        self.summary_text.setProperty("class", "mono")
        self.summary_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        sl.addWidget(self.summary_text)
        self.results_tabs.addTab(summary_tab, feather_icon("file-text", 16), "Summary")

        # Tab 3: Results Table
        table_tab = QWidget()
        tl = QVBoxLayout(table_tab)
        tl.setContentsMargins(12, 12, 12, 12)
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(4)
        self.results_table.setHorizontalHeaderLabels(["ID", "Species", "Category", "Motif Positions"])
        self.results_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        tl.addWidget(self.results_table)
        self.results_tabs.addTab(table_tab, feather_icon("list", 16), "Results Table")

        # Tab 4: Export
        export_tab = QWidget()
        el = QVBoxLayout(export_tab)
        el.setContentsMargins(12, 12, 12, 12)
        el.setSpacing(12)

        el.addWidget(QLabel("Export the search results:"))

        export_csv_btn = QPushButton("Export as CSV")
        export_csv_btn.setProperty("class", "success")
        set_button_icon(export_csv_btn, "download", 14, "#FFFFFF")
        export_csv_btn.clicked.connect(self.export_csv)
        el.addWidget(export_csv_btn)

        export_summary_btn = QPushButton("Export Summary")
        export_summary_btn.setProperty("class", "secondary")
        set_button_icon(export_summary_btn, "download", 14)
        export_summary_btn.clicked.connect(self.export_summary)
        el.addWidget(export_summary_btn)

        el.addStretch()
        self.results_tabs.addTab(export_tab, feather_icon("download", 16), "Export")

        splitter.addWidget(self.results_tabs)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        settings = QSettings("SenLab", "ProteinGUI")
        if settings.contains("motif_splitter"):
            splitter.restoreState(settings.value("motif_splitter"))
        else:
            splitter.setSizes([400, 400])

        self.splitter = splitter
        splitter.splitterMoved.connect(self._save_splitter_state)

        root.addWidget(splitter)

    def _update_file_info(self, file_path: str):
        t = get_theme()
        try:
            if os.path.exists(file_path):
                seq_count = 0
                with open(file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.startswith('>'):
                            seq_count += 1

                self.file_info_label.setText(f"{seq_count} sequences found in file")
                self.file_info_label.setStyleSheet(f"color: {t.get('success')}; font-style: italic;")
                self.current_fasta_path = file_path
            else:
                self.file_info_label.setText("File not found")
                self.file_info_label.setStyleSheet(f"color: {t.get('error')}; font-style: italic;")
                self.current_fasta_path = None
        except Exception as e:
            self.file_info_label.setText(f"Error reading file: {e}")
            self.file_info_label.setStyleSheet(f"color: {t.get('error')}; font-style: italic;")
            self.current_fasta_path = None

    def browse_fasta_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select FASTA File", "",
            "FASTA Files (*.fasta *.fa *.faa);;All Files (*.*)"
        )
        if file_path:
            self.file_path_input.setText(file_path)
            self._update_file_info(file_path)

    # ── Run search ───────────────────────────────────────────────
    def run_search(self):
        fasta_path = self.file_path_input.text()

        if not fasta_path or not os.path.exists(fasta_path):
            QMessageBox.warning(self, "No File", "Please select a valid FASTA file.")
            return

        is_valid, error_msg = self.motif_widget.validate()
        if not is_valid:
            QMessageBox.warning(self, "Invalid Motif", error_msg)
            return

        motif = self.motif_widget.get_motif()

        self.run_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.results_tabs.hide()

        if MATPLOTLIB_AVAILABLE:
            self.canvas.clear_plot()
        self.summary_text.clear()
        self.results_table.setRowCount(0)

        self.search_worker = MotifSearchWorker(fasta_path, motif)
        self.search_worker.progress.connect(self.on_progress)
        self.search_worker.finished.connect(self.on_search_finished)
        self.search_worker.error.connect(self.on_search_error)
        self.search_worker.start()

    def cancel_search(self):
        if self.search_worker:
            self.search_worker.cancel()
            self.search_worker.terminate()
            self.search_worker.wait()

        self.status_label.setText("Search cancelled")
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress_bar.hide()

    def on_progress(self, percent: int, message: str):
        self.progress_bar.setValue(percent)
        self.status_label.setText(message)

    def on_search_finished(self, results: dict):
        self.results = results

        if MATPLOTLIB_AVAILABLE:
            self.canvas.plot_results(results['categories'])

        motif_str = ' - '.join(results['motif'])
        summary_lines = [
            "MOTIF SEARCH RESULTS",
            "=" * 50,
            f"  Motif Pattern:      {motif_str}",
            f"  Total Sequences:    {results['total_sequences']}",
            f"  Total Motifs Found: {results['total_motifs']}",
            "",
            "CATEGORY BREAKDOWN",
            "-" * 50,
        ]
        for cat, stats in results['category_stats'].items():
            summary_lines.append(
                f"  {cat:<20} {stats['count']:>5} sequences, {stats['motifs']:>5} motifs"
            )
        summary_lines.append("=" * 50)

        self.summary_text.setPlainText("\n".join(summary_lines))

        self._populate_results_table(results)

        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress_bar.hide()
        self.status_label.setText(
            f"Complete! Found {results['total_motifs']} motifs "
            f"in {results['total_sequences']} sequences."
        )
        self.results_tabs.show()

    def _populate_results_table(self, results: dict):
        rows = []
        for cat_name, records in results['categories'].items():
            for record in records:
                if record.indices:
                    rows.append({
                        'id': record.id,
                        'species': record.species,
                        'category': cat_name,
                        'positions': ', '.join(map(str, record.indices))
                    })

        self.results_table.setRowCount(len(rows))

        for i, row in enumerate(rows):
            self.results_table.setItem(i, 0, QTableWidgetItem(row['id']))
            self.results_table.setItem(i, 1, QTableWidgetItem(row['species']))
            self.results_table.setItem(i, 2, QTableWidgetItem(row['category']))
            self.results_table.setItem(i, 3, QTableWidgetItem(row['positions']))

    def on_search_error(self, error_msg: str):
        QMessageBox.critical(self, "Search Error", f"An error occurred:\n\n{error_msg}")
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress_bar.hide()
        self.status_label.setText("Error occurred")

    # ── Export ───────────────────────────────────────────────────
    def export_csv(self):
        if not self.results:
            QMessageBox.warning(self, "No Results", "No results to export. Run a search first.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Results as CSV", "motif_results.csv",
            "CSV Files (*.csv);;All Files (*.*)"
        )

        if not file_path:
            return

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write("ID,Species,Category,Motif_Positions\n")
                for cat_name, records in self.results['categories'].items():
                    for record in records:
                        positions = ';'.join(map(str, record.indices)) if record.indices else ''
                        species = record.species.replace('"', '""')
                        f.write(f'"{record.id}","{species}","{cat_name}","{positions}"\n')

            QMessageBox.information(self, "Export Successful", f"Results exported to:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export:\n{str(e)}")

    def export_summary(self):
        if not self.results:
            QMessageBox.warning(self, "No Results", "No results to export. Run a search first.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Summary", "motif_summary.txt",
            "Text Files (*.txt);;All Files (*.*)"
        )

        if not file_path:
            return

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(self.summary_text.toPlainText())
            QMessageBox.information(self, "Export Successful", f"Summary exported to:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export:\n{str(e)}")

    def _save_splitter_state(self):
        settings = QSettings("SenLab", "ProteinGUI")
        settings.setValue("motif_splitter", self.splitter.saveState())
