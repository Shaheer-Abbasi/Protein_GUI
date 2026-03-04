"""Worker thread for running MMseqs2 searches (cross-platform)"""
import subprocess
import tempfile
import os
import shutil
from PyQt5.QtCore import QThread, pyqtSignal

from core.wsl_utils import run_wsl_command, convert_path_for_tool, WSLError
from utils.results_parser import MMSeqsResultsParser


class MMseqsWorker(QThread):
    """Worker thread to run MMseqs2 search without freezing the GUI"""
    finished = pyqtSignal(str, list)  # HTML, SearchHit objects
    error = pyqtSignal(str)
    
    def __init__(self, sequence, database_path, sensitivity="sensitive"):
        super().__init__()
        self.sequence = sequence
        self.database_path = database_path
        self.sensitivity = sensitivity
    
    def run(self):
        try:
            temp_dir = tempfile.mkdtemp(prefix='mmseqs_search_')
            
            query_fasta = os.path.join(temp_dir, 'query.fasta')
            with open(query_fasta, 'w') as f:
                f.write(f">query\n{self.sequence}\n")
            
            # Convert paths for the tool execution environment
            temp_dir_tool = convert_path_for_tool(temp_dir)
            query_fasta_tool = convert_path_for_tool(query_fasta)
            database_tool = convert_path_for_tool(self.database_path)
            
            query_db_tool = f"{temp_dir_tool}/queryDB"
            result_db_tool = f"{temp_dir_tool}/resultDB"
            tmp_folder_tool = f"{temp_dir_tool}/tmp"
            output_file_tool = f"{temp_dir_tool}/results.m8"
            
            tmp_folder = os.path.join(temp_dir, 'tmp')
            os.makedirs(tmp_folder, exist_ok=True)
            
            # Step 1: Create query database
            cmd_createdb = f'mmseqs createdb "{query_fasta_tool}" "{query_db_tool}"'
            result = run_wsl_command(cmd_createdb, timeout=60)
            
            if result.returncode != 0:
                self.error.emit(f"Error creating query database:\n{result.stderr}")
                shutil.rmtree(temp_dir, ignore_errors=True)
                return
            
            # Step 2: Run search
            sensitivity_value = self.get_sensitivity_value()
            cmd_search = f'mmseqs search "{query_db_tool}" "{database_tool}" "{result_db_tool}" "{tmp_folder_tool}" -s {sensitivity_value}'
            
            result = run_wsl_command(cmd_search, timeout=300)
            
            if result.returncode != 0:
                self.error.emit(f"MMseqs2 search error:\n{result.stderr}\n\nStdout:\n{result.stdout}")
                shutil.rmtree(temp_dir, ignore_errors=True)
                return
            
            # Step 3: Convert results to readable format
            cmd_convertalis = f'mmseqs convertalis "{query_db_tool}" "{database_tool}" "{result_db_tool}" "{output_file_tool}" --format-output "query,target,theader,pident,alnlen,mismatch,gapopen,qstart,qend,tstart,tend,evalue,bits"'
            
            result = run_wsl_command(cmd_convertalis, timeout=60)
            
            if result.returncode != 0:
                self.error.emit(f"Error converting results:\n{result.stderr}")
                shutil.rmtree(temp_dir, ignore_errors=True)
                return
            
            # Read and format results
            output_file = os.path.join(temp_dir, 'results.m8')
            formatted_results = self.format_results(output_file, result.stdout, result.stderr)
            
            structured_data = MMSeqsResultsParser.parse_m8(output_file) if os.path.exists(output_file) else []
            
            shutil.rmtree(temp_dir, ignore_errors=True)
            
            self.finished.emit(formatted_results, structured_data)
            
        except subprocess.TimeoutExpired:
            self.error.emit("MMseqs2 search timed out after 5 minutes.")
        except WSLError as e:
            self.error.emit(f"Execution error: {str(e)}")
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
    
    def get_evalue_color(self, evalue_str):
        """Get color based on E-value (lower is better)"""
        try:
            evalue = float(evalue_str)
            if evalue < 1e-100:
                return "#27ae60"
            elif evalue < 1e-50:
                return "#2ecc71"
            elif evalue < 1e-10:
                return "#f39c12"
            elif evalue < 1e-5:
                return "#e67e22"
            else:
                return "#e74c3c"
        except:
            return "#7f8c8d"
    
    def get_identity_color(self, identity_str):
        """Get color based on identity percentage"""
        try:
            identity = float(identity_str)
            if identity >= 90:
                return "#27ae60"
            elif identity >= 70:
                return "#2ecc71"
            elif identity >= 50:
                return "#f39c12"
            elif identity >= 30:
                return "#e67e22"
            else:
                return "#e74c3c"
        except:
            return "#7f8c8d"
    
    def format_results(self, results_file, stdout, stderr):
        """Format MMseqs2 results for display as HTML"""
        html = []
        html.append('<html><head><style>')
        html.append('body { font-family: "Courier New", monospace; font-size: 12px; }')
        html.append('.header { background-color: #8e44ad; color: white; padding: 15px; border-radius: 5px; margin-bottom: 20px; }')
        html.append('.header h1 { margin: 0; font-size: 20px; }')
        html.append('.info { background-color: #ecf0f1; padding: 10px; border-radius: 5px; margin-bottom: 15px; }')
        html.append('.hit { background-color: #ffffff; border: 1px solid #bdc3c7; padding: 15px; margin-bottom: 15px; border-radius: 5px; }')
        html.append('.hit-title { font-size: 14px; font-weight: bold; color: #2c3e50; margin-bottom: 10px; }')
        html.append('.stats { margin: 10px 0; }')
        html.append('.stat-row { margin: 5px 0; }')
        html.append('.stat-label { font-weight: bold; color: #7f8c8d; }')
        html.append('.no-results { color: #95a5a6; font-style: italic; text-align: center; padding: 30px; }')
        html.append('</style></head><body>')
        
        html.append(f'<div class="header">')
        html.append(f'<h1>MMSEQS2 SEARCH RESULTS</h1>')
        html.append(f'</div>')
        
        try:
            if os.path.exists(results_file) and os.path.getsize(results_file) > 0:
                with open(results_file, 'r') as f:
                    lines = f.readlines()
                
                if lines:
                    html.append(f'<div style="background-color: #d5f4e6; padding: 10px; border-radius: 5px; margin-bottom: 15px;">')
                    html.append(f'<b>✓ Found {len(lines)} alignment(s)</b>')
                    if len(lines) > 20:
                        html.append(f' <span style="color: #7f8c8d;">(showing top 20)</span>')
                    html.append(f'</div>')
                    
                    for i, line in enumerate(lines[:20], 1):
                        fields = line.strip().split('\t')
                        if len(fields) >= 13:
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
                            
                            evalue_color = self.get_evalue_color(evalue)
                            identity_color = self.get_identity_color(identity)
                            
                            html.append(f'<div class="hit">')
                            html.append(f'<div class="hit-title">#{i}. {target_desc}</div>')
                            html.append(f'<span style="color: #7f8c8d;">Accession: {target_acc}</span>')
                            
                            html.append(f'<div class="stats">')
                            html.append(f'<div class="stat-row"><span class="stat-label">Identity:</span> <b style="color: {identity_color};">{identity}%</b></div>')
                            html.append(f'<div class="stat-row"><span class="stat-label">E-value:</span> <b style="color: {evalue_color};">{evalue}</b></div>')
                            html.append(f'<div class="stat-row"><span class="stat-label">Bit Score:</span> <b>{bits}</b></div>')
                            html.append(f'<div class="stat-row"><span class="stat-label">Alignment Length:</span> {alnlen} amino acids</div>')
                            html.append(f'<div class="stat-row"><span class="stat-label">Query Position:</span> {qstart}-{qend}</div>')
                            html.append(f'<div class="stat-row"><span class="stat-label">Target Position:</span> {tstart}-{tend}</div>')
                            html.append(f'</div>')
                            
                            html.append(f'</div>')
                        else:
                            html.append(f'<div class="hit">#{i}. {line.strip()}</div>')
                else:
                    html.append(f'<div class="no-results">No significant alignments found.</div>')
            else:
                html.append(f'<div class="no-results">No results file generated or file is empty.</div>')
                
        except Exception as e:
            html.append(f'<div style="color: red; padding: 20px;">Error reading results: {str(e)}</div>')
        
        html.append('</body></html>')
        return ''.join(html)
