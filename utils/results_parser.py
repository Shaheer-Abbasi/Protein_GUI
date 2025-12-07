"""
Parser for BLAST and MMSeqs2 results into structured SearchHit objects
"""
from dataclasses import dataclass, field
from typing import List, Optional
import xml.etree.ElementTree as ET
import re


@dataclass
class SearchHit:
    """Structured representation of a search hit"""
    rank: int = 0
    accession: str = ""
    description: str = ""
    evalue: float = 0.0
    score: float = 0.0
    identity_percent: float = 0.0
    alignment_length: int = 0
    query_coverage: float = 0.0
    full_sequence: str = ""
    sequence_length: int = 0
    organism: str = ""
    
    def to_dict(self):
        """Convert to dictionary for serialization"""
        return {
            'rank': self.rank,
            'accession': self.accession,
            'description': self.description,
            'evalue': self.evalue,
            'score': self.score,
            'identity_percent': self.identity_percent,
            'alignment_length': self.alignment_length,
            'query_coverage': self.query_coverage,
            'full_sequence': self.full_sequence,
            'sequence_length': self.sequence_length,
            'organism': self.organism
        }


class BLASTResultsParser:
    """Parse BLAST XML output into SearchHit objects"""
    
    @staticmethod
    def parse_xml(xml_path: str) -> List[SearchHit]:
        """Parse BLAST XML file and return list of SearchHit objects"""
        hits = []
        
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            
            # Find all iterations (queries)
            for iteration in root.findall('.//Iteration'):
                query_len = int(iteration.find('Iteration_query-len').text or 0)
                
                # Find all hits
                rank = 0
                for hit in iteration.findall('.//Hit'):
                    rank += 1
                    
                    # Extract basic info
                    hit_id = hit.find('Hit_id').text or ""
                    hit_def = hit.find('Hit_def').text or ""
                    hit_len = int(hit.find('Hit_len').text or 0)
                    
                    # Extract best HSP (High-scoring Segment Pair)
                    hsp = hit.find('.//Hsp')
                    if hsp is None:
                        continue
                    
                    evalue = float(hsp.find('Hsp_evalue').text or 0)
                    score = float(hsp.find('Hsp_bit-score').text or 0)
                    identity = int(hsp.find('Hsp_identity').text or 0)
                    align_len = int(hsp.find('Hsp_align-len').text or 0)
                    query_from = int(hsp.find('Hsp_query-from').text or 0)
                    query_to = int(hsp.find('Hsp_query-to').text or 0)
                    
                    # Calculate percentages
                    identity_percent = (identity / align_len * 100) if align_len > 0 else 0
                    query_coverage = ((query_to - query_from + 1) / query_len * 100) if query_len > 0 else 0
                    
                    # Extract accession from hit_id or hit_def
                    accession = BLASTResultsParser._extract_accession(hit_id, hit_def)
                    
                    # Try to extract organism
                    organism = BLASTResultsParser._extract_organism(hit_def)
                    
                    # Create SearchHit object
                    search_hit = SearchHit(
                        rank=rank,
                        accession=accession,
                        description=hit_def,
                        evalue=evalue,
                        score=score,
                        identity_percent=identity_percent,
                        alignment_length=align_len,
                        query_coverage=query_coverage,
                        full_sequence="",  # Will be fetched separately if needed
                        sequence_length=hit_len,
                        organism=organism
                    )
                    
                    hits.append(search_hit)
        
        except Exception as e:
            print(f"Error parsing BLAST XML: {e}")
            return []
        
        return hits
    
    @staticmethod
    def _extract_accession(hit_id: str, hit_def: str) -> str:
        """Extract accession ID from hit ID or definition"""
        # Try various patterns
        patterns = [
            r'([A-Z0-9]+\.[0-9]+)',  # GenBank format (e.g., NP_123456.1)
            r'sp\|([A-Z0-9]+)\|',     # UniProt SwissProt
            r'tr\|([A-Z0-9]+)\|',     # UniProt TrEMBL
            r'ref\|([A-Z0-9]+\.[0-9]+)\|',  # RefSeq
            r'pdb\|([A-Z0-9]+)\|',    # PDB
            r'([A-Z][0-9][A-Z0-9]{3}[0-9])',  # UniProt format (e.g., P12345)
        ]
        
        combined = f"{hit_id} {hit_def}"
        
        for pattern in patterns:
            match = re.search(pattern, combined)
            if match:
                return match.group(1)
        
        # Fallback: return hit_id or first word of def
        if hit_id:
            return hit_id.split('|')[0] if '|' in hit_id else hit_id.split()[0]
        
        return hit_def.split()[0] if hit_def else "unknown"
    
    @staticmethod
    def _extract_organism(description: str) -> str:
        """Extract organism name from description"""
        # Look for pattern [Organism name]
        match = re.search(r'\[([^\]]+)\]', description)
        if match:
            return match.group(1)
        return "Unknown"


class MMSeqsResultsParser:
    """Parse MMSeqs2 M8 output into SearchHit objects"""
    
    @staticmethod
    def parse_m8(m8_path: str) -> List[SearchHit]:
        """Parse MMSeqs2 M8 format file and return list of SearchHit objects"""
        hits = []
        
        try:
            with open(m8_path, 'r') as f:
                rank = 0
                for line in f:
                    # Skip comments
                    if line.startswith('#'):
                        continue
                    
                    # M8 format (tab-separated):
                    # 0: query, 1: target, 2: identity, 3: alnLen, 4: mismatch, 5: gapopen
                    # 6: qstart, 7: qend, 8: tstart, 9: tend, 10: evalue, 11: bits
                    parts = line.strip().split('\t')
                    if len(parts) < 12:
                        continue
                    
                    rank += 1
                    
                    target_id = parts[1]
                    identity = float(parts[2])
                    align_len = int(parts[3])
                    evalue = float(parts[10])
                    score = float(parts[11])
                    
                    # Extract accession
                    accession = MMSeqsResultsParser._extract_accession(target_id)
                    
                    # Create SearchHit
                    search_hit = SearchHit(
                        rank=rank,
                        accession=accession,
                        description=target_id,
                        evalue=evalue,
                        score=score,
                        identity_percent=identity,
                        alignment_length=align_len,
                        query_coverage=0.0,  # Not directly available in M8
                        full_sequence="",
                        sequence_length=0,
                        organism="Unknown"
                    )
                    
                    hits.append(search_hit)
        
        except Exception as e:
            print(f"Error parsing MMSeqs2 M8: {e}")
            return []
        
        return hits
    
    @staticmethod
    def _extract_accession(target_id: str) -> str:
        """Extract accession from target ID"""
        # MMSeqs2 target IDs are usually just the accession
        # But may have | separators
        if '|' in target_id:
            parts = target_id.split('|')
            # Return the part that looks most like an accession
            for part in parts:
                if re.match(r'[A-Z0-9_]+', part):
                    return part
        
        return target_id.split()[0] if target_id else "unknown"
