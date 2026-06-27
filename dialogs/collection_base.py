import json
import logging
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout, QVBoxLayout, QComboBox, QLineEdit, QPushButton, QMessageBox, QListWidgetItem
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from .base import BaseTagDialog
from .profile_mixin import SeriesProfileMixin
from .widgets.video_list import create_video_section, create_blacklist_section
from utils import (
    load_collection_json, load_blacklist_json,
    get_video_display_name, format_duration,
    filter_videos_by_blacklist, is_video_in_blacklist,
    get_randomfill_config
)

logger = logging.getLogger(__name__)


class CollectionDialogBase(BaseTagDialog, SeriesProfileMixin):
    """
    Base class for dialogs managing collections, blacklists, and video lists.

    Provides shared functionality for TagDialog and RandomFillDialog, eliminating
    code duplication. Subclasses must implement get_tag() and may override
    _on_video_selected(), _should_auto_add(), and _on_collection_loaded().
    """

    # UI components (created in setup_common_ui)
    name_input: QLineEdit
    collection_profile_combo: QComboBox
    blacklist_profile_combo: QComboBox
    collection_path: QLineEdit
    browse_button: QPushButton
    collection_section: Any  # VideoSection
    added_section: Any     # VideoSection
    blacklist_section: Any # BlacklistSection
    save_btn: QPushButton
    cancel_btn: QPushButton

    # Additional attributes
    collection_videos: List[dict]
    added_videos: List[dict]
    blacklist: List[dict]
    blacklist_path: str
    collection_info_dict: Dict[str, dict]
    collection_dir: Path
    covers_root: Path

    def __init__(self, parent=None, tag=None):
        super().__init__(parent, tag)
        self.collection_videos = []
        self.added_videos = []
        self.blacklist = []
        self.blacklist_path = ""
        self.collection_info_dict = {}
        self.collection_dir = Path('.')
        self.covers_root = Path('.')
        self.setup_common_ui()

    def setup_common_ui(self):
        """Create all common widgets. Should be called by subclass during UI construction."""
        # Name input
        self.name_input = QLineEdit()

        # Profile combo boxes
        self.collection_profile_combo = QComboBox()
        self.collection_profile_combo.currentIndexChanged.connect(self.profile_selected)
        self.blacklist_profile_combo = QComboBox()
        self.blacklist_profile_combo.currentIndexChanged.connect(self.blacklist_profile_selected)

        # Collection path and browse
        self.collection_path = QLineEdit()
        self.collection_path.setPlaceholderText("Select collections_name.json...")
        self.collection_path.setReadOnly(True)
        self.browse_button = QPushButton("Browse")
        self.browse_button.clicked.connect(self.browse_collection)

        # Video sections
        self.collection_section = create_video_section(
            "Videos in Collection", True,
            on_video_selected=self._internal_video_selected,
            on_select_all=self.select_all_videos,
            on_clear=self.clear_selection,
            on_add=self.add_selected_videos
        )
        self.added_section = create_video_section(
            "Added Videos", False,
            on_video_selected=self.on_added_video_selected,
            on_remove=self.remove_selected_added,
            on_remove_all=self.remove_all_added,
            on_clear_selection=self.clear_added_selection,
            on_add_to_blacklist=self.add_to_blacklist,
            on_check_missing=self.check_missing_videos
        )
        self.blacklist_section = create_blacklist_section(
            on_video_selected=self.on_blacklist_video_selected,
            on_remove=self.remove_from_blacklist,
            on_clear_selection=self.clear_blacklist_selection,
            on_load=self.load_blacklist_file,
            on_save=self.save_blacklist_file
        )

        # Expose lists and count labels as direct attributes for compatibility
        self.videos_list = self.collection_section.videos_list
        self.videos_count_label = self.collection_section.count_label
        self.added_list = self.added_section.videos_list
        self.added_count_label = self.added_section.count_label
        self.blacklist_list = self.blacklist_section.blacklist_list
        self.blacklist_count_label = self.blacklist_section.count_label

        # Save/Cancel buttons
        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self.accept)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)

    # --- Video list management ---
    def _internal_video_selected(self, item):
        row = self.videos_list.row(item)
        if 0 <= row < len(self.collection_videos):
            video = self.collection_videos[row]
            self._on_video_selected(video)

    def _on_video_selected(self, video: dict):
        """Override to handle video selection from collection."""
        pass

    def on_added_video_selected(self, item):
        """Override to handle selection in added videos list."""
        pass

    def on_blacklist_video_selected(self, item):
        """Override to handle selection in blacklist."""
        pass

    def select_all_videos(self):
        self.videos_list.selectAll()

    def clear_selection(self):
        self.videos_list.clearSelection()

    def clear_added_selection(self):
        self.added_list.clearSelection()

    def clear_blacklist_selection(self):
        self.blacklist_list.clearSelection()

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
                if not is_video_in_blacklist(video, self.blacklist):
                    self.added_videos.append(video.copy())
        self.refresh_added_list()

    def remove_selected_added(self):
        for item in self.added_list.selectedItems():
            video_name = item.text().split(' (')[0]
            self.added_videos = [v for v in self.added_videos if v.get('name', '') != video_name]
        self.refresh_added_list()

    def remove_all_added(self):
        self.added_videos = []
        self.refresh_added_list()

    def add_to_blacklist(self):
        for item in self.added_list.selectedItems():
            video_name = item.text().split(' (')[0]
            for v in self.collection_videos:
                if v.get('name', '') == video_name or v.get('path', '').split('/')[-1] == video_name:
                    if not is_video_in_blacklist(v, self.blacklist):
                        self.blacklist.append(v.copy())
                    break
        self.added_videos = filter_videos_by_blacklist(self.added_videos, self.blacklist)
        self.refresh_added_list()
        self.refresh_blacklist_list()

    def remove_from_blacklist(self):
        selected_items = self.blacklist_list.selectedItems()
        if not selected_items:
            return
        paths_to_remove = {item.data(Qt.UserRole) for item in selected_items}
        removed_videos = [v for v in self.blacklist if v.get('path') in paths_to_remove]
        self.blacklist = [v for v in self.blacklist if v.get('path') not in paths_to_remove]
        existing_paths = {v.get('path') for v in self.added_videos}
        for v in removed_videos:
            if v.get('path') not in existing_paths:
                self.added_videos.append(v)
        self.refresh_added_list()
        self.refresh_blacklist_list()

    def refresh_added_list(self):
        self.added_list.clear()
        sorted_added = sorted(self.added_videos, key=lambda v: v.get('path', '').split('/')[-1])
        for video in sorted_added:
            src = video.get('_source_name', '')
            prefix = f"{src}: " if src else ""
            item = QListWidgetItem(f"{prefix}{get_video_display_name(video)} ({format_duration(video.get('duration', 0))})")
            item.setData(Qt.UserRole, video.get('path', ''))
            self.added_list.addItem(item)
        self.update_counts()

    def refresh_blacklist_list(self):
        self.blacklist_list.clear()
        sorted_blacklist = sorted(self.blacklist, key=lambda v: v.get('path', '').split('/')[-1])
        for video in sorted_blacklist:
            src = video.get('_source_name', '')
            prefix = f"{src}: " if src else ""
            item = QListWidgetItem(f"{prefix}{get_video_display_name(video)}")
            item.setData(Qt.UserRole, video.get('path', ''))
            self.blacklist_list.addItem(item)
        self.update_counts()

    def update_counts(self):
        self.collection_section.count_label.setText(f"Count: {len(self.collection_videos)}")
        self.added_section.count_label.setText(f"Count: {len(self.added_videos)}")
        self.blacklist_section.count_label.setText(f"Count: {len(self.blacklist)}")

    def check_missing_videos(self):
        """Check which added videos still exist on disk and mark missing ones in red."""
        missing_count = 0
        for i in range(self.added_list.count()):
            item = self.added_list.item(i)
            path = item.data(Qt.UserRole)
            if not path or not Path(path).exists():
                item.setForeground(QColor("red"))
                missing_count += 1
        total = self.added_list.count()
        if missing_count:
            self.added_section.count_label.setText(f"Count: {total}  ({missing_count} missing)")
            QMessageBox.information(self, "Missing Videos",
                f"{missing_count} of {total} added videos are missing on disk.")
        else:
            self.added_section.count_label.setText(f"Count: {total}")

    # --- Collection loading ---
    def load_collection(self, file_path: str, load_blacklist: bool = True):
        """Load collection JSON and populate video list. Optionally load blacklist."""
        collection_videos, collection_info_dict = load_collection_json(file_path)
        self.collection_path.setText(file_path)
        self.videos_list.clear()
        self.collection_videos = []
        self.added_videos = []
        if load_blacklist:
            self.blacklist = []

        self.collection_dir = Path(file_path).parent
        self.collection_info_dict = collection_info_dict

        # Find matching blacklist file if needed
        blacklist_data = []
        if load_blacklist:
            collection_stem = Path(file_path).stem
            blacklist_patterns = [
                f"{collection_stem}_blacklist.json",
                f"{collection_stem.replace('collections_', '')}_blacklist.json"
            ]
            for search_dir in [self.collection_dir, Path.cwd()]:
                for pattern in blacklist_patterns:
                    for bl_file in search_dir.glob(pattern):
                        blacklist_data = load_blacklist_json(str(bl_file))
                        break
                    if blacklist_data:
                        break
                if blacklist_data:
                    break

        # Populate collection videos
        for video in collection_videos:
            path = video.get('path', '')
            duration = video.get('duration', 0)
            video_data = video.copy()
            if 'name' not in video_data:
                video_data['name'] = get_video_display_name(video)
            self.collection_videos.append(video_data)
            self.videos_list.addItem(f"{video_data['name']} ({format_duration(duration)})")
            if load_blacklist and is_video_in_blacklist(video_data, blacklist_data):
                self.blacklist.append(video_data)

        self.refresh_blacklist_list()

        # Auto-add non-blacklisted videos if applicable
        if load_blacklist and self._should_auto_add():
            for video in self.collection_videos:
                path = video.get('path', '')
                if not is_video_in_blacklist(video, self.blacklist) and video not in self.added_videos:
                    self.added_videos.append(video.copy())
            self.refresh_added_list()

        # Subclass hook
        self._on_collection_loaded()

    def _should_auto_add(self) -> bool:
        """Return True if non-blacklisted videos should be auto-added when collection loads."""
        return get_randomfill_config()

    def _on_collection_loaded(self):
        """Hook called after collection is loaded. Override in subclasses for custom UI updates."""
        pass

    # --- Profile handling ---


    def save_blacklist_file(self):
        if not self.collection_path.text():
            return
        blacklist_path = self.collection_path.text().replace('.json', '_blacklist.json')
        stripped = []
        for e in self.blacklist:
            entry = {'path': e.get('path', '')}
            cid = e.get('collection_id', '')
            if cid:
                entry['collection_id'] = cid
            elif self.collection_videos:
                for cv in self.collection_videos:
                    if cv.get('path') == entry['path'] and cv.get('collection_id'):
                        entry['collection_id'] = cv['collection_id']
                        break
            stripped.append(entry)
        blacklist_data = {'blacklist': stripped}
        try:
            with open(blacklist_path, 'w') as f:
                json.dump(blacklist_data, f, indent=2)
            QMessageBox.information(self, "Saved", f"Blacklist saved to {blacklist_path}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to save blacklist: {e}")

    # --- Abstract method ---
    def get_tag(self):
        raise NotImplementedError("Subclasses must implement get_tag()")
