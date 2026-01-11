"""
Motif Search Worker - Background processing for glycosylation motif finding.

This module provides:
- FASTA parsing for pipe-separated format
- Protein record class for storing sequence data
- Motif finding algorithm (port of MATLAB implementation)
- Phylogeny categorization
"""

from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
from PyQt5.QtCore import QThread, pyqtSignal


@dataclass
class ProteinRecord:
    """
    Protein record class storing sequence data and search results.
    
    Attributes:
        seq: Protein sequence (may contain gaps as '-')
        id: Protein identifier
        species: Species name
        phylo: List of taxonomy levels
        indices: List of motif match positions (populated after search)
    """
    seq: str
    id: str
    species: str
    phylo: List[str] = field(default_factory=list)
    indices: List[int] = field(default_factory=list)


def parse_fasta(file_path: str) -> List[ProteinRecord]:
    """
    Parse a FASTA file with pipe-separated metadata headers.
    
    Expected format:
    >ID|description|species|taxonomy;hierarchy;path
    SEQUENCE-WITH-POSSIBLE-GAPS---
    
    Also supports simple FASTA format:
    >ID description
    SEQUENCE
    
    Args:
        file_path: Path to the FASTA file
        
    Returns:
        List of ProteinRecord objects
    """
    records = []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    current_header = None
    current_seq_parts = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        if line.startswith('>'):
            # Save previous record if exists
            if current_header is not None:
                seq = ''.join(current_seq_parts)
                record = _parse_header_and_create_record(current_header, seq)
                if record:
                    records.append(record)
            
            # Start new record
            current_header = line[1:]  # Remove '>'
            current_seq_parts = []
        else:
            # Sequence line
            current_seq_parts.append(line)
    
    # Don't forget the last record
    if current_header is not None:
        seq = ''.join(current_seq_parts)
        record = _parse_header_and_create_record(current_header, seq)
        if record:
            records.append(record)
    
    return records


def _parse_header_and_create_record(header: str, seq: str) -> Optional[ProteinRecord]:
    """
    Parse a FASTA header and create a ProteinRecord.
    
    Supports two formats:
    1. Pipe-separated: ID|description|species|taxonomy
    2. Simple: ID description
    """
    if not seq:
        return None
    
    parts = header.split('|')
    
    if len(parts) >= 4:
        # Pipe-separated format
        protein_id = parts[0].strip()
        species = parts[2].strip() if len(parts) > 2 else ""
        taxonomy_str = parts[3].strip() if len(parts) > 3 else ""
        phylo = [p.strip() for p in taxonomy_str.split(';') if p.strip()]
    else:
        # Simple format - extract what we can
        protein_id = parts[0].split()[0] if parts[0] else "unknown"
        species = ""
        phylo = []
    
    return ProteinRecord(
        seq=seq,
        id=protein_id,
        species=species,
        phylo=phylo
    )


def find_motifs(motif: List[str], protein: str, motif_len: int) -> List[int]:
    """
    Find motifs in a protein sequence.
    
    This is a direct port of the MATLAB find_motifs function.
    
    Motif specification:
    - Single residue: 'N' matches N
    - Multiple residues: 'ST' matches S or T
    - Exclusion: '~P' matches anything except P
    - Exclusion with multiple: '~NP' matches anything except N or P
    
    Gaps ('-') in the sequence are skipped.
    
    Args:
        motif: List of residue patterns for each position
        protein: Protein sequence string
        motif_len: Length of the motif pattern
        
    Returns:
        List of indices where the motif was found (0-based)
    """
    if not motif or not protein or motif_len <= 0:
        return []
    
    motif_list = []  # Candidate motif sequences
    index_list = []  # Starting indices of candidates
    
    protein_len = len(protein)
    
    # Section 1: Find all positions where the first residue matches
    for i in range(protein_len - motif_len + 1):
        residue = protein[i]
        
        # Skip gaps
        if residue == '-':
            continue
        
        first_pattern = motif[0]
        
        # Check if first position matches
        if first_pattern.startswith('~'):
            # Exclusion pattern
            excluded = first_pattern[1:]  # Characters after ~
            if residue in excluded:
                continue  # This residue is excluded, skip
            # Residue is NOT in excluded set, it's a match
        else:
            # Inclusion pattern
            if residue not in first_pattern:
                continue  # Residue not in allowed set, skip
        
        # First residue matches, now collect the rest of the motif
        new_motif = residue
        j = i
        counter = 1
        
        while counter < motif_len:
            j += 1
            if j >= protein_len:
                break
            
            next_residue = protein[j]
            
            # Skip gaps
            if next_residue == '-':
                continue
            
            new_motif += next_residue
            counter += 1
        
        # Only add if we got enough residues
        if len(new_motif) >= motif_len:
            motif_list.append(new_motif)
            index_list.append(i)
    
    # Section 2: Check remaining positions of each candidate
    final_indices = []
    
    for idx, candidate in enumerate(motif_list):
        if len(candidate) < motif_len:
            continue
        
        matches_all = True
        
        for pos in range(1, motif_len):  # Start from position 1 (already checked 0)
            pattern = motif[pos]
            residue = candidate[pos]
            
            if pattern.startswith('~'):
                # Exclusion pattern - residue should NOT be in the excluded set
                excluded = pattern[1:]
                if residue in excluded:
                    matches_all = False
                    break
            else:
                # Inclusion pattern - residue should be in the allowed set
                if residue not in pattern:
                    matches_all = False
                    break
        
        if matches_all:
            final_indices.append(index_list[idx])
    
    return final_indices


