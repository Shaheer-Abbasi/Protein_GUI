"""Setup wizard for Protein-GUI - helps configure paths on new machines (cross-platform)"""
import os
import json
import subprocess
import sys
import shutil


def is_windows():
    return sys.platform == 'win32'


def is_macos():
    return sys.platform == 'darwin'


def check_command(cmd):
    """Check if a command is available"""
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except:
        return False


def find_blast():
    """Try to find BLAST installation (cross-platform)"""
    if is_windows():
        common_paths = [
            r"C:\Program Files\NCBI\blast-2.17.0+\bin\blastp.exe",
            r"C:\Program Files\NCBI\blast-2.16.0+\bin\blastp.exe",
            r"C:\Program Files\NCBI\blast-2.15.0+\bin\blastp.exe",
            r"C:\blast\bin\blastp.exe",
        ]
        for path in common_paths:
            if os.path.exists(path):
                return path
    elif is_macos():
        common_paths = [
            "/usr/local/bin/blastp",
            "/opt/homebrew/bin/blastp",
            os.path.expanduser("~/miniconda3/bin/blastp"),
            os.path.expanduser("~/anaconda3/bin/blastp"),
        ]
        for path in common_paths:
            if os.path.exists(path):
                return path
    else:
        common_paths = [
            "/usr/bin/blastp",
            "/usr/local/bin/blastp",
            os.path.expanduser("~/miniconda3/bin/blastp"),
            os.path.expanduser("~/anaconda3/bin/blastp"),
        ]
        for path in common_paths:
            if os.path.exists(path):
                return path

    # Check if in PATH
    found = shutil.which('blastp')
    if found:
        return found

    if check_command(['blastp', '-version']):
        return 'blastp'

    return None


def find_mmseqs():
    """Try to find MMSeqs2 installation (cross-platform)"""
    if is_windows():
        common_paths = [
            r"C:\Program Files\MMSeqs2\mmseqs.exe",
            r"C:\MMSeqs2\mmseqs.exe",
            r"C:\mmseqs\bin\mmseqs.exe",
        ]
        for path in common_paths:
            if os.path.exists(path):
                return path
    elif is_macos():
        common_paths = [
            "/usr/local/bin/mmseqs",
            "/opt/homebrew/bin/mmseqs",
            os.path.expanduser("~/miniconda3/bin/mmseqs"),
            os.path.expanduser("~/anaconda3/bin/mmseqs"),
        ]
        for path in common_paths:
            if os.path.exists(path):
                return path
    else:
        common_paths = [
            "/usr/local/bin/mmseqs",
            "/usr/bin/mmseqs",
            os.path.expanduser("~/miniconda3/bin/mmseqs"),
            os.path.expanduser("~/anaconda3/bin/mmseqs"),
        ]
        for path in common_paths:
            if os.path.exists(path):
                return path

    found = shutil.which('mmseqs')
    if found:
        return found

    if check_command(['mmseqs', '--help']):
        return 'mmseqs'

    return None


def find_clustalo():
    """Try to find Clustal Omega installation"""
    found = shutil.which('clustalo')
    if found:
        return found

    if is_macos():
        for path in ["/usr/local/bin/clustalo", "/opt/homebrew/bin/clustalo"]:
            if os.path.exists(path):
                return path

    if check_command(['clustalo', '--version']):
        return 'clustalo'

    return None


def find_blastdbcmd():
    """Try to find blastdbcmd"""
    found = shutil.which('blastdbcmd')
    if found:
        return found

    if check_command(['blastdbcmd', '-version']):
        return 'blastdbcmd'

    return None


def check_wsl():
    """Check if WSL is available (Windows only)"""
    if not is_windows():
        return False
    try:
        result = subprocess.run(['wsl', '--status'], capture_output=True, timeout=15)
        return result.returncode == 0
    except:
        return False


def warmup_wsl():
    """Warmup WSL to avoid timeout on first command (Windows only)"""
    if not is_windows():
        return
    try:
        subprocess.run(['wsl', 'echo', 'warmup'], capture_output=True, timeout=15)
    except:
        pass


def check_wsl_command(cmd):
    """Check if a command exists in WSL (Windows only)"""
    if not is_windows():
        return False
    try:
        result = subprocess.run(['wsl', 'which', cmd], capture_output=True, text=True, timeout=30)
        return result.returncode == 0
    except Exception:
        return False


