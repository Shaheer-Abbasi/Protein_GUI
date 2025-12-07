"""Utility functions for WSL (Windows Subsystem for Linux) integration"""
import subprocess
import os


class WSLError(Exception):
    """Custom exception for WSL-related errors"""
    pass


def warmup_wsl():
    """Warm up WSL to avoid timeout on first command after boot"""
    try:
        subprocess.run(
            ['wsl', 'echo', 'warmup'],
            capture_output=True,
            timeout=15
        )
    except:
        pass


def is_wsl_available():
    """Check if WSL is available on the system"""
    try:
        result = subprocess.run(
            ['wsl', '--status'],
            capture_output=True,
            text=True,
            timeout=15
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def check_wsl_command(command):
    """Check if a command exists in WSL
    
    Args:
        command: Command name to check (e.g., 'mmseqs', 'blastdbcmd')
        
    Returns:
        tuple: (exists: bool, path: str or None)
    """
    try:
        result = subprocess.run(
            ['wsl', 'which', command],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            return True, result.stdout.strip()
        return False, None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False, None


def run_wsl_command(command, timeout=None):
    """Run a command in WSL
    
    Args:
        command: Command to run (string or list)
        timeout: Timeout in seconds (None for no timeout)
        
    Returns:
        subprocess.CompletedProcess object
        
    Raises:
        WSLError: If WSL is not available or command fails
    """
    if not is_wsl_available():
        raise WSLError("WSL is not available on this system")
    
    if isinstance(command, str):
        cmd = ['wsl', 'bash', '-c', command]
    else:
        cmd = ['wsl'] + command
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return result
    except subprocess.TimeoutExpired as e:
        raise WSLError(f"Command timed out after {timeout} seconds") from e
    except Exception as e:
        raise WSLError(f"Failed to run WSL command: {str(e)}") from e


def windows_path_to_wsl(windows_path):
    """Convert Windows path to WSL path
    
    Args:
        windows_path: Windows path (e.g., 'E:\\Projects\\file.txt')
        
    Returns:
        WSL path (e.g., '/mnt/e/Projects/file.txt')
    """
    # Normalize path separators
    path = windows_path.replace('\\', '/')
    
    # Check if it's an absolute Windows path (e.g., E:/ or E:\)
    if len(path) >= 2 and path[1] == ':':
        drive_letter = path[0].lower()
        path_without_drive = path[2:].lstrip('/')
        return f"/mnt/{drive_letter}/{path_without_drive}"
    
    return path


def wsl_path_to_windows(wsl_path):
    """Convert WSL path to Windows path
    
    Args:
        wsl_path: WSL path (e.g., '/mnt/e/Projects/file.txt')
        
    Returns:
        Windows path (e.g., 'E:\\Projects\\file.txt')
    """
    # Check if it's a /mnt/ path
    if wsl_path.startswith('/mnt/'):
        parts = wsl_path[5:].split('/', 1)
        if len(parts) >= 1:
            drive_letter = parts[0].upper()
            remaining_path = parts[1] if len(parts) > 1 else ''
            return f"{drive_letter}:\\{remaining_path.replace('/', '\\')}"
    
    return wsl_path


def check_mmseqs_installation():
    """Check if MMseqs2 is installed in WSL
    
    Returns:
        tuple: (installed: bool, version: str or None, path: str or None)
    """
    if not is_wsl_available():
        return False, None, None
    
    # Warm up WSL once before checks
    warmup_wsl()
    
    exists, path = check_wsl_command('mmseqs')
    if not exists:
        return False, None, None
    
    try:
        result = run_wsl_command(['mmseqs', 'version'], timeout=30)
        if result.returncode == 0:
            version = result.stdout.strip()
            return True, version, path
    except WSLError:
        pass
    
    return True, None, path


def check_blastdbcmd_installation():
    """Check if blastdbcmd is installed in WSL
    
    Returns:
        tuple: (installed: bool, version: str or None, path: str or None)
    """
    if not is_wsl_available():
        return False, None, None
    
    # Warm up WSL once before checks (if not already done)
    warmup_wsl()
    
    exists, path = check_wsl_command('blastdbcmd')
    if not exists:
        return False, None, None
    
    try:
        result = run_wsl_command(['blastdbcmd', '-version'], timeout=30)
        if result.returncode == 0:
            # Extract version from output
            version_line = result.stdout.split('\n')[0] if result.stdout else None
            return True, version_line, path
    except WSLError:
        pass
    
    return True, None, path


def get_disk_space_wsl(path):
    """Get available disk space at a WSL path
    
    Args:
        path: WSL path to check
        
    Returns:
        tuple: (available_bytes: int or None, total_bytes: int or None)
    """
    try:
        result = run_wsl_command(f"df -B1 '{path}' | tail -1 | awk '{{print $4,$2}}'", timeout=5)
        if result.returncode == 0:
            parts = result.stdout.strip().split()
            if len(parts) >= 2:
                available = int(parts[0])
                total = int(parts[1])
                return available, total
    except (WSLError, ValueError):
        pass
    
    return None, None

