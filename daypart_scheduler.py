#!/usr/bin/env python3
import sys
import random
import configparser
from datetime import datetime, timedelta
from typing import List, Optional
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QListWidgetItem, QPushButton, QDialog, QLineEdit,
    QLabel, QTimeEdit, QMessageBox, QScrollArea, QCheckBox
)
from PySide6.QtCore import Qt, QTime, QTimer
from PySide6.QtGui import QClipboard, QColor, QFont


VIDEOS = [
    "Superman", "Batman", "Spiderman", "Wonder Woman", "Iron Man",
    "Thor", "Hulk", "Captain America", "Black Panther", "Aquaman",
    "Flash", "Green Lantern", "Cyborg", "Supergirl", "Batgirl",
    "Robin", "Nightwing", "Joker", "Loki", "Thanos",
    "Doctor Strange", "Scarlet Witch", "Ant-Man", "Wonder Man"
]

APPROXIMATE_THRESHOLD_MINUTES = 40


class Tag:
    def __init__(self, tag_type: str, name: str = "Random Fill",
                 start_time: Optional[QTime] = None,
                 end_time: Optional[QTime] = None):
        self.tag_type = tag_type
        self.name = name
        self.start_time = start_time or QTime(0, 0)
        self.end_time = end_time or QTime(0, 0)
        self.is_random_fill = False

    def to_display_string(self) -> str:
        if self.tag_type == "random":
            return f"[R] {self.name}"
        if self.is_random_fill:
            return f"[R] {self.name} ({self.start_time.toString('HH:mm')}-{self.end_time.toString('HH:mm')})"
        return f"[C] {self.name} ({self.start_time.toString('HH:mm')}-{self.end_time.toString('HH:mm')})"

    def minutes_from_midnight(self, qtime: QTime) -> int:
        return qtime.hour() * 60 + qtime.minute()

    @staticmethod
    def qtime_to_minutes(qtime: QTime) -> int:
        return qtime.hour() * 60 + qtime.minute()


