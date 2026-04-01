"""Page for installing and managing external bioinformatics tools (managed runtime)."""

from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QFrame,
    QProgressBar,
    QTextEdit,
    QMessageBox,
    QSplitter,
)
from PyQt5.QtCore import Qt, pyqtSignal

from ui.theme import get_theme
from ui.icons import set_button_icon
from core.config_manager import get_config
from core.tool_install_worker import ToolInstallWorker
from core.tool_registry import TOOLS, current_platform_key, is_managed_install_supported
from core.tool_runtime import get_tool_runtime


class ToolCard(QFrame):
    """Card widget for displaying a managed tool and its current source."""

    install_requested = pyqtSignal(str)
    source_requested = pyqtSignal(str, str)
    refresh_requested = pyqtSignal(str)

    def __init__(self, tool_id: str, parent=None):
        super().__init__(parent)
        self.tool_id = tool_id
        self.spec = TOOLS[tool_id]
        self._init_ui()
        self.refresh()
        get_theme().theme_changed.connect(self._apply_style)

    def _apply_style(self, _theme_name=None):
        t = get_theme()
        self.setStyleSheet(
            f"""
            ToolCard {{
                background-color: {t.get('bg_card')};
                border: 1px solid {t.get('border')};
                border-radius: 8px;
                margin: 4px;
            }}
            ToolCard:hover {{
                border-color: {t.get('accent')};
            }}
        """
        )

    def _init_ui(self):
        self.setFrameShape(QFrame.StyledPanel)
        self._apply_style()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        header = QHBoxLayout()
        self.name_label = QLabel(self.spec.display_name)
        self.name_label.setProperty("class", "heading")
        header.addWidget(self.name_label)
        header.addStretch()
        self.status_badge = QLabel()
        header.addWidget(self.status_badge)
        layout.addLayout(header)

        self.details_label = QLabel()
        self.details_label.setWordWrap(True)
        self.details_label.setProperty("class", "muted")
        layout.addWidget(self.details_label)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)

        self.install_btn = QPushButton("Install")
        self.install_btn.setProperty("class", "success")
        set_button_icon(self.install_btn, "download", 14, "#FFFFFF")
        self.install_btn.clicked.connect(lambda: self.install_requested.emit(self.tool_id))
        button_row.addWidget(self.install_btn)

        self.managed_btn = QPushButton("Use Managed")
        self.managed_btn.setProperty("class", "secondary")
        self.managed_btn.clicked.connect(lambda: self.source_requested.emit(self.tool_id, "managed"))
        button_row.addWidget(self.managed_btn)

        self.system_btn = QPushButton("Use System")
        self.system_btn.setProperty("class", "secondary")
        self.system_btn.clicked.connect(lambda: self.source_requested.emit(self.tool_id, "system"))
        button_row.addWidget(self.system_btn)

        self.refresh_btn = QPushButton("Refresh Status")
        self.refresh_btn.setProperty("class", "secondary")
        set_button_icon(self.refresh_btn, "refresh-cw", 14)
        self.refresh_btn.clicked.connect(lambda: self.refresh_requested.emit(self.tool_id))
        button_row.addWidget(self.refresh_btn)

        button_row.addStretch()
        layout.addLayout(button_row)

    def refresh(self):
        runtime = get_tool_runtime()
        status = runtime.get_tool_status(self.tool_id)
        config = get_config()
        overrides = config.get_tool_source_overrides()
        override = overrides.get(self.tool_id)
        t = get_theme()

        if status.installed:
            badge_text = status.source.upper()
            badge_color = t.get("success") if status.source == "managed" else t.get("accent")
            self.status_badge.setText(badge_text)
            self.status_badge.setStyleSheet(
                f"background-color:{badge_color}; color:#FFFFFF; padding:2px 10px; "
                "border-radius:10px; font-size:10px; font-weight:bold;"
            )
            version_text = status.version or "Version unavailable"
            detail = f"{version_text}\nSource: {status.source}"
            if status.executable_path:
                detail += f"\nExecutable: {status.executable_path}"
            if override:
                detail += f"\nPreferred source override: {override}"
            self.details_label.setText(detail)
        else:
            self.status_badge.setText("MISSING")
            self.status_badge.setStyleSheet(
                f"background-color:{t.get('warning')}; color:#FFFFFF; padding:2px 10px; "
                "border-radius:10px; font-size:10px; font-weight:bold;"
            )
            missing_detail = "Not currently available."
            if current_platform_key() == "windows":
                missing_detail += " Windows uses WSL/system fallback for this tool."
            else:
                missing_detail += " Installable through the managed runtime."
            self.details_label.setText(missing_detail)

        managed_supported = is_managed_install_supported(self.tool_id)
        self.install_btn.setEnabled(managed_supported)
        self.install_btn.setText("Repair Managed Install" if status.source == "managed" else "Install")
        if not managed_supported:
            self.install_btn.setText("Managed install unavailable")
        self.managed_btn.setEnabled(managed_supported)
        self.system_btn.setText("Use WSL/System" if current_platform_key() == "windows" else "Use System")
        self.system_btn.setEnabled(
            status.source in {"system", "configured", "wsl"} or current_platform_key() == "windows"
        )


