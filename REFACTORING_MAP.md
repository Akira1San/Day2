# Refactoring Map: dialogs.py → dialogs/ package

This document maps original line numbers in `dialogs.py` to their new locations after refactoring.

## Classes and Major Components

| Component | Original Location (lines) | New Location |
|-----------|---------------------------|--------------|
| VideoListWidget class | dialogs.py:28-32 | dialogs/widgets/video_list.py |
| BaseTagDialog class | dialogs.py:39-60 | dialogs/base.py |
| TagDialog class | dialogs.py:65-622 | dialogs/custom_tag_dialogs.py |
| RandomFillDialog class | dialogs.py:623-1315 | dialogs/custom_tag_dialogs.py |
| ConfigDialog class | dialogs.py:1318-1429 | dialogs/config_dialog.py |
| SeriesDialog class | dialogs.py:1432-1727 | dialogs/series_dialogs.py |
| SeriesConfigDialog class | dialogs.py:1730-1822 | dialogs/series_dialogs.py |
| MultiSeriesDialog class | dialogs.py:1825-1977 | dialogs/series_dialogs.py |
| SchedulePreviewDialog class | dialogs.py:1980-2104 | dialogs/preview_dialog.py |

## Helper Widgets and Data Classes

| Component | Original | New Location |
|-----------|----------|--------------|
| VideoSection dataclass (inline type) | dialogs.py:241-243 | dialogs/widgets/video_list.py |
| BlacklistSection dataclass (inline type) | dialogs.py:277-279 | dialogs/widgets/video_list.py |
| `_create_video_list_section()` logic | TagDialog lines 195-244, RandomFillDialog lines 798-847 | dialogs/widgets/video_list.py: `create_video_section()` |
| `_create_blacklist_section()` logic | TagDialog lines 246-280, RandomFillDialog lines 849-883 | dialogs/widgets/video_list.py: `create_blacklist_section()` |
| CollectionInfoPanel (embedded in RandomFillDialog) | RandomFillDialog lines 682-711 | dialogs/widgets/info_panel.py: `CollectionInfoPanel` |
| Info panel cover display logic | RandomFillDialog lines 1112-1141 | dialogs/widgets/info_panel.py: `CollectionInfoPanel.set_cover_image` |
| VideoInfoDisplay (QLabel wrapper) | RandomFillDialog video_info QLabel | dialogs/widgets/info_panel.py: `VideoInfoDisplay` |

## Shared Logic Extraction

| Shared Logic | Original Locations | New Location |
|--------------|-------------------|--------------|
| Profile/blacklist loading methods (`load_available_profiles`, `profile_selected`, `blacklist_profile_selected`, `load_blacklist_file`, `browse_collection`) | TagDialog lines 471-554, RandomFillDialog lines 893-979, SeriesDialog lines 1581-1675 | dialogs/profile_mixin.py: `SeriesProfileMixin` |
| Collection/base dialog logic (`setup_common_ui`, video list management, load_collection, auto_calc, etc.) | TagDialog & RandomFillDialog shared code (~500 lines) | dialogs/collection_base.py: `CollectionDialogBase` |
| Base class with time inputs | BaseTagDialog lines 46-60 | dialogs/base.py |

## Import Changes

All imports from `dialogs` remain unchanged due to `dialogs/__init__.py` re-exporting:

```python
from dialogs import TagDialog, RandomFillDialog, SeriesDialog, SeriesConfigDialog, MultiSeriesDialog, ConfigDialog, SchedulePreviewDialog, BaseTagDialog, VideoListWidget, CollectionInfoPanel, VideoInfoDisplay
```

No changes required in consuming code (e.g., `daypart_scheduler.py`).

## Notes

- The original `dialogs.py` file (2104 lines) has been removed. Its contents are now spread across **10 files** in the `dialogs/` package.
- Debug `print("[DEBUG]...")` statements have been removed.
- All functionality is preserved; UI behavior unchanged.
- Circular dependencies avoided: dialogs depend on utils/models, not vice versa.
