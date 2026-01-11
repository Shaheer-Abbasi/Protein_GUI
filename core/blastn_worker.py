"""Worker thread for running BLASTN (nucleotide BLAST) searches"""
import subprocess
import tempfile
import os
from PyQt5.QtCore import QThread, pyqtSignal
from Bio.Blast import NCBIXML
from core.config_manager import get_config
from utils.results_parser import BLASTResultsParser


class BLASTNWorker(QThread):
    """Worker thread to run BLASTN without freezing the GUI"""
    finished = pyqtSignal(str, list)  # HTML, SearchHit objects
    error = pyqtSignal(str)
    progress = pyqtSignal(str)  # Progress message
    
    # Default advanced parameters for BLASTN
    DEFAULT_PARAMS = {
        'evalue': 10,
        'max_target_seqs': 100,
        'word_size': 11,  # Default for blastn (megablast uses 28)
        'reward': 2,      # Match reward
        'penalty': -3,    # Mismatch penalty
        'gap_open': 5,    # Gap opening cost
        'gap_extend': 2,  # Gap extension cost
        'dust': 'yes',    # DUST filter for low complexity (equivalent to SEG for proteins)
        'soft_masking': False,
        'task': 'blastn'  # Options: blastn, blastn-short, megablast, dc-megablast
    }
    
    # Timeout in seconds (5 minutes for remote, longer queries may need more)
    REMOTE_TIMEOUT = 300  # 5 minutes
    LOCAL_TIMEOUT = 120   # 2 minutes
    
    def __init__(self, sequence, database, use_remote=True, local_db_path="", advanced_params=None):
        super().__init__()
        self.sequence = sequence
        self.database = database
        self.use_remote = use_remote
        self.local_db_path = local_db_path
        self._cancelled = False
        self._process = None
        
        # Merge default params with provided params
        self.params = self.DEFAULT_PARAMS.copy()
        if advanced_params:
            self.params.update(advanced_params)
    
    def cancel(self):
        """Cancel the running BLAST search"""
        self._cancelled = True
        if self._process:
            try:
                self._process.terminate()
            except:
                pass
    
    def run(self):
        try:
            # Create temporary files for input and output
            with tempfile.NamedTemporaryFile(mode='w', suffix='.fasta', delete=False) as query_file:
                query_file.write(f">query\n{self.sequence}\n")
                query_path = query_file.name
            
            output_path = tempfile.mktemp(suffix='.xml')
            
            # Get BLASTN path from config
            config = get_config()
            blastn_path = config.get_blastn_path()
            
            # Build command
            cmd = [
                blastn_path,
                '-query', query_path,
                '-outfmt', '5',  # XML format for Biopython parsing
                '-out', output_path,
                '-task', self.params['task'],
                '-evalue', str(self.params['evalue']),
                '-max_target_seqs', str(self.params['max_target_seqs']),
                '-word_size', str(self.params['word_size']),
                '-reward', str(self.params['reward']),
                '-penalty', str(self.params['penalty']),
                '-gapopen', str(self.params['gap_open']),
                '-gapextend', str(self.params['gap_extend'])
            ]
            
            # Add DUST filter option
            if self.params['dust'] == 'yes':
                cmd.extend(['-dust', 'yes'])
            else:
                cmd.extend(['-dust', 'no'])
            
            # Add soft masking if enabled
            if self.params['soft_masking']:
                cmd.extend(['-soft_masking', 'true'])
            
            if self.use_remote:
                cmd.extend(['-remote', '-db', self.database])
                timeout = self.REMOTE_TIMEOUT
            else:
                # For local database
                if self.local_db_path:
                    local_db = os.path.join(self.local_db_path, self.database)
                else:
                    blast_db_dir = config.get_blast_db_dir()
                    local_db = os.path.join(blast_db_dir, self.database)
                
                cmd.extend(['-db', local_db])
                timeout = self.LOCAL_TIMEOUT
            
            # Check if cancelled before starting
            if self._cancelled:
                return
            
            # Execute BLASTN with timeout
            self.progress.emit("Starting BLAST search...")
            try:
                self._process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                
                try:
                    stdout, stderr = self._process.communicate(timeout=timeout)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                    self._process.communicate()
                    self.error.emit(
                        f"Search timed out after {timeout // 60} minutes.\n\n"
                        "Remote NCBI BLAST searches can take a very long time for large databases.\n\n"
                        "Try:\n"
                        "• Using a smaller database (e.g., refseq_rna instead of nt)\n"
                        "• Reducing the sequence length\n"
                        "• Using megablast algorithm for faster (but less sensitive) search"
                    )
                    # Cleanup temp files
                    try:
                        os.unlink(query_path)
                    except:
                        pass
                    return
                
                if self._cancelled:
                    # Cleanup and exit
                    try:
                        os.unlink(query_path)
                    except:
                        pass
                    return
                
                if self._process.returncode != 0:
                    raise subprocess.CalledProcessError(self._process.returncode, cmd, stdout, stderr)
                    
            except subprocess.CalledProcessError as e:
                raise e
            
            self.progress.emit("Parsing results...")
            
            # Parse results
            html_results = self.parse_blast_xml(output_path)
            structured_data = BLASTResultsParser.parse_xml(output_path)
            
            # Cleanup
            os.unlink(query_path)
            os.unlink(output_path)
            
            self.finished.emit(html_results, structured_data)
            
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if hasattr(e, 'stderr') and e.stderr else str(e)
            self.error.emit(f"BLASTN error: {error_msg}")
        except Exception as e:
            if not self._cancelled:
                self.error.emit(f"Error: {str(e)}")
    
    def get_evalue_color(self, evalue):
        """Get color based on E-value (lower is better)"""
        if evalue < 1e-100:
            return "#27ae60"  # Excellent - green
        elif evalue < 1e-50:
            return "#2ecc71"  # Very good - light green
        elif evalue < 1e-10:
            return "#f39c12"  # Good - orange
        elif evalue < 1e-5:
            return "#e67e22"  # Moderate - dark orange
        else:
            return "#e74c3c"  # Poor - red
    
    def get_identity_color(self, identity_percent):
        """Get color based on identity percentage"""
        if identity_percent >= 95:
            return "#27ae60"  # Excellent - green
        elif identity_percent >= 85:
            return "#2ecc71"  # Very good - light green
        elif identity_percent >= 70:
            return "#f39c12"  # Good - orange
        elif identity_percent >= 50:
            return "#e67e22"  # Moderate - dark orange
        else:
            return "#e74c3c"  # Poor - red
    
    def parse_blast_xml(self, xml_file_path):
        """Parse BLAST XML output using Biopython and format as HTML"""
        try:
            with open(xml_file_path, 'r') as result_handle:
                blast_records = NCBIXML.parse(result_handle)
                
                html = []
                html.append('<html><head><style>')
                html.append('body { font-family: "Courier New", monospace; font-size: 12px; }')
                html.append('.header { background-color: #1e8449; color: white; padding: 15px; border-radius: 5px; margin-bottom: 20px; }')
                html.append('.header h1 { margin: 0; font-size: 20px; }')
                html.append('.info { background-color: #e8f6f3; padding: 10px; border-radius: 5px; margin-bottom: 15px; }')
                html.append('.hit { background-color: #ffffff; border: 1px solid #bdc3c7; padding: 15px; margin-bottom: 15px; border-radius: 5px; }')
                html.append('.hit-title { font-size: 14px; font-weight: bold; color: #1e8449; margin-bottom: 10px; }')
                html.append('.stats { margin: 10px 0; }')
                html.append('.stat-row { margin: 5px 0; }')
                html.append('.stat-label { font-weight: bold; color: #7f8c8d; }')
                html.append('.alignment { background-color: #f8f9fa; padding: 10px; border-radius: 3px; font-family: "Courier New", monospace; margin-top: 10px; overflow-x: auto; }')
                html.append('.no-results { color: #95a5a6; font-style: italic; text-align: center; padding: 30px; }')
                html.append('</style></head><body>')
                
                for blast_record in blast_records:
                    html.append(f'<div class="header">')
                    html.append(f'<h1>🧬 BLASTN SEARCH RESULTS</h1>')
                    html.append(f'</div>')
                    
                    html.append(f'<div class="info">')
                    html.append(f'<b>Query:</b> {blast_record.query}<br>')
                    html.append(f'<b>Query Length:</b> {blast_record.query_length} nucleotides<br>')
                    html.append(f'<b>Database:</b> {blast_record.database}<br>')
                    html.append(f'<b>Sequences in Database:</b> {blast_record.database_sequences:,}')
                    html.append(f'</div>')
                    
                    if blast_record.alignments:
                        html.append(f'<div style="background-color: #d5f4e6; padding: 10px; border-radius: 5px; margin-bottom: 15px;">')
                        html.append(f'<b>✓ Found {len(blast_record.alignments)} significant alignment(s)</b>')
                        html.append(f'</div>')
                        
                        for i, alignment in enumerate(blast_record.alignments, 1):
                            html.append(f'<div class="hit">')
                            html.append(f'<div class="hit-title">#{i}. {alignment.title}</div>')
                            html.append(f'<span style="color: #7f8c8d;">Length: {alignment.length} nucleotides</span>')
                            
                            if alignment.hsps:
                                hsp = alignment.hsps[0]  # Best HSP
                                identity_percent = (hsp.identities/hsp.align_length)*100
                                gap_percent = (hsp.gaps/hsp.align_length)*100 if hsp.gaps else 0
                                
                                evalue_color = self.get_evalue_color(hsp.expect)
                                identity_color = self.get_identity_color(identity_percent)
                                
                                # Determine strand
                                query_strand = "Plus" if hsp.query_start < hsp.query_end else "Minus"
                                subject_strand = "Plus" if hsp.sbjct_start < hsp.sbjct_end else "Minus"
                                
                                html.append(f'<div class="stats">')
                                html.append(f'<div class="stat-row"><span class="stat-label">Score:</span> <b>{hsp.score}</b> bits</div>')
                                html.append(f'<div class="stat-row"><span class="stat-label">E-value:</span> <b style="color: {evalue_color};">{hsp.expect:.2e}</b></div>')
                                html.append(f'<div class="stat-row"><span class="stat-label">Identity:</span> <b style="color: {identity_color};">{hsp.identities}/{hsp.align_length} ({identity_percent:.1f}%)</b></div>')
                                html.append(f'<div class="stat-row"><span class="stat-label">Gaps:</span> {hsp.gaps}/{hsp.align_length} ({gap_percent:.1f}%)</div>')
                                html.append(f'<div class="stat-row"><span class="stat-label">Strand:</span> Query: {query_strand} / Subject: {subject_strand}</div>')
                                html.append(f'</div>')
                                
                                # Show alignment
                                html.append(f'<div class="alignment">')
                                html.append(f'<b>Alignment</b> (Query: {hsp.query_start}-{hsp.query_end}, Subject: {hsp.sbjct_start}-{hsp.sbjct_end})<br><br>')
                                html.append(f'<span style="color: #2980b9;">Query:</span> {hsp.query}<br>')
                                html.append(f'<span style="color: #7f8c8d;">      {hsp.match}</span><br>')
                                html.append(f'<span style="color: #1e8449;">Sbjct:</span> {hsp.sbjct}')
                                html.append(f'</div>')
                            
                            html.append(f'</div>')
                    else:
                        html.append(f'<div class="no-results">No significant alignments found.</div>')
                
                html.append('</body></html>')
                return ''.join(html)
                
        except Exception as e:
            return f'<html><body><div style="color: red; padding: 20px;">Error parsing BLAST results: {str(e)}</div></body></html>'

