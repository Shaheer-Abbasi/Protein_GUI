import subprocess
import tempfile
import os
from PyQt5.QtCore import QThread, pyqtSignal
from Bio.Blast import NCBIXML
from core.config_manager import get_config


class BLASTWorker(QThread):
    """Worker thread to run BLAST without freezing the GUI"""
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
            # Create temporary files for input and output
            with tempfile.NamedTemporaryFile(mode='w', suffix='.fasta', delete=False) as query_file:
                query_file.write(f">query\n{self.sequence}\n")
                query_path = query_file.name
            
            output_path = tempfile.mktemp(suffix='.xml')
            
            # Get BLASTP path from config (portable across machines)
            config = get_config()
            blastp_path = config.get_blast_path()
            
            # Build command based on remote vs local database
            cmd = [
                blastp_path,
                '-query', query_path,
                '-outfmt', '5',  # XML format for Biopython parsing
                '-max_target_seqs', '10',  # Limit to top 10 hits
                '-out', output_path
            ]
            
            if self.use_remote:
                cmd.extend(['-remote', '-db', self.database])
            else:
                # For local database, use the path relative to project root
                if self.local_db_path:
                    # If user specified a custom path
                    local_db = os.path.join(self.local_db_path, self.database)
                else:
                    # Use default local database directory (relative to project root)
                    blast_db_dir = config.get_blast_db_dir()
                    local_db = os.path.join(blast_db_dir, self.database)
                
                cmd.extend(['-db', local_db])
            
            # Execute BLAST
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            
            # Parse results with Biopython
            parsed_results = self.parse_blast_xml(output_path)
            
            # Cleanup
            os.unlink(query_path)
            os.unlink(output_path)
            
            self.finished.emit(parsed_results)
            
        except subprocess.CalledProcessError as e:
            self.error.emit(f"BLAST error: {e.stderr}")
        except Exception as e:
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
        if identity_percent >= 90:
            return "#27ae60"  # Excellent - green
        elif identity_percent >= 70:
            return "#2ecc71"  # Very good - light green
        elif identity_percent >= 50:
            return "#f39c12"  # Good - orange
        elif identity_percent >= 30:
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
                html.append('.header { background-color: #34495e; color: white; padding: 15px; border-radius: 5px; margin-bottom: 20px; }')
                html.append('.header h1 { margin: 0; font-size: 20px; }')
                html.append('.info { background-color: #ecf0f1; padding: 10px; border-radius: 5px; margin-bottom: 15px; }')
                html.append('.hit { background-color: #ffffff; border: 1px solid #bdc3c7; padding: 15px; margin-bottom: 15px; border-radius: 5px; }')
                html.append('.hit-title { font-size: 14px; font-weight: bold; color: #2c3e50; margin-bottom: 10px; }')
                html.append('.stats { margin: 10px 0; }')
                html.append('.stat-row { margin: 5px 0; }')
                html.append('.stat-label { font-weight: bold; color: #7f8c8d; }')
                html.append('.alignment { background-color: #f8f9fa; padding: 10px; border-radius: 3px; font-family: "Courier New", monospace; margin-top: 10px; }')
                html.append('.no-results { color: #95a5a6; font-style: italic; text-align: center; padding: 30px; }')
                html.append('</style></head><body>')
                
                for blast_record in blast_records:
                    html.append(f'<div class="header">')
                    html.append(f'<h1>BLASTP SEARCH RESULTS</h1>')
                    html.append(f'</div>')
                    
                    html.append(f'<div class="info">')
                    html.append(f'<b>Query:</b> {blast_record.query}<br>')
                    html.append(f'<b>Query Length:</b> {blast_record.query_length} amino acids<br>')
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
                            html.append(f'<span style="color: #7f8c8d;">Length: {alignment.length} amino acids</span>')
                            
                            # Get the best HSP (High-scoring Segment Pair)
                            if alignment.hsps:
                                hsp = alignment.hsps[0]  # Best HSP
                                identity_percent = (hsp.identities/hsp.align_length)*100
                                positive_percent = (hsp.positives/hsp.align_length)*100
                                gap_percent = (hsp.gaps/hsp.align_length)*100
                                
                                evalue_color = self.get_evalue_color(hsp.expect)
                                identity_color = self.get_identity_color(identity_percent)
                                
                                html.append(f'<div class="stats">')
                                html.append(f'<div class="stat-row"><span class="stat-label">Score:</span> <b>{hsp.score}</b> bits</div>')
                                html.append(f'<div class="stat-row"><span class="stat-label">E-value:</span> <b style="color: {evalue_color};">{hsp.expect:.2e}</b></div>')
                                html.append(f'<div class="stat-row"><span class="stat-label">Identity:</span> <b style="color: {identity_color};">{hsp.identities}/{hsp.align_length} ({identity_percent:.1f}%)</b></div>')
                                html.append(f'<div class="stat-row"><span class="stat-label">Positives:</span> <b>{hsp.positives}/{hsp.align_length} ({positive_percent:.1f}%)</b></div>')
                                html.append(f'<div class="stat-row"><span class="stat-label">Gaps:</span> {hsp.gaps}/{hsp.align_length} ({gap_percent:.1f}%)</div>')
                                html.append(f'</div>')
                                
                                # Show alignment
                                html.append(f'<div class="alignment">')
                                html.append(f'<b>Alignment</b> (Query: {hsp.query_start}-{hsp.query_end}, Subject: {hsp.sbjct_start}-{hsp.sbjct_end})<br><br>')
                                html.append(f'<span style="color: #2980b9;">Query:</span> {hsp.query}<br>')
                                html.append(f'<span style="color: #7f8c8d;">      {hsp.match}</span><br>')
                                html.append(f'<span style="color: #27ae60;">Sbjct:</span> {hsp.sbjct}')
                                html.append(f'</div>')
                            
                            html.append(f'</div>')
                    else:
                        html.append(f'<div class="no-results">No significant alignments found.</div>')
                
                html.append('</body></html>')
                return ''.join(html)
                
        except Exception as e:
            return f'<html><body><div style="color: red; padding: 20px;">Error parsing BLAST results: {str(e)}</div></body></html>'
