#!/usr/bin/env python3
import sys
import os
import json
import configparser
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime

log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_path = log_dir / f"daypart_scheduler_{timestamp}.log"
log_handler = RotatingFileHandler(log_path, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
log_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
logging.getLogger().addHandler(log_handler)
logging.getLogger().setLevel(logging.DEBUG)
stdout_handler = logging.StreamHandler(sys.stdout)
stdout_handler.setLevel(logging.DEBUG)
stdout_handler.setFormatter(logging.Formatter('[%(levelname)s] %(name)s: %(message)s'))
logging.getLogger().addHandler(stdout_handler)

from typing import List, Optional
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QListWidgetItem, QTreeWidget, QTreeWidgetItem, QPushButton, QDialog, QLineEdit,
    QLabel, QTimeEdit, QMessageBox, QScrollArea, QCheckBox, QRadioButton, QButtonGroup,
    QFileDialog, QSpinBox, QComboBox
)
from PySide6.QtCore import Qt, QTime
from PySide6.QtGui import QClipboard, QColor, QFont

import logging
preview_log = logging.getLogger("preview")
preview_log.setLevel(logging.DEBUG)


from utils import (
    load_collection_json, load_blacklist_json,
    parse_series_episode, parse_videos_for_series,
    get_video_display_name, format_duration, get_config_paths, filter_videos_by_blacklist,
    get_schedule_profiles, load_gap_collections
)
from models import Tag, ScheduleEntry, TagManager, ScheduleGenerator, compute_schedule_issues, mark_continuity_problems
from dialogs import TagDialog, RandomFillDialog, SeriesDialog, ConfigDialog, SchedulePreviewDialog, DurationDebugDialog, GapTagDialog


