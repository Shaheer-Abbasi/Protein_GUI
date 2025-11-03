# MMseqs2 WSL Integration - Complete Guide

## Overview
Successfully integrated MMseqs2 (via WSL Ubuntu) with automatic database conversion from BLAST format. This allows users to search using MMseqs2 with their existing BLAST databases.

## 🎯 Features Implemented

### 1. **WSL Integration** (`core/wsl_utils.py`)
- Check if WSL is available
- Run commands in WSL Ubuntu
- Path conversion (Windows ↔ WSL)
- Check for MMseqs2 and blastdbcmd installations
- Disk space checking

### 2. **Database Conversion Manager** (`core/db_conversion_manager.py`)
- Track conversion status (not_converted, converting, converted, failed)
- Cache converted databases (JSON-based)
- Automatic cleanup of old databases
- Persistent status across app restarts

### 3. **Database Conversion Worker** (`core/db_conversion_worker.py`)
- Background thread for conversion
- Extract FASTA from BLAST database using `blastdbcmd`
- Convert FASTA to MMseqs2 format using `mmseqs createdb`
- Progress reporting (percentage & messages)
- Cancellation support
- Comprehensive error handling

### 4. **Progress Dialog** (`ui/dialogs/conversion_progress_dialog.py`)
- Non-modal dialog (user can use other features while converting)
- Real-time progress updates
- Cancellable conversion
- Detailed log viewer
- Error display

### 5. **Enhanced MMseqs2 Page** (`ui/mmseqs_page.py`)
- Database dropdown with NCBI databases
- Status indicators:
  - ✓ Converted and ready
  - ⟳ Currently converting
  - ✗ Conversion failed
  - ○ Not yet converted
- Auto-conversion on first use
- System requirements checking
- Both NCBI and custom database support

## 📁 File Structure

```
E:\Projects\Protein-GUI\
├── core/
│   ├── wsl_utils.py                    # WSL integration utilities
│   ├── db_conversion_manager.py        # Conversion status tracking
│   ├── db_conversion_worker.py         # Conversion background worker
│   ├── blast_worker.py
│   ├── mmseqs_runner.py
│   └── db_definitions.py
├── ui/
│   ├── dialogs/
│   │   ├── __init__.py
│   │   └── conversion_progress_dialog.py  # Progress dialog
│   ├── blast_page.py
│   ├── home_page.py
│   └── mmseqs_page.py                  # Enhanced with conversion support
├── mmseqs_databases/
│   └── conversion_status.json          # Tracks conversion status
└── blast_databases/
    └── swissprot/                      # Your BLAST databases
```

## 🔧 System Requirements

### Required in WSL Ubuntu:
1. **MMseqs2** (installed at `/usr/local/bin/mmseqs`)
2. **NCBI BLAST+ tools** (specifically `blastdbcmd` version 2.12.0+)

### Verify Installation:
```bash
# Check MMseqs2
wsl mmseqs version

# Check blastdbcmd
wsl blastdbcmd -version

# Check paths
wsl which mmseqs
wsl which blastdbcmd
```

## 🚀 How It Works

### User Workflow:

1. **Open MMseqs2 Page**
   - System checks for WSL, MMseqs2, and blastdbcmd
   - Displays status messages if anything is missing

2. **Select Database Source**
   - **Option A:** Use NCBI Database (auto-convert)
     - Select from dropdown (swissprot, nr, pdb, etc.)
     - See status indicator (✓ ○ ⟳ ✗)
   - **Option B:** Use Custom MMseqs2 Database
     - Browse to existing MMseqs2 database

3. **First-Time Database Selection**
   - If database not converted, user is prompted
   - Confirms they want to start conversion
   - Progress dialog appears (non-modal)

4. **Conversion Process**
   - Step 1: Check disk space (needs >1GB)
   - Step 2: Extract FASTA from BLAST db (`blastdbcmd`)
   - Step 3: Convert to MMseqs2 format (`mmseqs createdb`)
   - Step 4: Cleanup temporary files
   - Step 5: Mark as converted

5. **Search with Converted Database**
   - Enter protein sequence
   - Select sensitivity level
   - Run search (uses WSL MMseqs2)

