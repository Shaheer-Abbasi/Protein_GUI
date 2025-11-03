from PyQt5.QtWidgets import QComboBox, QCompleter
from PyQt5.QtCore import Qt, QStringListModel


class SearchableComboBox(QComboBox):
    """A combobox with search/filter functionality"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        print("Creating SearchableComboBox...")
        
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        
        # Store all items for filtering
        self.all_items = []
        self.all_data = {}
        self._initializing = True
        
        # Create completer for auto-completion
        self.completer = QCompleter(self)
        self.completer.setCompletionMode(QCompleter.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.setCompleter(self.completer)
        
        print("SearchableComboBox created successfully")
    
    def addItemWithData(self, text, data=None):
        """Add item with optional data"""
        try:
            self.all_items.append(text)
            if data:
                self.all_data[text] = data
            super().addItem(text)
        except Exception as e:
            print(f"Error adding item {text}: {e}")
    
    def setItems(self, items_dict):
        """Set items from dictionary {text: data}"""
        print(f"Setting {len(items_dict)} database items...")
        
        try:
            # Temporarily block signals during initialization
            self.blockSignals(True)
            
            self.clear()
            self.all_items.clear()
            self.all_data.clear()
            
            # Add items more safely
            for i, (text, data) in enumerate(items_dict.items()):
                if i % 10 == 0:  # Progress indicator
                    print(f"  Adding item {i+1}/{len(items_dict)}: {text}")
                
                self.all_items.append(text)
                self.all_data[text] = data
                super().addItem(text)
            
            print("Database items added successfully")
            
            # Update completer
            self.completer.setModel(QStringListModel(self.all_items))
            print("Completer model updated")
            
            # Re-enable signals and connect filtering
            self.blockSignals(False)
            self._initializing = False
            
            # Connect signals for filtering after initialization
            self.lineEdit().textChanged.connect(self.filter_items)
            print("Signals connected")
            
        except Exception as e:
            print(f"Error in setItems: {e}")
            import traceback
            traceback.print_exc()
    
    def filter_items(self, text):
        """Filter items based on text input"""
        # Skip filtering during initialization
        if getattr(self, '_initializing', False):
            return
            
        try:
            if not text:
                # Show all items if no filter text
                self.clear()
                for item in self.all_items:
                    super().addItem(item)
            else:
                # Filter items that contain the text (case-insensitive)
                self.clear()
                filtered_items = [item for item in self.all_items 
                                if text.lower() in item.lower() or 
                                   text.lower() in self.all_data.get(item, '').lower()]
                for item in filtered_items:
                    super().addItem(item)
        except Exception as e:
            print(f"Error in filter_items: {e}")
    
    def getCurrentData(self):
        """Get data for currently selected item"""
        current_text = self.currentText()
        return self.all_data.get(current_text, current_text)
