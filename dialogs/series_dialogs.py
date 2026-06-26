import logging
from pathlib import Path
from typing import List, Optional
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QSpinBox, QPushButton, QListWidget, QListWidgetItem, QMessageBox, QFileDialog,
    QCheckBox
)
from PySide6.QtCore import QTime
from PySide6.QtGui import QColor

from .base import BaseTagDialog
from .profile_mixin import SeriesProfileMixin
from .widgets.info_panel import CollectionInfoPanel, VideoInfoDisplay
from models import Tag, MultiSeriesTag
from utils import (
    load_collection_json, load_blacklist_json,
    get_video_display_name, format_duration,
    get_config_paths, get_covers_path,
    parse_videos_for_series, qtime_to_minutes
)

logger = logging.getLogger(__name__)


class SeriesDialog(BaseTagDialog, SeriesProfileMixin):
    """Dialog for creating/editing a series tag."""

    def __init__(self, parent=None, tag: Optional[Tag] = None):
        super().__init__(parent, tag)
        self.setWindowTitle("Edit Series Tag" if tag else "Add Series Tag")
        self.setModal(True)
        self.collection_profile = ""
        self.blacklist_profile = ""
        self.collection_info_dict = {}

        # Determine covers root directory (matching RandomFillDialog pattern)
        try:
            collection_path, _ = get_config_paths()
            covers_cfg = get_covers_path()
            if covers_cfg:
                self.covers_root = Path(covers_cfg)
            else:
                self.covers_root = Path(collection_path).parent.parent
        except Exception:
            self.covers_root = Path('.')

        fallback = [
            self.covers_root / 'user' / 'collections' / 'covers' / 'tatkotv' / 'images',
            self.covers_root / 'user' / 'covers' / 'tatkotv',
        ]
        self.info_panel = CollectionInfoPanel(parent=self, covers_root=self.covers_root,
                                              fallback_dirs=fallback)
        self.video_info = VideoInfoDisplay()

        self.setup_ui()
        self.load_available_profiles()  # From mixin
        if tag:
            self._populate_from_tag(tag)

    def setup_ui(self):
        main_layout = QHBoxLayout(self)

        # ── Left panel: collection info + video info ──
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(self.info_panel)
        left_layout.addWidget(self.video_info)
        main_layout.addWidget(left)

        # ── Right panel: existing controls ──
        right = QWidget()
        right_layout = QVBoxLayout(right)

        # Name
        right_layout.addWidget(QLabel("Name:"))
        self.name_input = QLineEdit()
        right_layout.addWidget(self.name_input)

        # Profile row
        profile_layout = QHBoxLayout()
        profile_layout.addWidget(QLabel("Collection Profile:"))
        self.collection_profile_combo = QComboBox()
        self.collection_profile_combo.currentIndexChanged.connect(self.profile_selected)  # from mixin
        profile_layout.addWidget(self.collection_profile_combo)

        profile_layout.addWidget(QLabel("Blacklist Profile:"))
        self.blacklist_profile_combo = QComboBox()
        self.blacklist_profile_combo.currentIndexChanged.connect(self.blacklist_profile_selected)  # from mixin
        profile_layout.addWidget(self.blacklist_profile_combo)

        profile_layout.addStretch()
        right_layout.addLayout(profile_layout)

        # Collection browse
        coll_layout = QHBoxLayout()
        coll_layout.addWidget(QLabel("Collection:"))
        self.collection_path = QLineEdit()
        self.collection_path.setPlaceholderText("Select collections_name.json...")
        self.collection_path.setReadOnly(True)
        coll_layout.addWidget(self.collection_path)

        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self.browse_collection)  # from mixin
        coll_layout.addWidget(browse_btn)
        coll_layout.addStretch()
        right_layout.addLayout(coll_layout)

        # Videos list
        right_layout.addWidget(QLabel("Videos in Collection:"))
        self.videos_list = QListWidget()
        self.videos_list.setMinimumHeight(150)
        self.videos_list.itemSelectionChanged.connect(self._on_video_selection_changed)
        right_layout.addWidget(self.videos_list)

        # Check Missing button
        check_missing_btn = QPushButton("Check Missing")
        check_missing_btn.setToolTip("Check which videos no longer exist on disk")
        check_missing_btn.clicked.connect(self.check_missing_videos)
        right_layout.addWidget(check_missing_btn)

        # Series options
        series_layout = QHBoxLayout()
        series_layout.addWidget(QLabel("Start Season:"))
        self.start_season_spin = QSpinBox()
        self.start_season_spin.setMinimum(0)
        self.start_season_spin.setValue(0)
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
        self.play_mode_combo.addItems(["sequence", "season_sequence", "random"])
        self.play_mode_combo.setToolTip("sequence: order by season/episode\nseason_sequence: season-aware linear order\nrandom: shuffled order")
        series_layout.addWidget(self.play_mode_combo)

        series_layout.addWidget(QLabel("End:"))
        self.end_behavior_combo = QComboBox()
        self.end_behavior_combo.addItems(["stop", "repeat", "random"])
        self.end_behavior_combo.setToolTip("stop: stop after last episode\nrepeat: loop from chosen season\nrandom: shuffle without repeats")
        self.end_behavior_combo.currentTextChanged.connect(self._update_end_behavior_ui)
        series_layout.addWidget(self.end_behavior_combo)

        self.repeat_season_spin = QSpinBox()
        self.repeat_season_spin.setMinimum(0)
        self.repeat_season_spin.setValue(0)
        self.repeat_season_spin.setToolTip("Repeat from season (0 = all seasons, 1+ = specific season)")
        self.repeat_season_spin.setVisible(False)
        series_layout.addWidget(self.repeat_season_spin)

        self.random_season_spin = QSpinBox()
        self.random_season_spin.setMinimum(0)
        self.random_season_spin.setValue(0)
        self.random_season_spin.setToolTip("Random from season (0 = any season, 1+ = specific season)")
        self.random_season_spin.setVisible(False)
        series_layout.addWidget(self.random_season_spin)

        series_layout.addStretch()
        right_layout.addLayout(series_layout)

        # Active days
        active_days_layout = QHBoxLayout()
        active_days_layout.addWidget(QLabel("Active Days:"))
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        self.day_checkboxes = []
        for day_name in day_names:
            cb = QCheckBox(day_name)
            cb.setChecked(True)
            cb.stateChanged.connect(self._update_all_days_checkbox)
            active_days_layout.addWidget(cb)
            self.day_checkboxes.append(cb)
        self.all_days_cb = QCheckBox("All")
        self.all_days_cb.setChecked(True)
        self.all_days_cb.stateChanged.connect(self._on_all_days_toggled)
        active_days_layout.addWidget(self.all_days_cb)
        active_days_layout.addStretch()
        right_layout.addLayout(active_days_layout)

        # Time inputs + auto calc
        time_layout = QHBoxLayout()
        self._setup_time_inputs(time_layout)
        self.auto_calc_btn = QPushButton("Auto Calc End Time")
        self.auto_calc_btn.clicked.connect(self.auto_calc_end_time)
        time_layout.addWidget(self.auto_calc_btn)
        time_layout.addStretch()
        right_layout.addLayout(time_layout)

        # Dialog buttons
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        right_layout.addLayout(btn_layout)

        main_layout.addWidget(right)

    def _update_end_behavior_ui(self, behavior: str):
        self.repeat_season_spin.setVisible(behavior == "repeat")
        self.random_season_spin.setVisible(behavior == "random")

    def _on_collection_loaded(self):
        """Update info panel after collection is loaded."""
        default_info = next(iter(self.collection_info_dict.values())) if self.collection_info_dict else {}
        self.info_panel.set_collection_info(default_info)
        self.info_panel.set_cover_image(default_info.get('cover'))

    def _on_video_selection_changed(self):
        """Update video info when a video is selected in the list."""
        selected = self.videos_list.selectedItems()
        if not selected:
            self.video_info.setText("Select a video to see details")
            return
        row = self.videos_list.row(selected[0])
        if 0 <= row < len(self.collection_videos):
            video = self.collection_videos[row]
            self.video_info.set_video_info(video)

    def _on_all_days_toggled(self, checked: bool):
        enabled = not checked
        for cb in self.day_checkboxes:
            cb.setChecked(checked)
            cb.setEnabled(enabled)

    def _update_all_days_checkbox(self):
        all_checked = all(cb.isChecked() for cb in self.day_checkboxes)
        if all_checked:
            self.all_days_cb.setChecked(True)
            for cb in self.day_checkboxes:
                cb.setEnabled(False)

    def _populate_from_tag(self, tag: Tag):
        """Fill fields from existing Tag."""
        self.name_input.setText(tag.name)
        self.start_time_edit.setTime(tag.start_time)
        self.end_time_edit.setTime(tag.end_time)
        self.start_season_spin.setValue(getattr(tag, 'start_season', 1))
        self.start_episode_spin.setValue(getattr(tag, 'start_episode', 1))
        self.video_count_spin.setValue(tag.video_count)
        if hasattr(tag, 'play_mode') and tag.play_mode:
            idx = self.play_mode_combo.findText(tag.play_mode)
            if idx >= 0:
                self.play_mode_combo.setCurrentIndex(idx)
        if tag.collection_path:
            self.load_collection(tag.collection_path)
            if tag.collection_videos:
                self.collection_videos = tag.collection_videos.copy()
                self.videos_list.clear()
                for video in self.collection_videos:
                    path = video.get('path', '')
                    duration = video.get('duration', 0)
                    display_name = get_video_display_name(video)
                    item = QListWidgetItem(f"{display_name} ({format_duration(duration)})")
                    item.setData(Qt.UserRole, path)
                    self.videos_list.addItem(item)
        elif tag.collection_videos:
            self.collection_videos = tag.collection_videos.copy()
            for video in self.collection_videos:
                path = video.get('path', '')
                duration = video.get('duration', 0)
                display_name = get_video_display_name(video)
                item = QListWidgetItem(f"{display_name} ({format_duration(duration)})")
                item.setData(Qt.UserRole, path)
                self.videos_list.addItem(item)

        collection_profile = getattr(tag, 'collection_profile', '')
        if collection_profile:
            idx = self.collection_profile_combo.findText(collection_profile)
            if idx >= 0:
                self.collection_profile_combo.setCurrentIndex(idx)

        blacklist_profile = getattr(tag, 'blacklist_profile', '')
        if blacklist_profile:
            idx = self.blacklist_profile_combo.findText(blacklist_profile)
            if idx >= 0:
                self.blacklist_profile_combo.setCurrentIndex(idx)

        end_behavior = getattr(tag, 'series_end_behavior', 'stop')
        idx = self.end_behavior_combo.findText(end_behavior)
        if idx >= 0:
            self.end_behavior_combo.setCurrentIndex(idx)
        repeat_season = getattr(tag, 'series_repeat_season', 0)
        self.repeat_season_spin.setValue(repeat_season)
        random_season = getattr(tag, 'series_random_season', 0)
        self.random_season_spin.setValue(random_season)

        active_days = getattr(tag, 'active_days', None)
        if active_days is not None:
            self.all_days_cb.setChecked(False)
            for cb in self.day_checkboxes:
                cb.setEnabled(True)
                cb.setChecked(False)
            for d in active_days:
                if 1 <= d <= 7:
                    self.day_checkboxes[d - 1].setChecked(True)
        else:
            self.all_days_cb.setChecked(True)
            for cb in self.day_checkboxes:
                cb.setChecked(True)
                cb.setEnabled(False)

    def browse_collection(self):
        """Override to load selected collection."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Collection File", "", "JSON Files (*.json);;All Files (*)"
        )
        if file_path:
            self.load_collection(file_path)

    def load_collection(self, file_path: str):
        """Load collection JSON and populate video list (no blacklist handling)."""
        collection_videos, collection_info_dict = load_collection_json(file_path)
        self.collection_path.setText(file_path)
        self.videos_list.clear()
        self.collection_videos = collection_videos
        self.collection_info_dict = collection_info_dict
        for video in collection_videos:
            path = video.get('path', '')
            duration = video.get('duration', 0)
            display_name = get_video_display_name(video)
            item = QListWidgetItem(f"{display_name} ({format_duration(duration)})")
            item.setData(Qt.UserRole, path)
            self.videos_list.addItem(item)
        self._on_collection_loaded()

    def auto_calc_end_time(self):
        """Calculate end time based on series parsing and video count."""
        if not self.collection_videos:
            return
        start_season = self.start_season_spin.value()
        start_episode = self.start_episode_spin.value()
        play_mode = self.play_mode_combo.currentText()
        video_count = self.video_count_spin.value()

        videos_to_use, _ = parse_videos_for_series(
            self.collection_videos,
            start_season,
            start_episode,
            play_mode,
            video_count
        )
        total_duration = sum(v['video'].get('duration', 0) for v in videos_to_use)
        total_mins = int(total_duration // 60)
        start_mins = qtime_to_minutes(self.start_time_edit.time())
        end_mins = (start_mins + total_mins) % (24 * 60)
        self.end_time_edit.setTime(QTime(end_mins // 60, end_mins % 60))

    def load_blacklist_file(self, file_path: str = ""):
        """Load blacklist from file (overrides mixin's version, does not manage added videos)."""
        if not file_path:
            file_path, _ = QFileDialog.getOpenFileName(
                self, "Select Blacklist File", "", "INI Files (*.ini);;JSON Files (*.json);;All Files (*)"
            )
        if not file_path:
            return
        self.blacklist = load_blacklist_json(file_path)

    def check_missing_videos(self):
        """Check which collection videos still exist on disk and mark missing ones in red."""
        missing_count = 0
        for i in range(self.videos_list.count()):
            item = self.videos_list.item(i)
            path = item.data(Qt.UserRole)
            if not path or not Path(path).exists():
                item.setForeground(QColor("red"))
                missing_count += 1
        if missing_count:
            QMessageBox.information(self, "Missing Videos",
                f"{missing_count} of {self.videos_list.count()} videos are missing on disk.")

    def get_tag(self) -> Tag:
        """Construct Tag from current state."""
        name = self.name_input.text() or "Series Tag"
        self.auto_calc_end_time()
        collection_profile = self.collection_profile_combo.currentText()
        if collection_profile == "-- None --":
            collection_profile = ""
        blacklist_profile = self.blacklist_profile_combo.currentText()
        if blacklist_profile == "-- None --":
            blacklist_profile = ""
        if self.all_days_cb.isChecked():
            active_days = None
        else:
            active_days = [i + 1 for i, cb in enumerate(self.day_checkboxes) if cb.isChecked()]

        return Tag(
            tag_type="custom",
            name=name,
            start_time=self.start_time_edit.time(),
            end_time=self.end_time_edit.time(),
            collection_videos=self.collection_videos.copy(),
            collection_path=self.collection_path.text(),
            video_count=self.video_count_spin.value(),
            is_series=True,
            start_season=self.start_season_spin.value(),
            start_episode=self.start_episode_spin.value(),
            play_mode=self.play_mode_combo.currentText(),
            blacklist=self.blacklist.copy() if hasattr(self, 'blacklist') and self.blacklist else [],
            collection_profile=collection_profile,
            blacklist_profile=blacklist_profile,
            series_end_behavior=self.end_behavior_combo.currentText(),
            series_repeat_season=self.repeat_season_spin.value(),
            series_random_season=self.random_season_spin.value(),
            active_days=active_days
        )


class SeriesConfigDialog(QDialog):
    """Dialog for configuring a single series entry within a MultiSeriesTag."""

    def __init__(self, parent=None, config=None):
        super().__init__(parent)
        self.setWindowTitle("Series Configuration")
        self.setModal(True)
        self.collection_videos = []
        if config:
            self.collection_path_text = config.get('collection_path', '')
            self.collection_videos = config.get('collection_videos', [])
            self.start_season_val = config.get('start_season', 1)
            self.start_episode_val = config.get('start_episode', 1)
            self.video_count_val = config.get('video_count', 1)
            self.play_mode_val = config.get('play_mode', 'sequence')
            self.end_behavior_val = config.get('series_end_behavior', 'stop')
            self.repeat_season_val = config.get('series_repeat_season', 0)
            self.random_season_val = config.get('series_random_season', 0)
            self.active_days_val = config.get('active_days', None)
        else:
            self.collection_path_text = ''
            self.start_season_val = 0
            self.start_episode_val = 1
            self.video_count_val = 1
            self.play_mode_val = 'sequence'
            self.end_behavior_val = 'stop'
            self.repeat_season_val = 0
            self.random_season_val = 0
            self.active_days_val = None
        self.setup_ui()
        if self.collection_path_text:
            self.collection_path.setText(self.collection_path_text)
            self.videos_label.setText(f"Videos: {len(self.collection_videos)}")
        self._restore_active_days()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Collection selection
        coll_layout = QHBoxLayout()
        coll_layout.addWidget(QLabel("Collection:"))
        self.collection_path = QLineEdit()
        self.collection_path.setReadOnly(True)
        coll_layout.addWidget(self.collection_path)
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self.browse_collection)
        coll_layout.addWidget(browse_btn)
        layout.addLayout(coll_layout)

        # Videos count
        self.videos_label = QLabel("Videos: 0")
        layout.addWidget(self.videos_label)

        # Season/episode
        se_layout = QHBoxLayout()
        se_layout.addWidget(QLabel("Start Season:"))
        self.season_spin = QSpinBox()
        self.season_spin.setMinimum(0)
        self.season_spin.setValue(self.start_season_val)
        se_layout.addWidget(self.season_spin)

        se_layout.addWidget(QLabel("Start Episode:"))
        self.episode_spin = QSpinBox()
        self.episode_spin.setMinimum(1)
        self.episode_spin.setValue(self.start_episode_val)
        se_layout.addWidget(self.episode_spin)
        layout.addLayout(se_layout)

        # Video count and play mode
        vc_layout = QHBoxLayout()
        vc_layout.addWidget(QLabel("Video Count:"))
        self.count_spin = QSpinBox()
        self.count_spin.setMinimum(1)
        self.count_spin.setMaximum(9999)
        self.count_spin.setValue(self.video_count_val)
        vc_layout.addWidget(self.count_spin)

        # Active days alongside video count
        vc_layout.addWidget(QLabel("Active Days:"))
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        self.day_checkboxes = []
        for day_name in day_names:
            cb = QCheckBox(day_name)
            cb.setChecked(True)
            cb.stateChanged.connect(self._update_all_days_checkbox)
            vc_layout.addWidget(cb)
            self.day_checkboxes.append(cb)
        self.all_days_cb = QCheckBox("All")
        self.all_days_cb.setChecked(True)
        self.all_days_cb.stateChanged.connect(self._on_all_days_toggled)
        vc_layout.addWidget(self.all_days_cb)

        vc_layout.addWidget(QLabel("Play Mode:"))
        self.play_mode_combo = QComboBox()
        self.play_mode_combo.addItems(["sequence", "season_sequence", "random"])
        self.play_mode_combo.setCurrentText(self.play_mode_val)
        self.play_mode_combo.setToolTip("sequence: order by season/episode\nseason_sequence: season-aware linear order\nrandom: shuffled order")
        vc_layout.addWidget(self.play_mode_combo)

        vc_layout.addWidget(QLabel("End:"))
        self.end_behavior_combo = QComboBox()
        self.end_behavior_combo.addItems(["stop", "repeat", "random"])
        self.end_behavior_combo.setCurrentText(self.end_behavior_val)
        self.end_behavior_combo.setToolTip("stop: stop after last episode\nrepeat: loop from chosen season\nrandom: shuffle without repeats")
        self.end_behavior_combo.currentTextChanged.connect(self._update_end_behavior_ui)
        vc_layout.addWidget(self.end_behavior_combo)

        self.repeat_season_spin = QSpinBox()
        self.repeat_season_spin.setMinimum(0)
        self.repeat_season_spin.setValue(self.repeat_season_val)
        self.repeat_season_spin.setToolTip("Repeat from season (0 = all seasons, 1+ = specific season)")
        self.repeat_season_spin.setVisible(self.end_behavior_val == "repeat")
        vc_layout.addWidget(self.repeat_season_spin)

        self.random_season_spin = QSpinBox()
        self.random_season_spin.setMinimum(0)
        self.random_season_spin.setValue(self.random_season_val)
        self.random_season_spin.setToolTip("Random from season (0 = any season, 1+ = specific season)")
        self.random_season_spin.setVisible(self.end_behavior_val == "random")
        vc_layout.addWidget(self.random_season_spin)

        layout.addLayout(vc_layout)

        # Buttons
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _update_end_behavior_ui(self, behavior: str):
        self.repeat_season_spin.setVisible(behavior == "repeat")
        self.random_season_spin.setVisible(behavior == "random")

    def _on_all_days_toggled(self, checked: bool):
        enabled = not checked
        for cb in self.day_checkboxes:
            cb.setChecked(checked)
            cb.setEnabled(enabled)

    def _update_all_days_checkbox(self):
        all_checked = all(cb.isChecked() for cb in self.day_checkboxes)
        if all_checked:
            self.all_days_cb.setChecked(True)
            for cb in self.day_checkboxes:
                cb.setEnabled(False)

    def _restore_active_days(self):
        if self.active_days_val is not None:
            self.all_days_cb.setChecked(False)
            for cb in self.day_checkboxes:
                cb.setEnabled(True)
                cb.setChecked(False)
            for d in self.active_days_val:
                if 1 <= d <= 7:
                    self.day_checkboxes[d - 1].setChecked(True)
        else:
            self.all_days_cb.setChecked(True)
            for cb in self.day_checkboxes:
                cb.setChecked(True)
                cb.setEnabled(False)

    def browse_collection(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Collection File", "", "JSON Files (*.json);;All Files (*)"
        )
        if file_path:
            self.collection_videos, _ = load_collection_json(file_path)
            self.collection_path.setText(file_path)
            self.videos_label.setText(f"Videos: {len(self.collection_videos)}")

    def get_config(self):
        if self.all_days_cb.isChecked():
            active_days = None
        else:
            active_days = [i + 1 for i, cb in enumerate(self.day_checkboxes) if cb.isChecked()]
        return {
            'collection_videos': self.collection_videos,
            'collection_path': self.collection_path.text(),
            'start_season': self.season_spin.value(),
            'start_episode': self.episode_spin.value(),
            'video_count': self.count_spin.value(),
            'play_mode': self.play_mode_combo.currentText(),
            'series_end_behavior': self.end_behavior_combo.currentText(),
            'series_repeat_season': self.repeat_season_spin.value(),
            'series_random_season': self.random_season_spin.value(),
            'active_days': active_days,
            'name': Path(self.collection_path.text()).stem if self.collection_path.text() else 'Series'
        }


