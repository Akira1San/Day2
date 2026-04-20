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
    QLabel, QTimeEdit, QMessageBox, QScrollArea, QCheckBox, QRadioButton, QButtonGroup,
    QFileDialog, QSpinBox
)
from PySide6.QtCore import Qt, QTime, QTimer
from PySide6.QtGui import QClipboard, QColor, QFont


APPROXIMATE_THRESHOLD_MINUTES = 40


class Tag:
    def __init__(self, tag_type: str, name: str = "Random Fill",
                 start_time: Optional[QTime] = None,
                 end_time: Optional[QTime] = None,
                 collection_videos: Optional[List[dict]] = None,
                 collection_path: str = "",
                 randomize_videos: bool = False,
                 video_count: int = 1,
                 is_random_fill: bool = False,
                 blacklist: List[dict] = None,
                 blacklist_path: str = ""):
        self.tag_type = tag_type
        self.name = name
        self.start_time = start_time or QTime(0, 0)
        self.end_time = end_time or QTime(0, 0)
        self.is_random_fill = is_random_fill
        self.collection_videos = collection_videos or []
        self.collection_path = collection_path
        self.randomize_videos = randomize_videos
        self.video_count = video_count
        self.blacklist = blacklist or []
        self.blacklist_path = blacklist_path

    def to_display_string(self) -> str:
        if self.tag_type == "random":
            return f"[R] {self.name}"
        if self.is_random_fill:
            return f"[R] {self.name} ({self.start_time.toString('HH:mm')}-{self.end_time.toString('HH:mm')})"
        if self.randomize_videos:
            return f"[C] {self.name} ({self.start_time.toString('HH:mm')}-{self.end_time.toString('HH:mm')}) x{self.video_count}"
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
        return f"Day {day}\n{hours:02d}:{mins:02d}"

    def to_display_string(self) -> str:
        start_h = (self.start_minutes // 60) % 24
        start_m = self.start_minutes % 60
        end_h = (self.end_minutes // 60) % 24
        end_m = self.end_minutes % 60
        if self.start_minutes == 0:
            return f"Day {self.day}\n{start_h:02d}:{start_m:02d} - {end_h:02d}:{end_m:02d} - {self.video_name}"
        return f"{start_h:02d}:{start_m:02d} - {end_h:02d}:{end_m:02d} - {self.video_name}"

    def to_copy_string(self) -> str:
        start_h = (self.start_minutes // 60) % 24
        start_m = self.start_minutes % 60
        end_h = (self.end_minutes // 60) % 24
        end_m = self.end_minutes % 60
        return f"Day {self.day} {start_h:02d}:{start_m:02d} - Day {self.day} {end_h:02d}:{end_m:02d} - {self.video_name}"


class TagManager:
    def __init__(self):
        self.tags: List[Tag] = []
        self._cached_random_entries: Optional[List[ScheduleEntry]] = None

    def get_cached_random_entries(self) -> List[ScheduleEntry]:
        if self._cached_random_entries is None:
            return None
        return self._cached_random_entries

    def set_cached_random_entries(self, entries: List[ScheduleEntry]):
        self._cached_random_entries = entries

    def clear_cache(self):
        self._cached_random_entries = None

    def save_tags(self, filepath: str = "tags.ini"):
        import json
        config = configparser.ConfigParser()
        config['Tags'] = {}
        for i, tag in enumerate(self.tags):
            key = f"tag{i}"
            is_random = "1" if getattr(tag, 'is_random_fill', False) else "0"
            randomize = "1" if getattr(tag, 'randomize_videos', False) else "0"
            video_count = str(getattr(tag, 'video_count', 1))
            collection_path = getattr(tag, 'collection_path', '')
            videos_json = json.dumps(tag.collection_videos) if tag.collection_videos else ""
            config['Tags'][key] = f"{tag.tag_type}|{tag.name}|{tag.start_time.toString('HH:mm')}|{tag.end_time.toString('HH:mm')}|{is_random}|{randomize}|{video_count}|{collection_path}|{videos_json}"
        with open(filepath, 'w') as f:
            config.write(f)

    def load_tags(self, filepath: str = "tags.ini"):
        import json
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
                is_random_fill = len(parts) >= 5 and parts[4] == "1"
                randomize_videos = len(parts) >= 6 and parts[5] == "1"
                video_count = int(parts[6]) if len(parts) >= 7 and parts[6].isdigit() else 1
                collection_path = parts[7] if len(parts) >= 8 else ""
                collection_videos = []
                if len(parts) >= 9 and parts[8]:
                    try:
                        collection_videos = json.loads(parts[8])
                    except:
                        collection_videos = []
                if tag_type == 'random' or is_random_fill:
                    tag = Tag('random', name, QTime.fromString(start, 'HH:mm'), QTime.fromString(end, 'HH:mm'), collection_videos, collection_path, randomize_videos, video_count)
                    tag.is_random_fill = is_random_fill
                    self.tags.append(tag)
                else:
                    self.tags.append(Tag('custom', name, QTime.fromString(start, 'HH:mm'), QTime.fromString(end, 'HH:mm'), collection_videos, collection_path, randomize_videos, video_count))
        return True

    def add_tag(self, tag: Tag):
        self.tags.append(tag)

    def remove_tag(self, index: int):
        if index >= 0 and index < len(self.tags):
            self.tags.pop(index)
            return True
        return False

    def edit_tag(self, index: int, name: str, start_time: QTime, end_time: QTime,
                 collection_videos: List[dict] = None, collection_path: str = "",
                 video_count: int = 1):
        if index >= 0 and index < len(self.tags):
            self.tags[index].name = name
            self.tags[index].start_time = start_time
            self.tags[index].end_time = end_time
            self.tags[index].collection_videos = collection_videos or []
            self.tags[index].collection_path = collection_path
            self.tags[index].video_count = video_count
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
        all_tags = self.tag_manager.get_all_tags()
        collection_videos = []
        for tag in all_tags:
            if tag.collection_videos:
                collection_videos.extend(tag.collection_videos)
        
        if not collection_videos:
            return []
        
        entries = []
        random.shuffle(collection_videos)
        video_index = 0
        current_minute = 0
        current_day = 1

        while current_minute < remaining_minutes:
            video = collection_videos[video_index % len(collection_videos)]
            video_name = video.get('path', 'Unknown').split('/')[-1]
            duration = int(video.get('duration', 90)) // 60
            if duration < 1:
                duration = 90
            end_minute = current_minute + duration

            if end_minute > remaining_minutes:
                end_minute = remaining_minutes

            entries.append(ScheduleEntry(current_day, current_minute, end_minute, video_name))
            current_minute = end_minute
            video_index += 1

        return entries

    def apply_custom_tags(self, use_cache: bool = True) -> List[ScheduleEntry]:
        all_tags = self.tag_manager.get_all_tags()
        
        cached = self.tag_manager.get_cached_random_entries()
        if use_cache and cached is not None:
            return self._inject_custom_tags(cached)

        custom_tags = [t for t in all_tags if t.tag_type == "custom"]
        random_fill_tags = [t for t in all_tags if t.tag_type == "random" or t.is_random_fill]

        collection_videos = []
        for tag in all_tags:
            if tag.collection_videos:
                collection_videos.extend(tag.collection_videos)

        if not custom_tags and not random_fill_tags:
            entries = self.generate_random_fill(24 * 60)
            self.tag_manager.set_cached_random_entries(entries)
            return entries

        custom_sorted = sorted(custom_tags + random_fill_tags, key=lambda t: Tag.qtime_to_minutes(t.start_time))
        
        occupied = set()
        custom_entries = []
        random_videos_entries = []
        
        for ct in custom_sorted:
            start_min = Tag.qtime_to_minutes(ct.start_time)
            end_min = Tag.qtime_to_minutes(ct.end_time)
            if start_min >= end_min:
                continue
            if start_min >= 24 * 60 or end_min > 24 * 60:
                continue
                
            if ct.collection_videos:
                for m in range(start_min, end_min):
                    occupied.add(m)
                video_count = getattr(ct, 'video_count', 1)
                videos = ct.collection_videos.copy()
                random.shuffle(videos)
                pos = start_min
                vid_idx = 0
                while pos < end_min and vid_idx < video_count and vid_idx < len(videos):
                    video = videos[vid_idx % len(videos)]
                    video_name = video.get('path', 'Unknown').split('/')[-1]
                    duration = int(video.get('duration', 90)) // 60
                    if duration < 1:
                        duration = 1
                    if pos + duration > end_min:
                        duration = end_min - pos
                    if duration < 1:
                        break
                    random_videos_entries.append((pos, pos + duration, video_name))
                    pos += duration
                    vid_idx += 1
            else:
                custom_entries.append((start_min, end_min, ct.name))
                for m in range(start_min, end_min):
                    occupied.add(m)

        gaps = []
        current = 0
        if not custom_entries and not random_videos_entries:
            gaps.append((0, 24 * 60))
        else:
            for start, end, name in custom_entries:
                if current < start:
                    gaps.append((current, start))
                current = end
            for start, end, name in random_videos_entries:
                if current < start:
                    gaps.append((current, start))
                current = end
            if current < 24 * 60:
                gaps.append((current, 24 * 60))

        entries = []
        if collection_videos:
            random.shuffle(collection_videos)
        video_idx = 0

        for gap_start, gap_end in gaps:
            pos = gap_start
            while pos < gap_end:
                gap_size = gap_end - pos
                if collection_videos:
                    video = collection_videos[video_idx % len(collection_videos)]
                    video_name = video.get('path', 'Unknown').split('/')[-1]
                    duration = int(video.get('duration', 90)) // 60
                    if duration < 1:
                        duration = 90
                else:
                    video_name = "No videos loaded"
                    duration = 90
                if gap_size >= duration:
                    e_end = pos + duration
                else:
                    e_end = pos + gap_size
                    duration = gap_size
                entries.append(ScheduleEntry(1, pos, e_end, video_name))
                pos = e_end
                video_idx += 1
                if collection_videos and video_idx > len(collection_videos) * 2:
                    break

        for start, end, name in custom_entries:
            entries.append(ScheduleEntry(1, start, end, name))

        for start, end, name in random_videos_entries:
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

            if ct.collection_videos and getattr(ct, 'randomize_videos', False):
                video_count = getattr(ct, 'video_count', 1)
                videos = ct.collection_videos.copy()
                random.shuffle(videos)
                pos = start
                vid_idx = 0
                while pos < end and vid_idx < video_count and vid_idx < len(videos):
                    video = videos[vid_idx % len(videos)]
                    video_name = video.get('path', 'Unknown').split('/')[-1]
                    duration = int(video.get('duration', 90)) // 60
                    if duration < 1:
                        duration = 1
                    if pos + duration > end:
                        duration = end - pos
                    if duration < 1:
                        break
                    final.append(ScheduleEntry(1, pos, pos + duration, video_name))
                    pos += duration
                    vid_idx += 1
            else:
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
        self.collection_videos = []
        self.setup_ui()
        if tag:
            self.name_input.setText(tag.name)
            self.start_time_edit.setTime(tag.start_time)
            self.end_time_edit.setTime(tag.end_time)
            if tag.collection_videos:
                self.collection_videos = tag.collection_videos.copy()
                for video in self.collection_videos:
                    path = video.get('path', '')
                    duration = video.get('duration', 0)
                    display_name = path.split('/')[-1] if '/' in path else path
                    self.videos_list.addItem(f"{display_name} ({int(duration)}s)")
            if hasattr(tag, 'randomize_videos') and tag.randomize_videos:
                self.randomize_videos_check.setChecked(True)
            if hasattr(tag, 'video_count'):
                self.video_count_spin.setValue(tag.video_count)
            if hasattr(tag, 'collection_path') and tag.collection_path:
                self.collection_path.setText(tag.collection_path)
                if tag.collection_videos:
                    self.videos_list.clear()
                    self.collection_videos = tag.collection_videos.copy()
                    for video in self.collection_videos:
                        path = video.get('path', '')
                        duration = video.get('duration', 0)
                        display_name = path.split('/')[-1] if '/' in path else path
                        self.videos_list.addItem(f"{display_name} ({int(duration)}s)")

    def setup_ui(self):
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Name:"))
        self.name_input = QLineEdit()
        layout.addWidget(self.name_input)

        collection_layout = QHBoxLayout()
        collection_layout.addWidget(QLabel("Collection:"))
        self.collection_path = QLineEdit()
        self.collection_path.setPlaceholderText("Select collections_name.json...")
        self.collection_path.setReadOnly(True)
        collection_layout.addWidget(self.collection_path)

        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self.browse_collection)
        collection_layout.addWidget(browse_btn)
        layout.addLayout(collection_layout)

        layout.addWidget(QLabel("Videos in Collection:"))
        self.videos_list = QListWidget()
        self.videos_list.setMinimumHeight(150)
        layout.addWidget(self.videos_list)

        randomize_layout = QHBoxLayout()
        self.randomize_videos_check = QCheckBox("Randomize Videos")
        randomize_layout.addWidget(self.randomize_videos_check)
        randomize_layout.addWidget(QLabel("Video Count:"))
        self.video_count_spin = QSpinBox()
        self.video_count_spin.setMinimum(1)
        self.video_count_spin.setValue(1)
        randomize_layout.addWidget(self.video_count_spin)
        randomize_layout.addStretch()
        layout.addLayout(randomize_layout)

        calc_layout = QHBoxLayout()
        self.auto_calc_btn = QPushButton("Auto Calc End Time")
        self.auto_calc_btn.clicked.connect(self.auto_calc_end_time)
        calc_layout.addWidget(self.auto_calc_btn)
        calc_layout.addStretch()
        layout.addLayout(calc_layout)

        time_layout = QHBoxLayout()
        time_layout.addWidget(QLabel("Start Time:"))
        self.start_time_edit = QTimeEdit()
        self.start_time_edit.setDisplayFormat("HH:mm")
        self.start_time_edit.setTime(QTime(0, 0))
        time_layout.addWidget(self.start_time_edit)

        time_layout.addWidget(QLabel("End Time:"))
        self.end_time_edit = QTimeEdit()
        self.end_time_edit.setDisplayFormat("HH:mm")
        self.end_time_edit.setTime(QTime(1, 0))
        time_layout.addWidget(self.end_time_edit)
        layout.addLayout(time_layout)

        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def browse_collection(self):
        from PySide6.QtWidgets import QFileDialog
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Collection File", "",
            "JSON Files (*.json);;All Files (*)"
        )
        if file_path:
            self.load_collection(file_path)

    def load_collection(self, file_path: str):
        import json
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            self.collection_path.setText(file_path)
            self.videos_list.clear()
            self.collection_videos.clear()

            collections = data.get('collections', [])
            for collection in collections:
                for video in collection.get('videos', []):
                    path = video.get('path', '')
                    duration = video.get('duration', 0)
                    self.collection_videos.append({'path': path, 'duration': duration})
                    display_name = path.split('/')[-1] if '/' in path else path
                    self.videos_list.addItem(f"{display_name} ({int(duration)}s)")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to load collection: {e}")

    def get_tag(self) -> Tag:
        tag = Tag(
            tag_type="custom",
            name=self.name_input.text() or "Custom Video",
            start_time=self.start_time_edit.time(),
            end_time=self.end_time_edit.time(),
            collection_videos=self.collection_videos.copy(),
            collection_path=self.collection_path.text(),
            video_count=self.video_count_spin.value()
        )
        return tag

    def auto_calc_end_time(self):
        if not self.collection_videos:
            QMessageBox.warning(self, "No Videos", "Please load a collection first.")
            return

        if not self.randomize_videos_check.isChecked():
            selected = self.videos_list.currentRow()
            if selected < 0:
                QMessageBox.warning(self, "No Selection", "Please select a video from the list.")
                return
            duration = self.collection_videos[selected].get('duration', 0)
        else:
            count = self.video_count_spin.value()
            total_duration = 0
            for i in range(min(count, len(self.collection_videos))):
                total_duration += self.collection_videos[i].get('duration', 0)
            duration = total_duration

        start_time = self.start_time_edit.time()
        start_mins = start_time.hour() * 60 + start_time.minute()
        end_mins = start_mins + int(duration // 60)
        end_mins = end_mins % (24 * 60)
        self.end_time_edit.setTime(QTime(end_mins // 60, end_mins % 60))


class RandomFillDialog(QDialog):
    def __init__(self, parent=None, tag: Optional[Tag] = None):
        super().__init__(parent)
        self.setWindowTitle("Add Random Fill Tag" if not tag else "Edit Random Fill Tag")
        self.setModal(True)
        self.collection_videos = []
        self.added_videos = []
        self.blacklist = []
        self.setup_ui()
        
        if tag:
            self.name_input.setText(tag.name)
            self.start_time_edit.setTime(tag.start_time)
            self.end_time_edit.setTime(tag.end_time)
            self.blacklist = tag.blacklist.copy() if hasattr(tag, 'blacklist') and tag.blacklist else []
            
            if tag.collection_videos and tag.collection_path:
                self.load_collection(tag.collection_path)

    def setup_ui(self):
        main_layout = QHBoxLayout(self)
        
        info_panel = QWidget()
        info_layout = QVBoxLayout(info_panel)
        info_layout.addWidget(QLabel("<b>Collection Info</b>"))
        
        self.info_name = QLabel("Name: -")
        info_layout.addWidget(self.info_name)
        
        self.info_desc = QLabel("Description:")
        self.info_desc.setWordWrap(True)
        info_layout.addWidget(self.info_desc)
        
        self.info_genre = QLabel("Genre: -")
        info_layout.addWidget(self.info_genre)
        
        self.info_year = QLabel("Year: -")
        info_layout.addWidget(self.info_year)
        
        info_layout.addWidget(QLabel("<b>Video Info</b>"))
        self.video_info = QLabel("Select a video to see details")
        self.video_info.setWordWrap(True)
        info_layout.addWidget(self.video_info)
        
        main_layout.addWidget(info_panel)
        
        lists_panel = QWidget()
        lists_layout = QVBoxLayout(lists_panel)
        
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Name:"))
        self.name_input = QLineEdit()
        name_layout.addWidget(self.name_input)
        
        coll_layout = QHBoxLayout()
        coll_layout.addWidget(QLabel("Collection:"))
        self.collection_path = QLineEdit()
        self.collection_path.setPlaceholderText("Select collections_name.json...")
        self.collection_path.setReadOnly(True)
        coll_layout.addWidget(self.collection_path)

        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self.browse_collection)
        coll_layout.addWidget(browse_btn)
        
        lists_layout.addLayout(name_layout)
        lists_layout.addLayout(coll_layout)
        
        lists_container = QWidget()
        lists_inner = QHBoxLayout(lists_container)
        
        collection_widget = QWidget()
        collection_vbox = QVBoxLayout(collection_widget)
        collection_vbox.addWidget(QLabel("Videos in Collection"))
        self.videos_count_label = QLabel("Count: 0")
        collection_vbox.addWidget(self.videos_count_label)
        self.videos_list = QListWidget()
        self.videos_list.setMinimumHeight(200)
        self.videos_list.setSelectionMode(QListWidget.MultiSelection)
        self.videos_list.itemClicked.connect(self.on_video_selected)
        collection_vbox.addWidget(self.videos_list)
        
        collection_btn_layout = QHBoxLayout()
        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(self.select_all_videos)
        collection_btn_layout.addWidget(select_all_btn)
        
        clear_sel_btn = QPushButton("Clear")
        clear_sel_btn.clicked.connect(self.clear_selection)
        collection_btn_layout.addWidget(clear_sel_btn)
        
        add_btn = QPushButton("Add >>")
        add_btn.clicked.connect(self.add_selected_videos)
        collection_btn_layout.addWidget(add_btn)
        
        collection_vbox.addLayout(collection_btn_layout)
        lists_inner.addWidget(collection_widget)
        
        added_widget = QWidget()
        added_vbox = QVBoxLayout(added_widget)
        added_vbox.addWidget(QLabel("Added Videos"))
        self.added_count_label = QLabel("Count: 0")
        added_vbox.addWidget(self.added_count_label)
        self.added_list = QListWidget()
        self.added_list.setMinimumHeight(200)
        added_vbox.addWidget(self.added_list)
        
        added_btn_layout = QHBoxLayout()
        remove_btn = QPushButton("<< Remove")
        remove_btn.clicked.connect(self.remove_selected_added)
        added_btn_layout.addWidget(remove_btn)
        
        remove_all_btn = QPushButton("Remove All")
        remove_all_btn.clicked.connect(self.remove_all_added)
        added_btn_layout.addWidget(remove_all_btn)
        
        blacklist_btn = QPushButton("Add to Blacklist >>")
        blacklist_btn.clicked.connect(self.add_to_blacklist)
        added_btn_layout.addWidget(blacklist_btn)
        
        added_vbox.addLayout(added_btn_layout)
        lists_inner.addWidget(added_widget)
        
        blacklist_widget = QWidget()
        blacklist_vbox = QVBoxLayout(blacklist_widget)
        blacklist_vbox.addWidget(QLabel("Blacklist"))
        self.blacklist_count_label = QLabel("Count: 0")
        blacklist_vbox.addWidget(self.blacklist_count_label)
        self.blacklist_list = QListWidget()
        self.blacklist_list.setMinimumHeight(200)
        blacklist_vbox.addWidget(self.blacklist_list)
        
        blacklist_btn_layout = QHBoxLayout()
        remove_blacklist_btn = QPushButton("<< Remove")
        remove_blacklist_btn.clicked.connect(self.remove_from_blacklist)
        blacklist_btn_layout.addWidget(remove_blacklist_btn)
        
        load_blacklist_btn = QPushButton("Load")
        load_blacklist_btn.clicked.connect(self.load_blacklist_file)
        blacklist_btn_layout.addWidget(load_blacklist_btn)
        
        save_blacklist_btn = QPushButton("Save")
        save_blacklist_btn.clicked.connect(self.save_blacklist_file)
        blacklist_btn_layout.addWidget(save_blacklist_btn)
        
        blacklist_vbox.addLayout(blacklist_btn_layout)
        lists_inner.addWidget(blacklist_widget)
        
        lists_layout.addWidget(lists_container)
        
        time_layout = QHBoxLayout()
        time_layout.addWidget(QLabel("Start Time:"))
        self.start_time_edit = QTimeEdit()
        self.start_time_edit.setDisplayFormat("HH:mm")
        self.start_time_edit.setTime(QTime(0, 0))
        time_layout.addWidget(self.start_time_edit)

        self.calc_btn = QPushButton("Auto Calc")
        self.calc_btn.clicked.connect(self.auto_calc_end_time)
        time_layout.addWidget(self.calc_btn)
        
        time_layout.addWidget(QLabel("End Time:"))
        self.end_time_edit = QTimeEdit()
        self.end_time_edit.setDisplayFormat("HH:mm")
        self.end_time_edit.setTime(QTime(1, 0))
        self.end_time_edit.setReadOnly(True)
        time_layout.addWidget(self.end_time_edit)
        lists_layout.addLayout(time_layout)

        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        lists_layout.addLayout(btn_layout)
        
        main_layout.addWidget(lists_panel)

    def browse_collection(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Collection File", "",
            "JSON Files (*.json);;All Files (*)"
        )
        if file_path:
            self.load_collection(file_path)

    def load_collection(self, file_path: str):
        import json
        from pathlib import Path
        import configparser
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            self.collection_path.setText(file_path)
            self.videos_list.clear()
            self.collection_videos = []
            self.added_videos = []
            self.blacklist = []

            collection_dir = Path(file_path).parent
            collection_stem = Path(file_path).stem
            
            blacklist_data = []
            
            search_dirs = [collection_dir, Path.cwd()]
            
            for search_dir in search_dirs:
                for bl_file in search_dir.glob(f"{collection_stem}_blacklist.*"):
                    if bl_file.suffix == '.json':
                        with open(bl_file, 'r') as bf:
                            blacklist_data = json.load(bf).get('blacklist', [])
                        break
                    elif bl_file.suffix == '.ini':
                        bc = configparser.ConfigParser()
                        bc.read(bl_file)
                        if 'Blacklist' in bc:
                            for key in bc['Blacklist']:
                                blacklist_data.append({'path': bc['Blacklist'][key]})
                        break
                if blacklist_data:
                    break

            collections = data.get('collections', [])
            for collection in collections:
                self.info_name.setText(f"Name: {collection.get('name', '-')}")
                self.info_desc.setText(f"Description: {collection.get('description', '-')}")
                self.info_genre.setText(f"Genre: {', '.join(collection.get('genre', []))}")
                self.info_year.setText(f"Year: {collection.get('year', '-')}")
                
                for video in collection.get('videos', []):
                    path = video.get('path', '')
                    duration = video.get('duration', 0)
                    video_data = {
                        'path': path,
                        'duration': duration,
                        'name': path.split('/')[-1] if '/' in path else path
                    }
                    self.collection_videos.append(video_data)
                    self.videos_list.addItem(f"{video_data['name']} ({int(duration)}s)")
                    
                    if any(b.get('path') == path for b in blacklist_data):
                        self.blacklist.append(video_data)
            
            for bl_video in blacklist_data:
                if bl_video not in self.blacklist:
                    self.blacklist.append(bl_video)
            
            self.added_videos = []
            self.refresh_added_list()
            self.refresh_blacklist_list()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to load collection: {e}")

    def on_video_selected(self, item):
        row = self.videos_list.row(item)
        if 0 <= row < len(self.collection_videos):
            video = self.collection_videos[row]
            info = f"Name: {video.get('name', '-')}\nPath: {video.get('path', '-')}\nDuration: {int(video.get('duration', 0))}s"
            self.video_info.setText(info)

    def select_all_videos(self):
        self.videos_list.selectAll()

    def clear_selection(self):
        self.videos_list.clearSelection()

    def add_selected_videos(self):
        selected = self.videos_list.selectedItems()
        for item in selected:
            row = self.videos_list.row(item)
            if 0 <= row < len(self.collection_videos):
                video = self.collection_videos[row]
            else:
                text = item.text()
                video_name = text.split(' (')[0]
                video = {'path': f"/home/akira/Videos/Akiratv/{video_name}"}
            if video not in self.added_videos:
                self.added_videos.append(video)
        self.refresh_added_list()

    def remove_selected_added(self):
        selected_texts = [item.text() for item in self.added_list.selectedItems()]
        for text in selected_texts:
            video_name = text.split(' (')[0]
            self.added_videos = [v for v in self.added_videos if v.get('path', '').split('/')[-1] != video_name]
        self.refresh_added_list()

    def remove_all_added(self):
        self.added_videos = []
        self.refresh_added_list()

    def add_to_blacklist(self):
        for item in self.added_list.selectedItems():
            text = item.text()
            video_name = text.split(' (')[0]
            for v in self.collection_videos:
                if v.get('path', '').split('/')[-1] == video_name:
                    if v not in self.blacklist:
                        self.blacklist.append(v)
                    break
        self.refresh_added_list()
        self.refresh_blacklist_list()

    def remove_from_blacklist(self):
        for item in self.blacklist_list.selectedItems():
            row = self.blacklist_list.row(item)
            if 0 <= row < len(self.blacklist):
                self.blacklist.pop(row)
        self.refresh_blacklist_list()

    def refresh_added_list(self):
        sorted_added = sorted(self.added_videos, key=lambda v: v.get('path', '').split('/')[-1])
        self.added_list.clear()
        for video in sorted_added:
            path = video.get('path', '')
            name = path.split('/')[-1] if '/' in path else path
            self.added_list.addItem(f"{name} ({int(video.get('duration', 0))}s)")
        self.update_counts()

    def refresh_blacklist_list(self):
        self.blacklist_list.clear()
        sorted_blacklist = sorted(self.blacklist, key=lambda v: v.get('path', '').split('/')[-1])
        for video in sorted_blacklist:
            path = video.get('path', '')
            name = path.split('/')[-1] if '/' in path else path
            self.blacklist_list.addItem(name)
        self.update_counts()

    def update_counts(self):
        self.videos_count_label.setText(f"Count: {len(self.collection_videos)}")
        self.added_count_label.setText(f"Count: {len(self.added_videos)}")
        self.blacklist_count_label.setText(f"Count: {len(self.blacklist)}")

    def load_blacklist_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Blacklist File", "", "INI Files (*.ini);;JSON Files (*.json);;All Files (*)"
        )
        if not file_path:
            return
        
        import configparser
        blacklist_data = []
        
        if file_path.endswith('.ini'):
            bc = configparser.ConfigParser()
            bc.read(file_path)
            if 'Blacklist' in bc:
                for key in bc['Blacklist']:
                    value = bc['Blacklist'][key]
                    paths = [p.strip() for p in value.split('\n') if p.strip()]
                    for path in paths:
                        blacklist_data.append({'path': path})
        else:
            import json
            with open(file_path, 'r') as bf:
                blacklist_data = json.load(bf).get('blacklist', [])
        
        self.blacklist = blacklist_data
        
        self.added_videos = [v for v in self.added_videos 
                           if v.get('path', '') not in [b.get('path', '') for b in self.blacklist]]
        
        self.refresh_blacklist_list()
        self.refresh_added_list()

    def save_blacklist_file(self):
        if not self.collection_path.text():
            return
        
        import json
        blacklist_path = self.collection_path.text().replace('.json', '_blacklist.json')
        
        blacklist_data = {'blacklist': self.blacklist}
        
        with open(blacklist_path, 'w') as f:
            json.dump(blacklist_data, f, indent=2)
        
        QMessageBox.warning(self, "Saved", f"Blacklist saved to {blacklist_path}")

    def auto_calc_end_time(self):
        if not self.added_videos:
            QMessageBox.warning(self, "No Videos", "Please add videos first.")
            return
        
        total_duration = sum(v.get('duration', 0) for v in self.added_videos)
        total_mins = int(total_duration // 60)
        
        start_time = self.start_time_edit.time()
        start_mins = start_time.hour() * 60 + start_time.minute()
        end_mins = start_mins + total_mins
        end_mins = end_mins % (24 * 60)
        
        self.end_time_edit.setTime(QTime(end_mins // 60, end_mins % 60))

    def get_tag(self) -> Tag:
        if not self.added_videos:
            QMessageBox.warning(self, "No Videos", "Please add at least one video.")
            return None
        
        self.auto_calc_end_time()
        tag = Tag(
            tag_type="random",
            name=self.name_input.text() or "Random Fill",
            start_time=self.start_time_edit.time(),
            end_time=self.end_time_edit.time(),
            collection_videos=self.added_videos.copy(),
            collection_path=self.collection_path.text(),
            blacklist=self.blacklist.copy(),
            is_random_fill=True
        )
        return tag


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
        self.add_btn = QPushButton("Add Custom")
        self.add_btn.clicked.connect(self.add_custom_tag)
        btn_layout.addWidget(self.add_btn)

        self.add_random_btn = QPushButton("Add Random Fill")
        self.add_random_btn.clicked.connect(self.add_random_fill_tag)
        btn_layout.addWidget(self.add_random_btn)

        self.edit_btn = QPushButton("Edit")
        self.edit_btn.clicked.connect(self.edit_tag)
        btn_layout.addWidget(self.edit_btn)

        self.delete_btn = QPushButton("Delete")
        self.delete_btn.clicked.connect(self.delete_tag)
        btn_layout.addWidget(self.delete_btn)

        tags_layout.addLayout(btn_layout)

        save_load_layout = QHBoxLayout()
        self.save_btn = QPushButton("Save All")
        self.save_btn.clicked.connect(self.save_tags)
        save_load_layout.addWidget(self.save_btn)

        self.load_btn = QPushButton("Load All")
        self.load_btn.clicked.connect(self.load_tags)
        save_load_layout.addWidget(self.load_btn)

        self.save_single_btn = QPushButton("Save Tag")
        self.save_single_btn.clicked.connect(self.save_single_tag)
        save_load_layout.addWidget(self.save_single_btn)

        self.load_single_btn = QPushButton("Load Tag")
        self.load_single_btn.clicked.connect(self.load_single_tag)
        save_load_layout.addWidget(self.load_single_btn)
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
        
        for day_offset in range(7):
            current_date = start_date + timedelta(days=day_offset)
            day_name = days[current_date.weekday()]
            self.preview_list.addItem(f"=== {current_date} - {day_name} ===")
            self.tag_manager.clear_cache()
            entries = self.schedule_generator.apply_custom_tags() if not self.approximate_enabled else self.schedule_generator.apply_approximate()
            for entry in entries:
                start_h = (entry.start_minutes // 60) % 24
                start_m = entry.start_minutes % 60
                end_h = (entry.end_minutes // 60) % 24
                end_m = entry.end_minutes % 60
                if entry.start_minutes == 0:
                    self.preview_list.addItem(f"Day {day_offset + 1}\n{start_h:02d}:{start_m:02d} - {end_h:02d}:{end_m:02d} - {entry.video_name}")
                else:
                    self.preview_list.addItem(f"{start_h:02d}:{start_m:02d} - {end_h:02d}:{end_m:02d} - {entry.video_name}")

    def generate_monthly_preview(self):
        self.preview_list.clear()
        self.preview_title.setText("Calendar Schedule Preview (30 Days)")
        
        from datetime import date
        start_date = date.today()
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        
        for day_offset in range(30):
            current_date = start_date + timedelta(days=day_offset)
            day_name = days[current_date.weekday()]
            self.preview_list.addItem(f"=== {current_date} - {day_name} ===")
            self.tag_manager.clear_cache()
            entries = self.schedule_generator.apply_custom_tags() if not self.approximate_enabled else self.schedule_generator.apply_approximate()
            for entry in entries:
                start_h = (entry.start_minutes // 60) % 24
                start_m = entry.start_minutes % 60
                end_h = (entry.end_minutes // 60) % 24
                end_m = entry.end_minutes % 60
                if entry.start_minutes == 0:
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

    def add_tag(self):
        dialog = TagDialog(self)
        if dialog.exec():
            tag = dialog.get_tag()
            self.tag_manager.add_tag(tag)
            self.refresh_tags_list()
            self.refresh_preview()

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
            dialog = RandomFillDialog(self, tag)
        else:
            dialog = TagDialog(self, tag)
        
        if dialog.exec():
            new_tag = dialog.get_tag()
            self.tag_manager.edit_tag(
                current_row, new_tag.name,
                new_tag.start_time, new_tag.end_time,
                new_tag.collection_videos,
                new_tag.collection_path,
                new_tag.video_count
            )
            self.refresh_tags_list()
            self.refresh_preview()

    def delete_tag(self):
        current_row = self.tags_list.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "No Selection", "Please select a tag to delete.")
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

    def save_single_tag(self):
        current_row = self.tags_list.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "No Selection", "Please select a tag to save.")
            return

        tag = self.tag_manager.tags[current_row]
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Tag", "", "INI Files (*.ini);;All Files (*)")
        if file_path:
            import json
            config = configparser.ConfigParser()
            is_random = "1" if getattr(tag, 'is_random_fill', False) else "0"
            randomize = "1" if getattr(tag, 'randomize_videos', False) else "0"
            video_count = str(getattr(tag, 'video_count', 1))
            collection_path = getattr(tag, 'collection_path', '')
            blacklist_path = getattr(tag, 'blacklist_path', '')
            videos_json = json.dumps(tag.collection_videos) if tag.collection_videos else ""
            blacklist_json = json.dumps(tag.blacklist) if getattr(tag, 'blacklist', None) else ""
            config['Tag'] = {'data': f"{tag.tag_type}|{tag.name}|{tag.start_time.toString('HH:mm')}|{tag.end_time.toString('HH:mm')}|{is_random}|{randomize}|{video_count}|{collection_path}|{blacklist_path}|{videos_json}|{blacklist_json}"}
            with open(file_path, 'w') as f:
                config.write(f)
            self.statusBar().showMessage(f"Tag saved to {file_path}")

    def load_single_tag(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Load Tag", "", "INI Files (*.ini);;All Files (*)")
        if not file_path:
            return

        import json
        if not Path(file_path).exists():
            QMessageBox.warning(self, "Error", "File not found.")
            return

        config = configparser.ConfigParser()
        config.read(file_path)
        if 'Tag' not in config:
            QMessageBox.warning(self, "Error", "Invalid tag file.")
            return

        parts = config['Tag']['data'].split('|')
        if len(parts) >= 4:
            tag_type, name, start, end = parts[0], parts[1], parts[2], parts[3]
            is_random_fill = len(parts) >= 5 and parts[4] == "1"
            randomize_videos = len(parts) >= 6 and parts[5] == "1"
            video_count = int(parts[6]) if len(parts) >= 7 and parts[6].isdigit() else 1
            collection_path = parts[7] if len(parts) >= 8 else ""
            blacklist_path = parts[8] if len(parts) >= 9 else ""
            collection_videos = []
            if len(parts) >= 10 and parts[9]:
                try:
                    collection_videos = json.loads(parts[9])
                except:
                    collection_videos = []
            blacklist = []
            if len(parts) >= 11 and parts[10]:
                try:
                    blacklist = json.loads(parts[10])
                except:
                    blacklist = []

            tag = Tag(tag_type, name, QTime.fromString(start, 'HH:mm'), QTime.fromString(end, 'HH:mm'), collection_videos, collection_path, randomize_videos, video_count, is_random_fill, blacklist)
            tag.blacklist_path = blacklist_path
            if is_random_fill:
                tag.is_random_fill = True

            self.tag_manager.add_tag(tag)
            self.refresh_tags_list()
            self.refresh_preview()
            self.statusBar().showMessage(f"Tag loaded from {file_path}")


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()