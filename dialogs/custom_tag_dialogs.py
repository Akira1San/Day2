import json
import logging
from pathlib import Path
from typing import Optional, List, Dict
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QSpinBox,
    QMessageBox, QComboBox, QDialog, QTableWidget,
    QTableWidgetItem, QHeaderView, QPushButton, QFileDialog, QLineEdit
)
from PySide6.QtCore import Qt, QTime

from .collection_base import CollectionDialogBase
from .widgets.info_panel import CollectionInfoPanel, VideoInfoDisplay
from .widgets.dark_theme import DARK_TABLE_STYLESHEET
from models import Tag
from utils import (
    filter_videos_by_blacklist, get_video_display_name, format_duration,
    qtime_to_minutes, get_config_paths, get_covers_path, get_randomfill_config,
    load_collection_json, load_blacklist_json, load_rates_json, get_video_id
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

        fallback = [
            self.covers_root / 'user' / 'collections' / 'covers' / 'tatkotv' / 'images',
            self.covers_root / 'user' / 'covers' / 'tatkotv',
        ]
        self.info_panel = CollectionInfoPanel(parent=self, covers_root=self.covers_root,
                                              fallback_dirs=fallback)
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
            # (dict copies so dialog edits, incl. _transcoding_mode, don't
            # mutate the original tag before Save).
            self.added_videos = [v.copy() for v in tag.collection_videos]

        # Set profile combo boxes (triggers may load additional data)
        collection_profile = getattr(tag, 'collection_profile', '')
        if collection_profile:
            self.collection_profile_combo.blockSignals(True)
            idx = self.collection_profile_combo.findText(collection_profile)
            if idx >= 0:
                self.collection_profile_combo.setCurrentIndex(idx)
            self.collection_profile_combo.blockSignals(False)
        else:
            self.collection_profile_combo.blockSignals(True)
            self.collection_profile_combo.setCurrentIndex(0)
            self.collection_profile_combo.blockSignals(False)

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
        coll_id = get_video_id(video)
        coll_info = self.collection_info_dict.get(coll_id, {})
        self.info_panel.set_collection_info(coll_info)
        cover_path = coll_info.get('cover', '')
        self.info_panel.set_cover_image(cover_path)

    def on_added_video_selected(self, item):
        """Handle selection in added videos list."""
        vid = item.data(Qt.UserRole)
        video = next((v for v in self.added_videos if get_video_id(v) == vid), None)
        if video:
            self.video_info.set_video_info(video)
            coll_info = self.collection_info_dict.get(get_video_id(video), {})
            self.info_panel.set_collection_info(coll_info)
            cover_path = coll_info.get('cover', '')
            self.info_panel.set_cover_image(cover_path)

    def on_blacklist_video_selected(self, item):
        """Handle selection in blacklist."""
        vid = item.data(Qt.UserRole)
        video = next((v for v in self.blacklist if get_video_id(v) == vid), None)
        if video:
            self.video_info.set_video_info(video)
            coll_info = self.collection_info_dict.get(get_video_id(video), {})
            self.info_panel.set_collection_info(coll_info)
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
            collection_videos=[v.copy() for v in self.added_videos],
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
        fallback = [
            self.covers_root / 'user' / 'collections' / 'covers' / 'tatkotv' / 'images',
            self.covers_root / 'user' / 'covers' / 'tatkotv',
        ]
        self.info_panel = CollectionInfoPanel(parent=self, covers_root=self.covers_root,
                                              fallback_dirs=fallback)
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

        # Collection files header: label left, compact button right
        coll_header = QHBoxLayout()
        coll_header.addWidget(QLabel("Collection Files:"))
        coll_header.addStretch()
        add_coll_btn = QPushButton("Add Collection")
        add_coll_btn.setFixedWidth(130)
        add_coll_btn.clicked.connect(lambda: self._add_collection_row())
        coll_header.addWidget(add_coll_btn)
        right_layout.addLayout(coll_header)

        self.collection_table = QTableWidget(0, 3)
        self.collection_table.setStyleSheet(DARK_TABLE_STYLESHEET)
        self.collection_table.setHorizontalHeaderLabels(["Path", "", ""])
        self.collection_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.collection_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.collection_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.collection_table.setColumnWidth(1, 80)
        self.collection_table.setColumnWidth(2, 80)
        self.collection_table.verticalHeader().setVisible(False)
        right_layout.addWidget(self.collection_table)

        # Video sections container
        self.collection_section.videos_list.setMinimumWidth(450)
        video_container = QWidget()
        video_layout = QHBoxLayout(video_container)
        video_layout.addWidget(self.collection_section.widget)
        video_layout.addWidget(self.added_section.widget)
        video_layout.addWidget(self.blacklist_section.widget)
        right_layout.addWidget(video_container)

        # Time inputs (hidden: Random Fill is always 00:00-23:59)
        time_container = QWidget()
        time_container.setVisible(False)
        time_layout = QHBoxLayout(time_container)
        self._setup_time_inputs(time_layout)
        right_layout.addWidget(time_container)

        # Fill 24h (hidden: Random Fill is always 24h fill)
        self.fill_24h_check = QCheckBox("Fill 24 Hours (loop videos to fill full day)")
        self.fill_24h_check.setChecked(True)
        self.fill_24h_check.setVisible(False)

        # Marathon Mode: checkbox + summary + Configure dialog
        # (replaces the old inline single-tag combo + day checkboxes, which
        # could not express per-day / rotating tags).
        self.marathon_schedule: list = []
        self._available_marathon_tags: list = []
        marathon_row = QHBoxLayout()
        self.marathon_cb = QCheckBox("Marathon Mode (play all day on selected days)")
        self.marathon_cb.setChecked(False)
        marathon_row.addWidget(self.marathon_cb)
        self.marathon_summary_label = QLabel("Marathon off")
        marathon_row.addWidget(self.marathon_summary_label)
        self.marathon_config_btn = QPushButton("Configure...")
        self.marathon_config_btn.setFixedWidth(110)
        self.marathon_config_btn.setEnabled(False)
        self.marathon_config_btn.clicked.connect(self._open_marathon_dialog)
        marathon_row.addWidget(self.marathon_config_btn)
        marathon_row.addStretch()
        right_layout.addLayout(marathon_row)

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

        # Load primary + extra collections
        all_entries = []
        if tag.collection_path:
            all_entries.append({"path": tag.collection_path})
        for entry in getattr(tag, 'extra_collections', []):
            if isinstance(entry, dict):
                all_entries.append(entry)
            else:
                all_entries.append({"path": entry})
        for entry in all_entries:
            self._add_collection_row(entry["path"])
        if all_entries:
            self._reload_all_collections()
            # Enrich tag blacklist entries against freshly loaded videos so
            # matched entries show full metadata (name/duration). Raw
            # video_id entries without a match are kept as-is (the
            # blacklist list renders them via the video_id fallback).
            # Skip when the reload already auto-loaded the blacklist file.
            if self.blacklist and not self.blacklist_path:
                enriched = []
                seen = set()
                for entry in self.blacklist:
                    vid = get_video_id(entry) if isinstance(entry, dict) else ''
                    if vid and vid in seen:
                        continue
                    if vid:
                        seen.add(vid)
                    match = next((cv for cv in self.collection_videos if get_video_id(cv) == vid), None) if vid else None
                    enriched.append(match.copy() if match is not None else (dict(entry) if isinstance(entry, dict) else entry))
                self.blacklist = enriched
            # Preserve session-only transcoding marks from the edited tag
            # (freshly loaded collection dicts have no _transcoding_mode key).
            saved_modes = {}
            for v in getattr(tag, 'collection_videos', []) or []:
                mode = v.get('_transcoding_mode', '')
                if mode in ("transcode", "copy") and get_video_id(v):
                    saved_modes[get_video_id(v)] = mode
            self.added_videos = []
            for v in self.collection_videos:
                v_copy = v.copy()
                mode = saved_modes.get(get_video_id(v_copy))
                if mode:
                    v_copy['_transcoding_mode'] = mode
                self.added_videos.append(v_copy)

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

        # Marathon mode fields (migrate legacy single tag -> schedule)
        marathon_mode = getattr(tag, 'marathon_mode', False)
        try:
            from utils_marathon import migrate_legacy_marathon, normalize_marathon_schedule
            sched = normalize_marathon_schedule(getattr(tag, 'marathon_schedule', []) or [])
            if not sched:
                sched = migrate_legacy_marathon(
                    getattr(tag, 'marathon_tag_name', ''),
                    getattr(tag, 'active_days', None),
                )
        except Exception:
            sched = [dict(e) for e in (getattr(tag, 'marathon_schedule', []) or []) if isinstance(e, dict)]
        self.marathon_schedule = sched
        # Block signals so setting the checkbox doesn't fire the handler;
        # invoke it manually below so button/summary stay in sync.
        self.marathon_cb.blockSignals(True)
        self.marathon_cb.setChecked(marathon_mode)
        self.marathon_cb.blockSignals(False)
        self._on_marathon_toggled(marathon_mode)

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
        """Collect available collection tags for the marathon config dialog."""
        all_tags = set()
        for coll_info in getattr(self, 'collection_info_dict', {}).values():
            for t in coll_info.get('tags', []):
                all_tags.add(t)
        self._available_marathon_tags = sorted(all_tags)
        self._update_marathon_summary()

    def _add_collection_row(self, path: str = ""):
        """Add a row to the collection table, optionally with a pre-set path."""
        row = self.collection_table.rowCount()
        self.collection_table.insertRow(row)

        path_widget = QLineEdit(path)
        path_widget.setReadOnly(True)
        path_widget.setPlaceholderText("Select collection JSON...")
        self.collection_table.setCellWidget(row, 0, path_widget)

        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(lambda: self._browse_collection_row(row))
        self.collection_table.setCellWidget(row, 1, browse_btn)

        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(lambda: self._remove_collection_row(row))
        self.collection_table.setCellWidget(row, 2, remove_btn)

    def _browse_collection_row(self, row: int):
        """Open file dialog to select a collection JSON for the given row."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Collection File", "",
            "JSON Files (*.json);;All Files (*)"
        )
        if file_path:
            path_widget = self.collection_table.cellWidget(row, 0)
            if path_widget:
                path_widget.setText(file_path)
            self._reload_all_collections()

    def _remove_collection_row(self, row: int):
        """Remove a collection row and reload remaining collections."""
        self.collection_table.removeRow(row)
        # Reconnect browse/remove buttons since row indices shifted
        for r in range(self.collection_table.rowCount()):
            browse_btn = self.collection_table.cellWidget(r, 1)
            browse_btn.clicked.disconnect()
            browse_btn.clicked.connect(lambda checked, row=r: self._browse_collection_row(row))
            remove_btn = self.collection_table.cellWidget(r, 2)
            if remove_btn:
                remove_btn.clicked.disconnect()
                remove_btn.clicked.connect(lambda checked, row=r: self._remove_collection_row(row))
        self._reload_all_collections()

    def _reload_all_collections(self):
        """Load videos from all collection paths in the table, merging into collection_videos."""
        self.collection_videos = []
        self.collection_info_dict = {}
        self._rates = {}

        for row in range(self.collection_table.rowCount()):
            path_widget = self.collection_table.cellWidget(row, 0)
            path = path_widget.text() if path_widget else ""
            if path and Path(path).exists():
                coll_name = Path(path).stem
                if coll_name.startswith('collections_'):
                    coll_name = coll_name.replace('collections_', '')
                videos, info = load_collection_json(path)

                # Load rates file for this collection
                collection_stem = Path(path).stem
                rates_patterns = [
                    f"{collection_stem}_rates.json",
                    f"{collection_stem.replace('collections_', '')}_rates.json"
                ]
                collection_dir = Path(path).parent
                found = False
                for search_dir in [collection_dir, Path.cwd()]:
                    for pattern in rates_patterns:
                        for rates_file in search_dir.glob(pattern):
                            self._rates.update(load_rates_json(str(rates_file)))
                            found = True
                            break
                        if found:
                            break
                    if found:
                        break

                for video in videos:
                    v = video.copy()
                    v['_source_name'] = coll_name
                    if 'name' not in v:
                        v['name'] = get_video_display_name(v)
                    v['_rate'] = self._rates.get(get_video_id(v), 50)
                    self.collection_videos.append(v)
                self.collection_info_dict.update(info)

        # Auto-load stem-matching blacklist files for each collection row.
        # Only replaces the current blacklist when at least one file is
        # found, so adding a collection without its own blacklist file
        # never wipes a manually loaded list.
        from serialization import _find_blacklist_for_collection
        discovered = []
        discovered_path = ""
        seen_bl_ids = set()
        for row in range(self.collection_table.rowCount()):
            path_widget = self.collection_table.cellWidget(row, 0)
            path = path_widget.text() if path_widget else ""
            if not path:
                continue
            bl_file = _find_blacklist_for_collection(path)
            if not bl_file:
                continue
            if not discovered_path:
                discovered_path = bl_file
            for entry in load_blacklist_json(bl_file):
                vid = entry.get('video_id', '') if isinstance(entry, dict) else ''
                if not vid or vid in seen_bl_ids:
                    continue
                seen_bl_ids.add(vid)
                match = next((cv for cv in self.collection_videos if get_video_id(cv) == vid), None)
                discovered.append(match.copy() if match is not None else dict(entry))
        if discovered_path:
            self.blacklist = discovered
            self.blacklist_path = discovered_path
            self.added_videos = filter_videos_by_blacklist(self.added_videos, self.blacklist)

        # Keep self.collection_path in sync with the first row
        first_path = ""
        if self.collection_table.rowCount() > 0:
            first_widget = self.collection_table.cellWidget(0, 0)
            if first_widget:
                first_path = first_widget.text()
        self.collection_path.setText(first_path)

        self._populate_collection_filter_combo()
        self.refresh_collection_list()
        self.refresh_blacklist_list()
        self.refresh_added_list()
        self._on_collection_loaded()

    def _on_video_selected(self, video: dict):
        """Handle selection in collection list: update video info and cover."""
        self.video_info.set_video_info(video)
        coll_info = self.collection_info_dict.get(get_video_id(video), {})
        self.info_panel.set_collection_info(coll_info)
        cover_path = coll_info.get('cover', '')
        self.info_panel.set_cover_image(cover_path)

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
        if hasattr(self, 'marathon_config_btn'):
            self.marathon_config_btn.setEnabled(checked)
        self._update_marathon_summary()

    def _open_marathon_dialog(self):
        from .marathon_dialog import MarathonScheduleDialog
        self._populate_marathon_tag_combo()
        dlg = MarathonScheduleDialog(
            self,
            schedule=self.marathon_schedule,
            available_tags=self._available_marathon_tags,
        )
        if dlg.exec():
            self.marathon_schedule = dlg.get_schedule()
            if self.marathon_schedule and not self.marathon_cb.isChecked():
                self.marathon_cb.setChecked(True)
            self._update_marathon_summary()

    def _update_marathon_summary(self):
        if not hasattr(self, 'marathon_summary_label'):
            return
        if not self.marathon_cb.isChecked():
            self.marathon_summary_label.setText("Marathon off")
            return
        try:
            from utils_marathon import summarize_marathon_schedule
            text = summarize_marathon_schedule(self.marathon_schedule)
        except Exception:
            text = f"Marathon: {len(self.marathon_schedule)} rules" if self.marathon_schedule else "Marathon: no rules"
        self.marathon_summary_label.setText(text)

    def on_added_video_selected(self, item):
        """Handle selection in added videos list."""
        vid = item.data(Qt.UserRole)
        video = next((v for v in self.added_videos if get_video_id(v) == vid), None)
        if video:
            self.video_info.set_video_info(video)
            coll_info = self.collection_info_dict.get(get_video_id(video), {})
            self.info_panel.set_collection_info(coll_info)
            cover_path = coll_info.get('cover', '')
            self.info_panel.set_cover_image(cover_path)

    def on_blacklist_video_selected(self, item):
        """Handle selection in blacklist."""
        vid = item.data(Qt.UserRole)
        video = next((v for v in self.blacklist if get_video_id(v) == vid), None)
        if video:
            self.video_info.set_video_info(video)
            coll_info = self.collection_info_dict.get(get_video_id(video), {})
            self.info_panel.set_collection_info(coll_info)
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

        # Always 24h fill: time controls are hidden (see build_ui).
        fill_24h = True
        self.start_time_edit.setTime(QTime(0, 0))
        self.end_time_edit.setTime(QTime(23, 59))

        collection_profile = self.collection_profile_combo.currentText()
        if collection_profile == "-- None --":
            collection_profile = ""
        blacklist_profile = self.blacklist_profile_combo.currentText()
        if blacklist_profile == "-- None --":
            blacklist_profile = ""

        marathon_mode = self.marathon_cb.isChecked()
        try:
            from utils_marathon import normalize_marathon_schedule
            marathon_schedule = normalize_marathon_schedule(
                getattr(self, 'marathon_schedule', []) or [])
        except Exception:
            marathon_schedule = [dict(e) for e in (getattr(self, 'marathon_schedule', []) or [])
                                 if isinstance(e, dict)]
        if marathon_mode and not marathon_schedule:
            QMessageBox.warning(self, "No Marathon Rules",
                                "Marathon mode is on but no rules are configured. "
                                "Click Configure... to add at least one rule.")
            return None
        if not marathon_mode:
            marathon_schedule = []
        # Legacy compat: first rule's tag + union of days.
        marathon_tag_name = marathon_schedule[0]["tag_name"] if marathon_schedule else ""
        active_days = None
        if marathon_mode and marathon_schedule:
            union = set()
            all_days_covered = True
            for e in marathon_schedule:
                days = e.get("active_days", None)
                if days is None:
                    continue
                for d in days:
                    union.add(d)
            has_all = any(e.get("active_days", None) is None for e in marathon_schedule)
            if has_all:
                active_days = None
            else:
                active_days = sorted(union) or None
                if active_days is not None and len(active_days) == 7:
                    active_days = None

        # Collect all paths from the table
        all_entries = []
        for row in range(self.collection_table.rowCount()):
            w = self.collection_table.cellWidget(row, 0)
            if w and w.text():
                all_entries.append({"path": w.text()})
        collection_path = all_entries[0]["path"] if all_entries else self.collection_path.text()
        extra_collections = all_entries[1:] if len(all_entries) > 1 else []

        return Tag(
            tag_type="random",
            name=self.name_input.text() or "Random Fill",
            start_time=self.start_time_edit.time(),
            end_time=self.end_time_edit.time(),
            collection_videos=[v.copy() for v in self.added_videos],
            collection_path=collection_path,
            extra_collections=extra_collections,
            blacklist=self.blacklist.copy(),
            blacklist_path=self.blacklist_path,
            is_random_fill=True,
            fill_24h=fill_24h,
            collection_profile=collection_profile,
            blacklist_profile=blacklist_profile,
            marathon_mode=marathon_mode,
            marathon_tag_name=marathon_tag_name,
            marathon_schedule=marathon_schedule,
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
        self.name_input.setToolTip("Name for this gap filler tag. Displayed in the tag list.")
        self.gap_max_spin = QSpinBox()
        self.gap_max_spin.setRange(0, 86400)
        self.gap_max_spin.setValue(14400)
        self.gap_max_spin.setSuffix(" sec")
        self.gap_max_spin.setSpecialValueText("No limit")
        self.gap_max_spin.setToolTip(
            "Maximum seconds of gap content to insert per day (0 = unlimited).\n"
            "Higher values produce more entries and slower generation.\n"
            "Recommended: 7200–14400 (2–4 h)."
        )
        self.preserve_boundaries_cb = QCheckBox("Preserve day boundaries (don't split videos across days)")
        self.preserve_boundaries_cb.setChecked(False)
        self.preserve_boundaries_cb.setToolTip(
            "If checked, a gap video that would cross midnight is skipped\n"
            "instead of being split across two days."
        )
        self.gap_between_only_cb = QCheckBox("Only fill between tags (leave day edges empty to show gaps)")
        self.gap_between_only_cb.setChecked(False)
        self.gap_between_only_cb.setToolTip(
            "If checked, gap fill only fills gaps BETWEEN scheduled tags.\n"
            "Empty space before the first tag and after the last tag is\n"
            "left unfilled so you can see where extra content is needed."
        )
        self.auto_resolve_cb = QCheckBox("Auto-resolve overlapping tags (push later tags forward to create gaps)")
        self.auto_resolve_cb.setChecked(False)
        self.auto_resolve_cb.setToolTip(
            "If checked, overlapping custom tags are automatically shifted\n"
            "to eliminate overlap, creating a gap that the gap filler fills."
        )
        self.shift_padding_combo = QComboBox()
        self.shift_padding_combo.addItem("1 min", 60)
        self.shift_padding_combo.addItem("2 min", 120)
        self.shift_padding_combo.addItem("3 min", 180)
        self.shift_padding_combo.addItem("5 min", 300)
        self.shift_padding_combo.setCurrentIndex(2)  # default 3 min
        self.shift_padding_combo.setToolTip("Padding added between shifted tags (creates room for gap filler videos).")
        self.estimate_runtime_cb = QCheckBox("Use actual video duration for overlap detection")
        self.estimate_runtime_cb.setChecked(False)
        self.estimate_runtime_cb.setToolTip(
            "If checked, the overlap detector estimates each tag's actual end time\n"
            "by summing video durations. Catches cases where a video extends past\n"
            "the tag's end time, creating unexpected overlaps."
        )

        self.collection_table = QTableWidget(0, 4)
        self.collection_table.setStyleSheet(DARK_TABLE_STYLESHEET)
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
        self.add_collection_btn.setToolTip("Add a row to select a collection JSON file and its content type.")
        self.add_collection_btn.clicked.connect(self._add_empty_row)

        # Active days
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        self.day_checkboxes = []
        self.all_days_cb = QCheckBox("All")
        self.all_days_cb.setChecked(True)
        self.all_days_cb.setToolTip("Check all / uncheck all days. Unchecked days will skip the gap filler.")

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
        layout.addWidget(self.gap_between_only_cb)
        layout.addWidget(self.auto_resolve_cb)
        padding_row = QHBoxLayout()
        padding_row.addWidget(QLabel("    Shift padding:"))
        padding_row.addWidget(self.shift_padding_combo)
        padding_row.addStretch()
        layout.addLayout(padding_row)
        layout.addWidget(self.estimate_runtime_cb)

        # Active days
        days_row = QHBoxLayout()
        days_row.addWidget(QLabel("Active Days:"))
        day_tooltips = [
            "Fill gaps on Mondays", "Fill gaps on Tuesdays", "Fill gaps on Wednesdays",
            "Fill gaps on Thursdays", "Fill gaps on Fridays", "Fill gaps on Saturdays",
            "Fill gaps on Sundays"
        ]
        for day_name, tip in zip(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], day_tooltips):
            cb = QCheckBox(day_name)
            cb.setChecked(True)
            cb.setToolTip(tip)
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
        save_btn.setToolTip("Save this gap tag and add it to the tag list.")
        save_btn.clicked.connect(self._validate_and_accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setToolTip("Discard changes and close.")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _add_empty_row(self, path: str = "", type_str: str = "trailer"):
        row = self.collection_table.rowCount()
        self.collection_table.insertRow(row)

        browse_btn = QPushButton("Browse...")
        browse_btn.setToolTip("Browse for a collection JSON file containing gap content (trailers, promos, etc.).")
        browse_btn.clicked.connect(lambda: self._browse_collection(row))
        self.collection_table.setCellWidget(row, 0, browse_btn)

        path_label = QLabel(path if path else "(none)")
        path_label.setWordWrap(True)
        self.collection_table.setCellWidget(row, 1, path_label)

        type_combo = QComboBox()
        type_combo.addItems(self.GAP_TYPES)
        type_combo.setToolTip(
            "Content type for display purposes only:\n"
            "Trailer / Promo / Music / Standby Loop.\n"
            "Does not affect scheduling order."
        )
        if type_str in self.GAP_TYPES:
            type_combo.setCurrentIndex(self.GAP_TYPES.index(type_str))
        self.collection_table.setCellWidget(row, 2, type_combo)

        remove_btn = QPushButton("X")
        remove_btn.setToolTip("Remove this collection from the gap filler.")
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
        self.gap_between_only_cb.setChecked(
            getattr(tag, 'gap_fill_between_only', False)
        )
        self.auto_resolve_cb.setChecked(
            getattr(tag, 'gap_auto_resolve_overlaps', False)
        )
        padding = getattr(tag, 'gap_shift_padding', 180)
        idx = self.shift_padding_combo.findData(padding)
        if idx >= 0:
            self.shift_padding_combo.setCurrentIndex(idx)
        self.estimate_runtime_cb.setChecked(
            getattr(tag, 'gap_estimate_runtime_overlap', False)
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
            gap_fill_between_only=self.gap_between_only_cb.isChecked(),
            gap_auto_resolve_overlaps=self.auto_resolve_cb.isChecked(),
            gap_shift_padding=self.shift_padding_combo.currentData() or 180,
            gap_estimate_runtime_overlap=self.estimate_runtime_cb.isChecked(),
            active_days=active_days
        )
