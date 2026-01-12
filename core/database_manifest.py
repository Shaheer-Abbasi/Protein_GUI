"""
Database manifest management for the Database Downloads page.

This module loads and validates the databases_manifest.json file which
serves as the single source of truth for available database downloads.
"""

import json
import os
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from enum import Enum


class DistributionType(Enum):
    """Types of database distribution methods"""
    S3 = "s3"
    EXTERNAL = "external"
    INSTALLER = "installer"


class InstallerKind(Enum):
    """Types of installer tools supported"""
    NCBI_BLAST_UPDATE = "ncbi_blast_update"
    MMSEQS_CREATEDB = "mmseqs_createdb"


@dataclass
class S3Distribution:
    """S3/CloudFront download distribution"""
    url: str
    sha256: str
    compressed: bool = True
    
    @classmethod
    def from_dict(cls, data: dict) -> 'S3Distribution':
        return cls(
            url=data.get('url', ''),
            sha256=data.get('sha256', ''),
            compressed=data.get('compressed', True)
        )


@dataclass
class ExternalDistribution:
    """External link distribution (NCBI, UniProt, etc.)"""
    url: str
    notes: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: dict) -> 'ExternalDistribution':
        return cls(
            url=data.get('url', ''),
            notes=data.get('notes')
        )


@dataclass
class InstallerDistribution:
    """Tool-based installer distribution"""
    installer_kind: str
    params: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'InstallerDistribution':
        return cls(
            installer_kind=data.get('installer_kind', ''),
            params=data.get('params', {})
        )


@dataclass
class DatabaseEntry:
    """A single database entry from the manifest"""
    id: str
    display_name: str
    description: str
    tool_formats: List[str]  # ["blast"], ["mmseqs"], or ["blast", "mmseqs"]
    size_gb: float
    disk_required_gb: float
    last_updated: str  # ISO date string
    version: str
    distribution_type: DistributionType
    distribution: Any  # S3Distribution, ExternalDistribution, or InstallerDistribution
    category: str = "full"  # "starter" or "full"
    
    @classmethod
    def from_dict(cls, data: dict) -> 'DatabaseEntry':
        """Create DatabaseEntry from dictionary"""
        dist_data = data.get('distribution', {})
        dist_type_str = dist_data.get('type', 'external')
        
        try:
            dist_type = DistributionType(dist_type_str)
        except ValueError:
            dist_type = DistributionType.EXTERNAL
        
        if dist_type == DistributionType.S3:
            distribution = S3Distribution.from_dict(dist_data)
        elif dist_type == DistributionType.INSTALLER:
            distribution = InstallerDistribution.from_dict(dist_data)
        else:
            distribution = ExternalDistribution.from_dict(dist_data)
        
        return cls(
            id=data.get('id', ''),
            display_name=data.get('display_name', ''),
            description=data.get('description', ''),
            tool_formats=data.get('tool_formats', []),
            size_gb=data.get('size_gb', 0.0),
            disk_required_gb=data.get('disk_required_gb', 0.0),
            last_updated=data.get('last_updated', ''),
            version=data.get('version', ''),
            distribution_type=dist_type,
            distribution=distribution,
            category=data.get('category', 'full')
        )
    
    def is_starter_pack(self) -> bool:
        """Check if this is a starter pack (S3 hosted)"""
        return self.category == "starter" or self.distribution_type == DistributionType.S3
    
    def supports_blast(self) -> bool:
        return "blast" in self.tool_formats
    
    def supports_mmseqs(self) -> bool:
        return "mmseqs" in self.tool_formats
    
    def get_size_display(self) -> str:
        """Get human-readable size string"""
        if self.size_gb < 1:
            return f"{int(self.size_gb * 1024)} MB"
        return f"{self.size_gb:.1f} GB"
    
    def get_disk_required_display(self) -> str:
        """Get human-readable disk requirement string"""
        if self.disk_required_gb < 1:
            return f"{int(self.disk_required_gb * 1024)} MB"
        return f"{self.disk_required_gb:.1f} GB"


@dataclass
class DatabaseManifest:
    """The full database manifest"""
    version: str
    last_updated: str
    manifest_url: str  # URL to fetch updates from
    databases: List[DatabaseEntry]
    
    @classmethod
    def from_dict(cls, data: dict) -> 'DatabaseManifest':
        databases = [DatabaseEntry.from_dict(db) for db in data.get('databases', [])]
        return cls(
            version=data.get('version', '1.0.0'),
            last_updated=data.get('last_updated', ''),
            manifest_url=data.get('manifest_url', ''),
            databases=databases
        )
    
    def get_starter_packs(self) -> List[DatabaseEntry]:
        """Get databases categorized as starter packs"""
        return [db for db in self.databases if db.is_starter_pack()]
    
    def get_full_databases(self) -> List[DatabaseEntry]:
        """Get databases categorized as full (large)"""
        return [db for db in self.databases if not db.is_starter_pack()]
    
    def get_by_id(self, db_id: str) -> Optional[DatabaseEntry]:
        """Get a database entry by ID"""
        for db in self.databases:
            if db.id == db_id:
                return db
        return None
    
    def get_blast_databases(self) -> List[DatabaseEntry]:
        """Get all databases that support BLAST"""
        return [db for db in self.databases if db.supports_blast()]
    
    def get_mmseqs_databases(self) -> List[DatabaseEntry]:
        """Get all databases that support MMseqs2"""
        return [db for db in self.databases if db.supports_mmseqs()]


