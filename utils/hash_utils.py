"""
Hash verification utilities for database downloads.

Provides SHA256 checksum verification for downloaded files.
"""

import hashlib
import os
from typing import Optional, Callable


def calculate_sha256(
    filepath: str,
    chunk_size: int = 8192 * 1024,  # 8MB chunks
    progress_callback: Optional[Callable[[int, int], None]] = None
) -> str:
    """
    Calculate SHA256 hash of a file.
    
    Args:
        filepath: Path to the file
        chunk_size: Size of chunks to read at a time
        progress_callback: Optional callback(bytes_read, total_bytes) for progress
        
    Returns:
        Hex-encoded SHA256 hash string
    """
    sha256_hash = hashlib.sha256()
    file_size = os.path.getsize(filepath)
    bytes_read = 0
    
    with open(filepath, 'rb') as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            sha256_hash.update(chunk)
            bytes_read += len(chunk)
            
            if progress_callback:
                progress_callback(bytes_read, file_size)
    
    return sha256_hash.hexdigest()


def verify_sha256(filepath: str, expected_hash: str, progress_callback: Optional[Callable[[int, int], None]] = None) -> bool:
    """
    Verify a file's SHA256 hash matches the expected value.
    
    Args:
        filepath: Path to the file to verify
        expected_hash: Expected SHA256 hash (hex string, case-insensitive)
        progress_callback: Optional callback(bytes_read, total_bytes) for progress
        
    Returns:
        True if hash matches, False otherwise
    """
    if not os.path.exists(filepath):
        return False
    
    calculated = calculate_sha256(filepath, progress_callback=progress_callback)
    return calculated.lower() == expected_hash.lower()


def get_file_hash_info(filepath: str) -> dict:
    """
    Get hash information for a file.
    
    Args:
        filepath: Path to the file
        
    Returns:
        Dictionary with 'sha256', 'size_bytes', and 'filename' keys
    """
    if not os.path.exists(filepath):
        return {
            'sha256': None,
            'size_bytes': 0,
            'filename': os.path.basename(filepath),
            'exists': False
        }
    
    return {
        'sha256': calculate_sha256(filepath),
        'size_bytes': os.path.getsize(filepath),
        'filename': os.path.basename(filepath),
        'exists': True
    }


class HashVerificationError(Exception):
    """Raised when hash verification fails"""
    
    def __init__(self, filepath: str, expected: str, actual: str):
        self.filepath = filepath
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"Hash verification failed for {filepath}. "
            f"Expected: {expected}, Got: {actual}"
        )
