import subprocess
import tempfile
import os
from PyQt5.QtCore import QThread, pyqtSignal
from Bio.Blast import NCBIXML


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
            
            # Run BLASTP command with XML output for better parsing
            blastp_path = r'C:\Users\18329\NCBI\ncbi-blast-2.17.0+-x64-win64.tar\ncbi-blast-2.17.0+-x64-win64\ncbi-blast-2.17.0+\bin\blastp.exe'
            #blastp_path = r'C:\Users\abbas\Downloads\ncbi-blast-2.17.0+-x64-win64.tar\ncbi-blast-2.17.0+-x64-win64\ncbi-blast-2.17.0+\bin\blastp.exe'
            
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
                # For local database, use the full path
                if self.local_db_path:
                    # If user specified a custom path
                    local_db = os.path.join(self.local_db_path, self.database)
                else:
                    # Use default local database directory
                    script_dir = os.path.dirname(os.path.abspath(__file__))
                    local_db = os.path.join(script_dir, 'blast_databases', self.database)
                
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
    
    def parse_blast_xml(self, xml_file_path):
        """Parse BLAST XML output using Biopython"""
        try:
            with open(xml_file_path, 'r') as result_handle:
                blast_records = NCBIXML.parse(result_handle)
                
                formatted_results = []
                formatted_results.append("=" * 80)
                formatted_results.append("BLASTP SEARCH RESULTS")
                formatted_results.append("=" * 80)
                
                for blast_record in blast_records:
                    formatted_results.append(f"\nQuery: {blast_record.query}")
                    formatted_results.append(f"Query Length: {blast_record.query_length} amino acids")
                    formatted_results.append(f"Database: {blast_record.database}")
                    formatted_results.append(f"Number of sequences in database: {blast_record.database_sequences:,}")
                    formatted_results.append("\n" + "-" * 80)
                    
                    if blast_record.alignments:
                        formatted_results.append(f"Found {len(blast_record.alignments)} significant alignments:")
                        formatted_results.append("-" * 80)
                        
                        for i, alignment in enumerate(blast_record.alignments, 1):
                            formatted_results.append(f"\n#{i}. {alignment.title}")
                            formatted_results.append(f"Length: {alignment.length} amino acids")
                            
                            # Get the best HSP (High-scoring Segment Pair)
                            if alignment.hsps:
                                hsp = alignment.hsps[0]  # Best HSP
                                
                                formatted_results.append(f"\nBest Hit Statistics:")
                                formatted_results.append(f"  Score: {hsp.score} bits")
                                formatted_results.append(f"  E-value: {hsp.expect:.2e}")
                                formatted_results.append(f"  Identity: {hsp.identities}/{hsp.align_length} ({hsp.identities/hsp.align_length*100:.1f}%)")
                                formatted_results.append(f"  Positives: {hsp.positives}/{hsp.align_length} ({hsp.positives/hsp.align_length*100:.1f}%)")
                                formatted_results.append(f"  Gaps: {hsp.gaps}/{hsp.align_length} ({hsp.gaps/hsp.align_length*100:.1f}%)")
                                
                                # Show alignment
                                formatted_results.append(f"\nAlignment (Query: {hsp.query_start}-{hsp.query_end}, Subject: {hsp.sbjct_start}-{hsp.sbjct_end}):")
                                formatted_results.append(f"Query: {hsp.query}")
                                formatted_results.append(f"       {hsp.match}")
                                formatted_results.append(f"Sbjct: {hsp.sbjct}")
                                
                            formatted_results.append("-" * 60)
                    else:
                        formatted_results.append("No significant alignments found.")
                
                return "\n".join(formatted_results)
                
        except Exception as e:
            return f"Error parsing BLAST results: {str(e)}"
