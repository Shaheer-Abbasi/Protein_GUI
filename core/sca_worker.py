"""QThread worker for the built-in SCA analysis (Tier 1)."""

from __future__ import annotations

from PyQt5.QtCore import QThread, pyqtSignal

from core.sca_engine import SCAResults, run_full_sca
from utils.fasta_parser import FastaParser, FastaParseError


class SCAWorker(QThread):
    """Run built-in SCA in a background thread."""

    progress = pyqtSignal(int, str)
    finished = pyqtSignal(object)   # emits SCAResults
    error = pyqtSignal(str)

    MIN_SEQUENCES = 30

    def __init__(self, fasta_text: str, parent=None):
        super().__init__(parent)
        self._fasta_text = fasta_text
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            self.progress.emit(0, "Parsing alignment...")
            parser = FastaParser()
            try:
                seqs = parser.parse_string(self._fasta_text)
            except FastaParseError as e:
                self.error.emit(f"FASTA parse error: {e}")
                return

            if len(seqs) < self.MIN_SEQUENCES:
                self.error.emit(
                    f"SCA requires at least {self.MIN_SEQUENCES} sequences "
                    f"(got {len(seqs)})."
                )
                return

            labels = [s.id for s in seqs]
            sequences = [s.sequence.replace(" ", "").upper() for s in seqs]

            # Pad to common width
            width = max(len(s) for s in sequences)
            sequences = [s.ljust(width, "-") for s in sequences]

            # Validate equal length
            lengths = set(len(s) for s in sequences)
            if len(lengths) != 1:
                self.error.emit("Sequences are not aligned to equal length.")
                return

            if self._cancelled:
                return

            def _prog(pct, msg):
                if not self._cancelled:
                    self.progress.emit(pct, msg)

            results = run_full_sca(sequences, labels, progress_cb=_prog)

            if not self._cancelled:
                self.finished.emit(results)

        except Exception as e:
            self.error.emit(f"SCA computation failed: {e}")
