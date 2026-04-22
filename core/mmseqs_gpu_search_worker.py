"""Worker thread for GPU-accelerated MMseqs2 ``easy-search`` (protein or nucleotide)."""

import os
import shutil
import subprocess
import tempfile

from PyQt5.QtCore import QThread, pyqtSignal

from core.tool_runtime import ToolRuntimeError, get_tool_runtime
from core.wsl_utils import WSLError
from utils.results_parser import MMSeqsResultsParser, SearchHit


class MMseqsGPUSearchWorker(QThread):
    """Single-step ``mmseqs easy-search`` with optional ``--gpu 1``."""

    finished = pyqtSignal(str, list)  # HTML, list[SearchHit]
    error = pyqtSignal(str)

    def __init__(
        self,
        sequence: str,
        database_path: str,
        search_type: str = "protein",
        use_gpu: bool = False,
        sensitivity: str = "sensitive",
        max_seqs: int = 300,
    ):
        super().__init__()
        self.sequence = sequence
        self.database_path = database_path
        self.search_type = search_type  # "protein" or "nucleotide"
        self.use_gpu = use_gpu
        self.sensitivity = sensitivity
        self.max_seqs = max_seqs

    def run(self):
        temp_dir = None
        try:
            temp_dir = tempfile.mkdtemp(prefix="mmseqs_gpu_")
            runtime = get_tool_runtime()
            resolution = runtime.resolve_tool("mmseqs")
            if not resolution.executable:
                self.error.emit(
                    "MMseqs2 is not available. Install it from the Tools tab or via conda."
                )
                return

            query_path = os.path.join(temp_dir, "query.fasta")
            output_path = os.path.join(temp_dir, "results.m8")
            tmp_folder = os.path.join(temp_dir, "tmp")
            os.makedirs(tmp_folder, exist_ok=True)

            with open(query_path, "w") as f:
                f.write(f">query\n{self.sequence}\n")

            query_tool = runtime.prepare_path(resolution, query_path)
            db_tool = runtime.prepare_path(resolution, self.database_path)
            output_tool = runtime.prepare_path(resolution, output_path)
            tmp_tool = runtime.prepare_path(resolution, tmp_folder)

            search_type_val = "3" if self.search_type == "nucleotide" else "1"

            cmd = [
                "easy-search",
                query_tool,
                db_tool,
                output_tool,
                tmp_tool,
                "--search-type", search_type_val,
                "-s", self._sensitivity_value(),
                "--max-seqs", str(self.max_seqs),
                "--format-output",
                "query,target,theader,pident,alnlen,mismatch,gapopen,"
                "qstart,qend,tstart,tend,evalue,bits",
            ]

            if self.use_gpu:
                cmd.extend(["--gpu", "1"])

            runtime.run_resolved(resolution, cmd, check=True, timeout=600)

            hits = self._parse_results(output_path)
            html = self._format_html(hits)
            self.finished.emit(html, hits)

        except subprocess.CalledProcessError as exc:
            stderr = getattr(exc, "stderr", "") or str(exc)
            self.error.emit(f"MMseqs2 GPU search error: {stderr}")
        except (ToolRuntimeError, WSLError) as exc:
            self.error.emit(f"Execution error: {exc}")
        except Exception as exc:
            import traceback
            self.error.emit(f"Error: {exc}\n\n{traceback.format_exc()}")
        finally:
            if temp_dir:
                shutil.rmtree(temp_dir, ignore_errors=True)

    def _sensitivity_value(self):
        mapping = {
            "fast": "4",
            "sensitive": "5.7",
            "more-sensitive": "7",
            "very-sensitive": "8.5",
        }
        return mapping.get(self.sensitivity, "5.7")

    @staticmethod
    def _parse_results(m8_path: str):
        hits: list[SearchHit] = []
        if not os.path.exists(m8_path) or os.path.getsize(m8_path) == 0:
            return hits
        with open(m8_path) as f:
            for rank, line in enumerate(f, 1):
                if line.startswith("#"):
                    continue
                parts = line.strip().split("\t")
                if len(parts) < 13:
                    continue
                hits.append(SearchHit(
                    rank=rank,
                    accession=parts[1],
                    description=parts[2],
                    identity_percent=float(parts[3]),
                    alignment_length=int(parts[4]),
                    evalue=float(parts[11]),
                    score=float(parts[12]),
                ))
        return hits

    def _format_html(self, hits):
        kind = "NUCLEOTIDE" if self.search_type == "nucleotide" else "PROTEIN"
        gpu_tag = " (GPU)" if self.use_gpu else ""
        header_bg = "#1e8449" if self.search_type == "nucleotide" else "#8e44ad"

        html = [
            '<html><head><style>',
            'body { font-family: "Courier New", monospace; font-size: 12px; }',
            f'.header {{ background-color: {header_bg}; color: white; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}',
            '.header h1 { margin: 0; font-size: 20px; }',
            '.hit { background-color: #ffffff; border: 1px solid #bdc3c7; padding: 15px; margin-bottom: 15px; border-radius: 5px; }',
            '.hit-title { font-size: 14px; font-weight: bold; color: #2c3e50; margin-bottom: 10px; }',
            '.stats { margin: 10px 0; }',
            '.stat-row { margin: 5px 0; }',
            '.stat-label { font-weight: bold; color: #7f8c8d; }',
            '.no-results { color: #95a5a6; font-style: italic; text-align: center; padding: 30px; }',
            '</style></head><body>',
            f'<div class="header"><h1>MMSEQS2{gpu_tag} {kind} SEARCH RESULTS</h1></div>',
        ]

        if hits:
            shown = min(len(hits), 20)
            extra = f' <span style="color:#7f8c8d;">(showing top {shown})</span>' if len(hits) > 20 else ""
            html.append(
                f'<div style="background-color:#d5f4e6;padding:10px;border-radius:5px;margin-bottom:15px;">'
                f'<b>Found {len(hits)} alignment(s)</b>{extra}</div>'
            )
            unit = "nucleotides" if self.search_type == "nucleotide" else "amino acids"
            for h in hits[:20]:
                ec = _evalue_color(h.evalue)
                ic = _identity_color(h.identity_percent)
                html.append(f'<div class="hit">')
                html.append(f'<div class="hit-title">#{h.rank}. {h.description}</div>')
                html.append(f'<span style="color:#7f8c8d;">Accession: {h.accession}</span>')
                html.append('<div class="stats">')
                html.append(f'<div class="stat-row"><span class="stat-label">Identity:</span> <b style="color:{ic};">{h.identity_percent:.1f}%</b></div>')
                html.append(f'<div class="stat-row"><span class="stat-label">E-value:</span> <b style="color:{ec};">{h.evalue:.2e}</b></div>')
                html.append(f'<div class="stat-row"><span class="stat-label">Bit Score:</span> <b>{h.score:.1f}</b></div>')
                html.append(f'<div class="stat-row"><span class="stat-label">Alignment Length:</span> {h.alignment_length} {unit}</div>')
                html.append('</div></div>')
        else:
            html.append('<div class="no-results">No significant alignments found.</div>')

        html.append('</body></html>')
        return "".join(html)


def _evalue_color(ev):
    if ev < 1e-100:
        return "#27ae60"
    if ev < 1e-50:
        return "#2ecc71"
    if ev < 1e-10:
        return "#f39c12"
    if ev < 1e-5:
        return "#e67e22"
    return "#e74c3c"


def _identity_color(pct):
    if pct >= 90:
        return "#27ae60"
    if pct >= 70:
        return "#2ecc71"
    if pct >= 50:
        return "#f39c12"
    if pct >= 30:
        return "#e67e22"
    return "#e74c3c"
