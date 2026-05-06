"""Background thread for phylogenetic identity + hierarchical clustering."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal

from core.phylo_engine import LINKAGE_METHODS, run_phylo_analysis
from utils.fasta_parser import FastaParseError, FastaParser


@dataclass
class PhyloResult:
    """Result of a successful phylo run (picklable / emitted to Qt slot)."""

    labels: List[str]
    headers: List[str]
    sequences: List[str]
    identity: np.ndarray
    distance: np.ndarray
    Z: np.ndarray
    n: int
    method: str
    elapsed_s: float


class PhyloWorker(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(object)  # PhyloResult
    error = pyqtSignal(str)

    def __init__(
        self,
        fasta_text: str,
        method: str = "average",
        parent=None,
    ):
        super().__init__(parent)
        self._fasta_text = fasta_text
        self._method = method if method in LINKAGE_METHODS else "average"
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        import time

        t0 = time.perf_counter()
        try:
            self.progress.emit("Parsing FASTA...")
            parser = FastaParser()
            try:
                seqs = parser.parse_string(self._fasta_text)
            except FastaParseError as e:
                self.error.emit(f"FASTA parse error: {e}")
                return

            if self._cancelled:
                return

            self.progress.emit("Computing pairwise identity and linkage...")
            msa, ident, dist, z = run_phylo_analysis(seqs, method=self._method)

            if self._cancelled:
                return

            elapsed = time.perf_counter() - t0
            res = PhyloResult(
                labels=list(msa.labels),
                headers=list(msa.headers),
                sequences=list(msa.sequences),
                identity=ident,
                distance=dist,
                Z=z,
                n=len(msa.labels),
                method=self._method,
                elapsed_s=elapsed,
            )
            self.finished.emit(res)
        except ValueError as e:
            self.error.emit(str(e))
        except Exception as e:  # pragma: no cover
            self.error.emit(f"Phylogenetic analysis failed: {e}")
