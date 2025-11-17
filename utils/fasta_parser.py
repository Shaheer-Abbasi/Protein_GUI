"""FASTA file parser with robust validation and error handling"""
import os
from typing import List, Tuple, Optional


class FastaSequence:
    """Represents a single FASTA sequence"""
    def __init__(self, header: str, sequence: str):
        self.header = header
        self.sequence = sequence
        self.id = self._extract_id(header)
    
    def _extract_id(self, header: str) -> str:
        """Extract ID from FASTA header"""
        # Remove '>' if present
        header = header.lstrip('>')
        # Get first word as ID
        return header.split()[0] if header else "Unknown"
    
    def __str__(self):
        return f"{self.id}: {len(self.sequence)} amino acids"
    
    def __repr__(self):
        return f"FastaSequence(id='{self.id}', length={len(self.sequence)})"


class FastaParseError(Exception):
    """Custom exception for FASTA parsing errors"""
    pass


class FastaParser:
    """
    Robust FASTA file parser with validation
    
    Safety features:
    - File size limits (10MB warning, 50MB hard limit)
    - Character encoding validation
    - Empty file detection
    - Format validation
    - Multi-sequence support
    """
    
    # File size limits
    WARNING_SIZE_MB = 10
    MAX_SIZE_MB = 50
    
    # Valid amino acid codes (standard 20 + ambiguous codes)
    VALID_AA_CODES = set('ACDEFGHIKLMNPQRSTVWYBZXJU*-')
    
    def __init__(self):
        self.sequences: List[FastaSequence] = []
        self.warnings: List[str] = []
    
    def parse_file(self, filepath: str) -> List[FastaSequence]:
        """
        Parse a FASTA file and return list of sequences
        
        Args:
            filepath: Path to FASTA file
            
        Returns:
            List of FastaSequence objects
            
        Raises:
            FastaParseError: If file cannot be parsed
        """
        self.sequences = []
        self.warnings = []
        
        # Validate file exists
        if not os.path.exists(filepath):
            raise FastaParseError(f"File not found: {filepath}")
        
        # Check file size
        file_size_mb = os.path.getsize(filepath) / (1024 * 1024)
        if file_size_mb > self.MAX_SIZE_MB:
            raise FastaParseError(
                f"File too large: {file_size_mb:.1f}MB (max {self.MAX_SIZE_MB}MB)"
            )
        elif file_size_mb > self.WARNING_SIZE_MB:
            self.warnings.append(
                f"Large file: {file_size_mb:.1f}MB - parsing may take a moment"
            )
        
        # Read and parse file
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            # Try with latin-1 encoding as fallback
            try:
                with open(filepath, 'r', encoding='latin-1') as f:
                    content = f.read()
                self.warnings.append("File encoding detected as Latin-1")
            except Exception as e:
                raise FastaParseError(f"Unable to read file: {str(e)}")
        except Exception as e:
            raise FastaParseError(f"Error reading file: {str(e)}")
        
        # Check if file is empty
        if not content.strip():
            raise FastaParseError("File is empty")
        
        # Parse FASTA content
        self.sequences = self._parse_content(content)
        
        if not self.sequences:
            raise FastaParseError("No valid FASTA sequences found")
        
        return self.sequences
    
    def parse_string(self, fasta_string: str) -> List[FastaSequence]:
        """
        Parse FASTA format string
        
        Args:
            fasta_string: FASTA formatted text
            
        Returns:
            List of FastaSequence objects
        """
        self.sequences = []
        self.warnings = []
        
        if not fasta_string.strip():
            raise FastaParseError("Empty FASTA string")
        
        self.sequences = self._parse_content(fasta_string)
        
        if not self.sequences:
            raise FastaParseError("No valid FASTA sequences found")
        
        return self.sequences
    
    def _parse_content(self, content: str) -> List[FastaSequence]:
        """Parse FASTA content string"""
        sequences = []
        current_header = None
        current_sequence = []
        
        lines = content.split('\n')
        
        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            
            # Skip empty lines
            if not line:
                continue
            
            # Header line
            if line.startswith('>'):
                # Save previous sequence if exists
                if current_header is not None:
                    seq_str = ''.join(current_sequence)
                    if seq_str:  # Only add if sequence is not empty
                        sequences.append(FastaSequence(current_header, seq_str))
                    else:
                        self.warnings.append(
                            f"Empty sequence for header: {current_header}"
                        )
                
                # Start new sequence
                current_header = line
                current_sequence = []
            
            # Sequence line
            else:
                if current_header is None:
                    raise FastaParseError(
                        f"Line {line_num}: Sequence found before header. "
                        "FASTA files must start with '>' header line."
                    )
                
                # Validate characters
                line_upper = line.upper()
                invalid_chars = set(line_upper) - self.VALID_AA_CODES - {' ', '\t'}
                if invalid_chars:
                    self.warnings.append(
                        f"Line {line_num}: Invalid characters found: "
                        f"{', '.join(sorted(invalid_chars))}"
                    )
                
                # Remove whitespace and add to sequence
                clean_line = ''.join(line_upper.split())
                current_sequence.append(clean_line)
        
        # Don't forget the last sequence
        if current_header is not None:
            seq_str = ''.join(current_sequence)
            if seq_str:
                sequences.append(FastaSequence(current_header, seq_str))
            else:
                self.warnings.append(
                    f"Empty sequence for header: {current_header}"
                )
        
        return sequences
    
    def validate_sequence(self, sequence: str) -> Tuple[bool, Optional[str]]:
        """
        Validate a protein sequence
        
        Args:
            sequence: Amino acid sequence string
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not sequence:
            return False, "Sequence is empty"
        
        # Check length
        if len(sequence) < 10:
            return False, f"Sequence too short ({len(sequence)} amino acids). Minimum 10 required."
        
        if len(sequence) > 10000:
            return False, f"Sequence too long ({len(sequence)} amino acids). Maximum 10,000 allowed."
        
        # Check for invalid characters
        seq_upper = sequence.upper()
        invalid_chars = set(seq_upper) - self.VALID_AA_CODES - {' ', '\t', '\n', '\r'}
        
        if invalid_chars:
            return False, f"Invalid characters in sequence: {', '.join(sorted(invalid_chars))}"
        
        return True, None
    
    def get_warnings(self) -> List[str]:
        """Get list of parsing warnings"""
        return self.warnings.copy()
    
    def has_warnings(self) -> bool:
        """Check if there are any warnings"""
        return len(self.warnings) > 0


def validate_amino_acid_sequence(sequence: str) -> Tuple[bool, str]:
    """
    Quick validation function for amino acid sequences
    
    Args:
        sequence: Amino acid sequence
        
    Returns:
        Tuple of (is_valid, message)
    """
    parser = FastaParser()
    is_valid, error = parser.validate_sequence(sequence)
    
    if is_valid:
        return True, f"Valid sequence ({len(sequence)} amino acids)"
    else:
        return False, error

