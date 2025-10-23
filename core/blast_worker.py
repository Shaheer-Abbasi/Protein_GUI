import subprocess
import tempfile
import os
from PyQt5.QtCore import QThread, pyqtSignal
from Bio.Blast import NCBIXML


class BLASTWorker(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, sequence, database, use_remote=True, local_db_path=""):
        super().__init__()
        self.sequence = sequence
        self.database = database
        self.use_remote = use_remote
        self.local_db_path = local_db_path

    def run(self):
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.fasta', delete=False) as query_file:
                query_file.write(f">query\n{self.sequence}\n")
                query_path = query_file.name

            output_path = tempfile.mktemp(suffix='.xml')
            blastp_path = r"C:\Users\abbas\Downloads\ncbi-blast-2.17.0+-x64-win64\ncbi-blast-2.17.0+\bin\blastp.exe"

            cmd = [
                blastp_path, '-query', query_path, '-outfmt', '5',
                '-max_target_seqs', '10', '-out', output_path
            ]

            if self.use_remote:
                cmd.extend(['-remote', '-db', self.database])
            else:
                local_db = os.path.join(self.local_db_path, self.database)
                cmd.extend(['-db', local_db])

            subprocess.run(cmd, check=True, capture_output=True, text=True)
            parsed_results = self.parse_blast_xml(output_path)
            os.unlink(query_path)
            os.unlink(output_path)

            self.finished.emit(parsed_results)
        except subprocess.CalledProcessError as e:
            self.error.emit(f"BLAST error:\n{e.stderr}")
        except Exception as e:
            self.error.emit(str(e))

    def parse_blast_xml(self, xml_file_path):
        try:
            with open(xml_file_path, 'r') as handle:
                blast_records = NCBIXML.parse(handle)
                results = ["=" * 80, "BLASTP SEARCH RESULTS", "=" * 80]
                for record in blast_records:
                    results.append(f"\nQuery: {record.query}")
                    results.append(f"Query Length: {record.query_length}")
                    if not record.alignments:
                        results.append("No significant alignments found.")
                        continue
                    for i, alignment in enumerate(record.alignments, 1):
                        hsp = alignment.hsps[0]
                        results.append(f"\n#{i}. {alignment.title}")
                        results.append(f"  E-value: {hsp.expect:.2e}")
                        results.append(f"  Score: {hsp.score}")
                        results.append(f"  Identity: {hsp.identities}/{hsp.align_length}")
                return "\n".join(results)
        except Exception as e:
            return f"Error parsing BLAST XML: {e}"
