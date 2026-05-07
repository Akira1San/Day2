#!/usr/bin/env python3
import sys
import json
import configparser
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Configure root logger to write to a rotating file
log_path = Path("daypart_scheduler.log")
log_handler = RotatingFileHandler(log_path, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
log_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
logging.getLogger().addHandler(log_handler)
logging.getLogger().setLevel(logging.DEBUG)
# Also echo DEBUG+ to stdout for live monitoring
stdout_handler = logging.StreamHandler(sys.stdout)
stdout_handler.setLevel(logging.DEBUG)
stdout_handler.setFormatter(logging.Formatter('[%(levelname)s] %(name)s: %(message)s'))
logging.getLogger().addHandler(stdout_handler)

from typing import List, Optional
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QListWidgetItem, QPushButton, QDialog, QLineEdit,
    QLabel, QTimeEdit, QMessageBox, QScrollArea, QCheckBox, QRadioButton, QButtonGroup,
    QFileDialog, QSpinBox, QComboBox
)
from PySide6.QtCore import Qt, QTime
from PySide6.QtGui import QClipboard, QFont

from utils import (
    load_collection_json, load_blacklist_json,
    parse_series_episode, parse_videos_for_series,
    get_video_display_name, format_duration, get_config_paths, filter_videos_by_blacklist,
    get_schedule_profiles
)
from models import Tag, ScheduleEntry, TagManager, ScheduleGenerator
from dialogs import TagDialog, RandomFillDialog, SeriesDialog, ConfigDialog, SchedulePreviewDialog


