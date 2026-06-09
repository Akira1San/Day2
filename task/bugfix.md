# Bug: MISMATCHED entries in debug dialog when using custom tag + random fill with approximate mode

## Status: FIXED

## Reproduction

1. Load custom tag "Custom Test" (`Tags/Custom test.ini`):
   - 09:00-23:19, 6 videos from `movie_collection_001.json`
2. Load random fill tag "movies 3" (`Tags/Movies 3.ini`):
   - 00:00-23:59, fill_24h=true, from `movie_collection_003.json`
3. Enable approximate mode (find-replace is the default)
4. Generate preview
5. Open Duration Debug dialog

## Observed behavior

Every day shows at least one random fill entry with status `MISMATCHED` — the scheduled duration differs from the collection duration. The affected entries are tail portions of random-fill videos that got truncated when the custom tag slot was inserted on top of them.

## Root cause analysis

### How the approximate merge works (find-replace mode)

1. `_build_random_entries()` creates a continuous stream of random fill entries from 00:00-23:59, each entry having `video_name = "movies 3 - <filename>"` and `end_seconds - start_seconds = int(video.duration)` (e.g. `"movies 3 - The Crystal Storm Resurgence.mp4"` spanning `00:00 - 01:31`).

2. The custom tag "Custom Test" is placed in its target slot (09:00-23:19). The `_place_tag_videos` method inserts 6 custom entries.

3. `_consume_overlapping_tail()` handles random entries that overlap the slot start. It creates a **tail entry** from `current_pos` to `rand_e.end_seconds` with the **same video_name** as the original random entry (line 752/760 in `scheduler.py`).

4. `_approximate_finalize_day()` at line 1000-1003 handles random entries partially consumed by the advancing `current_pos`:
   ```python
   elif rand_e.start_seconds < current_pos < rand_e.end_seconds:
       dur = rand_e.end_seconds - current_pos
       if dur > 0:
           final.append(ScheduleEntry(1, current_pos, rand_e.end_seconds, rand_e.video_name))
   ```
   This creates another truncated entry with the original video_name.

The debug dialog compares `scheduled = entry.end_seconds - entry.start_seconds` against the full collection duration. Since the tail entry is shorter than the original video, it always shows MISMATCHED.

### Example

- Random fill entry: `"movies 3 - The Crystal Storm Resurgence.mp4"` (duration from collection: 5461s)
- Custom tag slot starts at 09:00 (32400s)
- If the random entry covers 07:30-09:01, the tail after 09:00 is 60s
- Tail entry: `"movies 3 - The Crystal Storm Resurgence.mp4"` from 09:00 to 09:01 (60s)
- Debug: scheduled=60s vs collection=5461s → MISMATCHED

## Fix applied

The root cause was that the scheduler created truncated entries with wrong durations. Videos from the random fill collection were partially overlapped by custom tag slots, and the scheduler created head/tail entries reusing the original video_name but with a shortened duration — a real scheduling bug, not just a display issue in the debug dialog.

### Changes in `scheduler.py`:

1. **`_consume_overlapping_tail`** (lines 785, 793): Removed creation of truncated head and tail entries. When a random fill entry overlaps a custom tag slot, the entry is consumed (marked as used) but not added to the schedule. No partial-video entries are created.

2. **`_apply_approximate_find_replace` best_rand path** (line 950-951): Removed creation of truncated entry when `current_pos` falls inside the anchor entry's time range. The anchor is consumed and skipped instead.

3. **`_apply_approximate_find_replace` inline code** (lines 1035-1038): Removed creation of truncated entry when `current_pos` falls inside a remaining random entry. The entry is consumed and skipped.

4. **`_approximate_finalize_day`** (lines 831-838): Same fix as #3 — removed truncated entry creation.

### Effect

No video entry in the schedule will have a duration that differs from its collection-defined duration. Overlapped random fill entries are skipped entirely (not added to the schedule). The scheduler continues with the next full-length entry after the custom tag slot. Some time gaps may occur, which is acceptable for approximate mode. Random fill entries come from a shuffled collection that cycles through videos, so skipping an occasional overlapped entry does not lose content — the next entry in the cycle continues normally.

### Additional fix: Debug dialog duplicate-aware lookup (`duration_debug_dialog.py`)

The debug dialog's `_build_comparison` previously used a flat `name → dict` lookup. If the same video file appeared in **multiple collections** with different durations (e.g., the same MP4 file in two different `.json` files), the second one loaded would silently overwrite the first, causing false MISMATCHED status.

**Fix**: The lookup now stores a **list** of all `(duration, had_duration)` tuples per video name. When comparing, it considers the entry OK if the scheduled duration matches **any** of the known durations for that video. A truly truncated entry (matching none) still correctly shows MISMATCH.

### Test file

Added `Test/test_no_truncated_entries.py` — creates a custom tag + 24h random fill tag scenario, runs approximate find-replace, and verifies every entry's scheduled duration matches its collection duration.