APPROXIMATE_THRESHOLD_MINUTES = 40


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Daypart Scheduler")
        self.resize(1000, 600)
        self.tag_manager = TagManager()
        self.schedule_generator = ScheduleGenerator(self.tag_manager)
        self.schedule_entries: List[ScheduleEntry] = []
        self.last_generated_schedule = None
        self.approximate_enabled = False
        self.statusBar().showMessage("Approximate: OFF")
        self.setup_ui()
        self.schedule_generator.video_order_mode = "random"
        self.load_default_tags()
        self.refresh_preview()

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)

        self.tags_panel = QWidget()
        self.tags_panel.setFixedWidth(500)
        tags_layout = QVBoxLayout(self.tags_panel)

        tags_title = QLabel("Daypart Tags")
        tags_title.setFont(QFont("", 16, QFont.Bold))
        tags_layout.addWidget(tags_title)

        self.tags_list = QListWidget()
        self.tags_list.setAlternatingRowColors(True)
        self.tags_list.setFont(QFont("", 14))
        tags_layout.addWidget(self.tags_list)

        btn_layout = QHBoxLayout()
        self.add_btn = QPushButton("Custom")
        self.add_btn.setToolTip("Add a custom time slot tag")
        self.add_btn.clicked.connect(self.add_custom_tag)
        btn_layout.addWidget(self.add_btn)

        self.add_random_btn = QPushButton("Random Fill")
        self.add_random_btn.setToolTip("Add a random fill tag for gaps")
        self.add_random_btn.clicked.connect(self.add_random_fill_tag)
        btn_layout.addWidget(self.add_random_btn)

        self.add_series_btn = QPushButton("Series")
        self.add_series_btn.setToolTip("Add a series/episode tag")
        self.add_series_btn.clicked.connect(self.add_series_tag)
        btn_layout.addWidget(self.add_series_btn)

        self.add_multi_series_btn = QPushButton("Multi-Series")
        self.add_multi_series_btn.setToolTip("Add a multi-series container tag")
        self.add_multi_series_btn.clicked.connect(self.add_multi_series_tag)
        btn_layout.addWidget(self.add_multi_series_btn)

        self.add_gap_btn = QPushButton("Gap")
        self.add_gap_btn.setToolTip("Add a gap filler tag to fill empty time intervals")
        self.add_gap_btn.clicked.connect(self.add_gap_tag)
        btn_layout.addWidget(self.add_gap_btn)

        self.edit_btn = QPushButton("Edit")
        self.edit_btn.setToolTip("Edit the selected tag")
        self.edit_btn.clicked.connect(self.edit_tag)
        btn_layout.addWidget(self.edit_btn)

        self.delete_btn = QPushButton("Delete")
        self.delete_btn.setToolTip("Delete the selected tag")
        self.delete_btn.clicked.connect(self.delete_tag)
        btn_layout.addWidget(self.delete_btn)

        tags_layout.addLayout(btn_layout)

        save_load_layout = QHBoxLayout()
        self.save_btn = QPushButton("Save All")
        self.save_btn.setToolTip("Save all tags to an INI file (default: tags.ini)")
        self.save_btn.clicked.connect(self.save_tags)
        save_load_layout.addWidget(self.save_btn)

        self.load_btn = QPushButton("Load All")
        self.load_btn.setToolTip("Load all tags from an INI file (default: tags.ini)")
        self.load_btn.clicked.connect(self.load_tags)
        save_load_layout.addWidget(self.load_btn)

        self.save_single_btn = QPushButton("Save Tag")
        self.save_single_btn.setToolTip("Save selected tag to file")
        self.save_single_btn.clicked.connect(self.save_single_tag)
        save_load_layout.addWidget(self.save_single_btn)

        self.load_single_btn = QPushButton("Load Tag")
        self.load_single_btn.setToolTip("Load tag from file")
        self.load_single_btn.clicked.connect(self.load_single_tag)
        save_load_layout.addWidget(self.load_single_btn)

        self.config_btn = QPushButton("Config")
        self.config_btn.setToolTip("Open configuration")
        self.config_btn.clicked.connect(self.open_config)
        save_load_layout.addWidget(self.config_btn)

        self.help_btn = QPushButton("Help")
        self.help_btn.setToolTip("Show help and usage guide")
        self.help_btn.clicked.connect(self.show_help)
        save_load_layout.addWidget(self.help_btn)

        tags_layout.addLayout(save_load_layout)

        main_layout.addWidget(self.tags_panel)

        self.preview_panel = QWidget()
        preview_layout = QVBoxLayout(self.preview_panel)

        self.preview_title = QLabel("24-Hour Schedule Preview")
        self.preview_title.setFont(QFont("", 16, QFont.Bold))
        preview_layout.addWidget(self.preview_title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.preview_list = QTreeWidget()
        self.preview_list.setHeaderHidden(True)
        self.preview_list.setIndentation(16)
        self.preview_list.setRootIsDecorated(True)
        self.preview_list.setAnimated(True)
        scroll.setWidget(self.preview_list)
        preview_layout.addWidget(scroll)

        # Initialize combo boxes before layout
        self.schedule_profile_combo = QComboBox()
        self.schedule_profile_combo.setEditable(True)
        self.load_schedule_profiles()

        self.approx_mode_combo = QComboBox()
        self.approx_mode_combo.addItems(["Linear", "Find-Replace", "Shift Overlay", "Early Fill", "Late Fill", "Priority", "Best Fit", "Round Robin", "Linear Spanning", "Exhaustive", "No Overlap", "Group Approximate"])
        self.approx_mode_combo.setToolTip("Approximate algorithm mode")
        self.approx_mode_combo.setFixedWidth(120)

        self.overlap_strategy_combo = QComboBox()
        self.overlap_strategy_combo.addItems(["Fragment (current)", "Skip overlapped", "Gap-fill", "Compact stream"])
        self.overlap_strategy_combo.setToolTip("How to handle random entries overlapping tag slots")
        self.overlap_strategy_combo.setFixedWidth(130)

        # Initialize buttons before layout
        self.copy_btn = QPushButton("Copy")
        self.copy_btn.setToolTip("Copy preview to clipboard")
        self.copy_btn.clicked.connect(self.copy_preview)

        self.generate_btn = QPushButton("Generate")
        self.generate_btn.setToolTip("Generate preview based on radio selection")
        self.generate_btn.clicked.connect(self.generate_new_preview)

        self.save_schedule_btn = QPushButton("Save Schedule")
        self.save_schedule_btn.setToolTip("Save schedule to file")
        self.save_schedule_btn.clicked.connect(self.save_schedule)

        self.inspect_btn = QPushButton("Inspect")
        self.inspect_btn.setToolTip("Browse and preview a saved schedule file")
        self.inspect_btn.clicked.connect(self.inspect_schedule)

        self.approx_btn = QPushButton("Approximate OFF")
        self.approx_btn.setToolTip("Toggle approximate scheduling mode")
        self.approx_btn.setStyleSheet("background-color: #4a4a5e; color: #a0a0b0; font-weight: bold; padding: 10px 20px; border-radius: 6px;")
        self.approx_btn.clicked.connect(self.run_approximate)

        bottom_btn_layout = QVBoxLayout()
        
        # First row: view options and profile
        row1_layout = QHBoxLayout()
        self.view_group = QButtonGroup(self)
        self.daily_radio = QRadioButton("Daily")
        self.daily_radio.setChecked(True)
        self.weekly_radio = QRadioButton("Weekly (7 days)")
        self.monthly_radio = QRadioButton("Calendar (30 days)")
        self.view_group.addButton(self.daily_radio)
        self.view_group.addButton(self.weekly_radio)
        self.view_group.addButton(self.monthly_radio)
        row1_layout.addWidget(self.daily_radio)
        row1_layout.addWidget(self.weekly_radio)
        row1_layout.addWidget(self.monthly_radio)
        
        row1_layout.addWidget(QLabel("Profile:"))
        row1_layout.addWidget(self.schedule_profile_combo)
        row1_layout.addWidget(QLabel("Video Order:"))
        self.video_order_combo = QComboBox()
        self.video_order_combo.addItems(["Random", "Movie Sequence"])
        self.video_order_combo.setToolTip("Global video ordering mode for non-series tags")
        self.video_order_combo.setFixedWidth(150)
        self.video_order_combo.currentIndexChanged.connect(self._on_video_order_changed)
        row1_layout.addWidget(self.video_order_combo)
        row1_layout.addStretch()
        bottom_btn_layout.addLayout(row1_layout)
        
        # Second row: action buttons and approximate controls
        row2_layout = QHBoxLayout()
        row2_layout.addWidget(self.copy_btn)
        row2_layout.addWidget(self.generate_btn)
        row2_layout.addWidget(self.save_schedule_btn)
        row2_layout.addWidget(self.inspect_btn)
        self.debug_btn = QPushButton("Debug")
        self.debug_btn.setToolTip("Debug video durations — compare schedule vs collection data")
        self.debug_btn.clicked.connect(self.debug_durations)
        row2_layout.addWidget(self.debug_btn)
        row2_layout.addStretch()
        row2_layout.addWidget(self.approx_mode_combo)
        row2_layout.addWidget(self.overlap_strategy_combo)
        row2_layout.addWidget(self.approx_btn)
        bottom_btn_layout.addLayout(row2_layout)

        preview_layout.addLayout(bottom_btn_layout)

        main_layout.addWidget(self.preview_panel)

        self.apply_styles()

    def apply_styles(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #1e1e2e; }
            QWidget { color: #f8f8f2; }
            QLabel { color: #f8f8f2; }
            QTreeWidget {
                background-color: #2a2a3e;
                border: 1px solid #3a3a4e;
                border-radius: 6px;
                padding: 4px;
                selection-background-color: #7c3aed;
                show-decoration-selected: 1;
            }
            QTreeWidget::item {
                padding: 4px;
                margin: 1px;
                border: 1px solid transparent;
            }
            QTreeWidget::item:selected {
                background-color: #7c3aed;
                border: 2px solid #a78bfa;
                color: white;
            }
            QTreeWidget::item:hover {
                background-color: #3a3a4e;
            }
            QTreeWidget::branch {
                background: transparent;
            }
            QPushButton {
                background-color: #2a2a3e;
                color: #f8f8f2;
                border: 1px solid #3a3a4e;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #3a3a4e; }
            QPushButton:pressed { background-color: #4a4a5e; }
            QLineEdit, QTimeEdit {
                background-color: #2a2a3e;
                color: #f8f8f2;
                border: 1px solid #3a3a4e;
                border-radius: 4px;
                padding: 8px;
            }
            QDialog { background-color: #1e1e2e; }
            QToolTip {
                font-size: 13px;
                padding: 4px 8px;
                border: 1px solid #3a3a4e;
                border-radius: 4px;
            }
        """)
        self.tags_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.tags_list.setFocusPolicy(Qt.StrongFocus)

    def load_default_tags(self):
        self.refresh_tags_list()

    def refresh_tags_list(self):
        self.tags_list.clear()
        for tag in self.tag_manager.tags:
            item = QListWidgetItem(tag.to_display_string())
            color = tag.tag_color
            if color:
                item.setForeground(color)
            self.tags_list.addItem(item)

    def refresh_preview(self):
        self.preview_list.clear()
        mode = None
        if self.approximate_enabled:
            mode = self.approx_mode_combo.currentText().lower().replace("-", "_").replace(" ", "_")
            entries = self.schedule_generator.apply_approximate(mode=mode, overlap_strategy=self._get_overlap_strategy())
        else:
            entries = self.schedule_generator.apply_custom_tags()
        mark_continuity_problems(entries)
        self._add_entries_to_tree(entries)
        self.schedule_entries = entries
        self.last_generated_schedule = {
            'entries': entries,
            'num_days': 1,
            'approximate_enabled': self.approximate_enabled,
            'mode': mode,
            'overlap_strategy': self._get_overlap_strategy() if self.approximate_enabled else None,
        }
        self._show_issues_in_statusbar(entries)

    def generate_new_preview(self):
        self.tag_manager.clear_cache()
        self.schedule_generator.video_order_mode = self.video_order_combo.currentText().lower().replace(" ", "_")
        
        if self.weekly_radio.isChecked():
            self.generate_weekly_preview()
        elif self.monthly_radio.isChecked():
            self.generate_monthly_preview()
        else:
            self.refresh_preview()

    def generate_weekly_preview(self):
        self.preview_list.clear()
        self.preview_title.setText("Weekly Schedule Preview (7 Days)")

        from datetime import date
        start_date = date.today()
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

        self.tag_manager.clear_cache()
        self.schedule_generator.video_order_mode = self.video_order_combo.currentText().lower().replace(" ", "_")
        self.schedule_generator.schedule_start_weekday = start_date.weekday()
        mode = None
        if not self.approximate_enabled:
            entries = self.schedule_generator.apply_custom_tags(num_days=7)
        else:
            mode = self.approx_mode_combo.currentText().lower().replace("-", "_").replace(" ", "_")
            entries = self.schedule_generator.apply_approximate(num_days=7, mode=mode, overlap_strategy=self._get_overlap_strategy())
        mark_continuity_problems(entries)
        self.schedule_entries = entries
        self.last_generated_schedule = {
            'entries': entries,
            'num_days': 7,
            'approximate_enabled': self.approximate_enabled,
            'mode': mode,
            'overlap_strategy': self._get_overlap_strategy() if self.approximate_enabled else None,
        }
        self._show_issues_in_statusbar(entries)

        for day_offset in range(7):
            current_date = start_date + __import__('datetime').timedelta(days=day_offset)
            day_name = days[current_date.weekday()]
            day_item = QTreeWidgetItem(self.preview_list)
            day_item.setText(0, f"=== {current_date} - {day_name} ===")
            is_weekend = day_name in ("Saturday", "Sunday")
            bg_color = QColor("#ef4444") if is_weekend else QColor("#7c3aed")
            day_item.setBackground(0, bg_color)
            day_item.setForeground(0, QColor("#ffffff"))
            font = day_item.font(0)
            font.setBold(True)
            day_item.setFont(0, font)
            day_item.setFlags(day_item.flags() & ~Qt.ItemIsSelectable)
            day_start_seconds = day_offset * 86400
            day_end_seconds = day_start_seconds + 86400
            day_entries = [
                e for e in entries
                if e.start_seconds >= day_start_seconds and e.start_seconds < day_end_seconds
            ]
            self._add_entries_to_tree(day_entries)
    def generate_monthly_preview(self):
        self.preview_list.clear()
        self.preview_title.setText("Calendar Schedule Preview (30 Days)")

        from datetime import date
        start_date = date.today()
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

        self.tag_manager.clear_cache()
        self.schedule_generator.video_order_mode = self.video_order_combo.currentText().lower().replace(" ", "_")
        self.schedule_generator.schedule_start_weekday = start_date.weekday()
        mode = None
        if not self.approximate_enabled:
            entries = self.schedule_generator.apply_custom_tags(num_days=30)
        else:
            mode = self.approx_mode_combo.currentText().lower().replace("-", "_").replace(" ", "_")
            entries = self.schedule_generator.apply_approximate(num_days=30, mode=mode, overlap_strategy=self._get_overlap_strategy())
        mark_continuity_problems(entries)
        # Store for save reuse and debug
        self.schedule_entries = entries
        self.last_generated_schedule = {
            'entries': entries,
            'num_days': 30,
            'approximate_enabled': self.approximate_enabled,
            'mode': mode,
            'overlap_strategy': self._get_overlap_strategy() if self.approximate_enabled else None,
        }
        self._show_issues_in_statusbar(entries)

        for day_offset in range(30):
            current_date = start_date + __import__('datetime').timedelta(days=day_offset)
            day_name = days[current_date.weekday()]
            day_item = QTreeWidgetItem(self.preview_list)
            day_item.setText(0, f"=== {current_date} - {day_name} ===")
            is_weekend = day_name in ("Saturday", "Sunday")
            bg_color = QColor("#ef4444") if is_weekend else QColor("#7c3aed")
            day_item.setBackground(0, bg_color)
            day_item.setForeground(0, QColor("#ffffff"))
            font = day_item.font(0)
            font.setBold(True)
            day_item.setFont(0, font)
            day_item.setFlags(day_item.flags() & ~Qt.ItemIsSelectable)
            day_start_seconds = day_offset * 86400
            day_end_seconds = day_start_seconds + 86400
            day_entries = [
                e for e in entries
                if e.start_seconds >= day_start_seconds and e.start_seconds < day_end_seconds
            ]
            self._add_entries_to_tree(day_entries)

    def _show_issues_in_statusbar(self, entries=None):
        if entries is None:
            entries = self.schedule_entries
        if not entries:
            self.statusBar().showMessage("No entries to check")
            return
        issues = compute_schedule_issues(entries)
        msg = f"{issues['total']} entries"
        if issues['gaps']:
            msg += f", {issues['gaps']} gap(s)"
        if issues['overlaps']:
            msg += f", {issues['overlaps']} overlap(s)"
        if issues['mismatches']:
            msg += f", {issues['mismatches']} mismatch(es)"
        if issues['gaps'] or issues['overlaps'] or issues['mismatches']:
            msg += " — check Debug for details"
        preview_log.info(f"Schedule issues: {msg}")
        self.statusBar().showMessage(msg)

    @staticmethod
    def _is_gap_entry(entry):
        return entry.tag_type == "gap_fill"

    def _add_gap_group(self, gap_entries):
        n = len(gap_entries)
        first = gap_entries[0]
        last = gap_entries[-1]
        start_h = (first.start_seconds // 3600) % 24
        start_m = (first.start_seconds % 3600) // 60
        end_h = (last.end_seconds // 3600) % 24
        end_m = (last.end_seconds % 3600) // 60
        parent = QTreeWidgetItem(self.preview_list)
        parent.setText(0, f"▶ Gap — {n} entries — {start_h:02d}:{start_m:02d}–{end_h:02d}:{end_m:02d}")
        parent.setForeground(0, QColor("#f59e0b"))
        font = parent.font(0)
        font.setBold(True)
        parent.setFont(0, font)
        parent.setExpanded(False)
        for gap_entry in gap_entries:
            child = QTreeWidgetItem(parent)
            child.setText(0, gap_entry.to_display_string())
            child.setData(0, Qt.UserRole, gap_entry)
            color = gap_entry.tag_color
            if color:
                child.setForeground(0, color)

    def _add_entries_to_tree(self, entries):
        i = 0
        while i < len(entries):
            entry = entries[i]
            if self._is_gap_entry(entry):
                gap_entries = [entry]
                i += 1
                while i < len(entries) and self._is_gap_entry(entries[i]):
                    gap_entries.append(entries[i])
                    i += 1
                self._add_gap_group(gap_entries)
            else:
                item = QTreeWidgetItem(self.preview_list)
                item.setText(0, entry.to_display_string())
                item.setData(0, Qt.UserRole, entry)
                color = entry.tag_color
                if color:
                    item.setForeground(0, color)
                i += 1

    def _collect_item_text(self, item, items):
        if item.childCount() > 0:
            for i in range(item.childCount()):
                self._collect_item_text(item.child(i), items)
        else:
            entry = item.data(0, Qt.UserRole)
            if entry and hasattr(entry, "to_copy_string"):
                items.append(entry.to_copy_string())
            else:
                items.append(item.text(0))

    def debug_durations(self):
        entries = self.schedule_entries
        if not entries and self.last_generated_schedule:
            entries = self.last_generated_schedule.get('entries', [])
        if not entries:
            self.statusBar().showMessage("No schedule entries to debug. Generate a preview first.")
            return

        from pathlib import Path
        from utils import get_config_paths, load_collection_videos_only
        collection_path, _ = get_config_paths()
        all_videos = []

        seen_paths = set()
        def _load_from(file_path, source_name=None):
            fp = str(file_path)
            if fp in seen_paths:
                return
            seen_paths.add(fp)
            videos = load_collection_videos_only(fp)
            if source_name is None:
                stem = Path(fp).stem
                if stem.startswith('collections_'):
                    source_name = stem.replace('collections_', '')
                else:
                    source_name = stem
            for v in videos:
                v['_source_name'] = source_name
            all_videos.extend(videos)

        coll_dir = Path(collection_path)
        if coll_dir.exists():
            for json_file in sorted(coll_dir.glob("*.json")):
                _load_from(json_file)

        for tag in self.tag_manager.tags:
            tag_path = getattr(tag, 'collection_path', '') or ''
            if tag_path:
                _load_from(tag_path)
            for extra_path in getattr(tag, 'extra_collections', []):
                _load_from(extra_path)

        dialog = DurationDebugDialog(self, entries, all_videos)
        dialog.exec()

    def save_tags(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save All Tags", "tags.ini",
            "INI Files (*.ini);;All Files (*)",
        )
        if not file_path:
            return
        if not file_path.endswith('.ini'):
            file_path += '.ini'
        if os.path.exists(file_path):
            reply = QMessageBox.question(
                self, "Overwrite?",
                f"{file_path} already exists. Overwrite it with the current tags?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
        try:
            self.tag_manager.save_tags(file_path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save tags:\n{e}")
            return
        QMessageBox.information(
            self, "Saved",
            f"Tags saved to {file_path} ({len(self.tag_manager.tags)} tag(s)).",
        )
        self.statusBar().showMessage(f"Tags saved to {file_path}")

    def load_tags(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Load All Tags", "tags.ini",
            "INI Files (*.ini);;All Files (*)",
        )
        if not file_path:
            return
        if not os.path.exists(file_path):
            QMessageBox.warning(self, "Not Found", f"No such file: {file_path}")
            return
        if self.tag_manager.tags:
            reply = QMessageBox.question(
                self, "Discard Current Tags?",
                f"Loading from {file_path} will replace the {len(self.tag_manager.tags)} "
                f"tag(s) currently in memory. Continue?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
        try:
            loaded = self.tag_manager.load_tags(file_path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load tags:\n{e}")
            return
        if loaded:
            self.refresh_tags_list()
            self.refresh_preview()
            QMessageBox.information(
                self, "Loaded",
                f"Loaded {len(self.tag_manager.tags)} tag(s) from {file_path}.",
            )
            self.statusBar().showMessage(f"Tags loaded from {file_path}")
        else:
            QMessageBox.information(
                self, "Empty File",
                f"{file_path} exists but contains no tags.",
            )

    def show_help(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Help — Daypart Scheduler")
        dialog.resize(600, 500)
        layout = QVBoxLayout(dialog)
        text = QLabel(
            "<h2>Daypart Scheduler</h2>"
            "<p>Schedule dayparted video playlists with custom tags, gap fillers, and approximate placement.</p>"
            "<hr>"
            "<h3>Tags Panel (Left)</h3>"
            "<p><b>Custom</b> — Add a fixed time-slot tag. Set a video, start/end time, and it appears at that position in the schedule.</p>"
            "<p><b>Random Fill</b> — Add a video collection used to fill gaps between custom tags. Supports 24h fill mode for continuous background playback.</p>"
            "<p><b>Series</b> — Add a series/episode tag with season/episode tracking for sequential playback.</p>"
            "<p><b>Multi-Series</b> — Group multiple series into a single contiguous block.</p>"
            "<p><b>Gap</b> — Add a gap-filler tag that fills empty time intervals left after scheduling.</p>"
            "<p><b>Edit / Delete</b> — Modify or remove the selected tag.</p>"
            "<hr>"
            "<h3>Save/Load</h3>"
            "<p><b>Save All / Load All</b> — Persist or restore all tags to/from an INI file.</p>"
            "<p><b>Save Tag / Load Tag</b> — Save/load a single selected tag.</p>"
            "<p><b>Config</b> — Global configuration settings.</p>"
            "<hr>"
            "<h3>Preview Panel (Right)</h3>"
            "<p><b>Daily / Weekly / Calendar</b> — Switch between 1-day, 7-day, or 30-day schedule views.</p>"
            "<p><b>Profile</b> — Select a saved schedule profile.</p>"
            "<p><b>Video Order</b> — Random shuffle or Movie Sequence mode.</p>"
            "<p><b>Copy</b> — Copy the schedule preview to clipboard.</p>"
            "<p><b>Generate</b> — Generate the schedule preview.</p>"
            "<p><b>Save Schedule</b> — Export the generated schedule to a JSON file.</p>"
            "<p><b>Inspect</b> — Browse and preview a saved schedule file.</p>"
            "<p><b>Debug</b> — Compare video durations between schedule and collection data.</p>"
            "<hr>"
            "<h3>Approximate Mode</h3>"
            "<p>When <b>Approximate OFF</b> is toggled to <b>ON</b>, the scheduler applies an algorithm to integrate custom/series tags with random fill seamlessly.</p>"
            "<p><b>Algorithm modes:</b></p>"
            "<ul>"
            "<li><b>Linear</b> — Place tags at exact requested times, truncating overlapping random fill.</li>"
            "<li><b>Find-Replace</b> — Snap tags to the nearest random entry boundary; overlapping random entries get fragmented.</li>"
            "<li><b>Shift Overlay</b> — Never removes random entries. If a random entry overlaps a tag, the tag shifts to after it and remaining entries shift forward.</li>"
            "<li><b>Early/Late Fill</b> — Place tags early or late in the day, fill remaining space with random content.</li>"
            "<li><b>Priority</b> — Higher-priority tags preempt lower-priority ones.</li>"
            "<li><b>Best Fit</b> — Place each tag at the random slot closest to its desired time.</li>"
            "<li><b>Round Robin</b> — Interleave tag videos with random fill.</li>"
            "<li><b>Linear Spanning</b> — Like Linear but allows tags to span multiple days.</li>"
            "<li><b>Exhaustive</b> — Try all placements and pick the best.</li>"
            "<li><b>No Overlap</b> — Guarantee no overlaps by shifting/resizing tags.</li>"
            "<li><b>Group Approximate</b> — Sort all tags by time and place them sequentially.</li>"
            "</ul>"
            "<p><b>Overlap strategy:</b> Controls how random entries that overlap tag slots are handled (fragment, skip, gap-fill, or compact).</p>"
        )
        text.setWordWrap(True)
        text.setTextFormat(Qt.RichText)
        text.setStyleSheet("font-size: 13pt;")
        scroll = QScrollArea()
        scroll.setWidget(text)
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)
        dialog.exec()

    def open_config(self):
        dialog = ConfigDialog(self)
        dialog.exec()

    def add_custom_tag(self):
        dialog = TagDialog(self)
        if dialog.exec():
            tag = dialog.get_tag()
            self.tag_manager.add_tag(tag)
            self.refresh_tags_list()
            self.refresh_preview()

    def add_random_fill_tag(self):
        dialog = RandomFillDialog(self)
        if dialog.exec():
            tag = dialog.get_tag()
            if tag is None:
                return
            self.tag_manager.add_tag(tag)
            self.refresh_tags_list()
            self.refresh_preview()

    def add_series_tag(self):
        dialog = SeriesDialog(self)
        if dialog.exec():
            tag = dialog.get_tag()
            if tag is None:
                return
            self.tag_manager.add_tag(tag)
            self.refresh_tags_list()
            self.refresh_preview()

    def add_multi_series_tag(self):
        from dialogs import MultiSeriesDialog
        dialog = MultiSeriesDialog(self)
        if dialog.exec():
            tag = dialog.get_tag()
            if tag is None:
                return
            self.tag_manager.add_tag(tag)
            self.refresh_tags_list()
            self.refresh_preview()

    def add_gap_tag(self):
        dialog = GapTagDialog(self)
        if dialog.exec():
            self.tag_manager.add_tag(dialog.get_tag())
            self.refresh_tags_list()
            self.refresh_preview()

    def edit_tag(self):
        items = self.tags_list.selectedItems()
        if not items:
            QMessageBox.warning(self, "No Selection", "Please select at least one tag to edit.")
            return

        for item in items:
            current_row = self.tags_list.row(item)
            tag = self.tag_manager.tags[current_row]
            if tag.is_gap_filler:
                dialog = GapTagDialog(self, tag)
                if dialog.exec():
                    self.tag_manager.tags[current_row] = dialog.get_tag()
                continue
            if tag.is_random_fill:
                dialog = RandomFillDialog(self, tag)
            elif tag.is_series:
                dialog = SeriesDialog(self, tag)
            elif getattr(tag, 'is_multi_series', False):
                from dialogs import MultiSeriesDialog
                dialog = MultiSeriesDialog(self, tag)
                if dialog.exec():
                    new_tag = dialog.get_tag()
                    self.tag_manager.tags[current_row] = new_tag
                continue
            else:
                dialog = TagDialog(self, tag)

            if dialog.exec():
                new_tag = dialog.get_tag()
                self.tag_manager.edit_tag(
                    current_row, new_tag.name,
                    new_tag.start_time, new_tag.end_time,
                    new_tag.collection_videos,
                    new_tag.collection_path,
                    new_tag.video_count,
                    new_tag.is_series,
                    new_tag.start_season,
                    new_tag.start_episode,
                    new_tag.play_mode,
                    new_tag.is_random_fill if hasattr(new_tag, 'is_random_fill') else False,
                    new_tag.blacklist if hasattr(new_tag, 'blacklist') else [],
                    new_tag.blacklist_path if hasattr(new_tag, 'blacklist_path') else '',
                    new_tag.fill_24h if hasattr(new_tag, 'fill_24h') else False,
                    new_tag.collection_profile if hasattr(new_tag, 'collection_profile') else '',
                    new_tag.blacklist_profile if hasattr(new_tag, 'blacklist_profile') else '',
                     new_tag.randomize_videos if hasattr(new_tag, 'randomize_videos') else False,
                    new_tag.series_end_behavior if hasattr(new_tag, 'series_end_behavior') else 'stop',
                    new_tag.series_repeat_season if hasattr(new_tag, 'series_repeat_season') else 0,
                    new_tag.series_random_season if hasattr(new_tag, 'series_random_season') else 0,
                    active_days=new_tag.active_days if hasattr(new_tag, 'active_days') else None,
                    marathon_mode=new_tag.marathon_mode if hasattr(new_tag, 'marathon_mode') else False,
                    marathon_tag_name=new_tag.marathon_tag_name if hasattr(new_tag, 'marathon_tag_name') else '',
                    extra_collections=getattr(new_tag, 'extra_collections', [])
                )
        self.refresh_tags_list()
        self.refresh_preview()

    def delete_tag(self):
        items = self.tags_list.selectedItems()
        if not items:
            QMessageBox.warning(self, "No Selection", "Please select at least one tag to delete.")
            return

        count = len(items)
        msg = "Are you sure you want to delete this tag?" if count == 1 else f"Are you sure you want to delete {count} tags?"
        reply = QMessageBox.question(self, "Confirm Delete", msg)
        if reply == QMessageBox.Yes:
            rows = sorted((self.tags_list.row(item) for item in items), reverse=True)
            for row in rows:
                self.tag_manager.remove_tag(row)
            self.refresh_tags_list()
            self.refresh_preview()

    def copy_preview(self):
        items = []
        for i in range(self.preview_list.topLevelItemCount()):
            self._collect_item_text(self.preview_list.topLevelItem(i), items)
        text = "\n".join(items)
        clipboard = QApplication.instance().clipboard()
        clipboard.setText(text)
        QMessageBox.information(self, "Copied", f"Schedule copied to clipboard ({len(items)} items)!")

    def load_schedule_profiles(self):
        profiles = get_schedule_profiles()
        self.schedule_profile_combo.clear()
        for profile in profiles:
            self.schedule_profile_combo.addItem(profile)

    def save_schedule(self):
        profile_name = self.schedule_profile_combo.currentText().strip()
        if not profile_name:
            QMessageBox.warning(self, "No Profile", "Please select or enter a schedule profile name.")
            return

        import json
        from datetime import date, timedelta

        collection_cache = {}

        def get_collection_info(collection_path):
            if collection_path in collection_cache:
                return collection_cache[collection_path]
            if not Path(collection_path).exists():
                return {}
            try:
                with open(collection_path, 'r') as f:
                    data = json.load(f)
                collections = data.get('collections', [])
                if collections:
                    coll = collections[0]
                    file_stem = Path(collection_path).stem
                    if file_stem.startswith('collections_'):
                        channel = file_stem.replace('collections_', '')
                    else:
                        channel = file_stem
                    info = {
                        'channel': channel,
                        'id': coll.get('id', channel)
                    }
                    collection_cache[collection_path] = info
                    return info
            except Exception:
                pass
            return {}

        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

        schedule_data = {
            "weekly": {},
            "calendar": {}
        }

        def get_schedule_entries_for_day(entries, day_start_seconds: int, day_end_seconds: int):
            schedule_entries = []
            for entry in entries:
                # Only include entries that start within this day's window
                if entry.start_seconds < day_start_seconds or entry.start_seconds >= day_end_seconds:
                    continue
                secs = entry.start_seconds % 86400
                h = secs // 3600
                m = (secs % 3600) // 60
                s = secs % 60
                time_str = f"{h:02d}:{m:02d}:{s:02d}"

                video_name = entry.video_name

                video_info = {'time': time_str, 'collection_id': '', 'channel': '', 'source': 'random'}

                matched = False
                for tag in self.tag_manager.get_all_tags():
                    collection_path = getattr(tag, 'collection_path', '')
                    if collection_path and tag.collection_videos:
                        coll_info = get_collection_info(collection_path)
                        channel = coll_info.get('channel', '')

                        for vid in tag.collection_videos:
                            vid_name = get_video_display_name(vid)
                            if vid_name in video_name or video_name in vid_name:
                                video_info['channel'] = profile_name
                                video_info['collection_id'] = vid.get('collection_id', '')
                                primary_src = Path(collection_path).stem
                                if primary_src.startswith('collections_'):
                                    primary_src = primary_src.replace('collections_', '')
                                vid_src = vid.get('_source_name', '')
                                if vid_src and vid_src != primary_src:
                                    video_info['collection_source'] = vid_src
                                matched = True
                                break
                        if matched:
                            break

                if not matched:
                    for tag in self.tag_manager.get_all_tags():
                        if getattr(tag, 'is_gap_filler', False) and tag.gap_collections:
                            gap_videos = load_gap_collections(tag.gap_collections)
                            for vid in gap_videos:
                                vid_name = get_video_display_name(vid)
                                if vid_name in video_name or video_name in vid_name:
                                    video_info['channel'] = profile_name
                                    video_info['collection_id'] = vid.get('collection_id', '')
                                    video_info['source'] = 'gap'
                                    matched = True
                                    break
                            if matched:
                                break

                schedule_entries.append(video_info)
            return schedule_entries

        start_date = date.today()

        # Determine number of days and key
        if self.weekly_radio.isChecked():
            num_days = 7
            save_key = "weekly"
        elif self.monthly_radio.isChecked():
            num_days = 30
            save_key = "calendar"
        else:
            num_days = 1
            save_key = "calendar"

        # Determine approximate mode if applicable
        mode = None
        if self.approximate_enabled:
            mode = self.approx_mode_combo.currentText().lower().replace("-", "_").replace(" ", "_")

        # Check if we can reuse the last generated schedule (matches current settings)
        reuse = False
        if hasattr(self, 'last_generated_schedule') and self.last_generated_schedule:
            ls = self.last_generated_schedule
            if ls['num_days'] == num_days and ls['approximate_enabled'] == self.approximate_enabled:
                cached_strat = ls.get('overlap_strategy')
                current_strat = self._get_overlap_strategy() if self.approximate_enabled else None
                if not self.approximate_enabled or (self.approximate_enabled and ls['mode'] == mode and cached_strat == current_strat):
                    all_entries = ls['entries']
                    reuse = True

        if not reuse:
            if not self.approximate_enabled:
                all_entries = self.schedule_generator.apply_custom_tags(use_cache=False, num_days=num_days)
            else:
                all_entries = self.schedule_generator.apply_approximate(num_days=num_days, mode=mode, overlap_strategy=self._get_overlap_strategy())
            # Update last_generated_schedule with this fresh generation
            self.last_generated_schedule = {
                'entries': all_entries,
                'num_days': num_days,
                'approximate_enabled': self.approximate_enabled,
                'mode': mode if self.approximate_enabled else None,
                'overlap_strategy': self._get_overlap_strategy() if self.approximate_enabled else None,
            }

        for day_offset in range(num_days):
            current_date = start_date + timedelta(days=day_offset)
            date_str = current_date.strftime("%Y-%m-%d")
            day_name = days[current_date.weekday()]
            key = f"{date_str}_{day_name.lower()}"

            day_start = day_offset * 86400
            day_end = day_start + 86400
            schedule_entries = get_schedule_entries_for_day(all_entries, day_start, day_end)

            schedule_data[save_key][key] = {
                "date": date_str,
                "day": day_name,
                "description": "Auto-generated schedule",
                "entries": schedule_entries
            }

        file_path = f"schedule_{profile_name}.json"

        reply = QMessageBox.question(
            self,
            "Save Schedule",
            f"Save schedule to {file_path}?",
            QMessageBox.Ok | QMessageBox.Cancel,
            QMessageBox.Cancel
        )
        if reply != QMessageBox.Ok:
            return

        with open(file_path, 'w') as f:
            json.dump(schedule_data, f, indent=2)

        QMessageBox.information(self, "Saved", f"Schedule saved to {file_path}")
        self.statusBar().showMessage(f"Schedule saved to {file_path}")

    def inspect_schedule(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Schedule File",
            "",
            "JSON Files (*.json);;All Files (*)"
        )
        if not file_path:
            return

        profile_name = Path(file_path).stem
        if profile_name.startswith("schedule_"):
            profile_name = profile_name[9:]  # Strip "schedule_" prefix

        try:
            with open(file_path, 'r') as f:
                schedule_data = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load schedule file:\n{e}")
            return

        calendar_data = schedule_data.get("calendar", {})
        if not calendar_data:
            QMessageBox.information(self, "Empty Schedule", "No calendar schedule data found in this file.")
            return

        dialog = SchedulePreviewDialog(self, profile_name, calendar_data)
        dialog.exec()


    def run_approximate(self):
        self.approximate_enabled = not self.approximate_enabled
        self.tag_manager.clear_cache()
        self.schedule_generator.video_order_mode = self.video_order_combo.currentText().lower().replace(" ", "_")
        mode = self.approx_mode_combo.currentText().lower().replace("-", "_").replace(" ", "_")
        if self.approximate_enabled:
            self.schedule_entries = self.schedule_generator.apply_approximate(mode=mode, overlap_strategy=self._get_overlap_strategy())
            self.preview_title.setText(f"24-Hour Schedule Preview [APPROXIMATE {mode.upper()}]")
            self.approx_btn.setText("APPROXIMATE ON")
            self.approx_btn.setStyleSheet("background-color: #22c55e; color: white; font-weight: bold; padding: 10px 20px; border-radius: 6px;")
            self.statusBar().showMessage("Approximate: ON")
        else:
            self.schedule_entries = self.schedule_generator.apply_custom_tags()
            self.preview_title.setText("24-Hour Schedule Preview [Approximate OFF]")
            self.approx_btn.setText("Approximate OFF")
            self.approx_btn.setStyleSheet("background-color: #4a4a5e; color: #a0a0b0; font-weight: bold; padding: 10px 20px; border-radius: 6px;")
        self.statusBar().showMessage("Approximate: OFF")
        self._show_issues_in_statusbar(self.schedule_entries)
        self.preview_list.clear()
        self._add_entries_to_tree(self.schedule_entries)
        # Store for save reuse
        self.last_generated_schedule = {
            'entries': self.schedule_entries,
            'num_days': 1,
            'approximate_enabled': self.approximate_enabled,
            'mode': mode if self.approximate_enabled else None,
            'overlap_strategy': self._get_overlap_strategy() if self.approximate_enabled else None,
        }

    def _get_overlap_strategy(self) -> str:
        text = self.overlap_strategy_combo.currentText()
        return {
            "Fragment (current)": "fragment",
            "Skip overlapped": "skip",
            "Gap-fill": "gap_fill",
            "Compact stream": "compact",
        }[text]

    def _on_video_order_changed(self):
        mode_text = self.video_order_combo.currentText().lower().replace(" ", "_")
        self.schedule_generator.video_order_mode = mode_text
        self.tag_manager.clear_cache()
        self.refresh_preview()

    def save_single_tag(self):
        items = self.tags_list.selectedItems()
        if not items:
            QMessageBox.warning(self, "No Selection", "Please select at least one tag to save.")
            return

        from serialization import save_single_tag_to_ini
        for item in items:
            current_row = self.tags_list.row(item)
            tag = self.tag_manager.tags[current_row]
            file_path, _ = QFileDialog.getSaveFileName(self, f"Save Tag - {tag.name}", "", "INI Files (*.ini);;All Files (*)")
            if file_path:
                if not file_path.endswith('.ini'):
                    file_path += '.ini'
                save_single_tag_to_ini(tag, file_path)
                self.statusBar().showMessage(f"Tag saved to {file_path}")

    def load_single_tag(self):
        file_paths, _ = QFileDialog.getOpenFileNames(self, "Load Tags", "", "INI Files (*.ini);;All Files (*)")
        if not file_paths:
            return

        from serialization import load_single_tag_from_ini
        loaded_count = 0
        for file_path in file_paths:
            tag = load_single_tag_from_ini(file_path, Tag, QTime.fromString)
            if tag:
                self.tag_manager.add_tag(tag)
                loaded_count += 1

        if loaded_count > 0:
            self.refresh_tags_list()
            self.refresh_preview()
            self.statusBar().showMessage(f"Loaded {loaded_count} tag(s)")
        else:
            QMessageBox.warning(self, "Error", "Failed to load tags.")


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()