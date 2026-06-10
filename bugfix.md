# Bugfix Tasks

## Task: Re-Generate Overlap Bug

**Status**: Open
**Priority**: Medium

### Description
When generating a schedule preview the first time, everything is correct (0 overlaps). After pressing the Generate button multiple times, overlaps start appearing.

### Root Cause
The `_generate_count` variable is bumped on every Generate call, which affects video ordering in `movie_sequence` mode via rotation (`scheduler.py:390`). This rotation changes which videos appear on which day, which produces different schedule layouts. The carryover shift and compact shift logic may not handle all possible layouts correctly.

### Reproduction
1. Open the app with `find_replace` mode and `compact` overlap strategy
2. Click Generate once → verify 0 overlaps
3. Click Generate 2-3 more times → overlaps appear

### Investigation Notes
- The `_generate_count` feeds into `_get_videos_for_day` via `effective_day = (day_offset + self._generate_count) % num_movies`
- Different generate counts can produce different inter-day carryover gaps
- The compact shift's `_consume_overlapping_tail` removes/modifies entries per-day, which may interact poorly with the rotated movie order
- The gap-fill (post-day_unused2) uses `_gap_video_idx` which is initialized from `len(random_entries) % len(rf_videos)` — this changes with different generate counts

### Fix Approach (proposed)
Investigate whether the carryover + compact + gap-fill pipeline is robust to all movie orderings. Potential fixes:
1. Reset the overlap state more aggressively between generate calls
2. Add overlap verification in the generate pipeline
3. Increase the gap-fill's overlap checking to catch edge cases

### Files
- `scheduler.py`: `_apply_approximate_find_replace`, `_consume_overlapping_tail`, gap-fill section
- `strategies.py`: FindReplaceApproximateStrategy

## Task: Problem Color + Status Bar

**Status**: X done
**Priority**: Low

### Description
Problematic entries (gap-fill, overlaps, mismatches) should be colored red in the preview to visually flag issues. Status bar and debug dialog show counts of gaps, overlaps, and mismatches.

### Changes
- Added `problem` field to `ScheduleEntry` (data_models.py:342). Default `""`.
- `tag_color` (data_models.py:389) returns red (`#ef4444`) when `problem` is set.
- Gap-fill entries in `_apply_approximate_find_replace` (scheduler.py:1189) set `problem = "gap"`.
- Added `compute_schedule_issues(entries)` function (data_models.py:420) — returns gap/overlap/mismatch counts.
- Added `_show_issues_in_statusbar()` method to `DayPartScheduler` — logs and displays counts in status bar.
- Wired into `refresh_preview`, `generate_weekly_preview`, `generate_monthly_preview`, `run_approximate`.
- Debug dialog summary now shows gap + overlap counts (duration_debug_dialog.py:107-108).
