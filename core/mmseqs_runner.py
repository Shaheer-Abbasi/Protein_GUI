"""Worker thread for running MMseqs2 searches via WSL"""
import subprocess
import tempfile
import os
import shutil
from PyQt5.QtCore import QThread, pyqtSignal

from core.wsl_utils import run_wsl_command, windows_path_to_wsl, WSLError


class MMseqsWorker(QThread):
    """Worker thread to run MMseqs2 search without freezing the GUI"""
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    
    def __init__(self, sequence, database_path, sensitivity="sensitive"):
        super().__init__()
        self.sequence = sequence
        self.database_path = database_path  # Windows path
        self.sensitivity = sensitivity
    
    def run(self):
        try:
            # Create temporary directory for MMseqs2 work
            temp_dir_windows = tempfile.mkdtemp(prefix='mmseqs_search_')
            
            # Create query FASTA file
            query_fasta_windows = os.path.join(temp_dir_windows, 'query.fasta')
            with open(query_fasta_windows, 'w') as f:
                f.write(f">query\n{self.sequence}\n")
            
            # Convert paths to WSL
            temp_dir_wsl = windows_path_to_wsl(temp_dir_windows)
            query_fasta_wsl = windows_path_to_wsl(query_fasta_windows)
            database_wsl = windows_path_to_wsl(self.database_path)
            
            # Create MMseqs2 database from query
            query_db_wsl = f"{temp_dir_wsl}/queryDB"
            result_db_wsl = f"{temp_dir_wsl}/resultDB"
            tmp_folder_wsl = f"{temp_dir_wsl}/tmp"
            output_file_wsl = f"{temp_dir_wsl}/results.m8"
            
            # Create tmp folder
            tmp_folder_windows = os.path.join(temp_dir_windows, 'tmp')
            os.makedirs(tmp_folder_windows, exist_ok=True)
            
            # Step 1: Create query database
            cmd_createdb = f'mmseqs createdb "{query_fasta_wsl}" "{query_db_wsl}"'
            result = run_wsl_command(cmd_createdb, timeout=60)
            
            if result.returncode != 0:
                self.error.emit(f"Error creating query database:\n{result.stderr}")
                shutil.rmtree(temp_dir_windows, ignore_errors=True)
                return
            
            # Step 2: Run search
            sensitivity_value = self.get_sensitivity_value()
            cmd_search = f'mmseqs search "{query_db_wsl}" "{database_wsl}" "{result_db_wsl}" "{tmp_folder_wsl}" -s {sensitivity_value}'
            
            result = run_wsl_command(cmd_search, timeout=300)  # 5 minute timeout
            
            if result.returncode != 0:
                self.error.emit(f"MMseqs2 search error:\n{result.stderr}\n\nStdout:\n{result.stdout}")
                shutil.rmtree(temp_dir_windows, ignore_errors=True)
                return
            
            # Step 3: Convert results to readable format
            # Include theader to get target description (e.g., "Cytochrome c")
            cmd_convertalis = f'mmseqs convertalis "{query_db_wsl}" "{database_wsl}" "{result_db_wsl}" "{output_file_wsl}" --format-output "query,target,theader,pident,alnlen,mismatch,gapopen,qstart,qend,tstart,tend,evalue,bits"'
            
            result = run_wsl_command(cmd_convertalis, timeout=60)
            
            if result.returncode != 0:
                self.error.emit(f"Error converting results:\n{result.stderr}")
                shutil.rmtree(temp_dir_windows, ignore_errors=True)
                return
            
            # Read and format results
            output_file_windows = os.path.join(temp_dir_windows, 'results.m8')
            formatted_results = self.format_results(output_file_windows, result.stdout, result.stderr)
            
            # Cleanup
            shutil.rmtree(temp_dir_windows, ignore_errors=True)
            
            self.finished.emit(formatted_results)
            
        except subprocess.TimeoutExpired:
            self.error.emit("MMseqs2 search timed out after 5 minutes.")
        except WSLError as e:
            self.error.emit(f"WSL error: {str(e)}")
        except Exception as e:
            import traceback
            self.error.emit(f"Error: {str(e)}\n\n{traceback.format_exc()}")
    
    def get_sensitivity_value(self):
        """Convert sensitivity name to MMseqs2 parameter value"""
        sensitivity_map = {
            "fast": "4",
            "sensitive": "5.7",
            "more-sensitive": "7",
            "very-sensitive": "8.5"
        }
        return sensitivity_map.get(self.sensitivity, "5.7")
    
    def format_results(self, results_file, stdout, stderr):
        """Format MMseqs2 results for display"""
        formatted = []
        formatted.append("=" * 80)
        formatted.append("MMSEQS2 SEARCH RESULTS")
        formatted.append("=" * 80)
        formatted.append("")
        
        # Read and parse results file
        try:
            if os.path.exists(results_file) and os.path.getsize(results_file) > 0:
                with open(results_file, 'r') as f:
                    lines = f.readlines()
                
                if lines:
                    formatted.append(f"Found {len(lines)} alignment(s)")
                    formatted.append("-" * 80)
                    formatted.append("")
                    
                    for i, line in enumerate(lines[:20], 1):  # Limit to top 20 hits
                        # Parse the tab-separated values
                        fields = line.strip().split('\t')
                        if len(fields) >= 13:
                            # Fields: query, target_acc, target_desc, pident, alnlen, mismatch, gapopen, qstart, qend, tstart, tend, evalue, bits
                            target_acc = fields[1]
                            target_desc = fields[2]
                            identity = fields[3]
                            alnlen = fields[4]
                            qstart = fields[7]
                            qend = fields[8]
                            tstart = fields[9]
                            tend = fields[10]
                            evalue = fields[11]
                            bits = fields[12]
                            
                            formatted.append(f"\n#{i}. {target_desc}")
                            formatted.append(f"   Accession: {target_acc}")
                            formatted.append(f"   Identity: {identity}%")
                            formatted.append(f"   Alignment Length: {alnlen} aa")
                            formatted.append(f"   Query Position: {qstart}-{qend}")
                            formatted.append(f"   Target Position: {tstart}-{tend}")
                            formatted.append(f"   E-value: {evalue}")
                            formatted.append(f"   Bit Score: {bits}")
                        else:
                            # Fallback for unexpected format
                            formatted.append(f"\n#{i}. {line.strip()}")
                    
                    if len(lines) > 20:
                        formatted.append(f"\n... and {len(lines) - 20} more hits (showing top 20)")
                else:
                    formatted.append("No significant alignments found.")
            else:
                formatted.append("No results file generated or file is empty.")
                
        except Exception as e:
            formatted.append(f"Error reading results: {str(e)}")
        
        formatted.append("")
        formatted.append("=" * 80)
        
        return "\n".join(formatted)
