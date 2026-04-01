"""QThread workers for the full pySCA package (Tier 2)."""

from __future__ import annotations

import os
import tempfile

from PyQt5.QtCore import QThread, pyqtSignal

from core.pysca_manager import (
    PySCAOutputs,
    PySCAParams,
    export_results,
    install_pysca,
    run_pysca_pipeline,
)


class PySCAInstallWorker(QThread):
    """Background thread that pip-installs pySCA from GitHub."""

    progress = pyqtSignal(str)
    install_finished = pyqtSignal(bool)

    def run(self):
        ok = install_pysca(progress_cb=lambda msg: self.progress.emit(msg))
        self.install_finished.emit(ok)


class PySCARunWorker(QThread):
    """Background thread that runs the full 3-step pySCA pipeline."""

    progress = pyqtSignal(str)
    pipeline_finished = pyqtSignal(object)  # emits PySCAOutputs
    error = pyqtSignal(str)

    def __init__(
        self,
        fasta_path: str,
        params: PySCAParams | None = None,
        output_dir: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._fasta_path = fasta_path
        self._params = params or PySCAParams()
        self._output_dir = output_dir or tempfile.mkdtemp(prefix="pysca_")
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    @property
    def output_dir(self) -> str:
        return self._output_dir

    def run(self):
        try:
            result = run_pysca_pipeline(
                self._fasta_path,
                self._output_dir,
                self._params,
                progress_cb=lambda msg: self.progress.emit(msg),
            )
            if self._cancelled:
                return
            self.pipeline_finished.emit(result)
        except Exception as exc:
            self.error.emit(f"pySCA pipeline error: {exc}")


class PySCAExportWorker(QThread):
    """Background thread that exports .db contents as CSV."""

    progress = pyqtSignal(str)
    export_finished = pyqtSignal(list)  # list of exported file paths
    error = pyqtSignal(str)

    def __init__(self, db_path: str, export_dir: str, parent=None):
        super().__init__(parent)
        self._db_path = db_path
        self._export_dir = export_dir

    def run(self):
        try:
            files = export_results(
                self._db_path,
                self._export_dir,
                progress_cb=lambda msg: self.progress.emit(msg),
            )
            self.export_finished.emit(files)
        except Exception as exc:
            self.error.emit(f"Export failed: {exc}")
