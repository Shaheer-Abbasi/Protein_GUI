"""MSAViewer widget - Safe QWebEngineView wrapper for displaying sequence alignments"""
import os
import base64

# Try to import QWebEngineView, provide fallback if not available
try:
    from PyQt5.QtWebEngineWidgets import QWebEngineView
    from PyQt5.QtWebChannel import QWebChannel
    HAS_WEBENGINE = True
except ImportError:
    HAS_WEBENGINE = False
    QWebEngineView = None

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
from PyQt5.QtCore import Qt, QUrl, pyqtSignal
from PyQt5.QtGui import QFont


class MSAViewerWidget(QWidget):
    """
    Widget for displaying multiple sequence alignments using MSAViewer.
    
    Uses QWebEngineView to embed the BioJS MSAViewer component.
    Falls back to a message if PyQtWebEngine is not installed.
    """
    
    # Signal emitted when viewer is ready
    viewer_ready = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.alignment_data = None
        self._setup_ui()
    
    def _setup_ui(self):
        """Set up the widget UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        if HAS_WEBENGINE:
            self._setup_webengine(layout)
        else:
            self._setup_fallback(layout)
    
    def _setup_webengine(self, layout):
        """Set up QWebEngineView for MSAViewer"""
        self.web_view = QWebEngineView()
        self.web_view.setMinimumHeight(300)
        
        # Enable JavaScript
        settings = self.web_view.settings()
        from PyQt5.QtWebEngineWidgets import QWebEngineSettings
        settings.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
        
        layout.addWidget(self.web_view)
        
        # Load empty viewer initially
        self._load_empty_viewer()
    
    def _setup_fallback(self, layout):
        """Set up fallback UI when QWebEngineView is not available"""
        self.web_view = None
        
        fallback_widget = QWidget()
        fallback_layout = QVBoxLayout(fallback_widget)
        fallback_layout.setAlignment(Qt.AlignCenter)
        
        icon_label = QLabel("⚠️")
        icon_label.setStyleSheet("font-size: 48px;")
        icon_label.setAlignment(Qt.AlignCenter)
        
        title_label = QLabel("PyQtWebEngine Not Installed")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        
        msg_label = QLabel(
            "The alignment viewer requires PyQtWebEngine.\n\n"
            "To install it, run:\n"
            "pip install PyQtWebEngine\n\n"
            "You can still run alignments and export results."
        )
        msg_label.setAlignment(Qt.AlignCenter)
        msg_label.setStyleSheet("color: #7f8c8d;")
        
        fallback_layout.addWidget(icon_label)
        fallback_layout.addWidget(title_label)
        fallback_layout.addWidget(msg_label)
        
        fallback_widget.setStyleSheet("""
            QWidget {
                background-color: #f8f9fa;
                border: 2px dashed #dee2e6;
                border-radius: 10px;
            }
        """)
        
        layout.addWidget(fallback_widget)
    
    def _get_project_root(self):
        """Get the project root directory"""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.dirname(os.path.dirname(script_dir))
    
    def _get_msa_js_path(self):
        """Get the path to the bundled MSAViewer JS file"""
        project_root = self._get_project_root()
        local_path = os.path.join(project_root, 'resources', 'msa', 'msa.min.js')
        
        if os.path.exists(local_path):
            # Return relative path - will be resolved with base URL
            return "resources/msa/msa.min.js"
        else:
            # Fall back to CDN - use jsdelivr which serves uncompressed content
            return "https://cdn.jsdelivr.net/npm/msa@1.0.3/dist/msa.js"
    
    def _get_base_url(self):
        """Get the base URL for loading local resources"""
        project_root = self._get_project_root()
        return QUrl.fromLocalFile(project_root + '/')
    
    def _load_empty_viewer(self):
        """Load an empty MSAViewer"""
        if not self.web_view:
            return
        
        html = self._generate_html("")
        # Set base URL so local file:// resources can be loaded
        self.web_view.setHtml(html, self._get_base_url())
    
    def _generate_html(self, fasta_b64):
        """
        Generate HTML with MSAViewer.
        
        Uses base64 encoding for safe data transfer (prevents XSS).
        """
        msa_js_url = self._get_msa_js_path()
        
        html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <script src="{msa_js_url}"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background-color: #ffffff;
            overflow: hidden;
        }}
        #msa-container {{
            width: 100%;
            height: 100vh;
        }}
        .empty-state {{
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100vh;
            color: #7f8c8d;
            text-align: center;
        }}
        .empty-state h2 {{
            margin-bottom: 10px;
            color: #34495e;
        }}
        .loading {{
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100vh;
        }}
        .spinner {{
            width: 40px;
            height: 40px;
            border: 4px solid #f3f3f3;
            border-top: 4px solid #3498db;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }}
        @keyframes spin {{
            0% {{ transform: rotate(0deg); }}
            100% {{ transform: rotate(360deg); }}
        }}
    </style>
</head>
<body>
    <div id="msa-container">
        <div class="loading" id="loading-state">
            <div class="spinner"></div>
            <p style="margin-top: 15px; color: #7f8c8d;">Loading alignment viewer...</p>
        </div>
        <div class="empty-state" id="empty-state" style="display: none;">
            <h2>🧬 Alignment Viewer</h2>
            <p>Run an alignment to visualize the results here.</p>
        </div>
    </div>
    
    <script>
        var msaInstance = null;
        var fastaB64 = "{fasta_b64}";
        
        function decodeBase64(str) {{
            try {{
                return decodeURIComponent(atob(str).split('').map(function(c) {{
                    return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
                }}).join(''));
            }} catch (e) {{
                return atob(str);
            }}
        }}
        
        function initMSA() {{
            document.getElementById('loading-state').style.display = 'none';
            
            if (!fastaB64 || fastaB64 === "") {{
                document.getElementById('empty-state').style.display = 'flex';
                return;
            }}
            
            try {{
                var fastaContent = decodeBase64(fastaB64);
                var seqs = msa.io.fasta.parse(fastaContent);
                
                if (seqs.length === 0) {{
                    document.getElementById('empty-state').style.display = 'flex';
                    return;
                }}
                
                // Clear container
                document.getElementById('msa-container').innerHTML = '';
                
                // Create MSAViewer with options
                msaInstance = msa({{
                    el: document.getElementById('msa-container'),
                    seqs: seqs,
                    vis: {{
                        conserv: true,
                        overviewbox: true,
                        seqlogo: true,
                        metacell: true
                    }},
                    conf: {{
                        dropImport: false
                    }},
                    zoomer: {{
                        labelWidth: 150,
                        labelFontsize: 12,
                        labelIdLength: 30
                    }},
                    colorscheme: {{
                        scheme: "clustal"
                    }}
                }});
                
                msaInstance.render();
                
            }} catch (e) {{
                console.error('Error loading alignment:', e);
                document.getElementById('msa-container').innerHTML = 
                    '<div class="empty-state"><h2>Error Loading Alignment</h2><p>' + e.message + '</p></div>';
            }}
        }}
        
        // Initialize when DOM is ready
        if (document.readyState === 'loading') {{
            document.addEventListener('DOMContentLoaded', initMSA);
        }} else {{
            // Give MSAViewer script time to load
            setTimeout(initMSA, 100);
        }}
    </script>
</body>
</html>'''
        return html
    
    def load_alignment(self, fasta_content):
        """
        Load an alignment into the viewer.
        
        Args:
            fasta_content: FASTA format string containing aligned sequences
        """
        if not self.web_view:
            return False
        
        if not fasta_content or not fasta_content.strip():
            self._load_empty_viewer()
            return False
        
        self.alignment_data = fasta_content
        
        # Base64 encode the FASTA content for safe transfer
        try:
            fasta_b64 = base64.b64encode(fasta_content.encode('utf-8')).decode('ascii')
        except Exception as e:
            print(f"Error encoding FASTA: {e}")
            return False
        
        # Generate and load HTML with base URL for local resources
        html = self._generate_html(fasta_b64)
        self.web_view.setHtml(html, self._get_base_url())
        
        return True
    
    def load_alignment_file(self, filepath):
        """
        Load an alignment from a file.
        
        Args:
            filepath: Path to FASTA or Clustal format alignment file
        """
        if not os.path.exists(filepath):
            return False
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # If it's Clustal format, we need to convert to FASTA
            if content.startswith('CLUSTAL') or content.startswith('MUSCLE'):
                content = self._clustal_to_fasta(content)
            
            return self.load_alignment(content)
            
        except Exception as e:
            print(f"Error loading alignment file: {e}")
            return False
    
    def _clustal_to_fasta(self, clustal_content):
        """Convert Clustal format to FASTA format"""
        sequences = {}
        
        lines = clustal_content.strip().split('\n')
        
        for line in lines:
            # Skip empty lines, header, and conservation lines
            if not line.strip():
                continue
            if line.startswith('CLUSTAL') or line.startswith('MUSCLE'):
                continue
            if line.strip().startswith('*') or line.strip().startswith(':') or line.strip().startswith('.'):
                continue
            if all(c in ' *:.' for c in line.strip()):
                continue
            
            parts = line.split()
            if len(parts) >= 2:
                name = parts[0]
                seq = parts[1]
                
                if name not in sequences:
                    sequences[name] = []
                sequences[name].append(seq)
        
        # Build FASTA
        fasta_lines = []
        for name, seq_parts in sequences.items():
            fasta_lines.append(f">{name}")
            fasta_lines.append(''.join(seq_parts))
        
        return '\n'.join(fasta_lines)
    
    def clear(self):
        """Clear the current alignment"""
        self.alignment_data = None
        self._load_empty_viewer()
    
    def get_alignment_data(self):
        """Get the current alignment data"""
        return self.alignment_data
    
    def is_available(self):
        """Check if the viewer is available (PyQtWebEngine installed)"""
        return HAS_WEBENGINE


def check_webengine_available():
    """Check if PyQtWebEngine is available"""
    return HAS_WEBENGINE

