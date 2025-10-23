from PyQt5.QtWidgets import QComboBox, QCompleter
from PyQt5.QtCore import Qt, QStringListModel


class SearchableComboBox(QComboBox):
    """QComboBox with live filtering."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.all_items = []
        self.completer = QCompleter(self)
        self.completer.setCompletionMode(QCompleter.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.setCompleter(self.completer)
        self.lineEdit().textChanged.connect(self.filter_items)

    def setItems(self, items):
        self.all_items = list(items)
        self.clear()
        self.addItems(self.all_items)
        self.completer.setModel(QStringListModel(self.all_items))

    def filter_items(self, text):
        self.clear()
        for item in self.all_items:
            if text.lower() in item.lower():
                self.addItem(item)
