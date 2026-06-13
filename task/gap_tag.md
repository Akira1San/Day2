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

### 1. Tag Model — X Done.
In `data_models.py`, extend `Tag`:

- `is_gap_filler: bool = False` — marks this tag as a gap filler.
- `gap_collections: List[Dict] = []` — list of collection configs, each:
  ```python
  {
      "path": "/path/to/collection_trailers.json",
      "type": "trailer"   # one of: trailer, promo, music, standby_loop
  }
  ```
- `gap_max_duration: Optional[int] = None` — optional max fill seconds per day. **Default now 14400 (4h)**.
- `gap_preserve_boundaries: bool = False` — if True, don't split videos across day boundaries.
- `gap_fill_between_only: bool = False` — if True, only fill gaps BETWEEN scheduled tags, leaving day edges empty.
- `gap_auto_resolve_overlaps: bool = False` — if True, shift overlapping custom tags to create gaps.
- `gap_shift_padding: int = 180` — padding (seconds) between shifted tags.
- `gap_estimate_runtime_overlap: bool = False` — if True, use video durations to detect runtime overlaps.

No separate `gap_collection_path` string; all collection references live in `gap_collections`.

### 2. Display & Color — X Done.
In `to_display_string()`, a gap tag renders as:
```
[Gap] My Gap (T:2, P:1, M:3, S:0)
```
Where T/P/M/S count the number of collections of each type.

`tag_color` returns `QColor("#f59e0b")` (amber) for gap tags, consistent with the gap color used by `ScheduleEntry` for continuity problems.

### 3. Scheduler Integration — X Done.
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

### 4. Collection Loading — X Done.
- Gap collections are loaded at runtime when the schedule is generated (similar to lazy-loading in other tags).
- Helper: `load_gap_collections(collections_config: List[Dict]) -> List[Dict]` — iterates the config list, calls `load_collection_videos_only(path)` for each, concatenates results.
- Each collection's type is stored only for UI display; not used during scheduling.

### 5. UI — GapTagDialog — X Done.
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

### 6. Serialization — X Done.
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

### 7. Implementation Steps — X Done.
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

### 8. Files to Modify — X Done.
- `data_models.py` — gap attributes on `Tag`, display string, tag color.
- `strategies.py` — `_fill_gap_fillers()` in `CustomTagMergeStrategy`.
- `utils.py` — `load_gap_collections()` helper.
- `dialogs/custom_tag_dialogs.py` (or new file) — `GapTagDialog`.
- `serialization.py` — serialize/deserialize `gap_collections`.
- `daypart_scheduler.py` — tag list UI, edit dispatch, add gap button.

### 9. Success Criteria — X Done.
- All unoccupied intervals within a day are filled with gap content.
- No gap video overlaps any primary tag.
- Videos from all gap collections are cycled round-robin across gaps.
- The schedule is continuous from 00:00 to 24:00 (or until `gap_max_duration` is reached).
- The UI shows collection type breakdown clearly in the tag list.
- Easy to configure: user browses to `.json` files and assigns types.

---

### 10. Performance: Gap fill cap & soft limit — X Done.
Default `gap_max_duration` raised to **14400** (4h), soft cap at 14400 for
None/0. Tooltip updated to recommend 7200–14400.

**Fix:**
1. Default `gap_max_duration` to 14400 (4h) in `data_models.py` `Tag.__init__()`.
2. Add a **soft internal cap** in `_fill_gap_fillers`: if `gap_max_duration` is
   None or 0, cap at **14400s (4h)** and log a warning.
3. Update `GapTagDialog` spinbox default to 14400 with tooltip.
4. Update `Tags/Gap fill 1.ini` to set `gap_max_duration = 14400`.

### 11. UI: Collapsible gap groups in schedule preview & debug dialog — X Done.
When the gap filler generates many entries (thousands), the flat schedule
preview list and debug table become unusable — gap entries drown out real
content.

**Changes:**

**Main preview (`daypart_scheduler.py`):**
- Swap `QListWidget` → `QTreeWidget` for `self.preview_list`
- New method `_populate_preview_tree(entries)` that groups consecutive gap
  entries (`tag_type == "gap_fill"` or `problem == "gap"`) under a single
  collapsible parent item
- Parent text: `"▶ Gap — N entries — HH:MM–HH:MM"` in amber bold
- Parents start **collapsed** by default
- Update `refresh_preview()`, `generate_weekly_preview()`,
  `generate_monthly_preview()`, `copy_preview()` to use tree + recurse children

**Duration Debug Dialog (`dialogs/duration_debug_dialog.py`):**
- Swap `QTableWidget` → `QTreeWidget` (supports columns natively)
- Group consecutive gap rows under a single collapsible parent in the table
- Update `copy_to_clipboard()` to recurse children
- Summary counts at top still reflect total entries (including collapsed)

### 12. Integration with approximate scheduling modes — X Done.
Gap tag currently only works when approximation is OFF (`CustomTagMergeStrategy`).
It should also work with all approximate modes (Find-Replace, Linear, Early Fill,
Late Fill, Priority, etc.) so the schedule is continuous regardless of mode.

