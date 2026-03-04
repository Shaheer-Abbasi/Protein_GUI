"""Worker thread for converting BLAST databases to MMseqs2 format (cross-platform)"""
import os
import subprocess
import tempfile
import shutil
from PyQt5.QtCore import QThread, pyqtSignal

from core.wsl_utils import (
    is_windows,
    is_wsl_available,
    convert_path_for_tool,
    run_wsl_command,
    WSLError,
    get_disk_space_wsl,
    get_platform_tool_install_hint
)


class DatabaseConversionWorker(QThread):
    """Worker thread to convert BLAST database to MMseqs2 format"""
    
    progress = pyqtSignal(str, int)  # (message, percentage)
    finished = pyqtSignal(str, str)  # (db_name, mmseqs_db_path)
    error = pyqtSignal(str, str)  # (db_name, error_message)
    
    def __init__(self, db_name, blast_db_path, output_dir):
        """Initialize the conversion worker
        
        Args:
            db_name: Name of the database
            blast_db_path: Path to BLAST database (without extension)
            output_dir: Path to output directory for MMseqs2 database
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
            # Check environment availability
            if not is_wsl_available():
                if is_windows():
                    self.error.emit(
                        self.db_name,
                        "WSL is not available. Please install Windows Subsystem for Linux.\n\n"
                        "You can use BLAST search instead, or install WSL to use MMseqs2."
                    )
                else:
                    self.error.emit(
                        self.db_name,
                        "Required tools are not available on your system.\n\n"
                        + get_platform_tool_install_hint('blastdbcmd') + "\n\n"
                        + get_platform_tool_install_hint('mmseqs')
                    )
                return
            
            if self._cancelled:
                self.error.emit(self.db_name, "Conversion cancelled by user")
                return
            
            # Step 1: Check disk space
            self.progress.emit("Checking disk space...", 5)
            
            check_path = convert_path_for_tool(self.output_dir) if is_windows() else self.output_dir
            available, total = get_disk_space_wsl(check_path)
            if available is not None and available < 1_000_000_000:
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
            
            temp_dir = os.path.join(self.output_dir, f'.temp_{self.db_name}')
            os.makedirs(temp_dir, exist_ok=True)
            temp_fasta_native = os.path.join(temp_dir, f'{self.db_name}.fasta')
            
            blast_db_tool = convert_path_for_tool(self.blast_db_path)
            temp_fasta_tool = convert_path_for_tool(temp_fasta_native)
            
            # Run blastdbcmd to extract FASTA
            self.progress.emit("Running blastdbcmd to extract sequences...", 20)
            
            blastdbcmd_cmd = f'blastdbcmd -db "{blast_db_tool}" -entry all -out "{temp_fasta_tool}"'
            
            try:
                result = run_wsl_command(blastdbcmd_cmd, timeout=3600)
                
                if result.returncode != 0:
                    error_msg = result.stderr if result.stderr else "Unknown error"
                    
                    if "not found" in error_msg or "No such file" in error_msg:
                        self.error.emit(
                            self.db_name,
                            f"BLAST database not found: {self.blast_db_path}\n\n"
                            "Please ensure the BLAST database files exist."
                        )
                    elif "blastdbcmd" in error_msg and "command not found" in error_msg:
                        self.error.emit(
                            self.db_name,
                            "blastdbcmd not found.\n\n"
                            + get_platform_tool_install_hint('blastdbcmd')
                        )
                    else:
                        self.error.emit(
                            self.db_name,
                            f"Failed to extract sequences from BLAST database:\n\n{error_msg}"
                        )
                    return
            except WSLError as e:
                self.error.emit(self.db_name, f"Command failed:\n\n{str(e)}")
                return
            
            if self._cancelled:
                self._cleanup_temp_files(temp_dir)
                self.error.emit(self.db_name, "Conversion cancelled by user")
                return
            
            if not os.path.exists(temp_fasta_native):
                self.error.emit(
                    self.db_name,
                    "Failed to create FASTA file. The extraction may have failed."
                )
                return
            
            fasta_size = os.path.getsize(temp_fasta_native)
            if fasta_size == 0:
                self.error.emit(
                    self.db_name,
                    "Extracted FASTA file is empty. The BLAST database may be corrupted or empty."
                )
                self._cleanup_temp_files(temp_dir)
                return
            
            self.progress.emit(
                f"Extracted {fasta_size / 1_000_000:.1f} MB of sequences",
                40
            )
            
            if self._cancelled:
                self._cleanup_temp_files(temp_dir)
                self.error.emit(self.db_name, "Conversion cancelled by user")
                return
            
            # Step 3: Convert FASTA to MMseqs2 database
            self.progress.emit("Converting to MMseqs2 format...", 50)
            
            mmseqs_db_native = os.path.join(self.output_dir, self.db_name)
            mmseqs_db_tool = convert_path_for_tool(mmseqs_db_native)
            
            if os.path.exists(mmseqs_db_native):
                self.progress.emit("Removing old database...", 45)
                self._delete_mmseqs_database(mmseqs_db_native)
            
            self.progress.emit("Creating MMseqs2 database...", 60)
            
            mmseqs_cmd = f'mmseqs createdb "{temp_fasta_tool}" "{mmseqs_db_tool}"'
            
            try:
                result = run_wsl_command(mmseqs_cmd, timeout=3600)
                
                if result.returncode != 0:
                    error_msg = result.stderr if result.stderr else "Unknown error"
                    
                    if "mmseqs" in error_msg and "command not found" in error_msg:
                        self.error.emit(
                            self.db_name,
                            "MMseqs2 not found.\n\n"
                            + get_platform_tool_install_hint('mmseqs')
                        )
                    else:
                        self.error.emit(
                            self.db_name,
                            f"Failed to create MMseqs2 database:\n\n{error_msg}"
                        )
                    return
            except WSLError as e:
                self.error.emit(self.db_name, f"Command failed:\n\n{str(e)}")
                return
            
            if self._cancelled:
                self._cleanup_temp_files(temp_dir)
                self._delete_mmseqs_database(mmseqs_db_native)
                self.error.emit(self.db_name, "Conversion cancelled by user")
                return
            
            if not os.path.exists(mmseqs_db_native):
                self.error.emit(
                    self.db_name,
                    "Failed to create MMseqs2 database. The conversion may have failed."
                )
                self._cleanup_temp_files(temp_dir)
                return
            
            # Step 4: Cleanup temp files
            self.progress.emit("Cleaning up temporary files...", 90)
            self._cleanup_temp_files(temp_dir)
            
            # Step 5: Done!
            self.progress.emit("Conversion complete!", 100)
            self.finished.emit(self.db_name, mmseqs_db_native)
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            self.error.emit(
                self.db_name,
                f"Unexpected error during conversion:\n\n{str(e)}\n\n{error_details}"
            )
            
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
            
            for file in parent_dir.glob(f"{base_name}*"):
                try:
                    file.unlink()
                except OSError:
                    pass
        except Exception as e:
            print(f"Warning: Could not delete MMseqs2 database files: {e}")
