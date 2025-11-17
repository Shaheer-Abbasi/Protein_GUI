# Configuration Guide - Portable Setup

## Overview
Your Protein-GUI application is now fully portable! All hardcoded file paths have been replaced with a centralized configuration system.

## What Changed?

### 1. **New Configuration System**
- Created `core/config_manager.py` - centralized config loader
- All paths are now stored in `config.json`
- Database directories are relative to project root

### 2. **Files Modified**
- ✅ `core/blast_worker.py` - Now reads BLAST path from config
- ✅ `utils/hardware_utils.py` - Now reads MMSeqs2 path from config
- ✅ `setup_wizard.py` - Enhanced to detect and save MMSeqs2 paths
- ✅ `config.json` - Added `mmseqs_path` field
- ✅ `README.md` - Updated with new setup instructions

### 3. **Removed Hardcoded Paths**
**Before:**
```python
# blast_worker.py
blastp_path = r'C:\Users\18329\NCBI\...\blastp.exe'

# hardware_utils.py
fallback = r"C:\Users\18329\MMSeqs2\mmseqs-win64\mmseqs\bin"
```

**After:**
```python
# blast_worker.py
config = get_config()
blastp_path = config.get_blast_path()

# hardware_utils.py
config = get_config()
mmseqs_path = config.get_mmseqs_path()
```

## Using on a New Computer

### Method 1: Automatic Setup (Recommended)
1. Copy the entire project folder to the new computer
2. Run the setup wizard:
   ```bash
   python setup_wizard.py
   ```
3. The wizard will automatically detect tool installations and update `config.json`

### Method 2: Manual Configuration
1. Copy the project folder to the new computer
2. Edit `config.json` with your machine-specific paths:
   ```json
   {
     "blast_path": "C:\\Path\\To\\blastp.exe",
     "mmseqs_path": "C:\\Path\\To\\mmseqs.exe",
     "mmseqs_available": true,
     "blastdbcmd_available": true,
     "databases_found": ["swissprot", "refseq_protein"]
   }
   ```

## config.json Structure

```json
{
  "blast_path": "blastp",           // Path to BLAST executable
  "mmseqs_path": "mmseqs",          // Path to MMSeqs2 executable  
  "mmseqs_available": true,         // MMSeqs2 functionality enabled
  "blastdbcmd_available": true,     // Auto-conversion enabled
  "databases_found": [              // Available databases
    "refseq_protein",
    "swissprot"
  ]
}
```

### Path Options:
- **"blastp"** or **"mmseqs"** - Tool is in system PATH
- **Full path** - e.g., `"C:\\Program Files\\NCBI\\blast\\bin\\blastp.exe"`
- **Relative path** - Relative to project directory

## Database Directories

Databases are stored relative to the project root:
- **BLAST databases**: `./blast_databases/`
- **MMSeqs2 databases**: `./mmseqs_databases/`

You can move the entire folder and databases together!

## Benefits

✅ **Portable** - Works on any computer after running setup wizard  
✅ **Version Control Friendly** - No hardcoded personal paths in git  
✅ **Multi-User** - Each developer has their own config.json  
✅ **Easy Migration** - Just copy folder and run setup wizard  
✅ **Relative Paths** - Database directories move with the project

## Troubleshooting

**Q: Tool not found error?**  
A: Run `python setup_wizard.py` to reconfigure paths

**Q: Can I use tools from WSL?**  
A: Yes! MMSeqs2 can use WSL. Set `"mmseqs_path": "mmseqs"` in config

**Q: Can I have different configs on different machines?**  
A: Yes! `config.json` is gitignored, so each machine has its own

**Q: How do I check my current configuration?**  
A: Open `config.json` in a text editor

## Best Practices

1. **Always run setup wizard on new machines**
2. **Keep config.json out of version control** (already in .gitignore)
3. **Keep databases in project folders** for portability
4. **Document custom paths** if you use non-standard locations

---

*Last updated after removing hardcoded paths and implementing portable configuration system*

