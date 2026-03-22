"""
Database Downloads page for managing protein database installations.

Provides a UI for:
- Viewing available databases (starter packs and full databases)
- Downloading databases from S3
- Installing databases via system tools
- Opening external links for large databases
- Tracking installed databases
"""

import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QGroupBox, QProgressBar,
    QTextEdit, QFileDialog, QMessageBox, QSplitter, QSizePolicy,
    QTabWidget, QLineEdit
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtCore import QUrl

from ui.theme import get_theme
from ui.icons import feather_icon, set_button_icon
from core.database_manifest import (
    load_database_manifest, DatabaseEntry, DistributionType,
    get_manifest_loader
)
from core.installed_databases import get_installed_databases_tracker
from core.database_download_worker import DatabaseDownloadWorker
from core.database_install_worker import DatabaseInstallWorker


class DatabaseCard(QFrame):
    """Card widget for displaying a single database entry."""

    download_requested = pyqtSignal(object)
    install_requested = pyqtSignal(object)
    open_link_requested = pyqtSignal(str)

    def __init__(self, entry: DatabaseEntry, is_installed: bool = False,
                 installed_version: str = None, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.is_installed = is_installed
        self.installed_version = installed_version
        self._icon_labels = []
        self._init_ui()
        get_theme().theme_changed.connect(self._apply_card_style)

    def _apply_card_style(self, _theme_name=None):
        t = get_theme()
        self.setStyleSheet(f"""
            DatabaseCard {{
                background-color: {t.get('bg_card')};
                border: 1px solid {t.get('border')};
                border-radius: 8px;
                margin: 4px;
            }}
            DatabaseCard:hover {{
                border-color: {t.get('accent')};
            }}
        """)
        for icon_lbl, icon_name in self._icon_labels:
            icon_lbl.setPixmap(
                feather_icon(icon_name, 12, t.get("text_muted")).pixmap(12, 12)
            )

    def _init_ui(self):
        t = get_theme()
        self.setFrameShape(QFrame.StyledPanel)
        self._apply_card_style()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        # Header row: Name + badges
        header = QHBoxLayout()

        name_label = QLabel(self.entry.display_name)
        name_label.setProperty("class", "heading")
        header.addWidget(name_label)
        header.addStretch()

        for tool in self.entry.tool_formats:
            badge = QLabel(tool.upper())
            bg = t.get('accent') if tool == "blast" else "#9B59B6"
            badge.setStyleSheet(f"""
                QLabel {{
                    background-color: {bg};
                    color: #FFFFFF;
                    padding: 2px 10px;
                    border-radius: 10px;
                    font-size: 10px;
                    font-weight: bold;
                }}
            """)
            header.addWidget(badge)

        if self.is_installed:
            installed_badge = QLabel("Installed")
            installed_badge.setStyleSheet(f"""
                QLabel {{
                    background-color: {t.get('success')};
                    color: #FFFFFF;
                    padding: 2px 10px;
                    border-radius: 10px;
                    font-size: 10px;
                    font-weight: bold;
                }}
            """)
            header.addWidget(installed_badge)

        layout.addLayout(header)

        # Description
        desc = QLabel(self.entry.description)
        desc.setWordWrap(True)
        desc.setProperty("class", "muted")
        layout.addWidget(desc)

        # Info row
        info_row = QHBoxLayout()
        info_row.setSpacing(20)

        info_items = [
            ("package", self.entry.get_size_display()),
            ("hard-drive", f"Requires: {self.entry.get_disk_required_display()}"),
            ("calendar", self.entry.version),
        ]

        for icon_name, text in info_items:
            pair = QHBoxLayout()
            pair.setSpacing(4)
            icon_w = QLabel()
            icon_w.setPixmap(feather_icon(icon_name, 12, t.get("text_muted")).pixmap(12, 12))
            icon_w.setFixedSize(14, 14)
            self._icon_labels.append((icon_w, icon_name))
            lbl = QLabel(text)
            lbl.setProperty("class", "muted")
            pair.addWidget(icon_w)
            pair.addWidget(lbl)
            info_row.addLayout(pair)

        info_row.addStretch()
        layout.addLayout(info_row)

        # Action buttons
        action_row = QHBoxLayout()
        action_row.setSpacing(10)

        if self.entry.distribution_type == DistributionType.S3:
            dl_btn = QPushButton("Download")
            dl_btn.setProperty("class", "success")
            set_button_icon(dl_btn, "download", 14, "#FFFFFF")
            dl_btn.clicked.connect(lambda: self.download_requested.emit(self.entry))
            action_row.addWidget(dl_btn)

        elif self.entry.distribution_type == DistributionType.INSTALLER:
            inst_btn = QPushButton("Install via Tool")
            set_button_icon(inst_btn, "tool", 14)
            inst_btn.clicked.connect(lambda: self.install_requested.emit(self.entry))
            action_row.addWidget(inst_btn)

        elif self.entry.distribution_type == DistributionType.EXTERNAL:
            link_btn = QPushButton("Open External Link")
            link_btn.setProperty("class", "secondary")
            set_button_icon(link_btn, "external-link", 14)
            link_btn.clicked.connect(
                lambda: self.open_link_requested.emit(self.entry.distribution.url)
            )
            action_row.addWidget(link_btn)

            if hasattr(self.entry.distribution, 'notes') and self.entry.distribution.notes:
                notes = QLabel(self.entry.distribution.notes)
                notes.setStyleSheet(f"color: {t.get('warning')}; font-size: 10px;")
                notes.setWordWrap(True)
                layout.addWidget(notes)

        action_row.addStretch()
        layout.addLayout(action_row)


class DatabaseDownloadsPage(QWidget):
    """Main page for database downloads and management."""

    back_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.current_worker = None
        self.tracker = get_installed_databases_tracker()
        self._init_ui()
        self._load_manifest()

    def _init_ui(self):
        t = get_theme()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Vertical)

        # ── Top: header + content in scroll area ─────────────────
        input_scroll = QScrollArea()
        input_scroll.setWidgetResizable(True)
        input_scroll.setFrameShape(QFrame.NoFrame)

        input_widget = QWidget()
        form = QVBoxLayout(input_widget)
        form.setContentsMargins(28, 24, 28, 16)
        form.setSpacing(16)

        # Title row with refresh button
        title_row = QHBoxLayout()
        title = QLabel("Database Downloads")
        title.setProperty("class", "title")
        title_row.addWidget(title)
        title_row.addStretch()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setProperty("class", "secondary")
        set_button_icon(refresh_btn, "refresh-cw", 14)
        refresh_btn.clicked.connect(self._refresh_manifest)
        title_row.addWidget(refresh_btn)
        form.addLayout(title_row)

        # Manifest info
        self.manifest_info = QLabel("Loading database catalog...")
        self.manifest_info.setProperty("class", "muted")
        form.addWidget(self.manifest_info)

        # Destination folder
        dest_group = QGroupBox("Installation Settings")
        dest_layout = QHBoxLayout()

        dest_layout.addWidget(QLabel("Download to:"))
        self.dest_path_label = QLineEdit(self._get_default_dest())
        self.dest_path_label.setReadOnly(True)
        dest_layout.addWidget(self.dest_path_label, 1)

        browse_btn = QPushButton("Browse")
        set_button_icon(browse_btn, "folder", 14, "#FFFFFF")
        browse_btn.clicked.connect(self._browse_destination)
        dest_layout.addWidget(browse_btn)

        dest_group.setLayout(dest_layout)
        form.addWidget(dest_group)

        # Tabs for starter packs vs full databases
        self.tabs = QTabWidget()

        self.starter_scroll = QScrollArea()
        self.starter_scroll.setWidgetResizable(True)
        self.starter_scroll.setFrameShape(QFrame.NoFrame)
        self.starter_content = QWidget()
        self.starter_layout = QVBoxLayout(self.starter_content)
        self.starter_layout.setAlignment(Qt.AlignTop)
        self.starter_scroll.setWidget(self.starter_content)

        self.full_scroll = QScrollArea()
        self.full_scroll.setWidgetResizable(True)
        self.full_scroll.setFrameShape(QFrame.NoFrame)
        self.full_content = QWidget()
        self.full_layout = QVBoxLayout(self.full_content)
        self.full_layout.setAlignment(Qt.AlignTop)
        self.full_scroll.setWidget(self.full_content)

        self.tabs.addTab(self.starter_scroll, feather_icon("zap", 16), "Quick Start (Recommended)")
        self.tabs.addTab(self.full_scroll, feather_icon("database", 16), "Full Databases (Large)")

        form.addWidget(self.tabs, 1)

        input_scroll.setWidget(input_widget)
        splitter.addWidget(input_scroll)

        # ── Bottom: progress / log section (initially hidden) ────
        self.progress_widget = QWidget()
        self.progress_widget.setVisible(False)
        pw_layout = QVBoxLayout(self.progress_widget)
        pw_layout.setContentsMargins(28, 12, 28, 12)
        pw_layout.setSpacing(8)

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        pw_layout.addWidget(self.progress_bar)

        status_row = QHBoxLayout()
        self.status_label = QLabel("Ready")
        self.status_label.setProperty("class", "muted")
        status_row.addWidget(self.status_label)
        status_row.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setProperty("class", "danger")
        set_button_icon(self.cancel_btn, "x", 14, "#FFFFFF")
        self.cancel_btn.clicked.connect(self._cancel_download)
        status_row.addWidget(self.cancel_btn)
        pw_layout.addLayout(status_row)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setProperty("class", "mono")
        self.log_output.setMaximumHeight(140)
        pw_layout.addWidget(self.log_output)

        splitter.addWidget(self.progress_widget)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([500, 180])

        root.addWidget(splitter)

    # ── Helpers ──────────────────────────────────────────────────
    def _get_default_dest(self) -> str:
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(script_dir, "databases")

    def _browse_destination(self):
        current = self.dest_path_label.text()
        folder = QFileDialog.getExistingDirectory(self, "Select Download Destination", current)
        if folder:
            self.dest_path_label.setText(folder)

    # ── Manifest loading ─────────────────────────────────────────
    def _load_manifest(self):
        t = get_theme()
        try:
            manifest = load_database_manifest()
            loader = get_manifest_loader()

            age = loader.get_manifest_age()
            age_text = f" (cached {age})" if age else ""
            self.manifest_info.setText(
                f"Catalog version: {manifest.version}  |  "
                f"Last updated: {manifest.last_updated}{age_text}  |  "
                f"{len(manifest.databases)} databases available"
            )

            self._clear_layout(self.starter_layout)
            starter_packs = manifest.get_starter_packs()
            if starter_packs:
                for entry in starter_packs:
                    self.starter_layout.addWidget(self._create_database_card(entry))
            else:
                empty = QLabel("No starter packs available")
                empty.setAlignment(Qt.AlignCenter)
                empty.setProperty("class", "muted")
                self.starter_layout.addWidget(empty)
            self.starter_layout.addStretch()

            self._clear_layout(self.full_layout)
            full_dbs = manifest.get_full_databases()
            if full_dbs:
                for entry in full_dbs:
                    self.full_layout.addWidget(self._create_database_card(entry))
            else:
                empty = QLabel("No full databases available")
                empty.setAlignment(Qt.AlignCenter)
                empty.setProperty("class", "muted")
                self.full_layout.addWidget(empty)
            self.full_layout.addStretch()

        except Exception as e:
            self.manifest_info.setText(f"Error loading catalog: {str(e)}")
            self.manifest_info.setStyleSheet(f"color: {t.get('error')};")

    def _create_database_card(self, entry: DatabaseEntry) -> DatabaseCard:
        is_installed = self.tracker.is_installed(entry.id)
        installed_version = self.tracker.get_installed_version(entry.id)
        card = DatabaseCard(entry, is_installed, installed_version)
        card.download_requested.connect(self._on_download_requested)
        card.install_requested.connect(self._on_install_requested)
        card.open_link_requested.connect(self._on_open_link)
        return card

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _refresh_manifest(self):
        t = get_theme()
        self.manifest_info.setText("Refreshing catalog...")
        self.manifest_info.setStyleSheet(f"color: {t.get('success')};")
        try:
            loader = get_manifest_loader()
            loader.load(force_refresh=True)
            self._load_manifest()
        except Exception as e:
            QMessageBox.warning(
                self, "Refresh Failed",
                f"Could not refresh catalog: {str(e)}\n\nUsing cached data."
            )
            self._load_manifest()
        self.manifest_info.setStyleSheet("")

    # ── Download / Install handlers ──────────────────────────────
    def _on_download_requested(self, entry: DatabaseEntry):
        if self.current_worker is not None:
            QMessageBox.warning(
                self, "Download in Progress",
                "A download is already in progress. Please wait or cancel it first."
            )
            return

        dest_dir = self.dest_path_label.text()
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

        self.log_output.clear()
        self.progress_widget.setVisible(True)
        self.progress_bar.setValue(0)
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
        if self.current_worker is not None:
            QMessageBox.warning(
                self, "Operation in Progress",
                "An operation is already in progress. Please wait or cancel it first."
            )
            return

        dest_dir = self.dest_path_label.text()
        warning = ""
        if entry.disk_required_gb > 50:
            warning = (
                f"\n\nWARNING: This is a large database ({entry.get_disk_required_display()}).\n"
                "The download may take several hours depending on your connection."
            )

        reply = QMessageBox.question(
            self, "Confirm Installation",
            f"Install {entry.display_name}?\n\n"
            f"Disk required: {entry.get_disk_required_display()}\n"
            f"Destination: {dest_dir}{warning}",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        self.log_output.clear()
        self.progress_widget.setVisible(True)
        self.progress_bar.setRange(0, 0)
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
        reply = QMessageBox.question(
            self, "Open External Link",
            f"This will open the following link in your browser:\n\n{url}\n\n"
            "You will need to download the database manually from there.",
            QMessageBox.Ok | QMessageBox.Cancel
        )
        if reply == QMessageBox.Ok:
            QDesktopServices.openUrl(QUrl(url))

    def _on_progress(self, current: int, total: int, status: str):
        if total > 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(current)
        self.status_label.setText(status)

    def _on_log(self, message: str):
        self.log_output.append(message)
        scrollbar = self.log_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _on_download_finished(self, entry: DatabaseEntry, path: str):
        self.progress_widget.setVisible(False)

        self.tracker.add(
            db_id=entry.id,
            display_name=entry.display_name,
            version=entry.version,
            install_path=path,
            tool_formats=entry.tool_formats,
            size_gb=entry.disk_required_gb,
            source_type=entry.distribution_type.value
        )

        self._load_manifest()

        QMessageBox.information(
            self, "Download Complete",
            f"{entry.display_name} has been installed successfully!\n\n"
            f"Location: {path}"
        )

        self.current_worker = None

    def _on_error(self, error_msg: str):
        t = get_theme()
        self.status_label.setText("Error")
        self.status_label.setStyleSheet(f"color: {t.get('error')}; font-weight: bold;")

        self.log_output.append(f"\nERROR: {error_msg}")

        QMessageBox.critical(self, "Error", f"An error occurred:\n\n{error_msg}")

        self.current_worker = None
        self.status_label.setStyleSheet("")

    def _cancel_download(self):
        if self.current_worker is not None:
            reply = QMessageBox.question(
                self, "Cancel Download",
                "Are you sure you want to cancel?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.current_worker.cancel()
                self.progress_widget.setVisible(False)
                self.current_worker = None
