"""
Motif Search Page - Glycosylation motif finding with visualization.

This page provides:
- FASTA file input (bundled sample or custom upload)
- Configurable motif pattern input
- Motif search with progress reporting
- Matplotlib visualization of results by phylogeny category
- Export functionality (CSV)
"""

import os
from typing import List, Optional
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QLineEdit, QGroupBox, QTextEdit, QProgressBar,
    QMessageBox, QTabWidget, QRadioButton, QButtonGroup, QFrame,
    QSpinBox, QFormLayout, QScrollArea, QSplitter, QTableWidget,
    QTableWidgetItem, QHeaderView, QSizePolicy
)
from PyQt5.QtCore import pyqtSignal, Qt, QSettings
from PyQt5.QtGui import QFont

# Check matplotlib availability
try:
    import matplotlib
    matplotlib.use('Qt5Agg')
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

from core.motif_worker import MotifSearchWorker


def get_bundled_fasta_path() -> Optional[str]:
    """Get the path to the bundled sample FASTA file."""
    # Try multiple possible locations
    possible_paths = [
        os.path.join(os.path.dirname(os.path.dirname(__file__)), 
                     'resources', 'sample_fasta', 'gamma_phylogeny_sort_3.fasta'),
        os.path.join(os.path.dirname(os.path.dirname(__file__)), 
                     'gamma_phylogeny_sort_3.fasta'),
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            return path
    
    return None


class MotifInputWidget(QWidget):
    """Widget for configuring motif pattern with dynamic position inputs."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.position_inputs: List[QLineEdit] = []
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Length selector
        length_layout = QHBoxLayout()
        length_label = QLabel("Motif Length:")
        length_label.setMinimumWidth(100)
        
        self.length_spin = QSpinBox()
        self.length_spin.setRange(1, 20)
        self.length_spin.setValue(3)
        self.length_spin.valueChanged.connect(self._update_position_inputs)
        
        length_layout.addWidget(length_label)
        length_layout.addWidget(self.length_spin)
        length_layout.addStretch()
        
        # Positions container
        self.positions_widget = QWidget()
        self.positions_layout = QFormLayout(self.positions_widget)
        self.positions_layout.setContentsMargins(0, 10, 0, 0)
        
        # Help text
        help_text = QLabel(
            "Enter residue(s) for each position:\n"
            "• Single residue: N (matches N)\n"
            "• Multiple residues: ST (matches S or T)\n"
            "• Exclude: ~P (matches anything except P)\n"
            "• Exclude multiple: ~NP (matches anything except N or P)"
        )
        help_text.setStyleSheet("""
            color: #7f8c8d; 
            font-size: 11px; 
            padding: 8px;
            background-color: #f8f9fa;
            border-radius: 4px;
        """)
        help_text.setWordWrap(True)
        
        # Preset button for common N-glycosylation motif
        preset_layout = QHBoxLayout()
        preset_label = QLabel("Quick preset:")
        self.nglyc_preset_btn = QPushButton("N-X-S/T (N-glycosylation)")
        self.nglyc_preset_btn.setStyleSheet("""
            QPushButton {
                background-color: #17a2b8;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #138496;
            }
        """)
        self.nglyc_preset_btn.clicked.connect(self._apply_nglyc_preset)
        
        preset_layout.addWidget(preset_label)
        preset_layout.addWidget(self.nglyc_preset_btn)
        preset_layout.addStretch()
        
        layout.addLayout(length_layout)
        layout.addWidget(self.positions_widget)
        layout.addWidget(help_text)
        layout.addLayout(preset_layout)
        
        # Initialize with default length
        self._update_position_inputs()
    
    def _update_position_inputs(self):
        """Update the position input fields based on motif length."""
        # Clear existing
        while self.positions_layout.count():
            item = self.positions_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        self.position_inputs.clear()
        
        # Create new inputs
        length = self.length_spin.value()
        for i in range(length):
            line_edit = QLineEdit()
            line_edit.setPlaceholderText(f"e.g., N, ST, ~P")
            line_edit.setMaximumWidth(150)
            self.position_inputs.append(line_edit)
            self.positions_layout.addRow(f"Position {i + 1}:", line_edit)
    
    def _apply_nglyc_preset(self):
        """Apply the N-X-S/T (N-glycosylation) motif preset."""
        self.length_spin.setValue(3)
        # Wait for UI update
        self._update_position_inputs()
        
        if len(self.position_inputs) >= 3:
            self.position_inputs[0].setText("N")
            self.position_inputs[1].setText("~P")
            self.position_inputs[2].setText("ST")
    
    def get_motif(self) -> List[str]:
        """Get the current motif pattern."""
        return [inp.text().strip().upper() for inp in self.position_inputs]
    
    def validate(self) -> tuple:
        """
        Validate the motif input.
        
        Returns:
            (is_valid, error_message)
        """
        motif = self.get_motif()
        
        for i, pattern in enumerate(motif):
            if not pattern:
                return False, f"Position {i + 1} is empty. Please enter a residue pattern."
            
            # Check for valid characters (amino acids + ~)
            valid_chars = set("ACDEFGHIKLMNPQRSTVWY~")
            pattern_chars = set(pattern)
            
            invalid = pattern_chars - valid_chars
            if invalid:
                return False, f"Position {i + 1} contains invalid characters: {invalid}"
            
            # Check ~ usage
            if '~' in pattern and not pattern.startswith('~'):
                return False, f"Position {i + 1}: '~' must be at the start (e.g., ~P)"
        
        return True, ""


class MatplotlibCanvas(FigureCanvas if MATPLOTLIB_AVAILABLE else QWidget):
    """Matplotlib canvas widget for embedding plots in PyQt5."""
    
    def __init__(self, parent=None):
        if MATPLOTLIB_AVAILABLE:
            self.figure = Figure(figsize=(12, 8), dpi=100)
            self.figure.set_facecolor('#fafafa')
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
        """
        Plot motif search results by phylogeny category.
        
        Args:
            categories: Dict mapping category name to list of ProteinRecord objects
        """
        if not MATPLOTLIB_AVAILABLE:
            return
        
        self.figure.clear()
        
        # Category colors (matching MATLAB)
        colors = {
            'Actinopterygii': 'green',
            'Mammalia': 'blue',
            'Aves': 'red',
            'Amphibia': 'cyan',
            'Other': 'magenta'
        }
        
        # Create 2x3 grid of subplots with better spacing
        axes = []
        for i, (name, color) in enumerate(colors.items()):
            ax = self.figure.add_subplot(2, 3, i + 1)
            axes.append((ax, name, color))
        
        for ax, name, color in axes:
            records = categories.get(name, [])
            
            ax.set_title(name, fontsize=10, fontweight='bold', pad=8)
            ax.set_xlabel("Motif Location", fontsize=8, labelpad=5)
            ax.set_ylabel("Sequence Index", fontsize=8, labelpad=5)
            
            if not records:
                ax.text(0.5, 0.5, "No sequences", ha='center', va='center',
                       transform=ax.transAxes, fontsize=9, color='gray')
                continue
            
            # Check if any motifs found
            has_motifs = any(len(r.indices) > 0 for r in records)
            
            if not has_motifs:
                ax.text(0.5, 0.5, "No motifs found", ha='center', va='center',
                       transform=ax.transAxes, fontsize=9, color='gray')
                continue
            
            # Plot scatter points
            for seq_idx, record in enumerate(records):
                for motif_pos in record.indices:
                    ax.scatter(motif_pos, seq_idx + 1, c=color, s=15, 
                              edgecolors=color, alpha=0.7)
            
            ax.tick_params(axis='both', which='major', labelsize=7)
        
        # Use constrained_layout for better spacing between subplots
        self.figure.tight_layout(pad=2.0, h_pad=3.0, w_pad=2.0)
        self.draw()
    
    def clear_plot(self):
        """Clear the plot."""
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
        
        self.init_ui()
    
    def init_ui(self):
        """Initialize the UI."""
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Page header
        header_layout = QHBoxLayout()
        
        back_button = QPushButton("← Back to Home")
        back_button.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 8px 15px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #7f8c8d;
            }
        """)
        back_button.clicked.connect(self.back_requested.emit)
        
        page_title = QLabel("Glycosylation Motif Search")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        page_title.setFont(title_font)
        page_title.setStyleSheet("color: #2c3e50;")
        
        header_layout.addWidget(back_button)
        header_layout.addStretch()
        header_layout.addWidget(page_title)
        header_layout.addStretch()
        
        # Matplotlib warning
        self.matplotlib_warning = QLabel()
        self.matplotlib_warning.setWordWrap(True)
        self.matplotlib_warning.setStyleSheet("""
            padding: 10px;
            background-color: #fff3cd;
            border: 1px solid #ffc107;
            border-radius: 5px;
            color: #856404;
        """)
        if not MATPLOTLIB_AVAILABLE:
            self.matplotlib_warning.setText(
                "⚠️ Matplotlib is not installed. Visualization is disabled.\n"
                "Install it with: pip install matplotlib"
            )
        else:
            self.matplotlib_warning.hide()
        
        # Input section
        input_group = QGroupBox("1. Input FASTA File")
        input_layout = QVBoxLayout()
        
        # Input method selection
        self.input_method_group = QButtonGroup()
        
        bundled_path = get_bundled_fasta_path()
        
        self.bundled_radio = QRadioButton("Use bundled sample file")
        self.upload_radio = QRadioButton("Upload custom FASTA file")
        
        if bundled_path:
            self.bundled_radio.setChecked(True)
            self.bundled_radio.setToolTip(f"File: {bundled_path}")
        else:
            self.bundled_radio.setEnabled(False)
            self.bundled_radio.setText("Use bundled sample file (not found)")
            self.upload_radio.setChecked(True)
        
        self.input_method_group.addButton(self.bundled_radio, 1)
        self.input_method_group.addButton(self.upload_radio, 2)
        
        radio_style = """
            QRadioButton {
                font-size: 12px;
                padding: 5px;
            }
        """
        self.bundled_radio.setStyleSheet(radio_style)
        self.upload_radio.setStyleSheet(radio_style)
        
        self.bundled_radio.toggled.connect(self._on_input_method_changed)
        self.upload_radio.toggled.connect(self._on_input_method_changed)
        
        input_layout.addWidget(self.bundled_radio)
        input_layout.addWidget(self.upload_radio)
        
        # Upload widget
        self.upload_widget = QWidget()
        upload_layout = QHBoxLayout()
        upload_layout.setContentsMargins(20, 5, 0, 0)
        
        self.file_path_input = QLineEdit()
        self.file_path_input.setPlaceholderText("No file selected...")
        self.file_path_input.setReadOnly(True)
        
        browse_button = QPushButton("Browse...")
        browse_button.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 8px 15px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        browse_button.clicked.connect(self.browse_fasta_file)
        
        upload_layout.addWidget(self.file_path_input)
        upload_layout.addWidget(browse_button)
        self.upload_widget.setLayout(upload_layout)
        
        if bundled_path:
            self.upload_widget.hide()
        
        input_layout.addWidget(self.upload_widget)
        
        # File info
        self.file_info_label = QLabel()
        self.file_info_label.setStyleSheet("color: #7f8c8d; font-style: italic; padding: 5px;")
        input_layout.addWidget(self.file_info_label)
        
        input_group.setLayout(input_layout)
        
        # Motif configuration section
        motif_group = QGroupBox("2. Configure Motif Pattern")
        motif_layout = QVBoxLayout()
        
        self.motif_widget = MotifInputWidget()
        motif_layout.addWidget(self.motif_widget)
        
        motif_group.setLayout(motif_layout)
        
        # Control buttons
        control_layout = QHBoxLayout()
        
        self.run_button = QPushButton("🔍 Run Motif Search")
        self.run_button.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 12px 30px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #219a52;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
            }
        """)
        self.run_button.clicked.connect(self.run_search)
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 12px 30px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        self.cancel_button.clicked.connect(self.cancel_search)
        self.cancel_button.setEnabled(False)
        
        control_layout.addStretch()
        control_layout.addWidget(self.run_button)
        control_layout.addWidget(self.cancel_button)
        
        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.hide()
        
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #7f8c8d; font-weight: bold; padding: 5px;")
        
        # Results section with tabs
        self.results_tabs = QTabWidget()
        self.results_tabs.hide()
        
        # Tab 1: Plots
        plots_tab = QWidget()
        plots_layout = QVBoxLayout()
        
        self.canvas = MatplotlibCanvas()
        plots_layout.addWidget(self.canvas)
        
        plots_tab.setLayout(plots_layout)
        
        # Tab 2: Summary
        summary_tab = QWidget()
        summary_layout = QVBoxLayout()
        
        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        self.summary_text.setFont(QFont("Consolas", 10))
        
        summary_layout.addWidget(self.summary_text)
        summary_tab.setLayout(summary_layout)
        
        # Tab 3: Results Table
        table_tab = QWidget()
        table_layout = QVBoxLayout()
        
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(4)
        self.results_table.setHorizontalHeaderLabels(["ID", "Species", "Category", "Motif Positions"])
        self.results_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.results_table.setAlternatingRowColors(True)
        
        table_layout.addWidget(self.results_table)
        table_tab.setLayout(table_layout)
        
        # Tab 4: Export
        export_tab = QWidget()
        export_layout = QVBoxLayout()
        
        export_info = QLabel("Export the search results:")
        export_info.setStyleSheet("margin-bottom: 10px;")
        
        export_csv_button = QPushButton("📄 Export as CSV")
        export_csv_button.clicked.connect(self.export_csv)
        export_csv_button.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                padding: 10px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #229954;
            }
        """)
        
        export_summary_button = QPushButton("📊 Export Summary")
        export_summary_button.clicked.connect(self.export_summary)
        export_summary_button.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                padding: 10px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        
        export_layout.addWidget(export_info)
        export_layout.addWidget(export_csv_button)
        export_layout.addWidget(export_summary_button)
        export_layout.addStretch()
        export_tab.setLayout(export_layout)
        
        self.results_tabs.addTab(plots_tab, "📊 Plots")
        self.results_tabs.addTab(summary_tab, "📋 Summary")
        self.results_tabs.addTab(table_tab, "📑 Results Table")
        self.results_tabs.addTab(export_tab, "💾 Export")
        
        # Create splitter
        top_container = QWidget()
        top_layout = QVBoxLayout(top_container)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.addWidget(self.matplotlib_warning)
        top_layout.addWidget(input_group)
        top_layout.addWidget(motif_group)
        top_layout.addLayout(control_layout)
        top_layout.addWidget(self.progress_bar)
        top_layout.addWidget(self.status_label)
        
        bottom_container = QWidget()
        bottom_layout = QVBoxLayout(bottom_container)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.addWidget(self.results_tabs)
        
        self.splitter = QSplitter(Qt.Vertical)
        self.splitter.addWidget(top_container)
        self.splitter.addWidget(bottom_container)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        
        # Restore splitter state
        settings = QSettings("SenLab", "ProteinGUI")
        if settings.contains("motif_splitter"):
            self.splitter.restoreState(settings.value("motif_splitter"))
        else:
            self.splitter.setSizes([400, 400])
        
        self.splitter.splitterMoved.connect(self._save_splitter_state)
        
        # Add to main layout
        layout.addLayout(header_layout)
        layout.addWidget(self.splitter)
        
        self.setLayout(layout)
        
        # Initialize file info if bundled is available
        if bundled_path:
            self._update_file_info(bundled_path)
    
    def _on_input_method_changed(self):
        """Handle input method radio button change."""
        if self.bundled_radio.isChecked():
            self.upload_widget.hide()
            bundled_path = get_bundled_fasta_path()
            if bundled_path:
                self._update_file_info(bundled_path)
        else:
            self.upload_widget.show()
            if self.file_path_input.text():
                self._update_file_info(self.file_path_input.text())
            else:
                self.file_info_label.setText("")
    
    def _update_file_info(self, file_path: str):
        """Update the file info label."""
        try:
            if os.path.exists(file_path):
                # Count sequences
                seq_count = 0
                with open(file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.startswith('>'):
                            seq_count += 1
                
                self.file_info_label.setText(f"✓ {seq_count} sequences found in file")
                self.file_info_label.setStyleSheet("color: #27ae60; font-style: italic; padding: 5px;")
                self.current_fasta_path = file_path
            else:
                self.file_info_label.setText("✗ File not found")
                self.file_info_label.setStyleSheet("color: #e74c3c; font-style: italic; padding: 5px;")
                self.current_fasta_path = None
        except Exception as e:
            self.file_info_label.setText(f"✗ Error reading file: {e}")
            self.file_info_label.setStyleSheet("color: #e74c3c; font-style: italic; padding: 5px;")
            self.current_fasta_path = None
    
    def browse_fasta_file(self):
        """Open file dialog to select FASTA file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select FASTA File",
            "",
            "FASTA Files (*.fasta *.fa *.faa);;All Files (*.*)"
        )
        
        if file_path:
            self.file_path_input.setText(file_path)
            self._update_file_info(file_path)
    
    def run_search(self):
        """Run the motif search."""
        # Determine FASTA path
        if self.bundled_radio.isChecked():
            fasta_path = get_bundled_fasta_path()
        else:
            fasta_path = self.file_path_input.text()
        
        if not fasta_path or not os.path.exists(fasta_path):
            QMessageBox.warning(self, "No File", "Please select a valid FASTA file.")
            return
        
        # Validate motif
        is_valid, error_msg = self.motif_widget.validate()
        if not is_valid:
            QMessageBox.warning(self, "Invalid Motif", error_msg)
            return
        
        motif = self.motif_widget.get_motif()
        
        # Disable controls
        self.run_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.results_tabs.hide()
        
        # Clear previous results
        if MATPLOTLIB_AVAILABLE:
            self.canvas.clear_plot()
        self.summary_text.clear()
        self.results_table.setRowCount(0)
        
        # Start worker
        self.search_worker = MotifSearchWorker(fasta_path, motif)
        self.search_worker.progress.connect(self.on_progress)
        self.search_worker.finished.connect(self.on_search_finished)
        self.search_worker.error.connect(self.on_search_error)
        self.search_worker.start()
    
    def cancel_search(self):
        """Cancel the running search."""
        if self.search_worker:
            self.search_worker.cancel()
            self.search_worker.terminate()
            self.search_worker.wait()
        
        self.status_label.setText("Search cancelled")
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress_bar.hide()
    
    def on_progress(self, percent: int, message: str):
        """Handle progress updates."""
        self.progress_bar.setValue(percent)
        self.status_label.setText(message)
    
    def on_search_finished(self, results: dict):
        """Handle search completion."""
        self.results = results
        
        # Update plots
        if MATPLOTLIB_AVAILABLE:
            self.canvas.plot_results(results['categories'])
        
        # Update summary
        motif_str = ' - '.join(results['motif'])
        summary = f"""
╔══════════════════════════════════════════════════════════════════╗
║                    MOTIF SEARCH RESULTS                          ║
╠══════════════════════════════════════════════════════════════════╣
║  Motif Pattern: {motif_str:<49}║
║  Total Sequences: {results['total_sequences']:<47}║
║  Total Motifs Found: {results['total_motifs']:<44}║
╠══════════════════════════════════════════════════════════════════╣
║  CATEGORY BREAKDOWN                                              ║
╠══════════════════════════════════════════════════════════════════╣
"""
        for cat, stats in results['category_stats'].items():
            summary += f"║  {cat:<20} {stats['count']:>5} sequences, {stats['motifs']:>5} motifs      ║\n"
        
        summary += "╚══════════════════════════════════════════════════════════════════╝"
        
        self.summary_text.setPlainText(summary)
        
        # Update results table
        self._populate_results_table(results)
        
        # Re-enable controls
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress_bar.hide()
        self.status_label.setText(f"Complete! Found {results['total_motifs']} motifs in {results['total_sequences']} sequences.")
        self.results_tabs.show()
    
    def _populate_results_table(self, results: dict):
        """Populate the results table."""
        # Build rows with category info
        rows = []
        for cat_name, records in results['categories'].items():
            for record in records:
                if record.indices:  # Only show records with matches
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
        """Handle search error."""
        QMessageBox.critical(self, "Search Error", f"An error occurred:\n\n{error_msg}")
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress_bar.hide()
        self.status_label.setText("Error occurred")
    
    def export_csv(self):
        """Export results as CSV."""
        if not self.results:
            QMessageBox.warning(self, "No Results", "No results to export. Run a search first.")
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Results as CSV",
            "motif_results.csv",
            "CSV Files (*.csv);;All Files (*.*)"
        )
        
        if not file_path:
            return
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                # Header
                f.write("ID,Species,Category,Motif_Positions\n")
                
                # Data
                for cat_name, records in self.results['categories'].items():
                    for record in records:
                        positions = ';'.join(map(str, record.indices)) if record.indices else ''
                        # Escape species field for CSV
                        species = record.species.replace('"', '""')
                        f.write(f'"{record.id}","{species}","{cat_name}","{positions}"\n')
            
            QMessageBox.information(self, "Export Successful", f"Results exported to:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export:\n{str(e)}")
    
    def export_summary(self):
        """Export summary text."""
        if not self.results:
            QMessageBox.warning(self, "No Results", "No results to export. Run a search first.")
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Summary",
            "motif_summary.txt",
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
        """Save splitter state."""
        settings = QSettings("SenLab", "ProteinGUI")
        settings.setValue("motif_splitter", self.splitter.saveState())
