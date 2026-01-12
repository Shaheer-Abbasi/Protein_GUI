"""
Tracker for installed databases.

Maintains a local JSON file that records which databases have been
installed, their versions, and installation paths.
"""

import os
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict


@dataclass
class InstalledDatabase:
    """Record of an installed database"""
    id: str
    display_name: str
    version: str
    install_path: str
    installed_date: str  # ISO format
    tool_formats: List[str]
    size_gb: float
    source_type: str  # "s3", "external", "installer"
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'InstalledDatabase':
        return cls(
            id=data.get('id', ''),
            display_name=data.get('display_name', ''),
            version=data.get('version', ''),
            install_path=data.get('install_path', ''),
            installed_date=data.get('installed_date', ''),
            tool_formats=data.get('tool_formats', []),
            size_gb=data.get('size_gb', 0.0),
            source_type=data.get('source_type', 'unknown')
        )
    
    def is_valid(self) -> bool:
        """Check if the installed database path still exists"""
        return os.path.exists(self.install_path)
    
    def get_installed_date_display(self) -> str:
        """Get human-readable installation date"""
        try:
            dt = datetime.fromisoformat(self.installed_date)
            return dt.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return self.installed_date


class InstalledDatabasesTracker:
    """
    Manages the installed_databases.json file.
    
    This file tracks:
    - Which databases are installed
    - Where they are located
    - What version is installed
    - When they were installed
    """
    
    def __init__(self, config_dir: Optional[str] = None):
        """
        Initialize the tracker.
        
        Args:
            config_dir: Directory to store the tracking file.
                       Defaults to app's config directory.
        """
        if config_dir is None:
            script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            config_dir = script_dir
        
        self.config_dir = config_dir
        self.tracking_file = os.path.join(config_dir, 'installed_databases.json')
        self._databases: Dict[str, InstalledDatabase] = {}
        self._load()
    
    def _load(self):
        """Load the tracking file"""
        if not os.path.exists(self.tracking_file):
            self._databases = {}
            return
        
        try:
            with open(self.tracking_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self._databases = {
                    db_id: InstalledDatabase.from_dict(db_data)
                    for db_id, db_data in data.get('databases', {}).items()
                }
        except (json.JSONDecodeError, IOError):
            self._databases = {}
    
    def _save(self):
        """Save the tracking file"""
        data = {
            'version': '1.0',
            'last_updated': datetime.now().isoformat(),
            'databases': {
                db_id: db.to_dict()
                for db_id, db in self._databases.items()
            }
        }
        
        try:
            os.makedirs(self.config_dir, exist_ok=True)
            with open(self.tracking_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except IOError as e:
            print(f"Warning: Could not save installed databases tracker: {e}")
    
    def add(
        self,
        db_id: str,
        display_name: str,
        version: str,
        install_path: str,
        tool_formats: List[str],
        size_gb: float,
        source_type: str
    ):
        """
        Record a newly installed database.
        
        Args:
            db_id: Database identifier
            display_name: Human-readable name
            version: Version string
            install_path: Path where database is installed
            tool_formats: List of supported tools (e.g., ["blast", "mmseqs"])
            size_gb: Approximate size in GB
            source_type: How it was installed ("s3", "external", "installer")
        """
        self._databases[db_id] = InstalledDatabase(
            id=db_id,
            display_name=display_name,
            version=version,
            install_path=install_path,
            installed_date=datetime.now().isoformat(),
            tool_formats=tool_formats,
            size_gb=size_gb,
            source_type=source_type
        )
        self._save()
    
    def remove(self, db_id: str) -> bool:
        """
        Remove a database from tracking.
        
        Note: This does NOT delete the actual files.
        
        Args:
            db_id: Database identifier to remove
            
        Returns:
            True if removed, False if not found
        """
        if db_id in self._databases:
            del self._databases[db_id]
            self._save()
            return True
        return False
    
    def get(self, db_id: str) -> Optional[InstalledDatabase]:
        """Get an installed database by ID"""
        return self._databases.get(db_id)
    
    def get_all(self) -> List[InstalledDatabase]:
        """Get all installed databases"""
        return list(self._databases.values())
    
    def is_installed(self, db_id: str) -> bool:
        """Check if a database is installed"""
        db = self._databases.get(db_id)
        if db is None:
            return False
        # Also verify the path still exists
        return db.is_valid()
    
    def get_installed_version(self, db_id: str) -> Optional[str]:
        """Get the installed version of a database"""
        db = self._databases.get(db_id)
        if db and db.is_valid():
            return db.version
        return None
    
    def has_update_available(self, db_id: str, latest_version: str) -> bool:
        """Check if an update is available for an installed database"""
        installed_version = self.get_installed_version(db_id)
        if installed_version is None:
            return False
        return installed_version != latest_version
    
    def get_blast_databases(self) -> List[InstalledDatabase]:
        """Get all installed BLAST databases"""
        return [
            db for db in self._databases.values()
            if 'blast' in db.tool_formats and db.is_valid()
        ]
    
    def get_mmseqs_databases(self) -> List[InstalledDatabase]:
        """Get all installed MMseqs2 databases"""
        return [
            db for db in self._databases.values()
            if 'mmseqs' in db.tool_formats and db.is_valid()
        ]
    
    def cleanup_invalid(self) -> int:
        """
        Remove entries for databases whose paths no longer exist.
        
        Returns:
            Number of entries removed
        """
        invalid_ids = [
            db_id for db_id, db in self._databases.items()
            if not db.is_valid()
        ]
        
        for db_id in invalid_ids:
            del self._databases[db_id]
        
        if invalid_ids:
            self._save()
        
        return len(invalid_ids)
    
    def get_total_size_gb(self) -> float:
        """Get total size of all installed databases in GB"""
        return sum(db.size_gb for db in self._databases.values() if db.is_valid())


# Global tracker instance
_tracker: Optional[InstalledDatabasesTracker] = None


def get_installed_databases_tracker() -> InstalledDatabasesTracker:
    """Get the global installed databases tracker"""
    global _tracker
    if _tracker is None:
        _tracker = InstalledDatabasesTracker()
    return _tracker