class ManifestLoader:
    """Loads and caches the database manifest"""
    
    # Default manifest URL for Sen Lab protein databases
    DEFAULT_MANIFEST_URL = "https://sen-lab-protein-databases.s3.us-east-2.amazonaws.com/databases_manifest.json"
    
    # Cache duration in hours
    CACHE_TTL_HOURS = 24
    
    def __init__(self, cache_dir: Optional[str] = None):
        """
        Initialize the manifest loader.
        
        Args:
            cache_dir: Directory to cache the manifest. Defaults to app config dir.
        """
        if cache_dir is None:
            # Use app's config directory
            script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            cache_dir = script_dir
        
        self.cache_dir = cache_dir
        self.cache_file = os.path.join(cache_dir, 'databases_manifest_cache.json')
        self.local_manifest_file = os.path.join(cache_dir, 'databases_manifest.json')
        self._manifest: Optional[DatabaseManifest] = None
    
    def load(self, force_refresh: bool = False) -> DatabaseManifest:
        """
        Load the database manifest.
        
        Priority:
        1. If force_refresh, fetch from remote
        2. If cache is fresh (< TTL), use cache
        3. Try to fetch from remote
        4. Fall back to cache (even if stale)
        5. Fall back to local bundled manifest
        
        Args:
            force_refresh: Force fetching from remote
            
        Returns:
            DatabaseManifest object
        """
        if self._manifest is not None and not force_refresh:
            return self._manifest
        
        manifest_data = None
        
        # Check cache freshness
        cache_is_fresh = self._is_cache_fresh()
        
        if not force_refresh and cache_is_fresh:
            manifest_data = self._load_from_cache()
        
        if manifest_data is None and (force_refresh or not cache_is_fresh):
            # Try to fetch from remote
            manifest_data = self._fetch_from_remote()
            if manifest_data is not None:
                self._save_to_cache(manifest_data)
        
        if manifest_data is None:
            # Fall back to stale cache
            manifest_data = self._load_from_cache()
        
        if manifest_data is None:
            # Fall back to local bundled manifest
            manifest_data = self._load_local_manifest()
        
        if manifest_data is None:
            # Create empty manifest
            manifest_data = {
                'version': '0.0.0',
                'last_updated': datetime.now().isoformat(),
                'manifest_url': self.DEFAULT_MANIFEST_URL,
                'databases': []
            }
        
        self._manifest = DatabaseManifest.from_dict(manifest_data)
        return self._manifest
    
    def _is_cache_fresh(self) -> bool:
        """Check if the cached manifest is still fresh"""
        if not os.path.exists(self.cache_file):
            return False
        
        try:
            cache_mtime = os.path.getmtime(self.cache_file)
            cache_age = datetime.now() - datetime.fromtimestamp(cache_mtime)
            return cache_age < timedelta(hours=self.CACHE_TTL_HOURS)
        except OSError:
            return False
    
    def _load_from_cache(self) -> Optional[dict]:
        """Load manifest from cache file"""
        if not os.path.exists(self.cache_file):
            return None
        
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None
    
    def _save_to_cache(self, data: dict):
        """Save manifest data to cache file"""
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except IOError:
            pass  # Cache save failure is not critical
    
    def _fetch_from_remote(self) -> Optional[dict]:
        """Fetch manifest from remote URL"""
        # First, check if we have a manifest_url in the local manifest
        manifest_url = self.DEFAULT_MANIFEST_URL
        
        local_data = self._load_local_manifest()
        if local_data and local_data.get('manifest_url'):
            manifest_url = local_data['manifest_url']
        
        try:
            request = urllib.request.Request(
                manifest_url,
                headers={'User-Agent': 'ProteinGUI/1.0'}
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))
                return data
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError):
            return None
    
    def _load_local_manifest(self) -> Optional[dict]:
        """Load the bundled local manifest file"""
        if not os.path.exists(self.local_manifest_file):
            return None
        
        try:
            with open(self.local_manifest_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None
    
    def get_manifest_age(self) -> Optional[str]:
        """Get human-readable age of the cached manifest"""
        if not os.path.exists(self.cache_file):
            return None
        
        try:
            cache_mtime = os.path.getmtime(self.cache_file)
            cache_age = datetime.now() - datetime.fromtimestamp(cache_mtime)
            
            if cache_age.days > 0:
                return f"{cache_age.days} day(s) ago"
            elif cache_age.seconds >= 3600:
                hours = cache_age.seconds // 3600
                return f"{hours} hour(s) ago"
            elif cache_age.seconds >= 60:
                minutes = cache_age.seconds // 60
                return f"{minutes} minute(s) ago"
            else:
                return "just now"
        except OSError:
            return None


# Global manifest loader instance
_manifest_loader: Optional[ManifestLoader] = None


def get_manifest_loader() -> ManifestLoader:
    """Get the global manifest loader instance"""
    global _manifest_loader
    if _manifest_loader is None:
        _manifest_loader = ManifestLoader()
    return _manifest_loader


def load_database_manifest(force_refresh: bool = False) -> DatabaseManifest:
    """Convenience function to load the database manifest"""
    return get_manifest_loader().load(force_refresh=force_refresh)
