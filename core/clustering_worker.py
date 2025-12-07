"""Worker thread for running MMseqs2 clustering via WSL"""
import subprocess
import tempfile
import os
import shutil
from PyQt5.QtCore import QThread, pyqtSignal

from core.wsl_utils import run_wsl_command, windows_path_to_wsl, WSLError


class ClusteringWorker(QThread):
    """Worker thread to run MMseqs2 clustering without freezing the GUI"""
    progress = pyqtSignal(int, str)  # percentage, message
    finished = pyqtSignal(dict, str, str)  # stats, rep_fasta_path, tsv_path
    error = pyqtSignal(str)
    
    def __init__(self, fasta_path, mode, min_seq_id, coverage, cov_mode, evalue, 
                 sensitivity=None, kmer_per_seq=None, single_step=False):
        super().__init__()
        self.fasta_path = fasta_path
        self.mode = mode  # 'cluster' or 'linclust'
        self.min_seq_id = min_seq_id
        self.coverage = coverage
        self.cov_mode = cov_mode
        self.evalue = evalue
        self.sensitivity = sensitivity
        self.kmer_per_seq = kmer_per_seq
        self.single_step = single_step
        self.cancelled = False
    
    def cancel(self):
        """Cancel the clustering operation"""
        self.cancelled = True
    
    def run(self):
        temp_dir_windows = None
        
        try:
            # Create temporary directory for MMseqs2 work
            temp_dir_windows = tempfile.mkdtemp(prefix='mmseqs_cluster_')
            temp_dir_wsl = windows_path_to_wsl(temp_dir_windows)
            
            # Convert paths to WSL
            fasta_wsl = windows_path_to_wsl(self.fasta_path)
            db_wsl = f"{temp_dir_wsl}/DB"
            clu_wsl = f"{temp_dir_wsl}/DB_clu"
            tmp_wsl = f"{temp_dir_wsl}/tmp"
            tsv_wsl = f"{temp_dir_wsl}/DB_clu.tsv"
            rep_db_wsl = f"{temp_dir_wsl}/DB_clu_rep"
            rep_fasta_wsl = f"{temp_dir_wsl}/DB_clu_rep.fasta"
            
            # Create tmp folder
            tmp_folder_windows = os.path.join(temp_dir_windows, 'tmp')
            os.makedirs(tmp_folder_windows, exist_ok=True)
            
            if self.cancelled:
                return
            
            # Step 1: Create database (0-20%)
            self.progress.emit(5, "Creating MMseqs2 database from FASTA file...")
            cmd_createdb = f'mmseqs createdb "{fasta_wsl}" "{db_wsl}"'
            result = run_wsl_command(cmd_createdb, timeout=300)
            
            if result.returncode != 0:
                self.error.emit(f"Error creating database:\n{result.stderr}")
                return
            
            self.progress.emit(20, "Database created successfully")
            
            if self.cancelled:
                return
            
            # Step 2: Run clustering (20-60%)
            self.progress.emit(25, f"Running {self.mode} clustering (this may take a while)...")
            
            # Build clustering command based on mode
            if self.mode == "linclust":
                cmd_cluster = f'mmseqs linclust "{db_wsl}" "{clu_wsl}" "{tmp_wsl}"'
                if self.kmer_per_seq:
                    cmd_cluster += f' --kmer-per-seq {self.kmer_per_seq}'
            else:
                cmd_cluster = f'mmseqs cluster "{db_wsl}" "{clu_wsl}" "{tmp_wsl}"'
                if self.single_step:
                    cmd_cluster += ' --single-step-clustering'
            
            # Add common parameters
            cmd_cluster += f' --min-seq-id {self.min_seq_id}'
            cmd_cluster += f' -c {self.coverage}'
            cmd_cluster += f' --cov-mode {self.cov_mode}'
            cmd_cluster += f' -e {self.evalue}'
            
            if self.sensitivity is not None:
                cmd_cluster += f' -s {self.sensitivity}'
            
            result = run_wsl_command(cmd_cluster, timeout=1800)  # 30 minute timeout
            
            if result.returncode != 0:
                self.error.emit(f"Clustering error:\n{result.stderr}\n\nStdout:\n{result.stdout}")
                return
            
            self.progress.emit(60, "Clustering complete")
            
            if self.cancelled:
                return
            
            # Step 3: Create TSV (60-75%)
            self.progress.emit(65, "Extracting clustering results to TSV format...")
            cmd_createtsv = f'mmseqs createtsv "{db_wsl}" "{db_wsl}" "{clu_wsl}" "{tsv_wsl}"'
            result = run_wsl_command(cmd_createtsv, timeout=300)
            
            if result.returncode != 0:
                self.error.emit(f"Error creating TSV:\n{result.stderr}")
                return
            
            self.progress.emit(75, "Results extracted to TSV")
            
            if self.cancelled:
                return
            
            # Step 4: Create representative database (75-85%)
            self.progress.emit(80, "Extracting representative sequences...")
            cmd_createsubdb = f'mmseqs createsubdb "{clu_wsl}" "{db_wsl}" "{rep_db_wsl}"'
            result = run_wsl_command(cmd_createsubdb, timeout=300)
            
            if result.returncode != 0:
                self.error.emit(f"Error creating representative database:\n{result.stderr}")
                return
            
            self.progress.emit(85, "Representatives extracted")
            
            if self.cancelled:
                return
            
            # Step 5: Convert to FASTA (85-95%)
            self.progress.emit(90, "Converting representatives to FASTA format...")
            cmd_convert2fasta = f'mmseqs convert2fasta "{rep_db_wsl}" "{rep_fasta_wsl}"'
            result = run_wsl_command(cmd_convert2fasta, timeout=300)
            
            if result.returncode != 0:
                self.error.emit(f"Error converting to FASTA:\n{result.stderr}")
                return
            
            self.progress.emit(95, "Conversion complete")
            
            # Parse results
            tsv_windows = os.path.join(temp_dir_windows, 'DB_clu.tsv')
            rep_fasta_windows = os.path.join(temp_dir_windows, 'DB_clu_rep.fasta')
            
            if not os.path.exists(tsv_windows):
                self.error.emit("Clustering completed but TSV file not found")
                return
            
            if not os.path.exists(rep_fasta_windows):
                self.error.emit("Clustering completed but representative FASTA file not found")
                return
            
            # Import here to avoid circular imports
            from core.clustering_manager import parse_clustering_results
            
            self.progress.emit(98, "Parsing results and generating statistics...")
            stats = parse_clustering_results(tsv_windows)
            
            self.progress.emit(100, "Clustering complete!")
            
            self.finished.emit(stats, rep_fasta_windows, tsv_windows)
            
        except subprocess.TimeoutExpired:
            self.error.emit("Clustering operation timed out. Please try with a smaller dataset or adjust parameters.")
        except WSLError as e:
            self.error.emit(f"WSL error: {str(e)}")
        except Exception as e:
            import traceback
            self.error.emit(f"Error: {str(e)}\n\n{traceback.format_exc()}")
        finally:
            # Note: We don't cleanup temp_dir here because we need the files for results
            # Cleanup will be handled by the UI after user exports/views results
            pass