def get_install_hint(tool):
    """Get platform-appropriate installation instructions"""
    if is_windows():
        hints = {
            'blast': "Download from: https://ftp.ncbi.nlm.nih.gov/blast/executables/blast+/LATEST/",
            'mmseqs': "Download from: https://github.com/soedinglab/MMseqs2/releases",
            'mmseqs_wsl': (
                "Install in WSL:\n"
                "        wsl\n"
                "        wget https://mmseqs.com/latest/mmseqs-linux-avx2.tar.gz\n"
                "        tar xvfz mmseqs-linux-avx2.tar.gz\n"
                "        sudo cp mmseqs/bin/mmseqs /usr/local/bin/"
            ),
            'blastdbcmd_wsl': (
                "Install in WSL:\n"
                "        wsl\n"
                "        sudo apt update\n"
                "        sudo apt install ncbi-blast+"
            ),
            'clustalo': "Install in WSL: sudo apt install clustalo",
        }
    elif is_macos():
        hints = {
            'blast': (
                "Install via Homebrew: brew install blast\n"
                "      Or download from: https://ftp.ncbi.nlm.nih.gov/blast/executables/blast+/LATEST/"
            ),
            'mmseqs': (
                "Install via Homebrew: brew install mmseqs2\n"
                "      Or via Conda: conda install -c conda-forge -c bioconda mmseqs2"
            ),
            'blastdbcmd': (
                "Install via Homebrew: brew install blast\n"
                "      Or download from: https://ftp.ncbi.nlm.nih.gov/blast/executables/blast+/LATEST/"
            ),
            'clustalo': (
                "Install via Homebrew: brew install clustal-omega\n"
                "      Or via Conda: conda install -c bioconda clustalo"
            ),
        }
    else:
        hints = {
            'blast': (
                "Install: sudo apt update && sudo apt install ncbi-blast+\n"
                "      Or download from: https://ftp.ncbi.nlm.nih.gov/blast/executables/blast+/LATEST/"
            ),
            'mmseqs': (
                "Install:\n"
                "        wget https://mmseqs.com/latest/mmseqs-linux-avx2.tar.gz\n"
                "        tar xvfz mmseqs-linux-avx2.tar.gz\n"
                "        sudo cp mmseqs/bin/mmseqs /usr/local/bin/"
            ),
            'blastdbcmd': "Install: sudo apt update && sudo apt install ncbi-blast+",
            'clustalo': "Install: sudo apt update && sudo apt install clustalo",
        }
    return hints.get(tool, f"Please install {tool}")