### Behind the Scenes:

```
User selects "swissprot" → Check if converted → No
    ↓
Prompt user to convert → User confirms
    ↓
DatabaseConversionWorker starts:
    ↓
1. Check disk space at /mnt/e/Projects/Protein-GUI/mmseqs_databases/
    ↓
2. Run: blastdbcmd -db /mnt/e/.../blast_databases/swissprot -entry all -out temp.fasta
    ↓
3. Run: mmseqs createdb temp.fasta /mnt/e/.../mmseqs_databases/swissprot
    ↓
4. Cleanup: Delete temp files
    ↓
5. Save status to conversion_status.json
    ↓
Database ready! User can now search
```

## 🧪 Testing Checklist

### Pre-Testing:
- [ ] WSL Ubuntu is installed and running
- [ ] MMseqs2 is installed at `/usr/local/bin/mmseqs`
- [ ] NCBI BLAST+ tools installed (`sudo apt install ncbi-blast+`)
- [ ] At least one BLAST database exists in `blast_databases/` folder
- [ ] At least 1-2 GB free disk space

### Test 1: System Requirements Check
1. Launch the application
2. Navigate to MMseqs2 page
3. Wait 500ms for system check
4. **Expected:** Info label shows "✓ MMseqs2 ready" (green background)

**If it shows warnings:**
- WSL not detected → Install WSL
- MMseqs2 not found → Install MMseqs2
- blastdbcmd not found → `sudo apt install ncbi-blast+`

### Test 2: Database Dropdown
1. Click database dropdown
2. **Expected:** See databases with status icons:
   - ○ swissprot (not converted)
   - ○ nr (not converted)
   - etc.

### Test 3: First-Time Conversion
1. Select "swissprot" from dropdown
2. **Expected:** Status label shows "○ swissprot not yet converted"
3. Enter a test sequence (e.g., `MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQVVID`)
4. Click "Run MMseqs2 Search"
5. **Expected:** Popup asks "Would you like to start the conversion now?"
6. Click "Yes"
7. **Expected:** Progress dialog appears showing:
   - Checking disk space... 5%
   - Extracting sequences... 20%
   - Running blastdbcmd... 40%
   - Creating MMseqs2 database... 60%
   - Cleaning up... 90%
   - Conversion complete! 100%

**Monitor for:**
- Progress percentage increases
- Status messages update
- "Show Details" button works
- Can minimize/move dialog

### Test 4: Conversion Cancellation
1. Start another database conversion
2. Click "Cancel" button mid-conversion
3. **Expected:** 
   - Status changes to "Cancelling conversion..."
   - Worker stops
   - Temp files are cleaned up
   - Database marked as "not_converted"

### Test 5: Search with Converted Database
1. Select a converted database (should have ✓ icon)
2. **Expected:** Status shows "✓ swissprot is ready to use"
3. Enter test sequence
4. Click "Run MMseqs2 Search"
5. **Expected:** Search starts immediately (no conversion prompt)
6. Wait for results
7. **Expected:** Results displayed in output area

### Test 6: Custom Database
1. Select "Use Custom MMseqs2 Database" radio button
2. **Expected:** Browse button appears, dropdown disappears
3. Click "Browse..."
4. Select an existing MMseqs2 database file
5. Run search
6. **Expected:** Works without conversion

### Test 7: Error Handling - Disk Space
1. (If possible) Fill disk to <1GB free
2. Try converting a database
3. **Expected:** Error: "Insufficient disk space"

### Test 8: Error Handling - Missing Database
1. Edit database path to non-existent database
2. Try conversion
3. **Expected:** Error: "BLAST database not found"

### Test 9: Conversion Status Persistence
1. Convert a database (e.g., swissprot)
2. Close the application
3. Reopen the application
4. Go to MMseqs2 page
5. **Expected:** swissprot still shows ✓ (converted)
6. Can immediately search without re-converting

### Test 10: Parallel Usage (BLAST while Converting)
1. Start a database conversion (e.g., nr - large database)
2. While it's converting, click "← Back to Home"
3. Navigate to BLAST page
4. Run a BLAST search
5. **Expected:** Both work simultaneously

