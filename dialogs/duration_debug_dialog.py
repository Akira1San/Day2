from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont

from utils import get_video_display_name
from data_models import FRAGMENT_TAG_TYPE


class DurationDebugDialog(QDialog):
    """Dialog showing duration comparison between schedule entries and collection data."""

    COLORS = {
        "ok":      (QColor("#1e1e2e"), QColor("#a0a0b0")),
        "mismatch": (QColor("#2a1515"), QColor("#ef4444")),
        "default": (QColor("#2a2a15"), QColor("#f59e0b")),
        "unknown": (QColor("#2a2a2e"), QColor("#6a6a7a")),
        "gap":     (QColor("#1e1e2e"), QColor("#94a3b8")),
        "overlap": (QColor("#2a1515"), QColor("#ef4444")),
        "fragment": (QColor("#1a1a2e"), QColor("#818cf8")),
    }
    STATUS_LABELS = {
        "ok":       "OK",
        "mismatch": "MISMATCH",
        "default":  "DEFAULT",
        "unknown":  "UNKNOWN",
        "gap":      "GAP",
        "overlap":  "OVERLAP",
        "fragment":  "FRAGMENT",
    }
    def __init__(self, parent, schedule_entries, collection_videos):
        super().__init__(parent)
        self.setWindowTitle("Duration Debug — Schedule Preview")
        self.setModal(True)
        self.resize(950, 550)
        self.comparison_data = self._build_comparison(schedule_entries, collection_videos)
        self.setup_ui()
        self.apply_styles()

    def _build_comparison(self, entries, collection_videos):
        lookup = {}
        for v in collection_videos:
            name = get_video_display_name(v)
            dur = v.get('duration', 90)
            had = 'duration' in v
            lookup.setdefault(name, []).append((dur, had))

        sorted_entries = sorted(entries, key=lambda e: (e.day, e.start_seconds))
        prev_end = None
        results = []
        for entry in sorted_entries:
            scheduled = entry.end_seconds - entry.start_seconds

            if entry.tag_type == FRAGMENT_TAG_TYPE:
                status = "fragment"
                coll_dur = None
            else:
                video_key = entry.video_name
                if " - " in video_key:
                    video_key = video_key.split(" - ", 1)[1]

                info_list = lookup.get(video_key)
                if info_list is None:
                    filename = video_key.split("/")[-1]
                    info_list = lookup.get(filename)

                if info_list is None:
                    status = "unknown"
                    coll_dur = None
                elif not any(had for _, had in info_list):
                    status = "default"
                    coll_dur = info_list[0][0]
                elif any(scheduled == int(dur) for dur, had in info_list if had):
                    matched = next((dur for dur, had in info_list if had and scheduled == int(dur)), None)
                    status = "ok"
                    coll_dur = matched
                else:
                    status = "mismatch"
                    coll_dur = info_list[0][0]

            if prev_end is None:
                continuity = "ok"
            elif entry.start_seconds == prev_end:
                continuity = "ok"
            elif entry.start_seconds > prev_end:
                continuity = "gap"
            else:
                continuity = "overlap"
            prev_end = entry.end_seconds

            results.append((entry, scheduled, coll_dur, status, continuity))

        return results

    def setup_ui(self):
        layout = QVBoxLayout(self)

        summary = QLabel()
        total = len(self.comparison_data)
        ok_count = sum(1 for _, _, _, s, _ in self.comparison_data if s == "ok")
        mismatch_count = sum(1 for _, _, _, s, _ in self.comparison_data if s == "mismatch")
        default_count = sum(1 for _, _, _, s, _ in self.comparison_data if s == "default")
        unknown_count = sum(1 for _, _, _, s, _ in self.comparison_data if s == "unknown")

        parts = [f"{total} entries"]
        if ok_count:
            parts.append(f"{ok_count} OK")
        if mismatch_count:
            parts.append(f"{mismatch_count} MISMATCH")
        if default_count:
            parts.append(f"{default_count} DEFAULT (90s)")
        if unknown_count:
            parts.append(f"{unknown_count} UNKNOWN")
        summary.setText(" | ".join(parts))
        summary.setFont(QFont("", 12, QFont.Bold))
        layout.addWidget(summary)

        self.table = QTableWidget()
        self.table.setColumnCount(8)
        headers = ["#", "Day", "Time", "Video", "Scheduled", "Collection", "Status", "Continuity"]
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeToContents)
        self.table.setColumnWidth(0, 40)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)

        self.table.setRowCount(len(self.comparison_data))
        for row, (entry, scheduled, coll_dur, status, continuity) in enumerate(self.comparison_data):
            bg, fg = self.COLORS.get(status, (QColor("#1e1e2e"), QColor("#a0a0b0")))

            start_h = (entry.start_seconds // 3600) % 24
            start_m = (entry.start_seconds % 3600) // 60
            end_h = (entry.end_seconds // 3600) % 24
            end_m = (entry.end_seconds % 3600) // 60
            time_str = f"{start_h:02d}:{start_m:02d} - {end_h:02d}:{end_m:02d}"

            coll_str = f"{int(coll_dur)}s" if coll_dur is not None else "N/A"
            status_label = self.STATUS_LABELS.get(status, status)

            continuity_label = self.STATUS_LABELS.get(continuity, continuity)
            items_data = [
                str(row + 1),
                str((entry.start_seconds // 86400) + 1),
                time_str,
                entry.video_name,
                f"{scheduled}s",
                coll_str,
                status_label,
                continuity_label,
            ]

            for col, text in enumerate(items_data):
                item = QTableWidgetItem(text)
                if col == 7:
                    cell_bg, cell_fg = self.COLORS.get(continuity, (QColor("#1e1e2e"), QColor("#a0a0b0")))
                    item.setBackground(cell_bg)
                    item.setForeground(cell_fg)
                else:
                    item.setBackground(bg)
                    item.setForeground(fg)
                if status in ("mismatch",) or continuity in ("overlap",):
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                self.table.setItem(row, col, item)

        layout.addWidget(self.table)

        self.copy_btn = QPushButton("Copy to Clipboard")
        self.copy_btn.clicked.connect(self.copy_to_clipboard)

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.copy_btn)
        btn_layout.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def copy_to_clipboard(self):
        lines = []
        lines.append("#\tDay\tTime\tVideo\tScheduled\tCollection\tStatus\tContinuity")
        for row, (entry, scheduled, coll_dur, status, continuity) in enumerate(self.comparison_data):
            start_h = (entry.start_seconds // 3600) % 24
            start_m = (entry.start_seconds % 3600) // 60
            end_h = (entry.end_seconds // 3600) % 24
            end_m = (entry.end_seconds % 3600) // 60
            time_str = f"{start_h:02d}:{start_m:02d} - {end_h:02d}:{end_m:02d}"
            coll_str = f"{int(coll_dur)}s" if coll_dur is not None else "N/A"
            status_label = self.STATUS_LABELS.get(status, status)
            continuity_label = self.STATUS_LABELS.get(continuity, continuity)
            lines.append(
                f"{row + 1}\t{(entry.start_seconds // 86400) + 1}\t{time_str}\t{entry.video_name}\t{scheduled}s\t{coll_str}\t{status_label}\t{continuity_label}"
            )
        QApplication.clipboard().setText("\n".join(lines))

    def apply_styles(self):
        self.setStyleSheet("""
            QDialog { background-color: #1e1e2e; }
            QLabel { color: #f8f8f2; }
            QPushButton {
                background-color: #2a2a3e;
                color: #f8f8f2;
                border: 1px solid #3a3a4e;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #3a3a4e; }
            QPushButton:pressed { background-color: #4a4a5e; }
            QTableWidget {
                background-color: #1e1e2e;
                border: 1px solid #3a3a4e;
                border-radius: 4px;
                gridline-color: #3a3a4e;
            }
            QHeaderView::section {
                background-color: #2a2a3e;
                color: #f8f8f2;
                border: 1px solid #3a3a4e;
                padding: 4px;
                font-weight: bold;
            }
        """)