**Approach:**
Since `_fill_gap_fillers` is a self-contained post-processing step (takes placed
entries, computes gaps, fills them), add it as a **common final step** in
`ScheduleGenerator.apply_approximate()` (`scheduler.py:728`), after the strategy
returns its entries. This covers all 9 approximate modes at once.

**Implementation sketch in `apply_approximate()`:**
```python
entries = strategy.generate(num_days)

# Post-process: fill remaining gaps with gap tag videos
gap_tags = [t for t in self.tag_manager.get_all_tags() if t.is_gap_filler]
if gap_tags:
    from strategies import CustomTagMergeStrategy
    dummy_strategy = CustomTagMergeStrategy(self)
    gap_entries = dummy_strategy._fill_gap_fillers(
        gap_tags, entries, [], [], [], num_days
    )
    entries = entries + gap_entries
    entries.sort(key=lambda e: e.start_seconds)

return entries
```

**Key points:**
- Fragment entries (head/tail from fragment overlap strategy) are naturally in the
  entries list, so the gap filler treats them as occupied — no re-filling over them.
- `_fill_gap_fillers` computes occupied ranges directly from placed entries; no
  separate `occupied` set needed.
- Day boundaries, `gap_max_duration`, and `gap_preserve_boundaries` all work the
  same as in non-approximate mode.
- All 9 modes benefit: Linear, Find-Replace, Early Fill, Late Fill, Priority,
  Best Fit, Round Robin, Linear Spanning, Exhaustive.

**Success criteria:**
- After any approximate strategy runs, any remaining empty intervals (00:00–24:00
  not covered by placed entries) are filled with gap videos.
- No gap video overlaps any primary or fragment entry.
- The schedule is continuous from 00:00 to 24:00 (or until `gap_max_duration` is
  reached).

### 13. Additional gap tag features — X Done.

Features added to the gap tag during the Jun 12 session:

**13a. Only fill between tags (`gap_fill_between_only`)**
Checkbox on the gap dialog: when checked, gap filler only fills gaps BETWEEN
scheduled custom tags. The pre-first-tag and post-last-tag day edges are left
empty to visually show unfilled space. Implemented in `_fill_gap_fillers` by
skipping gaps that touch 00:00 or 24:00.

**13b. Auto-resolve overlapping tags (`gap_auto_resolve_overlaps` + `gap_shift_padding`)**
Checkbox + padding combo (1/2/3/5 min) on the gap dialog. When enabled, the
auto-resolve pre-processing in `CustomTagMergeStrategy.generate()` sorts
custom tags by start time and shifts later tags forward past the previous
tag's end + padding if they overlap. Creates gaps that the filler fills.

**13c. Runtime overlap estimation (`gap_estimate_runtime_overlap`)**
Checkbox on the gap dialog. When enabled alongside auto-resolve, the overlap
detector sums video durations (`min(video_count, len(collection_videos))`) to
estimate each tag's actual end time. Catches cases where a tag's videos extend
past its defined end time, creating an overlap with the next tag that isn't
visible by comparing start/end times alone.

**Files changed (Jun 12 session):**
- `data_models.py` — field definitions + `edit_tag` signature
- `strategies.py` — auto-resolve pre-processing in `generate()`
- `dialogs/custom_tag_dialogs.py` — `GapTagDialog` checkboxes + combo
- `serialization.py` — save/load new fields
- `Test/test_gap_filler.py` — 14 tests covering all features

### 14. New approximation algorithm: No-Overlap — Planned (not yet implemented)

**Concept:** Place tags at their original start times, right-shifting any that
would overlap the previous tag. Produces a clean non-overlapping schedule with
natural gaps ready for gap filler.

**Comparison with existing modes:**

| Mode | Original times respected? | Can overlap? | Gaps created? |
|------|---------------------------|-------------|---------------|
| Linear | No (all start at 00:00) | No (back-to-back) | Rarely |
| Find-Replace | Partially | Yes | Sometimes |
| Early/Late Fill | Partially | Yes | No |
| Priority | No (by priority order) | Yes | No |
| **No-Overlap (new)** | **Yes** | **Never** | **Always (by design)** |

**Implementation steps:**
1. `strategies.py` — Add `NoOverlapApproximateStrategy` class (~50 lines):
   - Sort tags by `start_time` ascending
   - Per day: track `current_pos`, place each tag at `max(tag.start, current_pos)`,
     update `current_pos = tag.end`
   - Fill remaining gaps with random fill
2. `scheduler.py` — Import class + add dispatch:
   ```python
   elif mode == "no_overlap":
       return NoOverlapApproximateStrategy(self).generate(num_days)
   ```
3. `daypart_scheduler.py` — Add `"No Overlap"` to `approx_mode_combo`
4. Test files — Add `"no_overlap"` to mode lists in test_all_modes.py etc.
5. (Recommended) Implement Section 12 alongside so gap filler runs as common
   post-processing in `apply_approximate()` — making No-Overlap the ideal
   companion for gap tags, and benefiting all other modes too.

## Notes
- Gap Tag is independent from Group Approximation (which is an approximate-mode algorithm).
- They could be combined later (e.g., Group Approximation could also invoke gap filling for leftover gaps).
- The type field is currently display-only; future enhancement could use type in scheduling decisions (e.g., "play trailers in primetime only").
