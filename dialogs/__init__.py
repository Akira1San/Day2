"""Dialogs package - refactored from dialogs.py.

This package provides all dialog classes for the Daypart Scheduler application.
It maintains backward compatibility with the original dialogs.py module.

Main dialog classes:
- TagDialog: Create/edit custom tags
- RandomFillDialog: Create random fill tags
- SeriesDialog: Create series tag
- SeriesConfigDialog: Configure a single series
- MultiSeriesDialog: Create multi-series tag
- ConfigDialog: Application configuration
- SchedulePreviewDialog: Preview schedule calendar
- DurationDebugDialog: Debug video durations vs collection data

Base classes:
- BaseTagDialog: Base for tag-related dialogs
- CollectionDialogBase: Shared base for TagDialog and RandomFillDialog

Widgets:
- VideoListWidget: Custom list widget with extended selection
- CollectionInfoPanel: Displays collection metadata and cover
- VideoInfoDisplay: Shows selected video details
"""

from .base import BaseTagDialog
from .widgets.video_list import VideoListWidget
from .widgets.info_panel import CollectionInfoPanel, VideoInfoDisplay
from .collection_base import CollectionDialogBase
from .custom_tag_dialogs import TagDialog, RandomFillDialog, GapTagDialog
from .series_dialogs import SeriesDialog, SeriesConfigDialog, MultiSeriesDialog
from .config_dialog import ConfigDialog
from .preview_dialog import SchedulePreviewDialog
from .duration_debug_dialog import DurationDebugDialog

__all__ = [
    'TagDialog',
    'RandomFillDialog',
    'GapTagDialog',
    'SeriesDialog',
    'SeriesConfigDialog',
    'MultiSeriesDialog',
    'ConfigDialog',
    'SchedulePreviewDialog',
    'DurationDebugDialog',
    'BaseTagDialog',
    'CollectionDialogBase',
    'VideoListWidget',
    'CollectionInfoPanel',
    'VideoInfoDisplay',
]