### Test 11: Reconversion (Old Database Deletion)
1. Select a converted database
2. Manually delete its files from `mmseqs_databases/`
3. Try to search with it
4. **Expected:** Error about missing database
5. Reset the conversion status and reconvert
6. **Expected:** New database created, old status updated

## ⚙️ Configuration

### Paths (Can be modified if needed)

**In `core/db_conversion_worker.py`:**
- BLAST database directory: `E:\Projects\Protein-GUI\blast_databases`
- MMseqs2 output directory: `E:\Projects\Protein-GUI\mmseqs_databases`

**In `ui/mmseqs_page.py`:**
```python
blast_db_dir = "E:\\Projects\\Protein-GUI\\blast_databases"
mmseqs_db_dir = "E:\\Projects\\Protein-GUI\\mmseqs_databases"
```

**In `core/db_conversion_manager.py`:**
```python
status_file = "mmseqs_databases/conversion_status.json"
```

### Timeouts

**In `core/db_conversion_worker.py`:**
- blastdbcmd timeout: 3600 seconds (1 hour)
- mmseqs createdb timeout: 3600 seconds (1 hour)
- Can be adjusted based on database size

## 🐛 Troubleshooting

### Issue: "WSL is not available"
**Solution:** 
```powershell
# Enable WSL
wsl --install

# Or check status
wsl --status
```

### Issue: "MMseqs2 not found in WSL"
**Solution:**
```bash
wsl
cd /tmp
wget https://mmseqs.com/latest/mmseqs-linux-avx2.tar.gz
tar xvfz mmseqs-linux-avx2.tar.gz
sudo cp mmseqs/bin/mmseqs /usr/local/bin/
mmseqs version
```

### Issue: "blastdbcmd not found in WSL"
**Solution:**
```bash
wsl
sudo apt update
sudo apt install ncbi-blast+
blastdbcmd -version
```

### Issue: Conversion is very slow
**Reasons:**
- Large database (nr is huge!)
- Limited disk I/O
- WSL 1 vs WSL 2 (WSL 2 is faster for Linux I/O)

**Solution:**
- Use smaller databases first (swissprot)
- Upgrade to WSL 2 if using WSL 1
- Close other disk-intensive programs

### Issue: "No such file or directory" in WSL
**Check paths:**
```bash
# Should work
wsl ls /mnt/e/Projects/Protein-GUI/blast_databases

# If not, check drive letter and path
wsl ls /mnt/e
```

### Issue: Conversion fails at extraction step
**Check BLAST database integrity:**
```bash
wsl blastdbcmd -db /mnt/e/Projects/Protein-GUI/blast_databases/swissprot -info
```

Should show database statistics. If error, BLAST database may be corrupted.

## 📊 Database Conversion Times (Estimates)

| Database | Size | Extraction Time | Conversion Time | Total |
|----------|------|-----------------|-----------------|-------|
| swissprot | ~300 MB | ~30 sec | ~1 min | ~2 min |
| pdb | ~500 MB | ~45 sec | ~1.5 min | ~2.5 min |
| refseq_protein | ~30 GB | ~10 min | ~20 min | ~30 min |
| nr | ~100 GB | ~30 min | ~60 min | ~90 min |

*Times vary based on system specs and disk speed*

## 🎉 Benefits

1. **User-Friendly:** No manual database conversion needed
2. **Efficient:** Convert once, use many times (cached)
3. **Non-Blocking:** Can use BLAST while MMseqs2 databases convert
4. **Safe:** Original BLAST databases remain untouched
5. **Transparent:** Clear status indicators and progress updates
6. **Robust:** Comprehensive error handling and recovery

## 🔄 Future Enhancements (Optional)

1. **Scheduled Conversions:** Pre-convert popular databases on app startup
2. **Download FASTA:** Direct download from NCBI instead of using BLAST db
3. **Compression:** Compress old databases to save space
4. **Batch Conversion:** Convert multiple databases at once
5. **Database Update Detection:** Check if BLAST db is newer than MMseqs2 db

---

**Integration Complete!** 🎊

The application now seamlessly integrates MMseqs2 via WSL with automatic database conversion. Users can easily switch between BLAST and MMseqs2 depending on their needs.

