import json
import logging
from pathlib import Path
from typing import Optional, List, Dict
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QSpinBox,
    QMessageBox, QListWidgetItem, QComboBox, QDialog, QTableWidget,
    QTableWidgetItem, QHeaderView, QPushButton, QFileDialog, QLineEdit
)
from PySide6.QtCore import Qt, QTime

from .collection_base import CollectionDialogBase
from .widgets.info_panel import CollectionInfoPanel, VideoInfoDisplay
from models import Tag
from utils import (
    filter_videos_by_blacklist, get_video_display_name, format_duration,
    qtime_to_minutes, get_config_paths, get_covers_path, get_randomfill_config
)

logger = logging.getLogger(__name__)


class TagDialog(CollectionDialogBase):
    """Dialog for creating/editing custom tags."""

    def __init__(self, parent=None, tag: Optional[Tag] = None):
        super().__init__(parent, tag)
        self.setWindowTitle("Edit Tag" if tag else "Add Custom Tag")
        self.setModal(True)

        # Custom widgets
        self.video_count_spin = QSpinBox()
        self.video_count_spin.setMinimum(1)
        self.video_count_spin.setValue(1)

        # Determine covers root directory
        try:
            collection_path, _ = get_config_paths()
            covers_cfg = get_covers_path()
            if covers_cfg:
                self.covers_root = Path(covers_cfg)
            else:
                self.covers_root = Path(collection_path).parent.parent
        except Exception:
            self.covers_root = Path('.')

        self.info_panel = CollectionInfoPanel(parent=self, covers_root=self.covers_root)
        self.video_info = VideoInfoDisplay()

        # Build UI using common components
        self.build_ui()

        self.end_time_edit.setReadOnly(True)
        self.video_count_spin.valueChanged.connect(self._recalc_end_time)
        self.start_time_edit.timeChanged.connect(self._recalc_end_time)

        # Populate profile combo boxes
        self.load_available_profiles()

        # If editing an existing tag, populate fields
        if tag:
            self._populate_from_tag(tag)

    def build_ui(self):
        main_layout = QHBoxLayout(self)

        # ── Left panel: collection info + video info ──
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(self.info_panel)
        left_layout.addWidget(self.video_info)
        main_layout.addWidget(left)

        # ── Right panel: controls ──
        right = QWidget()
        right_layout = QVBoxLayout(right)

        # Name row
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Name:"))
        name_layout.addWidget(self.name_input)
        name_layout.addStretch()
        right_layout.addLayout(name_layout)

        # Profile selection row
        profile_widget = QWidget()
        profile_layout = QHBoxLayout(profile_widget)
        profile_layout.addWidget(QLabel("Collection Profile:"))
        profile_layout.addWidget(self.collection_profile_combo)
        profile_layout.addWidget(QLabel("Blacklist Profile:"))
        profile_layout.addWidget(self.blacklist_profile_combo)
        profile_layout.addStretch()
        right_layout.addWidget(profile_widget)

        # Collection browse row
        coll_widget = QWidget()
        coll_layout = QHBoxLayout(coll_widget)
        coll_layout.addWidget(QLabel("Collection:"))
        coll_layout.addWidget(self.collection_path)
        coll_layout.addWidget(self.browse_button)
        coll_layout.addStretch()
        right_layout.addWidget(coll_widget)

        # Video sections (collection, added, blacklist)
        video_container = QWidget()
        video_layout = QHBoxLayout(video_container)
        video_layout.addWidget(self.collection_section.widget)
        video_layout.addWidget(self.added_section.widget)
        video_layout.addWidget(self.blacklist_section.widget)
        right_layout.addWidget(video_container)

        # Video count + Active days
        count_layout = QHBoxLayout()
        count_layout.addWidget(QLabel("Video Count:"))
        count_layout.addWidget(self.video_count_spin)
        count_layout.addWidget(QLabel("Active Days:"))
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        self.day_checkboxes = []
        for day_name in day_names:
            cb = QCheckBox(day_name)
            cb.setChecked(True)
            cb.stateChanged.connect(self._update_all_days_checkbox)
            count_layout.addWidget(cb)
            self.day_checkboxes.append(cb)
        self.all_days_cb = QCheckBox("All")
        self.all_days_cb.setChecked(True)
        self.all_days_cb.stateChanged.connect(self._on_all_days_toggled)
        count_layout.addWidget(self.all_days_cb)
        count_layout.addStretch()
        right_layout.addLayout(count_layout)

        # Time inputs + auto calc
        time_layout = QHBoxLayout()
        self._setup_time_inputs(time_layout)
        right_layout.addLayout(time_layout)

        # Save/Cancel buttons
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(self.cancel_btn)
        right_layout.addLayout(btn_layout)

        main_layout.addWidget(right)

    def _populate_from_tag(self, tag: Tag):
        """Fill UI fields from an existing Tag."""
        self.name_input.setText(tag.name)
        self.start_time_edit.setTime(tag.start_time)
        self.end_time_edit.setTime(tag.end_time)

        # Set blacklist from tag (may be overwritten by load_collection below)
        if hasattr(tag, 'blacklist') and tag.blacklist:
            self.blacklist = tag.blacklist.copy()

        if hasattr(tag, 'video_count'):
            self.video_count_spin.setValue(tag.video_count)

        if tag.collection_path:
            self.load_collection(tag.collection_path, load_blacklist=False)
            # Override added_videos with tag's saved collection_videos
            self.added_videos = tag.collection_videos.copy()

        # Set profile combo boxes (triggers may load additional data)
        collection_profile = getattr(tag, 'collection_profile', '')
        if collection_profile:
            idx = self.collection_profile_combo.findText(collection_profile)
            if idx >= 0:
                self.collection_profile_combo.setCurrentIndex(idx)
        else:
            self.collection_profile_combo.setCurrentIndex(0)

        blacklist_profile = getattr(tag, 'blacklist_profile', '')
        if blacklist_profile:
            idx = self.blacklist_profile_combo.findText(blacklist_profile)
            if idx >= 0:
                self.blacklist_profile_combo.setCurrentIndex(idx)
        else:
            self.blacklist_profile_combo.setCurrentIndex(0)

        # Ensure added videos respect current blacklist
        self.added_videos = filter_videos_by_blacklist(self.added_videos, self.blacklist)
        self.refresh_added_list()
        self._recalc_end_time()

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

    def _on_collection_loaded(self):
        """Update info panel after collection is loaded."""
        default_info = next(iter(self.collection_info_dict.values())) if self.collection_info_dict else {}
        self.info_panel.set_collection_info(default_info)
        self.info_panel.set_cover_image(default_info.get('cover'))

    def _on_video_selected(self, video: dict):
        """Handle selection in collection list: update video info and cover."""
        self.video_info.set_video_info(video)
        coll_id = video.get('collection_id', '')
        coll_info = self.collection_info_dict.get(coll_id, {})
        cover_path = coll_info.get('cover', '')
        self.info_panel.set_cover_image(cover_path)

    def on_added_video_selected(self, item):
        """Handle selection in added videos list."""
        path = item.data(Qt.UserRole)
        video = next((v for v in self.added_videos if v.get('path') == path), None)
        if video:
            self.video_info.set_video_info(video)
            coll_id = video.get('collection_id', '')
            if not coll_id:
                for v in self.collection_videos:
                    if v.get('path', '') == path:
                        coll_id = v.get('collection_id', '')
                        break
            coll_info = self.collection_info_dict.get(coll_id, {})
            cover_path = coll_info.get('cover', '')
            self.info_panel.set_cover_image(cover_path)

    def on_blacklist_video_selected(self, item):
        """Handle selection in blacklist."""
        path = item.data(Qt.UserRole)
        video = next((v for v in self.blacklist if v.get('path') == path), None)
        if video:
            self.video_info.set_video_info(video)
            coll_id = video.get('collection_id', '')
            if not coll_id:
                for v in self.collection_videos:
                    if v.get('path', '') == path:
                        coll_id = v.get('collection_id', '')
                        break
            coll_info = self.collection_info_dict.get(coll_id, {})
            cover_path = coll_info.get('cover', '')
            self.info_panel.set_cover_image(cover_path)

    def _recalc_end_time(self):
        if not self.added_videos:
            return
        count = self.video_count_spin.value()
        total_duration = sum(
            self.added_videos[i].get('duration', 0)
            for i in range(min(count, len(self.added_videos)))
        )
        start_mins = qtime_to_minutes(self.start_time_edit.time())
        end_mins = (start_mins + int(total_duration // 60)) % (24 * 60)
        self.end_time_edit.setTime(QTime(end_mins // 60, end_mins % 60))

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

    def refresh_added_list(self):
        super().refresh_added_list()
        self._recalc_end_time()

    def get_tag(self) -> Tag:
        """Construct Tag object from current dialog state."""
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
            name=self.name_input.text() or "Custom Video",
            start_time=self.start_time_edit.time(),
            end_time=self.end_time_edit.time(),
            collection_videos=self.added_videos.copy(),
            collection_path=self.collection_path.text(),
            randomize_videos=True,
            video_count=self.video_count_spin.value(),
            blacklist=self.blacklist.copy(),
            active_days=active_days,
            collection_profile=collection_profile,
            blacklist_profile=blacklist_profile
        )

    # TagDialog uses base class save_blacklist_file (QMessageBox.information)


class RandomFillDialog(CollectionDialogBase):
    """Dialog for creating/editing random fill tags."""

    def __init__(self, parent=None, tag: Optional[Tag] = None):
        super().__init__(parent, tag)
        self.tag = tag
        self.setWindowTitle("Add Random Fill Tag" if not tag else "Edit Random Fill Tag")
        self.setModal(True)

        # Determine covers root directory
        try:
            collection_path, _ = get_config_paths()
            covers_cfg = get_covers_path()
            if covers_cfg:
                self.covers_root = Path(covers_cfg)
            else:
                self.covers_root = Path(collection_path).parent.parent
        except Exception:
            self.covers_root = Path('.')

        # Custom widgets
        self.info_panel = CollectionInfoPanel(parent=self, covers_root=self.covers_root)
        self.video_info = VideoInfoDisplay()

        # Build UI (arranges common widgets plus custom info panel)
        self.build_ui()

        self.end_time_edit.setReadOnly(True)
        self.start_time_edit.timeChanged.connect(self._recalc_end_time)

        # Load profiles
        self.load_available_profiles()

        # Populate from tag if editing
        if tag:
            self._populate_from_tag(tag)

    def build_ui(self):
        main_layout = QHBoxLayout(self)

        # Left panel: collection info and video info
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(self.info_panel)
        left_layout.addWidget(self.video_info)
        main_layout.addWidget(left)

        # Right panel: common UI and random fill controls
        right = QWidget()
        right_layout = QVBoxLayout(right)

        # Name row
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Name:"))
        name_layout.addWidget(self.name_input)
        name_layout.addStretch()
        right_layout.addLayout(name_layout)

        # Profiles row
        profile_widget = QWidget()
        profile_layout = QHBoxLayout(profile_widget)
        profile_layout.addWidget(QLabel("Collection Profile:"))
        profile_layout.addWidget(self.collection_profile_combo)
        profile_layout.addWidget(QLabel("Blacklist Profile:"))
        profile_layout.addWidget(self.blacklist_profile_combo)
        profile_layout.addStretch()
        right_layout.addWidget(profile_widget)

        # Collection browse row
        coll_widget = QWidget()
        coll_layout = QHBoxLayout(coll_widget)
        coll_layout.addWidget(QLabel("Collection:"))
        coll_layout.addWidget(self.collection_path)
        coll_layout.addWidget(self.browse_button)
        coll_layout.addStretch()
        right_layout.addWidget(coll_widget)

        # Video sections container
        video_container = QWidget()
        video_layout = QHBoxLayout(video_container)
        video_layout.addWidget(self.collection_section.widget)
        video_layout.addWidget(self.added_section.widget)
        video_layout.addWidget(self.blacklist_section.widget)
        right_layout.addWidget(video_container)

        # Time inputs
        time_layout = QHBoxLayout()
        self._setup_time_inputs(time_layout)
        right_layout.addLayout(time_layout)

        # Fill 24h checkbox
        self.fill_24h_check = QCheckBox("Fill 24 Hours (loop videos to fill full day)")
        self.fill_24h_check.setChecked(True)
        right_layout.addWidget(self.fill_24h_check)

        # Marathon Mode
        self.marathon_cb = QCheckBox("Marathon Mode (play all day on selected days)")
        self.marathon_cb.setChecked(False)
        right_layout.addWidget(self.marathon_cb)

        # Active Days (for marathon mode)
        active_days_layout = QHBoxLayout()
        active_days_layout.addWidget(QLabel("Active Days:"))
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        self.marathon_day_checkboxes = []
        for day_name in day_names:
            cb = QCheckBox(day_name)
            cb.setChecked(True)
            cb.stateChanged.connect(self._update_marathon_all_days_checkbox)
            active_days_layout.addWidget(cb)
            self.marathon_day_checkboxes.append(cb)
        self.marathon_all_days_cb = QCheckBox("All")
        self.marathon_all_days_cb.setChecked(True)
        self.marathon_all_days_cb.stateChanged.connect(self._on_marathon_all_days_toggled)
        active_days_layout.addWidget(self.marathon_all_days_cb)
        active_days_layout.addStretch()
        right_layout.addLayout(active_days_layout)

        # Collection Tag combo
        tag_combo_layout = QHBoxLayout()
        tag_combo_layout.addWidget(QLabel("Collection Tag:"))
        self.marathon_tag_combo = QComboBox()
        self.marathon_tag_combo.addItem("None", "")
        tag_combo_layout.addWidget(self.marathon_tag_combo)
        tag_combo_layout.addStretch()
        right_layout.addLayout(tag_combo_layout)

        # Connect marathon signals
        self.marathon_cb.toggled.connect(self._on_marathon_toggled)

        # Save/Cancel buttons
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(self.cancel_btn)
        right_layout.addLayout(btn_layout)

        main_layout.addWidget(right)

    def _populate_from_tag(self, tag: Tag):
        """Fill UI fields from an existing Tag."""
        self.name_input.setText(tag.name)
        self.start_time_edit.setTime(tag.start_time)
        self.end_time_edit.setTime(tag.end_time)

        if hasattr(tag, 'blacklist') and tag.blacklist:
            self.blacklist = tag.blacklist.copy()

        fill_24h = getattr(tag, 'fill_24h', False)
        self.fill_24h_check.setChecked(fill_24h)

        if tag.collection_path:
            # Load collection without auto-loading blacklist to preserve tag's blacklist initially
            self.load_collection(tag.collection_path, load_blacklist=False)
            self.added_videos = tag.collection_videos.copy()

        collection_profile = getattr(tag, 'collection_profile', '')
        if collection_profile:
            self.collection_profile_combo.blockSignals(True)
            idx = self.collection_profile_combo.findText(collection_profile)
            if idx >= 0:
                self.collection_profile_combo.setCurrentIndex(idx)
            self.collection_profile_combo.blockSignals(False)

        blacklist_profile = getattr(tag, 'blacklist_profile', '')
        if blacklist_profile:
            idx = self.blacklist_profile_combo.findText(blacklist_profile)
            if idx >= 0:
                self.blacklist_profile_combo.setCurrentIndex(idx)

        # Marathon mode fields
        marathon_mode = getattr(tag, 'marathon_mode', False)
        self.marathon_cb.setChecked(marathon_mode)
        if marathon_mode:
            self.fill_24h_check.setChecked(True)
            self.fill_24h_check.setEnabled(False)
            self.start_time_edit.setEnabled(False)
            self.end_time_edit.setEnabled(False)

        marathon_tag_name = getattr(tag, 'marathon_tag_name', '')
        if marathon_tag_name:
            idx = self.marathon_tag_combo.findData(marathon_tag_name)
            if idx >= 0:
                self.marathon_tag_combo.setCurrentIndex(idx)

        active_days = getattr(tag, 'active_days', None)
        if active_days is not None:
            self.marathon_all_days_cb.setChecked(False)
            for cb in self.marathon_day_checkboxes:
                cb.setEnabled(True)
                cb.setChecked(False)
            for d in active_days:
                if 1 <= d <= 7:
                    self.marathon_day_checkboxes[d - 1].setChecked(True)
        else:
            self.marathon_all_days_cb.setChecked(True)
            for cb in self.marathon_day_checkboxes:
                cb.setChecked(True)
                cb.setEnabled(False)

        # Ensure added videos are filtered by current blacklist
        self.added_videos = filter_videos_by_blacklist(self.added_videos, self.blacklist)
        self.refresh_added_list()
        self._recalc_end_time()

    def _should_auto_add(self) -> bool:
        """Auto-add non-blacklisted videos when loading collection, based on config."""
        return get_randomfill_config()

    def _on_collection_loaded(self):
        """Update info panel after collection is loaded."""
        default_info = next(iter(self.collection_info_dict.values())) if self.collection_info_dict else {}
        self.info_panel.set_collection_info(default_info)
        self.info_panel.set_cover_image(default_info.get('cover'))
        self._populate_marathon_tag_combo()

    def _populate_marathon_tag_combo(self):
        """Populate marathon tag combo from raw tags in collection metadata."""
        current = self.marathon_tag_combo.currentData()
        self.marathon_tag_combo.blockSignals(True)
        self.marathon_tag_combo.clear()
        self.marathon_tag_combo.addItem("None", "")
        all_tags = set()
        for coll_info in self.collection_info_dict.values():
            for t in coll_info.get('tags', []):
                all_tags.add(t)
        for t in sorted(all_tags):
            self.marathon_tag_combo.addItem(t, t)
        idx = self.marathon_tag_combo.findData(current)
        if idx >= 0:
            self.marathon_tag_combo.setCurrentIndex(idx)
        self.marathon_tag_combo.blockSignals(False)

    def _on_marathon_toggled(self, checked: bool):
        """Auto-check fill_24h when marathon mode is enabled."""
        if checked:
            self.fill_24h_check.setChecked(True)
            self.fill_24h_check.setEnabled(False)
            self.start_time_edit.setEnabled(False)
            self.end_time_edit.setEnabled(False)
        else:
            self.fill_24h_check.setEnabled(True)
            self.start_time_edit.setEnabled(True)
            self.end_time_edit.setEnabled(True)

    def _on_marathon_all_days_toggled(self, checked: bool):
        enabled = not checked
        for cb in self.marathon_day_checkboxes:
            cb.setChecked(checked)
            cb.setEnabled(enabled)

    def _update_marathon_all_days_checkbox(self):
        all_checked = all(cb.isChecked() for cb in self.marathon_day_checkboxes)
        if all_checked:
            self.marathon_all_days_cb.setChecked(True)
            for cb in self.marathon_day_checkboxes:
                cb.setEnabled(False)

    def _on_video_selected(self, video: dict):
        """Handle selection in collection list: update video info and cover."""
        self.video_info.set_video_info(video)
        coll_id = video.get('collection_id', '')
        coll_info = self.collection_info_dict.get(coll_id, {})
        cover_path = coll_info.get('cover', '')
        self.info_panel.set_cover_image(cover_path)

    def on_added_video_selected(self, item):
        """Handle selection in added videos list."""
        path = item.data(Qt.UserRole)
        video = next((v for v in self.added_videos if v.get('path') == path), None)
        if video:
            self.video_info.set_video_info(video)
            coll_id = video.get('collection_id', '')
            if not coll_id:
                for v in self.collection_videos:
                    if v.get('path', '') == path:
                        coll_id = v.get('collection_id', '')
                        break
            coll_info = self.collection_info_dict.get(coll_id, {})
            cover_path = coll_info.get('cover', '')
            self.info_panel.set_cover_image(cover_path)

    def on_blacklist_video_selected(self, item):
        """Handle selection in blacklist."""
        path = item.data(Qt.UserRole)
        video = next((v for v in self.blacklist if v.get('path') == path), None)
        if video:
            self.video_info.set_video_info(video)
            coll_id = video.get('collection_id', '')
            if not coll_id:
                for v in self.collection_videos:
                    if v.get('path', '') == path:
                        coll_id = v.get('collection_id', '')
                        break
            coll_info = self.collection_info_dict.get(coll_id, {})
            cover_path = coll_info.get('cover', '')
            self.info_panel.set_cover_image(cover_path)

    def _recalc_end_time(self):
        if not self.added_videos:
            return
        total_duration = sum(v.get('duration', 0) for v in self.added_videos)
        start_mins = qtime_to_minutes(self.start_time_edit.time())
        end_mins = (start_mins + int(total_duration // 60)) % (24 * 60)
        self.end_time_edit.setTime(QTime(end_mins // 60, end_mins % 60))

    def refresh_added_list(self):
        super().refresh_added_list()
        self._recalc_end_time()

    def get_tag(self) -> Optional[Tag]:
        """Construct Tag from dialog state. Returns None if validation fails."""
        if not self.added_videos:
            QMessageBox.warning(self, "No Videos", "Please add at least one video.")
            return None

        fill_24h = self.fill_24h_check.isChecked()
        if fill_24h:
            self.start_time_edit.setTime(QTime(0, 0))
            self.end_time_edit.setTime(QTime(23, 59))

        collection_profile = self.collection_profile_combo.currentText()
        if collection_profile == "-- None --":
            collection_profile = ""
        blacklist_profile = self.blacklist_profile_combo.currentText()
        if blacklist_profile == "-- None --":
            blacklist_profile = ""

        marathon_mode = self.marathon_cb.isChecked()
        marathon_tag_name = self.marathon_tag_combo.currentData() or ""

        active_days = None
        if marathon_mode:
            if self.marathon_all_days_cb.isChecked():
                active_days = None
            else:
                active_days = [i + 1 for i, cb in enumerate(self.marathon_day_checkboxes) if cb.isChecked()]

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
            collection_profile=collection_profile,
            blacklist_profile=blacklist_profile,
            marathon_mode=marathon_mode,
            marathon_tag_name=marathon_tag_name,
            active_days=active_days
        )


class GapTagDialog(QDialog):
    """Dialog for creating/editing gap filler tags with multiple typed collections."""

    GAP_TYPES = ["trailer", "promo", "music", "standby_loop"]

    def __init__(self, parent=None, tag: Optional[Tag] = None):
        super().__init__(parent)
        self.tag = tag
        self.setWindowTitle("Add Gap Tag" if not tag else "Edit Gap Tag")
        self.setModal(True)
        self.resize(650, 500)

        self.name_input = QLineEdit("Gap Fill")
        self.gap_max_spin = QSpinBox()
        self.gap_max_spin.setRange(0, 86400)
        self.gap_max_spin.setValue(0)
        self.gap_max_spin.setSuffix(" sec")
        self.gap_max_spin.setSpecialValueText("No limit")
        self.preserve_boundaries_cb = QCheckBox("Preserve day boundaries (don't split videos across days)")
        self.preserve_boundaries_cb.setChecked(False)

        self.collection_table = QTableWidget(0, 4)
        self.collection_table.setHorizontalHeaderLabels(["", "Collection File", "Type", ""])
        self.collection_table.horizontalHeader().setStretchLastSection(False)
        self.collection_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.collection_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.collection_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.collection_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.collection_table.setColumnWidth(0, 90)
        self.collection_table.setColumnWidth(2, 120)
        self.collection_table.setColumnWidth(3, 50)
        self.collection_table.verticalHeader().setVisible(False)

        self.add_collection_btn = QPushButton("Add Collection")
        self.add_collection_btn.clicked.connect(self._add_empty_row)

        # Active days
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        self.day_checkboxes = []
        self.all_days_cb = QCheckBox("All")
        self.all_days_cb.setChecked(True)

        self.build_ui()

        if tag:
            self._populate_from_tag(tag)
        elif not self.tag:
            self._add_empty_row()

    def build_ui(self):
        layout = QVBoxLayout(self)

        # Name
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Name:"))
        name_row.addWidget(self.name_input)
        layout.addLayout(name_row)

        # Collection table
        layout.addWidget(QLabel("Gap Collections:"))
        layout.addWidget(self.collection_table)
        layout.addWidget(self.add_collection_btn)

        # Max duration + preserve boundaries
        dur_row = QHBoxLayout()
        dur_row.addWidget(QLabel("Max fill per day:"))
        dur_row.addWidget(self.gap_max_spin)
        dur_row.addStretch()
        layout.addLayout(dur_row)
        layout.addWidget(self.preserve_boundaries_cb)

        # Active days
        days_row = QHBoxLayout()
        days_row.addWidget(QLabel("Active Days:"))
        for day_name in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]:
            cb = QCheckBox(day_name)
            cb.setChecked(True)
            cb.stateChanged.connect(self._update_all_days_checkbox)
            days_row.addWidget(cb)
            self.day_checkboxes.append(cb)
        self.all_days_cb.stateChanged.connect(self._on_all_days_toggled)
        days_row.addWidget(self.all_days_cb)
        days_row.addStretch()
        layout.addLayout(days_row)

        # Buttons
        btn_row = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._validate_and_accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _add_empty_row(self, path: str = "", type_str: str = "trailer"):
        row = self.collection_table.rowCount()
        self.collection_table.insertRow(row)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(lambda: self._browse_collection(row))
        self.collection_table.setCellWidget(row, 0, browse_btn)

        path_label = QLabel(path if path else "(none)")
        path_label.setWordWrap(True)
        self.collection_table.setCellWidget(row, 1, path_label)

        type_combo = QComboBox()
        type_combo.addItems(self.GAP_TYPES)
        if type_str in self.GAP_TYPES:
            type_combo.setCurrentIndex(self.GAP_TYPES.index(type_str))
        self.collection_table.setCellWidget(row, 2, type_combo)

        remove_btn = QPushButton("X")
        remove_btn.clicked.connect(lambda: self._remove_row(row))
        self.collection_table.setCellWidget(row, 3, remove_btn)

    def _browse_collection(self, row: int):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Collection JSON", "", "JSON Files (*.json);;All Files (*)"
        )
        if file_path:
            path_label = self.collection_table.cellWidget(row, 1)
            path_label.setText(file_path)

    def _remove_row(self, row: int):
        self.collection_table.removeRow(row)

    def _populate_from_tag(self, tag: Tag):
        self.name_input.setText(tag.name)
        for gc in getattr(tag, 'gap_collections', []):
            self._add_empty_row(
                path=gc.get("path", ""),
                type_str=gc.get("type", "trailer")
            )
        gap_max = getattr(tag, 'gap_max_duration', None)
        if gap_max is not None:
            self.gap_max_spin.setValue(gap_max)
        self.preserve_boundaries_cb.setChecked(
            getattr(tag, 'gap_preserve_boundaries', False)
        )
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

    def _validate_and_accept(self):
        if not self.name_input.text().strip():
            QMessageBox.warning(self, "No Name", "Please enter a name for the gap tag.")
            return
        gap_collections = []
        for row in range(self.collection_table.rowCount()):
            path_label = self.collection_table.cellWidget(row, 1)
            path = path_label.text() if path_label else ""
            if path and path != "(none)":
                gap_collections.append({"path": path, "type": self.collection_table.cellWidget(row, 2).currentText() if self.collection_table.cellWidget(row, 2) else "trailer"})
        if not gap_collections:
            QMessageBox.warning(self, "No Collections", "Please add at least one collection.")
            return
        self.accept()

    def get_tag(self) -> Tag:
        name = self.name_input.text().strip()
        gap_collections = []
        for row in range(self.collection_table.rowCount()):
            path_label = self.collection_table.cellWidget(row, 1)
            type_combo = self.collection_table.cellWidget(row, 2)
            path = path_label.text() if path_label else ""
            type_str = type_combo.currentText() if type_combo else "trailer"
            if path and path != "(none)":
                gap_collections.append({"path": path, "type": type_str})
        gap_max = self.gap_max_spin.value()
        if gap_max == 0:
            gap_max = None
        if self.all_days_cb.isChecked():
            active_days = None
        else:
            active_days = [i + 1 for i, cb in enumerate(self.day_checkboxes) if cb.isChecked()]
        return Tag(
            tag_type="gap",
            name=name,
            start_time=QTime(0, 0),
            end_time=QTime(23, 59),
            is_gap_filler=True,
            gap_collections=gap_collections,
            gap_max_duration=gap_max,
            gap_preserve_boundaries=self.preserve_boundaries_cb.isChecked(),
            active_days=active_days
        )
