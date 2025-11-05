"""Manager for parsing and handling MMseqs2 clustering results"""
from collections import Counter
import os


def parse_clustering_results(tsv_path):
    """
    Parse MMseqs2 clustering TSV format.
    
    TSV format: representative_id\tmember_id
    Each line shows a cluster member and its representative.
    
    Args:
        tsv_path: Path to the MMseqs2 clustering TSV file
        
    Returns:
        dict: Statistics and cluster information
    """
    clusters = {}  # {rep_id: [member_ids]}
    
    try:
        with open(tsv_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                parts = line.split('\t')
                if len(parts) != 2:
                    continue
                
                rep_id, member_id = parts
                
                if rep_id not in clusters:
                    clusters[rep_id] = []
                clusters[rep_id].append(member_id)
        
        if not clusters:
            return {
                'total_sequences': 0,
                'num_clusters': 0,
                'largest_cluster': 0,
                'avg_cluster_size': 0.0,
                'singletons': 0,
                'cluster_size_distribution': {},
                'clusters': {}
            }
        
        # Generate statistics
        cluster_sizes = [len(members) for members in clusters.values()]
        total_sequences = sum(cluster_sizes)
        
        stats = {
            'total_sequences': total_sequences,
            'num_clusters': len(clusters),
            'largest_cluster': max(cluster_sizes),
            'avg_cluster_size': total_sequences / len(clusters),
            'singletons': sum(1 for size in cluster_sizes if size == 1),
            'cluster_size_distribution': dict(Counter(cluster_sizes)),
            'clusters': clusters
        }
        
        return stats
        
    except Exception as e:
        raise Exception(f"Error parsing clustering results: {str(e)}")


def export_clustering_tsv(stats, output_path):
    """
    Export clustering results to TSV file.
    
    Format: cluster_id, representative_id, member_id, cluster_size
    
    Args:
        stats: Statistics dictionary from parse_clustering_results
        output_path: Path to save the TSV file
    """
    try:
        with open(output_path, 'w') as f:
            # Write header
            f.write("cluster_id\trepresentative_id\tmember_id\tcluster_size\n")
            
            # Write cluster data
            clusters = stats['clusters']
            for cluster_idx, (rep_id, members) in enumerate(clusters.items(), 1):
                cluster_size = len(members)
                for member_id in members:
                    f.write(f"{cluster_idx}\t{rep_id}\t{member_id}\t{cluster_size}\n")
        
        return True
    except Exception as e:
        raise Exception(f"Error exporting TSV: {str(e)}")


def get_cluster_table_data(stats, max_rows=1000):
    """
    Generate table data for display in UI.
    
    Args:
        stats: Statistics dictionary from parse_clustering_results
        max_rows: Maximum number of rows to return
        
    Returns:
        list: List of tuples (cluster_id, rep_id, cluster_size, members_preview)
    """
    table_data = []
    clusters = stats['clusters']
    
    for cluster_idx, (rep_id, members) in enumerate(sorted(
        clusters.items(), 
        key=lambda x: len(x[1]), 
        reverse=True  # Sort by cluster size, largest first
    ), 1):
        cluster_size = len(members)
        
        # Create a preview of members (first 5)
        if cluster_size <= 5:
            members_preview = ", ".join(members)
        else:
            members_preview = ", ".join(members[:5]) + f", ... ({cluster_size - 5} more)"
        
        table_data.append((cluster_idx, rep_id, cluster_size, members_preview))
        
        if len(table_data) >= max_rows:
            break
    
    return table_data


def validate_fasta_file(fasta_path):
    """
    Validate FASTA file format and get basic statistics.
    
    Args:
        fasta_path: Path to FASTA file
        
    Returns:
        tuple: (is_valid, error_message, sequence_count, file_size_mb)
    """
    try:
        if not os.path.exists(fasta_path):
            return False, "File does not exist", 0, 0
        
        file_size = os.path.getsize(fasta_path)
        file_size_mb = file_size / (1024 * 1024)
        
        # Check file size limit (500MB)
        if file_size_mb > 500:
            return False, f"File too large ({file_size_mb:.1f} MB). Maximum size is 500 MB.", 0, file_size_mb
        
        # Quick validation: check for FASTA format
        sequence_count = 0
        has_sequence = False
        
        with open(fasta_path, 'r') as f:
            first_line = f.readline().strip()
            if not first_line.startswith('>'):
                return False, "Not a valid FASTA file (must start with '>')", 0, file_size_mb
            
            sequence_count = 1
            
            # Count sequences (headers starting with '>')
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if line.startswith('>'):
                    sequence_count += 1
                elif not has_sequence:
                    # Check if we have at least one sequence line
                    has_sequence = True
                    # Validate amino acid characters (allow standard 20 + ambiguous)
                    valid_chars = set('ACDEFGHIKLMNPQRSTVWYXBZJU*-')
                    if not all(c.upper() in valid_chars for c in line if c.isalpha() or c in '*-'):
                        return False, "Invalid characters in sequence", sequence_count, file_size_mb
        
        if not has_sequence:
            return False, "No sequences found in FASTA file", 0, file_size_mb
        
        if sequence_count == 0:
            return False, "No sequences found in FASTA file", 0, file_size_mb
        
        return True, "", sequence_count, file_size_mb
        
    except Exception as e:
        return False, f"Error reading file: {str(e)}", 0, 0

