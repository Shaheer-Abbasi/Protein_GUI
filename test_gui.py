#!/usr/bin/env python3
"""
Simple PyQt5 test to diagnose GUI issues
"""
import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel, QVBoxLayout, QWidget
from PyQt5.QtCore import Qt

class TestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyQt5 Test Window")
        self.setGeometry(100, 100, 400, 200)
        
        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Create layout
        layout = QVBoxLayout(central_widget)
        
        # Add a simple label
        label = QLabel("If you can see this, PyQt5 is working!")
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("font-size: 16px; padding: 20px;")
        
        layout.addWidget(label)

def main():
    print("Starting PyQt5 test application...")
    
    try:
        app = QApplication(sys.argv)
        print("QApplication created successfully")
        
        window = TestWindow()
        print("Test window created successfully")
        
        window.show()
        print("Window.show() called successfully")
        
        print("Starting event loop...")
        sys.exit(app.exec_())
        
    except Exception as e:
        print(f"Error occurred: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()