APPROXIMATE_THRESHOLD_MINUTES = 40


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Daypart Scheduler")
        self.resize(1000, 600)
        self.tag_manager = TagManager()
        self.schedule_generator = ScheduleGenerator(self.tag_manager)
        self.schedule_entries: List[ScheduleEntry] = []
        self.approximate_enabled = False
        self.statusBar().showMessage("Approximate: OFF")
        self.setup_ui()
        self.load_default_tags()
        self.refresh_preview()

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)

        self.tags_panel = QWidget()
        self.tags_panel.setFixedWidth(400)
        tags_layout = QVBoxLayout(self.tags_panel)

        tags_title = QLabel("Daypart Tags")
        tags_title.setFont(QFont("", 16, QFont.Bold))
        tags_layout.addWidget(tags_title)

        self.tags_list = QListWidget()
        self.tags_list.setAlternatingRowColors(True)
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
        self.save_btn.setToolTip("Save all tags to tags.ini")
        self.save_btn.clicked.connect(self.save_tags)
        save_load_layout.addWidget(self.save_btn)

        self.load_btn = QPushButton("Load All")
        self.load_btn.setToolTip("Load all tags from tags.ini")
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

        tags_layout.addLayout(save_load_layout)

        main_layout.addWidget(self.tags_panel)

        self.preview_panel = QWidget()
        preview_layout = QVBoxLayout(self.preview_panel)

        self.preview_title = QLabel("24-Hour Schedule Preview")
        self.preview_title.setFont(QFont("", 16, QFont.Bold))
        preview_layout.addWidget(self.preview_title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.preview_list = QListWidget()
        scroll.setWidget(self.preview_list)
        preview_layout.addWidget(scroll)

        bottom_btn_layout = QHBoxLayout()
        
        self.view_group = QButtonGroup(self)
        self.daily_radio = QRadioButton("Daily")
        self.daily_radio.setChecked(True)
        self.weekly_radio = QRadioButton("Weekly (7 days)")
        self.monthly_radio = QRadioButton("Calendar (30 days)")
        self.view_group.addButton(self.daily_radio)
        self.view_group.addButton(self.weekly_radio)
        self.view_group.addButton(self.monthly_radio)
        bottom_btn_layout.addWidget(self.daily_radio)
        bottom_btn_layout.addWidget(self.weekly_radio)
        bottom_btn_layout.addWidget(self.monthly_radio)
        
        self.copy_btn = QPushButton("Copy")
        self.copy_btn.setToolTip("Copy preview to clipboard")
        self.copy_btn.clicked.connect(self.copy_preview)
        bottom_btn_layout.addWidget(self.copy_btn)

        self.generate_btn = QPushButton("Generate")
        self.generate_btn.setToolTip("Generate preview based on radio selection")
        self.generate_btn.clicked.connect(self.generate_new_preview)
        bottom_btn_layout.addWidget(self.generate_btn)

        self.save_schedule_btn = QPushButton("Save Schedule")
        self.save_schedule_btn.setToolTip("Save schedule to file")
        self.save_schedule_btn.clicked.connect(self.save_schedule)
        bottom_btn_layout.addWidget(self.save_schedule_btn)

        self.inspect_btn = QPushButton("Inspect")
        self.inspect_btn.setToolTip("Preview saved schedule in separate window")
        self.inspect_btn.clicked.connect(self.inspect_schedule)
        bottom_btn_layout.addWidget(self.inspect_btn)

        self.schedule_profile_combo = QComboBox()
        self.schedule_profile_combo.setEditable(True)
        self.load_schedule_profiles()
        bottom_btn_layout.addWidget(QLabel("Profile:"))
        bottom_btn_layout.addWidget(self.schedule_profile_combo)

        bottom_btn_layout.addStretch()

        self.approx_mode_combo = QComboBox()
        self.approx_mode_combo.addItems(["Linear", "Find-Replace", "Early Fill", "Late Fill", "Priority", "Best Fit", "Round Robin", "Linear Spanning", "Exhaustive"])
        self.approx_mode_combo.setToolTip("Approximate algorithm mode")
        self.approx_mode_combo.setFixedWidth(120)
        bottom_btn_layout.addWidget(self.approx_mode_combo)

        self.approx_btn = QPushButton("Approximate OFF")
        self.approx_btn.setToolTip("Toggle approximate scheduling mode")
        self.approx_btn.setStyleSheet("background-color: #4a4a5e; color: #a0a0b0; font-weight: bold; padding: 10px 20px; border-radius: 6px;")
        self.approx_btn.clicked.connect(self.run_approximate)
        bottom_btn_layout.addWidget(self.approx_btn)

        preview_layout.addLayout(bottom_btn_layout)

        main_layout.addWidget(self.preview_panel)

        self.apply_styles()

    def apply_styles(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #1e1e2e; }
            QWidget { color: #f8f8f2; }
            QLabel { color: #f8f8f2; }
            QListWidget {
                background-color: #2a2a3e;
                border: 1px solid #3a3a4e;
                border-radius: 6px;
                padding: 8px;
                selection-background-color: #7c3aed;
                show-decoration-selected: 1;
            }
            QListWidget::item {
                padding: 8px;
                margin: 2px;
                border: 1px solid transparent;
            }
            QListWidget::item:selected {
                background-color: #7c3aed;
                border: 2px solid #a78bfa;
                color: white;
            }
            QListWidget::item:hover {
                background-color: #3a3a4e;
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
        """)
        self.tags_list.setSelectionMode(QListWidget.SingleSelection)
        self.tags_list.setFocusPolicy(Qt.StrongFocus)

    def load_default_tags(self):
        self.refresh_tags_list()

    def refresh_tags_list(self):
        self.tags_list.clear()
        for tag in self.tag_manager.tags:
            item = QListWidgetItem(tag.to_display_string())
            self.tags_list.addItem(item)

    def refresh_preview(self):
        self.preview_list.clear()
        if self.approximate_enabled:
            mode = self.approx_mode_combo.currentText().lower().replace("-", "_").replace(" ", "_")
            entries = self.schedule_generator.apply_approximate(mode=mode)
            self.preview_title.setText(f"24-Hour Schedule Preview [APPROXIMATE {mode.upper()}]")
            self.approx_btn.setText("APPROXIMATE ON")
            self.approx_btn.setStyleSheet("background-color: #22c55e; color: white; font-weight: bold; padding: 10px 20px; border-radius: 6px;")
            self.statusBar().showMessage("Approximate: ON")
        else:
            entries = self.schedule_generator.apply_custom_tags()
            self.preview_title.setText("24-Hour Schedule Preview [Approximate OFF]")
            self.approx_btn.setText("Approximate OFF")
            self.approx_btn.setStyleSheet("background-color: #4a4a5e; color: #a0a0b0; font-weight: bold; padding: 10px 20px; border-radius: 6px;")
            self.statusBar().showMessage("Approximate: OFF")
        self.schedule_entries = entries

        for entry in entries:
            self.preview_list.addItem(entry.to_display_string())

    def generate_new_preview(self):
        self.tag_manager.clear_cache()
        
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
        entries = self.schedule_generator.apply_custom_tags(num_days=7) if not self.approximate_enabled else self.schedule_generator.apply_approximate(num_days=7)

        for day_offset in range(7):
            current_date = start_date + __import__('datetime').timedelta(days=day_offset)
            day_name = days[current_date.weekday()]
            self.preview_list.addItem(f"=== {current_date} - {day_name} ===")
            day_start_seconds = day_offset * 86400
            day_end_seconds = day_start_seconds + 86400
            for entry in entries:
                if entry.start_seconds >= day_start_seconds and entry.start_seconds < day_end_seconds:
                    start_h = (entry.start_seconds // 3600) % 24
                    start_m = (entry.start_seconds % 3600) // 60
                    end_h = (entry.end_seconds // 3600) % 24
                    end_m = (entry.end_seconds % 3600) // 60
                    if entry.start_seconds == day_start_seconds:
                        self.preview_list.addItem(f"Day {day_offset + 1}\n{start_h:02d}:{start_m:02d} - {end_h:02d}:{end_m:02d} - {entry.video_name}")
                    else:
                        self.preview_list.addItem(f"{start_h:02d}:{start_m:02d} - {end_h:02d}:{end_m:02d} - {entry.video_name}")

    def generate_monthly_preview(self):
        self.preview_list.clear()
        self.preview_title.setText("Calendar Schedule Preview (30 Days)")

        from datetime import date
        start_date = date.today()
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

        self.tag_manager.clear_cache()
        entries = self.schedule_generator.apply_custom_tags(num_days=30) if not self.approximate_enabled else self.schedule_generator.apply_approximate(num_days=30)

        for day_offset in range(30):
            current_date = start_date + __import__('datetime').timedelta(days=day_offset)
            day_name = days[current_date.weekday()]
            self.preview_list.addItem(f"=== {current_date} - {day_name} ===")
            day_start_seconds = day_offset * 86400
            day_end_seconds = day_start_seconds + 86400
            for entry in entries:
                if entry.start_seconds >= day_start_seconds and entry.start_seconds < day_end_seconds:
                    start_h = (entry.start_seconds // 3600) % 24
                    start_m = (entry.start_seconds % 3600) // 60
                    end_h = (entry.end_seconds // 3600) % 24
                    end_m = (entry.end_seconds % 3600) // 60
                    if entry.start_seconds == day_start_seconds:
                        self.preview_list.addItem(f"Day {day_offset + 1}\n{start_h:02d}:{start_m:02d} - {end_h:02d}:{end_m:02d} - {entry.video_name}")
                    else:
                        self.preview_list.addItem(f"{start_h:02d}:{start_m:02d} - {end_h:02d}:{end_m:02d} - {entry.video_name}")

    def save_tags(self):
        self.tag_manager.save_tags("tags.ini")
        self.statusBar().showMessage("Tags saved to tags.ini")

    def load_tags(self):
        if self.tag_manager.load_tags("tags.ini"):
            self.refresh_tags_list()
            self.refresh_preview()
            self.statusBar().showMessage("Tags loaded from tags.ini")
        else:
            self.statusBar().showMessage("No tags.ini found")

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

    def edit_tag(self):
         current_row = self.tags_list.currentRow()
         if current_row < 0:
             QMessageBox.warning(self, "No Selection", "Please select a tag to edit.")
             return
 
         tag = self.tag_manager.tags[current_row]
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
                 self.refresh_tags_list()
                 self.refresh_preview()
             return
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
                 new_tag.randomize_videos if hasattr(new_tag, 'randomize_videos') else False
             )
             self.refresh_tags_list()
             self.refresh_preview()

    def delete_tag(self):
        current_row = self.tags_list.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "No Selection", "Please select a tag to delete.")
            return

        reply = QMessageBox.question(self, "Confirm Delete", "Are you sure you want to delete this tag?")
        if reply == QMessageBox.Yes:
            self.tag_manager.remove_tag(current_row)
            self.refresh_tags_list()
            self.refresh_preview()

    def copy_preview(self):
        if self.weekly_radio.isChecked() or self.monthly_radio.isChecked():
            items = [self.preview_list.item(i).text() for i in range(self.preview_list.count())]
            text = "\n".join(items)
        else:
            text = "\n".join(entry.to_copy_string() for entry in self.schedule_entries)
        clipboard = QApplication.instance().clipboard()
        clipboard.setText(text)
        QMessageBox.information(self, "Copied", "Schedule copied to clipboard!")

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

                video_info = {'time': time_str, 'file': '', 'collection_id': '', 'channel': '', 'source': 'random'}

                matched = False
                for tag in self.tag_manager.get_all_tags():
                    collection_path = getattr(tag, 'collection_path', '')
                    if collection_path and tag.collection_videos:
                        coll_info = get_collection_info(collection_path)
                        channel = coll_info.get('channel', '')

                        for vid in tag.collection_videos:
                            vid_name = get_video_display_name(vid)
                            if vid_name in video_name or video_name in vid_name:
                                video_info['file'] = vid.get('path', '')
                                video_info['channel'] = profile_name
                                video_info['collection_id'] = vid.get('collection_id', '')
                                matched = True
                                break
                        if matched:
                            break

                if not video_info['file'] and ' - ' in video_name:
                    parts = video_name.split(' - ')
                    video_info['file'] = f"/home/akira/Videos/Akiratv/{parts[-1].strip()}"
                    video_info['channel'] = profile_name
                    video_info['collection_id'] = profile_name

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

        # Always regenerate full schedule for save to include all days (bypass preview cache)
        if not self.approximate_enabled:
            all_entries = self.schedule_generator.apply_custom_tags(use_cache=False, num_days=num_days)
        else:
            mode = self.approx_mode_combo.currentText().lower().replace("-", "_").replace(" ", "_")
            all_entries = self.schedule_generator.apply_approximate(num_days=num_days, mode=mode)

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
        with open(file_path, 'w') as f:
            json.dump(schedule_data, f, indent=2)

        QMessageBox.information(self, "Saved", f"Schedule saved to {file_path}")
        self.statusBar().showMessage(f"Schedule saved to {file_path}")

    def inspect_schedule(self):
        profile_name = self.schedule_profile_combo.currentText().strip()
        if not profile_name:
            QMessageBox.warning(self, "No Profile", "Please select or enter a schedule profile name.")
            return

        file_path = f"schedule_{profile_name}.json"
        if not Path(file_path).exists():
            QMessageBox.warning(self, "File Not Found", f"Schedule file '{file_path}' not found.\n\nSave the schedule first using 'Save Schedule'.")
            return

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
        mode = self.approx_mode_combo.currentText().lower().replace("-", "_").replace(" ", "_")
        if self.approximate_enabled:
            self.schedule_entries = self.schedule_generator.apply_approximate(mode=mode)
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
        self.preview_list.clear()
        for entry in self.schedule_entries:
            self.preview_list.addItem(entry.to_display_string())

    def save_single_tag(self):
        current_row = self.tags_list.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "No Selection", "Please select a tag to save.")
            return

        tag = self.tag_manager.tags[current_row]
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Tag", "", "INI Files (*.ini);;All Files (*)")
        if file_path:
            from serialization import save_single_tag_to_ini
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