#!/usr/bin/env python3
import sys
import json
import configparser
from typing import List, Optional
from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QLineEdit, QLabel, QListWidget, QListWidgetItem, QPushButton,
    QVBoxLayout, QHBoxLayout, QTimeEdit, QCheckBox, QSpinBox, QComboBox,
    QFileDialog, QMessageBox, QWidget
)
from PySide6.QtCore import QTime
from PySide6.QtGui import QFont

from utils import (
    load_collection_json, load_blacklist_json,
    qtime_to_minutes, get_video_display_name, format_duration,
    get_config_paths, filter_videos_by_blacklist, get_schedule_profiles,
    parse_videos_for_series
)
from models import Tag


class BaseTagDialog(QDialog):
    def __init__(self, parent=None, tag: Optional[Tag] = None):
        super().__init__(parent)
        self.collection_videos = []
        self.blacklist = []

    def _setup_time_inputs(self, layout: QHBoxLayout, start_time: QTime = None, end_time: QTime = None):
        start_time = start_time or QTime(0, 0)
        end_time = end_time or QTime(1, 0)
        
        layout.addWidget(QLabel("Start Time:"))
        self.start_time_edit = QTimeEdit()
        self.start_time_edit.setDisplayFormat("HH:mm")
        self.start_time_edit.setTime(start_time)
        layout.addWidget(self.start_time_edit)

        layout.addWidget(QLabel("End Time:"))
        self.end_time_edit = QTimeEdit()
        self.end_time_edit.setDisplayFormat("HH:mm")
        self.end_time_edit.setTime(end_time)
        layout.addWidget(self.end_time_edit)

    def _load_collection_to_list(self, file_path: str, list_widget: QListWidget):
        collection_videos, _ = load_collection_json(file_path)
        self.collection_videos = collection_videos
        for video in collection_videos:
            path = video.get('path', '')
            duration = video.get('duration', 0)
            display_name = get_video_display_name(video)
            list_widget.addItem(f"{display_name} ({format_duration(duration)})")


