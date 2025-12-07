"""Centralized configuration manager for Protein-GUI"""
import json
import os


class ConfigManager:
    """Manages application configuration across different machines"""
    
    def __init__(self, config_path="config.json"):
        self.config_path = config_path
        self.config = self._load_config()
    
    def _load_config(self):
        """Load configuration from file, return defaults if not found"""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Warning: Could not load config: {e}")
                return self._get_defaults()
        else:
            # First time setup - notify user
            print("=" * 60)
            print("⚠️  config.json not found!")
            print("=" * 60)
            print("This appears to be your first time running on this machine.")
            print("Please run: python setup_wizard.py")
            print("=" * 60)
            return self._get_defaults()
    
    def _get_defaults(self):
        """Return default configuration"""
        return {
            "blast_path": "blastp",  # Assume in PATH
            "mmseqs_path": "mmseqs",  # Assume in PATH
            "mmseqs_available": False,
            "blastdbcmd_available": False,
            "databases_found": []
        }
    
    def get(self, key, default=None):
        """Get configuration value"""
        return self.config.get(key, default)
    
    def set(self, key, value):
        """Set configuration value"""
        self.config[key] = value
    
    def save(self):
        """Save configuration to file"""
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
            return False
    
    def get_blast_path(self):
        """Get BLAST executable path"""
        return self.config.get('blast_path', 'blastp')
    
    def get_mmseqs_path(self):
        """Get MMSeqs2 executable path"""
        return self.config.get('mmseqs_path', 'mmseqs')
    
    def get_project_root(self):
        """Get the project root directory (where config.json is located)"""
        return os.path.dirname(os.path.abspath(self.config_path))
    
    def get_blast_db_dir(self):
        """Get the BLAST database directory relative to project root"""
        root = self.get_project_root()
        return os.path.join(root, 'blast_databases')
    
    def get_mmseqs_db_dir(self):
        """Get the MMSeqs2 database directory relative to project root"""
        root = self.get_project_root()
        return os.path.join(root, 'mmseqs_databases')


# Global config instance
_config_instance = None

def get_config():
    """Get global configuration instance"""
    global _config_instance
    if _config_instance is None:
        _config_instance = ConfigManager()
    return _config_instance

