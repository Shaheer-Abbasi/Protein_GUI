"""
Dialog for configuring clustering parameters before starting
Shows summary of successful/failed sequence retrievals
"""
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QComboBox, QGroupBox, QCheckBox, QTextEdit, QSpinBox,
                             QDoubleSpinBox, QMessageBox)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from typing import List, Dict, Any


class ClusteringConfigDialog(QDialog):
    """
    Dialog for configuring clustering parameters
    
    Shows:
    - Number of sequences successfully retrieved
    - List of failed sequences (if any)
    - Clustering method selection
    - Parameter configuration
    """
    
    def __init__(self, successful_hits: List, failed_hits: List, parent=None):
        super().__init__(parent)
        self.successful_hits = successful_hits
        self.failed_hits = failed_hits
        self.clustering_params = {}
        
        self.setWindowTitle("Configure Clustering")
        self.resize(600, 500)
        
        self._init_ui()
    
    def _init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()
        
        # Header
        header_label = QLabel("Configure Clustering")
        header_font = QFont()
        header_font.setPointSize(14)
        header_font.setBold(True)
        header_label.setFont(header_font)
        layout.addWidget(header_label)
        
        # Summary section
        summary_group = QGroupBox("Sequence Retrieval Summary")
        summary_layout = QVBoxLayout()
        
        success_count = len(self.successful_hits)
        failed_count = len(self.failed_hits)
        total_count = success_count + failed_count
        
        summary_text = f"<b>Total sequences:</b> {total_count}<br>"
        summary_text += f"<b>✓ Successfully retrieved:</b> {success_count}<br>"
        
        if failed_count > 0:
            summary_text += f"<b>✗ Failed to retrieve:</b> {failed_count}"
        
        summary_label = QLabel(summary_text)
        summary_label.setStyleSheet("padding: 10px; background-color: #ecf0f1; border-radius: 5px;")
        summary_layout.addWidget(summary_label)
        
        summary_group.setLayout(summary_layout)
        layout.addWidget(summary_group)
        
        # Show failed sequences if any
        if failed_count > 0:
            self.show_failed_checkbox = QCheckBox("Show failed sequences")
            self.show_failed_checkbox.toggled.connect(self._toggle_failed_list)
            layout.addWidget(self.show_failed_checkbox)
            
            self.failed_text = QTextEdit()
            self.failed_text.setReadOnly(True)
            self.failed_text.setMaximumHeight(100)
            self.failed_text.setVisible(False)
            
            failed_list = []
            for hit in self.failed_hits:
                failed_list.append(f"• {hit.accession} - {hit.description[:60]}")
            
            self.failed_text.setPlainText("\n".join(failed_list))
            layout.addWidget(self.failed_text)
        
        # Clustering method
        method_group = QGroupBox("Clustering Method")
        method_layout = QVBoxLayout()
        
        method_label = QLabel("Select clustering algorithm:")
        method_layout.addWidget(method_label)
        
        self.method_combo = QComboBox()
        self.method_combo.addItem("MMseqs2 Easy-Cluster (Recommended)", "easy-cluster")
        self.method_combo.addItem("MMseqs2 Linclust (Fast)", "linclust")
        self.method_combo.currentIndexChanged.connect(self._on_method_changed)
        method_layout.addWidget(self.method_combo)
        
        method_desc_label = QLabel(
            "<i>Easy-cluster: Balanced speed and sensitivity<br>"
            "Linclust: Very fast for large datasets</i>"
        )
        method_desc_label.setStyleSheet("color: #666; margin-top: 5px;")
        method_layout.addWidget(method_desc_label)
        
        method_group.setLayout(method_layout)
        layout.addWidget(method_group)
        
        # Parameters
        params_group = QGroupBox("Clustering Parameters")
        params_layout = QVBoxLayout()
        
        # Identity threshold
        identity_layout = QHBoxLayout()
        identity_label = QLabel("Minimum Sequence Identity:")
        identity_label.setFixedWidth(200)
        
        self.identity_spin = QDoubleSpinBox()
        self.identity_spin.setRange(0.0, 1.0)
        self.identity_spin.setValue(0.3)
        self.identity_spin.setSingleStep(0.05)
        self.identity_spin.setDecimals(2)
        self.identity_spin.setSuffix(" (30%)")
        self.identity_spin.valueChanged.connect(lambda v: self.identity_spin.setSuffix(f" ({int(v*100)}%)"))
        
        identity_layout.addWidget(identity_label)
        identity_layout.addWidget(self.identity_spin)
        identity_layout.addStretch()
        
        # Coverage
        coverage_layout = QHBoxLayout()
        coverage_label = QLabel("Coverage Threshold:")
        coverage_label.setFixedWidth(200)
        
        self.coverage_spin = QDoubleSpinBox()
        self.coverage_spin.setRange(0.0, 1.0)
        self.coverage_spin.setValue(0.8)
        self.coverage_spin.setSingleStep(0.05)
        self.coverage_spin.setDecimals(2)
        self.coverage_spin.setSuffix(" (80%)")
        self.coverage_spin.valueChanged.connect(lambda v: self.coverage_spin.setSuffix(f" ({int(v*100)}%)"))
        
        coverage_layout.addWidget(coverage_label)
        coverage_layout.addWidget(self.coverage_spin)
        coverage_layout.addStretch()
        
        # Sensitivity (for easy-cluster)
        self.sensitivity_layout = QHBoxLayout()
        sensitivity_label = QLabel("Sensitivity:")
        sensitivity_label.setFixedWidth(200)
        
        self.sensitivity_spin = QDoubleSpinBox()
        self.sensitivity_spin.setRange(1.0, 7.5)
        self.sensitivity_spin.setValue(7.5)
        self.sensitivity_spin.setSingleStep(0.5)
        self.sensitivity_spin.setDecimals(1)
        
        self.sensitivity_layout.addWidget(sensitivity_label)
        self.sensitivity_layout.addWidget(self.sensitivity_spin)
        self.sensitivity_layout.addStretch()
        
        params_layout.addLayout(identity_layout)
        params_layout.addLayout(coverage_layout)
        params_layout.addLayout(self.sensitivity_layout)
        
        params_group.setLayout(params_layout)
        layout.addWidget(params_group)
        
        # Warning for failed sequences
        if failed_count > 0:
            warning_label = QLabel(
                f"⚠️ {failed_count} sequence(s) could not be retrieved and will be excluded from clustering."
            )
            warning_label.setStyleSheet("""
                QLabel {
                    background-color: #fff3cd;
                    color: #856404;
                    padding: 10px;
                    border-radius: 5px;
                    font-weight: bold;
                }
            """)
            warning_label.setWordWrap(True)
            layout.addWidget(warning_label)
        
        # Continue prompt
        if success_count >= 2:
            continue_label = QLabel(f"Ready to cluster {success_count} sequences")
            continue_label.setStyleSheet("""
                QLabel {
                    background-color: #d4edda;
                    color: #155724;
                    padding: 10px;
                    border-radius: 5px;
                    font-weight: bold;
                }
            """)
            layout.addWidget(continue_label)
        else:
            error_label = QLabel(
                f"❌ Cannot cluster: Only {success_count} sequence(s) retrieved. Need at least 2."
            )
            error_label.setStyleSheet("""
                QLabel {
                    background-color: #f8d7da;
                    color: #721c24;
                    padding: 10px;
                    border-radius: 5px;
                    font-weight: bold;
                }
            """)
            layout.addWidget(error_label)
        
        layout.addStretch()
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        
        self.start_button = QPushButton("Start Clustering →")
        self.start_button.clicked.connect(self._on_start_clustering)
        self.start_button.setEnabled(success_count >= 2)
        self.start_button.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #229954;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
            }
        """)
        
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(self.start_button)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def _toggle_failed_list(self, checked):
        """Toggle visibility of failed sequences list"""
        if hasattr(self, 'failed_text'):
            self.failed_text.setVisible(checked)
    
    def _on_method_changed(self, index):
        """Handle clustering method change"""
        method = self.method_combo.currentData()
        
        # Sensitivity only applies to easy-cluster
        if method == 'easy-cluster':
            self.sensitivity_spin.setEnabled(True)
        else:
            self.sensitivity_spin.setEnabled(False)
    
    def _on_start_clustering(self):
        """Handle start clustering button click"""
        if len(self.successful_hits) < 2:
            QMessageBox.warning(
                self,
                "Insufficient Sequences",
                "Need at least 2 sequences for clustering."
            )
            return
        
        # Collect parameters
        self.clustering_params = {
            'method': self.method_combo.currentData(),
            'min_seq_id': self.identity_spin.value(),
            'coverage': self.coverage_spin.value(),
            'sensitivity': self.sensitivity_spin.value() if self.method_combo.currentData() == 'easy-cluster' else None
        }
        
        self.accept()
    
    def get_parameters(self) -> Dict[str, Any]:
        """Get the clustering parameters"""
        return self.clustering_params
    
    def get_successful_hits(self) -> List:
        """Get the successfully retrieved hits"""
        return self.successful_hits

