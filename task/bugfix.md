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

## Root cause

In approximate find-replace mode, when a custom tag slot overlaps a random fill entry, the scheduler creates **head/tail entries** that reuse the original `video_name` but have a shortened duration. The debug dialog compares `scheduled = end - start` against the collection duration and flags these as `MISMATCHED`.

Additionally, the debug dialog used a flat `name → dict` lookup: if the same video file appeared in two different collections (with different durations), the second overwrote the first, causing false MISMATCHED status.

## Fix

Three changes across the codebase:

### 1. `data_models.py` — Fragment tag type constant

Added `FRAGMENT_TAG_TYPE = "fragment"` and a distinct color (`#6366f1` / indigo) for fragment entries in the schedule view.

### 2. `scheduler.py` — Mark truncated entries as fragments

All 4 locations that create truncated entries now pass `tag_type=FRAGMENT_TAG_TYPE`:

| Location | What it creates |
|---|---|
| `_consume_overlapping_tail` (head) | Head portion of overlapped entry before slot start |
| `_consume_overlapping_tail` (tail) | Tail portion of overlapped entry after slot end |
| `_apply_approximate_find_replace` best_rand path | Partial entry when current_pos ≤ best_rand.end |
| `_apply_approximate_find_replace` inline | Partial entry when current_pos falls inside a random entry |
| `_approximate_finalize_day` | Same as above (deduplicated path) |

This keeps the schedule **continuous** (no gaps) while identifying fragments by their tag_type.

### 3. `duration_debug_dialog.py` — Handle fragments + duplicate-aware lookup

**Fragment handling**: Entries with `tag_type == FRAGMENT_TAG_TYPE` skip the duration mismatch check and display as `FRAGMENT` (indigo color) instead of `MISMATCHED`.

**Duplicate-aware lookup**: Changed from `name → dict` to `name → list[(dur, had_duration)]`. An entry is OK if its scheduled duration matches **any** collection entry for that video. A truly truncated entry (matching none) still shows MISMATCH.

**Continuity column**: Added 8th column "Continuity" that checks whether each entry starts exactly when the previous ends:

| Value | Meaning | Color |
|---|---|---|
| OK | Starts exactly when previous ends | default |
| GAP | Starts after previous ends — unfilled time | muted gray |
| OVERLAP | Starts before previous ends | bold red |

### Test file

`Test/test_no_truncated_entries.py` — creates a custom tag + 24h random fill tag scenario, runs approximate find-replace, and verifies:
- Fragment entries (tag_type="fragment") are allowed to have shorter durations
- Non-fragment entries must have scheduled == collection duration
