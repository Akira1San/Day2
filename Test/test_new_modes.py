#!/usr/bin/env python3
import sys
sys.path.insert(0, '/home/akira/akira/day2')
from PySide6.QtCore import QTime
from models import TagManager, Tag

# Create tag manager with a random fill tag and a custom tag
tm = TagManager()
rf = Tag(
    name="RandomFill",
    tag_type="random_fill",
    start_time=QTime(0, 0),
    end_time=QTime(23, 59),
    is_random_fill=True,
    fill_24h=True,
    collection_videos=[
        {"file": "/tmp/v1.mp4", "duration": 90 * 60},
        {"file": "/tmp/v2.mp4", "duration": 120 * 60},
    ]
)
custom = Tag(
    name="CustomTag",
    tag_type="custom",
    start_time=QTime(10, 0),
    end_time=QTime(12, 0),
    collection_videos=[
        {"file": "/tmp/c1.mp4", "duration": 90 * 60},
    ],
    video_count=1
)
tm.add_tag(rf)
tm.add_tag(custom)

from models import ScheduleGenerator
sg = ScheduleGenerator(tm)

modes = ["find_replace", "linear", "early_fill", "late_fill", "priority", "best_fit", "round_robin", "linear_spanning", "exhaustive"]
for m in modes:
    try:
        entries = sg.apply_approximate(num_days=1, mode=m)
        print(f"Mode {m}: OK, {len(entries)} entries")
    except Exception as e:
        print(f"Mode {m}: ERROR -> {e}")
        import traceback
        traceback.print_exc()
