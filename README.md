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

This is a research tool developed by the Sen Lab team at the University of Houston team biologists world-wide. For questions or issues, please contact Sen Lab.

Proprietary - Sen Lab