class ScheduleEntry:
    def __init__(self, day: int, start_minutes: int, end_minutes: int, video_name: str):
        self.day = day
        self.start_minutes = start_minutes
        self.end_minutes = end_minutes
        self.video_name = video_name

    def format_time(self, minutes: int, day: int) -> str:
        hours = (minutes // 60) % 24
        mins = minutes % 60
        return f"Day {day} {hours:02d}:{mins:02d}"

    def to_display_string(self) -> str:
        return f"{self.format_time(self.start_minutes, self.day)} - {self.format_time(self.end_minutes, self.day)} - {self.video_name}"

    def to_copy_string(self) -> str:
        return f"{self.format_time(self.start_minutes, self.day)} - {self.format_time(self.end_minutes, self.day)} - {self.video_name}"


class TagManager:
    def __init__(self):
        self.tags: List[Tag] = []
        self.videos = VIDEOS.copy()
        random.shuffle(self.videos)
        self._cached_random_entries: Optional[List[ScheduleEntry]] = None

    def get_cached_random_entries(self) -> List[ScheduleEntry]:
        if self._cached_random_entries is None:
            return None
        return self._cached_random_entries

    def set_cached_random_entries(self, entries: List[ScheduleEntry]):
        self._cached_random_entries = entries

    def clear_cache(self):
        self._cached_random_entries = None

    def shuffle_videos(self):
        random.shuffle(self.videos)

    def save_tags(self, filepath: str = "tags.ini"):
        config = configparser.ConfigParser()
        config['Tags'] = {}
        for i, tag in enumerate(self.tags):
            key = f"tag{i}"
            is_random = "1" if getattr(tag, 'is_random_fill', False) else "0"
            config['Tags'][key] = f"{tag.tag_type}|{tag.name}|{tag.start_time.toString('HH:mm')}|{tag.end_time.toString('HH:mm')}|{is_random}"
        with open(filepath, 'w') as f:
            config.write(f)

    def load_tags(self, filepath: str = "tags.ini"):
        if not Path(filepath).exists():
            return False
        config = configparser.ConfigParser()
        config.read(filepath)
        if 'Tags' not in config:
            return False
        self.tags.clear()
        for key in config['Tags']:
            parts = config['Tags'][key].split('|')
            if len(parts) >= 4:
                tag_type, name, start, end = parts[0], parts[1], parts[2], parts[3]
                is_random_fill = len(parts) == 5 and parts[4] == "1"
                if tag_type == 'random' or is_random_fill:
                    tag = Tag('random', name, QTime.fromString(start, 'HH:mm'), QTime.fromString(end, 'HH:mm'))
                    tag.is_random_fill = is_random_fill
                    self.tags.append(tag)
                else:
                    self.tags.append(Tag('custom', name, QTime.fromString(start, 'HH:mm'), QTime.fromString(end, 'HH:mm')))
        return True

    def add_tag(self, tag: Tag):
        self.tags.append(tag)

    def remove_tag(self, index: int):
        if index >= 0 and index < len(self.tags):
            if self.tags[index].tag_type == "random":
                return False
            self.tags.pop(index)
            return True
        return False

    def edit_tag(self, index: int, name: str, start_time: QTime, end_time: QTime):
        if index >= 0 and index < len(self.tags):
            self.tags[index].name = name
            self.tags[index].start_time = start_time
            self.tags[index].end_time = end_time
            return True
        return False

    def get_custom_tags(self) -> List[Tag]:
        return [t for t in self.tags if t.tag_type == "custom"]

    def get_random_tags(self) -> List[Tag]:
        return [t for t in self.tags if t.tag_type == "random" or t.is_random_fill]

    def get_all_tags(self) -> List[Tag]:
        return list(self.tags)


class ScheduleGenerator:
    def __init__(self, tag_manager: TagManager):
        self.tag_manager = tag_manager

    def generate_random_fill(self, remaining_minutes: int = 24 * 60) -> List[ScheduleEntry]:
        entries = []
        videos = self.tag_manager.videos.copy()
        random.shuffle(videos)
        video_index = 0
        current_minute = 0
        current_day = 1

        while current_minute < remaining_minutes:
            video_name = videos[video_index % len(videos)]
            duration = 90
            end_minute = current_minute + duration

            if end_minute > remaining_minutes:
                end_minute = remaining_minutes

            entries.append(ScheduleEntry(current_day, current_minute, end_minute, video_name))
            current_minute = end_minute
            video_index += 1

        return entries

    def apply_custom_tags(self, use_cache: bool = True) -> List[ScheduleEntry]:
        cached = self.tag_manager.get_cached_random_entries()
        if use_cache and cached is not None:
            return self._inject_custom_tags(cached)

        all_tags = self.tag_manager.get_all_tags()
        custom_tags = [t for t in all_tags if t.tag_type == "custom"]
        random_fill_tags = [t for t in all_tags if t.tag_type == "random" or t.is_random_fill]

        if not custom_tags and not random_fill_tags:
            entries = self.generate_random_fill(24 * 60)
            self.tag_manager.set_cached_random_entries(entries)
            return entries

        custom_sorted = sorted(custom_tags + random_fill_tags, key=lambda t: Tag.qtime_to_minutes(t.start_time))

        custom_entries = []
        occupied = set()
        for ct in custom_sorted:
            start_min = Tag.qtime_to_minutes(ct.start_time)
            end_min = Tag.qtime_to_minutes(ct.end_time)
            if start_min >= end_min:
                continue
            if start_min < 24 * 60 and end_min <= 24 * 60:
                custom_entries.append((start_min, end_min, ct.name))
                for m in range(start_min, end_min):
                    occupied.add(m)

        gaps = []
        current = 0
        for start, end, name in custom_entries:
            if current < start:
                gaps.append((current, start))
            current = end
        if current < 24 * 60:
            gaps.append((current, 24 * 60))

        entries = []
        videos = self.tag_manager.videos.copy()
        video_idx = 0

        for gap_start, gap_end in gaps:
            pos = gap_start
            while pos < gap_end:
                gap_size = gap_end - pos
                video = videos[video_idx % len(videos)]
                if gap_size >= 90:
                    e_end = pos + 90
                else:
                    e_end = pos + gap_size
                entries.append(ScheduleEntry(1, pos, e_end, video))
                pos = e_end
                video_idx += 1
                if video_idx > len(videos) * 2:
                    break

        for start, end, name in custom_entries:
            entries.append(ScheduleEntry(1, start, end, name))

        entries.sort(key=lambda e: e.start_minutes)
        self.tag_manager.set_cached_random_entries(entries)
        return entries

    def _inject_custom_tags(self, random_entries: List[ScheduleEntry]) -> List[ScheduleEntry]:
        custom_tags = self.tag_manager.get_custom_tags()
        if not custom_tags:
            return list(random_entries)

        final = []
        rand_idx = 0
        custom_sorted = sorted(custom_tags, key=lambda t: Tag.qtime_to_minutes(t.start_time))

        for ct in custom_sorted:
            start = Tag.qtime_to_minutes(ct.start_time)
            end = Tag.qtime_to_minutes(ct.end_time)
            if start >= end or start >= 24 * 60:
                continue

            while rand_idx < len(random_entries) and random_entries[rand_idx].end_minutes <= start:
                final.append(random_entries[rand_idx])
                rand_idx += 1

            if rand_idx < len(random_entries) and random_entries[rand_idx].start_minutes < start:
                final.append(random_entries[rand_idx])
                rand_idx += 1

            final.append(ScheduleEntry(1, start, end, ct.name))

            while rand_idx < len(random_entries) and random_entries[rand_idx].start_minutes < end:
                rand_idx += 1

        while rand_idx < len(random_entries):
            final.append(random_entries[rand_idx])
            rand_idx += 1

        final.sort(key=lambda e: e.start_minutes)
        return final

    def apply_approximate(self) -> List[ScheduleEntry]:
        base_entries = self.generate_random_fill(24 * 60)

        custom_tags = self.tag_manager.get_custom_tags()
        if not custom_tags:
            return base_entries

        custom_sorted = sorted(custom_tags, key=lambda t: Tag.qtime_to_minutes(t.start_time))

        final = []
        rand_idx = 0
        current_pos = 0
        next_custom_pos = 0

        for ct in custom_sorted:
            original_start = Tag.qtime_to_minutes(ct.start_time)
            original_end = Tag.qtime_to_minutes(ct.end_time)

            custom_start = max(original_start, next_custom_pos)
            custom_end = custom_start + (original_end - original_start)

            while current_pos < custom_start and rand_idx < len(base_entries):
                dur = min(90, base_entries[rand_idx].end_minutes - base_entries[rand_idx].start_minutes)
                final.append(ScheduleEntry(1, current_pos, current_pos + dur, base_entries[rand_idx].video_name))
                current_pos += dur
                rand_idx += 1

            if rand_idx < len(base_entries) and base_entries[rand_idx].start_minutes < original_start < base_entries[rand_idx].end_minutes:
                dur = base_entries[rand_idx].end_minutes - base_entries[rand_idx].start_minutes
                final.append(ScheduleEntry(1, current_pos, current_pos + dur, base_entries[rand_idx].video_name))
                current_pos += dur
                rand_idx += 1
                
                custom_start = current_pos
                custom_end = custom_start + (original_end - original_start)
                final.append(ScheduleEntry(1, custom_start, custom_end, ct.name))
                current_pos = custom_end
            else:
                if custom_start < current_pos:
                    custom_start = current_pos
                    custom_end = custom_start + (original_end - original_start)
                final.append(ScheduleEntry(1, custom_start, custom_end, ct.name))
                current_pos = custom_end

            next_custom_pos = current_pos

            while rand_idx < len(base_entries) and base_entries[rand_idx].start_minutes < current_pos:
                rand_idx += 1

        while rand_idx < len(base_entries):
            dur = base_entries[rand_idx].end_minutes - base_entries[rand_idx].start_minutes
            if current_pos + dur <= 24 * 60:
                final.append(ScheduleEntry(1, current_pos, current_pos + dur, base_entries[rand_idx].video_name))
                current_pos += dur
            rand_idx += 1

        final.sort(key=lambda e: e.start_minutes)
        return final

class TagDialog(QDialog):
    def __init__(self, parent=None, tag: Optional[Tag] = None):
        super().__init__(parent)
        self.setWindowTitle("Edit Tag" if tag else "Add Custom Tag")
        self.setModal(True)
        self.setup_ui()
        if tag:
            self.name_input.setText(tag.name)
            self.start_time_edit.setTime(tag.start_time)
            self.end_time_edit.setTime(tag.end_time)
            if hasattr(tag, 'is_random_fill') and tag.is_random_fill:
                self.random_fill_check.setChecked(True)

    def setup_ui(self):
        layout = QVBoxLayout(self)

        self.random_fill_check = QCheckBox("Random Fill (auto-generate videos)")
        self.random_fill_check.stateChanged.connect(self.on_random_fill_changed)
        layout.addWidget(self.random_fill_check)

        layout.addWidget(QLabel("Video Name:"))
        self.name_input = QLineEdit()
        layout.addWidget(self.name_input)

        layout.addWidget(QLabel("Start Time:"))
        self.start_time_edit = QTimeEdit()
        self.start_time_edit.setDisplayFormat("HH:mm")
        self.start_time_edit.setTime(QTime(0, 0))
        layout.addWidget(self.start_time_edit)

        layout.addWidget(QLabel("End Time:"))
        self.end_time_edit = QTimeEdit()
        self.end_time_edit.setDisplayFormat("HH:mm")
        self.end_time_edit.setTime(QTime(1, 0))
        layout.addWidget(self.end_time_edit)

        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def get_tag(self) -> Tag:
        is_random = self.random_fill_check.isChecked()
        if is_random:
            tag = Tag(
                tag_type="random",
                name="Random Fill" if not self.name_input.text() else self.name_input.text(),
                start_time=self.start_time_edit.time(),
                end_time=self.end_time_edit.time()
            )
            tag.is_random_fill = True
        else:
            tag = Tag(
                tag_type="custom",
                name=self.name_input.text() or "Custom Video",
                start_time=self.start_time_edit.time(),
                end_time=self.end_time_edit.time()
            )
        return tag

    def on_random_fill_changed(self, state):
        if state == Qt.Checked:
            self.name_input.setEnabled(False)
        else:
            self.name_input.setEnabled(True)


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
        self.tags_panel.setFixedWidth(350)
        tags_layout = QVBoxLayout(self.tags_panel)

        tags_title = QLabel("Daypart Tags")
        tags_title.setFont(QFont("", 16, QFont.Bold))
        tags_layout.addWidget(tags_title)

        self.tags_list = QListWidget()
        self.tags_list.setAlternatingRowColors(True)
        tags_layout.addWidget(self.tags_list)

        btn_layout = QHBoxLayout()
        self.add_btn = QPushButton("Add")
        self.add_btn.clicked.connect(self.add_tag)
        btn_layout.addWidget(self.add_btn)

        self.edit_btn = QPushButton("Edit")
        self.edit_btn.clicked.connect(self.edit_tag)
        btn_layout.addWidget(self.edit_btn)

        self.delete_btn = QPushButton("Delete")
        self.delete_btn.clicked.connect(self.delete_tag)
        btn_layout.addWidget(self.delete_btn)

        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self.save_tags)
        btn_layout.addWidget(self.save_btn)

        self.load_btn = QPushButton("Load")
        self.load_btn.clicked.connect(self.load_tags)
        btn_layout.addWidget(self.load_btn)

        tags_layout.addLayout(btn_layout)

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
        self.copy_btn = QPushButton("Copy Preview")
        self.copy_btn.clicked.connect(self.copy_preview)
        bottom_btn_layout.addWidget(self.copy_btn)

        self.generate_btn = QPushButton("Generate Preview")
        self.generate_btn.clicked.connect(self.generate_new_preview)
        bottom_btn_layout.addWidget(self.generate_btn)

        bottom_btn_layout.addStretch()

        self.approx_btn = QPushButton("Approximate OFF")
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
            }
            QListWidget::item { padding: 8px; margin: 2px; }
            QListWidget::item:selected { background-color: #7c3aed; }
            QListWidget::item:hover { background-color: #3a3a4e; }
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

    def load_default_tags(self):
        random_tag = Tag(tag_type="random", name="Random Fill")
        self.tag_manager.add_tag(random_tag)

        custom_tag = Tag(
            tag_type="custom",
            name="My Custom Video",
            start_time=QTime(13, 0),
            end_time=QTime(15, 0)
        )
        self.tag_manager.add_tag(custom_tag)

        self.refresh_tags_list()

    def refresh_tags_list(self):
        self.tags_list.clear()
        for tag in self.tag_manager.tags:
            item = QListWidgetItem(tag.to_display_string())
            if tag.tag_type == "random":
                item.setBackground(QColor("#3a3a4e"))
            self.tags_list.addItem(item)

    def refresh_preview(self):
        self.preview_list.clear()
        if self.approximate_enabled:
            entries = self.schedule_generator.apply_approximate()
            self.preview_title.setText("24-Hour Schedule Preview [APPROXIMATE ON]")
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
        self.tag_manager.shuffle_videos()
        self.refresh_preview()

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

    def add_tag(self):
        dialog = TagDialog(self)
        if dialog.exec():
            tag = dialog.get_tag()
            self.tag_manager.add_tag(tag)
            self.refresh_tags_list()
            self.refresh_preview()

    def edit_tag(self):
        current_row = self.tags_list.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "No Selection", "Please select a tag to edit.")
            return

        tag = self.tag_manager.tags[current_row]
        if tag.tag_type == "random":
            QMessageBox.warning(self, "Cannot Edit", "Cannot edit the random fill tag.")
            return

        dialog = TagDialog(self, tag)
        if dialog.exec():
            new_tag = dialog.get_tag()
            self.tag_manager.edit_tag(current_row, new_tag.name,
                                      new_tag.start_time, new_tag.end_time)
            self.refresh_tags_list()
            self.refresh_preview()

    def delete_tag(self):
        current_row = self.tags_list.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "No Selection", "Please select a tag to delete.")
            return

        tag = self.tag_manager.tags[current_row]
        if tag.tag_type == "random":
            QMessageBox.warning(self, "Cannot Delete", "Cannot delete the random fill tag.")
            return

        reply = QMessageBox.question(self, "Confirm Delete",
                                 "Are you sure you want to delete this tag?")
        if reply == QMessageBox.Yes:
            self.tag_manager.remove_tag(current_row)
            self.refresh_tags_list()
            self.refresh_preview()

    def copy_preview(self):
        text = "\n".join(entry.to_copy_string() for entry in self.schedule_entries)
        clipboard = QApplication.instance().clipboard()
        clipboard.setText(text)
        QMessageBox.information(self, "Copied", "Schedule copied to clipboard!")

    def run_approximate(self):
        self.approximate_enabled = not self.approximate_enabled
        self.tag_manager.clear_cache()
        if self.approximate_enabled:
            self.schedule_entries = self.schedule_generator.apply_approximate()
            self.preview_title.setText("24-Hour Schedule Preview [APPROXIMATE ON]")
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


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()