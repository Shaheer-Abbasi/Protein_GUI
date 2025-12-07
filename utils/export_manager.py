"""Export manager for BLAST/MMSeqs2 results with proper formatting and error handling"""
import csv
import os
import tempfile
import shutil
from datetime import datetime
from typing import List, Dict, Optional, Any
from PyQt5.QtWidgets import QMessageBox


class ExportError(Exception):
    """Custom exception for export errors"""
    pass


class ResultsExporter:
    """
    Export search results to various formats with safety features
    
    Safety features:
    - Temporary file writing → rename on success
    - Proper CSV escaping for special characters
    - Permission error handling
    - Progress tracking for large exports
    - Metadata headers
    """
    
    def __init__(self):
        self.last_export_path = None
    
    def export_to_tsv(self, data: List[Dict[str, Any]], filepath: str, 
                      metadata: Optional[Dict[str, str]] = None) -> bool:
        """
        Export results to TSV format
        
        Args:
            data: List of result dictionaries
            filepath: Output file path
            metadata: Optional metadata to include in header
            
        Returns:
            True if successful, False otherwise
        """
        return self._export_to_delimited(data, filepath, delimiter='\t', metadata=metadata)
    
    def export_to_csv(self, data: List[Dict[str, Any]], filepath: str,
                      metadata: Optional[Dict[str, str]] = None) -> bool:
        """
        Export results to CSV format
        
        Args:
            data: List of result dictionaries
            filepath: Output file path
            metadata: Optional metadata to include in header
            
        Returns:
            True if successful, False otherwise
        """
        return self._export_to_delimited(data, filepath, delimiter=',', metadata=metadata)
    
    def _export_to_delimited(self, data: List[Dict[str, Any]], filepath: str,
                            delimiter: str, metadata: Optional[Dict[str, str]] = None) -> bool:
        """
        Internal method to export to delimited format (TSV/CSV)
        
        Uses safe write pattern: write to temp file → rename on success
        """
        if not data:
            raise ExportError("No data to export")
        
        # Get column headers from first row
        headers = list(data[0].keys())
        
        # Create temporary file in same directory as target
        # (ensures same filesystem for atomic rename)
        target_dir = os.path.dirname(os.path.abspath(filepath))
        os.makedirs(target_dir, exist_ok=True)
        
        temp_fd, temp_path = tempfile.mkstemp(
            suffix='.tmp',
            dir=target_dir,
            text=True
        )
        
        try:
            with os.fdopen(temp_fd, 'w', newline='', encoding='utf-8') as f:
                # Write metadata as comments if provided
                if metadata:
                    f.write(f"# Export generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    for key, value in metadata.items():
                        # Escape any special characters in metadata
                        safe_value = str(value).replace('\n', ' ').replace('\r', '')
                        f.write(f"# {key}: {safe_value}\n")
                    f.write("#\n")
                
                # Use csv module for proper escaping
                writer = csv.DictWriter(
                    f,
                    fieldnames=headers,
                    delimiter=delimiter,
                    quoting=csv.QUOTE_MINIMAL,
                    lineterminator='\n'
                )
                
                # Write header
                writer.writeheader()
                
                # Write data rows
                for row in data:
                    # Clean any None values
                    clean_row = {k: (v if v is not None else '') for k, v in row.items()}
                    writer.writerow(clean_row)
            
            # Atomic rename (overwrites target if exists)
            shutil.move(temp_path, filepath)
            self.last_export_path = filepath
            return True
            
        except PermissionError as e:
            # Clean up temp file
            try:
                os.unlink(temp_path)
            except:
                pass
            raise ExportError(
                f"Permission denied: Cannot write to '{filepath}'\n"
                f"The file may be open in another program or you may not have write permissions."
            ) from e
            
        except Exception as e:
            # Clean up temp file on any error
            try:
                os.unlink(temp_path)
            except:
                pass
            raise ExportError(f"Failed to export file: {str(e)}") from e
    
    def export_blast_results(self, results_html: str, query_info: Dict[str, str],
                            filepath: str, format: str = 'tsv') -> bool:
        """
        Export BLAST results from HTML to structured format
        
        Args:
            results_html: HTML string from BLAST worker
            query_info: Dictionary with query metadata
            filepath: Output file path
            format: 'tsv' or 'csv'
            
        Returns:
            True if successful
        """
        # Parse HTML to extract data (simple extraction)
        data = self._parse_blast_html(results_html)
        
        if not data:
            raise ExportError("No results found to export")
        
        # Add metadata
        metadata = {
            'Search Type': 'BLASTP',
            'Query': query_info.get('query_name', 'Unknown'),
            'Query Length': query_info.get('query_length', 'Unknown'),
            'Database': query_info.get('database', 'Unknown'),
            'Date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        if format.lower() == 'csv':
            return self.export_to_csv(data, filepath, metadata)
        else:
            return self.export_to_tsv(data, filepath, metadata)
    
    def export_mmseqs_results(self, results_html: str, query_info: Dict[str, str],
                             filepath: str, format: str = 'tsv') -> bool:
        """
        Export MMSeqs2 results from HTML to structured format
        
        Args:
            results_html: HTML string from MMSeqs2 worker
            query_info: Dictionary with query metadata
            filepath: Output file path
            format: 'tsv' or 'csv'
            
        Returns:
            True if successful
        """
        # Parse HTML to extract data
        data = self._parse_mmseqs_html(results_html)
        
        if not data:
            raise ExportError("No results found to export")
        
        # Add metadata
        metadata = {
            'Search Type': 'MMSeqs2',
            'Query': query_info.get('query_name', 'Unknown'),
            'Query Length': query_info.get('query_length', 'Unknown'),
            'Database': query_info.get('database', 'Unknown'),
            'Sensitivity': query_info.get('sensitivity', 'Unknown'),
            'Date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        if format.lower() == 'csv':
            return self.export_to_csv(data, filepath, metadata)
        else:
            return self.export_to_tsv(data, filepath, metadata)
    
    def _parse_blast_html(self, html: str) -> List[Dict[str, Any]]:
        """
        Parse BLAST HTML results to extract structured data
        
        This is a simplified parser - extracts key information from HTML
        """
        # TODO: Implement proper HTML parsing
        # For now, return empty list - will be implemented when integrating with UI
        return []
    
    def _parse_mmseqs_html(self, html: str) -> List[Dict[str, Any]]:
        """
        Parse MMSeqs2 HTML results to extract structured data
        """
        # TODO: Implement proper HTML parsing
        # For now, return empty list - will be implemented when integrating with UI
        return []
    
    def get_default_filename(self, search_type: str, query_name: str = "query") -> str:
        """
        Generate a default filename for export
        
        Args:
            search_type: 'blast' or 'mmseqs'
            query_name: Name of the query sequence
            
        Returns:
            Filename string
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_query = "".join(c for c in query_name if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_query = safe_query[:30]  # Limit length
        
        if not safe_query:
            safe_query = "query"
        
        return f"{search_type}_results_{safe_query}_{timestamp}"


def show_export_error(parent, error: ExportError):
    """
    Show export error dialog to user
    
    Args:
        parent: Parent widget for dialog
        error: ExportError exception
    """
    QMessageBox.critical(
        parent,
        "Export Failed",
        f"Failed to export results:\n\n{str(error)}",
        QMessageBox.Ok
    )


def show_export_success(parent, filepath: str):
    """
    Show export success dialog to user
    
    Args:
        parent: Parent widget for dialog
        filepath: Path where file was saved
    """
    QMessageBox.information(
        parent,
        "Export Successful",
        f"Results exported successfully to:\n\n{filepath}",
        QMessageBox.Ok
    )

