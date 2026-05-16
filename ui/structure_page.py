"""Standalone structural mapping: PDB/mmCIF + pySCA-derived or manual sectors."""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QFileDialog,
    QButtonGroup,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from core.pysca_io import load_pysca_db, PySCAData
from core.pysca_sector_model import (
    default_sec_groups,
    format_sec_groups_display,
    merge_ics_to_sectors,
    validate_sec_groups,
    parse_sec_groups_literal,
)
from core.structure_fetch import PdbFetchWorker
from core.structure_mapping import (
    map_pdb_residue_lists_to_colors,
    map_sector_position_lists_to_pdb,
    map_sector_positions_to_pdb,
)
from ui.widgets.structure_viewer_widget import StructureViewerWidget


class StructureMappingPage(QWidget):
    """Colour a structure offline; sectors from a `.db`, or manual tuples."""

    send_to_alignment_pysca = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._data: Optional[PySCAData] = None
        self._db_path: Optional[str] = None
        self._sec_groups: List[List[int]] = []
        self._merged = []
        self._structure_plain: Optional[str] = None
        self._structure_fmt: str = "pdb"
        self._pdb_fetch_worker: Optional[PdbFetchWorker] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        head = QLabel(
            "Colour a 3D structure by sectors (offline 3Dmol); fetch coordinates from "
            "RCSB or open a local PDB/mmCIF."
        )
        head.setWordWrap(True)
        head.setProperty("class", "muted")
        root.addWidget(head)

        mode_grp = QGroupBox("Sector source")
        mv = QVBoxLayout()
        self._rb_sectors_from_db = QRadioButton(
            "From pySCA .db (sector groups → merged ICs)"
        )
        self._rb_sectors_manual = QRadioButton(
            "Manual tuples (notebook-style lists per sector)"
        )
        self._rb_sectors_from_db.setChecked(True)
        self._sector_source_group = QButtonGroup(self)
        self._sector_source_group.addButton(self._rb_sectors_from_db)
        self._sector_source_group.addButton(self._rb_sectors_manual)
        mv.addWidget(self._rb_sectors_from_db)
        mv.addWidget(self._rb_sectors_manual)
        mh = QHBoxLayout()
        mh.addWidget(QLabel("Manual interpretation:"))
        self._manual_interp = QComboBox()
        self._manual_interp.addItems(
            (
                "Alignment columns → PDB (needs .db for ats)",
                "PDB residue numbers (same chain)",
            ),
        )
        mh.addWidget(self._manual_interp)
        mh.addStretch()
        mv.addLayout(mh)
        hint = QLabel(
            "For manual PDB numbers, tuples are residue lists only, "
            'e.g. `([12,13], [41,52])`; alignment mode uses mapping via `ats` from a loaded .db.'
        )
        hint.setProperty("class", "muted")
        hint.setWordWrap(True)
        mv.addWidget(hint)
        mode_grp.setLayout(mv)
        root.addWidget(mode_grp)

        db_grp = QGroupBox("pySCA .db (required for Alignment-column manual mode)")
        dvl = QVBoxLayout()
        btn_row = QHBoxLayout()
        self._load_db_btn = QPushButton("Load pySCA .db…")
        self._load_db_btn.clicked.connect(self._browse_db)
        btn_row.addWidget(self._load_db_btn)
        self._to_alignment_btn = QPushButton("Send to pySCA results…")
        self._to_alignment_btn.clicked.connect(self._emit_send_to_alignment)
        self._to_alignment_btn.setEnabled(False)
        btn_row.addWidget(self._to_alignment_btn)
        btn_row.addStretch()
        dvl.addLayout(btn_row)
        self._db_status = QLabel("No database loaded.")
        self._db_status.setProperty("class", "muted")
        self._db_status.setWordWrap(True)
        dvl.addWidget(self._db_status)
        db_grp.setLayout(dvl)
        root.addWidget(db_grp)

        sec_grp = QGroupBox("Sector groups / manual tuples")
        svg = QVBoxLayout()
        self._sector_text = QPlainTextEdit()
        self._sector_text.setPlaceholderText("([0], [1], [2], …)")
        self._sector_text.setProperty("class", "mono")
        self._sector_text.setMaximumHeight(100)
        self._sector_text.setEnabled(False)
        svg.addWidget(self._sector_text)
        ar = QHBoxLayout()
        self._apply_db_sectors_btn = QPushButton("Apply sector groups (.db)")
        self._apply_db_sectors_btn.clicked.connect(self._apply_db_sectors)
        self._apply_db_sectors_btn.setEnabled(False)
        ar.addWidget(self._apply_db_sectors_btn)
        self._reset_sectors_btn = QPushButton("Reset to default IC groups")
        self._reset_sectors_btn.clicked.connect(self._reset_db_sectors)
        self._reset_sectors_btn.setEnabled(False)
        ar.addWidget(self._reset_sectors_btn)
        self._apply_manual_btn = QPushButton("Apply manual tuples")
        self._apply_manual_btn.clicked.connect(self._apply_manual_sectors)
        self._apply_manual_btn.hide()
        ar.addWidget(self._apply_manual_btn)
        ar.addStretch()
        svg.addLayout(ar)
        sec_grp.setLayout(svg)
        root.addWidget(sec_grp)

        st_grp = QGroupBox("Structure")
        sg = QVBoxLayout()
        r1 = QHBoxLayout()
        r1.addWidget(QLabel("PDB id"))
        self._pdb_id = QLineEdit()
        self._pdb_id.setPlaceholderText("e.g. 1CRN")
        self._pdb_id.setMaximumWidth(130)
        r1.addWidget(self._pdb_id)
        r1.addWidget(QLabel("Chain"))
        self._chain = QLineEdit()
        self._chain.setPlaceholderText("A")
        self._chain.setMaximumWidth(56)
        r1.addWidget(self._chain)
        self._fetch_btn = QPushButton("Fetch from RCSB")
        self._fetch_btn.clicked.connect(self._fetch_rcsb)
        r1.addWidget(self._fetch_btn)
        self._open_struct_btn = QPushButton("Open file…")
        self._open_struct_btn.clicked.connect(self._browse_structure)
        r1.addWidget(self._open_struct_btn)
        r1.addStretch()
        sg.addLayout(r1)
        self._struct_status = QLabel(
            "Load sectors, fetch or open structure, then apply colouring."
        )
        self._struct_status.setWordWrap(True)
        self._struct_status.setProperty("class", "muted")
        sg.addWidget(self._struct_status)
        st_grp.setLayout(sg)
        root.addWidget(st_grp)

        self._viewer = StructureViewerWidget()
        root.addWidget(self._viewer, 1)

        self._rb_sectors_from_db.toggled.connect(self._on_sector_source_changed)
        self._on_sector_source_changed()

    def shutdown_workers(self) -> None:
        w = self._pdb_fetch_worker
        if w is None:
            return
        if w.isRunning():
            w.cancel()
            w.wait(300_000)
        self._pdb_fetch_worker = None

    def _on_sector_source_changed(self, _checked=False) -> None:
        manual = self._rb_sectors_manual.isChecked()
        self._manual_interp.setVisible(manual)
        self._apply_db_sectors_btn.setVisible(not manual)
        self._reset_sectors_btn.setVisible(not manual)
        self._apply_manual_btn.setVisible(manual)
        if manual:
            self._sector_text.setPlaceholderText(
                "([10, 11], [22])  alignment columns OR PDB residue lists (see dropdown)"
            )
            self._sector_text.setEnabled(True)
        elif self._data is not None:
            self._sector_text.setPlaceholderText("([0], [1], [2], …)")
            self._sector_text.setEnabled(True)
        else:
            self._sector_text.clear()
            self._sector_text.setEnabled(False)

    def _browse_db(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open pySCA database", "", "Pickle (*.db);;All (*.*)"
        )
        if not path:
            return
        try:
            self._data = load_pysca_db(path)
        except Exception as exc:
            QMessageBox.warning(self, "pySCA", f"Could not load:\n{exc}")
            return
        self._db_path = path
        n_ic = len(self._data.Dsect.get("ics") or [])
        self._sec_groups = default_sec_groups(n_ic)
        self._sector_text.setPlainText(format_sec_groups_display(self._sec_groups))
        if self._rb_sectors_from_db.isChecked():
            self._sector_text.setEnabled(True)
        self._apply_db_sectors_btn.setEnabled(True)
        self._reset_sectors_btn.setEnabled(True)
        self._to_alignment_btn.setEnabled(True)
        self._db_status.setText(f"{n_ic} ICs  |  {os.path.basename(path)}")
        if self._rb_sectors_from_db.isChecked():
            self._apply_db_sectors()

    def _apply_db_sectors(self) -> None:
        if self._data is None:
            QMessageBox.warning(self, "pySCA", "Load a .db file first.")
            return
        try:
            self._sec_groups = parse_sec_groups_literal(self._sector_text.toPlainText())
        except ValueError as e:
            QMessageBox.warning(self, "Sectors", str(e))
            return
        n_ic = len(self._data.Dsect.get("ics") or [])
        err = validate_sec_groups(n_ic, self._sec_groups)
        if err:
            QMessageBox.warning(self, "Sectors", err)
            return
        self._merged, _ = merge_ics_to_sectors(self._data.Dsect, self._sec_groups)
        self._struct_status.setText(
            "Sector merge updated (.db mode); refresh colouring if structure is loaded."
        )
        self._repaint_structure()

    def _reset_db_sectors(self) -> None:
        if self._data is None:
            return
        n_ic = len(self._data.Dsect.get("ics") or [])
        self._sec_groups = default_sec_groups(n_ic)
        self._sector_text.setPlainText(format_sec_groups_display(self._sec_groups))
        self._apply_db_sectors()

    def _apply_manual_sectors(self) -> None:
        plain = self._sector_text.toPlainText().strip()
        if not plain:
            QMessageBox.information(self, "Sectors", "Enter manual tuples first.")
            return
        idx = self._manual_interp.currentIndex()
        try:
            _ = parse_sec_groups_literal(plain)
        except ValueError as e:
            QMessageBox.warning(self, "Sectors", str(e))
            return
        if idx == 0:
            if self._data is None:
                QMessageBox.warning(
                    self,
                    ".db required",
                    "Alignment-column colouring needs `ats`; load a pySCA .db first.",
                )
                return
            ds = self._data.Dseq
            ats = ds.get("ats") if isinstance(ds, dict) else None
            if not ats:
                QMessageBox.warning(self, ".db incomplete", "`ats` missing in database.")
                return
        self._repaint_structure()
        self._struct_status.setText("Applied manual tuples; updated residue colours.")

    def _db_mode_residue_colors(self):
        if self._data is None or not self._merged:
            return []
        ds = self._data.Dseq
        ats = ds.get("ats") if isinstance(ds, dict) else None
        return map_sector_positions_to_pdb(
            self._merged, ats, self._chain.text().strip() or "A",
        )

    def _manual_residue_colors(self):
        plain = self._sector_text.toPlainText().strip()
        if not plain:
            return []
        try:
            groups = parse_sec_groups_literal(plain)
        except ValueError:
            return []
        ch = self._chain.text().strip() or "A"
        if self._manual_interp.currentIndex() == 1:
            return map_pdb_residue_lists_to_colors(groups, ch)
        if self._data is None:
            return []
        ats = self._data.Dseq.get("ats") if isinstance(self._data.Dseq, dict) else None
        return map_sector_position_lists_to_pdb(groups, ats, ch)

    def _effective_residue_colors(self):
        if self._rb_sectors_from_db.isChecked():
            return self._db_mode_residue_colors()
        return self._manual_residue_colors()

    def _repaint_structure(self) -> None:
        if self._structure_plain is None:
            return
        cols = self._effective_residue_colors()
        ch = self._chain.text().strip() or "A"
        self._viewer.set_structure(self._structure_plain, self._structure_fmt, ch)
        self._viewer.set_residue_colors(cols)
        self._struct_status.setText(
            f"{self._structure_fmt.upper()} view; chain {ch}; "
            f"{len(cols)} residue colour mapping(s)."
        )

    def _fetch_rcsb(self) -> None:
        self.shutdown_workers()
        pid = self._pdb_id.text().strip()
        self._struct_status.setText("Downloading…")
        self._fetch_btn.setEnabled(False)
        self._pdb_fetch_worker = PdbFetchWorker(pid, parent=self)
        self._pdb_fetch_worker.progress.connect(self._struct_status.setText)
        self._pdb_fetch_worker.finished.connect(self._on_fetch_done)
        self._pdb_fetch_worker.error.connect(self._on_fetch_error)
        self._pdb_fetch_worker.start()

    def _on_fetch_done(self, path: str, fmt: str) -> None:
        self._pdb_fetch_worker = None
        self._fetch_btn.setEnabled(True)
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            self._struct_status.setText(str(e))
            return
        self._structure_plain = text
        self._structure_fmt = fmt
        self._repaint_structure()

    def _on_fetch_error(self, msg: str) -> None:
        self._pdb_fetch_worker = None
        self._fetch_btn.setEnabled(True)
        self._struct_status.setText(msg)
        QMessageBox.warning(self, "Structure", msg)

    def _browse_structure(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open structure",
            "",
            "Structure (*.pdb *.cif *.mmcif);;All (*.*)",
        )
        if not path:
            return
        low = path.lower()
        fmt = "cif" if low.endswith(".cif") or low.endswith(".mmcif") else "pdb"
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            QMessageBox.warning(self, "Structure", str(e))
            return
        self._structure_plain = text
        self._structure_fmt = fmt
        self._repaint_structure()

    def _emit_send_to_alignment(self) -> None:
        if not self._db_path or not os.path.isfile(self._db_path):
            QMessageBox.information(self, "pySCA", "Load a .db file first.")
            return
        self.send_to_alignment_pysca.emit(self._db_path)
