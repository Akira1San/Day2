# Marathon Tag (Random Fill Enhancement)

## Overview
Add a "Marathon Mode" to Random Fill tags that plays all videos from a selected collection tag/series on specific days, looping to fill the full day.

## Approach
Option B — add to `RandomFillDialog` as a checkbox + tag selector + active days.

## UI Changes (RandomFillDialog)

### New controls (after fill_24h checkbox, before save/cancel):
```
☐ Marathon Mode (play all day on selected days)
Active Days: [Mon] [Tue] [Wed] [Thu] [Fri] [Sat] [Sun] [All]
Collection Tag: [combobox ▼]  (populated from loaded collection's video metadata)
```

### Layout order (right panel):
1. Name
2. Profiles row
3. Collection browse row + Collection Tag combobox
4. Video sections (collection, added, blacklist)
5. Time inputs
6. Fill 24h checkbox
7. **Marathon Mode checkbox** + **Active Days** + **Collection Tag combo**
8. Save/Cancel

### Behavior:
- "Marathon Mode" checkbox unchecked by default (existing behavior)
- When checked → `fill_24h` auto-checks + disables time inputs (marathon = all day)
- "Active Days" same day checkboxes as Series/Tag dialogs (default all)
- "Collection Tag" combobox populated from distinct `_meta_series` values (or video `name`) in loaded collection; default empty/"None"

## Data Model

**`data_models.py` — Tag class**
No new fields needed — already has:
- `active_days: List[int]` — for day filtering
- `fill_24h: bool` — for all-day play
- `is_random_fill: bool` — already on random fill tags

Add:
```python
marathon_mode: bool = False         # True = marathon mode enabled
marathon_tag_name: str = ""         # selected tag/series name (e.g. "Superman")
```

## Serialization

**`serialization.py`**
Save (random fill block):
```ini
marathon_mode = true
marathon_tag_name = Superman
```
Load: parse both fields, default to `False`/`""`.

## Scheduler Integration

### New helper on ScheduleGenerator:
```python
def _get_marathon_videos(self, tag, day_offset: int) -> List[dict]:
    """Filter collection_videos to only those matching marathon_tag_name, then
    repeat the list to fill the full day window."""
```

### Strategy changes (`strategies.py`):
In all strategies' random-fill processing paths, if `tag.marathon_mode` is True:
- Filter videos to `marathon_tag_name` match (from `_meta_series` or video `name`)
- If `active_days` doesn't include current `day_offset` → skip entirely
- If included → play marathon-filtered videos in sequence, repeating to fill the time slot

The existing `fill_24h` logic already loops videos to fill the day, so the marathon mode can piggyback on that — just filter the video list first.

### Day filter:
- `_is_tag_active_on_day` already exists and works for all Tag types
- Marathon tags with `active_days` set will be skipped on non-selected days
- Default (all days checked) = current behavior

## Files to modify
- `data_models.py` — add `marathon_mode`, `marathon_tag_name` fields
- `serialization.py` — save/load new fields in random tag block
- `dialogs/custom_tag_dialogs.py` — RandomFillDialog: add marathon checkbox, tag combo, active days
- `scheduler.py` — add `_get_marathon_videos` helper
- `strategies.py` — filter by marathon mode + active_days in all strategies

## Backward Compatibility
- Old random fill tags without `marathon_mode` → `False` (existing behavior)
- Default for new tags: marathon unchecked, all days active
