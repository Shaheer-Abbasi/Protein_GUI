"""
Cross-platform utility functions for running external bioinformatics tools.

On Windows: commands run through WSL (Windows Subsystem for Linux).
On macOS/Linux: commands run natively.
"""
import subprocess
import os
import sys
import shutil


def is_windows():
    """Check if running on Windows"""
    return sys.platform == 'win32'


class WSLError(Exception):
    """Custom exception for command execution errors (WSL or native)"""
    pass


def warmup_wsl():
    """Warm up WSL to avoid timeout on first command after boot.
    No-op on macOS/Linux since tools run natively.
    """
    if not is_windows():
        return
    try:
        subprocess.run(
            ['wsl', 'echo', 'warmup'],
            capture_output=True,
            timeout=15
        )
    except:
        pass


def is_wsl_available():
    """Check if the system can run external CLI tools.
    On Windows: checks WSL availability.
    On macOS/Linux: always True (native execution).
    """
    if not is_windows():
        return True
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
    """Check if a command is available.
    On Windows: checks inside WSL.
    On macOS/Linux: checks native PATH.

    Args:
        command: Command name to check (e.g., 'mmseqs', 'blastdbcmd')

    Returns:
        tuple: (exists: bool, path: str or None)
    """
    if not is_windows():
        path = shutil.which(command)
        return (True, path) if path else (False, None)
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
    """Run a command, routing through WSL on Windows or natively on macOS/Linux.

    Args:
        command: Command to run (string or list)
        timeout: Timeout in seconds (None for no timeout)

    Returns:
        subprocess.CompletedProcess object

    Raises:
        WSLError: If the execution environment is unavailable or the command fails
    """
    if not is_windows():
        if isinstance(command, str):
            cmd = ['bash', '-c', command]
        else:
            cmd = command
    else:
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
        raise WSLError(f"Failed to run command: {str(e)}") from e


def convert_path_for_tool(native_path):
    """Convert a native OS path to one accessible by CLI tools.
    On Windows: converts to WSL /mnt/ path.
    On macOS/Linux: returns path unchanged.

    Args:
        native_path: A native filesystem path

    Returns:
        Path string suitable for the tool execution environment
    """
    if not is_windows():
        return native_path
    return windows_path_to_wsl(native_path)


def windows_path_to_wsl(windows_path):
    """Convert Windows path to WSL path.

    Args:
        windows_path: Windows path (e.g., 'E:\\Projects\\file.txt')

    Returns:
        WSL path (e.g., '/mnt/e/Projects/file.txt')
    """
    if not is_windows():
        return windows_path

    path = windows_path.replace('\\', '/')

    if len(path) >= 2 and path[1] == ':':
        drive_letter = path[0].lower()
        path_without_drive = path[2:].lstrip('/')
        return f"/mnt/{drive_letter}/{path_without_drive}"

    return path


def wsl_path_to_windows(wsl_path):
    """Convert WSL path to Windows path.

    Args:
        wsl_path: WSL path (e.g., '/mnt/e/Projects/file.txt')

    Returns:
        Windows path (e.g., 'E:\\Projects\\file.txt')
    """
    if not is_windows():
        return wsl_path

    if wsl_path.startswith('/mnt/'):
        parts = wsl_path[5:].split('/', 1)
        if len(parts) >= 1:
            drive_letter = parts[0].upper()
            remaining_path = parts[1] if len(parts) > 1 else ''
            win_path = remaining_path.replace('/', '\\')
            return f"{drive_letter}:\\{win_path}"

    return wsl_path


def check_mmseqs_installation():
    """Check if MMseqs2 is installed.
    On Windows: checks inside WSL.
    On macOS/Linux: checks native installation.

    Returns:
        tuple: (installed: bool, version: str or None, path: str or None)
    """
    if is_windows() and not is_wsl_available():
        return False, None, None

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
    """Check if blastdbcmd is installed.
    On Windows: checks inside WSL.
    On macOS/Linux: checks native installation.

    Returns:
        tuple: (installed: bool, version: str or None, path: str or None)
    """
    if is_windows() and not is_wsl_available():
        return False, None, None

    warmup_wsl()

    exists, path = check_wsl_command('blastdbcmd')
    if not exists:
        return False, None, None

    try:
        result = run_wsl_command(['blastdbcmd', '-version'], timeout=30)
        if result.returncode == 0:
            version_line = result.stdout.split('\n')[0] if result.stdout else None
            return True, version_line, path
    except WSLError:
        pass

    return True, None, path


