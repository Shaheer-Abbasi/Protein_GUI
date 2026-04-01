"""Background worker for installing app-managed tools."""

from PyQt5.QtCore import QThread, pyqtSignal

from core.tool_runtime import ToolRuntimeError, get_tool_runtime


class ToolInstallWorker(QThread):
    """Install one or more tools via the managed runtime without blocking the UI."""

    progress = pyqtSignal(int, int, str)
    log = pyqtSignal(str)
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, tool_ids):
        super().__init__()
        self.tool_ids = list(tool_ids)
        self._cancelled = False

    def cancel(self):
        """Request cancellation of the in-flight install."""

        self._cancelled = True
        get_tool_runtime().manager.cancel()

    def run(self):
        runtime = get_tool_runtime()

        def progress_cb(current, total, status):
            self.progress.emit(current, total, status)

        def log_cb(message):
            self.log.emit(message)

        try:
            env_path = runtime.install_tools(
                self.tool_ids,
                progress_cb=progress_cb,
                log_cb=log_cb,
                cancel_check=lambda: self._cancelled,
            )
            self.finished.emit(
                {
                    "tool_ids": self.tool_ids,
                    "env_path": env_path,
                    "cancelled": self._cancelled,
                }
            )
        except ToolRuntimeError as exc:
            self.error.emit(str(exc))
        except Exception as exc:
            self.error.emit(f"Tool installation failed: {exc}")
