"""Visualization tools for MMseqs2 clustering results"""
import os


def create_distribution_chart(stats, output_path=None, max_display=50):
    """
    Create a bar chart showing cluster size distribution.
    
    Args:
        stats: Statistics dictionary from parse_clustering_results
        output_path: Optional path to save the chart as PNG
        max_display: Maximum number of bars to display (aggregates rest as "Others")
        
    Returns:
        tuple: (success: bool, figure or error_message)
    """
    try:
        import matplotlib
        matplotlib.use('Agg')  # Use non-interactive backend
        import matplotlib.pyplot as plt
        from collections import Counter
        
        cluster_size_dist = stats['cluster_size_distribution']
        
        if not cluster_size_dist:
            return False, "No cluster data available"
        
        # Sort by cluster size (descending)
        # cluster_size_dist is {cluster_size: count}
        sorted_items = sorted(cluster_size_dist.items(), key=lambda x: x[0], reverse=False)
        
        # If too many unique cluster sizes, aggregate the long tail
        if len(sorted_items) > max_display:
            top_items = sorted_items[:max_display]
            other_count = sum(count for size, count in sorted_items[max_display:])
            
            labels = [f"{size}" for size, count in top_items] + ["Others"]
            values = [count for size, count in top_items] + [other_count]
            colors = ['#8e44ad'] * len(top_items) + ['#95a5a6']
        else:
            labels = [f"{size}" for size, count in sorted_items]
            values = [count for size, count in sorted_items]
            colors = ['#8e44ad'] * len(values)
        
        # Create figure
        fig, ax = plt.subplots(figsize=(14, 7))
        
        # Create bars
        bars = ax.bar(range(len(values)), values, color=colors, edgecolor='#34495e', linewidth=0.5)
        
        # Customize chart
        ax.set_xlabel('Cluster Size (number of sequences)', fontsize=12, fontweight='bold')
        ax.set_ylabel('Number of Clusters', fontsize=12, fontweight='bold')
        ax.set_title(f'Cluster Size Distribution ({stats["num_clusters"]} total clusters)', 
                     fontsize=14, fontweight='bold', pad=20)
        
        # Set x-axis labels
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=45, ha='right')
        
        # Add grid for readability
        ax.grid(axis='y', alpha=0.3, linestyle='--')
        ax.set_axisbelow(True)
        
        # Add value labels on top of bars
        for bar in bars:
            height = bar.get_height()
            if height > 0:
                ax.text(bar.get_x() + bar.get_width()/2., height,
                       f'{int(height)}',
                       ha='center', va='bottom', fontsize=9)
        
        # Add statistics box
        stats_text = (
            f"Total Sequences: {stats['total_sequences']}\n"
            f"Total Clusters: {stats['num_clusters']}\n"
            f"Singletons: {stats['singletons']}\n"
            f"Largest Cluster: {stats['largest_cluster']} sequences\n"
            f"Average Cluster Size: {stats['avg_cluster_size']:.1f}"
        )
        
        ax.text(0.98, 0.97, stats_text,
               transform=ax.transAxes,
               fontsize=10,
               verticalalignment='top',
               horizontalalignment='right',
               bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
        
        plt.tight_layout()
        
        # Save if path provided
        if output_path:
            fig.savefig(output_path, dpi=150, bbox_inches='tight')
        
        return True, fig
        
    except ImportError:
        return False, "Matplotlib not installed. Please install it with: pip install matplotlib"
    except Exception as e:
        return False, f"Error creating chart: {str(e)}"


def create_text_summary(stats):
    """
    Create a text-based summary of clustering results.
    Fallback when matplotlib is not available.
    
    Args:
        stats: Statistics dictionary from parse_clustering_results
        
    Returns:
        str: Formatted text summary
    """
    lines = []
    lines.append("=" * 60)
    lines.append("CLUSTERING SUMMARY")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"Total Sequences:      {stats['total_sequences']:,}")
    lines.append(f"Total Clusters:       {stats['num_clusters']:,}")
    lines.append(f"Singletons:           {stats['singletons']:,} ({stats['singletons']/stats['num_clusters']*100:.1f}%)")
    lines.append(f"Largest Cluster:      {stats['largest_cluster']:,} sequences")
    lines.append(f"Average Cluster Size: {stats['avg_cluster_size']:.2f} sequences")
    lines.append("")
    lines.append("Cluster Size Distribution:")
    lines.append("-" * 60)
    lines.append(f"{'Size':<15} {'Count':<15} {'Percentage'}")
    lines.append("-" * 60)
    
    cluster_size_dist = stats['cluster_size_distribution']
    sorted_items = sorted(cluster_size_dist.items(), key=lambda x: x[1], reverse=True)[:20]
    
    for size, count in sorted_items:
        percentage = (count / stats['num_clusters']) * 100
        lines.append(f"{size:<15} {count:<15} {percentage:.1f}%")
    
    if len(cluster_size_dist) > 20:
        lines.append(f"... and {len(cluster_size_dist) - 20} more cluster sizes")
    
    lines.append("=" * 60)
    
    return "\n".join(lines)


