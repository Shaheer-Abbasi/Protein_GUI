"""
Manager for temporary FASTA files with guaranteed cleanup
"""
import os
import tempfile
import atexit
from typing import List


class TemporaryFastaManager:
    """Manages temporary FASTA files with guaranteed cleanup"""
    
    def __init__(self):
        self.temp_files = []
        atexit.register(self.cleanup_all)
    
    def create_temp_fasta(self, sequences: List, prefix='cluster_') -> str:
        """
        Create temporary FASTA file from search hits
        
        Args:
            sequences: List of SearchHit objects or dicts with 'accession', 'description', 'full_sequence'
            prefix: Prefix for temp file name
            
        Returns:
            Path to created FASTA file
        """
        fd, path = tempfile.mkstemp(
            suffix='.fasta',
            prefix=prefix,
            text=True
        )
        
        with os.fdopen(fd, 'w') as f:
            for hit in sequences:
                # Handle both SearchHit objects and dicts
                if hasattr(hit, 'accession'):
                    accession = hit.accession
                    description = hit.description
                    sequence = hit.full_sequence
                else:
                    accession = hit.get('accession', 'unknown_id')
                    description = hit.get('description', '')
                    sequence = hit.get('full_sequence', '')
                
                # Write FASTA entry
                f.write(f">{accession} {description}\n")
                # Write sequence in 80-character lines
                for i in range(0, len(sequence), 80):
                    f.write(f"{sequence[i:i+80]}\n")
        
        self.temp_files.append(path)
        return path
    
    def cleanup_all(self):
        """Cleanup all temporary files"""
        for path in self.temp_files:
            try:
                if os.path.exists(path):
                    os.unlink(path)
            except Exception as e:
                print(f"Warning: Could not delete temporary file {path}: {e}")
        
        self.temp_files.clear()


# Global instance
_temp_fasta_manager = None


def get_temp_fasta_manager() -> TemporaryFastaManager:
    """Get the global temporary FASTA manager instance"""
    global _temp_fasta_manager
    if _temp_fasta_manager is None:
        _temp_fasta_manager = TemporaryFastaManager()
    return _temp_fasta_manager
