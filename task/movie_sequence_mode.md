# Movie Sequence Mode - Global Video Ordering Option

## Overview
Add a global video selection mode that allows users to choose between random shuffle and "Movie Sequence" ordering for non-series tags. Movie Sequence groups videos by numeric identifier in the filename (e.g., "Movie 1", "Part 1") and assigns each group to a specific day.

## User Story
As a user, I want to schedule movies in sequential order across days so that:
- Day 1 shows Movie 1 (all parts)
- Day 2 shows Movie 2 (all parts)
- Day N shows Movie N
- If there are more days than movies, it wraps around (Movie 1 appears again)
- Within each movie's parts, either sequential or random order based on the tag's "Randomize videos" flag

## Requirements

### Functional
1. Add a combobox in the main UI (near Profile) with options: "Random" (default), "Movie Sequence"
2. The setting applies globally to all non-series tags during generation
3. Series tags (with season metadata) remain unaffected
4. Random Fill tags respect the global mode
5. Approximate modes (Linear, Find-Replace, etc.) respect the global mode
6. Daily/Weekly/Monthly generation all respect the mode

### Non-Functional
- No changes to existing behavior when mode = "Random" (default)
- Backward compatible with existing tags and saved schedules
- Performance: grouping happens once per generation, not per tag

## Technical Design

### Data Model
No new attributes needed on Tag. The mode is global (stored in `ScheduleGenerator`).

### Utility Functions (utils.py)
Add these helpers:

```python
def extract_movie_sequence_key(path: str) -> Tuple[int, int]:
    """Extract (movie_number, part_number) from filename.
    
    Patterns matched:
    - "Movie 1", "Part 1", "Film 1" (with optional multiplier suffix like "x1")
    - Leading number: "1 - Video Name"
    - Two number groups: "1x02" or "S01E02" format (movie=first, part=second)
    
    Returns: (movie_num, part_num) with defaults (1, 0)
    """
    import re
    name = path.split('/')[-1] if '/' in path else path
    
    # Try explicit markers: "Movie 1", "Part 1", "Film 1"
    m = re.search(r'(?:movie|part|film)\s*(\d+)', name, re.IGNORECASE)
    if m:
        movie = int(m.group(1))
        # Check for part/multiplier suffix like "x1", "x2"
        m2 = re.search(r'x(\d+)', name, re.IGNORECASE)
        part = int(m2.group(1)) if m2 else 0
        return (movie, part)
    
    # Extract all number sequences
    numbers = [int(n) for n in re.findall(r'\d+', name)]
    if not numbers:
        return (1, 0)
    if len(numbers) == 1:
        return (numbers[0], 0)
    return (numbers[0], numbers[1])

def group_videos_by_movie(videos: List[Dict]) -> Dict[int, List[Dict]]:
    """Group videos into movie buckets sorted by movie number.
    Within each group, sort by part number then preserve original order.
    Returns: {movie_num: [video1, video2, ...]} sorted by movie_num ascending.
    """
    groups = {}
    for v in videos:
        path = v.get('path', '')
        movie_num, part_num = extract_movie_sequence_key(path)
        groups.setdefault(movie_num, []).append((part_num, v))
    
    result = {}
    for movie_num in sorted(groups.keys()):
        # Sort by part number, then by original order
        items = sorted(groups[movie_num], key=lambda x: (x[0], 0))
        result[movie_num] = [v for _, v in items]
    return result
```

### ScheduleGenerator Modifications (scheduler.py)

**New attribute in `__init__`:**
```python
def __init__(self, tag_manager: TagManager):
    self.tag_manager = tag_manager
    self.video_order_mode = "random"  # "random" | "movie_sequence"
```

**New helper method:**
```python
def _get_videos_for_day(self, videos: List[dict], day_offset: int) -> List[dict]:
    """Select videos according to global video_order_mode for a given day.
    
    Args:
        videos: Full list of collection videos
        day_offset: 0-based day index (0=day1, 1=day2, ...)
    
    Returns:
        Ordered list of videos to use for this day
    """
    if not videos:
        return []
    
    if self.video_order_mode == 'movie_sequence':
        groups = group_videos_by_movie(videos)
        if not groups:
            return videos.copy()
        movie_numbers = sorted(groups.keys())
        # Select movie group based on day_offset (wrap around)
        selected_movie = movie_numbers[day_offset % len(movie_numbers)]
        day_videos = groups[selected_movie].copy()
        return day_videos
    else:
        # Random mode: shuffle
        shuffled = videos.copy()
        random.shuffle(shuffled)
        return shuffled
```

**Update `_process_custom_tag`** (replace lines 267-286):

Current:
```python
if ct.collection_videos:
    for s in range(start_sec, end_sec):
        occupied.add(s)
    video_count = getattr(ct, 'video_count', 1)
    videos = ct.collection_videos.copy()
    random.shuffle(videos)
    pos = start_sec
    ...
```

