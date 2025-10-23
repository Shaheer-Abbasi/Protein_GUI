# Comprehensive NCBI BLAST databases with descriptions
NCBI_DATABASES = {
    # Protein databases
    'nr': 'Non-redundant protein sequences (all proteins)',
    'refseq_protein': 'Reference proteins (RefSeq)',
    'swissprot': 'UniProtKB/Swiss-Prot (curated protein sequences)',
    'pdb': 'Protein Data Bank proteins',
    'env_nr': 'Non-redundant protein sequences from environmental samples',
    'tsa_nr': 'Non-redundant protein sequences from transcriptome shotgun assembly',
    'pataa': 'Patent protein sequences',
    'pdbaa': 'PDB protein sequences (deprecated, use pdb)',

    # Nucleotide databases  
    'nt': 'Nucleotide collection (nt)',
    'refseq_rna': 'Reference RNA sequences',
    'refseq_genomic': 'Reference genomic sequences',
    'chromosome': 'RefSeq chromosome sequences',
    'tsa_nt': 'Transcriptome Shotgun Assembly nucleotides',
    'env_nt': 'Environmental nucleotide sequences',
    'wgs': 'Whole-genome shotgun sequences',
    'gss': 'Genome survey sequences',
    'est': 'Expressed sequence tags',
    'est_human': 'Human ESTs',
    'est_mouse': 'Mouse ESTs',
    'est_others': 'ESTs from organisms other than human and mouse',
    'htgs': 'High throughput genomic sequences',
    'patnt': 'Patent nucleotide sequences',
    'pdbnt': 'PDB nucleotide sequences',
    'dbsts': 'Database of sequence tagged sites',
    'landmark': 'Landmark database for BLAST',
    '16S_ribosomal_RNA': '16S ribosomal RNA sequences',
    'ITS_RefSeq_Fungi': 'Internal transcribed spacer region, fungi',
    '18S_fungal_sequences': '18S ribosomal RNA sequences, fungi',
    '28S_fungal_sequences': '28S ribosomal RNA sequences, fungi',
    'Betacoronavirus': 'Betacoronavirus sequences',

    # Organism-specific databases
    'ref_euk_rep_genomes': 'Representative eukaryotic genomes',
    'ref_prok_rep_genomes': 'Representative prokaryotic genomes',
    'ref_viroids_rep_genomes': 'Representative viroid genomes',
    'ref_viruses_rep_genomes': 'Representative viral genomes',

    # Specialized databases
    'cdd': 'Conserved Domain Database',
    'smart': 'Simple Modular Architecture Research Tool',
    'pfam': 'Protein families database',
    'kog': 'EuKaryotic Orthologous Groups',
    'cog': 'Clusters of Orthologous Groups',
    'prk': 'Protein clusters',
    'tigr': 'TIGRFAMs database',

    # Human genome databases
    'human_genomic': 'Human genomic sequences',
    'human_genome': 'Human genome',
    'mouse_genomic': 'Mouse genomic sequences',
    'mouse_genome': 'Mouse genome'
}

# Categories for better organization
DATABASE_CATEGORIES = {
    'Protein Databases': [
        'nr', 'refseq_protein', 'swissprot', 'pdb', 'env_nr', 'tsa_nr', 'pataa'
    ],
    'Nucleotide Databases': [
        'nt', 'refseq_rna', 'refseq_genomic', 'chromosome', 'tsa_nt', 'env_nt', 'wgs'
    ],
    'Specialized Sequences': [
        '16S_ribosomal_RNA', 'ITS_RefSeq_Fungi', '18S_fungal_sequences',
        '28S_fungal_sequences', 'Betacoronavirus'
    ],
    'Genome Collections': [
        'ref_euk_rep_genomes', 'ref_prok_rep_genomes', 'ref_viroids_rep_genomes',
        'ref_viruses_rep_genomes', 'human_genomic', 'mouse_genomic'
    ],
    'Domain/Family Databases': [
        'cdd', 'smart', 'pfam', 'kog', 'cog', 'prk', 'tigr'
    ],
    'Legacy/Other': [
        'est', 'est_human', 'est_mouse', 'est_others', 'htgs', 'patnt',
        'pdbnt', 'dbsts', 'landmark', 'gss', 'pdbaa'
    ]
}
