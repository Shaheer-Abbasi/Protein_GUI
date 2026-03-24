"""Worker thread for running MMseqs2 clustering (cross-platform)"""
import subprocess
import tempfile
import os
import shutil
from PyQt5.QtCore import QThread, pyqtSignal

from core.tool_runtime import ToolRuntimeError, get_tool_runtime
from core.wsl_utils import WSLError


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
        temp_dir = None
        
        try:
            temp_dir = tempfile.mkdtemp(prefix='mmseqs_cluster_')
            runtime = get_tool_runtime()
            resolution = runtime.resolve_tool("mmseqs")
            if not resolution.executable:
                self.error.emit("MMseqs2 is not available. Install it from the app or configure a valid executable path.")
                return
            temp_dir_tool = runtime.prepare_path(resolution, temp_dir)
            
            fasta_tool = runtime.prepare_path(resolution, self.fasta_path)
            db_tool = f"{temp_dir_tool}/DB"
            clu_tool = f"{temp_dir_tool}/DB_clu"
            tmp_tool = f"{temp_dir_tool}/tmp"
            tsv_tool = f"{temp_dir_tool}/DB_clu.tsv"
            rep_db_tool = f"{temp_dir_tool}/DB_clu_rep"
            rep_fasta_tool = f"{temp_dir_tool}/DB_clu_rep.fasta"
            
            tmp_folder = os.path.join(temp_dir, 'tmp')
            os.makedirs(tmp_folder, exist_ok=True)
            
            if self.cancelled:
                return
            
            # Step 1: Create database (0-20%)
            self.progress.emit(5, "Creating MMseqs2 database from FASTA file...")
            result = runtime.run_resolved(
                resolution,
                ["createdb", fasta_tool, db_tool],
                timeout=300,
            )
            
            if result.returncode != 0:
                self.error.emit(f"Error creating database:\n{result.stderr}")
                return
            
            self.progress.emit(20, "Database created successfully")
            
            if self.cancelled:
                return
            
            # Step 2: Run clustering (20-60%)
            self.progress.emit(25, f"Running {self.mode} clustering (this may take a while)...")
            
            if self.mode == "linclust":
                cmd_cluster = ["linclust", db_tool, clu_tool, tmp_tool]
                if self.kmer_per_seq:
                    cmd_cluster.extend(["--kmer-per-seq", str(self.kmer_per_seq)])
            else:
                cmd_cluster = ["cluster", db_tool, clu_tool, tmp_tool]
                if self.single_step:
                    cmd_cluster.append("--single-step-clustering")
            
            cmd_cluster.extend(["--min-seq-id", str(self.min_seq_id)])
            cmd_cluster.extend(["-c", str(self.coverage)])
            cmd_cluster.extend(["--cov-mode", str(self.cov_mode)])
            cmd_cluster.extend(["-e", str(self.evalue)])
            
            if self.sensitivity is not None and self.mode != "linclust":
                cmd_cluster.extend(["-s", str(self.sensitivity)])
            
            result = runtime.run_resolved(resolution, cmd_cluster, timeout=1800)
            
            if result.returncode != 0:
                self.error.emit(f"Clustering error:\n{result.stderr}\n\nStdout:\n{result.stdout}")
                return
            
            self.progress.emit(60, "Clustering complete")
            
            if self.cancelled:
                return
            
            # Step 3: Create TSV (60-75%)
            self.progress.emit(65, "Extracting clustering results to TSV format...")
            result = runtime.run_resolved(
                resolution,
                ["createtsv", db_tool, db_tool, clu_tool, tsv_tool],
                timeout=300,
            )
            
            if result.returncode != 0:
                self.error.emit(f"Error creating TSV:\n{result.stderr}")
                return
            
            self.progress.emit(75, "Results extracted to TSV")
            
            if self.cancelled:
                return
            
            # Step 4: Create representative database (75-85%)
            self.progress.emit(80, "Extracting representative sequences...")
            result = runtime.run_resolved(
                resolution,
                ["createsubdb", clu_tool, db_tool, rep_db_tool],
                timeout=300,
            )
            
            if result.returncode != 0:
                self.error.emit(f"Error creating representative database:\n{result.stderr}")
                return
            
            self.progress.emit(85, "Representatives extracted")
            
            if self.cancelled:
                return
            
            # Step 5: Convert to FASTA (85-95%)
            self.progress.emit(90, "Converting representatives to FASTA format...")
            result = runtime.run_resolved(
                resolution,
                ["convert2fasta", rep_db_tool, rep_fasta_tool],
                timeout=300,
            )
            
            if result.returncode != 0:
                self.error.emit(f"Error converting to FASTA:\n{result.stderr}")
                return
            
            self.progress.emit(95, "Conversion complete")
            
            # Parse results
            tsv_path = os.path.join(temp_dir, 'DB_clu.tsv')
            rep_fasta_path = os.path.join(temp_dir, 'DB_clu_rep.fasta')
            
            if not os.path.exists(tsv_path):
                self.error.emit("Clustering completed but TSV file not found")
                return
            
            if not os.path.exists(rep_fasta_path):
                self.error.emit("Clustering completed but representative FASTA file not found")
                return
            
            from core.clustering_manager import parse_clustering_results
            
            self.progress.emit(98, "Parsing results and generating statistics...")
            stats = parse_clustering_results(tsv_path)
            
            self.progress.emit(100, "Clustering complete!")
            
            self.finished.emit(stats, rep_fasta_path, tsv_path)
            
        except subprocess.TimeoutExpired:
            self.error.emit("Clustering operation timed out. Please try with a smaller dataset or adjust parameters.")
        except (WSLError, ToolRuntimeError) as e:
            self.error.emit(f"Execution error: {str(e)}")
        except Exception as e:
            import traceback
            self.error.emit(f"Error: {str(e)}\n\n{traceback.format_exc()}")
        finally:
            pass
