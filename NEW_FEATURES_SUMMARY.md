# New MMseqs2 Features - Summary

## ✨ What's New

### 1. **Auto-Detection of Installed Databases**
- Application now scans `blast_databases/` folder on startup
- Shows which databases you actually have installed
- No more confusion about which databases are available!

### 2. **Status Icons in Dropdown**
The dropdown now shows 5 different status indicators:

| Icon | Meaning | Description |
|------|---------|-------------|
| ✓ | Converted & Ready | Database is ready for MMseqs2 searches |
| ⟳ | Converting | Conversion in progress |
| ✗ | Failed | Conversion failed (can retry) |
| ○ | Installed | BLAST database installed but not converted yet |
| ⊘ | Not Installed | Database not found in blast_databases folder |

### 3. **Three Database Source Options**

#### **Option 1: Use NCBI Database (from blast_databases folder)**
- Shows all NCBI databases with availability indicators
- Only allows conversion if database is installed
- Best for databases in your default location

#### **Option 2: Browse for NCBI Database (other location)** ⭐ NEW!
- Browse to a BLAST database anywhere on your computer
- Perfect for databases in external drives or custom locations
- Auto-converts and caches them
- Example use: "I have swissprot on D:\\ drive"

#### **Option 3: Use Existing MMseqs2 Database**
- Skip conversion entirely
- Use pre-converted MMseqs2 databases
- Fastest option if you already have MMseqs2 databases

## 🎯 How to Use

### Scenario 1: Using Default blast_databases Folder
```
1. Select "Use NCBI Database (from blast_databases folder)"
2. Choose database from dropdown (look for ○ or ✓)
3. Enter sequence and search
4. If ○ (installed), it will ask to convert
5. If ⊘ (not installed), you'll get a helpful error
```

### Scenario 2: Using Custom BLAST Database Location
```
1. Select "Browse for NCBI Database (other location)"
2. Click "Browse..." button
3. Navigate to your BLAST database file (e.g., D:\databases\swissprot\swissprot.phr)
4. The path will auto-fill
5. Enter sequence and search
6. First time: Asks to convert
7. Next time: Uses cached version!
```

### Scenario 3: Using Pre-converted MMseqs2 Database
```
1. Select "Use Existing MMseqs2 Database"
2. Click "Browse..." button
3. Select your MMseqs2 database file
4. Enter sequence and search
5. No conversion needed - instant search!
```

## 📊 UI Changes

### Before:
```
Database Options:
○ Use NCBI Database (auto-convert from BLAST)
○ Use Custom MMseqs2 Database

Select Database: [dropdown with all databases]
                 [no indicators]
```

### After:
```
Database Options:
○ Use NCBI Database (from blast_databases folder)
○ Browse for NCBI Database (other location)  ← NEW!
○ Use Existing MMseqs2 Database

Select Database: [✓ swissprot  ▼]  ← Status indicators!
Status: ✓ swissprot is ready to use
        Converted: 2025-11-03

--- OR ---

BLAST Database: [Browse...] [/path/to/custom/db]  ← Browse option!

--- OR ---

MMseqs2 Database: [Browse...] [/path/to/mmseqs2/db]
```

## 🔔 Important Notes

### Database Naming for Custom Databases
When you browse for a custom BLAST database, the system:
1. Extracts the database name from the file path
2. Prefixes it with `custom_` to avoid conflicts
3. Caches it separately from default databases

Example:
- File: `D:\external\databases\my_proteins\my_proteins.phr`
- Cached as: `custom_my_proteins`
- Saved to: `E:\Projects\Protein-GUI\mmseqs_databases\custom_my_proteins`

### Status Persistence
- All conversion status is saved in `mmseqs_databases/conversion_status.json`
- Persists across application restarts
- Tracks both default and custom databases

### Installation Check
The scan looks for `.phr` files (protein database headers):
```
blast_databases/
├── swissprot/
│   └── swissprot.phr  ← Found! ✓ Installed
├── nr/
│   └── nr.phr  ← Found! ✓ Installed
└── pdb/
    └── (empty)  ← Not found! ⊘ Not installed
```

## 🐛 Helpful Error Messages

### Not Installed
```
⊘ nr not installed

Download from NCBI or use 'Browse' to locate it
```
**What to do:**
- Download from NCBI and place in `blast_databases/nr/`
- OR use "Browse for NCBI Database" to locate it elsewhere

### Custom Database Not Found
```
Error: BLAST database files not found at:
D:\external\databases\mydb

Please ensure you selected the correct database file.
```
**What to do:**
- Check the path is correct
- Make sure you selected a `.phr` file
- Verify files exist (need `.phr`, `.pin`, `.psq`)

## 📈 Benefits

1. **✅ No More "Database Not Found" Confusion**
   - Clearly shows which databases are available
   - Explains what to do if not installed

2. **✅ Flexible Database Locations**
   - Use databases from anywhere on your system
   - No need to move large files

3. **✅ Better Organization**
   - Custom databases tracked separately
   - Easy to see what's converted vs what needs conversion

4. **✅ Time Saving**
   - Skip conversion if you have MMseqs2 databases
   - Cache all conversions regardless of source

## 🎉 Example Workflows

### Workflow A: First-Time User with swissprot Installed
```
1. Open MMseqs2 page
2. See: "✓ swissprot" in dropdown (scanned automatically!)
3. Enter sequence → Search
4. Instant search (already converted from earlier)
```

### Workflow B: User with External Database
```
1. Downloaded UniProt to D:\databases\
2. Select "Browse for NCBI Database"
3. Browse to D:\databases\uniprot\uniprot.phr
4. Convert (one-time, ~5 minutes)
5. Next time: Instant searches!
```

### Workflow C: User with Pre-converted MMseqs2 DB
```
1. Already have mmseqs2 database from HPC cluster
2. Select "Use Existing MMseqs2 Database"
3. Browse to database file
4. Instant searches (no conversion!)
```

---

## 🚀 Ready to Use!

Run the application and you'll see all the new features. The scanning happens automatically within 100ms of opening the MMseqs2 page!

```bash
python protein_gui.py
```

Enjoy the new flexibility! 🎊

