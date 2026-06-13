# Task: Implement Shift Overlay Approximate Mode

## Concept
Shift Overlay is a new approximate scheduling mode inspired by `find_replace` but with a key difference: **never consume, fragment, or skip random fill entries**. Instead, shift the custom tag forward to the end of any overlapping random entry, then shift all subsequent random entries forward by the same amount.

## Problem with find_replace
`find_replace` still consumes/removes random fill entries in two cases:
1. **Close-after entries** — a random entry starting just after the tag's desired time gets used as an anchor and consumed (replaced by the tag).
2. **Overlapping tails** — random entries that span across the placed tag slot get fragmented or discarded.

## Algorithm: Shift Overlay

For each day, after generating the full random fill stream:

1. Sort all custom/series/multi-series tags by original start time.
2. Initialize `cursor = day_start`.
3. For each tag in sorted order:
   - Walk through remaining unused random entries from `cursor` forward.
   - Find the random entry whose end is **at or before** the tag's desired start time (like `best_before` in find_replace).
   - **Shift the tag** to start at that random entry's end time:
     ```
     slot_start = best_before.end_seconds
     slot_end = slot_start + (tag_end - tag_start)
     ```
   - Place tag videos in `[slot_start, slot_end)`.
   - **Do NOT consume/fragment any random entry** — the anchor entry is kept in the output before the tag.
   - **Shift all subsequent unused random entries forward** by the same delta (i.e., their start/end times increase so they come after the tag).
   - Update `cursor = slot_end`.
4. Any remaining unused random entries output as-is after `cursor`.

## Key Difference from find_replace

| Aspect | find_replace | shift_overlay |
|---|---|---|
| Anchor RF entry | Kept (appended) | Kept (appended) |
| Close-after RF | Consumed (replaced by tag) | Kept — tag shifts after anchor; close-after entry also kept and shifted |
| Spanning/overlapping RF | Fragmented or skipped | Kept — tag shifted past them; they remain intact in output |
| Subsequent RF times | Not adjusted (left at original times, may overlap tags) | Shifted forward by the delta so they appear after the tag |

## Tail Handling
No `_consume_overlapping_tail` needed — since we shift the tag to be after the anchor and shift subsequent entries forward, nothing overlaps by construction.

## Files to Modify
- `strategies.py`: Add `ShiftOverlayApproximateStrategy` class.
- `scheduler.py`: Add `"shift_overlay"` dispatch branch in `apply_approximate()`.
- `daypart_scheduler.py`: Add `"Shift Overlay"` to `approx_mode_combo`.

## Testing
- Verify no random fill entries are ever consumed or fragmented.
- Verify tag is shifted to the nearest non-overlapping position.
- Verify all subsequent random fill entries appear after the tag.
- Compare total random entry count against original (should be identical, just shifted).
- Test with overlapping tags (multiple tags on same day).
