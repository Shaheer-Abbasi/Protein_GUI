"""Setup wizard for Protein-GUI - helps configure paths on new machines"""
import os
import json
import subprocess
import sys

def check_command(cmd):
    """Check if a command is available"""
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except:
        return False

def find_blast():
    """Try to find BLAST installation"""
    common_paths = [
        r"C:\Program Files\NCBI\blast-2.17.0+\bin\blastp.exe",
        r"C:\Program Files\NCBI\blast-2.16.0+\bin\blastp.exe",
        r"C:\Program Files\NCBI\blast-2.15.0+\bin\blastp.exe",
        r"C:\blast\bin\blastp.exe",
    ]
    
    for path in common_paths:
        if os.path.exists(path):
            return path
    
    # Check if in PATH
    if check_command(['blastp', '-version']):
        return 'blastp'  # Available in PATH
    
    return None

def find_mmseqs_windows():
    """Try to find MMSeqs2 installation on Windows"""
    common_paths = [
        r"C:\Program Files\MMSeqs2\mmseqs.exe",
        r"C:\MMSeqs2\mmseqs.exe",
        r"C:\mmseqs\bin\mmseqs.exe",
    ]
    
    for path in common_paths:
        if os.path.exists(path):
            return path
    
    # Check if in PATH
    if check_command(['mmseqs', '--help']):
        return 'mmseqs'  # Available in PATH
    
    return None

def check_wsl():
    """Check if WSL is available"""
    try:
        result = subprocess.run(['wsl', '--status'], capture_output=True, timeout=15)
        return result.returncode == 0
    except:
        return False

def warmup_wsl():
    """Warmup WSL to avoid timeout on first command"""
    try:
        # Run a simple command to initialize WSL
        subprocess.run(['wsl', 'echo', 'warmup'], capture_output=True, timeout=15)
    except:
        pass

def check_wsl_command(cmd):
    """Check if a command exists in WSL"""
    try:
        result = subprocess.run(['wsl', 'which', cmd], capture_output=True, text=True, timeout=30)
        print(f"    DEBUG: {cmd} check - returncode={result.returncode}, stdout='{result.stdout.strip()[:100]}', stderr='{result.stderr.strip()[:100]}'")
        return result.returncode == 0
    except Exception as e:
        print(f"    DEBUG: {cmd} check failed with exception: {e}")
        return False

def main():
    print("=" * 60)
    print("Protein-GUI Setup Wizard")
    print("=" * 60)
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
        print("      Download from: https://ftp.ncbi.nlm.nih.gov/blast/executables/blast+/LATEST/")
        manual_path = input("\n  Enter BLAST path (or press Enter to skip): ").strip()
        if manual_path and os.path.exists(manual_path):
            config['blast_path'] = manual_path
            print(f"  [OK] Using: {manual_path}")
    print()
    
    # Check MMSeqs2 on Windows (before checking WSL)
    print("Checking MMSeqs2 on Windows...")
    mmseqs_windows = find_mmseqs_windows()
    if mmseqs_windows:
        print(f"  [OK] MMSeqs2 found on Windows: {mmseqs_windows}")
        config['mmseqs_path'] = mmseqs_windows
        config['mmseqs_available'] = True
    else:
        print("  [!] MMSeqs2 not found on Windows")
        print("      Download from: https://github.com/soedinglab/MMseqs2/releases")
        manual_mmseqs = input("\n  Enter MMSeqs2 path (or press Enter to check WSL): ").strip()
        if manual_mmseqs and os.path.exists(manual_mmseqs):
            config['mmseqs_path'] = manual_mmseqs
            config['mmseqs_available'] = True
            print(f"  [OK] Using: {manual_mmseqs}")
        else:
            config['mmseqs_path'] = 'mmseqs'  # Default, will check WSL next
    print()
    
    # Check WSL
    print("Checking WSL installation...")
    if check_wsl():
        print("  [OK] WSL is available")
        print("  Initializing WSL (first command may take a moment)...")
        warmup_wsl()
        
        # Check MMseqs2 in WSL (only if not already found on Windows)
        if not config.get('mmseqs_available'):
            if check_wsl_command('mmseqs'):
                print("  [OK] MMseqs2 installed in WSL")
                config['mmseqs_available'] = True
                config['mmseqs_path'] = 'mmseqs'  # Will use WSL
            else:
                print("  [X] MMseqs2 not found in WSL")
                print("      Install with:")
                print("        wsl")
                print("        wget https://mmseqs.com/latest/mmseqs-linux-avx2.tar.gz")
                print("        tar xvfz mmseqs-linux-avx2.tar.gz")
                print("        sudo cp mmseqs/bin/mmseqs /usr/local/bin/")
                config['mmseqs_available'] = False
        else:
            print("  [OK] Using MMseqs2 from Windows (WSL check skipped)")

        
        # Check blastdbcmd
        if check_wsl_command('blastdbcmd'):
            print("  [OK] blastdbcmd installed in WSL")
            config['blastdbcmd_available'] = True
        else:
            print("  [X] blastdbcmd not found in WSL")
            print("      Install with:")
            print("        wsl")
            print("        sudo apt update")
            print("        sudo apt install ncbi-blast+")
            config['blastdbcmd_available'] = False
    else:
        print("  [X] WSL not available")
        print("      Install with: wsl --install")
        print("      (Requires administrator privileges and restart)")
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

