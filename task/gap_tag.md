# Task: Implement Gap Tag Feature (Approximation OFF)

## Concept
A **Gap Tag** is a procedural tag type that fills empty time intervals between scheduled programs with interstitial content (trailers, promos, music, standby loops). It is intended for use when **approximation is OFF** (i.e., during exact tag placement) to eliminate dead air.

The user manually creates a video collection (e.g., `collection_gap.json`) from a folder of filler videos and marks a custom tag as a Gap Tag. During scheduling, after all non-gap tags are placed, the gap filler scans for unoccupied intervals and fills them with videos from that collection.

## User Clarifications
- Works with approximation OFF.
- Single gap tag (maybe more later?).
- Procedural: user loads a folder with trailers/music/loops and generates `collection_gap.json`.
- It fills empty spaces in the preview.

## Implementation Proposal

### 1. Tag Model
In `data_models.py`, extend `Tag`:
- `is_gap_filler: bool = False`
- `gap_collection_path: str = ""` (path to the folder/JSON)
- `gap_max_duration: int = None` (optional max fill time per day)
- `gap_preserve_boundaries: bool = False` (optional: don't split videos that would end at a boundary)

### 2. Scheduler Integration
In `ScheduleGenerator.apply_custom_tags()` (used when approximate is OFF):
- After placing all non-gap tags, collect occupied minute ranges.
- For each day:
  - Compute gaps: intervals between `day_start` and `day_end` not occupied.
  - For each gap, iterate through the gap collection videos and place as many as fit without overlapping occupied ranges.
  - Respect `gap_max_duration` per day if set.
  - Add placed gap videos to `final` schedule.
  - Update occupied ranges.

### 3. Gap Collection Loading
- The gap tag's `collection_videos` can be populated at runtime by reading the specified folder/JSON, similar to other tags.
- Helper: `load_gap_collection(path)`.

### 4. Multiple Gap Tags?
Initially support a single gap tag. If more than one exists, combine their collections or process by priority.

### 5. UI
- In the tag editor, add a "Gap filler" checkbox and a folder selector for the gap collection.
- The gap tag appears in the tag list with a special icon or label.
- User must generate `collection_gap.json` externally (or we could add a tool to convert a folder to collection format).

### 6. Implementation Steps
1. Extend `Tag` class in `data_models.py`.
2. In `apply_custom_tags()`, after main placement, call `_fill_gap_fillers()` if any gap tags exist.
3. Implement `_fill_gap_fillers()` in `ScheduleGenerator`. It will loop days, compute gaps, and fill from the gap collection(s).
4. Update UI dialogs (e.g., `RandomFillDialog` or new `GapDialog`) to configure gap properties.
5. Ensure gap videos are treated as "random" entries but with a distinct source.

### 7. Files to Modify
- `data_models.py`: Add gap-related attributes.
- `scheduler.py`: Add `_fill_gap_fillers()` method; call from `apply_custom_tags()`.
- `dialogs.py`: Add gap filler options.
- `daypart_scheduler.py`: Update tag list UI to show gap fillers.
- Utilities: maybe a `load_collection_from_folder()` function.

### 8. Success Criteria
- All unoccupied minutes within a day are filled with gap content up to the max duration.
- No gap video overlaps any primary tag.
- The schedule is continuous from day start to day end (or until gap max reached).
- Easy to configure: user points to a folder of filler videos.

---

## Notes
- Both features are independent: Group Approximation is an approximate-mode algorithm; Gap Tag is for exact mode.
- They could be combined later if desired (e.g., Group Approximation could also invoke gap filling for leftover gaps).
