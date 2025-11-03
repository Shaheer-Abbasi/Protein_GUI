import subprocess
import tempfile
import os
from PyQt5.QtCore import QThread, pyqtSignal


class MMseqsWorker(QThread):
    """Worker thread to run MMseqs2 search without freezing the GUI"""
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    
    def __init__(self, sequence, database_path, sensitivity="sensitive"):
        super().__init__()
        self.sequence = sequence
        self.database_path = database_path
        self.sensitivity = sensitivity
    
    def run(self):
        try:
            # Create temporary directory for MMseqs2 work
            temp_dir = tempfile.mkdtemp(prefix='mmseqs_')
            
            # Create query FASTA file
            query_fasta = os.path.join(temp_dir, 'query.fasta')
            with open(query_fasta, 'w') as f:
                f.write(f">query\n{self.sequence}\n")
            
            # MMseqs2 executable path
            #mmseqs_path = r'C:\Users\abbas\Downloads\mmseqs-win64\mmseqs\bin\mmseqs.exe'
            mmseqs_path = r'C:\Users\18329\MMSeqs2\mmseqs-win64\mmseqs\bin\mmseqs.exe'
            
            # Create MMseqs2 database from query
            query_db = os.path.join(temp_dir, 'queryDB')
            result_db = os.path.join(temp_dir, 'resultDB')
            tmp_folder = os.path.join(temp_dir, 'tmp')
            os.makedirs(tmp_folder, exist_ok=True)
            
            # Step 1: Create query database
            cmd_createdb = [mmseqs_path, 'createdb', query_fasta, query_db]
            result = subprocess.run(cmd_createdb, capture_output=True, text=True)
            if result.returncode != 0:
                self.error.emit(f"Error creating query database:\n{result.stderr}")
                return
            
            # Step 2: Run search (Windows-compatible, no bash scripts)
            cmd_search = [
                mmseqs_path, 'search',
                query_db,
                self.database_path,
                result_db,
                tmp_folder,
                '-s', self.get_sensitivity_value()
            ]
            
            result = subprocess.run(cmd_search, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                self.error.emit(f"MMseqs2 search error:\n{result.stderr}\n\nStdout:\n{result.stdout}")
                return
            
            # Step 3: Convert results to readable format
            output_file = os.path.join(temp_dir, 'results.m8')
            cmd_convertalis = [
                mmseqs_path, 'convertalis',
                query_db,
                self.database_path,
                result_db,
                output_file,
                '--format-output', 'query,target,pident,alnlen,mismatch,gapopen,qstart,qend,tstart,tend,evalue,bits'
            ]
            
            result = subprocess.run(cmd_convertalis, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                self.error.emit(f"Error converting results:\n{result.stderr}")
                return
            
            # Read and format results
            formatted_results = self.format_results(output_file, result.stdout, result.stderr)
            
            # Cleanup
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            
            self.finished.emit(formatted_results)
            
        except subprocess.TimeoutExpired:
            self.error.emit("MMseqs2 search timed out after 5 minutes.")
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
        
        # Add any stdout/stderr information
        if stdout.strip():
            formatted.append("Search Information:")
            formatted.append(stdout.strip())
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
                    
                    # Header
                    formatted.append("Columns: Query | Target | Identity% | AlnLen | Mismatch | GapOpen | QStart | QEnd | TStart | TEnd | E-value | BitScore")
                    formatted.append("-" * 80)
                    
                    for i, line in enumerate(lines[:20], 1):  # Limit to top 20 hits
                        formatted.append(f"\n#{i}. {line.strip()}")
                        
                        # Parse the tab-separated values for better formatting
                        fields = line.strip().split('\t')
                        if len(fields) >= 12:
                            formatted.append(f"   Target: {fields[1]}")
                            formatted.append(f"   Identity: {fields[2]}%")
                            formatted.append(f"   Alignment Length: {fields[3]}")
                            formatted.append(f"   E-value: {fields[10]}")
                            formatted.append(f"   Bit Score: {fields[11]}")
                    
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
