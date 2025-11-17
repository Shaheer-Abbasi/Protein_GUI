"""
Dialog for selecting search results to cluster
Supports multiple selection modes with live preview
"""
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QRadioButton, QSpinBox, QLineEdit, QTableWidget, 
                             QTableWidgetItem, QHeaderView, QGroupBox, QCheckBox,
                             QButtonGroup, QMessageBox, QWidget)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QDoubleValidator

from typing import List


class ClusterSelectionDialog(QDialog):
    """
    Dialog for selecting which search results to cluster
    
    Features:
    - Top N matches selection
    - E-value threshold selection
    - Manual checkbox selection
    - Live selection count
    - Duplicate detection
    """
    
    def __init__(self, search_hits: List, parent=None):
        super().__init__(parent)
        self.search_hits = search_hits
        self.selected_hits = []
        self.selection_mode = 'top_n'  # 'top_n', 'evalue', 'manual'
        
        self.setWindowTitle("Select Results for Clustering")
        self.resize(800, 600)
        
        self._init_ui()
        self._update_selection()
    
    def _init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()
        
        # Header
        header_label = QLabel("Select Results for Clustering")
        header_font = QFont()
        header_font.setPointSize(14)
        header_font.setBold(True)
        header_label.setFont(header_font)
        layout.addWidget(header_label)
        
        # Selection mode group
        mode_group = QGroupBox("Selection Mode")
        mode_layout = QVBoxLayout()
        
        self.mode_button_group = QButtonGroup()
        
        # Top N mode
        top_n_layout = QHBoxLayout()
        self.top_n_radio = QRadioButton("Top N matches")
        self.top_n_radio.setChecked(True)
        self.mode_button_group.addButton(self.top_n_radio, 1)
        
        self.top_n_spin = QSpinBox()
        self.top_n_spin.setRange(2, min(500, len(self.search_hits)))
        self.top_n_spin.setValue(min(50, len(self.search_hits)))
        self.top_n_spin.setFixedWidth(100)
        self.top_n_spin.valueChanged.connect(self._on_top_n_changed)
        
        self.top_n_count_label = QLabel()
        
        top_n_layout.addWidget(self.top_n_radio)
        top_n_layout.addWidget(self.top_n_spin)
        top_n_layout.addWidget(self.top_n_count_label)
        top_n_layout.addStretch()
        
        # E-value threshold mode
        evalue_layout = QHBoxLayout()
        self.evalue_radio = QRadioButton("E-value threshold ≤")
        self.mode_button_group.addButton(self.evalue_radio, 2)
        
        self.evalue_input = QLineEdit("1e-10")
        self.evalue_input.setFixedWidth(100)
        validator = QDoubleValidator()
        validator.setNotation(QDoubleValidator.ScientificNotation)
        self.evalue_input.setValidator(validator)
        self.evalue_input.textChanged.connect(self._on_evalue_changed)
        
        self.evalue_count_label = QLabel()
        
        evalue_layout.addWidget(self.evalue_radio)
        evalue_layout.addWidget(self.evalue_input)
        evalue_layout.addWidget(self.evalue_count_label)
        evalue_layout.addStretch()
        
        # Manual selection mode
        manual_layout = QHBoxLayout()
        self.manual_radio = QRadioButton("Manual selection")
        self.mode_button_group.addButton(self.manual_radio, 3)
        
        self.manual_count_label = QLabel()
        
        manual_layout.addWidget(self.manual_radio)
        manual_layout.addWidget(self.manual_count_label)
        manual_layout.addStretch()
        
        # Connect mode changes
        self.top_n_radio.toggled.connect(self._on_mode_changed)
        self.evalue_radio.toggled.connect(self._on_mode_changed)
        self.manual_radio.toggled.connect(self._on_mode_changed)
        
        mode_layout.addLayout(top_n_layout)
        mode_layout.addLayout(evalue_layout)
        mode_layout.addLayout(manual_layout)
        mode_group.setLayout(mode_layout)
        layout.addWidget(mode_group)
        
        # Results table
        table_label = QLabel("Search Results:")
        layout.addWidget(table_label)
        
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(6)
        self.results_table.setHorizontalHeaderLabels([
            "", "Rank", "Accession", "E-value", "Identity", "Length"
        ])
        
        # Set column widths
        header = self.results_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)  # Checkbox
        header.setSectionResizeMode(1, QHeaderView.Fixed)  # Rank
        header.setSectionResizeMode(2, QHeaderView.Stretch)  # Accession
        header.setSectionResizeMode(3, QHeaderView.Fixed)  # E-value
        header.setSectionResizeMode(4, QHeaderView.Fixed)  # Identity
        header.setSectionResizeMode(5, QHeaderView.Fixed)  # Length
        
        self.results_table.setColumnWidth(0, 30)
        self.results_table.setColumnWidth(1, 60)
        self.results_table.setColumnWidth(3, 100)
        self.results_table.setColumnWidth(4, 80)
        self.results_table.setColumnWidth(5, 80)
        
        # Populate table
        self._populate_table()
        
        layout.addWidget(self.results_table)
        
        # Selection controls
        controls_layout = QHBoxLayout()
        
        self.remove_duplicates_checkbox = QCheckBox("Remove Duplicates")
        self.remove_duplicates_checkbox.setChecked(True)
        self.remove_duplicates_checkbox.toggled.connect(self._update_selection_display)
        
        select_all_button = QPushButton("Select All")
        select_all_button.clicked.connect(self._select_all)
        
        clear_all_button = QPushButton("Clear All")
        clear_all_button.clicked.connect(self._clear_all)
        
        controls_layout.addWidget(self.remove_duplicates_checkbox)
        controls_layout.addStretch()
        controls_layout.addWidget(select_all_button)
        controls_layout.addWidget(clear_all_button)
        
        layout.addLayout(controls_layout)
        
        # Selection summary
        self.summary_label = QLabel()
        self.summary_label.setStyleSheet("""
            QLabel {
                background-color: #ecf0f1;
                padding: 10px;
                border-radius: 5px;
                font-weight: bold;
            }
        """)
        layout.addWidget(self.summary_label)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        
        self.continue_button = QPushButton("Continue →")
        self.continue_button.clicked.connect(self._on_continue)
        self.continue_button.setStyleSheet("""
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
        button_layout.addWidget(self.continue_button)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def _populate_table(self):
        """Populate the results table with search hits"""
        self.results_table.setRowCount(len(self.search_hits))
        
        for i, hit in enumerate(self.search_hits):
            # Checkbox
            checkbox_widget = QWidget()
            checkbox_layout = QHBoxLayout(checkbox_widget)
            checkbox = QCheckBox()
            checkbox.setChecked(True)  # Default selected
            checkbox.stateChanged.connect(lambda state, row=i: self._on_manual_selection_changed(row, state))
            checkbox_layout.addWidget(checkbox)
            checkbox_layout.setAlignment(Qt.AlignCenter)
            checkbox_layout.setContentsMargins(0, 0, 0, 0)
            self.results_table.setCellWidget(i, 0, checkbox_widget)
            
            # Rank
            rank_item = QTableWidgetItem(str(hit.rank))
            rank_item.setTextAlignment(Qt.AlignCenter)
            self.results_table.setItem(i, 1, rank_item)
            
            # Accession
            acc_item = QTableWidgetItem(hit.accession)
            self.results_table.setItem(i, 2, acc_item)
            
            # E-value
            evalue_item = QTableWidgetItem(f"{hit.evalue:.2e}")
            evalue_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.results_table.setItem(i, 3, evalue_item)
            
            # Identity
            identity_item = QTableWidgetItem(f"{hit.identity_percent:.1f}%")
            identity_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.results_table.setItem(i, 4, identity_item)
            
            # Length
            length_item = QTableWidgetItem(f"{hit.sequence_length} aa")
            length_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.results_table.setItem(i, 5, length_item)
    
    def _on_mode_changed(self):
        """Handle selection mode change"""
        if self.top_n_radio.isChecked():
            self.selection_mode = 'top_n'
            self.top_n_spin.setEnabled(True)
            self.evalue_input.setEnabled(False)
        elif self.evalue_radio.isChecked():
            self.selection_mode = 'evalue'
            self.top_n_spin.setEnabled(False)
            self.evalue_input.setEnabled(True)
        else:
            self.selection_mode = 'manual'
            self.top_n_spin.setEnabled(False)
            self.evalue_input.setEnabled(False)
        
        self._update_selection()
    
    def _on_top_n_changed(self, value):
        """Handle top N value change"""
        if self.selection_mode == 'top_n':
            self._update_selection()
    
    def _on_evalue_changed(self, text):
        """Handle e-value threshold change"""
        if self.selection_mode == 'evalue':
            self._update_selection()
    
    def _on_manual_selection_changed(self, row, state):
        """Handle manual checkbox change"""
        if self.selection_mode == 'manual':
            self._update_selection()
    
    def _update_selection(self):
        """Update selection based on current mode"""
        # Update checkboxes based on mode
        for i in range(self.results_table.rowCount()):
            checkbox_widget = self.results_table.cellWidget(i, 0)
            checkbox = checkbox_widget.findChild(QCheckBox)
            
            if self.selection_mode == 'top_n':
                checkbox.setEnabled(False)
                n = self.top_n_spin.value()
                checkbox.setChecked(i < n)
            
            elif self.selection_mode == 'evalue':
                checkbox.setEnabled(False)
                try:
                    threshold = float(self.evalue_input.text())
                    hit = self.search_hits[i]
                    checkbox.setChecked(hit.evalue <= threshold)
                except:
                    checkbox.setChecked(False)
            
            else:  # manual
                checkbox.setEnabled(True)
        
        self._update_selection_display()
    
    def _update_selection_display(self):
        """Update the selection count display"""
        # Count selected
        selected_count = 0
        for i in range(self.results_table.rowCount()):
            checkbox_widget = self.results_table.cellWidget(i, 0)
            checkbox = checkbox_widget.findChild(QCheckBox)
            if checkbox.isChecked():
                selected_count += 1
        
        # Update mode labels
        self.top_n_count_label.setText(f"(Currently: {self.top_n_spin.value()})")
        
        try:
            evalue_threshold = float(self.evalue_input.text())
            evalue_matches = sum(1 for hit in self.search_hits if hit.evalue <= evalue_threshold)
            self.evalue_count_label.setText(f"({evalue_matches} matches)")
        except:
            self.evalue_count_label.setText("(Invalid value)")
        
        self.manual_count_label.setText(f"(Check boxes below)")
        
        # Update summary
        duplicate_text = ""
        if self.remove_duplicates_checkbox.isChecked() and selected_count > 0:
            # Simulate duplicate detection
            duplicate_text = " (duplicates will be removed)"
        
        self.summary_label.setText(
            f"Selected: {selected_count} sequences{duplicate_text}"
        )
        
        # Enable/disable continue button
        self.continue_button.setEnabled(selected_count >= 2)
        
        if selected_count < 2:
            self.summary_label.setStyleSheet("""
                QLabel {
                    background-color: #f8d7da;
                    color: #721c24;
                    padding: 10px;
                    border-radius: 5px;
                    font-weight: bold;
                }
            """)
            if selected_count == 0:
                self.summary_label.setText("⚠️ No sequences selected. Select at least 2 sequences.")
            else:
                self.summary_label.setText("⚠️ Only 1 sequence selected. Select at least 2 sequences.")
        elif selected_count > 100:
            self.summary_label.setStyleSheet("""
                QLabel {
                    background-color: #fff3cd;
                    color: #856404;
                    padding: 10px;
                    border-radius: 5px;
                    font-weight: bold;
                }
            """)
            self.summary_label.setText(
                f"⚠️ Selected: {selected_count} sequences{duplicate_text} (Large selection may be slow)"
            )
        else:
            self.summary_label.setStyleSheet("""
                QLabel {
                    background-color: #d4edda;
                    color: #155724;
                    padding: 10px;
                    border-radius: 5px;
                    font-weight: bold;
                }
            """)
    
    def _select_all(self):
        """Select all checkboxes"""
        if self.selection_mode != 'manual':
            return
        
        for i in range(self.results_table.rowCount()):
            checkbox_widget = self.results_table.cellWidget(i, 0)
            checkbox = checkbox_widget.findChild(QCheckBox)
            checkbox.setChecked(True)
    
    def _clear_all(self):
        """Clear all checkboxes"""
        if self.selection_mode != 'manual':
            return
        
        for i in range(self.results_table.rowCount()):
            checkbox_widget = self.results_table.cellWidget(i, 0)
            checkbox = checkbox_widget.findChild(QCheckBox)
            checkbox.setChecked(False)
    
    def _on_continue(self):
        """Handle continue button click"""
        # Collect selected hits
        selected = []
        for i in range(self.results_table.rowCount()):
            checkbox_widget = self.results_table.cellWidget(i, 0)
            checkbox = checkbox_widget.findChild(QCheckBox)
            if checkbox.isChecked():
                selected.append(self.search_hits[i])
        
        if len(selected) < 2:
            QMessageBox.warning(
                self,
                "Insufficient Selection",
                "Please select at least 2 sequences for clustering."
            )
            return
        
        # Remove duplicates if requested (by accession)
        if self.remove_duplicates_checkbox.isChecked():
            # Deduplicate by accession
            seen_accessions = set()
            unique = []
            for hit in selected:
                if hit.accession not in seen_accessions:
                    seen_accessions.add(hit.accession)
                    unique.append(hit)
            
            num_removed = len(selected) - len(unique)
            if num_removed > 0:
                reply = QMessageBox.question(
                    self,
                    "Duplicates Found",
                    f"Found {num_removed} duplicate sequence(s) based on accession.\n\n"
                    f"Continue with {len(unique)} unique sequences?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.No:
                    return
                selected = unique
        
        # Warn about large selections
        if len(selected) > 100:
            reply = QMessageBox.question(
                self,
                "Large Selection",
                f"You've selected {len(selected)} sequences.\n"
                f"Clustering may take several minutes.\n\n"
                f"Continue?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.No:
                return
        
        self.selected_hits = selected
        self.accept()
    
    def get_selected_hits(self) -> List:
        """Get the selected hits"""
        return self.selected_hits