def get_disk_space_wsl(path):
    """Get available disk space at a path.
    On Windows: queries via WSL.
    On macOS/Linux: uses shutil.disk_usage.

    Args:
        path: Path to check

    Returns:
        tuple: (available_bytes: int or None, total_bytes: int or None)
    """
    if not is_windows():
        try:
            usage = shutil.disk_usage(path)
            return usage.free, usage.total
        except (OSError, ValueError):
            return None, None

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


def get_platform_tool_install_hint(tool_name):
    """Get platform-appropriate installation instructions for a tool.

    Args:
        tool_name: 'mmseqs', 'clustalo', 'blastdbcmd', or 'blast+'

    Returns:
        str: Installation instructions
    """
    if is_windows():
        hints = {
            'mmseqs': (
                "Install MMseqs2 in WSL:\n"
                "  wsl\n"
                "  wget https://mmseqs.com/latest/mmseqs-linux-avx2.tar.gz\n"
                "  tar xvfz mmseqs-linux-avx2.tar.gz\n"
                "  sudo cp mmseqs/bin/mmseqs /usr/local/bin/"
            ),
            'clustalo': (
                "Install Clustal Omega in WSL:\n"
                "  wsl\n"
                "  sudo apt update && sudo apt install clustalo"
            ),
            'blastdbcmd': (
                "Install BLAST+ tools in WSL:\n"
                "  wsl\n"
                "  sudo apt update && sudo apt install ncbi-blast+"
            ),
            'blast+': (
                "Install BLAST+ tools in WSL:\n"
                "  wsl\n"
                "  sudo apt update && sudo apt install ncbi-blast+"
            ),
        }
    elif sys.platform == 'darwin':
        hints = {
            'mmseqs': (
                "Install MMseqs2 via Homebrew:\n"
                "  brew install mmseqs2\n\n"
                "Or via Conda:\n"
                "  conda install -c conda-forge -c bioconda mmseqs2"
            ),
            'clustalo': (
                "Install Clustal Omega via Homebrew:\n"
                "  brew install clustal-omega\n\n"
                "Or via Conda:\n"
                "  conda install -c bioconda clustalo"
            ),
            'blastdbcmd': (
                "Install BLAST+ via Homebrew:\n"
                "  brew install blast\n\n"
                "Or download from NCBI:\n"
                "  https://ftp.ncbi.nlm.nih.gov/blast/executables/blast+/LATEST/"
            ),
            'blast+': (
                "Install BLAST+ via Homebrew:\n"
                "  brew install blast\n\n"
                "Or download from NCBI:\n"
                "  https://ftp.ncbi.nlm.nih.gov/blast/executables/blast+/LATEST/"
            ),
        }
    else:
        hints = {
            'mmseqs': (
                "Install MMseqs2:\n"
                "  wget https://mmseqs.com/latest/mmseqs-linux-avx2.tar.gz\n"
                "  tar xvfz mmseqs-linux-avx2.tar.gz\n"
                "  sudo cp mmseqs/bin/mmseqs /usr/local/bin/\n\n"
                "Or via Conda:\n"
                "  conda install -c conda-forge -c bioconda mmseqs2"
            ),
            'clustalo': (
                "Install Clustal Omega:\n"
                "  sudo apt update && sudo apt install clustalo"
            ),
            'blastdbcmd': (
                "Install BLAST+ tools:\n"
                "  sudo apt update && sudo apt install ncbi-blast+"
            ),
            'blast+': (
                "Install BLAST+ tools:\n"
                "  sudo apt update && sudo apt install ncbi-blast+"
            ),
        }
    return hints.get(tool_name, f"Please install {tool_name} and ensure it is on your PATH.")


def get_platform_name():
    """Get a user-friendly name for the current platform"""
    if is_windows():
        return "Windows (WSL)"
    elif sys.platform == 'darwin':
        return "macOS"
    else:
        return "Linux"


def run_command_live(command):
    """Run a command with live output streaming.
    On Windows: runs through WSL.
    On macOS/Linux: runs natively.

    Args:
        command: Shell command string to execute

    Returns:
        subprocess.Popen object
    """
    if is_windows():
        return subprocess.Popen(
            ['wsl', 'bash', '-c', command],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
    else:
        return subprocess.Popen(
            ['bash', '-c', command],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