Updated:
```python
if ct.collection_videos:
    for s in range(start_sec, end_sec):
        occupied.add(s)
    video_count = getattr(ct, 'video_count', 1)
    # Compute day offset from start_sec (absolute seconds)
    day_offset = start_sec // 86400
    videos = self._get_videos_for_day(ct.collection_videos, day_offset)
    # Honor randomize_videos flag: if true, shuffle within the day's selection
    if getattr(ct, 'randomize_videos', False):
        random.shuffle(videos)
    pos = start_sec
    ...
```

**Update `_place_tag_videos`** (custom tag branch, lines 178-196):

Current:
```python
else:
    random.shuffle(ct.collection_videos)
    ordered_videos = ct.collection_videos.copy()
```

Updated:
```python
else:
    # For non-series custom tags: use day-aware selection
    day_offset = start // 86400  # start is absolute seconds
    ordered_videos = self._get_videos_for_day(ct.collection_videos, day_offset)
    if getattr(ct, 'randomize_videos', False):
        random.shuffle(ordered_videos)
```

**Update `_process_random_fill_tag`** (fill_24h branch, lines 346-380):

Current:
```python
if rf_fill_24h:
    rf_videos = rf.collection_videos.copy() if rf.collection_videos else []
    if not rf_videos:
        return
    random.shuffle(rf_videos)
    gaps = []
    ...
```

Updated:
```python
if rf_fill_24h:
    rf_videos_base = rf.collection_videos.copy() if rf.collection_videos else []
    if not rf_videos_base:
        return
    # Determine day_offset from start_offset (passed param)
    day_offset = start_offset // 86400
    rf_videos = self._get_videos_for_day(rf_videos_base, day_offset)
    gaps = []
    ...
```

**Update `generate_random_fill`** (lines 231-255):

Current:
```python
def generate_random_fill(self, remaining_seconds: int = 24 * 3600) -> List[ScheduleEntry]:
    all_tags = self.tag_manager.get_all_tags()
    collection_videos = self._get_all_videos(all_tags)
    if not collection_videos:
        return []
    entries = []
    random.shuffle(collection_videos)
    video_index = 0
    ...
```

Updated:
```python
def generate_random_fill(self, remaining_seconds: int = 24 * 3600) -> List[ScheduleEntry]:
    all_tags = self.tag_manager.get_all_tags()
    collection_videos = self._get_all_videos(all_tags)
    if not collection_videos:
        return []
    entries = []
    # Use global video order mode for ordering
    ordered_videos = self._get_videos_for_day(collection_videos, day_offset=0)
    # For multi-day fills (>24h), cycle through groups sequentially
    if remaining_seconds > 86400:
        # Build extended list by concatenating groups in order for each day
        groups = group_videos_by_movie(collection_videos) if self.video_order_mode == 'movie_sequence' else None
        if groups:
            movie_nums = sorted(groups.keys())
            ordered_extended = []
            num_days = (remaining_seconds + 86399) // 86400
            for day_idx in range(num_days):
                movie_idx = day_idx % len(movie_nums)
                day_group = groups[movie_nums[movie_idx]]
                ordered_extended.extend(day_group)
            # Trim to fit remaining_seconds based on average duration
            avg_dur = sum(v.get('duration', 90) for v in ordered_extended) // len(ordered_extended) if ordered_extended else 90
            needed_count = remaining_seconds // max(1, avg_dur)
            ordered_videos = ordered_extended[:needed_count]
        else:
            # Random mode: just shuffle once
            random.shuffle(collection_videos)
            ordered_videos = collection_videos
    video_index = 0
    ...
```

**Update `_build_random_entries`** (lines 201-222):

Current:
```python
def _build_random_entries(self, videos: List[dict], start_pos: int, end_pos: int, tag_name: str = "") -> List[ScheduleEntry]:
    entries = []
    pos = start_pos
    if not videos:
        ...
    videos = videos.copy()
    random.shuffle(videos)
    vid_idx = 0
    while pos < end_pos:
        video = videos[vid_idx % len(videos)]
        ...
```

Updated:
```python
def _build_random_entries(self, videos: List[dict], start_pos: int, end_pos: int, tag_name: str = "") -> List[ScheduleEntry]:
    entries = []
    pos = start_pos
    if not videos:
        ...
    # Determine day offset from start_pos (absolute seconds to relative day)
    day_offset = start_pos // 86400 if start_pos >= 0 else 0
    ordered_videos = self._get_videos_for_day(videos, day_offset)
    vid_idx = 0
    while pos < end_pos:
        video = ordered_videos[vid_idx % len(ordered_videos)]
        ...
```

### Main Window UI (daypart_scheduler.py)

**In `setup_ui()` row1_layout** (after line 201):

