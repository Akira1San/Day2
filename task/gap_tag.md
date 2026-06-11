# Task: Implement Gap Tag Feature (Approximation OFF)

## Concept
A **Gap Tag** is a procedural tag type that fills empty time intervals between scheduled programs with interstitial content (trailers, promos, music, standby loops). It is intended for use when **approximation is OFF** (i.e., during exact tag placement) to eliminate dead air.

The user creates multiple video collection `.json` files from folders of filler content and assigns each a content type (trailer, promo, music, standby loop). A Gap Tag references these collections. During scheduling, after all non-gap tags are placed, the gap filler scans for unoccupied intervals and fills them with videos from the pooled collections in round-robin order.

## User Clarifications
- Works with approximation OFF.
- Single gap tag, multiple collections within it.
- Procedural: user generates collection `.json` files from folders of trailers/music/loops.
- Each collection is tagged with a content type (trailer/promo/music/standby_loop).
- All videos are pooled and cycled round-robin during gap filling; types are display-only.
- Fills empty spaces in the preview.

## Implementation Proposal

### 1. Tag Model
In `data_models.py`, extend `Tag`:

- `is_gap_filler: bool = False` — marks this tag as a gap filler.
- `gap_collections: List[Dict] = []` — list of collection configs, each:
  ```python
  {
      "path": "/path/to/collection_trailers.json",
      "type": "trailer"   # one of: trailer, promo, music, standby_loop
  }
  ```
- `gap_max_duration: Optional[int] = None` — optional max fill seconds per day.
- `gap_preserve_boundaries: bool = False` — if True, don't split videos across day boundaries.

No separate `gap_collection_path` string; all collection references live in `gap_collections`.

### 2. Display & Color
In `to_display_string()`, a gap tag renders as:
```
[Gap] My Gap (T:2, P:1, M:3, S:0)
```
Where T/P/M/S count the number of collections of each type.

`tag_color` returns `QColor("#f59e0b")` (amber) for gap tags, consistent with the gap color used by `ScheduleEntry` for continuity problems.

### 3. Scheduler Integration
In `CustomTagMergeStrategy.generate()` (used when approximation is OFF):
- After placing all non-gap tags, check for gap tags.
- Pool all videos from all `gap_collections` into a single flat list (load each collection path, extract videos, concatenate).
- For each day:
  1. Collect occupied minute ranges from all placed entries.
  2. Compute gaps: intervals between `day_start` (00:00) and `day_end` (24:00) not occupied.
  3. For each gap, iterate through the pooled gap videos in round-robin order and place as many as fit.
  4. Respect `gap_max_duration` per day if set (stop filling once total gap fill time ≥ max).
  5. Respect `gap_preserve_boundaries`: if a video would end after `day_end`, skip it (don't fragment).
  6. Set `entry.problem = "gap"` on placed gap entries for continuity marking.
  7. Add placed gap entries to final schedule; update occupied ranges for subsequent gaps.

### 4. Collection Loading
- Gap collections are loaded at runtime when the schedule is generated (similar to lazy-loading in other tags).
- Helper: `load_gap_collections(collections_config: List[Dict]) -> List[Dict]` — iterates the config list, calls `load_collection_videos_only(path)` for each, concatenates results.
- Each collection's type is stored only for UI display; not used during scheduling.

### 5. UI — GapTagDialog
A new dialog `GapTagDialog` (analogous to `RandomFillDialog` but purpose-built for gap tags).

Layout:

- **Name** input (top).
- **Collection table** (center, scrollable):
  - Each row contains:
    - **Browse button** → opens file dialog for `.json` selection.
    - **Path label** (read-only, shows selected file path).
    - **Type combo** with four items: Trailer, Promo, Music, Standby Loop.
    - **Remove button** → deletes the row.
  - **Add Collection** button below the table appends a new empty row.
  - Table supports visual feedback: path truncated for readability, type shown as badge-style text.

- **Gap Max Duration** spinbox (seconds, 0 = unlimited), with a label "Max fill per day (0 = no limit)".

- **Preserve Boundaries** checkbox.

- **Active Days** section (same pattern as marathon mode in RandomFillDialog):
  - Mon Tue Wed Thu Fri Sat Sun checkboxes + All toggle.
  - Default: all days checked.

- **Save / Cancel** buttons.

### 6. Serialization
In `serialization.py`, serialize `gap_collections` as a JSON-encoded string in the INI entry:

```
[Tag]
type = gap
name = My Gap
gap_collections = [{"path": "/path/to/trailers.json", "type": "trailer"}, {"path": "/path/to/music.json", "type": "music"}]
gap_max_duration = 3600
gap_preserve_boundaries = false
active_days = 1,2,3,4,5,6,7
```

### 7. Implementation Steps
1. Extend `Tag` class in `data_models.py` with `is_gap_filler`, `gap_collections`, `gap_max_duration`, `gap_preserve_boundaries`.
2. Update `to_display_string()` and `tag_color` for gap tags.
3. Create `GapTagDialog` in `dialogs/custom_tag_dialogs.py` (or new `dialogs/gap_dialog.py`).
4. Add `load_gap_collections()` utility in `utils.py`.
5. In `CustomTagMergeStrategy.generate()`, after main placement, call `_fill_gap_fillers()` if any gap tags exist.
6. Implement `_fill_gap_fillers()`: loop days, compute gaps, fill from pooled gap videos.
7. Update serialization in `serialization.py` to save/load `gap_collections`.
8. Update `daypart_scheduler.py`:
   - `refresh_tags_list()` to render `[Gap]` entries with amber color.
   - `edit_tag()` to dispatch to `GapTagDialog`.
   - Add "Gap" button in tag list panel (or integrate into existing add flow).
9. Ensure gap videos are treated as distinct from random fill in schedule continuity checks.

### 8. Files to Modify
- `data_models.py` — gap attributes on `Tag`, display string, tag color.
- `strategies.py` — `_fill_gap_fillers()` in `CustomTagMergeStrategy`.
- `utils.py` — `load_gap_collections()` helper.
- `dialogs/custom_tag_dialogs.py` (or new file) — `GapTagDialog`.
- `serialization.py` — serialize/deserialize `gap_collections`.
- `daypart_scheduler.py` — tag list UI, edit dispatch, add gap button.

### 9. Success Criteria
- All unoccupied intervals within a day are filled with gap content.
- No gap video overlaps any primary tag.
- Videos from all gap collections are cycled round-robin across gaps.
- The schedule is continuous from 00:00 to 24:00 (or until `gap_max_duration` is reached).
- The UI shows collection type breakdown clearly in the tag list.
- Easy to configure: user browses to `.json` files and assigns types.

---

## Notes
- Gap Tag is independent from Group Approximation (which is an approximate-mode algorithm).
- They could be combined later (e.g., Group Approximation could also invoke gap filling for leftover gaps).
- The type field is currently display-only; future enhancement could use type in scheduling decisions (e.g., "play trailers in primetime only").
