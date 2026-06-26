from PySide6.QtWidgets import QListWidget, QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
from PySide6.QtCore import Qt
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Callable


class VideoListWidget(QListWidget):
    """List widget with ExtendedSelection: plain click selects one, Ctrl toggles, Shift ranges."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QListWidget.ExtendedSelection)


@dataclass
class VideoSection:
    """Container for video list section UI components."""
    widget: QWidget
    videos_list: VideoListWidget
    count_label: QLabel


@dataclass
class BlacklistSection:
    """Container for blacklist section UI components."""
    widget: QWidget
    blacklist_list: VideoListWidget
    count_label: QLabel


def create_video_section(
    title: str,
    with_buttons: bool,
    on_video_selected: Optional[Callable] = None,
    on_select_all: Optional[Callable] = None,
    on_clear: Optional[Callable] = None,
    on_add: Optional[Callable] = None,
    on_remove: Optional[Callable] = None,
    on_remove_all: Optional[Callable] = None,
    on_clear_selection: Optional[Callable] = None,
    on_add_to_blacklist: Optional[Callable] = None,
    on_check_missing: Optional[Callable] = None
) -> VideoSection:
    """
    Create a video list section with optional buttons.

    Args:
        title: Section title
        with_buttons: If True, shows Select All/Clear/Add buttons; else shows Remove/Remove All/Clear Selection/Blacklist buttons
        on_video_selected: Callback for video selection
        on_select_all: Callback for Select All button
        on_clear: Callback for Clear button
        on_add: Callback for Add button
        on_remove: Callback for Remove button
        on_remove_all: Callback for Remove All button
        on_clear_selection: Callback for Clear Selection button
        on_add_to_blacklist: Callback for Add to Blacklist button

    Returns:
        VideoSection container with widget, videos_list, and count_label
    """
    widget = QWidget()
    vbox = QVBoxLayout(widget)
    vbox.addWidget(QLabel(title))

    count_label = QLabel("Count: 0")
    vbox.addWidget(count_label)

    if on_check_missing:
        check_missing_btn = QPushButton("Check Missing")
        check_missing_btn.clicked.connect(on_check_missing)
        vbox.addWidget(check_missing_btn)

    videos_list = VideoListWidget()
    videos_list.setMinimumHeight(200)
    if on_video_selected:
        videos_list.itemClicked.connect(on_video_selected)
    vbox.addWidget(videos_list)

    btn_layout = QHBoxLayout()
    if with_buttons:
        if on_select_all:
            select_all_btn = QPushButton("Select All")
            select_all_btn.clicked.connect(on_select_all)
            btn_layout.addWidget(select_all_btn)
        if on_clear:
            clear_btn = QPushButton("Clear")
            clear_btn.clicked.connect(on_clear)
            btn_layout.addWidget(clear_btn)
        if on_add:
            add_btn = QPushButton("Add >>")
            add_btn.clicked.connect(on_add)
            btn_layout.addWidget(add_btn)
    else:
        if on_remove:
            remove_btn = QPushButton("<< Remove")
            remove_btn.clicked.connect(on_remove)
            btn_layout.addWidget(remove_btn)
        if on_remove_all:
            remove_all_btn = QPushButton("Remove All")
            remove_all_btn.clicked.connect(on_remove_all)
            btn_layout.addWidget(remove_all_btn)
        if on_clear_selection:
            clear_sel_btn = QPushButton("Clear Selection")
            clear_sel_btn.clicked.connect(on_clear_selection)
            btn_layout.addWidget(clear_sel_btn)
        if on_add_to_blacklist:
            blacklist_btn = QPushButton("Add to Blacklist >>")
            blacklist_btn.clicked.connect(on_add_to_blacklist)
            btn_layout.addWidget(blacklist_btn)
    vbox.addLayout(btn_layout)

    return VideoSection(widget=widget, videos_list=videos_list, count_label=count_label)


def create_blacklist_section(
    on_remove: Optional[Callable] = None,
    on_clear_selection: Optional[Callable] = None,
    on_load: Optional[Callable] = None,
    on_save: Optional[Callable] = None,
    on_video_selected: Optional[Callable] = None
) -> BlacklistSection:
    """
    Create a blacklist management section.

    Args:
        on_remove: Callback for Remove button
        on_clear_selection: Callback for Clear Selection button
        on_load: Callback for Load button
        on_save: Callback for Save button
        on_video_selected: Callback for video selection

    Returns:
        BlacklistSection container with widget, blacklist_list, and count_label
    """
    widget = QWidget()
    vbox = QVBoxLayout(widget)
    vbox.addWidget(QLabel("Blacklist"))

    count_label = QLabel("Count: 0")
    vbox.addWidget(count_label)

    blacklist_list = VideoListWidget()
    blacklist_list.setMinimumHeight(200)
    if on_video_selected:
        blacklist_list.itemClicked.connect(on_video_selected)
    vbox.addWidget(blacklist_list)

    btn_layout = QHBoxLayout()
    if on_remove:
        remove_btn = QPushButton("<< Remove")
        remove_btn.clicked.connect(on_remove)
        btn_layout.addWidget(remove_btn)
    if on_clear_selection:
        clear_btn = QPushButton("Clear Selection")
        clear_btn.clicked.connect(on_clear_selection)
        btn_layout.addWidget(clear_btn)
    if on_load:
        load_btn = QPushButton("Load")
        load_btn.clicked.connect(on_load)
        btn_layout.addWidget(load_btn)
    if on_save:
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(on_save)
        btn_layout.addWidget(save_btn)

    vbox.addLayout(btn_layout)

    return BlacklistSection(widget=widget, blacklist_list=blacklist_list, count_label=count_label)
