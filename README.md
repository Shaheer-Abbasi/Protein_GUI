# Sen Lab Protein Sequence Analysis Tool

A GUI application built with PyQt5 for running BLASTP searches on protein sequences with support for both remote NCBI databases and local databases.

## Features

- **User-friendly Interface**: Clean and intuitive GUI for entering protein sequences
- **BLASTP Integration**: Run BLASTP searches against NCBI databases
- **Remote & Local Database Support**: Choose between remote NCBI searches or local database files
- **Biopython Parsing**: Structured parsing of BLAST results with detailed statistics
- **Multiple Databases**: Support for SwissProt, nr, and PDB databases

## Requirements

- Python 3.7+
- PyQt5
- Biopython
- NCBI BLAST+ toolkit

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

3. Install NCBI BLAST+ toolkit:
   - Download from: https://blast.ncbi.nlm.nih.gov/Blast.cgi?PAGE_TYPE=BlastDocs&DOC_TYPE=Download
   - Update the `blastp_path` in the code to match your installation

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

1. Run the application:
   ```bash
   python protein_gui.py
   ```

2. Enter or paste a protein sequence (single-letter amino acid codes)

3. Choose database options:
   - **Remote**: Check "Use Remote NCBI Database" for online searches
   - **Local**: Uncheck for local database searches (much faster)

4. Select database: SwissProt, nr, or PDB

5. Click "Run BLASTP Search"

6. View detailed results with:
   - E-values and significance scores
   - Sequence alignments
   - Identity and similarity percentages

## Future Enhancements

- Integration with BLASTP for sequence similarity searches
- Implement GPU/CUDA acceleration to BLASTP to improve run time
- Improve UI design to support additional sequencing features
