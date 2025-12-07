"""
Dialog for displaying a maximized view of a chart with zoom controls
"""
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QScrollArea
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap, QFont


class ChartMaximizeDialog(QDialog):
    """
    Dialog for displaying a chart in full size with zoom controls
    """
    
    def __init__(self, chart_pixmap: QPixmap, title: str = "Chart View", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.original_pixmap = chart_pixmap
        self.current_zoom = 1.0  # 100%
        self.min_zoom = 0.1  # 10%
        self.max_zoom = 5.0  # 500%
        self.zoom_step = 0.1  # 10% per step
        
        # Set dialog to be large but not fullscreen
        self.resize(1200, 800)
        
        self._init_ui()
    
    def _init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()
        
        # Header with title
        header_layout = QHBoxLayout()
        
        title_label = QLabel("Cluster Distribution Chart")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        
        close_button = QPushButton("✕ Close")
        close_button.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 5px 15px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        close_button.clicked.connect(self.accept)
        
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(close_button)
        
        # Zoom controls
        zoom_layout = QHBoxLayout()
        
        zoom_label = QLabel("Zoom:")
        zoom_label.setStyleSheet("font-weight: bold; color: #34495e;")
        
        self.zoom_out_button = QPushButton("−")
        self.zoom_out_button.setFixedSize(35, 35)
        self.zoom_out_button.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                color: white;
                border: none;
                border-radius: 3px;
                font-size: 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #7f8c8d;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
            }
        """)
        self.zoom_out_button.clicked.connect(self._zoom_out)
        
        self.zoom_level_label = QLabel("100%")
        self.zoom_level_label.setMinimumWidth(60)
        self.zoom_level_label.setAlignment(Qt.AlignCenter)
        self.zoom_level_label.setStyleSheet("""
            QLabel {
                background-color: #ecf0f1;
                border: 1px solid #bdc3c7;
                border-radius: 3px;
                padding: 5px;
                font-weight: bold;
                color: #2c3e50;
            }
        """)
        
        self.zoom_in_button = QPushButton("+")
        self.zoom_in_button.setFixedSize(35, 35)
        self.zoom_in_button.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                color: white;
                border: none;
                border-radius: 3px;
                font-size: 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #7f8c8d;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
            }
        """)
        self.zoom_in_button.clicked.connect(self._zoom_in)
        
        self.fit_button = QPushButton("Fit to Window")
        self.fit_button.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 5px 15px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        self.fit_button.clicked.connect(self._fit_to_window)
        
        self.reset_button = QPushButton("100%")
        self.reset_button.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 5px 15px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #7f8c8d;
            }
        """)
        self.reset_button.clicked.connect(self._reset_zoom)
        
        zoom_layout.addWidget(zoom_label)
        zoom_layout.addWidget(self.zoom_out_button)
        zoom_layout.addWidget(self.zoom_level_label)
        zoom_layout.addWidget(self.zoom_in_button)
        zoom_layout.addSpacing(20)
        zoom_layout.addWidget(self.fit_button)
        zoom_layout.addWidget(self.reset_button)
        zoom_layout.addStretch()
        
        # Chart display
        self.chart_label = QLabel()
        self.chart_label.setAlignment(Qt.AlignCenter)
        self.chart_label.setScaledContents(False)
        self._update_chart_display()
        
        # Scroll area for chart
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidget(self.chart_label)
        self.scroll_area.setWidgetResizable(False)  # Important for zoom to work
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                border: 2px solid #bdc3c7;
                border-radius: 5px;
                background-color: white;
            }
        """)
        
        # Install event filter for Ctrl+Scroll zoom
        self.scroll_area.viewport().installEventFilter(self)
        
        # Help text
        help_label = QLabel("💡 Tip: Use Ctrl+Scroll to zoom, or use the zoom buttons above")
        help_label.setStyleSheet("""
            QLabel {
                color: #7f8c8d;
                font-style: italic;
                padding: 5px;
            }
        """)
        
        # Close button at bottom
        bottom_button_layout = QHBoxLayout()
        bottom_close_button = QPushButton("Close")
        bottom_close_button.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 10px 30px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #7f8c8d;
            }
        """)
        bottom_close_button.clicked.connect(self.accept)
        
        bottom_button_layout.addStretch()
        bottom_button_layout.addWidget(bottom_close_button)
        
        # Add to layout
        layout.addLayout(header_layout)
        layout.addLayout(zoom_layout)
        layout.addWidget(self.scroll_area)
        layout.addWidget(help_label)
        layout.addLayout(bottom_button_layout)
        
        self.setLayout(layout)
    
    def eventFilter(self, obj, event):
        """Handle mouse wheel events for zooming with Ctrl"""
        if obj == self.scroll_area.viewport() and event.type() == event.Wheel:
            # Check if Ctrl is pressed
            if event.modifiers() == Qt.ControlModifier:
                # Zoom in or out based on wheel direction
                if event.angleDelta().y() > 0:
                    self._zoom_in()
                else:
                    self._zoom_out()
                return True  # Event handled
        
        return super().eventFilter(obj, event)
    
    def _update_chart_display(self):
        """Update the chart display with current zoom level"""
        scaled_pixmap = self.original_pixmap.scaled(
            self.original_pixmap.width() * self.current_zoom,
            self.original_pixmap.height() * self.current_zoom,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        self.chart_label.setPixmap(scaled_pixmap)
        self.chart_label.adjustSize()
        
        # Update zoom level label
        self.zoom_level_label.setText(f"{int(self.current_zoom * 100)}%")
        
        # Enable/disable zoom buttons
        self.zoom_out_button.setEnabled(self.current_zoom > self.min_zoom)
        self.zoom_in_button.setEnabled(self.current_zoom < self.max_zoom)
    
    def _zoom_in(self):
        """Zoom in by zoom_step"""
        new_zoom = min(self.current_zoom + self.zoom_step, self.max_zoom)
        if new_zoom != self.current_zoom:
            self.current_zoom = new_zoom
            self._update_chart_display()
    
    def _zoom_out(self):
        """Zoom out by zoom_step"""
        new_zoom = max(self.current_zoom - self.zoom_step, self.min_zoom)
        if new_zoom != self.current_zoom:
            self.current_zoom = new_zoom
            self._update_chart_display()
    
    def _reset_zoom(self):
        """Reset zoom to 100%"""
        self.current_zoom = 1.0
        self._update_chart_display()
    
    def _fit_to_window(self):
        """Fit chart to window size"""
        # Calculate zoom to fit width or height
        viewport_width = self.scroll_area.viewport().width() - 20  # Padding
        viewport_height = self.scroll_area.viewport().height() - 20
        
        width_ratio = viewport_width / self.original_pixmap.width()
        height_ratio = viewport_height / self.original_pixmap.height()
        
        # Use the smaller ratio to ensure it fits both dimensions
        fit_zoom = min(width_ratio, height_ratio)
        fit_zoom = max(self.min_zoom, min(fit_zoom, self.max_zoom))
        
        self.current_zoom = fit_zoom
        self._update_chart_display()

