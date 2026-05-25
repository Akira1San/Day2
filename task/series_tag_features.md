# Series Tag Enhancements

## 1. Collection Info Panel (Left Side)

### Overview
Add a collection info panel to the SeriesDialog, matching what RandomFillDialog has — cover image, collection name, description, genre, year on the left side.

### Current State
- `SeriesDialog` extends `BaseTagDialog` + `SeriesProfileMixin` and uses a single `QVBoxLayout` with all controls stacked vertically
- `RandomFillDialog` uses `CollectionDialogBase` which provides a `QHBoxLayout` with left panel (info) and right panel (controls)

### Required Changes

**dialogs/series_dialogs.py — SeriesDialog.setup_ui()**
- Replace `QVBoxLayout` with `QHBoxLayout` main layout
- Create left panel widget with `CollectionInfoPanel` + `VideoInfoDisplay`
- Move existing controls to right panel widget
- Wire up `_on_collection_loaded()` and video selection signals

**Imports needed:**
```python
from .widgets.info_panel import CollectionInfoPanel, VideoInfoDisplay
from utils import get_covers_path
from pathlib import Path
```

**Suggested layout structure:**
```
QHBoxLayout
├── Left QWidget (QVBoxLayout)
│   ├── CollectionInfoPanel  (cover, name, desc, genre, year)
│   └── VideoInfoDisplay     (selected video details)
└── Right QWidget (QVBoxLayout) — existing controls
    ├── Name
    ├── Profiles row
    ├── Collection browse
    ├── Videos list
    ├── Series options row (season/episode/count/mode/end)
    ├── Auto calc
    ├── Time inputs
    └── Save/Cancel
```

**Additional wiring:**
- Override `load_collection` to call `_on_collection_loaded()` which updates info panel
- Connect videos list selection to update info_panel cover and video_info
- Same for blacklist video selection (if applicable)

### Files to modify
- `dialogs/series_dialogs.py` — layout restructure, signal wiring
- `dialogs/base.py` — possibly need `_on_collection_loaded()` hook

---

## 2. Days Selection (Per-Tag Day Filter)

### Overview
Add a day-of-week selector to series tags so users can restrict which days a series tag should play. Default is all days. E.g., select Saturday+Sunday for weekend morning cartoons.

### User Story
As a user, I want to schedule a series tag only on specific days so that:
- Weekend cartoons only appear on Saturday and Sunday
- Weekday series only appear Monday through Friday
- By default, all days are selected (current behavior)

### Data Model

**`data_models.py` — Tag class**
Add a field:
```python
active_days: List[int] = None  # None or [1,2,3,4,5,6,7] = all days; subset limits to those days
```
Using 1=Monday, 7=Sunday convention (Python weekday).

Or store as a bitmask or comma-separated string:
```python
active_days: str = ""  # "" = all, or comma-sep like "1,2,3,4,5" for weekdays
```

### UI Design

**`dialogs/series_dialogs.py` — SeriesDialog.setup_ui()**
Add after the series options row:
- Label "Active Days:"
- 7 checkboxes: Mon Tue Wed Thu Fri Sat Sun, arranged horizontally
- "All" checkbox to toggle all/none (default checked)
- When "All" unchecked, individual day checkboxes become editable

**SeriesConfigDialog** — same treatment for multi-series.

### Serialization

**`serialization.py`**
Save:
```ini
active_days = 1,2,3,4,5,6,7   ; comma-separated or empty = all
```
Load: parse comma-separated string, default to all days.

### Scheduler Integration

The key integration point is where the scheduler processes series tags per day. In each day_offset loop in the strategies, skip the tag if its active_days doesn't include the current day.

**`scheduler.py`** — add a helper method:
```python
def _is_tag_active_on_day(self, tag, day_offset: int) -> bool:
    """Check if a tag should be active on the given day_offset (0-based, day 0 = Monday)."""
    active_days = getattr(tag, 'active_days', None)
    if not active_days:  # None or empty = all days
        return True
    weekday = (day_offset % 7) + 1  # 1=Monday, 7=Sunday
    return weekday in active_days
```

**`strategies.py`** — in all 9 strategy classes, before calling `_process_series_tag`:
```python
for st in series_tags:
    if not self.sg._is_tag_active_on_day(st, day_offset):
        continue
    self.sg._process_series_tag(st, series_entries, occupied, day_offset, ...)
```

Same for multi-series tags.

**`scheduler.py`** — also in `_process_series_tag` and `_place_tag_videos` for the non-strategy path (`apply_custom_tags`).

### Files to modify
- `data_models.py` — add `active_days` field
- `serialization.py` — save/load `active_days`
- `dialogs/series_dialogs.py` — add day checkboxes to both dialogs
- `scheduler.py` — add `_is_tag_active_on_day` helper
- `strategies.py` — all 9 strategy classes, add day filter check

### Backward Compatibility
- Old tags without `active_days` → treated as "all days" (current behavior)
- Default for new tags is all days checked

### Future Considerations
- Could extend to custom tags and random fill tags later
- Could add a UI indicator showing which days a tag is active on (e.g., in the main tag list)
