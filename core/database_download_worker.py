"""
Background worker for downloading databases from S3/HTTP sources.

Handles:
- HTTP/HTTPS downloads with progress
- SHA256 verification
- Archive extraction (zip, tar.gz, tar.zst)
- Resumable downloads (partial support)
"""

import os
import urllib.request
import urllib.error
import zipfile
import tarfile
import tempfile
import shutil
from typing import Optional
from PyQt5.QtCore import QThread, pyqtSignal

from core.database_manifest import DatabaseEntry, S3Distribution, DistributionType
from utils.hash_utils import calculate_sha256, HashVerificationError


class DownloadError(Exception):
    """Exception raised for download errors"""
    pass


class DatabaseDownloadWorker(QThread):
    """
    Worker thread for downloading databases from S3/HTTP sources.
    
    Signals:
        progress(int, int, str): (bytes_downloaded, total_bytes, status_message)
        log(str): Log message for display
        finished(str): Emitted on success with the final database path
        error(str): Emitted on error with error message
    """
    
    progress = pyqtSignal(int, int, str)  # bytes_downloaded, total_bytes, status
    log = pyqtSignal(str)
    finished = pyqtSignal(str)  # final_path
    error = pyqtSignal(str)
    
    # Chunk size for downloads (1 MB)
    CHUNK_SIZE = 1024 * 1024
    
    def __init__(
        self,
        database_entry: DatabaseEntry,
        destination_dir: str,
        parent=None
    ):
        """
        Initialize the download worker.
        
        Args:
            database_entry: The DatabaseEntry to download
            destination_dir: Directory where database should be installed
        """
        super().__init__(parent)
        self.database_entry = database_entry
        self.destination_dir = destination_dir
        self._cancelled = False
    
    def cancel(self):
        """Request cancellation of the download"""
        self._cancelled = True
    
    def run(self):
        """Execute the download in a background thread"""
        try:
            self._do_download()
        except Exception as e:
            if not self._cancelled:
                self.error.emit(str(e))
    
    def _do_download(self):
        """Main download logic"""
        if self.database_entry.distribution_type != DistributionType.S3:
            self.error.emit("This worker only handles S3/HTTP downloads")
            return
        
        distribution: S3Distribution = self.database_entry.distribution
        
        # Create destination directory
        db_dest_dir = os.path.join(
            self.destination_dir,
            self.database_entry.id,
            self.database_entry.version
        )
        os.makedirs(db_dest_dir, exist_ok=True)
        
        self.log.emit(f"Starting download of {self.database_entry.display_name}")
        self.log.emit(f"Version: {self.database_entry.version}")
        self.log.emit(f"Destination: {db_dest_dir}")
        
        # Determine filename from URL
        url = distribution.url
        filename = os.path.basename(url.split('?')[0])  # Remove query params
        if not filename:
            filename = f"{self.database_entry.id}.zip"
        
        download_path = os.path.join(db_dest_dir, filename)
        
        # Download the file
        self.log.emit(f"Downloading from: {url}")
        self._download_file(url, download_path)
        
        if self._cancelled:
            self._cleanup(download_path)
            return
        
        # Verify checksum
        if distribution.sha256:
            self.log.emit("Verifying checksum...")
            self.progress.emit(0, 100, "Verifying SHA256 checksum...")
            
            if not self._verify_checksum(download_path, distribution.sha256):
                self._cleanup(download_path)
                self.error.emit("Checksum verification failed! The download may be corrupted.")
                return
            
            self.log.emit("✓ Checksum verified successfully")
        
        if self._cancelled:
            self._cleanup(download_path)
            return
        
        # Extract if compressed
        final_path = db_dest_dir
        if distribution.compressed:
            self.log.emit("Extracting archive...")
            self.progress.emit(0, 100, "Extracting files...")
            
            try:
                final_path = self._extract_archive(download_path, db_dest_dir)
                self.log.emit(f"✓ Extracted to: {final_path}")
                
                # Remove the archive after successful extraction
                os.remove(download_path)
            except Exception as e:
                self.error.emit(f"Extraction failed: {str(e)}")
                return
        
        if self._cancelled:
            return
        
        self.log.emit(f"✓ Download complete!")
        self.log.emit(f"Database installed to: {final_path}")
        self.finished.emit(final_path)
    
    def _download_file(self, url: str, dest_path: str):
        """Download a file with progress reporting"""
        try:
            request = urllib.request.Request(
                url,
                headers={
                    'User-Agent': 'ProteinGUI/1.0',
                    'Accept': '*/*'
                }
            )
            
            with urllib.request.urlopen(request, timeout=30) as response:
                total_size = int(response.headers.get('Content-Length', 0))
                downloaded = 0
                
                self.log.emit(f"File size: {self._format_size(total_size)}")
                
                with open(dest_path, 'wb') as f:
                    while True:
                        if self._cancelled:
                            return
                        
                        chunk = response.read(self.CHUNK_SIZE)
                        if not chunk:
                            break
                        
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        # Report progress
                        percent = (downloaded / total_size * 100) if total_size > 0 else 0
                        status = f"Downloading: {self._format_size(downloaded)} / {self._format_size(total_size)} ({percent:.1f}%)"
                        self.progress.emit(downloaded, total_size, status)
                
        except urllib.error.HTTPError as e:
            raise DownloadError(f"HTTP Error {e.code}: {e.reason}")
        except urllib.error.URLError as e:
            raise DownloadError(f"URL Error: {e.reason}")
        except TimeoutError:
            raise DownloadError("Connection timed out")
    
    def _verify_checksum(self, filepath: str, expected_hash: str) -> bool:
        """Verify file checksum with progress"""
        def progress_callback(bytes_read: int, total_bytes: int):
            if total_bytes > 0:
                percent = bytes_read / total_bytes * 100
                self.progress.emit(
                    bytes_read, total_bytes,
                    f"Verifying checksum: {percent:.1f}%"
                )
        
        calculated = calculate_sha256(filepath, progress_callback=progress_callback)
        return calculated.lower() == expected_hash.lower()
    
    def _extract_archive(self, archive_path: str, dest_dir: str) -> str:
        """Extract an archive file"""
        lower_path = archive_path.lower()
        
        if lower_path.endswith('.zip'):
            return self._extract_zip(archive_path, dest_dir)
        elif lower_path.endswith('.tar.gz') or lower_path.endswith('.tgz'):
            return self._extract_tar(archive_path, dest_dir, 'gz')
        elif lower_path.endswith('.tar.zst') or lower_path.endswith('.tzst'):
            return self._extract_tar_zst(archive_path, dest_dir)
        elif lower_path.endswith('.tar'):
            return self._extract_tar(archive_path, dest_dir, None)
        else:
            # Not compressed, return as-is
            return dest_dir
    
    def _extract_zip(self, archive_path: str, dest_dir: str) -> str:
        """Extract a ZIP archive"""
        with zipfile.ZipFile(archive_path, 'r') as zf:
            total_files = len(zf.namelist())
            for i, member in enumerate(zf.namelist()):
                if self._cancelled:
                    return dest_dir
                
                zf.extract(member, dest_dir)
                self.progress.emit(
                    i + 1, total_files,
                    f"Extracting: {i + 1}/{total_files} files"
                )
        
        return dest_dir
    
    def _extract_tar(self, archive_path: str, dest_dir: str, compression: Optional[str]) -> str:
        """Extract a TAR archive (optionally gzipped)"""
        mode = 'r'
        if compression == 'gz':
            mode = 'r:gz'
        elif compression == 'bz2':
            mode = 'r:bz2'
        
        with tarfile.open(archive_path, mode) as tf:
            members = tf.getmembers()
            total_files = len(members)
            for i, member in enumerate(members):
                if self._cancelled:
                    return dest_dir
                
                tf.extract(member, dest_dir)
                self.progress.emit(
                    i + 1, total_files,
                    f"Extracting: {i + 1}/{total_files} files"
                )
        
        return dest_dir
    
    def _extract_tar_zst(self, archive_path: str, dest_dir: str) -> str:
        """Extract a Zstandard-compressed TAR archive"""
        try:
            import zstandard as zstd
        except ImportError:
            raise DownloadError(
                "Zstandard (zstd) decompression not available. "
                "Please install the 'zstandard' Python package."
            )
        
        # Decompress to temp file, then extract
        temp_tar = tempfile.mktemp(suffix='.tar')
        try:
            with open(archive_path, 'rb') as compressed:
                dctx = zstd.ZstdDecompressor()
                with open(temp_tar, 'wb') as output:
                    dctx.copy_stream(compressed, output)
            
            # Now extract the tar
            return self._extract_tar(temp_tar, dest_dir, None)
        finally:
            if os.path.exists(temp_tar):
                os.remove(temp_tar)
    
    def _cleanup(self, filepath: str):
        """Clean up partial downloads"""
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except OSError:
                pass
    
    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """Format bytes as human-readable string"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