def categorize_by_phylogeny(records: List[ProteinRecord]) -> Dict[str, List[ProteinRecord]]:
    """
    Categorize protein records by phylogeny.
    
    Categories:
    - Actinopterygii (ray-finned fishes)
    - Mammalia (mammals)
    - Aves (birds)
    - Amphibia (amphibians)
    - Other (everything else)
    
    Args:
        records: List of ProteinRecord objects
        
    Returns:
        Dictionary mapping category name to list of records
    """
    categories = {
        'Actinopterygii': [],
        'Mammalia': [],
        'Aves': [],
        'Amphibia': [],
        'Other': []
    }
    
    category_keywords = {
        'Actinopterygii': 'actinopterygii',
        'Mammalia': 'mammalia',
        'Aves': 'aves',
        'Amphibia': 'amphibia'
    }
    
    for record in records:
        found_category = False
        
        # Check each phylogeny level
        for phylo_level in record.phylo:
            phylo_lower = phylo_level.lower()
            
            for category, keyword in category_keywords.items():
                if keyword in phylo_lower:
                    categories[category].append(record)
                    found_category = True
                    break
            
            if found_category:
                break
        
        if not found_category:
            categories['Other'].append(record)
    
    return categories


class MotifSearchWorker(QThread):
    """
    Background worker for motif searching.
    
    Signals:
        progress: (int percent, str message) - Progress updates
        finished: (dict results) - Search completed successfully
        error: (str message) - Error occurred
    """
    
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    
    def __init__(self, fasta_path: str, motif: List[str], parent=None):
        """
        Initialize the worker.
        
        Args:
            fasta_path: Path to FASTA file
            motif: List of residue patterns (e.g., ['N', '~P', 'ST'])
            parent: Parent QObject
        """
        super().__init__(parent)
        self.fasta_path = fasta_path
        self.motif = motif
        self.motif_len = len(motif)
        self._cancelled = False
    
    def cancel(self):
        """Request cancellation of the search."""
        self._cancelled = True
    
    def run(self):
        """Execute the motif search."""
        try:
            # Step 1: Parse FASTA file
            self.progress.emit(5, "Parsing FASTA file...")
            
            records = parse_fasta(self.fasta_path)
            
            if not records:
                self.error.emit("No valid sequences found in the FASTA file.")
                return
            
            if self._cancelled:
                return
            
            self.progress.emit(15, f"Loaded {len(records)} sequences")
            
            # Step 2: Find motifs in each sequence
            total = len(records)
            motifs_found_total = 0
            
            for i, record in enumerate(records):
                if self._cancelled:
                    return
                
                record.indices = find_motifs(self.motif, record.seq, self.motif_len)
                motifs_found_total += len(record.indices)
                
                # Update progress (15% to 85%)
                progress_pct = 15 + int((i + 1) / total * 70)
                if (i + 1) % 50 == 0 or i == total - 1:
                    self.progress.emit(
                        progress_pct, 
                        f"Searching... {i + 1}/{total} sequences ({motifs_found_total} motifs found)"
                    )
            
            if self._cancelled:
                return
            
            # Step 3: Categorize by phylogeny
            self.progress.emit(90, "Categorizing by phylogeny...")
            
            categories = categorize_by_phylogeny(records)
            
            # Step 4: Prepare results
            self.progress.emit(95, "Preparing results...")
            
            results = {
                'records': records,
                'categories': categories,
                'motif': self.motif,
                'motif_len': self.motif_len,
                'total_sequences': len(records),
                'total_motifs': motifs_found_total,
                'category_stats': {
                    name: {
                        'count': len(recs),
                        'motifs': sum(len(r.indices) for r in recs)
                    }
                    for name, recs in categories.items()
                }
            }
            
            self.progress.emit(100, "Complete!")
            self.finished.emit(results)
            
        except FileNotFoundError:
            self.error.emit(f"FASTA file not found: {self.fasta_path}")
        except PermissionError:
            self.error.emit(f"Permission denied reading: {self.fasta_path}")
        except Exception as e:
            self.error.emit(f"Error during search: {str(e)}")
