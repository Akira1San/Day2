# Bug: MISMATCHED entries in debug dialog when using custom tag + random fill with approximate mode

## Status: PARTIALLY FIXED — see "Remaining issue" below

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

## Fix applied (v1 — fragment marking)

### Changes

| File | Change |
|---|---|
| `data_models.py` | Added `FRAGMENT_TAG_TYPE = "fragment"` and indigo color in `tag_color` |
| `scheduler.py` | All 4 truncated-entry sites pass `tag_type=FRAGMENT_TAG_TYPE` instead of empty string |
| `duration_debug_dialog.py` | Fragment entries skip mismatch check, show FRAGMENT (indigo); duplicate-aware lookup; Continuity column (OK/GAP/OVERLAP) |
| `Test/test_no_truncated_entries.py` | Verifies fragments accepted, non-fragments must match collection duration |

### What this achieves

- Schedule stays **continuous** — the head/tail entries fill all time, no gaps
- Debug dialog shows **FRAGMENT** instead of MISMATCHED for truncated entries
- Debug dialog detects real mismatches (non-fragment entries with wrong durations)
- Same video in multiple collections with different durations no longer causes false MISMATCHES

### Why this is not enough

The fragment approach **still creates cut videos** in the schedule. A random fill entry gets split into head/tail fragments, each showing with the original video name but a wrong duration. The debug dialog prettifies this with "FRAGMENT" instead of "MISMATCHED", but the underlying issue — a video being cut mid-play — remains in the schedule itself.

---

## Remaining issue: Cut videos still appear in the schedule

### Why it happens

The random fill stream is built as a **continuous** back-to-back sequence from 00:00 to 23:59. Every second is occupied by some video. When the custom/series tag is placed, its slot overlaps entries in the stream. The algorithm cuts those entries into head/tail portions rather than dropping them entirely.

```
Random stream: |--- A ---||--- B ---||--- C ---||--- D ---|...
                              ^
                    tag inserted here
                              |------- tag slot -------|
```

### What needs to change

The find-replace algorithm should **not cut entries at all**. Instead, when a random entry overlaps the tag slot, the entire entry should be removed from the schedule. The stream continues with the next entry after the slot. The overlapped video is simply not shown that day — acceptable for random fill (shuffled collection, videos cycle).

---

## Possible solutions for next task

### Solution A: Skip overlapped entries entirely

Remove the `_consume_overlapping_tail` logic and all fragment creation. When an entry overlaps the tag slot, mark it as used and skip it. After the tag, the next non-overlapped entry continues the stream.

- **Pro**: Simple, no cut videos, no wrong durations
- **Con**: Gaps may form between tag end and next entry's original start
- **Implementation**: Remove head/tail entry creation, don't advance `current_pos`

### Solution B: Gap-fill after tag placement (most promising)

Instead of building a continuous random stream and then cleaning up overlap, **place tags first, then fill remaining time with random entries**. This is essentially what `_process_random_fill_tag` already does in fill_24h mode — it finds gaps in the schedule and fills each gap with full-duration random entries, skipping any video that doesn't fit.

```
Step 1: Place all custom/series tags
         |--- tag ---|
Step 2: Fill gaps with full random entries (skip if doesn't fit)
|--- A ---| |--- B ---||--- C ---|
```

- **Pro**: No cut videos, no fragments, no wrong durations
- **Pro**: Already implemented in `_process_random_fill_tag` for 24h fill mode — proven approach
- **Con**: Some random fill videos may be skipped if gap is too small
- **Implementation**: Replace the `_build_random_entries` + `_consume_overlapping_tail` + `_approximate_finalize_day` flow with gap-filling logic similar to `_process_random_fill_tag`

### Solution C: Compact the stream after tag

Remove overlapped entries, then shift remaining entries (after the tag) leftward so they start immediately at the tag's end. Their durations stay correct — only their positions shift.

- **Pro**: No gaps, no cut videos
- **Con**: Changes scheduled times of entries after the tag (acceptable for random fill)
- **Implementation**: After consuming overlapped entries, recompute positions for remaining unused entries

### Solution D: Re-anchor to avoid overlap entirely

Before placing the tag, find a gap between two random entries that is at least as long as the tag slot. Move the tag there. If no such gap exists, the tag can't be placed in this mode.

- **Pro**: No overlap means no cut videos
- **Con**: May not be possible for long slots (14h+)

### Solution E: Try different approximate modes

The scheduler already supports multiple approximate modes (`linear`, `early_fill`, `late_fill`, `priority`, `best_fit`, `round_robin`, `linear_spanning`, `exhaustive`). Some may handle the overlap better than find-replace for specific scenarios.

---

## Appendix: Continuity column in debug dialog

New 8th column "Continuity" in Duration Debug dialog:

| Value | Meaning | Color |
|---|---|---|
| OK | Starts exactly when previous ends | default |
| GAP | Starts after previous ends — unfilled time | muted gray |
| OVERLAP | Starts before previous ends | bold red |
