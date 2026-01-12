"""
Database Downloads page for managing protein database installations.

Provides a UI for:
- Viewing available databases (starter packs and full databases)
- Downloading databases from S3
- Installing databases via WSL tools
- Opening external links for large databases
- Tracking installed databases
"""

import os
import webbrowser
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QGroupBox, QGridLayout, QProgressBar,
    QTextEdit, QFileDialog, QMessageBox, QSplitter, QSizePolicy,
    QTabWidget
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QDesktopServices
from PyQt5.QtCore import QUrl

from core.database_manifest import (
    load_database_manifest, DatabaseEntry, DistributionType,
    get_manifest_loader
)
from core.installed_databases import get_installed_databases_tracker
from core.database_download_worker import DatabaseDownloadWorker
from core.database_install_worker import DatabaseInstallWorker


class DatabaseCard(QFrame):
    """Card widget for displaying a single database entry"""
    
    download_requested = pyqtSignal(object)  # DatabaseEntry
    install_requested = pyqtSignal(object)   # DatabaseEntry
    open_link_requested = pyqtSignal(str)    # URL
    
    def __init__(self, entry: DatabaseEntry, is_installed: bool = False, 
                 installed_version: str = None, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.is_installed = is_installed
        self.installed_version = installed_version
        self._init_ui()
    
    def _init_ui(self):
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("""
            DatabaseCard {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                margin: 4px;
            }
            DatabaseCard:hover {
                border: 1px solid #3498db;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(8)
        
        # Header row: Name + Status badge
        header_layout = QHBoxLayout()
        
        name_label = QLabel(self.entry.display_name)
        name_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #2c3e50;")
        header_layout.addWidget(name_label)
        
        header_layout.addStretch()
        
        # Tool format badges
        for tool in self.entry.tool_formats:
            badge = QLabel(tool.upper())
            if tool == "blast":
                badge.setStyleSheet("""
                    QLabel {
                        background-color: #3498db;
                        color: white;
                        padding: 2px 8px;
                        border-radius: 10px;
                        font-size: 10px;
                        font-weight: bold;
                    }
                """)
            else:
                badge.setStyleSheet("""
                    QLabel {
                        background-color: #9b59b6;
                        color: white;
                        padding: 2px 8px;
                        border-radius: 10px;
                        font-size: 10px;
                        font-weight: bold;
                    }
                """)
            header_layout.addWidget(badge)
        
        # Installed badge
        if self.is_installed:
            installed_badge = QLabel("✓ Installed")
            installed_badge.setStyleSheet("""
                QLabel {
                    background-color: #27ae60;
                    color: white;
                    padding: 2px 8px;
                    border-radius: 10px;
                    font-size: 10px;
                    font-weight: bold;
                }
            """)
            header_layout.addWidget(installed_badge)
        
        layout.addLayout(header_layout)
        
        # Description
        desc_label = QLabel(self.entry.description)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #7f8c8d; font-size: 11px;")
        layout.addWidget(desc_label)
        
        # Info row: Size, Version, Last Updated
        info_layout = QHBoxLayout()
        info_layout.setSpacing(20)
        
        size_label = QLabel(f"📦 {self.entry.get_size_display()}")
        size_label.setStyleSheet("color: #5d6d7e; font-size: 11px;")
        info_layout.addWidget(size_label)
        
        disk_label = QLabel(f"💾 Requires: {self.entry.get_disk_required_display()}")
        disk_label.setStyleSheet("color: #5d6d7e; font-size: 11px;")
        info_layout.addWidget(disk_label)
        
        version_label = QLabel(f"📅 {self.entry.version}")
        version_label.setStyleSheet("color: #5d6d7e; font-size: 11px;")
        info_layout.addWidget(version_label)
        
        info_layout.addStretch()
        layout.addLayout(info_layout)
        
        # Action button row
        action_layout = QHBoxLayout()
        action_layout.setSpacing(10)
        
        if self.entry.distribution_type == DistributionType.S3:
            # Direct download button
            download_btn = QPushButton("⬇️ Download")
            download_btn.setStyleSheet("""
                QPushButton {
                    background-color: #27ae60;
                    color: white;
                    border: none;
                    border-radius: 5px;
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
            download_btn.clicked.connect(lambda: self.download_requested.emit(self.entry))
            action_layout.addWidget(download_btn)
            
        elif self.entry.distribution_type == DistributionType.INSTALLER:
            # Install via tool button
            install_btn = QPushButton("🔧 Install via Tool")
            install_btn.setStyleSheet("""
                QPushButton {
                    background-color: #3498db;
                    color: white;
                    border: none;
                    border-radius: 5px;
                    padding: 8px 16px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
            """)
            install_btn.clicked.connect(lambda: self.install_requested.emit(self.entry))
            action_layout.addWidget(install_btn)
            
        elif self.entry.distribution_type == DistributionType.EXTERNAL:
            # External link button
            link_btn = QPushButton("🔗 Open External Link")
            link_btn.setStyleSheet("""
                QPushButton {
                    background-color: #e67e22;
                    color: white;
                    border: none;
                    border-radius: 5px;
                    padding: 8px 16px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #d35400;
                }
            """)
            link_btn.clicked.connect(
                lambda: self.open_link_requested.emit(self.entry.distribution.url)
            )
            action_layout.addWidget(link_btn)
            
            # Show notes if available
            if hasattr(self.entry.distribution, 'notes') and self.entry.distribution.notes:
                notes_label = QLabel(f"⚠️ {self.entry.distribution.notes}")
                notes_label.setStyleSheet("color: #e74c3c; font-size: 10px;")
                notes_label.setWordWrap(True)
                layout.addWidget(notes_label)
        
        action_layout.addStretch()
        layout.addLayout(action_layout)


class DatabaseDownloadsPage(QWidget):
    """Main page for database downloads and management"""
    
    back_requested = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self.current_worker = None
        self.tracker = get_installed_databases_tracker()
        self._init_ui()
        self._load_manifest()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Header
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
        
        page_title = QLabel("Database Downloads")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        page_title.setFont(title_font)
        page_title.setStyleSheet("color: #2c3e50;")
        
        # Refresh button
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 8px 15px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        refresh_btn.clicked.connect(self._refresh_manifest)
        
        header_layout.addWidget(back_button)
        header_layout.addStretch()
        header_layout.addWidget(page_title)
        header_layout.addStretch()
        header_layout.addWidget(refresh_btn)
        
        layout.addLayout(header_layout)
        
        # Manifest info bar
        self.manifest_info = QLabel("Loading database catalog...")
        self.manifest_info.setStyleSheet("""
            QLabel {
                background-color: #ecf0f1;
                padding: 8px 12px;
                border-radius: 5px;
                color: #7f8c8d;
                font-size: 11px;
            }
        """)
        layout.addWidget(self.manifest_info)
        
        # Destination folder selector
        dest_group = QGroupBox("Installation Settings")
        dest_layout = QHBoxLayout()
        
        dest_label = QLabel("Download to:")
        self.dest_path_label = QLabel(self._get_default_dest())
        self.dest_path_label.setStyleSheet("color: #2c3e50; font-weight: bold;")
        
        browse_btn = QPushButton("📁 Browse...")
        browse_btn.clicked.connect(self._browse_destination)
        browse_btn.setStyleSheet("""
            QPushButton {
                background-color: #ecf0f1;
                border: 1px solid #bdc3c7;
                border-radius: 4px;
                padding: 5px 12px;
            }
            QPushButton:hover {
                background-color: #d5dbdb;
            }
        """)
        
        dest_layout.addWidget(dest_label)
        dest_layout.addWidget(self.dest_path_label, 1)
        dest_layout.addWidget(browse_btn)
        dest_group.setLayout(dest_layout)
        layout.addWidget(dest_group)
        
        # Main content - Splitter with databases and log
        splitter = QSplitter(Qt.Vertical)
        
        # Tabs for Starter Packs vs Full Databases
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #e0e0e0;
                border-radius: 5px;
                background: white;
            }
            QTabBar::tab {
                background: #ecf0f1;
                border: 1px solid #bdc3c7;
                padding: 8px 20px;
                margin-right: 2px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
            }
            QTabBar::tab:selected {
                background: white;
                border-bottom-color: white;
            }
            QTabBar::tab:hover:!selected {
                background: #d5dbdb;
            }
        """)
        
        # Starter packs tab
        self.starter_scroll = QScrollArea()
        self.starter_scroll.setWidgetResizable(True)
        self.starter_scroll.setFrameShape(QFrame.NoFrame)
        self.starter_content = QWidget()
        self.starter_layout = QVBoxLayout(self.starter_content)
        self.starter_layout.setAlignment(Qt.AlignTop)
        self.starter_scroll.setWidget(self.starter_content)
        
        # Full databases tab
        self.full_scroll = QScrollArea()
        self.full_scroll.setWidgetResizable(True)
        self.full_scroll.setFrameShape(QFrame.NoFrame)
        self.full_content = QWidget()
        self.full_layout = QVBoxLayout(self.full_content)
        self.full_layout.setAlignment(Qt.AlignTop)
        self.full_scroll.setWidget(self.full_content)
        
        self.tabs.addTab(self.starter_scroll, "⚡ Quick Start (Recommended)")
        self.tabs.addTab(self.full_scroll, "📚 Full Databases (Large)")
        
        splitter.addWidget(self.tabs)
        
        # Progress and log section
        progress_group = QGroupBox("Download Progress")
        progress_layout = QVBoxLayout()
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #bdc3c7;
                border-radius: 5px;
                text-align: center;
                height: 25px;
            }
            QProgressBar::chunk {
                background-color: #27ae60;
                border-radius: 4px;
            }
        """)
        progress_layout.addWidget(self.progress_bar)
        
        # Status label
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #7f8c8d; font-weight: bold;")
        progress_layout.addWidget(self.status_label)
        
        # Log output
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumHeight(150)
        self.log_output.setStyleSheet("""
            QTextEdit {
                background-color: #2c3e50;
                color: #ecf0f1;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 11px;
                border-radius: 5px;
                padding: 8px;
            }
        """)
        progress_layout.addWidget(self.log_output)
        
        # Cancel button
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 8px 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        self.cancel_btn.clicked.connect(self._cancel_download)
        progress_layout.addWidget(self.cancel_btn, alignment=Qt.AlignRight)
        
        progress_group.setLayout(progress_layout)
        splitter.addWidget(progress_group)
        
        # Set splitter proportions
        splitter.setSizes([400, 200])
        
        layout.addWidget(splitter, 1)
    
    def _get_default_dest(self) -> str:
        """Get default destination directory"""
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(script_dir, "databases")
    
    def _browse_destination(self):
        """Open folder browser for destination"""
        current = self.dest_path_label.text()
        folder = QFileDialog.getExistingDirectory(
            self, "Select Download Destination", current
        )
        if folder:
            self.dest_path_label.setText(folder)
    
    def _load_manifest(self):
        """Load the database manifest"""
        try:
            manifest = load_database_manifest()
            loader = get_manifest_loader()
            
            # Update manifest info
            age = loader.get_manifest_age()
            age_text = f" (cached {age})" if age else ""
            self.manifest_info.setText(
                f"📋 Catalog version: {manifest.version} | "
                f"Last updated: {manifest.last_updated}{age_text} | "
                f"{len(manifest.databases)} databases available"
            )
            
            # Populate starter packs
            self._clear_layout(self.starter_layout)
            starter_packs = manifest.get_starter_packs()
            if starter_packs:
                for entry in starter_packs:
                    card = self._create_database_card(entry)
                    self.starter_layout.addWidget(card)
            else:
                empty_label = QLabel("No starter packs available")
                empty_label.setStyleSheet("color: #95a5a6; padding: 20px;")
                empty_label.setAlignment(Qt.AlignCenter)
                self.starter_layout.addWidget(empty_label)
            
            self.starter_layout.addStretch()
            
            # Populate full databases
            self._clear_layout(self.full_layout)
            full_dbs = manifest.get_full_databases()
            if full_dbs:
                for entry in full_dbs:
                    card = self._create_database_card(entry)
                    self.full_layout.addWidget(card)
            else:
                empty_label = QLabel("No full databases available")
                empty_label.setStyleSheet("color: #95a5a6; padding: 20px;")
                empty_label.setAlignment(Qt.AlignCenter)
                self.full_layout.addWidget(empty_label)
            
            self.full_layout.addStretch()
            
        except Exception as e:
            self.manifest_info.setText(f"⚠️ Error loading catalog: {str(e)}")
            self.manifest_info.setStyleSheet("""
                QLabel {
                    background-color: #fadbd8;
                    padding: 8px 12px;
                    border-radius: 5px;
                    color: #e74c3c;
                    font-size: 11px;
                }
            """)
    
    def _create_database_card(self, entry: DatabaseEntry) -> DatabaseCard:
        """Create a database card widget"""
        is_installed = self.tracker.is_installed(entry.id)
        installed_version = self.tracker.get_installed_version(entry.id)
        
        card = DatabaseCard(entry, is_installed, installed_version)
        card.download_requested.connect(self._on_download_requested)
        card.install_requested.connect(self._on_install_requested)
        card.open_link_requested.connect(self._on_open_link)
        
        return card
    
    def _clear_layout(self, layout):
        """Clear all widgets from a layout"""
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
    
    def _refresh_manifest(self):
        """Force refresh the manifest from remote"""
        self.manifest_info.setText("🔄 Refreshing catalog...")
        self.manifest_info.setStyleSheet("""
            QLabel {
                background-color: #d5f4e6;
                padding: 8px 12px;
                border-radius: 5px;
                color: #27ae60;
                font-size: 11px;
            }
        """)
        
        # Force refresh
        try:
            from core.database_manifest import get_manifest_loader
            loader = get_manifest_loader()
            loader.load(force_refresh=True)
            self._load_manifest()
        except Exception as e:
            QMessageBox.warning(
                self, "Refresh Failed",
                f"Could not refresh catalog: {str(e)}\n\nUsing cached data."
            )
            self._load_manifest()
    
    def _on_download_requested(self, entry: DatabaseEntry):
        """Handle download request for S3 database"""
        if self.current_worker is not None:
            QMessageBox.warning(
                self, "Download in Progress",
                "A download is already in progress. Please wait or cancel it first."
            )
            return
        
        dest_dir = self.dest_path_label.text()
        
        # Confirm download
        reply = QMessageBox.question(
            self, "Confirm Download",
            f"Download {entry.display_name}?\n\n"
            f"Size: {entry.get_size_display()}\n"
            f"Disk required: {entry.get_disk_required_display()}\n"
            f"Destination: {dest_dir}",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        # Start download
        self.log_output.clear()
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.cancel_btn.setVisible(True)
        self.status_label.setText(f"Downloading {entry.display_name}...")
        
        self.current_worker = DatabaseDownloadWorker(entry, dest_dir)
        self.current_worker.progress.connect(self._on_progress)
        self.current_worker.log.connect(self._on_log)
        self.current_worker.finished.connect(
            lambda path: self._on_download_finished(entry, path)
        )
        self.current_worker.error.connect(self._on_error)
        self.current_worker.start()
    
    def _on_install_requested(self, entry: DatabaseEntry):
        """Handle install request for WSL-based installation"""
        if self.current_worker is not None:
            QMessageBox.warning(
                self, "Operation in Progress",
                "An operation is already in progress. Please wait or cancel it first."
            )
            return
        
        dest_dir = self.dest_path_label.text()
        
        # Warn about large databases
        warning = ""
        if entry.disk_required_gb > 50:
            warning = (
                f"\n\n⚠️ WARNING: This is a large database ({entry.get_disk_required_display()}).\n"
                "The download may take several hours depending on your connection."
            )
        
        reply = QMessageBox.question(
            self, "Confirm Installation",
            f"Install {entry.display_name} via WSL tools?\n\n"
            f"Disk required: {entry.get_disk_required_display()}\n"
            f"Destination: {dest_dir}{warning}",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        # Start installation
        self.log_output.clear()
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.cancel_btn.setVisible(True)
        self.status_label.setText(f"Installing {entry.display_name}...")
        
        self.current_worker = DatabaseInstallWorker(entry, dest_dir)
        self.current_worker.progress.connect(self._on_progress)
        self.current_worker.log.connect(self._on_log)
        self.current_worker.finished.connect(
            lambda path: self._on_download_finished(entry, path)
        )
        self.current_worker.error.connect(self._on_error)
        self.current_worker.start()
    
    def _on_open_link(self, url: str):
        """Open external link in browser"""
        reply = QMessageBox.question(
            self, "Open External Link",
            f"This will open the following link in your browser:\n\n{url}\n\n"
            "You will need to download the database manually from there.",
            QMessageBox.Ok | QMessageBox.Cancel
        )
        
        if reply == QMessageBox.Ok:
            QDesktopServices.openUrl(QUrl(url))
    
    def _on_progress(self, current: int, total: int, status: str):
        """Handle progress updates"""
        if total > 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(current)
        self.status_label.setText(status)
    
    def _on_log(self, message: str):
        """Handle log messages"""
        self.log_output.append(message)
        # Auto-scroll to bottom
        scrollbar = self.log_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def _on_download_finished(self, entry: DatabaseEntry, path: str):
        """Handle successful download/installation"""
        self.progress_bar.setVisible(False)
        self.cancel_btn.setVisible(False)
        self.status_label.setText("✓ Complete!")
        self.status_label.setStyleSheet("color: #27ae60; font-weight: bold;")
        
        # Record in tracker
        self.tracker.add(
            db_id=entry.id,
            display_name=entry.display_name,
            version=entry.version,
            install_path=path,
            tool_formats=entry.tool_formats,
            size_gb=entry.disk_required_gb,
            source_type=entry.distribution_type.value
        )
        
        # Refresh the display
        self._load_manifest()
        
        QMessageBox.information(
            self, "Download Complete",
            f"{entry.display_name} has been installed successfully!\n\n"
            f"Location: {path}"
        )
        
        self.current_worker = None
        self.status_label.setStyleSheet("color: #7f8c8d; font-weight: bold;")
    
    def _on_error(self, error_msg: str):
        """Handle errors"""
        self.progress_bar.setVisible(False)
        self.cancel_btn.setVisible(False)
        self.status_label.setText("✗ Error")
        self.status_label.setStyleSheet("color: #e74c3c; font-weight: bold;")
        
        self.log_output.append(f"\n❌ ERROR: {error_msg}")
        
        QMessageBox.critical(
            self, "Error",
            f"An error occurred:\n\n{error_msg}"
        )
        
        self.current_worker = None
        self.status_label.setStyleSheet("color: #7f8c8d; font-weight: bold;")
    
    def _cancel_download(self):
        """Cancel the current download/installation"""
        if self.current_worker is not None:
            reply = QMessageBox.question(
                self, "Cancel Download",
                "Are you sure you want to cancel?",
                QMessageBox.Yes | QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                self.current_worker.cancel()
                self.progress_bar.setVisible(False)
                self.cancel_btn.setVisible(False)
                self.status_label.setText("Cancelled")
                self.log_output.append("\n⚠️ Operation cancelled by user")
                self.current_worker = None
