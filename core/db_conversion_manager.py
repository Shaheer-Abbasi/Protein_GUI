"""Database conversion status tracking and management"""
import json
import os
from datetime import datetime
from pathlib import Path


class DatabaseConversionManager:
    """Manages conversion status of databases"""
    
    def __init__(self, status_file="mmseqs_databases/conversion_status.json"):
        """Initialize the conversion manager
        
        Args:
            status_file: Path to JSON file storing conversion status
        """
        self.status_file = status_file
        self.status_data = self._load_status()
    
    def _load_status(self):
        """Load conversion status from JSON file"""
        if os.path.exists(self.status_file):
            try:
                with open(self.status_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        
        return {"databases": {}, "last_updated": None}
    
    def _save_status(self):
        """Save conversion status to JSON file"""
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.status_file) if os.path.dirname(self.status_file) else '.', exist_ok=True)
        
        self.status_data["last_updated"] = datetime.now().isoformat()
        
        try:
            with open(self.status_file, 'w') as f:
                json.dump(self.status_data, f, indent=2)
        except IOError as e:
            print(f"Warning: Could not save conversion status: {e}")
    
    def get_database_status(self, db_name):
        """Get conversion status for a database
        
        Args:
            db_name: Name of the database
            
        Returns:
            dict with keys: status, converted_path, converted_date, source_path
            status can be: 'not_converted', 'converting', 'converted', 'failed'
        """
        if db_name in self.status_data["databases"]:
            return self.status_data["databases"][db_name]
        
        return {
            "status": "not_converted",
            "converted_path": None,
            "converted_date": None,
            "source_path": None,
            "error": None
        }
    
    def is_converted(self, db_name):
        """Check if a database is converted and ready to use
        
        Args:
            db_name: Name of the database
            
        Returns:
            bool: True if converted and MMseqs2 db exists
        """
        status = self.get_database_status(db_name)
        if status["status"] != "converted":
            return False
        
        # Verify the converted database still exists
        converted_path = status.get("converted_path")
        if converted_path and os.path.exists(converted_path):
            return True
        
        # If path doesn't exist, mark as not converted
        if db_name in self.status_data["databases"]:
            self.status_data["databases"][db_name]["status"] = "not_converted"
            self._save_status()
        
        return False
    
    def is_converting(self, db_name):
        """Check if a database is currently being converted"""
        status = self.get_database_status(db_name)
        return status["status"] == "converting"
    
    def mark_converting(self, db_name, source_path, target_path):
        """Mark a database as currently converting
        
        Args:
            db_name: Name of the database
            source_path: Path to source BLAST database
            target_path: Target path for MMseqs2 database
        """
        self.status_data["databases"][db_name] = {
            "status": "converting",
            "converted_path": target_path,
            "converted_date": None,
            "source_path": source_path,
            "error": None,
            "conversion_started": datetime.now().isoformat()
        }
        self._save_status()
    
    def mark_converted(self, db_name, converted_path):
        """Mark a database as successfully converted
        
        Args:
            db_name: Name of the database
            converted_path: Path to converted MMseqs2 database
        """
        if db_name in self.status_data["databases"]:
            self.status_data["databases"][db_name]["status"] = "converted"
            self.status_data["databases"][db_name]["converted_path"] = converted_path
            self.status_data["databases"][db_name]["converted_date"] = datetime.now().isoformat()
            self.status_data["databases"][db_name]["error"] = None
            
            # Remove conversion_started timestamp
            if "conversion_started" in self.status_data["databases"][db_name]:
                del self.status_data["databases"][db_name]["conversion_started"]
        else:
            self.status_data["databases"][db_name] = {
                "status": "converted",
                "converted_path": converted_path,
                "converted_date": datetime.now().isoformat(),
                "source_path": None,
                "error": None
            }
        
        self._save_status()
    
    def mark_failed(self, db_name, error_message):
        """Mark a database conversion as failed
        
        Args:
            db_name: Name of the database
            error_message: Error message describing the failure
        """
        if db_name in self.status_data["databases"]:
            self.status_data["databases"][db_name]["status"] = "failed"
            self.status_data["databases"][db_name]["error"] = error_message
            self.status_data["databases"][db_name]["failed_date"] = datetime.now().isoformat()
            
            # Remove conversion_started timestamp
            if "conversion_started" in self.status_data["databases"][db_name]:
                del self.status_data["databases"][db_name]["conversion_started"]
        
        self._save_status()
    
    def reset_status(self, db_name):
        """Reset conversion status for a database (for retry)
        
        Args:
            db_name: Name of the database
        """
        if db_name in self.status_data["databases"]:
            self.status_data["databases"][db_name]["status"] = "not_converted"
            self.status_data["databases"][db_name]["error"] = None
            if "failed_date" in self.status_data["databases"][db_name]:
                del self.status_data["databases"][db_name]["failed_date"]
            if "conversion_started" in self.status_data["databases"][db_name]:
                del self.status_data["databases"][db_name]["conversion_started"]
            self._save_status()
    
    def get_converted_databases(self):
        """Get list of all converted databases
        
        Returns:
            list: List of database names that are converted
        """
        converted = []
        for db_name, info in self.status_data["databases"].items():
            if info["status"] == "converted":
                # Verify file exists
                if info.get("converted_path") and os.path.exists(info["converted_path"]):
                    converted.append(db_name)
        return converted
    
    def delete_converted_database(self, db_name):
        """Delete a converted database and its status
        
        Args:
            db_name: Name of the database
            
        Returns:
            bool: True if deleted successfully
        """
        if db_name not in self.status_data["databases"]:
            return False
        
        status = self.status_data["databases"][db_name]
        converted_path = status.get("converted_path")
        
        # Delete the MMseqs2 database files
        if converted_path:
            try:
                # MMseqs2 creates multiple files with extensions
                base_path = Path(converted_path)
                parent_dir = base_path.parent
                base_name = base_path.name
                
                # Delete all files starting with the database name
                for file in parent_dir.glob(f"{base_name}*"):
                    try:
                        file.unlink()
                    except OSError:
                        pass
            except Exception as e:
                print(f"Warning: Could not delete database files: {e}")
        
        # Remove from status
        del self.status_data["databases"][db_name]
        self._save_status()
        
        return True
    
    def get_all_statuses(self):
        """Get status information for all databases
        
        Returns:
            dict: Database name -> status info
        """
        return self.status_data["databases"].copy()

