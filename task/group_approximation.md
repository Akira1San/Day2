# Task: Implement Group Approximation Mode

## Concept
Group Approximation is a distinct approximate scheduling mode that processes all custom/series/multi-series tags as a single sorted group, placing them sequentially to naturally group overlapping/adjacent windows without gaps between them. It uses the existing random fill (24h or linear) to occupy any gaps before the first tag or between non-overlapping groups.

## User Clarifications
- Treat all tags as custom tags with different names and durations.
- Use existing random fill for gap content.
- Should be a distinct mode (e.g., `"group_approximate"`).

## Algorithm
For each day:
1. Collect all custom, series, and multi-series tags with their original absolute times.
2. Sort them by original `start_time` ascending.
3. Initialize `current_pos = day_start`.
4. For each tag in sorted order:
   - `slot_start = max(original_start, current_pos)`
   - `slot_end = slot_start + (original_end - original_start)`
   - Place tag content in that slot (using `_place_tag_videos`).
   - Update `current_pos = actual_end` (the actual end of placed content).
5. After all tags, run the standard random fill (24h or linear) to occupy remaining time.

This naturally groups tags that have overlapping or close windows: later tags will start exactly at the end of the previous tag if their original windows overlap or are adjacent.

## Tail Handling
- Use `_consume_overlapping_tail` to handle any random entries that overlap tag slots, splitting them into head (before tag) and tail (after tag) to maintain continuity.
- The finalization step (`_approximate_finalize_day`) will also skip placing random entries that would overlap scheduled slots.

## Differences from Existing Modes
- **find_replace**: Anchors tags to random entry boundaries; may leave gaps.
- **early_fill**: Processes tags in type order (custom then series then multi), not globally sorted; can place later-starting tag before earlier one if types differ.
- **group_approximate**: Single sorted stream across all tag types, ensuring chronological ordering and grouping of overlapping windows.

## UI Integration
Add `"Group Approximate"` to `approx_mode_combo` in `daypart_scheduler.py` (line 188). Map to mode string `"group_approximate"`.

## Files to Modify
- `strategies.py`: Add `GroupApproximateStrategy` class; its `generate()` method will implement the algorithm above (similar to `EarlyFillApproximateStrategy` but with all tags sorted together and without per-type loops).
- Possibly reuse `_consume_overlapping_tail` and `_approximate_finalize_day` from `scheduler.py`.
- `daypart_scheduler.py`: Update combo box items.

## Testing
Create `test_group_approximation.py` to:
- Verify tags placed in chronological order.
- Check overlapping tags are contiguous (second starts at first's end).
- Confirm no random entries intrude into tag slots.
- Compare with other modes to show grouping behavior.

## Open Questions
- Should group_approximate also sort by priority if multiple tags have same start time? Probably not; stable sort by start time is fine.
- Should it handle tags that span midnight? Likely yes, by using absolute minutes.

## Success Criteria
- Tags sorted by start time across all types.
- Overlapping/adjacent tags produce contiguous placement.
- No overlaps with random fill.
- Continuous schedule with no unexpected gaps between grouped tags.
