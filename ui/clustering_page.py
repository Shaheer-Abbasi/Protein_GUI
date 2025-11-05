import os
import time
import shutil
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
                             QFileDialog, QLineEdit, QComboBox, QSlider, QGroupBox, 
                             QTextEdit, QProgressBar, QMessageBox, QTabWidget, QTableWidget,
                             QTableWidgetItem, QDoubleSpinBox, QCheckBox, QScrollArea)
from PyQt5.QtCore import pyqtSignal, Qt, QTimer
from PyQt5.QtGui import QFont, QPixmap

from core.clustering_worker import ClusteringWorker
from core.clustering_manager import validate_fasta_file, export_clustering_tsv, get_cluster_table_data
from core.clustering_visualizer import create_distribution_chart, create_text_summary, export_chart_html
from core.wsl_utils import is_wsl_available, check_mmseqs_installation, warmup_wsl


class ClusteringPage(QWidget):
    """MMseqs2 Clustering page widget"""
    back_requested = pyqtSignal()  # Signal to go back to home page

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
        self.init_ui()
        
        # Warm up WSL first, then check system requirements after a longer delay
        QTimer.singleShot(100, lambda: warmup_wsl())
        QTimer.singleShot(2000, self.check_system_requirements)  # Increased delay to 2 seconds

    def init_ui(self):
        """Initialize the clustering page UI"""
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

        page_title = QLabel("MMseqs2 Clustering")
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
        
        # File upload section
        file_group = QGroupBox("1. Select FASTA File")
        file_layout = QVBoxLayout()
        
        upload_layout = QHBoxLayout()
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
        
        self.file_info_label = QLabel()
        self.file_info_label.setStyleSheet("color: #7f8c8d; font-style: italic; padding: 5px;")
        
        file_layout.addLayout(upload_layout)
        file_layout.addWidget(self.file_info_label)
        file_group.setLayout(file_layout)
        
        # Parameters section
        params_group = QGroupBox("2. Clustering Parameters")
        params_layout = QVBoxLayout()
        
        # Clustering mode
        mode_layout = QHBoxLayout()
        mode_label = QLabel("Clustering Mode:")
        mode_label.setMinimumWidth(150)
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Cluster (Cascaded - Accurate, slower)", "cluster")
        self.mode_combo.addItem("Cluster (Single-step - Faster)", "cluster_single")
        self.mode_combo.addItem("Linclust (Linear time, ≥50% identity only)", "linclust")
        self.mode_combo.setToolTip("Cluster: Accurate cascaded clustering\nLinclust: Very fast but requires ≥50% sequence identity")
        self.mode_combo.currentIndexChanged.connect(self.on_mode_changed)
        mode_layout.addWidget(mode_label)
        mode_layout.addWidget(self.mode_combo)
        mode_layout.addStretch()
        
        # Min sequence identity
        identity_layout = QHBoxLayout()
        identity_label = QLabel("Min Sequence Identity:")
        identity_label.setMinimumWidth(150)
        self.identity_spin = QDoubleSpinBox()
        self.identity_spin.setRange(0.0, 1.0)
        self.identity_spin.setSingleStep(0.05)
        self.identity_spin.setValue(0.5)
        self.identity_spin.setDecimals(2)
        self.identity_spin.setToolTip("Minimum sequence identity threshold (0.0-1.0). Default: 0.5 (50%)")
        self.identity_spin.valueChanged.connect(self.validate_parameters)
        identity_layout.addWidget(identity_label)
        identity_layout.addWidget(self.identity_spin)
        identity_layout.addStretch()
        
        # Coverage
        coverage_layout = QHBoxLayout()
        coverage_label = QLabel("Coverage:")
        coverage_label.setMinimumWidth(150)
        self.coverage_spin = QDoubleSpinBox()
        self.coverage_spin.setRange(0.0, 1.0)
        self.coverage_spin.setSingleStep(0.05)
        self.coverage_spin.setValue(0.8)
        self.coverage_spin.setDecimals(2)
        self.coverage_spin.setToolTip("Minimum coverage of alignment (0.0-1.0). Default: 0.8 (80%)")
        coverage_layout.addWidget(coverage_label)
        coverage_layout.addWidget(self.coverage_spin)
        coverage_layout.addStretch()
        
        # Coverage mode
        covmode_layout = QHBoxLayout()
        covmode_label = QLabel("Coverage Mode:")
        covmode_label.setMinimumWidth(150)
        self.covmode_combo = QComboBox()
        self.covmode_combo.addItem("Bidirectional (max of query/target)", 0)
        self.covmode_combo.addItem("Target coverage", 1)
        self.covmode_combo.addItem("Query coverage", 2)
        self.covmode_combo.setToolTip("How coverage is calculated:\n0: max(query, target)\n1: target length\n2: query length")
        covmode_layout.addWidget(covmode_label)
        covmode_layout.addWidget(self.covmode_combo)
        covmode_layout.addStretch()
        
        # E-value
        evalue_layout = QHBoxLayout()
        evalue_label = QLabel("E-value Threshold:")
        evalue_label.setMinimumWidth(150)
        self.evalue_spin = QDoubleSpinBox()
        self.evalue_spin.setRange(1e-100, 100)
        self.evalue_spin.setDecimals(6)
        self.evalue_spin.setValue(0.001)
        self.evalue_spin.setToolTip("Maximum E-value threshold. Default: 0.001")
        evalue_layout.addWidget(evalue_label)
        evalue_layout.addWidget(self.evalue_spin)
        evalue_layout.addStretch()
        
        # Advanced options
        self.advanced_checkbox = QCheckBox("Show Advanced Options")
        self.advanced_checkbox.stateChanged.connect(self.toggle_advanced_options)
        
        self.advanced_widget = QWidget()
        advanced_layout = QVBoxLayout()
        
        # Sensitivity
        sens_layout = QHBoxLayout()
        sens_label = QLabel("Sensitivity:")
        sens_label.setMinimumWidth(150)
        self.sens_spin = QDoubleSpinBox()
        self.sens_spin.setRange(1.0, 7.5)
        self.sens_spin.setSingleStep(0.5)
        self.sens_spin.setValue(7.5)
        self.sens_spin.setDecimals(1)
        self.sens_spin.setToolTip("Sensitivity parameter (1.0-7.5). Higher is more sensitive but slower. Leave at default for auto-adjustment.")
        self.sens_auto_checkbox = QCheckBox("Auto (recommended)")
        self.sens_auto_checkbox.setChecked(True)
        self.sens_auto_checkbox.stateChanged.connect(lambda: self.sens_spin.setEnabled(not self.sens_auto_checkbox.isChecked()))
        self.sens_spin.setEnabled(False)
        sens_layout.addWidget(sens_label)
        sens_layout.addWidget(self.sens_spin)
        sens_layout.addWidget(self.sens_auto_checkbox)
        sens_layout.addStretch()
        
        # K-mers per sequence (linclust only)
        kmer_layout = QHBoxLayout()
        kmer_label = QLabel("K-mers per Sequence:")
        kmer_label.setMinimumWidth(150)
        self.kmer_spin = QDoubleSpinBox()
        self.kmer_spin.setRange(10, 100)
        self.kmer_spin.setSingleStep(5)
        self.kmer_spin.setValue(20)
        self.kmer_spin.setDecimals(0)
        self.kmer_spin.setToolTip("Number of k-mers per sequence for linclust. Higher is more sensitive. Default: 20")
        self.kmer_label_widget = kmer_label
        self.kmer_spin.setEnabled(False)
        kmer_layout.addWidget(kmer_label)
        kmer_layout.addWidget(self.kmer_spin)
        kmer_layout.addStretch()
        
        advanced_layout.addLayout(sens_layout)
        advanced_layout.addLayout(kmer_layout)
        self.advanced_widget.setLayout(advanced_layout)
        self.advanced_widget.hide()
        
        # Add all to params layout
        params_layout.addLayout(mode_layout)
        params_layout.addLayout(identity_layout)
        params_layout.addLayout(coverage_layout)
        params_layout.addLayout(covmode_layout)
        params_layout.addLayout(evalue_layout)
        params_layout.addWidget(self.advanced_checkbox)
        params_layout.addWidget(self.advanced_widget)
        params_group.setLayout(params_layout)
        
        # Parameter validation message
        self.param_warning_label = QLabel()
        self.param_warning_label.setWordWrap(True)
        self.param_warning_label.setStyleSheet("""
            padding: 8px;
            background-color: #f8d7da;
            border: 1px solid #f5c6cb;
            border-radius: 5px;
            color: #721c24;
        """)
        self.param_warning_label.hide()
        
        # Control buttons
        control_layout = QHBoxLayout()
        
        self.run_button = QPushButton("Run Clustering")
        self.run_button.setStyleSheet("""
            QPushButton {
                background-color: #8e44ad;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 12px 30px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #7d3c98;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
            }
        """)
        self.run_button.clicked.connect(self.run_clustering)
        
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
        self.cancel_button.clicked.connect(self.cancel_clustering)
        self.cancel_button.setEnabled(False)
        
        control_layout.addWidget(self.run_button)
        control_layout.addWidget(self.cancel_button)
        control_layout.addStretch()
        
        # Progress section
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.hide()
        
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #7f8c8d; font-weight: bold; padding: 5px;")
        
        # Results section
        self.results_tabs = QTabWidget()
        self.results_tabs.hide()
        
        # Tab 1: Overview
        overview_tab = QWidget()
        overview_layout = QVBoxLayout()
        
        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        self.summary_text.setMaximumHeight(200)
        
        self.chart_label = QLabel()
        self.chart_label.setAlignment(Qt.AlignCenter)
        self.chart_label.setStyleSheet("background-color: white; border: 1px solid #bdc3c7; border-radius: 5px;")
        
        chart_scroll = QScrollArea()
        chart_scroll.setWidget(self.chart_label)
        chart_scroll.setWidgetResizable(True)
        
        overview_layout.addWidget(QLabel("Summary Statistics:"))
        overview_layout.addWidget(self.summary_text)
        overview_layout.addWidget(QLabel("Cluster Distribution:"))
        overview_layout.addWidget(chart_scroll)
        overview_tab.setLayout(overview_layout)
        
        # Tab 2: Clusters Table
        clusters_tab = QWidget()
        clusters_layout = QVBoxLayout()
        
        self.clusters_table = QTableWidget()
        self.clusters_table.setColumnCount(4)
        self.clusters_table.setHorizontalHeaderLabels(["Cluster ID", "Representative", "Size", "Members (preview)"])
        self.clusters_table.horizontalHeader().setStretchLastSection(True)
        
        clusters_layout.addWidget(self.clusters_table)
        clusters_tab.setLayout(clusters_layout)
        
        # Tab 3: Export
        export_tab = QWidget()
        export_layout = QVBoxLayout()
        
        export_info = QLabel("Export clustering results in various formats:")
        export_info.setStyleSheet("margin-bottom: 10px;")
        
        export_tsv_button = QPushButton("Export as TSV (Cluster Assignments)")
        export_tsv_button.clicked.connect(self.export_tsv)
        export_tsv_button.setStyleSheet("""
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
        
        export_fasta_button = QPushButton("Export Representatives as FASTA")
        export_fasta_button.clicked.connect(self.export_fasta)
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
        
        export_layout.addWidget(export_info)
        export_layout.addWidget(export_tsv_button)
        export_layout.addWidget(export_fasta_button)
        export_layout.addStretch()
        export_tab.setLayout(export_layout)
        
        self.results_tabs.addTab(overview_tab, "Overview")
        self.results_tabs.addTab(clusters_tab, "Clusters")
        self.results_tabs.addTab(export_tab, "Export")
        
        # Add everything to main layout
        layout.addLayout(header_layout)
        layout.addWidget(self.warning_label)
        layout.addWidget(file_group)
        layout.addWidget(params_group)
        layout.addWidget(self.param_warning_label)
        layout.addLayout(control_layout)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.status_label)
        layout.addWidget(self.results_tabs)
        
        self.setLayout(layout)
    
    def check_system_requirements(self):
        """Check if WSL and MMseqs2 are available"""
        # Warm up WSL again to ensure it's ready
        warmup_wsl()
        
        if not is_wsl_available():
            self.warning_label.setText(
                "⚠️ WSL not detected. MMseqs2 clustering requires Windows Subsystem for Linux.\n"
                "Please install WSL to use this feature."
            )
            self.warning_label.show()
            self.run_button.setEnabled(False)
            return
        
        mmseqs_installed, mmseqs_version, mmseqs_path = check_mmseqs_installation()
        if not mmseqs_installed:
            self.warning_label.setText(
                "⚠️ MMseqs2 not found in WSL. Please install MMseqs2 to use clustering.\n"
                "Installation: wget https://mmseqs.com/latest/mmseqs-linux-avx2.tar.gz"
            )
            self.warning_label.show()
            self.run_button.setEnabled(False)
            return
        
        # If we get here, everything is good - hide the warning
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
            self.fasta_path = file_path
            self.file_path_input.setText(file_path)
            
            # Validate file
            is_valid, error_msg, seq_count, file_size_mb = validate_fasta_file(file_path)
            
            if is_valid:
                self.file_info_label.setText(
                    f"✓ Valid FASTA file: {seq_count:,} sequences, {file_size_mb:.1f} MB"
                )
                self.file_info_label.setStyleSheet("color: #27ae60; font-style: italic; padding: 5px;")
            else:
                self.file_info_label.setText(f"✗ {error_msg}")
                self.file_info_label.setStyleSheet("color: #e74c3c; font-style: italic; padding: 5px;")
                self.fasta_path = None
    
    def on_mode_changed(self):
        """Handle clustering mode change"""
        mode = self.mode_combo.currentData()
        
        # Enable/disable k-mer option for linclust
        if mode == "linclust":
            self.kmer_spin.setEnabled(True)
            self.kmer_label_widget.setEnabled(True)
        else:
            self.kmer_spin.setEnabled(False)
            self.kmer_label_widget.setEnabled(False)
        
        self.validate_parameters()
    
    def validate_parameters(self):
        """Validate clustering parameters"""
        mode = self.mode_combo.currentData()
        min_seq_id = self.identity_spin.value()
        
        # Critical validation: linclust requires >= 0.5 identity
        if mode == "linclust" and min_seq_id < 0.5:
            self.param_warning_label.setText(
                "⚠️ Linclust requires minimum sequence identity ≥ 0.5 (50%)\n"
                "Please increase the identity threshold or use regular clustering."
            )
            self.param_warning_label.show()
            self.run_button.setEnabled(False)
            return False
        else:
            self.param_warning_label.hide()
            self.run_button.setEnabled(True if self.fasta_path else False)
            return True
    
    def toggle_advanced_options(self):
        """Show/hide advanced options"""
        if self.advanced_checkbox.isChecked():
            self.advanced_widget.show()
        else:
            self.advanced_widget.hide()
    
    def run_clustering(self):
        """Run MMseqs2 clustering"""
        if not self.fasta_path:
            QMessageBox.warning(self, "No File", "Please select a FASTA file first.")
            return
        
        if not self.validate_parameters():
            return
        
        # Get parameters
        mode = self.mode_combo.currentData()
        min_seq_id = self.identity_spin.value()
        coverage = self.coverage_spin.value()
        cov_mode = self.covmode_combo.currentData()
        evalue = self.evalue_spin.value()
        sensitivity = self.sens_spin.value() if not self.sens_auto_checkbox.isChecked() else None
        kmer_per_seq = int(self.kmer_spin.value()) if mode == "linclust" else None
        single_step = (mode == "cluster_single")
        actual_mode = "linclust" if mode == "linclust" else "cluster"
        
        # Disable controls
        self.run_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.results_tabs.hide()
        
        # Start clustering
        self.search_start_time = time.time()
        self.clustering_worker = ClusteringWorker(
            self.fasta_path, actual_mode, min_seq_id, coverage, cov_mode,
            evalue, sensitivity, kmer_per_seq, single_step
        )
        self.clustering_worker.progress.connect(self.on_progress)
        self.clustering_worker.finished.connect(self.on_clustering_finished)
        self.clustering_worker.error.connect(self.on_clustering_error)
        self.clustering_worker.start()
    
    def cancel_clustering(self):
        """Cancel the clustering operation"""
        if self.clustering_worker:
            self.clustering_worker.cancel()
            self.clustering_worker.terminate()
            self.clustering_worker.wait()
        
        self.status_label.setText("Clustering cancelled")
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress_bar.hide()
    
    def on_progress(self, percent, message):
        """Update progress bar and status"""
        self.progress_bar.setValue(percent)
        self.status_label.setText(message)
    
    def on_clustering_finished(self, stats, rep_fasta_path, tsv_path):
        """Handle clustering completion"""
        search_time = time.time() - self.search_start_time if self.search_start_time else 0
        
        self.clustering_results = stats
        self.rep_fasta_path = rep_fasta_path
        self.tsv_path = tsv_path
        
        # Display results
        self.display_results(stats, search_time)
        
        # Re-enable controls
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress_bar.hide()
        self.status_label.setText(f"Clustering complete! ({search_time:.1f}s)")
        self.results_tabs.show()
    
    def on_clustering_error(self, error_msg):
        """Handle clustering error"""
        QMessageBox.critical(self, "Clustering Error", f"An error occurred:\n\n{error_msg}")
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress_bar.hide()
        self.status_label.setText("Error occurred")
    
    def display_results(self, stats, search_time):
        """Display clustering results in tabs"""
        # Tab 1: Overview - Summary and chart
        summary = create_text_summary(stats)
        summary += f"\n\nClustering Time: {search_time:.2f} seconds"
        self.summary_text.setPlainText(summary)
        
        # Create chart
        import tempfile
        self.chart_path = os.path.join(tempfile.gettempdir(), 'clustering_chart.png')
        success, result = create_distribution_chart(stats, self.chart_path)
        
        if success:
            pixmap = QPixmap(self.chart_path)
            self.chart_label.setPixmap(pixmap.scaled(1000, 600, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.chart_label.setText(f"Chart generation failed: {result}")
        
        # Tab 2: Clusters table
        table_data = get_cluster_table_data(stats, max_rows=1000)
        self.clusters_table.setRowCount(len(table_data))
        
        for row, (cluster_id, rep_id, size, members) in enumerate(table_data):
            self.clusters_table.setItem(row, 0, QTableWidgetItem(str(cluster_id)))
            self.clusters_table.setItem(row, 1, QTableWidgetItem(rep_id))
            self.clusters_table.setItem(row, 2, QTableWidgetItem(str(size)))
            self.clusters_table.setItem(row, 3, QTableWidgetItem(members))
        
        self.clusters_table.resizeColumnsToContents()
    
    def export_tsv(self):
        """Export clustering results as TSV"""
        if not self.clustering_results:
            QMessageBox.warning(self, "No Results", "No clustering results to export.")
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Clustering TSV",
            "clustering_results.tsv",
            "TSV Files (*.tsv);;All Files (*.*)"
        )
        
        if file_path:
            try:
                export_clustering_tsv(self.clustering_results, file_path)
                QMessageBox.information(self, "Export Successful", f"Results exported to:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to export:\n{str(e)}")
    
    def export_fasta(self):
        """Export representative sequences as FASTA"""
        if not self.rep_fasta_path or not os.path.exists(self.rep_fasta_path):
            QMessageBox.warning(self, "No Results", "No representative sequences available.")
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Representatives FASTA",
            "cluster_representatives.fasta",
            "FASTA Files (*.fasta *.fa);;All Files (*.*)"
        )
        
        if file_path:
            try:
                shutil.copy2(self.rep_fasta_path, file_path)
                QMessageBox.information(self, "Export Successful", f"Representatives exported to:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to export:\n{str(e)}")

