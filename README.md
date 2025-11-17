# Sen Lab Protein Sequence Analysis Suite

A comprehensive GUI application built with PyQt5 for protein sequence analysis, featuring BLASTP searches, MMseqs2 searches, and protein clustering capabilities. Designed for both remote NCBI databases and local database files with full cross-platform support.

## Overview

This application provides a complete workflow for protein sequence analysis:

1. **Search**: Run BLASTP or MMseqs2 searches against protein databases
2. **Analyze**: View detailed results with statistics and alignments
3. **Export**: Save results in TSV or CSV format
4. **Cluster**: Select interesting results and perform sequence clustering
5. **Visualize**: Interactive charts with zoom capabilities

## Features

### Search Tools
- **BLASTP Search**: Industry-standard protein sequence alignment
- **MMseqs2 Search**: Ultra-fast protein sequence search (up to 400x faster than BLAST)
- **Remote & Local Databases**: Use NCBI remote servers or local database files
- **Multiple Input Methods**: 
  - Paste sequences directly
  - Upload FASTA files (including multi-sequence support)
  - Search by protein name or UniProt ID via AlphaFold database

### Results Analysis
- **Detailed Statistics**: E-values, bit scores, identity percentages, query coverage
- **Interactive Results**: Click to view full alignments and sequence details
- **Real-time Summary Panel**: Total hits, best E-value, average identity
- **Export Options**: Save results as TSV or CSV files

### Clustering
- **Cluster from Search Results**: Select interesting hits and cluster them directly
- **Multiple Selection Modes**: 
  - Top N matches
  - E-value threshold
  - Manual checkbox selection
- **MMseqs2 Clustering**: Fast and sensitive sequence clustering
- **Configurable Parameters**: Adjust identity threshold, coverage, and sensitivity
- **Interactive Visualization**: Distribution charts with zoom and pan

### User Interface
- **Resizable Layouts**: Drag-and-drop splitters for custom workspace
- **Persistent Settings**: UI state saved between sessions
- **Chart Zoom Controls**: Ctrl+Scroll or button controls for chart viewing
- **Progress Tracking**: Real-time progress for long-running operations
- **Cross-platform**: Works on Windows with WSL support for MMseqs2

## Requirements

### Software
- Python 3.7 or higher
- PyQt5
- Biopython
- NCBI BLAST+ toolkit
- MMseqs2 (optional, for MMseqs2 search and clustering)
- WSL (Windows Subsystem for Linux) - Required for MMseqs2 on Windows

### Python Packages
- PyQt5
- Biopython
- requests (for AlphaFold/UniProt API)
- matplotlib (for clustering visualization)

## Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/yourusername/Protein-GUI.git
   cd Protein-GUI
   ```

2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the setup wizard to configure paths (recommended):
   ```bash
   python setup_wizard.py
   ```
   The setup wizard will:
   - Detect BLAST+ installation automatically
   - Detect MMSeqs2 installation (Windows or WSL)
   - Find available databases
   - Create a portable `config.json` file

4. **Manual Installation** (if setup wizard doesn't find tools):
   - **BLAST+**: Download from https://ftp.ncbi.nlm.nih.gov/blast/executables/blast+/LATEST/
   - **MMSeqs2**: Download from https://github.com/soedinglab/MMseqs2/releases
   - Update paths in `config.json` after installation

## Configuration for Multiple Computers

The application is now **fully portable**! To use on a different computer:

1. Copy the entire project folder to the new computer
2. Run `python setup_wizard.py` to auto-detect tools on the new system
3. The wizard will create a new `config.json` with machine-specific paths

**Note**: All database paths are now relative to the project directory, so you can move the entire folder without issues.

## Database Setup

### Remote Databases (Default)
- No setup required
- Uses NCBI's remote servers
- Slower but always up-to-date

### Local Databases (Recommended for frequent use)
1. Create a `blast_databases` directory in your project folder
2. Download databases from NCBI:
   ```bash
   # For SwissProt
   wget https://ftp.ncbi.nlm.nih.gov/blast/db/swissprot.tar.gz
   tar -xzf swissprot.tar.gz
   ```
3. Or use the GUI's "Browse..." button to point to your database directory

## Usage

### Starting the Application

```bash
python protein_gui.py
```

The home screen provides access to three main tools:
- **BLASTP Search**: Standard protein BLAST searches
- **MMseqs2 Search**: Fast protein sequence searches
- **MMseqs2 Clustering**: Cluster protein sequences

### BLASTP Search

1. **Input your sequence** using one of three methods:
   - **Paste**: Directly paste amino acid sequence
   - **Upload FASTA**: Select a FASTA file from your computer
   - **Search Protein**: Search by protein name or UniProt ID
   
2. **Configure search parameters**:
   - Choose between remote NCBI or local database
   - Select database (SwissProt, nr, PDB, etc.)
   - Browse to custom database location if needed

3. **Run the search**:
   - Click "Run BLASTP Search"
   - Monitor progress in real-time
   - View results with statistics

4. **Work with results**:
   - Export as TSV or CSV
   - Click "Cluster Results" to cluster selected hits

### MMseqs2 Search

1. **Input your sequence** (same three methods as BLASTP)

2. **Configure parameters**:
   - Select database
   - Choose sensitivity level (fast, sensitive, very sensitive)
   - Databases must be converted to MMseqs2 format (automatic prompt)

3. **View results** and export or cluster as needed

### Clustering Workflow

#### From Search Results:
1. Run a BLASTP or MMseqs2 search
2. Click "Cluster Results" button
3. **Select sequences** using:
   - Top N matches (e.g., top 50)
   - E-value threshold (e.g., < 1e-10)
   - Manual checkbox selection
4. **Configure clustering**:
   - View sequence retrieval summary
   - Choose clustering method (easy-cluster or linclust)
   - Adjust parameters (identity, coverage, sensitivity)
5. **View results**:
   - Interactive distribution chart
   - Detailed cluster table
   - Export options

#### From FASTA File:
1. Select "MMseqs2 Clustering" from home screen
2. Upload FASTA file
3. Configure clustering parameters
4. Run clustering
5. View and export results

### Advanced Features

#### Chart Viewing
- Click "Maximize Chart" to open full-screen view
- Use Ctrl+Scroll to zoom in/out
- Use zoom buttons: +, -, 100%, Fit to Window
- Zoom range: 10% to 500%

#### Export Options
- **TSV/CSV Export**: Save search results with all metadata
- **FASTA Export**: Save representative sequences from clusters
- **Cluster TSV**: Export detailed cluster membership

#### Sequence Input
- **Multi-FASTA Support**: Upload files with multiple sequences
- **AlphaFold Database**: Search by protein name and auto-populate sequence
- **UniProt Integration**: Automatic sequence retrieval from UniProt
- **Validation**: Real-time sequence length counter and validation

## Configuration

### Portable Setup
The application stores configuration in `config.json`, which is machine-specific and not tracked by git. To use on multiple computers:

1. Copy the project folder to the new computer
2. Run `python setup_wizard.py`
3. The wizard auto-detects tools and creates appropriate config

### Manual Configuration
Edit `config.json` to set paths:
```json
{
  "blast_path": "blastp",
  "mmseqs_path": "mmseqs",
  "blast_db_dir": "blast_databases"
}
```

### Database Management
- Place local databases in `blast_databases/` directory
- MMseqs2 databases are auto-converted on first use
- Both absolute and relative paths supported

## Troubleshooting

### MMseqs2 Not Found
- **Windows**: Install WSL and MMseqs2 in WSL environment
- **Linux/Mac**: Install MMseqs2 and ensure it's in PATH
- Run `setup_wizard.py` to detect installation

### BLAST Not Found
- Download BLAST+ from NCBI
- Add to system PATH or specify full path in `config.json`
- Run `setup_wizard.py` for automatic detection

### Clustering Shows 1 Cluster
- This is normal when selecting very similar sequences (e.g., top 5 matches)
- Try selecting more diverse results (higher E-value threshold)
- Or increase identity threshold in clustering parameters

### Missing Sequences During Clustering
- Some sequences may fail to retrieve (this is normal)
- The dialog shows success/failure summary
- Uses 3-layer fallback: local hit data → blastdbcmd → UniProt API
- Can proceed with successfully retrieved sequences

## Architecture

### Core Components
- `protein_gui.py`: Main application entry point
- `ui/`: User interface pages and dialogs
- `core/`: Workers for BLAST, MMseqs2, and clustering operations
- `utils/`: Helper modules for parsing, export, and sequence retrieval

### Key Features
- **Non-blocking Operations**: All searches use QThread workers
- **Automatic Cleanup**: Temporary files cleaned on exit
- **Persistent State**: UI preferences saved with QSettings
- **Error Handling**: Comprehensive validation and user feedback

## Contributing

This is a research tool developed for the Sen Lab. For questions or issues, please contact the development team.

## License

Proprietary - Sen Lab
