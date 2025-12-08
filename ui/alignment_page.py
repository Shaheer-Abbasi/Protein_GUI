"""Sequence Alignment page - Multiple Sequence Alignment using Clustal Omega"""
import os
import shutil
import tempfile
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QFileDialog, QLineEdit, QComboBox, QGroupBox, QTextEdit, 
    QProgressBar, QMessageBox, QTabWidget, QRadioButton, QButtonGroup,
    QFrame, QSpinBox, QCheckBox, QSplitter, QScrollArea
)
from PyQt5.QtCore import pyqtSignal, Qt, QTimer, QSettings
from PyQt5.QtGui import QFont

from core.wsl_utils import is_wsl_available, warmup_wsl
from core.alignment_worker import (
    AlignmentWorker, 
    check_clustalo_installation, 
    SequenceAlignmentPrep
)
from ui.widgets.msa_viewer_widget import MSAViewerWidget, check_webengine_available
from utils.fasta_parser import FastaParser, FastaParseError


class AlignmentPage(QWidget):
    """Sequence Alignment page using Clustal Omega"""
    
    back_requested = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        
        self.alignment_worker = None
        self.input_fasta_path = None
        self.output_alignment_path = None
        self.aligned_content = None
        self.loaded_sequences = []
        self.is_temp_fasta = False
        
        self.init_ui()
        
        # Check system requirements after a delay
        QTimer.singleShot(100, lambda: warmup_wsl())
        QTimer.singleShot(2000, self.check_system_requirements)
    
    def init_ui(self):
        """Initialize the UI"""
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
        
        page_title = QLabel("Sequence Alignment")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        page_title.setFont(title_font)
        page_title.setStyleSheet("color: #2c3e50;")
        
        header_layout.addWidget(back_button)
        header_layout.addStretch()
        header_layout.addWidget(page_title)
        header_layout.addStretch()
        
        # System requirements warning
        self.warning_label = QLabel()
        self.warning_label.setWordWrap(True)
        self.warning_label.setStyleSheet("""
            padding: 10px;
            background-color: #fff3cd;
            border: 1px solid #ffc107;
            border-radius: 5px;
            color: #856404;
        """)
        self.warning_label.hide()
        
        # PyQtWebEngine warning
        self.webengine_warning = QLabel()
        self.webengine_warning.setWordWrap(True)
        self.webengine_warning.setStyleSheet("""
            padding: 10px;
            background-color: #cce5ff;
            border: 1px solid #b8daff;
            border-radius: 5px;
            color: #004085;
        """)
        if not check_webengine_available():
            self.webengine_warning.setText(
                "ℹ️ PyQtWebEngine is not installed. The alignment viewer is disabled.\n"
                "You can still run alignments and export results. To enable the viewer:\n"
                "pip install PyQtWebEngine"
            )
        else:
            self.webengine_warning.hide()
        
        # Input section
        input_group = QGroupBox("1. Input Sequences")
        input_layout = QVBoxLayout()
        
        # Input method selection
        method_layout = QHBoxLayout()
        self.input_method_group = QButtonGroup()
        
        self.upload_radio = QRadioButton("Upload FASTA File")
        self.paste_radio = QRadioButton("Paste Sequences")
        
        self.upload_radio.setChecked(True)
        
        self.input_method_group.addButton(self.upload_radio, 1)
        self.input_method_group.addButton(self.paste_radio, 2)
        
        radio_style = """
            QRadioButton {
                font-size: 12px;
                font-weight: bold;
                padding: 5px;
            }
        """
        self.upload_radio.setStyleSheet(radio_style)
        self.paste_radio.setStyleSheet(radio_style)
        
        self.upload_radio.toggled.connect(self._on_input_method_changed)
        self.paste_radio.toggled.connect(self._on_input_method_changed)
        
        method_layout.addWidget(self.upload_radio)
        method_layout.addWidget(self.paste_radio)
        method_layout.addStretch()
        
        input_layout.addLayout(method_layout)
        
        # Upload widget
        self.upload_widget = QWidget()
        upload_layout = QHBoxLayout()
        upload_layout.setContentsMargins(0, 10, 0, 0)
        
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
        
        # Paste widget
        self.paste_widget = QWidget()
        paste_layout = QVBoxLayout()
        paste_layout.setContentsMargins(0, 10, 0, 0)
        
        paste_label = QLabel("Paste sequences in FASTA format:")
        self.paste_text = QTextEdit()
        self.paste_text.setPlaceholderText(
            ">sequence1\nMKTLLILAVVAAALA...\n"
            ">sequence2\nMKTLLILAVVAAALA...\n"
            ">sequence3\nMKTLLILAVV---LA..."
        )
        self.paste_text.setMaximumHeight(120)
        
        paste_layout.addWidget(paste_label)
        paste_layout.addWidget(self.paste_text)
        self.paste_widget.setLayout(paste_layout)
        self.paste_widget.hide()
        
        input_layout.addWidget(self.upload_widget)
        input_layout.addWidget(self.paste_widget)
        
        # File info label
        self.file_info_label = QLabel()
        self.file_info_label.setStyleSheet("color: #7f8c8d; font-style: italic; padding: 5px;")
        input_layout.addWidget(self.file_info_label)
        
        input_group.setLayout(input_layout)
        
        # Parameters section
        params_group = QGroupBox("2. Alignment Parameters")
        params_layout = QVBoxLayout()
        
        # Output format
        format_layout = QHBoxLayout()
        format_label = QLabel("Output Format:")
        format_label.setMinimumWidth(150)
        self.format_combo = QComboBox()
        self.format_combo.addItem("FASTA (aligned)", "fasta")
        self.format_combo.addItem("Clustal", "clustal")
        self.format_combo.addItem("MSF", "msf")
        self.format_combo.addItem("PHYLIP", "phylip")
        self.format_combo.addItem("Stockholm", "stockholm")
        format_layout.addWidget(format_label)
        format_layout.addWidget(self.format_combo)
        format_layout.addStretch()
        
        # Iterations
        iter_layout = QHBoxLayout()
        iter_label = QLabel("Iterations:")
        iter_label.setMinimumWidth(150)
        self.iter_spin = QSpinBox()
        self.iter_spin.setRange(0, 5)
        self.iter_spin.setValue(0)
        self.iter_spin.setToolTip("Number of combined iterations (0 = auto)")
        iter_layout.addWidget(iter_label)
        iter_layout.addWidget(self.iter_spin)
        iter_layout.addStretch()
        
        # Full iteration
        self.full_iter_checkbox = QCheckBox("Full iterative refinement")
        self.full_iter_checkbox.setToolTip("Use full iterative refinement (slower but more accurate)")
        
        params_layout.addLayout(format_layout)
        params_layout.addLayout(iter_layout)
        params_layout.addWidget(self.full_iter_checkbox)
        params_group.setLayout(params_layout)
        
        # Control buttons
        control_layout = QHBoxLayout()
        
        self.save_fasta_button = QPushButton("💾 Save Input FASTA")
        self.save_fasta_button.setStyleSheet("""
            QPushButton {
                background-color: #16a085;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 12px 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #138d75;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
            }
        """)
        self.save_fasta_button.clicked.connect(self._save_input_fasta)
        self.save_fasta_button.setVisible(False)
        
        self.run_button = QPushButton("Run Alignment")
        self.run_button.setStyleSheet("""
            QPushButton {
                background-color: #1abc9c;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 12px 30px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #16a085;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
            }
        """)
        self.run_button.clicked.connect(self.run_alignment)
        
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
        self.cancel_button.clicked.connect(self.cancel_alignment)
        self.cancel_button.setEnabled(False)
        
        control_layout.addStretch()
        control_layout.addWidget(self.save_fasta_button)
        control_layout.addWidget(self.run_button)
        control_layout.addWidget(self.cancel_button)
        
        # Progress section
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.hide()
        
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #7f8c8d; font-weight: bold; padding: 5px;")
        
        # Results section with tabs
        self.results_tabs = QTabWidget()
        self.results_tabs.hide()
        
        # Tab 1: Alignment Viewer
        viewer_tab = QWidget()
        viewer_layout = QVBoxLayout()
        
        self.msa_viewer = MSAViewerWidget()
        viewer_layout.addWidget(self.msa_viewer)
        
        viewer_tab.setLayout(viewer_layout)
        
        # Tab 2: Raw Alignment
        raw_tab = QWidget()
        raw_layout = QVBoxLayout()
        
        self.raw_alignment_text = QTextEdit()
        self.raw_alignment_text.setReadOnly(True)
        self.raw_alignment_text.setFont(QFont("Courier New", 10))
        self.raw_alignment_text.setStyleSheet("""
            QTextEdit {
                background-color: #2d2d2d;
                color: #f8f8f2;
                border: 1px solid #444;
            }
        """)
        
        raw_layout.addWidget(self.raw_alignment_text)
        raw_tab.setLayout(raw_layout)
        
        # Tab 3: Export
        export_tab = QWidget()
        export_layout = QVBoxLayout()
        
        export_info = QLabel("Export the alignment in various formats:")
        export_info.setStyleSheet("margin-bottom: 10px;")
        
        export_fasta_button = QPushButton("Export as FASTA")
        export_fasta_button.clicked.connect(lambda: self._export_alignment('fasta'))
        export_fasta_button.setStyleSheet("""
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
        
        export_clustal_button = QPushButton("Export as Clustal")
        export_clustal_button.clicked.connect(lambda: self._export_alignment('clustal'))
        export_clustal_button.setStyleSheet("""
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
        
        export_layout.addWidget(export_info)
        export_layout.addWidget(export_fasta_button)
        export_layout.addWidget(export_clustal_button)
        export_layout.addStretch()
        export_tab.setLayout(export_layout)
        
        self.results_tabs.addTab(viewer_tab, "Alignment Viewer")
        self.results_tabs.addTab(raw_tab, "Raw Alignment")
        self.results_tabs.addTab(export_tab, "Export")
        
        # Create splitter for top/bottom sections
        top_container = QWidget()
        top_layout = QVBoxLayout(top_container)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.addWidget(self.warning_label)
        top_layout.addWidget(self.webengine_warning)
        top_layout.addWidget(input_group)
        top_layout.addWidget(params_group)
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
        if settings.contains("alignment_splitter"):
            self.splitter.restoreState(settings.value("alignment_splitter"))
        else:
            self.splitter.setSizes([350, 350])
        
        self.splitter.splitterMoved.connect(self._save_splitter_state)
        
        # Add to main layout
        layout.addLayout(header_layout)
        layout.addWidget(self.splitter)
        
        self.setLayout(layout)
    
    def _on_input_method_changed(self):
        """Handle input method change"""
        if self.upload_radio.isChecked():
            self.upload_widget.show()
            self.paste_widget.hide()
        else:
            self.upload_widget.hide()
            self.paste_widget.show()
    
    def check_system_requirements(self):
        """Check if WSL and Clustal Omega are available"""
        warmup_wsl()
        
        if not is_wsl_available():
            self.warning_label.setText(
                "⚠️ WSL not detected. Clustal Omega requires Windows Subsystem for Linux.\n"
                "Please install WSL to use this feature."
            )
            self.warning_label.show()
            self.run_button.setEnabled(False)
            return
        
        clustalo_installed, version, path = check_clustalo_installation()
        if not clustalo_installed:
            self.warning_label.setText(
                "⚠️ Clustal Omega not found in WSL. Please install it to use alignment.\n"
                "Installation: sudo apt install clustalo"
            )
            self.warning_label.show()
            self.run_button.setEnabled(False)
            return
        
        self.warning_label.hide()
    
    def browse_fasta_file(self):
        """Open file dialog to select FASTA file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select FASTA File",
            "",
            "FASTA Files (*.fasta *.fa *.faa);;All Files (*.*)"
        )
        
        if file_path:
            self.load_fasta_file(file_path)
    
    def load_fasta_file(self, file_path, is_temp=False):
        """Load a FASTA file"""
        if not os.path.exists(file_path):
            QMessageBox.warning(self, "File Not Found", f"File not found: {file_path}")
            return False
        
        # Validate for alignment
        is_valid, message, seq_count = SequenceAlignmentPrep.validate_fasta_for_alignment(file_path)
        
        self.input_fasta_path = file_path
        self.file_path_input.setText(file_path)
        self.is_temp_fasta = is_temp
        
        if is_valid:
            self.file_info_label.setText(f"✓ {message}")
            self.file_info_label.setStyleSheet("color: #27ae60; font-style: italic; padding: 5px;")
            self.run_button.setEnabled(True)
        else:
            self.file_info_label.setText(f"✗ {message}")
            self.file_info_label.setStyleSheet("color: #e74c3c; font-style: italic; padding: 5px;")
            self.run_button.setEnabled(False)
        
        # Show save button if temp file
        self.save_fasta_button.setVisible(is_temp)
        
        return is_valid
    
    def run_alignment(self):
        """Run Clustal Omega alignment"""
        # Handle pasted sequences
        if self.paste_radio.isChecked():
            paste_content = self.paste_text.toPlainText().strip()
            if not paste_content:
                QMessageBox.warning(self, "No Sequences", "Please paste sequences in FASTA format.")
                return
            
            # Save to temp file
            try:
                fd, temp_path = tempfile.mkstemp(suffix='.fasta', prefix='alignment_input_')
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    f.write(paste_content)
                
                self.input_fasta_path = temp_path
                self.is_temp_fasta = True
                
                # Validate
                is_valid, message, seq_count = SequenceAlignmentPrep.validate_fasta_for_alignment(temp_path)
                if not is_valid:
                    QMessageBox.warning(self, "Invalid Sequences", message)
                    os.remove(temp_path)
                    return
                    
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save sequences: {str(e)}")
                return
        
        if not self.input_fasta_path:
            QMessageBox.warning(self, "No File", "Please select a FASTA file first.")
            return
        
        # Get parameters
        output_format = self.format_combo.currentData()
        iterations = self.iter_spin.value()
        full_iter = self.full_iter_checkbox.isChecked()
        
        # Disable controls
        self.run_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.results_tabs.hide()
        
        # Start alignment
        self.alignment_worker = AlignmentWorker(
            self.input_fasta_path,
            output_format=output_format,
            iterations=iterations,
            full_iter=full_iter
        )
        self.alignment_worker.progress.connect(self.on_progress)
        self.alignment_worker.finished.connect(self.on_alignment_finished)
        self.alignment_worker.error.connect(self.on_alignment_error)
        self.alignment_worker.start()
    
    def cancel_alignment(self):
        """Cancel the alignment"""
        if self.alignment_worker:
            self.alignment_worker.cancel()
            self.alignment_worker.terminate()
            self.alignment_worker.wait()
        
        self.status_label.setText("Alignment cancelled")
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress_bar.hide()
    
    def on_progress(self, percent, message):
        """Update progress"""
        self.progress_bar.setValue(percent)
        self.status_label.setText(message)
    
    def on_alignment_finished(self, aligned_content, output_path):
        """Handle alignment completion"""
        self.aligned_content = aligned_content
        self.output_alignment_path = output_path
        
        # Display in viewer
        # Convert to FASTA if needed for viewer
        if self.format_combo.currentData() == 'fasta':
            self.msa_viewer.load_alignment(aligned_content)
        else:
            # For other formats, load the file directly
            self.msa_viewer.load_alignment_file(output_path)
        
        # Display raw alignment
        self.raw_alignment_text.setPlainText(aligned_content)
        
        # Re-enable controls
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress_bar.hide()
        self.status_label.setText("Alignment complete!")
        self.results_tabs.show()
    
    def on_alignment_error(self, error_msg):
        """Handle alignment error"""
        QMessageBox.critical(self, "Alignment Error", f"An error occurred:\n\n{error_msg}")
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress_bar.hide()
        self.status_label.setText("Error occurred")
    
    def _export_alignment(self, format_type):
        """Export alignment in specified format"""
        if not self.aligned_content:
            QMessageBox.warning(self, "No Alignment", "No alignment available to export.")
            return
        
        # If current format matches, use directly
        if self.format_combo.currentData() == format_type:
            content = self.aligned_content
        else:
            # Need to re-run alignment with different format
            QMessageBox.information(
                self, 
                "Format Conversion",
                f"To export in {format_type.upper()} format, please re-run the alignment "
                f"with '{format_type.upper()}' selected as the output format."
            )
            return
        
        ext_map = {
            'fasta': '.fasta',
            'clustal': '.aln',
        }
        ext = ext_map.get(format_type, '.txt')
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            f"Export Alignment as {format_type.upper()}",
            f"alignment{ext}",
            f"{format_type.upper()} Files (*{ext});;All Files (*.*)"
        )
        
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                QMessageBox.information(self, "Export Successful", f"Alignment exported to:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to export:\n{str(e)}")
    
    def _save_input_fasta(self):
        """Save the input FASTA file permanently"""
        if not self.input_fasta_path or not os.path.exists(self.input_fasta_path):
            QMessageBox.warning(self, "No File", "No input FASTA file to save.")
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save FASTA File",
            "sequences.fasta",
            "FASTA Files (*.fasta *.fa);;All Files (*.*)"
        )
        
        if file_path:
            try:
                shutil.copy2(self.input_fasta_path, file_path)
                QMessageBox.information(
                    self,
                    "Save Successful",
                    f"FASTA file saved to:\n{file_path}"
                )
                
                # Update to use the permanent file
                self.input_fasta_path = file_path
                self.file_path_input.setText(file_path)
                self.is_temp_fasta = False
                self.save_fasta_button.setVisible(False)
                
            except Exception as e:
                QMessageBox.critical(self, "Save Error", f"Failed to save:\n{str(e)}")
    
    def _save_splitter_state(self):
        """Save splitter state"""
        settings = QSettings("SenLab", "ProteinGUI")
        settings.setValue("alignment_splitter", self.splitter.saveState())
    
    def load_sequences_from_search(self, fasta_path, source_info=None):
        """
        Load sequences from a search result (BLAST/MMseqs2).
        
        Args:
            fasta_path: Path to FASTA file with sequences
            source_info: Optional dict with source information
        """
        success = self.load_fasta_file(fasta_path, is_temp=True)
        
        if success:
            QMessageBox.information(
                self,
                "Sequences Loaded",
                "Sequences have been loaded for alignment.\n\n"
                "• This is a temporary file.\n"
                "• Click '💾 Save Input FASTA' to save permanently.\n"
                "• Adjust parameters and click 'Run Alignment' when ready."
            )

