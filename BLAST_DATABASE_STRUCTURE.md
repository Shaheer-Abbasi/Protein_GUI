# BLAST Database Folder Structure

## ✅ Correct Structure

Your BLAST databases should be organized as follows:

```
blast_databases/
├── swissprot/
│   ├── swissprot.pdb
│   ├── swissprot.phr
│   ├── swissprot.pin
│   ├── swissprot.pjs
│   ├── swissprot.pog
│   ├── swissprot.pos
│   ├── swissprot.pot
│   ├── swissprot.ppd
│   ├── swissprot.ppi
│   ├── swissprot.psq
│   ├── swissprot.ptf
│   ├── swissprot.pto
│   ├── taxdb.btd
│   ├── taxdb.bti
│   └── taxonomy4blast.sqlite3
│
├── nr/
│   ├── nr.00.phr
│   ├── nr.00.pin
│   ├── nr.00.psq
│   └── ... (more nr files)
│
└── pdb/
    ├── pdb.phr
    ├── pdb.pin
    ├── pdb.psq
    └── ... (more pdb files)
```

## 📁 Path Structure

Each database should follow this pattern:
```
blast_databases/{db_name}/{db_name}.{extension}
```

Examples:
- `blast_databases/swissprot/swissprot.phr`
- `blast_databases/nr/nr.phr`
- `blast_databases/pdb/pdb.phr`

## 🔧 How the Application Uses This

When you select "swissprot" in the MMseqs2 page:

1. Application looks for: `E:\Projects\Protein-GUI\blast_databases\swissprot\swissprot`
2. Converts to WSL path: `/mnt/e/Projects/Protein-GUI/blast_databases/swissprot/swissprot`
3. blastdbcmd reads files: `swissprot.phr`, `swissprot.pin`, `swissprot.psq`, etc.

## ❌ Common Mistakes

### Mistake 1: Files in root directory
```
❌ blast_databases/
    ├── swissprot.phr
    ├── swissprot.pin
    └── swissprot.psq
```
**Fix:** Move files into a subfolder named `swissprot/`

### Mistake 2: Wrong subfolder name
```
❌ blast_databases/
    └── swiss/              ← Wrong name
        ├── swissprot.phr
        └── ...
```
**Fix:** Rename folder to match database name: `swissprot/`

### Mistake 3: Nested incorrectly
```
❌ blast_databases/
    └── swissprot/
        └── swissprot/      ← Too many levels
            ├── swissprot.phr
            └── ...
```
**Fix:** Remove extra nesting level

## 📥 Setting Up BLAST Databases

### Option 1: Download from NCBI
```bash
# Create directory
mkdir -p blast_databases/swissprot

# Download database
cd blast_databases/swissprot
wget ftp://ftp.ncbi.nlm.nih.gov/blast/db/swissprot.tar.gz

# Extract
tar -xvzf swissprot.tar.gz
rm swissprot.tar.gz
```

### Option 2: Use update_blastdb.pl
```bash
# In blast_databases directory
cd blast_databases

# Download swissprot
mkdir swissprot
cd swissprot
update_blastdb.pl --decompress swissprot
```

### Option 3: Create from FASTA
```bash
# If you have a FASTA file
mkdir -p blast_databases/mydb
cd blast_databases/mydb

# Create BLAST database
makeblastdb -in sequences.fasta -dbtype prot -out mydb -parse_seqids
```

## 🧪 Verify Your Setup

Run this in PowerShell/CMD:

```powershell
# Check if files exist
dir E:\Projects\Protein-GUI\blast_databases\swissprot\

# Should see files like:
#   swissprot.phr
#   swissprot.pin
#   swissprot.psq
```

Or in WSL:

```bash
# Check from WSL
ls /mnt/e/Projects/Protein-GUI/blast_databases/swissprot/

# Test with blastdbcmd
blastdbcmd -db /mnt/e/Projects/Protein-GUI/blast_databases/swissprot/swissprot -info

# Should show database statistics
```

## 🔍 Troubleshooting

### Error: "BLAST Database error: No alias or index file found"
**Cause:** Database files not in correct location
**Fix:** 
1. Check folder structure matches pattern above
2. Verify `.phr`, `.pin`, `.psq` files exist
3. Make sure folder name matches database name

### Error: "BLAST database files not found"
**Cause:** Missing or incomplete database
**Fix:**
1. Re-download database from NCBI
2. Ensure extraction completed successfully
3. Check file permissions

## 📊 Required Files

For **protein databases** (like swissprot, nr, pdb):
- `.phr` - Header file ✓
- `.pin` - Index file ✓
- `.psq` - Sequence file ✓
- `.pdb` - Metadata (optional)
- `.pog`, `.pos`, `.pot`, etc. - Additional indices

For **nucleotide databases** (like nt):
- `.nhr` - Header file
- `.nin` - Index file
- `.nsq` - Sequence file

## ✅ Final Checklist

- [ ] Database folder exists: `blast_databases/{db_name}/`
- [ ] Files are inside subfolder, not root
- [ ] Folder name matches database name
- [ ] `.phr`, `.pin`, `.psq` files present
- [ ] Can run `blastdbcmd -db {path} -info` successfully
- [ ] Path works from WSL: `/mnt/e/Projects/Protein-GUI/...`

---

**Your structure is correct!** ✅ The fix has been applied and the application will now find your databases properly.

