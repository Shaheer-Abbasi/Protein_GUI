"""AlphaFold Database API client with robust error handling"""
import requests
import json
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta


class AlphaFoldAPIError(Exception):
    """Custom exception for AlphaFold API errors"""
    pass


class AlphaFoldClient:
    """
    Client for AlphaFold Protein Structure Database API
    
    Safety features:
    - 10-second timeout for all requests
    - Rate limit tracking
    - Response validation
    - Fallback to UniProt API
    - Request caching
    """
    
    BASE_URL = "https://www.alphafold.ebi.ac.uk/api"
    UNIPROT_BASE_URL = "https://rest.uniprot.org/uniprotkb"
    
    # Timeout for API requests (seconds)
    TIMEOUT = 10
    
    # Rate limiting (conservative estimate)
    MAX_REQUESTS_PER_MINUTE = 50
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Protein-GUI/1.0 (Educational/Research)'
        })
        
        # Simple rate limiting tracking
        self.request_times: List[datetime] = []
        
        # Simple cache: {uniprot_id: response_data}
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.cache_duration = timedelta(hours=24)
        self.cache_timestamps: Dict[str, datetime] = {}
    
    def get_protein_by_uniprot_id(self, uniprot_id: str) -> Dict[str, Any]:
        """
        Retrieve protein data from AlphaFold DB by UniProt ID
        
        Args:
            uniprot_id: UniProt accession ID (e.g., 'P12345')
            
        Returns:
            Dictionary with protein data including sequence
            
        Raises:
            AlphaFoldAPIError: If request fails
        """
        # Validate and clean UniProt ID
        uniprot_id = uniprot_id.strip().upper()
        if not self._validate_uniprot_id(uniprot_id):
            raise AlphaFoldAPIError(
                f"Invalid UniProt ID format: '{uniprot_id}'\n"
                f"Expected format: 1-2 letters followed by 5-6 digits (e.g., P12345)"
            )
        
        # Check cache first
        if self._is_cached(uniprot_id):
            return self.cache[uniprot_id]
        
        # Check rate limit
        self._check_rate_limit()
        
        # Make API request
        url = f"{self.BASE_URL}/prediction/{uniprot_id}"
        
        try:
            response = self.session.get(url, timeout=self.TIMEOUT)
            self._track_request()
            
            if response.status_code == 200:
                data = response.json()
                
                # Extract sequence from response
                sequence = self._extract_sequence(data)
                
                if not sequence:
                    # Fallback to UniProt API
                    return self._fallback_to_uniprot(uniprot_id)
                
                result = {
                    'uniprot_id': uniprot_id,
                    'sequence': sequence,
                    'source': 'alphafold',
                    'full_data': data
                }
                
                # Cache the result
                self._cache_result(uniprot_id, result)
                
                return result
                
            elif response.status_code == 404:
                # Protein not in AlphaFold DB - try UniProt
                return self._fallback_to_uniprot(uniprot_id)
                
            else:
                raise AlphaFoldAPIError(
                    f"AlphaFold API returned status {response.status_code}\n"
                    f"Response: {response.text[:200]}"
                )
                
        except requests.Timeout:
            raise AlphaFoldAPIError(
                f"Request timed out after {self.TIMEOUT} seconds\n"
                f"Please check your internet connection and try again."
            )
        except requests.ConnectionError:
            raise AlphaFoldAPIError(
                "Unable to connect to AlphaFold Database\n"
                "Please check your internet connection."
            )
        except requests.RequestException as e:
            raise AlphaFoldAPIError(f"Network error: {str(e)}")
        except json.JSONDecodeError:
            raise AlphaFoldAPIError("Invalid response from AlphaFold API")
    
    def search_protein_by_name(self, protein_name: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Search for proteins by name using UniProt API
        
        Args:
            protein_name: Protein name to search for
            limit: Maximum number of results
            
        Returns:
            List of protein dictionaries with id, name, organism, sequence
        """
        if not protein_name.strip():
            raise AlphaFoldAPIError("Protein name cannot be empty")
        
        # Check rate limit
        self._check_rate_limit()
        
        # Search UniProt
        url = f"{self.UNIPROT_BASE_URL}/search"
        params = {
            'query': protein_name,
            'format': 'json',
            'size': limit,
            'fields': 'accession,protein_name,organism_name,sequence'
        }
        
        try:
            response = self.session.get(url, params=params, timeout=self.TIMEOUT)
            self._track_request()
            
            if response.status_code == 200:
                data = response.json()
                results = []
                
                for entry in data.get('results', []):
                    protein_info = {
                        'uniprot_id': entry.get('primaryAccession', 'Unknown'),
                        'protein_name': entry.get('proteinDescription', {}).get('recommendedName', {}).get('fullName', {}).get('value', 'Unknown'),
                        'organism': entry.get('organism', {}).get('scientificName', 'Unknown'),
                        'sequence': entry.get('sequence', {}).get('value', ''),
                        'length': entry.get('sequence', {}).get('length', 0)
                    }
                    results.append(protein_info)
                
                return results
            else:
                raise AlphaFoldAPIError(f"UniProt search failed: {response.status_code}")
                
        except requests.Timeout:
            raise AlphaFoldAPIError(f"Search timed out after {self.TIMEOUT} seconds")
        except requests.RequestException as e:
            raise AlphaFoldAPIError(f"Search failed: {str(e)}")
    
    def _fallback_to_uniprot(self, uniprot_id: str) -> Dict[str, Any]:
        """
        Fallback to UniProt API when protein not in AlphaFold DB
        
        Args:
            uniprot_id: UniProt accession ID
            
        Returns:
            Dictionary with protein data
        """
        url = f"{self.UNIPROT_BASE_URL}/{uniprot_id}.json"
        
        try:
            response = self.session.get(url, timeout=self.TIMEOUT)
            self._track_request()
            
            if response.status_code == 200:
                data = response.json()
                sequence = data.get('sequence', {}).get('value', '')
                
                if not sequence:
                    raise AlphaFoldAPIError(
                        f"Protein '{uniprot_id}' found but has no sequence data"
                    )
                
                result = {
                    'uniprot_id': uniprot_id,
                    'sequence': sequence,
                    'source': 'uniprot',
                    'protein_name': data.get('proteinDescription', {}).get('recommendedName', {}).get('fullName', {}).get('value', 'Unknown'),
                    'organism': data.get('organism', {}).get('scientificName', 'Unknown'),
                    'full_data': data
                }
                
                # Cache the result
                self._cache_result(uniprot_id, result)
                
                return result
                
            elif response.status_code == 404:
                raise AlphaFoldAPIError(
                    f"Protein '{uniprot_id}' not found in AlphaFold DB or UniProt\n"
                    f"Please verify the UniProt ID is correct."
                )
            else:
                raise AlphaFoldAPIError(f"UniProt API error: {response.status_code}")
                
        except requests.Timeout:
            raise AlphaFoldAPIError(f"UniProt request timed out after {self.TIMEOUT} seconds")
        except requests.RequestException as e:
            raise AlphaFoldAPIError(f"UniProt request failed: {str(e)}")
    
    def _extract_sequence(self, data: Dict[str, Any]) -> Optional[str]:
        """
        Extract sequence from AlphaFold API response
        
        Handles different response structures based on API documentation
        """
        # Try different possible locations for sequence
        
        # Option 1: Direct in data
        if 'sequence' in data:
            return data['sequence']
        
        # Option 2: In uniprotSequence field
        if 'uniprotSequence' in data:
            seq = data['uniprotSequence']
            if isinstance(seq, dict):
                return seq.get('value') or seq.get('sequence')
            return seq
        
        # Option 3: Nested in structure
        if isinstance(data, list) and len(data) > 0:
            first_entry = data[0]
            if 'sequence' in first_entry:
                return first_entry['sequence']
            if 'uniprotSequence' in first_entry:
                return first_entry['uniprotSequence']
        
        return None
    
    def _validate_uniprot_id(self, uniprot_id: str) -> bool:
        """
        Validate UniProt ID format
        
        UniProt format: [A-Z]{1,2}[0-9]{5,6} (e.g., P12345, A0A023GPI8)
        """
        if not uniprot_id:
            return False
        
        # Must be 6-10 characters
        if len(uniprot_id) < 6 or len(uniprot_id) > 10:
            return False
        
        # Check basic pattern
        if not uniprot_id[0].isalpha():
            return False
        
        # More relaxed validation - just check if it looks reasonable
        return uniprot_id.replace('_', '').isalnum()
    
    def _check_rate_limit(self):
        """Check if we're within rate limits"""
        now = datetime.now()
        
        # Remove requests older than 1 minute
        self.request_times = [
            t for t in self.request_times 
            if now - t < timedelta(minutes=1)
        ]
        
        # Check if at limit
        if len(self.request_times) >= self.MAX_REQUESTS_PER_MINUTE:
            raise AlphaFoldAPIError(
                f"Rate limit reached ({self.MAX_REQUESTS_PER_MINUTE} requests per minute)\n"
                f"Please wait a moment before making more requests."
            )
    
    def _track_request(self):
        """Track request time for rate limiting"""
        self.request_times.append(datetime.now())
    
    def _is_cached(self, uniprot_id: str) -> bool:
        """Check if result is in cache and still valid"""
        if uniprot_id not in self.cache:
            return False
        
        cache_time = self.cache_timestamps.get(uniprot_id)
        if not cache_time:
            return False
        
        # Check if cache is still valid
        if datetime.now() - cache_time > self.cache_duration:
            # Cache expired
            del self.cache[uniprot_id]
            del self.cache_timestamps[uniprot_id]
            return False
        
        return True
    
    def _cache_result(self, uniprot_id: str, result: Dict[str, Any]):
        """Cache API result"""
        self.cache[uniprot_id] = result
        self.cache_timestamps[uniprot_id] = datetime.now()
    
    def clear_cache(self):
        """Clear all cached results"""
        self.cache.clear()
        self.cache_timestamps.clear()
    
    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache statistics"""
        return {
            'cached_entries': len(self.cache),
            'recent_requests': len(self.request_times)
        }