```python
row1_layout.addWidget(QLabel("Video Order:"))
self.video_order_combo = QComboBox()
self.video_order_combo.addItems(["Random", "Movie Sequence"])
self.video_order_combo.setToolTip("Global video ordering mode for non-series tags")
self.video_order_combo.setFixedWidth(150)
row1_layout.addWidget(self.video_order_combo)
```

**Connect signal** (after self.schedule_profile_combo setup):
```python
self.video_order_combo.currentIndexChanged.connect(self._on_video_order_changed)
```

**Initialize mode** (in `__init__` after `self.setup_ui()`):
```python
self.schedule_generator.video_order_mode = "random"
```

**Add slot method** to MainWindow:

```python
def _on_video_order_changed(self):
    mode_text = self.video_order_combo.currentText().lower().replace(" ", "_")
    self.schedule_generator.video_order_mode = mode_text
    self.tag_manager.clear_cache()
    self.refresh_preview()
```

**Update all generation entry points** to explicitly set the mode before generating:

In `generate_new_preview`, `generate_weekly_preview`, `generate_monthly_preview`, `run_approximate` — add at the top:

```python
self.schedule_generator.video_order_mode = (
    self.video_order_combo.currentText().lower().replace(" ", "_")
)
```

### Serialization (serialization.py)
No changes needed – the mode is global, not per-tag.

### Dialogs (dialogs/ package)
No changes needed – the setting is at main window level, not per-tag. The dialogs refactoring into a package maintains backward compatibility via `dialogs/__init__.py` re-exports, so no modifications required.

## Implementation Order

1. **Utils**: `extract_movie_sequence_key()`, `group_videos_by_movie()`
2. **Scheduler**: Add `video_order_mode` + `_get_videos_for_day()` helper
3. **Scheduler**: Update `generate_random_fill()`, `_build_random_entries()`
4. **Scheduler**: Update `_process_custom_tag()` and `_place_tag_videos()` custom branch
5. **Scheduler**: Update `_process_random_fill_tag()` (fill_24h branch)
6. **UI**: Add combobox + signal/slot in daypart_scheduler.py
7. **UI**: Wire mode updates to all generation entry points
8. **Testing**: Verify with sample collections containing multi-part movies

## Edge Cases & Considerations

| Scenario | Behavior |
|----------|----------|
| No numbers in any filename | All videos fall into group 1 → treated as one movie |
| Only some videos have numbers | Grouped by number; unnumberable videos go to group 1? |
| Duplicate movie numbers | All videos with same first number belong to same group |
| More days than movie groups | Wrap using modulo: day 5 uses group 1 again |
| Day has only 1 video in group | That single video plays, duration may be shorter than slot |
| Tag's `randomize_videos=True` with Movie Sequence | Videos within the selected movie's parts are shuffled |
| Tag's `video_count` limits number shown | Only first N videos from the day's movie group are used |
| Series tags | Unaffected – they use season/episode ordering |
| 24h Random Fill with Movie Sequence | Day-by-day grouping: each day gets next movie group, looping |

**Unnumberable videos**: Proposal – treat as movie group 1 (so they appear on Day 1). This ensures no video is lost.

## Testing Checklist

- [ ] Create test collection: files named `Movie 1 Part 1.mp4`, `Movie 1 Part 2.mp4`, `Movie 2 Part 1.mp4`, `Movie 2 Part 2.mp4`
- [ ] Mode=Random: verify each generation produces shuffled order
- [ ] Mode=Movie Sequence, 2-day schedule:
  - Day 1 shows only Movie 1 parts
  - Day 2 shows only Movie 2 parts
- [ ] Mode=Movie Sequence, 4-day schedule (2 movies): wrapping occurs (days 3/4 repeat movie 1/2)
- [ ] Tag with `randomize_videos=True`: parts within each movie shuffled
- [ ] Custom tag with time slot shorter than total movie duration: truncates correctly
- [ ] Series tags remain sequential/random per their own `play_mode`
- [ ] Approximate modes (Linear & Find-Replace) respect global mode
- [ ] Random Fill tag (fill_24h) respects mode across multiple days
- [ ] Weekly and Monthly calendar views show correct grouping

## Files Modified

```
daypart_scheduler.py     # UI combobox + signal handling
scheduler.py             # video_order_mode, _get_videos_for_day, updates to 5 methods
utils.py                # extract_movie_sequence_key, group_videos_by_movie
```

## Future Enhancements

- [ ] Allow per-tag override of global mode (combobox in TagDialog)
- [ ] Configurable extraction regex pattern
- [ ] Preview in UI: highlight which movie group appears on each day
- [ ] Option to sort by season+episode for series-like groupings across non-series tags

---

**Last Updated:** 2026-05-14  
**Status:** Draft for review  
**Owner:** Kilo (implementation agent)
