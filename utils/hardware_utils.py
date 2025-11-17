import subprocess
import os
import sys

# Add parent directory to path to import config_manager
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config_manager import get_config


def has_nvidia_gpu():
    try:
        subprocess.check_output(["nvidia-smi"], stderr=subprocess.STDOUT)
        return True
    except Exception:
        return False


def detect_mmseqs_path():
    """Check if mmseqs is accessible, using config for portable path."""
    config = get_config()
    mmseqs_path = config.get_mmseqs_path()
    
    # First try the path from config
    try:
        if mmseqs_path:
            # Test if the configured path works
            subprocess.check_output([mmseqs_path, "--help"], stderr=subprocess.STDOUT)
            return mmseqs_path
    except Exception:
        pass
    
    # Fall back to checking if mmseqs is in PATH
    try:
        subprocess.check_output(["mmseqs", "--help"], stderr=subprocess.STDOUT)
        return "mmseqs"
    except Exception:
        return None
