from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTreeWidget, QTreeWidgetItem, QHeaderView, QMessageBox
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
        "gap":     (QColor("#1e1e2e"), QColor("#f59e0b")),
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
        source_lookup = {}
        for v in collection_videos:
            name = get_video_display_name(v)
            dur = v.get('duration', 90)
            had = 'duration' in v
            lookup.setdefault(name, []).append((dur, had))
            src = v.get('_source_name', '')
            if src:
                source_lookup[name] = src

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

            source = source_lookup.get(video_key, '')
            if not source:
                source = source_lookup.get(video_key.split("/")[-1], '')

            if prev_end is None:
                continuity = "ok"
            elif entry.start_seconds == prev_end:
                continuity = "ok"
            elif entry.start_seconds > prev_end:
                continuity = "gap"
            else:
                continuity = "overlap"
            prev_end = entry.end_seconds

            results.append((entry, scheduled, coll_dur, status, continuity, source))

        return results

    def setup_ui(self):
        layout = QVBoxLayout(self)

        summary = QLabel()
        total = len(self.comparison_data)
        ok_count = sum(1 for _, _, _, s, _, _ in self.comparison_data if s == "ok")
        mismatch_count = sum(1 for _, _, _, s, _, _ in self.comparison_data if s == "mismatch")
        default_count = sum(1 for _, _, _, s, _, _ in self.comparison_data if s == "default")
        unknown_count = sum(1 for _, _, _, s, _, _ in self.comparison_data if s == "unknown")
        gap_count = sum(1 for _, _, _, _, _, c in self.comparison_data if c == "gap")
        overlap_count = sum(1 for _, _, _, _, _, c in self.comparison_data if c == "overlap")

        parts = [f"{total} entries"]
        if ok_count:
            parts.append(f"{ok_count} OK")
        if mismatch_count:
            parts.append(f"{mismatch_count} MISMATCH")
        if default_count:
            parts.append(f"{default_count} DEFAULT (90s)")
        if unknown_count:
            parts.append(f"{unknown_count} UNKNOWN")
        if gap_count:
            parts.append(f"{gap_count} GAP")
        if overlap_count:
            parts.append(f"{overlap_count} OVERLAP")
        summary.setText(" | ".join(parts))
        summary.setFont(QFont("", 12, QFont.Bold))
        layout.addWidget(summary)

        self.table = QTreeWidget()
        self.table.setColumnCount(9)
        headers = ["#", "Day", "Time", "Video", "Source", "Scheduled", "Collection", "Status", "Continuity"]
        self.table.setHeaderLabels(headers)
        self.table.header().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.header().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.header().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.header().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table.header().setSectionResizeMode(6, QHeaderView.ResizeToContents)
        self.table.header().setSectionResizeMode(7, QHeaderView.ResizeToContents)
        self.table.header().setSectionResizeMode(8, QHeaderView.ResizeToContents)
        self.table.setColumnWidth(0, 40)
        self.table.setSelectionMode(QTreeWidget.NoSelection)
        self.table.setEditTriggers(QTreeWidget.NoEditTriggers)
        self.table.setRootIsDecorated(True)
        self.table.setAnimated(True)

        i = 0
        row_counter = 0
        while i < len(self.comparison_data):
            entry, scheduled, coll_dur, status, continuity, source = self.comparison_data[i]
            gap_fill_entries = []
            while i < len(self.comparison_data) and self.comparison_data[i][0].tag_type == "gap_fill":
                gap_fill_entries.append(self.comparison_data[i])
                i += 1
            if gap_fill_entries:
                first_entry = gap_fill_entries[0][0]
                last_entry = gap_fill_entries[-1][0]
                start_h = (first_entry.start_seconds // 3600) % 24
                start_m = (first_entry.start_seconds % 3600) // 60
                end_h = (last_entry.end_seconds // 3600) % 24
                end_m = (last_entry.end_seconds % 3600) // 60
                total_scheduled = sum(e.end_seconds - e.start_seconds for e, _, _, _, _, _ in gap_fill_entries)
                parent = QTreeWidgetItem(self.table)
                parent_texts = [
                    "-",
                    str((first_entry.start_seconds // 86400) + 1),
                    f"{start_h:02d}:{start_m:02d} - {end_h:02d}:{end_m:02d}",
                    "Gap filler entries",
                    "-",
                    f"{total_scheduled}s",
                    "N/A",
                    "GAP",
                    "-",
                ]
                for col, text in enumerate(parent_texts):
                    parent.setText(col, text)
                    parent.setForeground(col, QColor("#f59e0b"))
                font = parent.font(0)
                font.setBold(True)
                parent.setFont(0, font)
                parent.setExpanded(False)
                for ge, gsched, gdur, gstatus, gcont, gsrc in gap_fill_entries:
                    child = QTreeWidgetItem(parent)
                    start_h = (ge.start_seconds // 3600) % 24
                    start_m = (ge.start_seconds % 3600) // 60
                    end_h = (ge.end_seconds // 3600) % 24
                    end_m = (ge.end_seconds % 3600) // 60
                    time_str = f"{start_h:02d}:{start_m:02d} - {end_h:02d}:{end_m:02d}"
                    coll_str = f"{int(gdur)}s" if gdur is not None else "N/A"
                    status_label = self.STATUS_LABELS.get(gstatus, gstatus)
                    continuity_label = self.STATUS_LABELS.get(gcont, gcont)
                    child_texts = [
                        str(row_counter + 1),
                        str((ge.start_seconds // 86400) + 1),
                        time_str,
                        ge.video_name,
                        gsrc,
                        f"{gsched}s",
                        coll_str,
                        status_label,
                        continuity_label,
                    ]
                    child_bg, child_fg = self.COLORS.get(gstatus, (QColor("#1e1e2e"), QColor("#a0a0b0")))
                    for col, text in enumerate(child_texts):
                        child.setText(col, text)
                        child.setBackground(col, child_bg)
                        child.setForeground(col, child_fg)
                    row_counter += 1
            else:
                bg, fg = self.COLORS.get(status, (QColor("#1e1e2e"), QColor("#a0a0b0")))
                start_h = (entry.start_seconds // 3600) % 24
                start_m = (entry.start_seconds % 3600) // 60
                end_h = (entry.end_seconds // 3600) % 24
                end_m = (entry.end_seconds % 3600) // 60
                time_str = f"{start_h:02d}:{start_m:02d} - {end_h:02d}:{end_m:02d}"
                coll_str = f"{int(coll_dur)}s" if coll_dur is not None else "N/A"
                status_label = self.STATUS_LABELS.get(status, status)
                continuity_label = self.STATUS_LABELS.get(continuity, continuity)
                item_texts = [
                    str(row_counter + 1),
                    str((entry.start_seconds // 86400) + 1),
                    time_str,
                    entry.video_name,
                    source,
                    f"{scheduled}s",
                    coll_str,
                    status_label,
                    continuity_label,
                ]
                item = QTreeWidgetItem(self.table)
                for col, text in enumerate(item_texts):
                    if col == 8:
                        cell_bg, cell_fg = self.COLORS.get(continuity, (QColor("#1e1e2e"), QColor("#a0a0b0")))
                        item.setBackground(col, cell_bg)
                        item.setForeground(col, cell_fg)
                    else:
                        item.setBackground(col, bg)
                        item.setForeground(col, fg)
                    item.setText(col, text)
                if status in ("mismatch",) or continuity in ("overlap",):
                    font = item.font(0)
                    font.setBold(True)
                    item.setFont(0, font)
                row_counter += 1
                i += 1

        layout.addWidget(self.table)

        self.copy_btn = QPushButton("Copy to Clipboard")
        self.copy_btn.clicked.connect(self.copy_to_clipboard)

        help_btn = QPushButton("Help")
        help_btn.clicked.connect(self.show_help)

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.copy_btn)
        btn_layout.addWidget(help_btn)
        btn_layout.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _collect_row_lines(self, item, lines):
        if item.childCount() > 0:
            for i in range(item.childCount()):
                self._collect_row_lines(item.child(i), lines)
        else:
            parts = []
            for col in range(self.table.columnCount()):
                parts.append(item.text(col) if item.text(col) else "")
            line = "\t".join(parts)
            if line.strip():
                lines.append(line)

    def copy_to_clipboard(self):
        lines = []
        lines.append("#\tDay\tTime\tVideo\tSource\tScheduled\tCollection\tStatus\tContinuity")
        for i in range(self.table.topLevelItemCount()):
            self._collect_row_lines(self.table.topLevelItem(i), lines)
        QApplication.clipboard().setText("\n".join(lines))

    def show_help(self):
        QMessageBox.information(self, "Debug Dialog — Legend",
            "<b>Status column</b><br>"
            "<b>OK</b> — Scheduled duration matches collection duration<br>"
            "<b>MISMATCH</b> — Scheduled duration differs from collection<br>"
            "<b>DEFAULT</b> — No explicit duration in collection; 90s assumed<br>"
            "<b>UNKNOWN</b> — Video not found in any loaded collection<br>"
            "<b>FRAGMENT</b> — Head/tail portion of a video cut by a tag slot;<br>"
            "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;duration comparison skipped<br>"
            "<br>"
            "<b>Continuity column</b><br>"
            "<b>OK</b> — Starts exactly when previous entry ends<br>"
            "<b>GAP</b> — Starts after previous entry — unfilled time<br>"
            "<b>OVERLAP</b> — Starts before previous entry ends<br>"
            "<br>"
            "<b>Collection column</b><br>"
            "Expected duration (seconds) from the collection file.<br>"
            "Shows <b>N/A</b> for fragments (duration comparison not applicable).")

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
            QTreeWidget {
                background-color: #1e1e2e;
                border: 1px solid #3a3a4e;
                border-radius: 4px;
                alternate-background-color: #252535;
            }
            QHeaderView::section {
                background-color: #2a2a3e;
                color: #f8f8f2;
                border: 1px solid #3a3a4e;
                padding: 4px;
                font-weight: bold;
            }
            QTreeWidget::branch {
                background: transparent;
            }
        """)
