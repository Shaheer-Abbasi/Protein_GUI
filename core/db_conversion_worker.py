"""Worker thread for converting BLAST databases to MMseqs2 format"""
import os
import subprocess
import tempfile
import shutil
from PyQt5.QtCore import QThread, pyqtSignal

from core.wsl_utils import (
    is_wsl_available,
    windows_path_to_wsl,
    run_wsl_command,
    WSLError,
    get_disk_space_wsl
)


class DatabaseConversionWorker(QThread):
    """Worker thread to convert BLAST database to MMseqs2 format"""
    
    # Signals
    progress = pyqtSignal(str, int)  # (message, percentage)
    finished = pyqtSignal(str, str)  # (db_name, mmseqs_db_path)
    error = pyqtSignal(str, str)  # (db_name, error_message)
    
    def __init__(self, db_name, blast_db_path, output_dir):
        """Initialize the conversion worker
        
        Args:
            db_name: Name of the database
            blast_db_path: Windows path to BLAST database (without extension)
            output_dir: Windows path to output directory for MMseqs2 database
        """
        super().__init__()
        self.db_name = db_name
        self.blast_db_path = blast_db_path
        self.output_dir = output_dir
        self._cancelled = False
    
    def cancel(self):
        """Cancel the conversion process"""
        self._cancelled = True
    
    def run(self):
        """Run the conversion process"""
        temp_fasta = None
        
        try:
            # Check WSL availability
            if not is_wsl_available():
                self.error.emit(
                    self.db_name,
                    "WSL is not available. Please install Windows Subsystem for Linux.\n\n"
                    "You can use BLAST search instead, or install WSL to use MMseqs2."
                )
                return
            
            # Check if conversion was cancelled
            if self._cancelled:
                self.error.emit(self.db_name, "Conversion cancelled by user")
                return
            
            # Step 1: Check disk space
            self.progress.emit("Checking disk space...", 5)
            output_dir_wsl = windows_path_to_wsl(self.output_dir)
            
            available, total = get_disk_space_wsl(output_dir_wsl)
            if available is not None and available < 1_000_000_000:  # Less than 1GB
                self.error.emit(
                    self.db_name,
                    f"Insufficient disk space. Available: {available / 1_000_000_000:.2f} GB\n\n"
                    "Please free up disk space and try again."
                )
                return
            
            if self._cancelled:
                self.error.emit(self.db_name, "Conversion cancelled by user")
                return
            
            # Step 2: Convert BLAST database to FASTA
            self.progress.emit("Extracting sequences from BLAST database...", 10)
            
            # Create temp FASTA file in WSL-accessible location
            temp_dir_windows = os.path.join(self.output_dir, f'.temp_{self.db_name}')
            os.makedirs(temp_dir_windows, exist_ok=True)
            temp_fasta_windows = os.path.join(temp_dir_windows, f'{self.db_name}.fasta')
            
            # Convert paths to WSL
            blast_db_wsl = windows_path_to_wsl(self.blast_db_path)
            temp_fasta_wsl = windows_path_to_wsl(temp_fasta_windows)
            
            # Run blastdbcmd to extract FASTA
            self.progress.emit("Running blastdbcmd to extract sequences...", 20)
            
            blastdbcmd_cmd = f'blastdbcmd -db "{blast_db_wsl}" -entry all -out "{temp_fasta_wsl}"'
            
            try:
                result = run_wsl_command(blastdbcmd_cmd, timeout=3600)  # 1 hour timeout
                
                if result.returncode != 0:
                    error_msg = result.stderr if result.stderr else "Unknown error"
                    
                    # Check for common errors
                    if "not found" in error_msg or "No such file" in error_msg:
                        self.error.emit(
                            self.db_name,
                            f"BLAST database not found: {blast_db_wsl}\n\n"
                            "Please ensure the BLAST database files exist."
                        )
                    elif "blastdbcmd" in error_msg and "command not found" in error_msg:
                        self.error.emit(
                            self.db_name,
                            "blastdbcmd not found in WSL.\n\n"
                            "Please install NCBI BLAST+ tools in WSL:\n"
                            "  sudo apt update\n"
                            "  sudo apt install ncbi-blast+"
                        )
                    else:
                        self.error.emit(
                            self.db_name,
                            f"Failed to extract sequences from BLAST database:\n\n{error_msg}"
                        )
                    return
            except WSLError as e:
                self.error.emit(self.db_name, f"WSL command failed:\n\n{str(e)}")
                return
            
            if self._cancelled:
                self._cleanup_temp_files(temp_dir_windows)
                self.error.emit(self.db_name, "Conversion cancelled by user")
                return
            
            # Verify FASTA file was created
            if not os.path.exists(temp_fasta_windows):
                self.error.emit(
                    self.db_name,
                    "Failed to create FASTA file. The extraction may have failed."
                )
                return
            
            # Check FASTA file size
            fasta_size = os.path.getsize(temp_fasta_windows)
            if fasta_size == 0:
                self.error.emit(
                    self.db_name,
                    "Extracted FASTA file is empty. The BLAST database may be corrupted or empty."
                )
                self._cleanup_temp_files(temp_dir_windows)
                return
            
            self.progress.emit(
                f"Extracted {fasta_size / 1_000_000:.1f} MB of sequences",
                40
            )
            
            if self._cancelled:
                self._cleanup_temp_files(temp_dir_windows)
                self.error.emit(self.db_name, "Conversion cancelled by user")
                return
            
            # Step 3: Convert FASTA to MMseqs2 database
            self.progress.emit("Converting to MMseqs2 format...", 50)
            
            # Output MMseqs2 database path
            mmseqs_db_windows = os.path.join(self.output_dir, self.db_name)
            mmseqs_db_wsl = windows_path_to_wsl(mmseqs_db_windows)
            
            # Delete existing MMseqs2 database if it exists
            if os.path.exists(mmseqs_db_windows):
                self.progress.emit("Removing old database...", 45)
                self._delete_mmseqs_database(mmseqs_db_windows)
            
            # Run mmseqs createdb
            self.progress.emit("Creating MMseqs2 database...", 60)
            
            mmseqs_cmd = f'mmseqs createdb "{temp_fasta_wsl}" "{mmseqs_db_wsl}"'
            
            try:
                result = run_wsl_command(mmseqs_cmd, timeout=3600)  # 1 hour timeout
                
                if result.returncode != 0:
                    error_msg = result.stderr if result.stderr else "Unknown error"
                    
                    # Check for common errors
                    if "mmseqs" in error_msg and "command not found" in error_msg:
                        self.error.emit(
                            self.db_name,
                            "MMseqs2 not found in WSL.\n\n"
                            "Please install MMseqs2 in WSL:\n"
                            "  wget https://mmseqs.com/latest/mmseqs-linux-avx2.tar.gz\n"
                            "  tar xvfz mmseqs-linux-avx2.tar.gz\n"
                            "  sudo cp mmseqs/bin/mmseqs /usr/local/bin/\n\n"
                            "Or use BLAST search instead."
                        )
                    else:
                        self.error.emit(
                            self.db_name,
                            f"Failed to create MMseqs2 database:\n\n{error_msg}"
                        )
                    return
            except WSLError as e:
                self.error.emit(self.db_name, f"WSL command failed:\n\n{str(e)}")
                return
            
            if self._cancelled:
                self._cleanup_temp_files(temp_dir_windows)
                self._delete_mmseqs_database(mmseqs_db_windows)
                self.error.emit(self.db_name, "Conversion cancelled by user")
                return
            
            # Verify MMseqs2 database was created
            if not os.path.exists(mmseqs_db_windows):
                self.error.emit(
                    self.db_name,
                    "Failed to create MMseqs2 database. The conversion may have failed."
                )
                self._cleanup_temp_files(temp_dir_windows)
                return
            
            # Step 4: Cleanup temp files
            self.progress.emit("Cleaning up temporary files...", 90)
            self._cleanup_temp_files(temp_dir_windows)
            
            # Step 5: Done!
            self.progress.emit("Conversion complete!", 100)
            # Emit Windows path (not WSL path) for status tracking
            self.finished.emit(self.db_name, mmseqs_db_windows)
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            self.error.emit(
                self.db_name,
                f"Unexpected error during conversion:\n\n{str(e)}\n\n{error_details}"
            )
            
            # Try to cleanup on error
            if temp_fasta and os.path.exists(temp_fasta):
                try:
                    os.unlink(temp_fasta)
                except:
                    pass
    
    def _cleanup_temp_files(self, temp_dir):
        """Clean up temporary files"""
        try:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception as e:
            print(f"Warning: Could not clean up temp files: {e}")
    
    def _delete_mmseqs_database(self, mmseqs_db_path):
        """Delete MMseqs2 database files (they have multiple extensions)"""
        try:
            from pathlib import Path
            base_path = Path(mmseqs_db_path)
            parent_dir = base_path.parent
            base_name = base_path.name
            
            # Delete all files starting with the database name
            for file in parent_dir.glob(f"{base_name}*"):
                try:
                    file.unlink()
                except OSError:
                    pass
        except Exception as e:
            print(f"Warning: Could not delete MMseqs2 database files: {e}")

