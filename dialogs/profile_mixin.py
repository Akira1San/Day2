"""Mixin providing profile and blacklist loading functionality for dialogs."""

import logging
from pathlib import Path
from PySide6.QtWidgets import QFileDialog, QMessageBox

from utils import get_config_paths, load_blacklist_json, filter_videos_by_blacklist

logger = logging.getLogger(__name__)


class SeriesProfileMixin:
    """
    Mixin class that provides common methods for loading collection profiles,
    blacklist profiles, and handling their selection.

    Expected attributes on the subclass:
    - collection_profile_combo: QComboBox
    - blacklist_profile_combo: QComboBox
    - collection_path: QLineEdit (read-only)
    - blacklist: list (the current blacklist)
    - added_videos: list (for auto-add filtering, optional)
    - collection_videos: list (populated by load_collection)
    - collection_info_dict: dict (optional, for info panel)
    - collection_dir: Path (set by load_collection)
    - load_collection(file_path, load_blacklist=True) method
    - refresh_added_list() method (if using auto-add)
    - refresh_blacklist_list() method
    - update_counts() method
    - videos_list, added_list, blacklist_list as needed

    Subclasses must implement their own load_collection signature compatible with
    load_collection(file_path, load_blacklist=True).
    """

    def browse_collection(self):
        """Open file dialog to select collection JSON."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Collection File", "",
            "JSON Files (*.json);;All Files (*)"
        )
        if file_path:
            self.load_collection(file_path)

    def load_available_profiles(self):
        """Populate collection and blacklist profile combo boxes."""
        self.collection_profile_combo.clear()
        self.blacklist_profile_combo.clear()
        self.collection_profile_combo.addItem("-- None --")
        self.blacklist_profile_combo.addItem("-- None --")

        collection_path, blacklist_path = get_config_paths()

        coll_path = Path(collection_path)
        if coll_path.exists():
            for json_file in sorted(coll_path.glob("*.json")):
                self.collection_profile_combo.addItem(json_file.name)

        # Scan for blacklist files in collection dir, blacklist dir, and current directory
        blacklist_files = {}
        for scan_dir in set([Path(collection_path), Path(blacklist_path), Path('.')]):
            logger.debug(f"load_available_profiles: scanning {scan_dir} for blacklist files")
            if scan_dir.exists():
                for json_file in scan_dir.glob("*_blacklist.json"):
                    blacklist_files[json_file.name] = str(json_file.resolve())

        logger.debug(f"blacklist_files found: {sorted(blacklist_files)}")
        for name in sorted(blacklist_files):
            index = self.blacklist_profile_combo.count()
            self.blacklist_profile_combo.addItem(name)
            self.blacklist_profile_combo.setItemData(index, blacklist_files[name])

    def profile_selected(self, index):
        """Handle selection of a collection profile."""
        if index <= 0:
            return
        file_name = self.collection_profile_combo.currentText()
        collection_path, blacklist_path = get_config_paths()
        file_path = Path(collection_path) / file_name
        if file_path.exists():
            self.load_collection(str(file_path))

        collection_name = Path(file_name).stem
        if collection_name.startswith("collections_"):
            collection_name = collection_name[len("collections_"):]
        # Try to auto-select matching blacklist
        for i in range(self.blacklist_profile_combo.count()):
            bl_name = self.blacklist_profile_combo.itemText(i)
            if collection_name in bl_name:
                self.blacklist_profile_combo.setCurrentIndex(i)
                bl_path = self.blacklist_profile_combo.itemData(i)
                if bl_path and Path(bl_path).exists():
                    self.load_blacklist_file(bl_path)
                else:
                    # Try collection directory first, then config blacklist path
                    bl_file = None
                    if hasattr(self, 'collection_dir') and self.collection_dir:
                        bl_candidate = self.collection_dir / bl_name
                        if bl_candidate.exists():
                            bl_file = bl_candidate
                    if bl_file is None:
                        bl_candidate = Path(blacklist_path) / bl_name
                        if bl_candidate.exists():
                            bl_file = bl_candidate
                    if bl_file is not None:
                        self.load_blacklist_file(str(bl_file))
                break

    def blacklist_profile_selected(self, index):
        """Handle selection of a blacklist profile."""
        if index <= 0:
            return
        file_name = self.blacklist_profile_combo.currentText()
        bl_path = self.blacklist_profile_combo.itemData(index)
        if bl_path and Path(bl_path).exists():
            self.load_blacklist_file(bl_path)
            return
        # Try collection directory first, then config blacklist path
        if hasattr(self, 'collection_dir') and self.collection_dir:
            bl_candidate = self.collection_dir / file_name
            if bl_candidate.exists():
                self.load_blacklist_file(str(bl_candidate))
                return
        _, blacklist_path = get_config_paths()
        file_path = Path(blacklist_path) / file_name
        if file_path.exists():
            self.load_blacklist_file(str(file_path))

    def load_blacklist_file(self, file_path: str = ""):
        """Load blacklist from given file or open file dialog."""
        if not file_path:
            file_path, _ = QFileDialog.getOpenFileName(
                self, "Select Blacklist File", "", "JSON Files (*.json);;All Files (*)"
            )
        if not file_path:
            return
        blacklist_data = load_blacklist_json(file_path)
        self.blacklist = blacklist_data
        self.blacklist_path = file_path
        self.added_videos = filter_videos_by_blacklist(self.added_videos, self.blacklist)
        self.refresh_blacklist_list()
        self.refresh_added_list()
