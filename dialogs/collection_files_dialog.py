#!/usr/bin/env python3
"""Dialog for managing Random Fill collection files.

Replaces the old inline Collection Files table in RandomFillDialog so the
main dialog stays compact (same pattern as MarathonScheduleDialog).
"""

from __future__ import annotations
from pathlib import Path
from typing import List, Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QTableWidget, QHeaderView, QPushButton, QFileDialog,
)

from .widgets.dark_theme import DARK_TABLE_STYLESHEET


class CollectionFilesDialog(QDialog):
    """Table editor: each row = one collection JSON path."""

    def __init__(self, parent=None, paths: Optional[List[str]] = None):
        super().__init__(parent)
        self.setWindowTitle("Collection Files")
        self.setModal(True)
        self.resize(620, 380)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Each row = one collection JSON file. "
            "The first file is the primary collection."
        ))

        self.table = QTableWidget(0, 3)
        self.table.setStyleSheet(DARK_TABLE_STYLESHEET)
        self.table.setHorizontalHeaderLabels(["Path", "", ""])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.table.setColumnWidth(1, 80)
        self.table.setColumnWidth(2, 80)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add Collection")
        add_btn.clicked.connect(lambda: self._add_row())
        btn_row.addWidget(add_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        ok_row = QHBoxLayout()
        ok_row.addStretch()
        save_btn = QPushButton("OK")
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        ok_row.addWidget(save_btn)
        ok_row.addWidget(cancel_btn)
        layout.addLayout(ok_row)

        for p in (paths or []):
            if p:
                self._add_row(p)
        if self.table.rowCount() == 0:
            self._add_row()

    def _add_row(self, path: str = ""):
        row = self.table.rowCount()
        self.table.insertRow(row)

        path_widget = QLineEdit(path)
        path_widget.setReadOnly(True)
        path_widget.setPlaceholderText("Select collection JSON...")
        self.table.setCellWidget(row, 0, path_widget)

        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(lambda _=False, r=row: self._browse_row(r))
        self.table.setCellWidget(row, 1, browse_btn)

        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(lambda _=False, r=row: self._remove_row(r))
        self.table.setCellWidget(row, 2, remove_btn)

    def _browse_row(self, row: int):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Collection File", "",
            "JSON Files (*.json);;All Files (*)"
        )
        if file_path:
            path_widget = self.table.cellWidget(row, 0)
            if path_widget:
                path_widget.setText(file_path)

    def _remove_row(self, row: int):
        self.table.removeRow(row)
        # Reconnect buttons (row indices shifted).
        for r in range(self.table.rowCount()):
            browse_btn = self.table.cellWidget(r, 1)
            if isinstance(browse_btn, QPushButton):
                try:
                    browse_btn.clicked.disconnect()
                except Exception:
                    pass
                browse_btn.clicked.connect(lambda _=False, rr=r: self._browse_row(rr))
            remove_btn = self.table.cellWidget(r, 2)
            if isinstance(remove_btn, QPushButton):
                try:
                    remove_btn.clicked.disconnect()
                except Exception:
                    pass
                remove_btn.clicked.connect(lambda _=False, rr=r: self._remove_row(rr))

    def get_paths(self) -> List[str]:
        result = []
        for row in range(self.table.rowCount()):
            w = self.table.cellWidget(row, 0)
            if w and w.text():
                result.append(w.text())
        # De-duplicate while preserving order.
        seen = set()
        deduped = []
        for p in result:
            if p not in seen:
                seen.add(p)
                deduped.append(p)
        return deduped