class TagDialog(BaseTagDialog):
    def __init__(self, parent=None, tag: Optional[Tag] = None):
        super().__init__(parent, tag)
        self.setWindowTitle("Edit Tag" if tag else "Add Custom Tag")
        self.setModal(True)
        self.setup_ui()
        self.load_available_collection_profiles()
        self.load_channels()
        if tag:
            self.name_input.setText(tag.name)
            self.start_time_edit.setTime(tag.start_time)
            self.end_time_edit.setTime(tag.end_time)
            if tag.collection_videos:
                self.collection_videos = tag.collection_videos.copy()
                for video in self.collection_videos:
                    path = video.get('path', '')
                    duration = video.get('duration', 0)
                    display_name = get_video_display_name(video)
                    self.videos_list.addItem(f"{display_name} ({format_duration(duration)})")
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
                        display_name = get_video_display_name(video)
                        self.videos_list.addItem(f"{display_name} ({format_duration(duration)})")

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

        profile_layout = QHBoxLayout()
        profile_layout.addWidget(QLabel("Collection Profile:"))
        self.collection_profile_combo = QComboBox()
        self.collection_profile_combo.currentIndexChanged.connect(self.profile_selected)
        profile_layout.addWidget(self.collection_profile_combo)
        
        profile_layout.addWidget(QLabel("Blacklist Profile:"))
        self.blacklist_profile_combo = QComboBox()
        self.blacklist_profile_combo.currentIndexChanged.connect(self.blacklist_profile_selected)
        profile_layout.addWidget(self.blacklist_profile_combo)
        
        profile_layout.addStretch()
        layout.addLayout(profile_layout)

        channel_layout = QHBoxLayout()
        channel_layout.addWidget(QLabel("Channel:"))
        self.channel_combo = QComboBox()
        self.channel_combo.setEditable(True)
        self.load_channels()
        channel_layout.addWidget(self.channel_combo)
        channel_layout.addStretch()
        layout.addLayout(channel_layout)

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
        self._setup_time_inputs(time_layout)
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
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Collection File", "",
            "JSON Files (*.json);;All Files (*)"
        )
        if file_path:
            self.load_collection(file_path)

    def load_collection(self, file_path: str):
        self.collection_path.setText(file_path)
        self.videos_list.clear()
        self.collection_videos.clear()

        collection_videos, _ = load_collection_json(file_path)
        self.collection_videos = collection_videos

        for video in collection_videos:
            path = video.get('path', '')
            duration = video.get('duration', 0)
            display_name = get_video_display_name(video)
            self.videos_list.addItem(f"{display_name} ({format_duration(duration)})")

    def load_available_collection_profiles(self):
        collection_path, blacklist_path = get_config_paths()

        self.collection_profile_combo.addItem("-- None --")
        self.blacklist_profile_combo.addItem("-- None --")

        coll_path = Path(collection_path)
        if coll_path.exists():
            for json_file in sorted(coll_path.glob("*.json")):
                self.collection_profile_combo.addItem(json_file.name)

        blck_path = Path(blacklist_path)
        blacklist_files = set()
        if blck_path.exists():
            for ini_file in sorted(blck_path.glob("*_blacklist.ini")):
                blacklist_files.add(ini_file.name)
            for ini_file in sorted(blck_path.glob("*blacklist*.ini")):
                blacklist_files.add(ini_file.name)
        
        if blck_path != Path('.'):
            for ini_file in sorted(Path('.').glob("*blacklist*.ini")):
                blacklist_files.add(ini_file.name)
        
        for name in sorted(blacklist_files):
            self.blacklist_profile_combo.addItem(name)

    def profile_selected(self, index):
        if index <= 0:
            return
        file_name = self.collection_profile_combo.currentText()
        collection_path, _ = get_config_paths()
        file_path = Path(collection_path) / file_name
        if file_path.exists():
            self.load_collection(str(file_path))

    def blacklist_profile_selected(self, index):
        if index <= 0:
            return
        file_name = self.blacklist_profile_combo.currentText()
        _, blacklist_path = get_config_paths()
        file_path = Path(blacklist_path) / file_name
        if file_path.exists():
            self.load_blacklist_file(str(file_path))

    def load_blacklist_file(self, file_path: str):
        self.blacklist = load_blacklist_json(file_path)

    def load_channels(self):
        profiles = get_schedule_profiles()
        self.channel_combo.clear()
        self.channel_combo.addItem("")
        for profile in profiles:
            self.channel_combo.addItem(profile)
        if hasattr(self, 'tag') and self.tag and hasattr(self.tag, 'channel') and self.tag.channel:
            index = self.channel_combo.findText(self.tag.channel)
            if index >= 0:
                self.channel_combo.setCurrentIndex(index)
            else:
                self.channel_combo.setCurrentText(self.tag.channel)

    def get_tag(self) -> Tag:
        return Tag(
            tag_type="custom",
            name=self.name_input.text() or "Custom Video",
            start_time=self.start_time_edit.time(),
            end_time=self.end_time_edit.time(),
            collection_videos=self.collection_videos.copy(),
            collection_path=self.collection_path.text(),
            video_count=self.video_count_spin.value(),
            blacklist=self.blacklist.copy()
        )

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
            total_duration = sum(self.collection_videos[i].get('duration', 0) for i in range(min(count, len(self.collection_videos))))
            duration = total_duration

        start_time = self.start_time_edit.time()
        start_mins = qtime_to_minutes(start_time)
        end_mins = (start_mins + int(duration // 60)) % (24 * 60)
        self.end_time_edit.setTime(QTime(end_mins // 60, end_mins % 60))


class RandomFillDialog(BaseTagDialog):
    def __init__(self, parent=None, tag: Optional[Tag] = None):
        super().__init__(parent, tag)
        self.setWindowTitle("Add Random Fill Tag" if not tag else "Edit Random Fill Tag")
        self.setModal(True)
        self.added_videos = []
        self.blacklist_path = ""
        self.collection_profile = ""
        self.blacklist_profile = ""
        self.setup_ui()
        self.load_available_profiles()
        
        if tag:
            self.name_input.setText(tag.name)
            self.start_time_edit.setTime(tag.start_time)
            self.end_time_edit.setTime(tag.end_time)
            self.blacklist = tag.blacklist.copy() if hasattr(tag, 'blacklist') and tag.blacklist else []
            fill_24h = getattr(tag, 'fill_24h', False)
            self.fill_24h_check.setChecked(fill_24h)
            
            if tag.collection_videos and tag.collection_path:
                self.load_collection(tag.collection_path)
            
            collection_profile = getattr(tag, 'collection_profile', '')
            if collection_profile:
                index = self.collection_profile_combo.findText(collection_profile)
                if index >= 0:
                    self.collection_profile_combo.setCurrentIndex(index)
            
            blacklist_profile = getattr(tag, 'blacklist_profile', '')
            if blacklist_profile:
                index = self.blacklist_profile_combo.findText(blacklist_profile)
                if index >= 0:
                    self.blacklist_profile_combo.setCurrentIndex(index)

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
        name_layout.addStretch()
        
        profile_layout = QHBoxLayout()
        profile_layout.addWidget(QLabel("Collection Profile:"))
        self.collection_profile_combo = QComboBox()
        self.collection_profile_combo.currentIndexChanged.connect(self.collection_profile_selected)
        profile_layout.addWidget(self.collection_profile_combo)
        
        profile_layout.addWidget(QLabel("Blacklist Profile:"))
        self.blacklist_profile_combo = QComboBox()
        self.blacklist_profile_combo.currentIndexChanged.connect(self.blacklist_profile_selected)
        profile_layout.addWidget(self.blacklist_profile_combo)
        
        profile_layout.addStretch()
        
        coll_layout = QHBoxLayout()
        coll_layout.addWidget(QLabel("Collection:"))
        self.collection_path = QLineEdit()
        self.collection_path.setPlaceholderText("Select collections_name.json...")
        self.collection_path.setReadOnly(True)
        coll_layout.addWidget(self.collection_path)

        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self.browse_collection)
        coll_layout.addWidget(browse_btn)
        
        coll_layout.addStretch()
        
        lists_layout.addLayout(name_layout)
        lists_layout.addLayout(profile_layout)
        lists_layout.addLayout(coll_layout)
        
        lists_container = QWidget()
        lists_inner = QHBoxLayout(lists_container)
        
        collection_widget = self._create_video_list_section("Videos in Collection", True)
        self.videos_list = collection_widget.videos_list
        self.videos_count_label = collection_widget.count_label
        
        added_widget = self._create_video_list_section("Added Videos", False)
        self.added_list = added_widget.videos_list
        self.added_count_label = added_widget.count_label
        
        blacklist_widget = self._create_blacklist_section()
        self.blacklist_list = blacklist_widget.blacklist_list
        self.blacklist_count_label = blacklist_widget.count_label
        
        lists_inner.addWidget(collection_widget.widget)
        lists_inner.addWidget(added_widget.widget)
        lists_inner.addWidget(blacklist_widget.widget)
        
        lists_layout.addWidget(lists_container)
        
        time_layout = QHBoxLayout()
        self._setup_time_inputs(time_layout)

        self.calc_btn = QPushButton("Auto Calc")
        self.calc_btn.clicked.connect(self.auto_calc_end_time)
        time_layout.addWidget(self.calc_btn)
        lists_layout.addLayout(time_layout)

        self.fill_24h_check = QCheckBox("Fill 24 Hours (loop videos to fill full day)")
        self.fill_24h_check.setChecked(True)
        lists_layout.addWidget(self.fill_24h_check)

        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        lists_layout.addLayout(btn_layout)
        
        main_layout.addWidget(lists_panel)

    def _create_video_list_section(self, title: str, with_buttons: bool):
        widget = QWidget()
        vbox = QVBoxLayout(widget)
        vbox.addWidget(QLabel(title))
        
        count_label = QLabel("Count: 0")
        vbox.addWidget(count_label)
        
        videos_list = QListWidget()
        videos_list.setMinimumHeight(200)
        if with_buttons:
            videos_list.setSelectionMode(QListWidget.MultiSelection)
            videos_list.itemClicked.connect(self.on_video_selected)
        vbox.addWidget(videos_list)
        
        btn_layout = QHBoxLayout()
        if with_buttons:
            select_all_btn = QPushButton("Select All")
            select_all_btn.clicked.connect(self.select_all_videos)
            btn_layout.addWidget(select_all_btn)
            
            clear_sel_btn = QPushButton("Clear")
            clear_sel_btn.clicked.connect(self.clear_selection)
            btn_layout.addWidget(clear_sel_btn)
            
            add_btn = QPushButton("Add >>")
            add_btn.clicked.connect(self.add_selected_videos)
            btn_layout.addWidget(add_btn)
        else:
            remove_btn = QPushButton("<< Remove")
            remove_btn.clicked.connect(self.remove_selected_added)
            btn_layout.addWidget(remove_btn)
            
            remove_all_btn = QPushButton("Remove All")
            remove_all_btn.clicked.connect(self.remove_all_added)
            btn_layout.addWidget(remove_all_btn)
            
            blacklist_btn = QPushButton("Add to Blacklist >>")
            blacklist_btn.clicked.connect(self.add_to_blacklist)
            btn_layout.addWidget(blacklist_btn)
        
        vbox.addLayout(btn_layout)
        
        section = type('VideoSection', (), {
            'widget': widget, 'videos_list': videos_list, 'count_label': count_label
        })()
        return section

    def _create_blacklist_section(self):
        widget = QWidget()
        vbox = QVBoxLayout(widget)
        vbox.addWidget(QLabel("Blacklist"))
        
        count_label = QLabel("Count: 0")
        vbox.addWidget(count_label)
        
        blacklist_list = QListWidget()
        blacklist_list.setMinimumHeight(200)
        vbox.addWidget(blacklist_list)
        
        btn_layout = QHBoxLayout()
        remove_blacklist_btn = QPushButton("<< Remove")
        remove_blacklist_btn.clicked.connect(self.remove_from_blacklist)
        btn_layout.addWidget(remove_blacklist_btn)
        
        load_blacklist_btn = QPushButton("Load")
        load_blacklist_btn.clicked.connect(self.load_blacklist_file)
        btn_layout.addWidget(load_blacklist_btn)
        
        save_blacklist_btn = QPushButton("Save")
        save_blacklist_btn.clicked.connect(self.save_blacklist_file)
        btn_layout.addWidget(save_blacklist_btn)
        
        vbox.addLayout(btn_layout)
        
        section = type('BlacklistSection', (), {
            'widget': widget, 'blacklist_list': blacklist_list, 'count_label': count_label
        })()
        return section

    def browse_collection(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Collection File", "",
            "JSON Files (*.json);;All Files (*)"
        )
        if file_path:
            self.load_collection(file_path)

    def load_available_profiles(self):
        collection_path, blacklist_path = get_config_paths()

        self.collection_profile_combo.addItem("-- None --")
        self.blacklist_profile_combo.addItem("-- None --")

        coll_path = Path(collection_path)
        if coll_path.exists():
            for json_file in sorted(coll_path.glob("*.json")):
                self.collection_profile_combo.addItem(json_file.name)

        blck_path = Path(blacklist_path)
        blacklist_files = set()
        if blck_path.exists():
            for ini_file in sorted(blck_path.glob("*_blacklist.ini")):
                blacklist_files.add(ini_file.name)
            for ini_file in sorted(blck_path.glob("*blacklist*.ini")):
                blacklist_files.add(ini_file.name)
        
        if blck_path != Path('.'):
            for ini_file in sorted(Path('.').glob("*blacklist*.ini")):
                blacklist_files.add(ini_file.name)
        
        for name in sorted(blacklist_files):
            self.blacklist_profile_combo.addItem(name)

    def collection_profile_selected(self, index):
        if index <= 0:
            return
        file_name = self.collection_profile_combo.currentText()
        collection_path, _ = get_config_paths()
        file_path = Path(collection_path) / file_name
        if file_path.exists():
            self.load_collection(str(file_path))

    def blacklist_profile_selected(self, index):
        if index <= 0:
            return
        file_name = self.blacklist_profile_combo.currentText()
        _, blacklist_path = get_config_paths()
        file_path = Path(blacklist_path) / file_name
        if file_path.exists():
            self.load_blacklist_file(str(file_path))

    def load_collection(self, file_path: str):
        collection_videos, collection_info = load_collection_json(file_path)
        self.collection_path.setText(file_path)
        self.videos_list.clear()
        self.collection_videos = []
        self.added_videos = []
        self.blacklist = []

        collection_dir = Path(file_path).parent
        collection_stem = Path(file_path).stem
        
        blacklist_data = []
        for search_dir in [collection_dir, Path.cwd()]:
            for bl_file in search_dir.glob(f"{collection_stem}_blacklist.*"):
                blacklist_data = load_blacklist_json(str(bl_file))
                break
            if blacklist_data:
                break

        self.info_name.setText(f"Name: {collection_info.get('name', '-')}")
        self.info_desc.setText(f"Description: {collection_info.get('description', '-')}")
        self.info_genre.setText(f"Genre: {', '.join(collection_info.get('genre', []))}")
        self.info_year.setText(f"Year: {collection_info.get('year', '-')}")
        
        for video in collection_videos:
            path = video.get('path', '')
            duration = video.get('duration', 0)
            video_data = {'path': path, 'duration': duration, 'name': get_video_display_name(video)}
            self.collection_videos.append(video_data)
            self.videos_list.addItem(f"{video_data['name']} ({format_duration(duration)})")
            
            if any(b.get('path') == path for b in blacklist_data):
                self.blacklist.append(video_data)
        
        for bl_video in blacklist_data:
            if bl_video not in self.blacklist:
                self.blacklist.append(bl_video)
        
        self.added_videos = []
        self.refresh_added_list()
        self.refresh_blacklist_list()

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
        for item in self.videos_list.selectedItems():
            row = self.videos_list.row(item)
            if 0 <= row < len(self.collection_videos):
                video = self.collection_videos[row]
            else:
                text = item.text()
                video_name = text.split(' (')[0]
                video = {'name': video_name}
            if video not in self.added_videos:
                self.added_videos.append(video)
        self.refresh_added_list()

    def remove_selected_added(self):
        for item in self.added_list.selectedItems():
            video_name = item.text().split(' (')[0]
            self.added_videos = [v for v in self.added_videos if v.get('path', '').split('/')[-1] != video_name]
        self.refresh_added_list()

    def remove_all_added(self):
        self.added_videos = []
        self.refresh_added_list()

    def add_to_blacklist(self):
        for item in self.added_list.selectedItems():
            video_name = item.text().split(' (')[0]
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
            self.added_list.addItem(f"{get_video_display_name(video)} ({format_duration(video.get('duration', 0))})")
        self.update_counts()

    def refresh_blacklist_list(self):
        self.blacklist_list.clear()
        sorted_blacklist = sorted(self.blacklist, key=lambda v: v.get('path', '').split('/')[-1])
        for video in sorted_blacklist:
            self.blacklist_list.addItem(get_video_display_name(video))
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
        
        blacklist_data = load_blacklist_json(file_path)
        self.blacklist = blacklist_data
        self.blacklist_path = file_path
        
        self.added_videos = filter_videos_by_blacklist(self.added_videos, self.blacklist)
        
        self.refresh_blacklist_list()
        self.refresh_added_list()

    def save_blacklist_file(self):
        if not self.collection_path.text():
            return
        
        blacklist_path = self.collection_path.text().replace('.json', '_blacklist.json')
        
        blacklist_data = {'blacklist': self.blacklist}
        
        with open(blacklist_path, 'w') as f:
            json.dump(blacklist_data, f, indent=2)
        
        QMessageBox.warning(self, "Saved", f"Blacklist saved to {blacklist_path}")

    def load_channels(self):
        profiles = get_schedule_profiles()
        self.channel_combo.clear()
        self.channel_combo.addItem("")
        for profile in profiles:
            self.channel_combo.addItem(profile)
        if hasattr(self, 'tag') and self.tag and hasattr(self.tag, 'channel') and self.tag.channel:
            index = self.channel_combo.findText(self.tag.channel)
            if index >= 0:
                self.channel_combo.setCurrentIndex(index)
            else:
                self.channel_combo.setCurrentText(self.tag.channel)

    def auto_calc_end_time(self):
        if not self.added_videos:
            QMessageBox.warning(self, "No Videos", "Please add videos first.")
            return
        
        total_duration = sum(v.get('duration', 0) for v in self.added_videos)
        total_mins = int(total_duration // 60)
        
        start_time = self.start_time_edit.time()
        start_mins = qtime_to_minutes(start_time)
        end_mins = (start_mins + total_mins) % (24 * 60)
        
        self.end_time_edit.setTime(QTime(end_mins // 60, end_mins % 60))

    def get_tag(self) -> Optional[Tag]:
        if not self.added_videos:
            QMessageBox.warning(self, "No Videos", "Please add at least one video.")
            return None
        
        fill_24h = self.fill_24h_check.isChecked()
        
        if fill_24h:
            self.start_time_edit.setTime(QTime(0, 0))
            self.end_time_edit.setTime(QTime(23, 59))
        
        return Tag(
            tag_type="random",
            name=self.name_input.text() or "Random Fill",
            start_time=self.start_time_edit.time(),
            end_time=self.end_time_edit.time(),
            collection_videos=self.added_videos.copy(),
            collection_path=self.collection_path.text(),
            blacklist=self.blacklist.copy(),
            blacklist_path=self.blacklist_path,
            is_random_fill=True,
            fill_24h=fill_24h,
            collection_profile=self.collection_profile_combo.currentText(),
            blacklist_profile=self.blacklist_profile_combo.currentText()
        )


class ConfigDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Config Settings")
        self.setModal(True)
        self.config_path = "config.ini"
        self.setup_ui()
        self.load_config()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        collection_path, blacklist_path = get_config_paths()

        layout.addWidget(QLabel("Collection Path:"))
        collection_layout = QHBoxLayout()
        self.collection_path_edit = QLineEdit()
        self.collection_path_edit.setPlaceholderText(collection_path)
        collection_layout.addWidget(self.collection_path_edit)
        
        browse_col_btn = QPushButton("Browse")
        browse_col_btn.clicked.connect(self.browse_collection_path)
        collection_layout.addWidget(browse_col_btn)
        layout.addLayout(collection_layout)

        layout.addWidget(QLabel("Blacklist Path:"))
        blacklist_layout = QHBoxLayout()
        self.blacklist_path_edit = QLineEdit()
        self.blacklist_path_edit.setPlaceholderText(blacklist_path)
        blacklist_layout.addWidget(self.blacklist_path_edit)
        
        browse_bl_btn = QPushButton("Browse")
        browse_bl_btn.clicked.connect(self.browse_blacklist_path)
        blacklist_layout.addWidget(browse_bl_btn)
        layout.addLayout(blacklist_layout)

        layout.addWidget(QLabel("Schedule Profiles (comma-separated names):"))
        self.schedule_profiles_edit = QLineEdit()
        self.schedule_profiles_edit.setPlaceholderText("akiratv, superman, horror")
        layout.addWidget(self.schedule_profiles_edit)

        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.save_config)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def browse_collection_path(self):
        path = QFileDialog.getExistingDirectory(self, "Select Collection Directory", "")
        if path:
            self.collection_path_edit.setText(path)

    def browse_blacklist_path(self):
        path = QFileDialog.getExistingDirectory(self, "Select Blacklist Directory", "")
        if path:
            self.blacklist_path_edit.setText(path)

    def load_config(self):
        if Path(self.config_path).exists():
            config = configparser.ConfigParser()
            config.read(self.config_path)
            if 'Paths' in config:
                self.collection_path_edit.setText(config['Paths'].get('collection_path', ''))
                self.blacklist_path_edit.setText(config['Paths'].get('blacklist_path', ''))
            if 'ScheduleProfiles' in config:
                self.schedule_profiles_edit.setText(config['ScheduleProfiles'].get('profiles', ''))

    def save_config(self):
        config = configparser.ConfigParser()
        config['Paths'] = {
            'collection_path': self.collection_path_edit.text(),
            'blacklist_path': self.blacklist_path_edit.text()
        }
        profiles = self.schedule_profiles_edit.text().strip()
        if profiles:
            config['ScheduleProfiles'] = {
                'profiles': profiles
            }
        with open(self.config_path, 'w') as f:
            config.write(f)
        self.accept()


class SeriesDialog(BaseTagDialog):
    def __init__(self, parent=None, tag: Optional[Tag] = None):
        super().__init__(parent, tag)
        self.setWindowTitle("Edit Series Tag" if tag else "Add Series Tag")
        self.setModal(True)
        self.collection_profile = ""
        self.blacklist_profile = ""
        self.setup_ui()
        self.load_available_profiles()
        if tag:
            self.name_input.setText(tag.name)
            self.start_time_edit.setTime(tag.start_time)
            self.end_time_edit.setTime(tag.end_time)
            self.start_season_spin.setValue(getattr(tag, 'start_season', 1))
            self.start_episode_spin.setValue(getattr(tag, 'start_episode', 1))
            self.video_count_spin.setValue(tag.video_count)
            if hasattr(tag, 'play_mode') and tag.play_mode:
                index = self.play_mode_combo.findText(tag.play_mode)
                if index >= 0:
                    self.play_mode_combo.setCurrentIndex(index)
            if tag.collection_videos:
                self.collection_videos = tag.collection_videos.copy()
                for video in self.collection_videos:
                    path = video.get('path', '')
                    duration = video.get('duration', 0)
                    display_name = get_video_display_name(video)
                    self.videos_list.addItem(f"{display_name} ({format_duration(duration)})")
            if hasattr(tag, 'collection_path') and tag.collection_path:
                self.collection_path.setText(tag.collection_path)
            
            collection_profile = getattr(tag, 'collection_profile', '')
            if collection_profile:
                index = self.collection_profile_combo.findText(collection_profile)
                if index >= 0:
                    self.collection_profile_combo.setCurrentIndex(index)
            
            blacklist_profile = getattr(tag, 'blacklist_profile', '')
            if blacklist_profile:
                index = self.blacklist_profile_combo.findText(blacklist_profile)
                if index >= 0:
                    self.blacklist_profile_combo.setCurrentIndex(index)

    def setup_ui(self):
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Name:"))
        self.name_input = QLineEdit()
        layout.addWidget(self.name_input)

        profile_layout = QHBoxLayout()
        profile_layout.addWidget(QLabel("Collection Profile:"))
        self.collection_profile_combo = QComboBox()
        self.collection_profile_combo.currentIndexChanged.connect(self.collection_profile_selected)
        profile_layout.addWidget(self.collection_profile_combo)
        
        profile_layout.addWidget(QLabel("Blacklist Profile:"))
        self.blacklist_profile_combo = QComboBox()
        self.blacklist_profile_combo.currentIndexChanged.connect(self.blacklist_profile_selected)
        profile_layout.addWidget(self.blacklist_profile_combo)
        
        profile_layout.addStretch()
        layout.addLayout(profile_layout)

        collection_layout = QHBoxLayout()
        collection_layout.addWidget(QLabel("Collection:"))
        self.collection_path = QLineEdit()
        self.collection_path.setPlaceholderText("Select collections_name.json...")
        self.collection_path.setReadOnly(True)
        collection_layout.addWidget(self.collection_path)

        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self.browse_collection)
        collection_layout.addWidget(browse_btn)
        
        collection_layout.addStretch()
        layout.addLayout(collection_layout)

        layout.addWidget(QLabel("Videos in Collection:"))
        self.videos_list = QListWidget()
        self.videos_list.setMinimumHeight(150)
        layout.addWidget(self.videos_list)

        series_layout = QHBoxLayout()
        series_layout.addWidget(QLabel("Start Season:"))
        self.start_season_spin = QSpinBox()
        self.start_season_spin.setMinimum(1)
        self.start_season_spin.setValue(1)
        series_layout.addWidget(self.start_season_spin)

        series_layout.addWidget(QLabel("Start Episode:"))
        self.start_episode_spin = QSpinBox()
        self.start_episode_spin.setMinimum(1)
        self.start_episode_spin.setValue(1)
        series_layout.addWidget(self.start_episode_spin)

        series_layout.addWidget(QLabel("Video Count:"))
        self.video_count_spin = QSpinBox()
        self.video_count_spin.setMinimum(1)
        self.video_count_spin.setValue(1)
        series_layout.addWidget(self.video_count_spin)

        series_layout.addWidget(QLabel("Play Mode:"))
        self.play_mode_combo = QComboBox()
        self.play_mode_combo.addItems(["sequence", "random"])
        series_layout.addWidget(self.play_mode_combo)
        
        series_layout.addStretch()
        layout.addLayout(series_layout)

        calc_layout = QHBoxLayout()
        self.auto_calc_btn = QPushButton("Auto Calc End Time")
        self.auto_calc_btn.clicked.connect(self.auto_calc_end_time)
        calc_layout.addWidget(self.auto_calc_btn)
        calc_layout.addStretch()
        layout.addLayout(calc_layout)

        time_layout = QHBoxLayout()
        self._setup_time_inputs(time_layout)
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
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Collection File", "",
            "JSON Files (*.json);;All Files (*)"
        )
        if file_path:
            self.load_collection(file_path)

    def load_collection(self, file_path: str):
        collection_videos, _ = load_collection_json(file_path)
        self.collection_path.setText(file_path)
        self.videos_list.clear()
        self.collection_videos = collection_videos

        for video in collection_videos:
            path = video.get('path', '')
            duration = video.get('duration', 0)
            display_name = get_video_display_name(video)
            self.videos_list.addItem(f"{display_name} ({format_duration(duration)})")

    def load_available_profiles(self):
        collection_path, blacklist_path = get_config_paths()

        self.collection_profile_combo.addItem("-- None --")
        self.blacklist_profile_combo.addItem("-- None --")

        coll_path = Path(collection_path)
        if coll_path.exists():
            for json_file in sorted(coll_path.glob("*.json")):
                self.collection_profile_combo.addItem(json_file.name)

        blck_path = Path(blacklist_path)
        blacklist_files = set()
        if blck_path.exists():
            for ini_file in sorted(blck_path.glob("*_blacklist.ini")):
                blacklist_files.add(ini_file.name)
            for ini_file in sorted(blck_path.glob("*blacklist*.ini")):
                blacklist_files.add(ini_file.name)
        
        if blck_path != Path('.'):
            for ini_file in sorted(Path('.').glob("*blacklist*.ini")):
                blacklist_files.add(ini_file.name)
        
        for name in sorted(blacklist_files):
            self.blacklist_profile_combo.addItem(name)

    def collection_profile_selected(self, index):
        if index <= 0:
            return
        file_name = self.collection_profile_combo.currentText()
        collection_path, _ = get_config_paths()
        file_path = Path(collection_path) / file_name
        if file_path.exists():
            self.load_collection(str(file_path))

    def blacklist_profile_selected(self, index):
        pass

    def auto_calc_end_time(self):
        if not self.collection_videos:
            return
        
        start_season = self.start_season_spin.value()
        start_episode = self.start_episode_spin.value()
        
        videos_to_use, _ = parse_videos_for_series(
            self.collection_videos,
            start_season,
            start_episode,
            self.play_mode_combo.currentText(),
            self.video_count_spin.value()
        )
        
        total_duration = sum(v['video'].get('duration', 0) for v in videos_to_use)
        total_mins = int(total_duration / 60)

        start_time = self.start_time_edit.time()
        start_mins = qtime_to_minutes(start_time)
        end_mins = (start_mins + total_mins) % (24 * 60)

        self.end_time_edit.setTime(QTime(end_mins // 60, end_mins % 60))

    def get_tag(self) -> Optional[Tag]:
        if not self.name_input.text():
            QMessageBox.warning(self, "No Name", "Please enter a name.")
            return None
        
        self.auto_calc_end_time()
        return Tag(
            tag_type="custom",
            name=self.name_input.text(),
            start_time=self.start_time_edit.time(),
            end_time=self.end_time_edit.time(),
            collection_videos=self.collection_videos.copy(),
            collection_path=self.collection_path.text(),
            video_count=self.video_count_spin.value(),
            is_series=True,
            start_season=self.start_season_spin.value(),
            start_episode=self.start_episode_spin.value(),
            play_mode=self.play_mode_combo.currentText(),
            collection_profile=self.collection_profile_combo.currentText(),
            blacklist_profile=self.blacklist_profile_combo.currentText()
        )