"""Worker thread for running multiple sequence alignments (cross-platform)."""
import os
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from PyQt5.QtCore import QThread, pyqtSignal

from core.tool_registry import ALIGNMENT_TOOL_IDS
from core.tool_runtime import get_tool_runtime
from core.wsl_utils import run_wsl_command, WSLError


class AlignmentError(Exception):
    """Custom exception for alignment errors"""
    pass


# Max sequences per aligner (FAMSA is designed for very large inputs).
MAX_SEQUENCES_BY_TOOL = {
    "clustalo": 2000,
    "mafft": 2000,
    "muscle": 2000,
    "famsa": 100_000,
}


def max_sequences_for_tool(tool_id: str) -> int:
    return MAX_SEQUENCES_BY_TOOL.get(tool_id, 2000)


def aligner_display_name(tool_id: str) -> str:
    names = {
        "clustalo": "Clustal Omega",
        "mafft": "MAFFT",
        "muscle": "MUSCLE",
        "famsa": "FAMSA",
    }
    return names.get(tool_id, tool_id)


def check_alignment_tool_installation(tool_id: str):
    """
    Check if the given alignment tool is installed.

    Returns:
        tuple: (installed: bool, version: str or None, path: str or None)
    """
    status = get_tool_runtime().get_tool_status(tool_id)
    return status.installed, status.version, status.executable_path


def check_clustalo_installation():
    """Backward-compatible wrapper for Clustal Omega only."""
    return check_alignment_tool_installation("clustalo")


