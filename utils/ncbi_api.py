"""NCBI E-utilities API client for nucleotide sequence searches"""
import requests
import json
import re
import time
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from xml.etree import ElementTree


class NCBIAPIError(Exception):
    """Custom exception for NCBI API errors"""
    pass


class NCBIClient:
    """
    Client for NCBI E-utilities (Entrez) API
    
    Provides access to GenBank nucleotide sequence database.
    
    Safety features:
    - 10-second timeout for all requests
    - Rate limiting (3 requests/second without API key, 10 with)
    - Response validation
    - Request caching
    
    NCBI requires:
    - Email address in requests (for abuse tracking)
    - Rate limiting: 3 requests/second without API key
    """
    
    BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    
    # Timeout for API requests (seconds)
    TIMEOUT = 15
    
    # Rate limiting (NCBI allows 3/sec without key, 10/sec with key)
    MIN_REQUEST_INTERVAL = 0.35  # ~3 requests per second
    
    def __init__(self, email: str = "protein-gui@example.com", api_key: Optional[str] = None):
        """
        Initialize NCBI client.
        
        Args:
            email: Email address for NCBI tracking (required by NCBI policy)
            api_key: Optional NCBI API key for higher rate limits
        """
        self.email = email
        self.api_key = api_key
        
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Protein-GUI/1.0 (Educational/Research)'
        })
        
        # Rate limiting
        self.last_request_time = 0
        
        # Simple cache
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.cache_duration = timedelta(hours=24)
        self.cache_timestamps: Dict[str, datetime] = {}
    
    def _get_params(self) -> Dict[str, str]:
        """Get common parameters for all requests"""
        params = {
            'tool': 'ProteinGUI',
            'email': self.email
        }
        if self.api_key:
            params['api_key'] = self.api_key
        return params
    
    def _rate_limit(self):
        """Ensure we don't exceed rate limits"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.MIN_REQUEST_INTERVAL:
            time.sleep(self.MIN_REQUEST_INTERVAL - elapsed)
        self.last_request_time = time.time()
    
    def search_nucleotide(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Search for nucleotide sequences by gene name, organism, or keywords.
        
        Args:
            query: Search query (gene name, organism, accession, etc.)
            limit: Maximum number of results
            
        Returns:
            List of dictionaries with sequence metadata
        """
        if not query.strip():
            raise NCBIAPIError("Search query cannot be empty")
        
        self._rate_limit()
        
        # First, search for IDs using esearch
        search_url = f"{self.BASE_URL}/esearch.fcgi"
        search_params = self._get_params()
        search_params.update({
            'db': 'nucleotide',
            'term': query,
            'retmax': str(limit),
            'retmode': 'json',
            'usehistory': 'y'
        })
        
        try:
            response = self.session.get(search_url, params=search_params, timeout=self.TIMEOUT)
            
            if response.status_code != 200:
                raise NCBIAPIError(f"NCBI search failed: HTTP {response.status_code}")
            
            data = response.json()
            result = data.get('esearchresult', {})
            
            id_list = result.get('idlist', [])
            
            if not id_list:
                return []
            
            # Fetch summaries for the IDs
            return self._fetch_summaries(id_list)
            
        except requests.Timeout:
            raise NCBIAPIError(f"Search timed out after {self.TIMEOUT} seconds")
        except requests.RequestException as e:
            raise NCBIAPIError(f"Network error: {str(e)}")
        except json.JSONDecodeError:
            raise NCBIAPIError("Invalid response from NCBI API")
    
    def _fetch_summaries(self, id_list: List[str]) -> List[Dict[str, Any]]:
        """Fetch document summaries for a list of IDs"""
        self._rate_limit()
        
        summary_url = f"{self.BASE_URL}/esummary.fcgi"
        summary_params = self._get_params()
        summary_params.update({
            'db': 'nucleotide',
            'id': ','.join(id_list),
            'retmode': 'json'
        })
        
        try:
            response = self.session.get(summary_url, params=summary_params, timeout=self.TIMEOUT)
            
            if response.status_code != 200:
                raise NCBIAPIError(f"NCBI summary fetch failed: HTTP {response.status_code}")
            
            data = response.json()
            result_data = data.get('result', {})
            
            results = []
            for uid in id_list:
                if uid in result_data:
                    entry = result_data[uid]
                    
                    # Parse the entry
                    info = {
                        'id': uid,
                        'accession': entry.get('accessionversion', entry.get('caption', 'Unknown')),
                        'title': entry.get('title', 'Unknown'),
                        'organism': entry.get('organism', 'Unknown'),
                        'length': entry.get('slen', 0),
                        'mol_type': entry.get('moltype', 'Unknown'),
                        'create_date': entry.get('createdate', ''),
                        'update_date': entry.get('updatedate', ''),
                        'source': 'genbank'
                    }
                    results.append(info)
            
            return results
            
        except requests.Timeout:
            raise NCBIAPIError(f"Summary fetch timed out after {self.TIMEOUT} seconds")
        except requests.RequestException as e:
            raise NCBIAPIError(f"Network error: {str(e)}")
    
    def get_sequence_by_accession(self, accession: str) -> Dict[str, Any]:
        """
        Retrieve nucleotide sequence by accession number.
        
        Args:
            accession: GenBank accession number (e.g., 'NM_001301717', 'NC_000001')
            
        Returns:
            Dictionary with sequence data
        """
        accession = accession.strip().upper()
        
        # Check cache
        if self._is_cached(accession):
            return self.cache[accession]
        
        self._rate_limit()
        
        # Fetch sequence using efetch
        fetch_url = f"{self.BASE_URL}/efetch.fcgi"
        fetch_params = self._get_params()
        fetch_params.update({
            'db': 'nucleotide',
            'id': accession,
            'rettype': 'fasta',
            'retmode': 'text'
        })
        
        try:
            response = self.session.get(fetch_url, params=fetch_params, timeout=self.TIMEOUT)
            
            if response.status_code == 400:
                raise NCBIAPIError(f"Invalid accession number: '{accession}'")
            elif response.status_code != 200:
                raise NCBIAPIError(f"NCBI fetch failed: HTTP {response.status_code}")
            
            fasta_text = response.text.strip()
            
            if not fasta_text or not fasta_text.startswith('>'):
                raise NCBIAPIError(f"No sequence found for accession: '{accession}'")
            
            # Parse FASTA
            lines = fasta_text.split('\n')
            header = lines[0][1:]  # Remove '>'
            sequence = ''.join(lines[1:])
            
            # Get additional metadata
            metadata = self._fetch_metadata(accession)
            
            result = {
                'accession': accession,
                'header': header,
                'sequence': sequence,
                'length': len(sequence),
                'title': metadata.get('title', header),
                'organism': metadata.get('organism', 'Unknown'),
                'mol_type': metadata.get('mol_type', 'Unknown'),
                'source': 'genbank'
            }
            
            # Cache result
            self._cache_result(accession, result)
            
            return result
            
        except requests.Timeout:
            raise NCBIAPIError(f"Request timed out after {self.TIMEOUT} seconds")
        except requests.RequestException as e:
            raise NCBIAPIError(f"Network error: {str(e)}")
    
    def _fetch_metadata(self, accession: str) -> Dict[str, Any]:
        """Fetch additional metadata for an accession"""
        self._rate_limit()
        
        summary_url = f"{self.BASE_URL}/esummary.fcgi"
        summary_params = self._get_params()
        summary_params.update({
            'db': 'nucleotide',
            'id': accession,
            'retmode': 'json'
        })
        
        try:
            response = self.session.get(summary_url, params=summary_params, timeout=self.TIMEOUT)
            
            if response.status_code == 200:
                data = response.json()
                result = data.get('result', {})
                
                # Get the first matching entry
                for key, entry in result.items():
                    if key != 'uids' and isinstance(entry, dict):
                        return {
                            'title': entry.get('title', ''),
                            'organism': entry.get('organism', ''),
                            'mol_type': entry.get('moltype', '')
                        }
            
            return {}
            
        except:
            return {}
    
    def search_by_gene(self, gene_name: str, organism: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Search for nucleotide sequences by gene name.
        
        Args:
            gene_name: Gene name or symbol (e.g., 'BRCA1', 'insulin')
            organism: Optional organism filter (e.g., 'Homo sapiens')
            limit: Maximum number of results
            
        Returns:
            List of matching sequences
        """
        # Build search query
        query = f"{gene_name}[Gene Name]"
        if organism:
            query += f" AND {organism}[Organism]"
        
        return self.search_nucleotide(query, limit)
    
    def validate_accession(self, accession: str) -> bool:
        """
        Validate if an accession number format is correct.
        
        Common formats:
        - RefSeq: NM_*, NR_*, NC_*, NG_*, XM_*, XR_*
        - GenBank: 1-2 letters + 5-6 digits (e.g., M12345, AB123456)
        """
        accession = accession.strip().upper()
        
        # RefSeq patterns
        refseq_patterns = [
            r'^[NXAW][CGMRPTZ]_\d+(\.\d+)?$',  # NM_001234.1
        ]
        
        # GenBank pattern
        genbank_patterns = [
            r'^[A-Z]{1,2}\d{5,6}(\.\d+)?$',  # M12345.1, AB123456
            r'^[A-Z]{4,6}\d{8,10}(\.\d+)?$',  # AAAA01234567
        ]
        
        all_patterns = refseq_patterns + genbank_patterns
        
        for pattern in all_patterns:
            if re.match(pattern, accession):
                return True
        
        return False
    
    def _is_cached(self, key: str) -> bool:
        """Check if result is in cache and still valid"""
        if key not in self.cache:
            return False
        
        cache_time = self.cache_timestamps.get(key)
        if not cache_time:
            return False
        
        if datetime.now() - cache_time > self.cache_duration:
            del self.cache[key]
            del self.cache_timestamps[key]
            return False
        
        return True
    
    def _cache_result(self, key: str, result: Dict[str, Any]):
        """Cache API result"""
        self.cache[key] = result
        self.cache_timestamps[key] = datetime.now()
    
    def clear_cache(self):
        """Clear all cached results"""
        self.cache.clear()
        self.cache_timestamps.clear()

