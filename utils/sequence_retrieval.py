"""
Utilities for retrieving full protein sequences from various sources
"""
import subprocess
import requests
import os
from typing import Optional, Dict, Any


# UniProt API base URL
UNIPROT_API_BASE = "https://rest.uniprot.org/uniprotkb/"


def fetch_sequence_from_blastdbcmd(db_path: str, accession: str) -> Optional[str]:
    """
    Fetch full sequence using blastdbcmd from a local BLAST database
    
    Args:
        db_path: Path to BLAST database (without extension)
        accession: Accession ID to fetch
        
    Returns:
        Sequence string or None if failed
    """
    if not db_path or not accession:
        return None
    
    try:
        cmd = [
            'blastdbcmd',
            '-db', db_path,
            '-entry', accession,
            '-outfmt', '%s'  # Sequence only
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            timeout=10
        )
        
        sequence = result.stdout.strip()
        if sequence and not sequence.startswith('Error'):
            return sequence.replace('\n', '').replace(' ', '')
        
        return None
        
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"blastdbcmd failed for {accession}: {e}")
        return None


def fetch_sequence_from_uniprot(uniprot_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch protein sequence and metadata from UniProt API
    
    Args:
        uniprot_id: UniProt accession ID
        
    Returns:
        Dict with sequence, protein_name, organism, etc. or None if failed
    """
    if not uniprot_id:
        return None
    
    # Clean the ID (remove version numbers, etc.)
    clean_id = uniprot_id.split('.')[0].split('|')[-1]
    
    url = f"{UNIPROT_API_BASE}{clean_id}.json"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data and 'sequence' in data and 'value' in data['sequence']:
            result = {
                'sequence': data['sequence']['value'],
                'length': len(data['sequence']['value']),
                'uniprot_id': clean_id
            }
            
            # Extract protein name
            if 'proteinDescription' in data:
                if 'recommendedName' in data['proteinDescription']:
                    result['protein_name'] = data['proteinDescription']['recommendedName']['fullName']['value']
                elif 'submittedName' in data['proteinDescription']:
                    names = data['proteinDescription']['submittedName']
                    if isinstance(names, list) and len(names) > 0:
                        result['protein_name'] = names[0]['fullName']['value']
            
            # Extract organism
            if 'organism' in data and 'scientificName' in data['organism']:
                result['organism'] = data['organism']['scientificName']
            
            return result
        
        return None
        
    except requests.exceptions.RequestException as e:
        print(f"UniProt fetch failed for {uniprot_id}: {e}")
        return None
    except Exception as e:
        print(f"Error parsing UniProt response for {uniprot_id}: {e}")
        return None