def main():
    print("=" * 60)
    print("Protein-GUI Setup Wizard")
    print("=" * 60)

    platform_name = "Windows" if is_windows() else ("macOS" if is_macos() else "Linux")
    print(f"Platform: {platform_name}")
    print()

    config = {}

    # Check Python version
    print("[OK] Python version:", sys.version.split()[0])
    print()

    # Check dependencies
    print("Checking Python dependencies...")
    try:
        import PyQt5
        print("  [OK] PyQt5 installed")
    except:
        print("  [X] PyQt5 NOT installed")
        print("      Install with: pip install PyQt5")

    try:
        import Bio
        print("  [OK] Biopython installed")
    except:
        print("  [X] Biopython NOT installed")
        print("      Install with: pip install biopython")
    print()

    # Check BLAST
    print("Checking BLAST installation...")
    blast_path = find_blast()
    if blast_path:
        print(f"  [OK] BLAST found: {blast_path}")
        config['blast_path'] = blast_path
    else:
        print("  [X] BLAST not found")
        print(f"      {get_install_hint('blast')}")
        manual_path = input("\n  Enter BLAST path (or press Enter to skip): ").strip()
        if manual_path and os.path.exists(manual_path):
            config['blast_path'] = manual_path
            print(f"  [OK] Using: {manual_path}")
    print()

    # Check MMSeqs2 (native first, then WSL on Windows)
    print("Checking MMSeqs2 installation...")
    mmseqs_path = find_mmseqs()
    if mmseqs_path:
        print(f"  [OK] MMSeqs2 found: {mmseqs_path}")
        config['mmseqs_path'] = mmseqs_path
        config['mmseqs_available'] = True
    else:
        print(f"  [!] MMSeqs2 not found natively")
        print(f"      {get_install_hint('mmseqs')}")
        manual_mmseqs = input("\n  Enter MMSeqs2 path (or press Enter to skip): ").strip()
        if manual_mmseqs and os.path.exists(manual_mmseqs):
            config['mmseqs_path'] = manual_mmseqs
            config['mmseqs_available'] = True
            print(f"  [OK] Using: {manual_mmseqs}")
        else:
            config['mmseqs_path'] = 'mmseqs'
            config['mmseqs_available'] = False
    print()

    # Check blastdbcmd and clustalo
    if not is_windows():
        # On macOS/Linux, check native installations
        print("Checking blastdbcmd...")
        blastdbcmd_path = find_blastdbcmd()
        if blastdbcmd_path:
            print(f"  [OK] blastdbcmd found: {blastdbcmd_path}")
            config['blastdbcmd_available'] = True
        else:
            print("  [X] blastdbcmd not found")
            print(f"      {get_install_hint('blastdbcmd')}")
            config['blastdbcmd_available'] = False
        print()

        print("Checking Clustal Omega...")
        clustalo_path = find_clustalo()
        if clustalo_path:
            print(f"  [OK] Clustal Omega found: {clustalo_path}")
            config['clustalo_available'] = True
        else:
            print("  [X] Clustal Omega not found")
            print(f"      {get_install_hint('clustalo')}")
            config['clustalo_available'] = False
        print()
    else:
        # On Windows, check WSL
        print("Checking WSL installation...")
        if check_wsl():
            print("  [OK] WSL is available")
            print("  Initializing WSL (first command may take a moment)...")
            warmup_wsl()

            if not config.get('mmseqs_available'):
                if check_wsl_command('mmseqs'):
                    print("  [OK] MMseqs2 installed in WSL")
                    config['mmseqs_available'] = True
                    config['mmseqs_path'] = 'mmseqs'
                else:
                    print("  [X] MMseqs2 not found in WSL")
                    print(f"      {get_install_hint('mmseqs_wsl')}")
                    config['mmseqs_available'] = False
            else:
                print("  [OK] Using MMseqs2 from Windows (WSL check skipped)")

            if check_wsl_command('blastdbcmd'):
                print("  [OK] blastdbcmd installed in WSL")
                config['blastdbcmd_available'] = True
            else:
                print("  [X] blastdbcmd not found in WSL")
                print(f"      {get_install_hint('blastdbcmd_wsl')}")
                config['blastdbcmd_available'] = False
        else:
            print("  [X] WSL not available")
            print("      Install with: wsl --install")
            print("      (Requires administrator privileges and restart)")
            if not config.get('mmseqs_available'):
                config['mmseqs_available'] = False
            config['blastdbcmd_available'] = False
        print()

    # Check database directory
    print("Checking database directory...")
    db_dir = "blast_databases"
    if os.path.exists(db_dir):
        databases = [d for d in os.listdir(db_dir) if os.path.isdir(os.path.join(db_dir, d))]
        if databases:
            print(f"  [OK] Found {len(databases)} database(s): {', '.join(databases)}")
            config['databases_found'] = databases
        else:
            print("  [!] blast_databases folder exists but is empty")
            config['databases_found'] = []
    else:
        print("  [!] blast_databases folder not found")
        print("      Download databases from NCBI or use custom location")
        config['databases_found'] = []
    print()

    # Save configuration
    config_file = "config.json"
    with open(config_file, 'w') as f:
        json.dump(config, f, indent=2)

    print("=" * 60)
    print("Setup Summary")
    print("=" * 60)
    print()

    all_good = True

    if config.get('blast_path'):
        print("[OK] BLAST: Ready")
    else:
        print("[X] BLAST: Not configured")
        all_good = False

    if config.get('mmseqs_available') and config.get('blastdbcmd_available'):
        print("[OK] MMseqs2: Ready (full functionality)")
    elif config.get('mmseqs_available'):
        print("[!] MMseqs2: Partial (missing blastdbcmd for auto-conversion)")
    else:
        print("[!] MMseqs2: Not available (will use BLAST only)")

    if config.get('databases_found'):
        print(f"[OK] Databases: {len(config['databases_found'])} found")
    else:
        print("[!] Databases: None found (searches will require databases)")

    print()
    print(f"Configuration saved to: {config_file}")
    print()

    if all_good:
        print("All systems ready! You can run: python protein_gui.py")
    else:
        print("[!] Some components missing. The application will run with limited features.")
        print("    See messages above for installation instructions.")
    print()

    input("Press Enter to exit...")

if __name__ == "__main__":
    main()
