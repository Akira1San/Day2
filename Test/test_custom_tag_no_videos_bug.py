#!/usr/bin/env python3
"""Test: 'No videos' placeholder should not overlap custom tag content when
no random fill videos are available (linear strategy fallback path)."""
import sys
sys.path.insert(0, '/home/akira/akira/day2')
import random
random.seed(42)
from PySide6.QtCore import QTime
from models import ScheduleGenerator, TagManager, Tag

VIDEOS = [
    {"path": "/v/a.mp4", "duration": 7943.46},
    {"path": "/v/b.mp4", "duration": 10266.02},
    {"path": "/v/c.mp4", "duration": 8930.3},
    {"path": "/v/d.mp4", "duration": 7828.85},
    {"path": "/v/e.mp4", "duration": 8854.95},
    {"path": "/v/f.mp4", "duration": 10380.74},
]

def has_no_videos(entries):
    return any("No videos" in e.video_name for e in entries)

def overlapping_starts(entries):
    seen = {}
    for e in entries:
        if e.start_seconds in seen:
            return True
        seen[e.start_seconds] = e
    return False

# Test 1: Linear strategy (fallback when no rf tag exists)
tg = TagManager()
tg.add_tag(Tag(
    name="Custom Test", tag_type="custom",
    start_time=QTime(0,0), end_time=QTime(23,19),
    randomize_videos=True, video_count=6, is_random_fill=False, is_series=False,
    collection_videos=VIDEOS,
))
sg = ScheduleGenerator(tg)
sg.video_order_mode = "random"
entries = sg.apply_approximate(num_days=1, mode="find_replace")
assert not has_no_videos(entries), "No videos placeholder should not appear in linear fallback"
assert not overlapping_starts(entries), "No overlapping entries in linear fallback"
print("Test 1 (linear/no-rf-fallback): OK, %d entries" % len(entries))

# Test 2: Find-replace with empty rf videos
tg2 = TagManager()
tg2.add_tag(Tag(
    name="RF", tag_type="random_fill",
    start_time=QTime(0,0), end_time=QTime(23,59),
    is_random_fill=True, fill_24h=True,
    collection_videos=[],
))
tg2.add_tag(Tag(
    name="Custom Test", tag_type="custom",
    start_time=QTime(0,0), end_time=QTime(23,19),
    randomize_videos=True, video_count=6, is_random_fill=False, is_series=False,
    collection_videos=VIDEOS,
))
random.seed(42)
sg2 = ScheduleGenerator(tg2)
sg2.video_order_mode = "random"
entries2 = sg2.apply_approximate(num_days=1, mode="find_replace")
assert not has_no_videos(entries2), "No videos placeholder should not appear in find_replace"
assert not overlapping_starts(entries2), "No overlapping entries in find_replace"
print("Test 2 (find_replace/empty-rf): OK, %d entries" % len(entries2))

# Test 3: Linear strategy directly (no custom tags edge case - no rf at all)
tg3 = TagManager()
tg3.add_tag(Tag(
    name="Custom Test", tag_type="custom",
    start_time=QTime(0,0), end_time=QTime(23,19),
    randomize_videos=True, video_count=6, is_random_fill=False, is_series=False,
    collection_videos=VIDEOS,
))
random.seed(42)
sg3 = ScheduleGenerator(tg3)
sg3.video_order_mode = "random"
entries3 = sg3.apply_approximate(num_days=1, mode="linear")
assert not has_no_videos(entries3), "No videos placeholder should not appear in linear direct"
assert not overlapping_starts(entries3), "No overlapping entries in linear direct"
print("Test 3 (linear/direct): OK, %d entries" % len(entries3))

# Test 4: Linear strategy with non-empty rf (should still work)
tg4 = TagManager()
tg4.add_tag(Tag(
    name="RF", tag_type="random_fill",
    start_time=QTime(0,0), end_time=QTime(23,59),
    is_random_fill=True, fill_24h=False,
    collection_videos=[
        {"path": "/v/r1.mp4", "duration": 7200},
        {"path": "/v/r2.mp4", "duration": 5400},
    ],
))
tg4.add_tag(Tag(
    name="Custom Test", tag_type="custom",
    start_time=QTime(0,0), end_time=QTime(23,19),
    randomize_videos=True, video_count=6, is_random_fill=False, is_series=False,
    collection_videos=VIDEOS,
))
random.seed(42)
sg4 = ScheduleGenerator(tg4)
sg4.video_order_mode = "random"
entries4 = sg4.apply_approximate(num_days=1, mode="linear")
# With non-empty rf videos, No videos placeholder should NOT appear
assert not has_no_videos(entries4), "No videos placeholder should not appear when rf has videos"
print("Test 4 (linear/with-rf-videos): OK, %d entries" % len(entries4))

print("\nAll tests passed.")
