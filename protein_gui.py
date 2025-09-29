import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QTextEdit, QPushButton, QLabel

class ProteinGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sen Protein Sequence Tool")
        self.setGeometry(100, 100, 600, 400)
        
        # Create central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Create widgets
        self.input_label = QLabel("Enter protein sequence:")
        self.input_text = QTextEdit()
        self.input_text.setPlaceholderText("Paste your amino acid sequence here...")
        self.input_text.setMaximumHeight(100)
        
        self.process_button = QPushButton("Process Sequence")
        self.process_button.clicked.connect(self.process_sequence)
        
        self.output_label = QLabel("Results:")
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        
        # Add widgets to layout
        layout.addWidget(self.input_label)
        layout.addWidget(self.input_text)
        layout.addWidget(self.process_button)
        layout.addWidget(self.output_label)
        layout.addWidget(self.output_text)
    
    def process_sequence(self):
        """Process the input sequence (for now, just echo it back)"""
        input_sequence = self.input_text.toPlainText().strip()
        
        if input_sequence:
            # For now, just echo back with some basic info
            result = f"Input sequence received:\n"
            result += f"Length: {len(input_sequence)} characters\n"
            result += f"Sequence: {input_sequence}\n\n"
            result += "Next step: This will be replaced with BLASTP results!"
            
            self.output_text.setText(result)
        else:
            self.output_text.setText("Please enter a protein sequence first.")

def main():
    app = QApplication(sys.argv)
    window = ProteinGUI()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()