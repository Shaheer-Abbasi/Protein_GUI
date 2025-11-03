import subprocess
import os


def has_nvidia_gpu():
    try:
        subprocess.check_output(["nvidia-smi"], stderr=subprocess.STDOUT)
        return True
    except Exception:
        return False


def detect_mmseqs_path():
    """Check if mmseqs is accessible, else fall back to default location."""
    try:
        subprocess.check_output(["mmseqs", "--help"], stderr=subprocess.STDOUT)
        return "mmseqs"
    except Exception:
        #fallback = r"C:\Users\abbas\Downloads\mmseqs-win64\mmseqs.exe"
        fallback = r"C:\Users\18329\MMSeqs2\mmseqs-win64\mmseqs\bin"
        if os.path.exists(fallback):
            return fallback
        return None
