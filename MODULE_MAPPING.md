# Module Mapping - Backup to Refactored Structure

This document shows exactly where each piece of code from `protein_gui_backup.py` has been moved.

## Source File: `protein_gui_backup.py` (1221 lines)

### Lines 1-11: Imports
**Moved to:** Each respective module
- Core imports → `core/blast_worker.py`, `core/mmseqs_runner.py`
- UI imports → `ui/*.py` files
- Main imports → `protein_gui.py`

---

### Lines 13-68: Database Definitions
```python
NCBI_DATABASES = { ... }
```
**Moved to:** `core/db_definitions.py` (lines 2-57)
**Status:** ✅ Identical

---

### Lines 70-93: Database Categories
```python
DATABASE_CATEGORIES = { ... }
```
**Moved to:** `core/db_definitions.py` (lines 60-82)
**Status:** ✅ Identical

---

### Lines 96-196: SearchableComboBox Class
```python
class SearchableComboBox(QComboBox):
    def __init__(self, parent=None): ...
    def addItemWithData(self, text, data=None): ...
    def setItems(self, items_dict): ...
    def filter_items(self, text): ...
    def getCurrentData(self): ...
```
**Moved to:** `ui/widgets/searchable_combobox.py` (lines 5-104)
**Status:** ✅ Identical

---

### Lines 197-313: BLASTWorker Class
```python
class BLASTWorker(QThread):
    def __init__(self, sequence, database, use_remote=True, local_db_path=""): ...
    def run(self): ...
    def parse_blast_xml(self, xml_file_path): ...
```
**Moved to:** `core/blast_worker.py` (lines 8-123)
**Status:** ✅ Identical
**Key Features:**
- Complete XML parsing
- Detailed alignment statistics
- Query/Match/Subject display
- Error handling

---

### Lines 315-463: MMseqsWorker Class
```python
class MMseqsWorker(QThread):
    def __init__(self, sequence, database_path, sensitivity="sensitive"): ...
    def run(self): ...
    def get_sensitivity_value(self): ...
    def format_results(self, results_file, stdout, stderr): ...
```
**Moved to:** `core/mmseqs_runner.py` (lines 7-154)
**Status:** ✅ Identical
**Key Features:**
- 4 sensitivity levels
- Temporary directory management
- Top 20 hits display
- Timeout handling (5 min)

---

### Lines 465-637: HomePage Class
```python
class HomePage(QWidget):
    service_selected = pyqtSignal(str)
    def __init__(self): ...
    def init_ui(self): ...
```
**Moved to:** `ui/home_page.py` (lines 6-177)
**Status:** ✅ Identical
**Key Features:**
- Welcome frame with title/subtitle
- BLAST service card (blue)
- MMseqs2 service card (purple)
- "More Tools Coming Soon" placeholder

---

### Lines 639-921: BLASTPage Class
```python
class BLASTPage(QWidget):
    back_requested = pyqtSignal()
    def __init__(self): ...
    def init_ui(self): ...
    def on_database_changed(self): ...
    def update_database_description(self): ...
    def on_database_source_changed(self): ...
    def browse_database_path(self): ...
    def run_blast(self): ...
    def on_blast_finished(self, results): ...
    def on_blast_error(self, error_msg): ...
```
**Moved to:** `ui/blast_page.py` (lines 9-295)
**Status:** ✅ Identical
**Key Features:**
- 50+ database dropdown
- Popular databases quick access
- Remote/Local toggle
- Database path browser
- Sequence validation

---

### Lines 923-1136: MMseqsPage Class
```python
class MMseqsPage(QWidget):
    back_requested = pyqtSignal()
    def __init__(self): ...
    def init_ui(self): ...
    def browse_database_path(self): ...
    def run_mmseqs(self): ...
    def on_mmseqs_finished(self, results): ...
    def on_mmseqs_error(self, error_msg): ...
```
**Moved to:** `ui/mmseqs_page.py` (lines 9-241)
**Status:** ✅ Identical
**Key Features:**
- Sensitivity dropdown
- Database path selection
- FASTA file detection
- Helpful error messages

---

### Lines 1138-1207: ProteinGUI Main Class
```python
class ProteinGUI(QMainWindow):
    def __init__(self): ...
    def show_home_page(self): ...
    def show_service_page(self, service): ...
```
**Moved to:** `protein_gui.py` (lines 9-77)
**Status:** ✅ Identical
**Key Features:**
- Stacked widget management
- Signal connections
- Window title updates

---

### Lines 1208-1221: Main Function
```python
def main():
    try:
        app = QApplication(sys.argv)
        window = ProteinGUI()
        window.show()
        sys.exit(app.exec_())
    except Exception as e:
        print(f"Error occurred: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
```
**Moved to:** `protein_gui.py` (lines 79-92)
**Status:** ✅ Identical

---

## Import Paths

### In Refactored Code:
```python
# protein_gui.py
from ui.home_page import HomePage
from ui.blast_page import BLASTPage
from ui.mmseqs_page import MMseqsPage

# ui/blast_page.py
from core.db_definitions import NCBI_DATABASES
from core.blast_worker import BLASTWorker

# ui/mmseqs_page.py
from core.mmseqs_runner import MMseqsWorker
```

---

## Summary

| Component | Original Lines | New File | New Lines | Status |
|-----------|---------------|----------|-----------|--------|
| Imports | 1-11 | Various | - | ✅ Distributed |
| NCBI_DATABASES | 13-68 | core/db_definitions.py | 2-57 | ✅ Identical |
| DATABASE_CATEGORIES | 70-93 | core/db_definitions.py | 60-82 | ✅ Identical |
| SearchableComboBox | 96-196 | ui/widgets/searchable_combobox.py | 5-104 | ✅ Identical |
| BLASTWorker | 197-313 | core/blast_worker.py | 8-123 | ✅ Identical |
| MMseqsWorker | 315-463 | core/mmseqs_runner.py | 7-154 | ✅ Identical |
| HomePage | 465-637 | ui/home_page.py | 6-177 | ✅ Identical |
| BLASTPage | 639-921 | ui/blast_page.py | 9-295 | ✅ Identical |
| MMseqsPage | 923-1136 | ui/mmseqs_page.py | 9-241 | ✅ Identical |
| ProteinGUI | 1138-1207 | protein_gui.py | 9-77 | ✅ Identical |
| main() | 1208-1221 | protein_gui.py | 79-92 | ✅ Identical |

**Total Lines:**
- Original: 1221 lines (single file)
- Refactored: ~1272 lines (8 modules with better organization)

**Code Increase:** Slight increase due to:
- Module-level docstrings
- Cleaner import statements
- Better spacing and organization

**Functionality:** 100% preserved ✅

