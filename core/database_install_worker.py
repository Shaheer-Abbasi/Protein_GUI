"""
Background worker for installing databases (cross-platform).

On Windows: runs tools through WSL.
On macOS/Linux: runs tools natively.

Supports:
- NCBI BLAST update_blastdb.pl
- MMseqs2 database creation from FASTA
- Custom installer scripts
"""

import os
import subprocess
import re
from typing import Optional, Dict, Any
from PyQt5.QtCore import QThread, pyqtSignal

from core.database_manifest import DatabaseEntry, InstallerDistribution, DistributionType
from core.wsl_utils import (
    is_windows,
    is_wsl_available, convert_path_for_tool, run_wsl_command, 
    WSLError, check_wsl_command, warmup_wsl,
    run_command_live, get_platform_tool_install_hint,
    get_platform_name
)


class InstallError(Exception):
    """Exception raised for installation errors"""
    pass


class DatabaseInstallWorker(QThread):
    """
    Worker thread for installing databases.
    
    Signals:
        progress(int, int, str): (current_step, total_steps, status_message)
        log(str): Log message for display (supports ANSI-stripped output)
        finished(str): Emitted on success with the final database path
        error(str): Emitted on error with error message
    """
    
    progress = pyqtSignal(int, int, str)
    log = pyqtSignal(str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    
    def __init__(
        self,
        database_entry: DatabaseEntry,
        destination_dir: str,
        parent=None
    ):
        super().__init__(parent)
        self.database_entry = database_entry
        self.destination_dir = destination_dir
        self._cancelled = False
        self._process: Optional[subprocess.Popen] = None
    
    def cancel(self):
        """Request cancellation of the installation"""
        self._cancelled = True
        if self._process is not None:
            try:
                self._process.terminate()
            except Exception:
                pass
    
    def run(self):
        """Execute the installation in a background thread"""
        try:
            self._do_install()
        except Exception as e:
            if not self._cancelled:
                self.error.emit(str(e))
    
    def _do_install(self):
        """Main installation logic"""
        if self.database_entry.distribution_type != DistributionType.INSTALLER:
            self.error.emit("This worker only handles installer-based databases")
            return
        
        distribution: InstallerDistribution = self.database_entry.distribution
        installer_kind = distribution.installer_kind
        
        # Check environment availability
        if not is_wsl_available():
            if is_windows():
                self.error.emit(
                    "WSL (Windows Subsystem for Linux) is not available.\n"
                    "Please install WSL to use this installation method."
                )
            else:
                self.error.emit(
                    "Required tools are not available. Please check your installation."
                )
            return
        
        # Warm up WSL (no-op on non-Windows)
        self.log.emit(f"Initializing on {get_platform_name()}...")
        warmup_wsl()
        
        if installer_kind == "ncbi_blast_update":
            self._install_blast_database(distribution.params)
        elif installer_kind == "mmseqs_createdb":
            self._install_mmseqs_database(distribution.params)
        else:
            self.error.emit(f"Unknown installer type: {installer_kind}")
    
    def _install_blast_database(self, params: Dict[str, Any]):
        """Install a BLAST database using update_blastdb.pl"""
        db_name = params.get('db_name', self.database_entry.id)
        
        self.log.emit(f"Installing BLAST database: {db_name}")
        self.log.emit(f"This may take a while for large databases...")
        
        exists, path = check_wsl_command('update_blastdb.pl')
        if not exists:
            self.error.emit(
                "update_blastdb.pl not found.\n"
                + get_platform_tool_install_hint('blast+')
            )
            return
        
        db_dest_dir = os.path.join(self.destination_dir, db_name)
        os.makedirs(db_dest_dir, exist_ok=True)
        
        tool_dest_dir = convert_path_for_tool(db_dest_dir)
        
        cmd = f"cd '{tool_dest_dir}' && update_blastdb.pl --decompress {db_name}"
        
        self.log.emit(f"Destination: {db_dest_dir}")
        self.log.emit(f"Running: update_blastdb.pl --decompress {db_name}")
        self.log.emit("-" * 50)
        
        self._run_command_live(cmd)
        
        if self._cancelled:
            return
        
        # Verify installation
        expected_files = [f"{db_name}.pal", f"{db_name}.pin", f"{db_name}.phr"]
        found_any = False
        for ext in expected_files:
            check_path = os.path.join(db_dest_dir, ext)
            pattern_path = os.path.join(db_dest_dir, f"{db_name}.00.pin")
            if os.path.exists(check_path) or os.path.exists(pattern_path):
                found_any = True
                break
        
        if not found_any:
            for f in os.listdir(db_dest_dir):
                if f.endswith('.pin') or f.endswith('.nal') or f.endswith('.pal'):
                    found_any = True
                    break
        
        if found_any:
            self.log.emit("-" * 50)
            self.log.emit(f"BLAST database installed successfully!")
            self.log.emit(f"Location: {db_dest_dir}")
            self.finished.emit(db_dest_dir)
        else:
            self.error.emit(
                f"Installation may have failed. "
                f"Expected database files not found in {db_dest_dir}"
            )
    
    def _install_mmseqs_database(self, params: Dict[str, Any]):
        """Create/download an MMseqs2 database"""
        db_name = params.get('db_name', self.database_entry.id)
        source_url = params.get('source_url', '')
        source_type = params.get('source_type', 'download')
        
        self.log.emit(f"Setting up MMseqs2 database: {db_name}")
        
        exists, path = check_wsl_command('mmseqs')
        if not exists:
            self.error.emit(
                "MMseqs2 not found.\n"
                + get_platform_tool_install_hint('mmseqs')
            )
            return
        
        db_dest_dir = os.path.join(self.destination_dir, db_name)
        os.makedirs(db_dest_dir, exist_ok=True)
        
        tool_dest_dir = convert_path_for_tool(db_dest_dir)
        db_path = f"{tool_dest_dir}/{db_name}"
        
        self.log.emit(f"Destination: {db_dest_dir}")
        
        if source_type == 'download' and source_url:
            self.log.emit(f"Downloading from: {source_url}")
            cmd = f"cd '{tool_dest_dir}' && wget -c '{source_url}' -O db.tar.gz && tar xzf db.tar.gz && rm db.tar.gz"
        else:
            self.log.emit(f"Downloading {db_name} using mmseqs databases...")
            tmp_dir = f"{tool_dest_dir}/tmp"
            cmd = f"mkdir -p '{tmp_dir}' && mmseqs databases {db_name} '{db_path}' '{tmp_dir}' --remove-tmp-files 1"
        
        self.log.emit("-" * 50)
        self._run_command_live(cmd)
        
        if self._cancelled:
            return
        
        db_files_found = False
        for f in os.listdir(db_dest_dir):
            if f.endswith('.dbtype') or f.endswith('.index'):
                db_files_found = True
                break
        
        if db_files_found:
            self.log.emit("-" * 50)
            self.log.emit(f"MMseqs2 database installed successfully!")
            self.log.emit(f"Location: {db_dest_dir}")
            self.finished.emit(db_dest_dir)
        else:
            self.error.emit(
                f"Installation may have failed. "
                f"Expected database files not found in {db_dest_dir}"
            )
    
    def _run_command_live(self, command: str):
        """Run a command with live output streaming (cross-platform)"""
        try:
            self._process = run_command_live(command)
            
            for line in iter(self._process.stdout.readline, ''):
                if self._cancelled:
                    self._process.terminate()
                    return
                
                clean_line = self._strip_ansi(line.rstrip())
                if clean_line:
                    self.log.emit(clean_line)
            
            self._process.wait()
            
            if self._process.returncode != 0 and not self._cancelled:
                self.error.emit(f"Command exited with code {self._process.returncode}")
                
        except Exception as e:
            if not self._cancelled:
                raise InstallError(f"Failed to run command: {str(e)}")
        finally:
            self._process = None
    
    @staticmethod
    def _strip_ansi(text: str) -> str:
        """Remove ANSI escape codes from text"""
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)