class ToolsPage(QWidget):
    """Install and manage BLAST+, MMseqs2, blastdbcmd, and Clustal Omega."""

    def __init__(self):
        super().__init__()
        self.current_worker = None
        self._init_ui()
        self._load_tools()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Vertical)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        form = QVBoxLayout(content)
        form.setContentsMargins(28, 24, 28, 16)
        form.setSpacing(16)

        title = QLabel("Tools")
        title.setProperty("class", "title")
        form.addWidget(title)

        self.tools_host = QWidget()
        self.tools_layout = QVBoxLayout(self.tools_host)
        self.tools_layout.setAlignment(Qt.AlignTop)
        form.addWidget(self.tools_host, 1)
        form.addStretch()

        scroll.setWidget(content)
        splitter.addWidget(scroll)

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
        self.cancel_btn.clicked.connect(self._cancel_install)
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

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _load_tools(self):
        self._clear_layout(self.tools_layout)
        intro = QLabel(
            "Install and manage the command-line tools required by search, clustering, "
            "alignment, and database conversion. On macOS and Linux you can use the managed "
            "runtime; on Windows, use system or WSL installations."
        )
        intro.setWordWrap(True)
        intro.setProperty("class", "muted")
        self.tools_layout.addWidget(intro)

        for tool_id in TOOLS:
            card = ToolCard(tool_id)
            card.install_requested.connect(self._on_tool_install_requested)
            card.source_requested.connect(self._on_tool_source_requested)
            card.refresh_requested.connect(self._on_tool_refresh_requested)
            self.tools_layout.addWidget(card)

        self.tools_layout.addStretch()

    def _on_tool_install_requested(self, tool_id: str):
        if self.current_worker is not None:
            QMessageBox.warning(
                self,
                "Operation in Progress",
                "Please wait for the current operation to finish or cancel it first.",
            )
            return

        spec = TOOLS[tool_id]
        if not is_managed_install_supported(tool_id):
            QMessageBox.information(
                self,
                "Managed Install Unavailable",
                f"{spec.display_name} is not available through the managed runtime on this platform.\n\n"
                "Please use the system/WSL-backed installation for now.",
            )
            return

        reply = QMessageBox.question(
            self,
            "Install Tool",
            f"Install or repair {spec.display_name} in the app-managed environment?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self.log_output.clear()
        self.progress_widget.setVisible(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.status_label.setText(f"Installing {spec.display_name}...")

        self.current_worker = ToolInstallWorker([tool_id])
        self.current_worker.progress.connect(self._on_progress)
        self.current_worker.log.connect(self._on_log)
        self.current_worker.install_finished.connect(self._on_tool_install_finished)
        self.current_worker.error.connect(self._on_error)
        self.current_worker.finished.connect(self._on_tool_install_thread_finished)
        self.current_worker.start()

    def _on_tool_source_requested(self, tool_id: str, source: str):
        config = get_config()
        overrides = dict(config.get_tool_source_overrides())
        overrides[tool_id] = "wsl" if source == "system" and current_platform_key() == "windows" else source
        config.set("tool_source_overrides", overrides)
        config.save()
        self._load_tools()

    def _on_tool_refresh_requested(self, _tool_id: str):
        self._load_tools()

    def _on_tool_install_thread_finished(self):
        """QThread.finished: clear reference only after the worker thread has stopped."""
        worker = self.sender()
        if worker is not self.current_worker:
            return
        self.current_worker = None
        self.progress_widget.setVisible(False)
        self.cancel_btn.setEnabled(True)

    def _on_tool_install_finished(self, result: dict):
        self._load_tools()

        tool_names = ", ".join(TOOLS[tid].display_name for tid in result.get("tool_ids", []))
        QMessageBox.information(
            self,
            "Tool Installation Complete",
            f"Managed installation complete for: {tool_names}\n\nEnvironment: {result.get('env_path', '')}",
        )

    def _on_progress(self, current: int, total: int, status: str):
        if total > 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(current)
        self.status_label.setText(status)

    def _on_log(self, message: str):
        self.log_output.append(message)
        scrollbar = self.log_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _on_error(self, error_msg: str):
        t = get_theme()
        self.status_label.setText("Error")
        self.status_label.setStyleSheet(f"color: {t.get('error')}; font-weight: bold;")
        self.log_output.append(f"\nERROR: {error_msg}")
        QMessageBox.critical(self, "Error", f"An error occurred:\n\n{error_msg}")
        self._load_tools()
        self.status_label.setStyleSheet("")

    def _cancel_install(self):
        if self.current_worker is not None:
            reply = QMessageBox.question(
                self,
                "Cancel",
                "Cancel the current tool installation?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                self.current_worker.cancel()
                self.status_label.setText("Cancelling installation...")
                self.cancel_btn.setEnabled(False)
