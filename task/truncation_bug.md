# Task: Fix Video Truncation at Slot Boundaries

## Bug Description

When a video is too long for the remaining space in a tag's time window, the scheduler silently truncates it via `duration = min(duration, remaining_space)`. This produces incorrect ScheduleEntries (e.g., a 6088s video becomes 3160s).

The truncation happens identically in both Approximation ON and OFF modes, because all code paths share the same truncation pattern.

## Root Cause

Every video placement loop uses `min(duration, boundary - pos)` which silently clips the video to whatever space remains. There is no check that the video was massively truncated.

## Fix Strategy

Replace every `min(duration, boundary - pos)` / `duration = boundary - pos` with a skip-to-next-video pattern:

```python
# Before (truncates):
duration = min(duration, end - pos)
if duration < 1:
    break

# After (skips):
if pos + duration > end:
    vid_idx += 1
    continue
```

## All Fix Locations

### `scheduler.py` (8 sites)

| # | Approx Line | Loop Type | Current Code | Fix |
|---|---|---|---|---|
| 1 | 228 | `for v in videos_to_use:` (multi-series) | `duration = end - pos` | `continue` (skip to next video) |
| 2 | 262 | `while pos<end and vid_idx<count` (custom tag) | `min(duration, end - pos)` | `vid_idx += 1; continue` |
| 3 | 410 | `while pos<end_sec and vid_idx<count` (custom tag, non-approx) | `min(duration, end_sec - pos)` | `vid_idx += 1; continue` |
| 4 | 446 | `for v in videos_to_use:` (series tag, non-approx) | `min(duration, end_sec - pos)` | `continue` |
| 5 | 505 | `while pos < gap_end:` (random fill 24h) | `min(duration, gap_end - pos)` | `vid_idx += 1; continue` |
| 6 | 1000 | `while pos<custom_end and vid_idx<count` (linear approx, custom) | `min(duration, custom_end - pos)` | `vid_idx += 1; continue` |
| 7 | 1049 | same as #6 (linear approx 24h, custom) | `min(duration, custom_end - pos)` | `vid_idx += 1; continue` |
| 8 | 1090 | `for v in videos_to_use:` (linear approx, series) | `min(duration, series_end - pos)` | `continue` |

### `strategies.py` (1 site)

| 9 | 134 | `while pos<end and vid_idx<count` (CustomTagMergeStrategy) | `min(duration, end - pos)` | `vid_idx += 1; continue` |

## Why It's Safe

- All loops have bounds (`vid_idx < video_count`, `vid_idx < len(videos)`, or iterate over a fixed list), so skipping videos can't cause an infinite loop.
- The `if duration < 1: duration = 90` guard runs before the truncation check, so duration is always valid.
- When all videos are skipped, `pos` doesn't advance — the slot simply stays empty (gap). The scheduler handles gaps fine.

## Testing

- Run any schedule with a video longer than its tag's remaining slot time.
- Before fix: entry shows truncated duration (e.g., 3160s instead of 6088s).
- After fix: entry should not exist (video skipped), no truncation artifacts.