class AlignmentWorker(QThread):
    """
    Worker thread for running MSA with Clustal Omega, MAFFT, MUSCLE, or FAMSA.

    Cross-platform: uses WSL on Windows, native execution on macOS/Linux.
    """

    progress = pyqtSignal(int, str)
    finished = pyqtSignal(str, str)  # aligned_fasta_content, output_file_path
    error = pyqtSignal(str)

    DEFAULT_TIMEOUT = 600

    def __init__(
        self,
        input_fasta_path,
        tool_id="clustalo",
        output_format="fasta",
        iterations=0,
        full_iter=False,
        force=True,
        threads=None,
        mafft_strategy="auto",
        famsa_medoid_tree=False,
    ):
        super().__init__()

        if tool_id not in ALIGNMENT_TOOL_IDS:
            raise ValueError(f"Unsupported alignment tool: {tool_id}")

        self.tool_id = tool_id
        self.input_fasta_path = input_fasta_path
        self.output_format = output_format
        self.iterations = iterations
        self.full_iter = full_iter
        self.force = force
        self.threads = threads
        self.mafft_strategy = mafft_strategy
        self.famsa_medoid_tree = famsa_medoid_tree

        self._cancelled = False
        self._temp_files = []

    @property
    def max_sequences(self):
        return max_sequences_for_tool(self.tool_id)

    def cancel(self):
        """Cancel the alignment"""
        self._cancelled = True

    def run(self):
        """Run the alignment"""
        output_path = None
        display = aligner_display_name(self.tool_id)

        try:
            self.progress.emit(0, "Preparing alignment...")

            if not os.path.exists(self.input_fasta_path):
                raise AlignmentError(f"Input file not found: {self.input_fasta_path}")

            seq_count = self._count_sequences()
            if seq_count < 2:
                raise AlignmentError("At least 2 sequences are required for alignment")

            if seq_count > self.max_sequences:
                raise AlignmentError(
                    f"Too many sequences ({seq_count}). Maximum for {display} is {self.max_sequences}.\n"
                    "Consider reducing the number of sequences or choosing another aligner (e.g. FAMSA for large sets)."
                )

            if self._cancelled:
                return

            runtime = get_tool_runtime()
            resolution = runtime.resolve_tool(self.tool_id)
            if not resolution.executable:
                raise AlignmentError(
                    f"{display} is not available. Install it from the Tools tab or configure a valid executable path."
                )

            if resolution.backend == "wsl":
                self.progress.emit(10, f"Found {seq_count} sequences. Copying to WSL...")
                tool_input_path = self._copy_to_wsl_temp()
            else:
                self.progress.emit(10, f"Found {seq_count} sequences. Preparing...")
                tool_input_path = self._prepare_native_temp()

            self.progress.emit(20, f"Running {display} alignment...")

            if self._cancelled:
                return

            aligned_content = self._run_aligner(resolution, tool_input_path, seq_count)

            self.progress.emit(80, "Reading alignment results...")

            if self._cancelled:
                return

            output_path = self._save_output(aligned_content)

            self.progress.emit(100, "Alignment complete!")
            self.finished.emit(aligned_content, output_path)

        except AlignmentError as e:
            self._cleanup_windows_output(output_path)
            self.error.emit(str(e))
        except Exception as e:
            self._cleanup_windows_output(output_path)
            self.error.emit(f"Unexpected error: {str(e)}")
        finally:
            self._cleanup_temp_files()

    def _run_aligner(self, resolution, input_path, seq_count):
        if self.tool_id == "clustalo":
            out_path = self._run_clustalo(resolution, input_path, seq_count)
            return self._read_output(resolution, out_path)
        if self.tool_id == "mafft":
            return self._run_mafft(resolution, input_path, seq_count)
        if self.tool_id == "muscle":
            out_path = self._run_muscle(resolution, input_path, seq_count)
            return self._read_output(resolution, out_path)
        if self.tool_id == "famsa":
            out_path = self._run_famsa(resolution, input_path, seq_count)
            return self._read_output(resolution, out_path)
        raise AlignmentError(f"Unknown aligner: {self.tool_id}")

    def _count_sequences(self):
        """Count sequences in the input FASTA file"""
        count = 0
        try:
            with open(self.input_fasta_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith(">"):
                        count += 1
        except Exception as e:
            raise AlignmentError(f"Error reading input file: {str(e)}")
        return count

    def _effective_threads(self):
        if self.threads is not None and self.threads > 0:
            return int(self.threads)
        return max(1, min(8, (os.cpu_count() or 4)))

    def _alignment_timeout(self, seq_count):
        base = self.DEFAULT_TIMEOUT
        if self.tool_id == "famsa":
            return max(base, seq_count // 50 + 120)
        if self.tool_id == "mafft":
            return max(base, seq_count * 3)
        return max(base, seq_count * 2)

    def _argv_for_resolution(self, resolution, cmd_parts):
        """Build argv for subprocess (native or WSL)."""
        exe = resolution.executable
        if resolution.backend == "wsl":
            return ["wsl", exe] + list(cmd_parts)
        return [exe] + list(cmd_parts)

    def _run_subprocess_with_live_feedback(
        self,
        resolution,
        cmd_parts,
        timeout,
        phase_label,
        *,
        capture_stdout=False,
        file_stdout=None,
    ):
        """
        Run the aligner with stderr streamed into progress updates.
        If the tool is quiet on stderr (common for MUSCLE), emit periodic heartbeats
        with elapsed time so the UI does not look frozen.

        Use ``file_stdout`` for large stdout (e.g. MAFFT) to avoid pipe deadlocks;
        ``capture_stdout`` reads stdout into memory after the process exits.
        """
        cmd = self._argv_for_resolution(resolution, cmd_parts)
        file_handle = None
        if file_stdout is not None:
            file_handle = open(file_stdout, "w", encoding="utf-8", errors="replace")
            stdout_target = file_handle
        elif capture_stdout:
            stdout_target = subprocess.PIPE
        else:
            stdout_target = subprocess.DEVNULL

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=stdout_target,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                errors="replace",
            )
        except OSError as e:
            if file_handle:
                file_handle.close()
            raise AlignmentError(f"Could not start {phase_label}: {e}") from e

        line_count = [0]
        last_stderr_activity = [time.monotonic()]
        stop_drain = threading.Event()

        def drain_stderr():
            try:
                for line in iter(proc.stderr.readline, ""):
                    if stop_drain.is_set():
                        break
                    line = line.rstrip()
                    if not line:
                        continue
                    last_stderr_activity[0] = time.monotonic()
                    line_count[0] += 1
                    pct = 21 + min(52, (line_count[0] // 2) + min(10, len(line) // 20))
                    self.progress.emit(pct, f"{phase_label}: {line[:120]}")
            except Exception:
                pass
            finally:
                try:
                    if proc.stderr:
                        proc.stderr.close()
                except Exception:
                    pass

        drain_t = threading.Thread(target=drain_stderr, daemon=True)
        drain_t.start()

        deadline = time.monotonic() + timeout
        started = time.monotonic()
        last_hb = started
        rc = None

        try:
            while proc.poll() is None:
                if self._cancelled:
                    proc.terminate()
                    try:
                        proc.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    raise AlignmentError("Alignment cancelled")

                now = time.monotonic()
                if now > deadline:
                    proc.kill()
                    try:
                        proc.wait(timeout=8)
                    except subprocess.TimeoutExpired:
                        pass
                    raise AlignmentError(
                        f"Alignment timed out after {timeout} seconds.\n"
                        "Try fewer sequences or a faster aligner."
                    )

                if now - last_hb >= 1.5 and (now - last_stderr_activity[0] >= 2.0):
                    elapsed = int(now - started)
                    span = max(timeout * 0.9, 90.0)
                    creep = 22 + int(min(34, 34 * (elapsed / span)))
                    if line_count[0] == 0:
                        msg = (
                            f"{phase_label}: working... ({elapsed}s elapsed, "
                            "this step can take several minutes)"
                        )
                    else:
                        msg = f"{phase_label}: still running... ({elapsed}s elapsed)"
                    self.progress.emit(min(76, max(creep, 22)), msg)
                    last_hb = now

                time.sleep(0.12)

            rc = proc.returncode if proc.returncode is not None else 0
        finally:
            stop_drain.set()
            drain_t.join(timeout=4)
            if file_handle:
                try:
                    file_handle.flush()
                    file_handle.close()
                except Exception:
                    pass

        stdout_data = ""
        if file_stdout is not None:
            try:
                with open(file_stdout, encoding="utf-8", errors="replace") as f:
                    stdout_data = f.read() or ""
            except OSError:
                stdout_data = ""
        elif capture_stdout and proc.stdout:
            stdout_data = proc.stdout.read() or ""

        if rc != 0:
            raise AlignmentError(
                f"{phase_label} failed (exit code {rc}).\n"
                "Check the Tools tab that the binary runs correctly, or try another aligner."
            )

        return stdout_data

    def _prepare_native_temp(self):
        """Prepare input in a native temp directory (macOS/Linux)"""
        unique_id = str(uuid.uuid4())[:8]
        temp_input = os.path.join(tempfile.gettempdir(), f"alignment_input_{unique_id}.fasta")

        try:
            shutil.copy2(self.input_fasta_path, temp_input)
        except Exception as e:
            raise AlignmentError(f"Error copying input file: {str(e)}")

        self._temp_files.append(("native", temp_input))
        return temp_input

    def _copy_to_wsl_temp(self):
        """Copy input file to WSL /tmp directory (Windows)"""
        unique_id = str(uuid.uuid4())[:8]
        wsl_input_path = f"/tmp/alignment_input_{unique_id}.fasta"

        try:
            with open(self.input_fasta_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            raise AlignmentError(f"Error reading input file: {str(e)}")

        try:
            result = run_wsl_command(
                f"cat > '{wsl_input_path}' << 'FASTA_EOF'\n{content}\nFASTA_EOF",
                timeout=60,
            )
            if result.returncode != 0:
                raise AlignmentError(f"Failed to copy file to WSL: {result.stderr}")
        except WSLError as e:
            raise AlignmentError(f"WSL error: {str(e)}")

        self._temp_files.append(("wsl", wsl_input_path))
        return wsl_input_path

    def _run_clustalo(self, resolution, input_path, seq_count):
        """Run Clustal Omega alignment; returns path to output file."""
        unique_id = str(uuid.uuid4())[:8]

        if resolution.backend == "wsl":
            output_path = f"/tmp/alignment_output_{unique_id}.aln"
        else:
            output_path = os.path.join(tempfile.gettempdir(), f"alignment_output_{unique_id}.aln")

        cmd_parts = [
            "-i",
            input_path,
            "-o",
            output_path,
            f"--outfmt={self.output_format}",
        ]

        if self.force:
            cmd_parts.append("--force")

        if self.iterations > 0:
            cmd_parts.extend(["--iterations", str(self.iterations)])

        if self.full_iter:
            cmd_parts.append("--full-iter")

        if self.threads:
            cmd_parts.extend(["--threads", str(self.threads)])
        else:
            cmd_parts.extend(["--threads", str(self._effective_threads())])

        cmd_parts.append("--verbose")

        timeout = self._alignment_timeout(seq_count)
        self._run_subprocess_with_live_feedback(
            resolution, cmd_parts, timeout, "Clustal Omega", capture_stdout=False
        )

        file_type = "wsl" if resolution.backend == "wsl" else "native"
        self._temp_files.append((file_type, output_path))
        return output_path

    def _mafft_strategy_args(self):
        s = self.mafft_strategy or "auto"
        if s == "auto":
            return ["--auto"]
        if s == "linsi":
            return ["--localpair", "--maxiterate", "1000"]
        if s == "ginsi":
            return ["--globalpair", "--maxiterate", "1000"]
        if s == "einsi":
            return ["--ep", "0", "--genafpair", "--maxiterate", "1000"]
        if s == "fftns2":
            return ["--retree", "2"]
        return ["--auto"]

    def _run_mafft(self, resolution, input_path, seq_count):
        """Run MAFFT; alignment is written to stdout."""
        cmd_parts = list(self._mafft_strategy_args())
        cmd_parts.extend(["--thread", str(self._effective_threads())])
        if self.output_format == "clustal":
            cmd_parts.append("--clustalout")
        cmd_parts.append(input_path)

        timeout = self._alignment_timeout(seq_count)
        mafft_out = os.path.join(
            tempfile.gettempdir(), f"mafft_out_{uuid.uuid4().hex[:8]}.fasta"
        )
        try:
            stdout_data = self._run_subprocess_with_live_feedback(
                resolution, cmd_parts, timeout, "MAFFT", file_stdout=mafft_out
            )
        finally:
            if os.path.exists(mafft_out):
                try:
                    os.remove(mafft_out)
                except OSError:
                    pass
        aligned = (stdout_data or "").strip()
        if not aligned:
            raise AlignmentError("MAFFT produced no output.")
        return aligned

    def _run_muscle(self, resolution, input_path, seq_count):
        """Run MUSCLE v5; returns path to output file."""
        unique_id = str(uuid.uuid4())[:8]
        if resolution.backend == "wsl":
            output_path = f"/tmp/alignment_output_{unique_id}.fasta"
        else:
            output_path = os.path.join(tempfile.gettempdir(), f"alignment_output_{unique_id}.fasta")

        cmd_parts = [
            "-align",
            input_path,
            "-output",
            output_path,
            "-threads",
            str(self._effective_threads()),
        ]

        timeout = self._alignment_timeout(seq_count)
        self._run_subprocess_with_live_feedback(
            resolution, cmd_parts, timeout, "MUSCLE", capture_stdout=False
        )

        file_type = "wsl" if resolution.backend == "wsl" else "native"
        self._temp_files.append((file_type, output_path))
        return output_path

    def _run_famsa(self, resolution, input_path, seq_count):
        """Run FAMSA; returns path to output file."""
        unique_id = str(uuid.uuid4())[:8]
        if resolution.backend == "wsl":
            output_path = f"/tmp/alignment_output_{unique_id}.fasta"
        else:
            output_path = os.path.join(tempfile.gettempdir(), f"alignment_output_{unique_id}.fasta")

        cmd_parts = ["-t", str(self._effective_threads())]
        if self.famsa_medoid_tree:
            cmd_parts.append("--medoid-tree")
        cmd_parts.extend([input_path, output_path])

        timeout = self._alignment_timeout(seq_count)
        self._run_subprocess_with_live_feedback(
            resolution, cmd_parts, timeout, "FAMSA", capture_stdout=False
        )

        file_type = "wsl" if resolution.backend == "wsl" else "native"
        self._temp_files.append((file_type, output_path))
        return output_path

    def _read_output(self, resolution, output_path):
        """Read alignment text from native path or WSL."""
        if resolution.backend == "wsl":
            return self._read_wsl_output(output_path)
        return self._read_native_output(output_path)

    def _read_native_output(self, output_path):
        """Read alignment output from a native file (macOS/Linux)"""
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            raise AlignmentError(f"Error reading output: {str(e)}")

    def _read_wsl_output(self, wsl_output_path):
        """Read the alignment output from WSL (Windows)"""
        try:
            result = run_wsl_command(f"cat '{wsl_output_path}'", timeout=60)

            if result.returncode != 0:
                raise AlignmentError(f"Failed to read output: {result.stderr}")

            return result.stdout

        except WSLError as e:
            raise AlignmentError(f"Error reading output: {str(e)}")

    def _save_output(self, content):
        """Save alignment output to a temp file"""
        ext_map = {
            "fasta": ".fasta",
            "clustal": ".aln",
            "msf": ".msf",
            "phylip": ".phy",
            "selex": ".slx",
            "stockholm": ".sto",
            "vienna": ".vie",
        }
        ext = ext_map.get(self.output_format, ".aln")

        fd, output_path = tempfile.mkstemp(suffix=ext, prefix="alignment_")

        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            raise AlignmentError(f"Error saving output: {str(e)}")

        return output_path

    def _cleanup_temp_files(self):
        """Clean up all temporary files"""
        for file_type, path in self._temp_files:
            if file_type == "wsl":
                try:
                    run_wsl_command(f"rm -f '{path}'", timeout=10)
                except Exception:
                    pass
            elif file_type == "native":
                try:
                    os.remove(path)
                except Exception:
                    pass

        self._temp_files = []

    def _cleanup_windows_output(self, output_path):
        """Clean up output file on error"""
        if output_path and os.path.exists(output_path):
            try:
                os.remove(output_path)
            except Exception:
                pass


class SequenceAlignmentPrep:
    """Helper class for preparing sequences for alignment"""

    @staticmethod
    def prepare_from_hits(hits, output_path):
        """
        Prepare a FASTA file from search hits for alignment.

        Args:
            hits: List of SearchHit objects with 'id' and 'sequence' attributes
            output_path: Path to write the FASTA file

        Returns:
            tuple: (success: bool, message: str, sequence_count: int)
        """
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                count = 0
                for hit in hits:
                    if hasattr(hit, "sequence") and hit.sequence:
                        seq = hit.sequence.replace(" ", "").replace("\n", "")
                        hit_id = getattr(hit, "id", None) or getattr(hit, "accession", f"seq_{count+1}")

                        f.write(f">{hit_id}\n")
                        for i in range(0, len(seq), 80):
                            f.write(seq[i : i + 80] + "\n")

                        count += 1

            if count < 2:
                return False, "At least 2 sequences with retrieved sequences are required", count

            return True, f"Prepared {count} sequences for alignment", count

        except Exception as e:
            return False, f"Error preparing sequences: {str(e)}", 0

    @staticmethod
    def validate_fasta_for_alignment(fasta_path, max_sequences=2000):
        """
        Validate a FASTA file for alignment.

        Args:
            fasta_path: Path to FASTA file
            max_sequences: Maximum allowed sequences (depends on selected aligner)

        Returns:
            tuple: (is_valid: bool, message: str, sequence_count: int)
        """
        if not os.path.exists(fasta_path):
            return False, "File not found", 0

        try:
            count = 0
            max_len = 0
            min_len = float("inf")

            current_seq = []

            with open(fasta_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith(">"):
                        if current_seq:
                            seq_len = len("".join(current_seq))
                            max_len = max(max_len, seq_len)
                            min_len = min(min_len, seq_len)
                            current_seq = []
                        count += 1
                    elif line:
                        current_seq.append(line)

                if current_seq:
                    seq_len = len("".join(current_seq))
                    max_len = max(max_len, seq_len)
                    min_len = min(min_len, seq_len)

            if count < 2:
                return False, "At least 2 sequences are required for alignment", count

            if count > max_sequences:
                return False, f"Too many sequences ({count}). Maximum is {max_sequences}", count

            return True, f"{count} sequences (length range: {min_len}-{max_len} aa)", count

        except Exception as e:
            return False, f"Error reading file: {str(e)}", 0
