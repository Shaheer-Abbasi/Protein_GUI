"""Worker thread for running Clustal Omega alignments via WSL"""
import os
import tempfile
import uuid
from PyQt5.QtCore import QThread, pyqtSignal

from core.wsl_utils import (
    is_wsl_available, 
    check_wsl_command, 
    run_wsl_command, 
    windows_path_to_wsl,
    WSLError,
    warmup_wsl
)


class AlignmentError(Exception):
    """Custom exception for alignment errors"""
    pass


def check_clustalo_installation():
    """
    Check if Clustal Omega is installed in WSL.
    
    Returns:
        tuple: (installed: bool, version: str or None, path: str or None)
    """
    if not is_wsl_available():
        return False, None, None
    
    # Warm up WSL first
    warmup_wsl()
    
    exists, path = check_wsl_command('clustalo')
    if not exists:
        return False, None, None
    
    try:
        result = run_wsl_command(['clustalo', '--version'], timeout=30)
        if result.returncode == 0:
            version = result.stdout.strip()
            return True, version, path
    except WSLError:
        pass
    
    return True, None, path


class AlignmentWorker(QThread):
    """
    Worker thread for running Clustal Omega alignments.
    
    Runs alignments via WSL to leverage Linux-native Clustal Omega.
    """
    
    # Signals
    progress = pyqtSignal(int, str)  # percent, message
    finished = pyqtSignal(str, str)  # aligned_fasta_content, output_file_path
    error = pyqtSignal(str)  # error message
    
    # Alignment parameters
    DEFAULT_TIMEOUT = 600  # 10 minutes
    MAX_SEQUENCES = 2000  # Maximum sequences to prevent hanging
    
    def __init__(self, input_fasta_path, output_format='fasta', 
                 iterations=0, full_iter=False, force=True, threads=None):
        """
        Initialize alignment worker.
        
        Args:
            input_fasta_path: Path to input FASTA file (Windows path)
            output_format: Output format ('fasta', 'clustal', 'msf', 'phylip', 'selex', 'stockholm', 'vienna')
            iterations: Number of iterations (0 = auto)
            full_iter: Use full iterative refinement
            force: Force overwrite of output file
            threads: Number of threads (None = auto)
        """
        super().__init__()
        
        self.input_fasta_path = input_fasta_path
        self.output_format = output_format
        self.iterations = iterations
        self.full_iter = full_iter
        self.force = force
        self.threads = threads
        
        self._cancelled = False
        self._temp_files = []
    
    def cancel(self):
        """Cancel the alignment"""
        self._cancelled = True
    
    def run(self):
        """Run the alignment"""
        output_path = None
        
        try:
            self.progress.emit(0, "Preparing alignment...")
            
            # Validate input
            if not os.path.exists(self.input_fasta_path):
                raise AlignmentError(f"Input file not found: {self.input_fasta_path}")
            
            # Count sequences and validate
            seq_count = self._count_sequences()
            if seq_count < 2:
                raise AlignmentError("At least 2 sequences are required for alignment")
            
            if seq_count > self.MAX_SEQUENCES:
                raise AlignmentError(
                    f"Too many sequences ({seq_count}). Maximum is {self.MAX_SEQUENCES}.\n"
                    "Consider reducing the number of sequences or using a different tool."
                )
            
            self.progress.emit(10, f"Found {seq_count} sequences. Copying to WSL...")
            
            if self._cancelled:
                return
            
            # Copy input file to WSL temp directory
            wsl_input_path = self._copy_to_wsl_temp()
            
            self.progress.emit(20, "Running Clustal Omega alignment...")
            
            if self._cancelled:
                return
            
            # Run Clustal Omega
            wsl_output_path = self._run_clustalo(wsl_input_path, seq_count)
            
            self.progress.emit(80, "Reading alignment results...")
            
            if self._cancelled:
                return
            
            # Read the output
            aligned_content = self._read_wsl_output(wsl_output_path)
            
            # Save to a Windows temp file (not tracked for cleanup - caller owns it)
            output_path = self._save_output(aligned_content)
            
            self.progress.emit(100, "Alignment complete!")
            
            self.finished.emit(aligned_content, output_path)
            
        except AlignmentError as e:
            self._cleanup_windows_output(output_path)
            self.error.emit(str(e))
        except Exception as e:
            self._cleanup_windows_output(output_path)
            self.error.emit(f"Unexpected error: {str(e)}")
        finally:
            # Always clean up WSL temp files
            self._cleanup_wsl_temp_files()
    
    def _count_sequences(self):
        """Count sequences in the input FASTA file"""
        count = 0
        try:
            with open(self.input_fasta_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith('>'):
                        count += 1
        except Exception as e:
            raise AlignmentError(f"Error reading input file: {str(e)}")
        return count
    
    def _copy_to_wsl_temp(self):
        """Copy input file to WSL /tmp directory"""
        # Generate unique filename
        unique_id = str(uuid.uuid4())[:8]
        wsl_input_path = f"/tmp/alignment_input_{unique_id}.fasta"
        
        # Read the Windows file
        try:
            with open(self.input_fasta_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            raise AlignmentError(f"Error reading input file: {str(e)}")
        
        # Write to WSL temp using bash
        # Escape single quotes in content
        escaped_content = content.replace("'", "'\\''")
        
        try:
            result = run_wsl_command(
                f"cat > '{wsl_input_path}' << 'FASTA_EOF'\n{content}\nFASTA_EOF",
                timeout=60
            )
            if result.returncode != 0:
                raise AlignmentError(f"Failed to copy file to WSL: {result.stderr}")
        except WSLError as e:
            raise AlignmentError(f"WSL error: {str(e)}")
        
        self._temp_files.append(('wsl', wsl_input_path))
        return wsl_input_path
    
    def _run_clustalo(self, wsl_input_path, seq_count):
        """Run Clustal Omega alignment"""
        unique_id = str(uuid.uuid4())[:8]
        wsl_output_path = f"/tmp/alignment_output_{unique_id}.aln"
        
        # Build command
        cmd_parts = [
            'clustalo',
            '-i', wsl_input_path,
            '-o', wsl_output_path,
            f'--outfmt={self.output_format}'
        ]
        
        if self.force:
            cmd_parts.append('--force')
        
        if self.iterations > 0:
            cmd_parts.extend(['--iterations', str(self.iterations)])
        
        if self.full_iter:
            cmd_parts.append('--full-iter')
        
        if self.threads:
            cmd_parts.extend(['--threads', str(self.threads)])
        
        # Add verbose output for progress tracking
        cmd_parts.append('--verbose')
        
        cmd = ' '.join(cmd_parts)
        
        # Estimate timeout based on sequence count
        timeout = max(self.DEFAULT_TIMEOUT, seq_count * 2)
        
        try:
            result = run_wsl_command(cmd, timeout=timeout)
            
            if result.returncode != 0:
                error_msg = result.stderr if result.stderr else result.stdout
                raise AlignmentError(f"Clustal Omega failed:\n{error_msg}")
                
        except WSLError as e:
            if "timed out" in str(e).lower():
                raise AlignmentError(
                    f"Alignment timed out after {timeout} seconds.\n"
                    "Try reducing the number of sequences or increasing the timeout."
                )
            raise AlignmentError(f"WSL error: {str(e)}")
        
        self._temp_files.append(('wsl', wsl_output_path))
        return wsl_output_path
    
    def _read_wsl_output(self, wsl_output_path):
        """Read the alignment output from WSL"""
        try:
            result = run_wsl_command(f"cat '{wsl_output_path}'", timeout=60)
            
            if result.returncode != 0:
                raise AlignmentError(f"Failed to read output: {result.stderr}")
            
            return result.stdout
            
        except WSLError as e:
            raise AlignmentError(f"Error reading output: {str(e)}")
    
    def _save_output(self, content):
        """Save alignment output to Windows temp file"""
        # Determine file extension based on format
        ext_map = {
            'fasta': '.fasta',
            'clustal': '.aln',
            'msf': '.msf',
            'phylip': '.phy',
            'selex': '.slx',
            'stockholm': '.sto',
            'vienna': '.vie'
        }
        ext = ext_map.get(self.output_format, '.aln')
        
        # Create temp file
        fd, output_path = tempfile.mkstemp(suffix=ext, prefix='alignment_')
        
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(content)
        except Exception as e:
            raise AlignmentError(f"Error saving output: {str(e)}")
        
        # Note: Don't add to _temp_files - caller owns this file
        return output_path
    
    def _cleanup_wsl_temp_files(self):
        """Clean up WSL temporary files only"""
        for file_type, path in self._temp_files:
            if file_type == 'wsl':
                try:
                    run_wsl_command(f"rm -f '{path}'", timeout=10)
                except:
                    pass  # Best effort cleanup
        
        self._temp_files = []
    
    def _cleanup_windows_output(self, output_path):
        """Clean up Windows output file on error"""
        if output_path and os.path.exists(output_path):
            try:
                os.remove(output_path)
            except:
                pass  # Best effort cleanup
    
    def _cleanup_temp_files(self):
        """Clean up all temporary files (legacy method for compatibility)"""
        self._cleanup_wsl_temp_files()


class SequenceAlignmentPrep:
    """Helper class for preparing sequences for alignment"""
    
    @staticmethod
    def prepare_from_hits(hits, output_path):
        """
        Prepare a FASTA file from search hits for alignment.
        
        Args:
            hits: List of SearchHit objects with 'id' and 'sequence' attributes
            output_path: Path to write the FASTA file
            
        Returns:
            tuple: (success: bool, message: str, sequence_count: int)
        """
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                count = 0
                for hit in hits:
                    if hasattr(hit, 'sequence') and hit.sequence:
                        # Clean the sequence
                        seq = hit.sequence.replace(' ', '').replace('\n', '')
                        
                        # Get identifier
                        hit_id = getattr(hit, 'id', None) or getattr(hit, 'accession', f'seq_{count+1}')
                        
                        # Write FASTA entry
                        f.write(f">{hit_id}\n")
                        
                        # Write sequence in 80-character lines
                        for i in range(0, len(seq), 80):
                            f.write(seq[i:i+80] + '\n')
                        
                        count += 1
            
            if count < 2:
                return False, "At least 2 sequences with retrieved sequences are required", count
            
            return True, f"Prepared {count} sequences for alignment", count
            
        except Exception as e:
            return False, f"Error preparing sequences: {str(e)}", 0
    
    @staticmethod
    def validate_fasta_for_alignment(fasta_path):
        """
        Validate a FASTA file for alignment.
        
        Returns:
            tuple: (is_valid: bool, message: str, sequence_count: int)
        """
        if not os.path.exists(fasta_path):
            return False, "File not found", 0
        
        try:
            count = 0
            max_len = 0
            min_len = float('inf')
            
            current_seq = []
            
            with open(fasta_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('>'):
                        if current_seq:
                            seq_len = len(''.join(current_seq))
                            max_len = max(max_len, seq_len)
                            min_len = min(min_len, seq_len)
                            current_seq = []
                        count += 1
                    elif line:
                        current_seq.append(line)
                
                # Don't forget the last sequence
                if current_seq:
                    seq_len = len(''.join(current_seq))
                    max_len = max(max_len, seq_len)
                    min_len = min(min_len, seq_len)
            
            if count < 2:
                return False, "At least 2 sequences are required for alignment", count
            
            if count > AlignmentWorker.MAX_SEQUENCES:
                return False, f"Too many sequences ({count}). Maximum is {AlignmentWorker.MAX_SEQUENCES}", count
            
            return True, f"{count} sequences (length range: {min_len}-{max_len} aa)", count
            
        except Exception as e:
            return False, f"Error reading file: {str(e)}", 0

