"""Worker thread for running DIAMOND blastp searches.

Accepts a BLAST database path prefix (e.g. /path/to/swissprot).
If a .dmnd database does not already exist alongside the BLAST files,
the worker auto-converts using blastdbcmd + diamond makedb before
running the search.  The .dmnd file is cached for future runs.
"""

import os
import shutil
import subprocess
import tempfile

from PyQt5.QtCore import QThread, pyqtSignal

from core.tool_runtime import ToolRuntimeError, get_tool_runtime
from core.wsl_utils import WSLError
from utils.results_parser import SearchHit


class DiamondWorker(QThread):
    """QThread worker that runs ``diamond blastp`` against a local database."""

    finished = pyqtSignal(str, list)  # HTML, list[SearchHit]
    error = pyqtSignal(str)

    DEFAULT_PARAMS = {
        "evalue": 10,
        "max_target_seqs": 100,
        "matrix": "BLOSUM62",
        "threads": 0,  # 0 = auto
    }

    def __init__(self, sequence: str, database_path: str, advanced_params=None):
        super().__init__()
        self.sequence = sequence
        self.database_path = database_path  # BLAST db prefix, e.g. .../swissprot

        self.params = self.DEFAULT_PARAMS.copy()
        if advanced_params:
            self.params.update(advanced_params)

    # ------------------------------------------------------------------

    def run(self):
        temp_dir = None
        try:
            temp_dir = tempfile.mkdtemp(prefix="diamond_")
            runtime = get_tool_runtime()
            resolution = runtime.resolve_tool("diamond")
            if not resolution.executable:
                self.error.emit(
                    "DIAMOND is not available. Install it via conda:\n"
                    "  conda install -c bioconda diamond"
                )
                return

            dmnd_path = self._ensure_dmnd_db(runtime, resolution, temp_dir)
            if dmnd_path is None:
                return

            query_path = os.path.join(temp_dir, "query.fasta")
            output_path = os.path.join(temp_dir, "results.tsv")
            with open(query_path, "w") as f:
                f.write(f">query\n{self.sequence}\n")

            query_tool = runtime.prepare_path(resolution, query_path)
            output_tool = runtime.prepare_path(resolution, output_path)
            db_tool = runtime.prepare_path(resolution, dmnd_path)

            threads = int(self.params.get("threads", 0)) or max(1, (os.cpu_count() or 4))

            cmd = [
                "blastp",
                "-q", query_tool,
                "-d", db_tool,
                "-o", output_tool,
                "--outfmt", "6",
                "qseqid", "sseqid", "stitle",
                "pident", "length", "mismatch", "gapopen",
                "qstart", "qend", "sstart", "send",
                "evalue", "bitscore",
                "--evalue", str(self.params["evalue"]),
                "--max-target-seqs", str(self.params["max_target_seqs"]),
                "--matrix", self.params["matrix"],
                "--threads", str(threads),
            ]

            runtime.run_resolved(resolution, cmd, check=True, timeout=600)

            hits = self._parse_results(output_path)
            html = self._format_html(hits)
            self.finished.emit(html, hits)

        except subprocess.CalledProcessError as exc:
            stderr = getattr(exc, "stderr", "") or str(exc)
            self.error.emit(f"DIAMOND error: {stderr}")
        except (ToolRuntimeError, WSLError) as exc:
            self.error.emit(f"Execution error: {exc}")
        except Exception as exc:
            self.error.emit(f"Error: {exc}")
        finally:
            if temp_dir:
                shutil.rmtree(temp_dir, ignore_errors=True)

    # ------------------------------------------------------------------

    def _ensure_dmnd_db(self, runtime, diamond_resolution, temp_dir: str):
        """Return the path to a .dmnd database, building one if necessary.

        Looks for ``<database_path>.dmnd`` next to the BLAST files.
        If missing, extracts FASTA via ``blastdbcmd`` then builds the
        DIAMOND database with ``diamond makedb``.
        """
        dmnd_path = self.database_path + ".dmnd"
        if os.path.isfile(dmnd_path):
            return dmnd_path

        blast_phr = self.database_path + ".phr"
        blast_phr_multi = self.database_path + ".00.phr"
        if not os.path.isfile(blast_phr) and not os.path.isfile(blast_phr_multi):
            self.error.emit(
                f"No DIAMOND (.dmnd) or BLAST (.phr) database found at:\n"
                f"{self.database_path}\n\n"
                "Please install the database via the Database Downloads page."
            )
            return None

        try:
            blast_resolution = runtime.resolve_tool("blastp")
        except Exception:
            blast_resolution = None

        blastdbcmd_exe = shutil.which("blastdbcmd")
        if blast_resolution and blast_resolution.executable:
            blastdbcmd_exe = os.path.join(
                os.path.dirname(blast_resolution.executable), "blastdbcmd"
            )
            if not os.path.isfile(blastdbcmd_exe):
                blastdbcmd_exe = shutil.which("blastdbcmd")

        if not blastdbcmd_exe:
            self.error.emit(
                "blastdbcmd is required to build a DIAMOND database from BLAST files.\n"
                "Install BLAST+ (conda install -c bioconda blast) and try again."
            )
            return None

        fasta_path = os.path.join(temp_dir, "sequences.fasta")
        db_path_tool = runtime.prepare_path(diamond_resolution, self.database_path)

        extract_cmd = [
            blastdbcmd_exe, "-entry", "all",
            "-db", db_path_tool,
            "-out", fasta_path,
        ]
        subprocess.run(extract_cmd, check=True, capture_output=True, text=True, timeout=600)

        if not os.path.isfile(fasta_path) or os.path.getsize(fasta_path) == 0:
            self.error.emit("blastdbcmd produced no output. Is the BLAST database valid?")
            return None

        fasta_tool = runtime.prepare_path(diamond_resolution, fasta_path)
        dmnd_tool = runtime.prepare_path(diamond_resolution, dmnd_path)

        makedb_cmd = [
            "makedb",
            "--in", fasta_tool,
            "-d", dmnd_tool,
        ]
        runtime.run_resolved(diamond_resolution, makedb_cmd, check=True, timeout=600)

        if os.path.isfile(dmnd_path):
            return dmnd_path

        self.error.emit("diamond makedb completed but .dmnd file was not created.")
        return None

    # ------------------------------------------------------------------

    @staticmethod
    def _parse_results(tsv_path: str):
        hits: list[SearchHit] = []
        if not os.path.exists(tsv_path):
            return hits
        with open(tsv_path) as f:
            for rank, line in enumerate(f, 1):
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
        html = [
            '<html><head><style>',
            'body { font-family: "Courier New", monospace; font-size: 12px; }',
            '.header { background-color: #2e86c1; color: white; padding: 15px; border-radius: 5px; margin-bottom: 20px; }',
            '.header h1 { margin: 0; font-size: 20px; }',
            '.hit { background-color: #ffffff; border: 1px solid #bdc3c7; padding: 15px; margin-bottom: 15px; border-radius: 5px; }',
            '.hit-title { font-size: 14px; font-weight: bold; color: #2c3e50; margin-bottom: 10px; }',
            '.stats { margin: 10px 0; }',
            '.stat-row { margin: 5px 0; }',
            '.stat-label { font-weight: bold; color: #7f8c8d; }',
            '.no-results { color: #95a5a6; font-style: italic; text-align: center; padding: 30px; }',
            '</style></head><body>',
            '<div class="header"><h1>DIAMOND BLASTP RESULTS</h1></div>',
        ]

        if hits:
            html.append(
                f'<div style="background-color:#d5f4e6;padding:10px;border-radius:5px;margin-bottom:15px;">'
                f'<b>Found {len(hits)} alignment(s)</b></div>'
            )
            for h in hits[:100]:
                ec = _evalue_color(h.evalue)
                ic = _identity_color(h.identity_percent)
                html.append(f'<div class="hit">')
                html.append(f'<div class="hit-title">#{h.rank}. {h.description}</div>')
                html.append(f'<span style="color:#7f8c8d;">Accession: {h.accession}</span>')
                html.append('<div class="stats">')
                html.append(f'<div class="stat-row"><span class="stat-label">Identity:</span> <b style="color:{ic};">{h.identity_percent:.1f}%</b></div>')
                html.append(f'<div class="stat-row"><span class="stat-label">E-value:</span> <b style="color:{ec};">{h.evalue:.2e}</b></div>')
                html.append(f'<div class="stat-row"><span class="stat-label">Bit Score:</span> <b>{h.score:.1f}</b></div>')
                html.append(f'<div class="stat-row"><span class="stat-label">Alignment Length:</span> {h.alignment_length}</div>')
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
