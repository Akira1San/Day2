#!/usr/bin/env python3
"""Dialog for editing marathon schedules (per-day / rotating collection tags)."""

from __future__ import annotations
from typing import List, Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QPushButton, QMessageBox,
    QWidget,
)
from PySide6.QtCore import Qt

from utils_marathon import (
    normalize_marathon_schedule, DAY_NAMES_SHORT,
)
from .widgets.dark_theme import DARK_TABLE_STYLESHEET


class MarathonScheduleDialog(QDialog):
    """Table editor: each row = collection tag + active days.

    Table order defines rotation order when several rows match the same day
    (e.g. two Sunday-only rows alternate week after week).
    """

    def __init__(self, parent=None, schedule: Optional[List[dict]] = None,
                 available_tags: Optional[List[str]] = None):
        super().__init__(parent)
        self.setWindowTitle("Marathon Schedule")
        self.setModal(True)
        self.resize(620, 380)
        self._available_tags = sorted(set(available_tags or []))

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Each row = one collection tag + days. "
            "Each checked weekday fires only once (first occurrence in the preview, no repeat). "
            "If several rows cover the same day, the topmost row wins."
        ))

        self.table = QTableWidget(0, 3)
        self.table.setStyleSheet(DARK_TABLE_STYLESHEET)
        self.table.setHorizontalHeaderLabels(["Collection Tag", "Days", ""])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.table.setColumnWidth(1, 330)
        self.table.setColumnWidth(2, 70)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add rule")
        add_btn.clicked.connect(lambda: self._add_row())
        btn_row.addWidget(add_btn)
        up_btn = QPushButton("Up")
        up_btn.clicked.connect(lambda: self._move_selected(-1))
        btn_row.addWidget(up_btn)
        down_btn = QPushButton("Down")
        down_btn.clicked.connect(lambda: self._move_selected(1))
        btn_row.addWidget(down_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        ok_row = QHBoxLayout()
        ok_row.addStretch()
        save_btn = QPushButton("OK")
        save_btn.clicked.connect(self._validate_and_accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        ok_row.addWidget(save_btn)
        ok_row.addWidget(cancel_btn)
        layout.addLayout(ok_row)

        for entry in normalize_marathon_schedule(schedule):
            self._add_row(entry.get("tag_name", ""),
                          entry.get("active_days", None))
        if self.table.rowCount() == 0:
            self._add_row()

    def set_available_tags(self, tags: List[str]):
        self._available_tags = sorted(set(tags or []))
        for row in range(self.table.rowCount()):
            combo = self.table.cellWidget(row, 0)
            if isinstance(combo, QComboBox):
                current = combo.currentData() or combo.currentText()
                combo.blockSignals(True)
                combo.clear()
                combo.addItem("None", "")
                for t in self._available_tags:
                    combo.addItem(t, t)
                idx = combo.findData(current)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                combo.blockSignals(False)

    _UNSET = object()
    """Sentinel: fresh row with no days pre-checked; the user must pick days.

    Loaded rules always pass an explicit value (None = all days, or a list),
    so saved schedules keep rendering exactly as stored.
    """

    def _add_row(self, tag_name: str = "", active_days=_UNSET):
        if active_days is self._UNSET:
            preset_days = []
        elif active_days is None:
            preset_days = None  # all days (loaded rule)
        else:
            preset_days = list(active_days)
        row = self.table.rowCount()
        self.table.insertRow(row)

        combo = QComboBox()
        combo.addItem("None", "")
        for t in self._available_tags:
            combo.addItem(t, t)
        if tag_name:
            idx = combo.findData(tag_name)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            elif tag_name not in self._available_tags:
                combo.addItem(tag_name, tag_name)
                combo.setCurrentIndex(combo.findData(tag_name))
        self.table.setCellWidget(row, 0, combo)

        days_widget = QWidget()
        days_layout = QHBoxLayout(days_widget)
        days_layout.setContentsMargins(2, 2, 2, 2)
        day_cbs = []
        for i, day_name in enumerate(DAY_NAMES_SHORT):
            cb = QCheckBox(day_name)
            if preset_days is None:
                cb.setChecked(True)
            else:
                cb.setChecked((i + 1) in preset_days)
            days_layout.addWidget(cb)
            day_cbs.append(cb)
        days_widget.setProperty("day_checkboxes", day_cbs)
        # Store separately since QVariant may not keep python list reliably.
        days_widget._day_cbs = day_cbs
        self.table.setCellWidget(row, 1, days_widget)

        remove_btn = QPushButton("X")
        remove_btn.clicked.connect(lambda _=False, r=row: self._remove_row(r))
        self.table.setCellWidget(row, 2, remove_btn)

    def _row_widgets(self, row: int):
        combo = self.table.cellWidget(row, 0)
        days_widget = self.table.cellWidget(row, 1)
        cbs = getattr(days_widget, "_day_cbs", []) if days_widget is not None else []
        return combo, cbs

    def _remove_row(self, row: int):
        self.table.removeRow(row)
        # Reconnect remove buttons (row indices shifted).
        for r in range(self.table.rowCount()):
            btn = self.table.cellWidget(r, 2)
            if isinstance(btn, QPushButton):
                try:
                    btn.clicked.disconnect()
                except Exception:
                    pass
                btn.clicked.connect(lambda _=False, rr=r: self._remove_row(rr))

    def _move_selected(self, delta: int):
        row = self.table.currentRow()
        if row < 0:
            return
        other = row + delta
        if not 0 <= other < self.table.rowCount():
            return
        # Swap row contents.
        combo_a, cbs_a = self._row_widgets(row)
        combo_b, cbs_b = self._row_widgets(other)
        tag_a = combo_a.currentData() if combo_a else ""
        tag_b = combo_b.currentData() if combo_b else ""
        days_a = [i + 1 for i, cb in enumerate(cbs_a) if cb.isChecked()]
        days_b = [i + 1 for i, cb in enumerate(cbs_b) if cb.isChecked()]
        self._set_row(row, tag_b, days_b)
        self._set_row(other, tag_a, days_a)
        self.table.setCurrentCell(other, self.table.currentColumn())

    def _set_row(self, row: int, tag_name: str, active_days: List[int]):
        combo, cbs = self._row_widgets(row)
        if isinstance(combo, QComboBox):
            idx = combo.findData(tag_name)
            combo.setCurrentIndex(idx if idx >= 0 else 0)
        for i, cb in enumerate(cbs):
            cb.setChecked((i + 1) in active_days)

    def _validate_and_accept(self):
        sched = self.get_schedule()
        if not sched:
            QMessageBox.warning(self, "No Rules",
                                "Add at least one rule with a collection tag and one day.")
            return
        self.accept()

    def get_schedule(self) -> List[dict]:
        result = []
        for row in range(self.table.rowCount()):
            combo, cbs = self._row_widgets(row)
            tag = (combo.currentData() or "") if combo is not None else ""
            if not tag:
                continue
            days = [i + 1 for i, cb in enumerate(cbs) if cb.isChecked()]
            if not days:
                continue
            result.append({"tag_name": tag,
                           "active_days": None if len(days) == 7 else days})
        return normalize_marathon_schedule(result)