def export_chart_html(stats, chart_image_path=None):
    """
    Generate an HTML representation of the clustering results.
    
    Args:
        stats: Statistics dictionary from parse_clustering_results
        chart_image_path: Optional path to chart image to embed
        
    Returns:
        str: HTML content
    """
    html = []
    html.append('<html><head><style>')
    html.append('body { font-family: Arial, sans-serif; padding: 20px; background-color: #f5f5f5; }')
    html.append('.header { background-color: #8e44ad; color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }')
    html.append('.header h1 { margin: 0; font-size: 24px; }')
    html.append('.stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 20px; }')
    html.append('.stat-box { background-color: white; padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }')
    html.append('.stat-value { font-size: 32px; font-weight: bold; color: #8e44ad; margin-bottom: 5px; }')
    html.append('.stat-label { font-size: 14px; color: #7f8c8d; }')
    html.append('.chart-container { background-color: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }')
    html.append('.chart-container img { width: 100%; height: auto; }')
    html.append('</style></head><body>')
    
    html.append('<div class="header">')
    html.append('<h1>⚡ MMseqs2 Clustering Results</h1>')
    html.append('</div>')
    
    html.append('<div class="stats-grid">')
    
    html.append('<div class="stat-box">')
    html.append(f'<div class="stat-value">{stats["total_sequences"]:,}</div>')
    html.append('<div class="stat-label">Total Sequences</div>')
    html.append('</div>')
    
    html.append('<div class="stat-box">')
    html.append(f'<div class="stat-value">{stats["num_clusters"]:,}</div>')
    html.append('<div class="stat-label">Clusters Formed</div>')
    html.append('</div>')
    
    html.append('<div class="stat-box">')
    html.append(f'<div class="stat-value">{stats["largest_cluster"]:,}</div>')
    html.append('<div class="stat-label">Largest Cluster</div>')
    html.append('</div>')
    
    html.append('<div class="stat-box">')
    html.append(f'<div class="stat-value">{stats["avg_cluster_size"]:.1f}</div>')
    html.append('<div class="stat-label">Avg Cluster Size</div>')
    html.append('</div>')
    
    html.append('<div class="stat-box">')
    html.append(f'<div class="stat-value">{stats["singletons"]:,}</div>')
    html.append('<div class="stat-label">Singletons</div>')
    html.append('</div>')
    
    html.append('</div>')
    
    if chart_image_path and os.path.exists(chart_image_path):
        html.append('<div class="chart-container">')
        html.append('<h2>Cluster Size Distribution</h2>')
        html.append(f'<img src="file:///{chart_image_path.replace(os.sep, "/")}" alt="Cluster Distribution Chart">')
        html.append('</div>')
    
    html.append('</body></html>')
    
    return ''.join(html)