class MultiSeriesDialog(BaseTagDialog):
    """Dialog for creating/editing a multi-series tag."""

    def __init__(self, parent=None, tag: Optional[MultiSeriesTag] = None):
        super().__init__(parent, tag)
        self.setWindowTitle("Edit Multi-Series Tag" if tag else "Add Multi-Series Tag")
        self.setModal(True)
        self.series_configs = []
        self.blacklist_path = ""
        if tag:
            self.series_configs = tag.series_list.copy() if hasattr(tag, 'series_list') else []
            self.blacklist = tag.blacklist.copy() if hasattr(tag, 'blacklist') else []
        self.setup_ui()
        if tag:
            self.name_input.setText(tag.name)
            self.start_time_edit.setTime(tag.start_time)
            self.end_time_edit.setTime(tag.end_time)
        self.refresh_series_list()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Name
        layout.addWidget(QLabel("Name:"))
        self.name_input = QLineEdit()
        layout.addWidget(self.name_input)

        # Series list section
        layout.addWidget(QLabel("Series List:"))
        self.series_list_widget = QListWidget()
        self.series_list_widget.setMinimumHeight(150)
        layout.addWidget(self.series_list_widget)

        # Series buttons
        series_btn_layout = QHBoxLayout()
        add_series_btn = QPushButton("Add Series")
        add_series_btn.clicked.connect(self.add_series)
        series_btn_layout.addWidget(add_series_btn)
        edit_series_btn = QPushButton("Edit Series")
        edit_series_btn.clicked.connect(self.edit_series)
        series_btn_layout.addWidget(edit_series_btn)
        remove_series_btn = QPushButton("Remove Series")
        remove_series_btn.clicked.connect(self.remove_series)
        series_btn_layout.addWidget(remove_series_btn)
        series_btn_layout.addStretch()
        layout.addLayout(series_btn_layout)

        # Preview: total duration
        self.preview_label = QLabel("Total Duration: 0 minutes")
        layout.addWidget(self.preview_label)

        # Time inputs
        time_layout = QHBoxLayout()
        self._setup_time_inputs(time_layout)
        layout.addLayout(time_layout)

        # Auto calc button
        calc_layout = QHBoxLayout()
        self.auto_calc_btn = QPushButton("Auto Calc End Time")
        self.auto_calc_btn.clicked.connect(self.auto_calc_end_time)
        calc_layout.addWidget(self.auto_calc_btn)
        calc_layout.addStretch()
        layout.addLayout(calc_layout)

        # Dialog buttons
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def refresh_series_list(self):
        self.series_list_widget.clear()
        for cfg in self.series_configs:
            coll_name = Path(cfg.get('collection_path', '')).stem if cfg.get('collection_path') else 'No Collection'
            season = cfg.get('start_season', 1)
            episode = cfg.get('start_episode', 1)
            count = cfg.get('video_count', 1)
            mode = cfg.get('play_mode', 'sequence')
            end_behavior = cfg.get('series_end_behavior', 'stop')
            end_str = f", end:{end_behavior}" if end_behavior != "stop" else ""
            display = f"{coll_name}: S{season}E{episode}, {count} eps, {mode}{end_str}"
            self.series_list_widget.addItem(display)
        self.update_preview()

    def add_series(self):
        dlg = SeriesConfigDialog(self)
        if dlg.exec():
            cfg = dlg.get_config()
            self.series_configs.append(cfg)
            self.refresh_series_list()

    def edit_series(self):
        row = self.series_list_widget.currentRow()
        if row < 0:
            return
        current_cfg = self.series_configs[row]
        dlg = SeriesConfigDialog(self, current_cfg)
        if dlg.exec():
            self.series_configs[row] = dlg.get_config()
            self.refresh_series_list()

    def remove_series(self):
        row = self.series_list_widget.currentRow()
        if row >= 0:
            del self.series_configs[row]
            self.refresh_series_list()

    def update_preview(self):
        total_minutes = self.calculate_total_duration()
        self.preview_label.setText(f"Total Duration: {total_minutes} minutes")

    def auto_calc_end_time(self):
        total_minutes = self.calculate_total_duration()
        start_time = self.start_time_edit.time()
        start_mins = qtime_to_minutes(start_time)
        end_mins = (start_mins + total_minutes) % (24 * 60)
        self.end_time_edit.setTime(QTime(end_mins // 60, end_mins % 60))
        self.update_preview()

    def calculate_total_duration(self) -> int:
        total = 0
        for cfg in self.series_configs:
            collection_videos = cfg.get('collection_videos', [])
            start_season = cfg.get('start_season', 1)
            start_episode = cfg.get('start_episode', 1)
            play_mode = cfg.get('play_mode', 'sequence')
            video_count = cfg.get('video_count', 1)
            if not collection_videos:
                total += 60
                continue
            videos_to_use, _ = parse_videos_for_series(
                collection_videos,
                start_season,
                start_episode,
                play_mode,
                video_count
            )
            for v in videos_to_use:
                duration = int(v['video'].get('duration', 90)) // 60
                if duration < 1:
                    duration = 1
                total += duration
        return total

    def get_tag(self) -> MultiSeriesTag:
        name = self.name_input.text() or "Multi-Series"
        return MultiSeriesTag(
            name=name,
            series_list=self.series_configs.copy(),
            start_time=self.start_time_edit.time(),
            end_time=self.end_time_edit.time(),
            blacklist=self.blacklist.copy() if hasattr(self, 'blacklist') and self.blacklist else []
        )
