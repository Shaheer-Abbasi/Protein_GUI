"""
Worker thread for fetching full protein sequences from multiple sources
"""
from PyQt5.QtCore import QThread, pyqtSignal
from typing import List, Optional
from utils.sequence_retrieval import fetch_sequence_from_blastdbcmd, fetch_sequence_from_uniprot


class SequenceFetcherWorker(QThread):
    """
    Worker thread to fetch full sequences for selected hits using multi-layered fallback
    
    Signals:
        progress(current, total, status_message)
        finished(successful_hits, failed_hits)
    """
    progress = pyqtSignal(int, int, str)  # current, total, status_message
    finished = pyqtSignal(list, list)     # successful_hits, failed_hits
    
    def __init__(self, selected_hits: List, database_path: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.selected_hits = selected_hits
        self.database_path = database_path
        self._is_running = True
    
    def stop(self):
        """Stop the worker"""
        self._is_running = False
    
    def run(self):
        """Main execution method"""
        successful_hits = []
        failed_hits = []
        total = len(self.selected_hits)
        
        for i, hit in enumerate(self.selected_hits):
            if not self._is_running:
                break
            
            # Update progress
            self.progress.emit(i + 1, total, f"Fetching sequence for {hit.accession}...")
            
            # Layer 1: Check if full_sequence is already available
            if hasattr(hit, 'full_sequence') and hit.full_sequence:
                successful_hits.append(hit)
                continue
            
            fetched_sequence = None
            
            # Layer 2: Try fetching from local BLAST database using blastdbcmd
            if self.database_path and self._is_running:
                fetched_sequence = fetch_sequence_from_blastdbcmd(
                    self.database_path,
                    hit.accession
                )
                
                if fetched_sequence:
                    hit.full_sequence = fetched_sequence
                    hit.sequence_length = len(fetched_sequence)
                    successful_hits.append(hit)
                    continue
            
            # Layer 3: Try fetching from UniProt API
            if self._is_running:
                uniprot_data = fetch_sequence_from_uniprot(hit.accession)
                
                if uniprot_data and uniprot_data.get('sequence'):
                    hit.full_sequence = uniprot_data['sequence']
                    hit.sequence_length = uniprot_data['length']
                    
                    # Update metadata if available
                    if 'organism' in uniprot_data:
                        hit.organism = uniprot_data['organism']
                    if 'protein_name' in uniprot_data and uniprot_data['protein_name'] != hit.accession:
                        hit.description = uniprot_data['protein_name']
                    
                    successful_hits.append(hit)
                    continue
            
            # If all layers fail
            failed_hits.append(hit)
        
        # Emit final results
        if self._is_running:
            self.finished.emit(successful_hits, failed_hits)
