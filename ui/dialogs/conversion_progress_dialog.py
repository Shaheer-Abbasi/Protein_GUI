"""Progress dialog for database conversion"""
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar, QPushButton, QTextEdit
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from ui.theme import get_theme


class ConversionProgressDialog(QDialog):
    """Dialog showing database conversion progress"""
    
    def __init__(self, db_name, parent=None):
        super().__init__(parent)
        self.db_name = db_name
        self.conversion_worker = None
        self.init_ui()
    
    def init_ui(self):
        """Initialize the dialog UI"""
        self.setWindowTitle(f"Converting Database: {self.db_name}")
        self.setModal(False)  # Non-modal so user can use other features
        self.setMinimumWidth(500)
        self.setMinimumHeight(250)
        
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Title
        title_label = QLabel(f"Converting {self.db_name} to MMseqs2 format")
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setProperty("class", "heading")
        
        # Info label
        info_label = QLabel(
            "This process will:\n"
            "1. Extract sequences from BLAST database\n"
            "2. Convert to MMseqs2 format\n"
            "3. Save the converted database"
        )
        info_label.setProperty("class", "muted")
        
        # Status label
        self.status_label = QLabel("Initializing...")
        self.status_label.setStyleSheet(self._status_style("text_secondary"))
        self.status_label.setWordWrap(True)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        
        # Details text (hidden by default)
        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        self.details_text.setMaximumHeight(100)
        self.details_text.setVisible(False)
        
        # Buttons
        button_layout = QVBoxLayout()
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setProperty("class", "danger")
        self.cancel_button.clicked.connect(self.on_cancel_clicked)
        
        self.close_button = QPushButton("Close")
        self.close_button.setProperty("class", "secondary")
        self.close_button.clicked.connect(self.accept)
        self.close_button.setVisible(False)
        
        self.show_details_button = QPushButton("Show Details")
        self.show_details_button.setProperty("class", "secondary")
        self.show_details_button.clicked.connect(self.toggle_details)
        
        button_layout.addWidget(self.show_details_button)
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.close_button)
        
        # Add all widgets to layout
        layout.addWidget(title_label)
        layout.addWidget(info_label)
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.details_text)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)

    def _status_style(self, color_key):
        return f"color: {get_theme().get(color_key)}; font-weight: bold;"
    
    def set_worker(self, worker):
        """Set the conversion worker and connect signals
        
        Args:
            worker: DatabaseConversionWorker instance
        """
        self.conversion_worker = worker
        
        # Connect signals
        worker.progress.connect(self.on_progress)
        worker.finished.connect(self.on_finished)
        worker.error.connect(self.on_error)
    
    def on_progress(self, message, percentage):
        """Handle progress update
        
        Args:
            message: Progress message
            percentage: Progress percentage (0-100)
        """
        self.status_label.setText(message)
        self.progress_bar.setValue(percentage)
        
        # Add to details
        self.details_text.append(f"[{percentage}%] {message}")
    
    def on_finished(self, db_name, mmseqs_path):
        """Handle conversion completion
        
        Args:
            db_name: Name of the database
            mmseqs_path: Path to converted MMseqs2 database
        """
        self.status_label.setText(f"✓ Conversion complete! Database ready to use.")
        self.status_label.setStyleSheet(self._status_style("success"))
        self.progress_bar.setValue(100)
        
        self.cancel_button.setVisible(False)
        self.close_button.setVisible(True)
        
        self.details_text.append(f"\n✓ Successfully converted {db_name}")
        self.details_text.append(f"MMseqs2 database: {mmseqs_path}")
    
    def on_error(self, db_name, error_message):
        """Handle conversion error
        
        Args:
            db_name: Name of the database
            error_message: Error message
        """
        self.status_label.setText(f"✗ Conversion failed")
        self.status_label.setStyleSheet(self._status_style("error"))
        
        self.cancel_button.setVisible(False)
        self.close_button.setVisible(True)
        
        self.details_text.append(f"\n✗ Error converting {db_name}:")
        self.details_text.append(error_message)
        self.details_text.setVisible(True)
        self.show_details_button.setText("Hide Details")
        
        # Expand dialog to show error
        self.resize(self.width(), 400)
    
    def on_cancel_clicked(self):
        """Handle cancel button click"""
        if self.conversion_worker:
            self.status_label.setText("Cancelling conversion...")
            self.cancel_button.setEnabled(False)
            self.conversion_worker.cancel()
    
    def toggle_details(self):
        """Toggle details visibility"""
        if self.details_text.isVisible():
            self.details_text.setVisible(False)
            self.show_details_button.setText("Show Details")
            self.resize(self.width(), 250)
        else:
            self.details_text.setVisible(True)
            self.show_details_button.setText("Hide Details")
            self.resize(self.width(), 400)
    
    def closeEvent(self, event):
        """Handle dialog close event"""
        if self.conversion_worker and self.conversion_worker.isRunning():
            # Ask user if they want to cancel
            self.conversion_worker.cancel()
        event.accept()
