import subprocess
import tempfile
import os
from utils.hardware_utils import detect_mmseqs_path


class MMseqsRunner:
    """Runs MMseqs2 searches and returns raw stdout/stderr."""

    def __init__(self):
        self.mmseqs_path = detect_mmseqs_path()

    def run_easy_search(self, query_seq, db_path, output_dir="mmseqs_out"):
        if not self.mmseqs_path:
            return "⚠️ MMseqs2 not found. Please add it to PATH or update your mmseqs path."

        query_fasta = tempfile.mktemp(suffix=".fasta")
        with open(query_fasta, "w") as f:
            f.write(f">query\n{query_seq}\n")

        os.makedirs(output_dir, exist_ok=True)
        cmd = [
            self.mmseqs_path, "easy-search", query_fasta, db_path,
            f"{output_dir}/result", "tmp"
        ]

        process = subprocess.run(cmd, capture_output=True, text=True)
        os.remove(query_fasta)

        if process.returncode != 0:
            return f"MMseqs2 Error:\n\n{process.stderr}"
        return f"MMseqs2 Output:\n\n{process.stdout}"
