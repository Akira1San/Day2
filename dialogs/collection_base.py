import json
import logging
import os
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout, QVBoxLayout, QComboBox, QLineEdit, QPushButton, QMessageBox, QTableWidgetItem, QDoubleSpinBox, QHeaderView
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from .base import BaseTagDialog
from .profile_mixin import SeriesProfileMixin
from .widgets.video_list import create_video_section, create_blacklist_section
from utils import (
    load_collection_json, load_blacklist_json, load_rates_json, save_rates_json,
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
    _rates: Dict[str, int]

    def __init__(self, parent=None, tag=None):
        super().__init__(parent, tag)
        self.collection_videos = []
        self.added_videos = []
        self.blacklist = []
        self.blacklist_path = ""
        self.collection_info_dict = {}
        self.collection_dir = Path('.')
        self.covers_root = Path('.')
        self._rates = {}
        self.sort_mode = "name_asc"
        self.search_text = ""
        self.collection_filter = ""
        self.collection_search_text = ""
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
            on_add=self.add_selected_videos,
            on_filter_changed=self._on_collection_filter_changed,
            on_search_changed=self._on_collection_search_changed,
            columns=2
        )
        self.added_section = create_video_section(
            "Added Videos", False,
            on_video_selected=self.on_added_video_selected,
            on_remove=self.remove_selected_added,
            on_remove_all=self.remove_all_added,
            on_clear_selection=self.clear_added_selection,
            on_add_to_blacklist=self.add_to_blacklist,
            on_check_missing=self.check_missing_videos,
            on_sort_changed=self._on_added_sort_changed,
            on_search_changed=self._on_added_search_changed
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

    # --- Rate management ---

    def _on_rate_changed(self, video_path: str, value: float):
        rate = int(value)
        self._rates[video_path] = rate
        for video in self.collection_videos:
            if video.get('path') == video_path:
                video['_rate'] = rate
                break
        for video in self.added_videos:
            if video.get('path') == video_path:
                video['_rate'] = rate
                break

    def accept(self):
        self.save_rates_file()
        super().accept()

    def _load_rates_file(self, file_path: str):
        self._rates = {}
        collection_stem = Path(file_path).stem
        rates_patterns = [
            f"{collection_stem}_rates.json",
            f"{collection_stem.replace('collections_', '')}_rates.json"
        ]
        collection_dir = Path(file_path).parent
        for search_dir in [collection_dir, Path.cwd()]:
            for pattern in rates_patterns:
                for rates_file in search_dir.glob(pattern):
                    self._rates = load_rates_json(str(rates_file))
                    return

    def save_rates_file(self):
        if not self.collection_path.text():
            return
        rates_path = self.collection_path.text().replace('.json', '_rates.json')
        rates_dict = {}
        for video in self.collection_videos:
            path = video.get('path', '')
            if path:
                rates_dict[path] = video.get('_rate', 50)
        save_rates_json(rates_path, rates_dict)

    # --- Video list management ---

    @staticmethod
    def _selected_table_rows(table) -> Set[int]:
        return set(item.row() for item in table.selectedItems())

    def _internal_video_selected(self, item):
        row = self.videos_list.row(item)
        if 0 <= row < self.videos_list.rowCount():
            path = item.data(Qt.UserRole)
            video = next((v for v in self.collection_videos if v.get('path') == path), None)
            if video:
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
        rows = self._selected_table_rows(self.videos_list)
        for row in sorted(rows):
            item = self.videos_list.item(row, 0)
            if not item:
                continue
            path = item.data(Qt.UserRole)
            video = next((v for v in self.collection_videos if v.get('path') == path), None)
            if video is None:
                text = item.text()
                video_name = text.split(' (')[0]
                video = {'name': video_name}
            if video not in self.added_videos:
                if not is_video_in_blacklist(video, self.blacklist):
                    video_copy = video.copy()
                    video_copy['_rate'] = self._rates.get(path, 50)
                    self.added_videos.append(video_copy)
        self.refresh_added_list()

    def remove_selected_added(self):
        scroll_bar = self.added_list.verticalScrollBar()
        scroll_pos = scroll_bar.value() if scroll_bar else 0
        rows = sorted(self._selected_table_rows(self.added_list))
        first_row = rows[0] if rows else None

        paths_to_remove = set()
        for row in rows:
            item = self.added_list.item(row, 0)
            if item:
                paths_to_remove.add(item.data(Qt.UserRole))

        self.added_videos = [v for v in self.added_videos if v.get('path', '') not in paths_to_remove]
        self.refresh_added_list()

        if first_row is not None and self.added_list.rowCount() > 0:
            restore_row = min(first_row, self.added_list.rowCount() - 1)
            item = self.added_list.item(restore_row, 0)
            if item:
                self.added_list.setCurrentCell(restore_row, 0)
                self.added_list.scrollToItem(item)
        elif scroll_bar:
            scroll_bar.setValue(min(scroll_pos, scroll_bar.maximum()))

    def remove_all_added(self):
        self.added_videos = []
        self.refresh_added_list()

    def add_to_blacklist(self):
        rows = sorted(self._selected_table_rows(self.added_list))
        first_row = rows[0] if rows else None

        for row in rows:
            item = self.added_list.item(row, 0)
            if not item:
                continue
            path = item.data(Qt.UserRole)
            for v in self.collection_videos:
                if v.get('path', '') == path:
                    if not is_video_in_blacklist(v, self.blacklist):
                        self.blacklist.append(v.copy())
                    break

        scroll_bar = self.added_list.verticalScrollBar()
        scroll_pos = scroll_bar.value() if scroll_bar else 0

        self.added_videos = filter_videos_by_blacklist(self.added_videos, self.blacklist)
        self.refresh_added_list()
        self.refresh_blacklist_list()

        if first_row is not None and self.added_list.rowCount() > 0:
            restore_row = min(first_row, self.added_list.rowCount() - 1)
            item = self.added_list.item(restore_row, 0)
            if item:
                self.added_list.setCurrentCell(restore_row, 0)
                self.added_list.scrollToItem(item)
        elif scroll_bar:
            scroll_bar.setValue(min(scroll_pos, scroll_bar.maximum()))

    def remove_from_blacklist(self):
        selected_items = self.blacklist_list.selectedItems()
        if not selected_items:
            return
        rows = set(item.row() for item in selected_items)
        paths_to_remove = set()
        for row in rows:
            item = self.blacklist_list.item(row, 0)
            if item:
                paths_to_remove.add(item.data(Qt.UserRole))
        removed_videos = [v for v in self.blacklist if v.get('path') in paths_to_remove]
        self.blacklist = [v for v in self.blacklist if v.get('path') not in paths_to_remove]
        existing_paths = {v.get('path') for v in self.added_videos}
        for v in removed_videos:
            if v.get('path') not in existing_paths:
                v['_rate'] = self._rates.get(v.get('path', ''), 50)
                self.added_videos.append(v)
        self.refresh_added_list()
        self.refresh_blacklist_list()

    def _on_added_sort_changed(self, index):
        combo = self.added_section.sort_combo
        if combo:
            self.sort_mode = combo.itemData(index)
            self.refresh_added_list()

    def _on_added_search_changed(self, text):
        self.search_text = text
        self.refresh_added_list()

    def _on_collection_filter_changed(self, index):
        combo = self.collection_section.filter_combo
        if combo:
            self.collection_filter = combo.itemData(index)
            self.refresh_collection_list()

    def _on_collection_search_changed(self, text):
        self.collection_search_text = text
        self.refresh_collection_list()

    def _populate_collection_filter_combo(self):
        combo = self.collection_section.filter_combo
        if not combo:
            return
        combo.blockSignals(True)
        current = combo.currentData()
        combo.clear()
        combo.addItem("All Collections", "")
        sources = sorted({v.get('_source_name', '') for v in self.collection_videos if v.get('_source_name')})
        for src in sources:
            combo.addItem(src, src)
        idx = combo.findData(current)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        combo.blockSignals(False)

    def refresh_collection_list(self):
        self.videos_list.setRowCount(0)

        filtered = self.collection_videos
        if self.collection_filter:
            filtered = [v for v in filtered if v.get('_source_name') == self.collection_filter]
        if self.collection_search_text:
            search_lower = self.collection_search_text.lower()
            filtered = [v for v in filtered if search_lower in get_video_display_name(v).lower()]

        for video in filtered:
            row = self.videos_list.rowCount()
            self.videos_list.insertRow(row)
            src = video.get('_source_name', '')
            prefix = f"{src}: " if src else ""
            name_item = QTableWidgetItem(f"{prefix}{get_video_display_name(video)}")
            name_item.setData(Qt.UserRole, video.get('path', ''))
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.videos_list.setItem(row, 0, name_item)

            dur_item = QTableWidgetItem(format_duration(video.get('duration', 0)))
            dur_item.setFlags(dur_item.flags() & ~Qt.ItemIsEditable)
            self.videos_list.setItem(row, 1, dur_item)
        self.update_counts()

    def refresh_added_list(self):
        self.added_list.setRowCount(0)

        # Apply sort
        if self.sort_mode == "added_asc":
            sorted_videos = list(self.added_videos)
        elif self.sort_mode == "added_desc":
            sorted_videos = list(reversed(self.added_videos))
        elif self.sort_mode == "name_asc":
            sorted_videos = sorted(self.added_videos, key=lambda v: v.get('path', '').split('/')[-1])
        elif self.sort_mode == "name_desc":
            sorted_videos = sorted(self.added_videos, key=lambda v: v.get('path', '').split('/')[-1], reverse=True)
        else:
            sorted_videos = sorted(self.added_videos, key=lambda v: v.get('path', '').split('/')[-1])

        # Apply search filter (case-insensitive on display name)
        if self.search_text:
            search_lower = self.search_text.lower()
            sorted_videos = [
                v for v in sorted_videos
                if search_lower in get_video_display_name(v).lower()
            ]

        for video in sorted_videos:
            row = self.added_list.rowCount()
            self.added_list.insertRow(row)
            src = video.get('_source_name', '')
            prefix = f"{src}: " if src else ""
            name_item = QTableWidgetItem(f"{prefix}{get_video_display_name(video)}")
            name_item.setData(Qt.UserRole, video.get('path', ''))
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.added_list.setItem(row, 0, name_item)

            dur_item = QTableWidgetItem(format_duration(video.get('duration', 0)))
            dur_item.setFlags(dur_item.flags() & ~Qt.ItemIsEditable)
            self.added_list.setItem(row, 1, dur_item)

            spinbox = QDoubleSpinBox()
            spinbox.setRange(0, 100)
            spinbox.setSuffix("%")
            spinbox.setDecimals(0)
            spinbox.setSingleStep(1)
            spinbox.setValue(video.get('_rate', 50))
            video_path = video.get('path', '')
            spinbox.valueChanged.connect(lambda val, p=video_path: self._on_rate_changed(p, val))
            self.added_list.setCellWidget(row, 2, spinbox)
        self.update_counts()

    def refresh_blacklist_list(self):
        self.blacklist_list.setRowCount(0)
        sorted_blacklist = sorted(self.blacklist, key=lambda v: v.get('path', '').split('/')[-1])
        for video in sorted_blacklist:
            row = self.blacklist_list.rowCount()
            self.blacklist_list.insertRow(row)
            src = video.get('_source_name', '')
            prefix = f"{src}: " if src else ""
            name_item = QTableWidgetItem(f"{prefix}{get_video_display_name(video)}")
            name_item.setData(Qt.UserRole, video.get('path', ''))
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.blacklist_list.setItem(row, 0, name_item)
        self.update_counts()

    def update_counts(self):
        self.collection_section.count_label.setText(f"Count: {len(self.collection_videos)}")
        self.added_section.count_label.setText(f"Count: {len(self.added_videos)}")
        self.blacklist_section.count_label.setText(f"Count: {len(self.blacklist)}")

    def check_missing_videos(self):
        """Check which added videos still exist on disk and mark missing ones in red."""
        missing_count = 0
        for i in range(self.added_list.rowCount()):
            item = self.added_list.item(i, 0)
            if not item:
                continue
            path = item.data(Qt.UserRole)
            if not path or not Path(path).exists():
                item.setForeground(QColor("red"))
                missing_count += 1
        total = self.added_list.rowCount()
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
        self.collection_videos = []
        self.added_videos = []
        if load_blacklist:
            self.blacklist = []

        self.collection_dir = Path(file_path).parent
        self.collection_info_dict = collection_info_dict

        # Load rates file
        self._load_rates_file(file_path)

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
            video_data = video.copy()
            if 'name' not in video_data:
                video_data['name'] = get_video_display_name(video)
            path = video_data.get('path', '')
            video_data['_rate'] = self._rates.get(path, 50)
            self.collection_videos.append(video_data)
            if load_blacklist and is_video_in_blacklist(video_data, blacklist_data):
                self.blacklist.append(video_data)

        self.refresh_blacklist_list()
        self._populate_collection_filter_combo()
        self.refresh_collection_list()

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
