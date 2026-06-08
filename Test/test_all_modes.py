#!/usr/bin/env python3
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
random.seed(42)
from PySide6.QtCore import QTime
from models import ScheduleGenerator, TagManager, Tag

def create_test_data():
    tag_manager = TagManager()
    rf_tag = Tag(
        name="Movie collection 01", tag_type="random_fill",
        start_time=QTime(0,0), end_time=QTime(23,59),
        is_random_fill=True, fill_24h=True,
        collection_videos=[
            {"file":"/p/1.mp4","duration":160*60},{"file":"/p/2.mp4","duration":171*60},{"file":"/p/3.mp4","duration":148*60},
            {"file":"/p/4.mp4","duration":103*60},{"file":"/p/5.mp4","duration":37*60},{"file":"/p/6.mp4","duration":132*60},
            {"file":"/p/7.mp4","duration":120*60},{"file":"/p/8.mp4","duration":113*60},{"file":"/p/9.mp4","duration":95*60},
            {"file":"/p/10.mp4","duration":105*60},{"file":"/p/11.mp4","duration":88*60},{"file":"/p/12.mp4","duration":142*60},
        ])
    tag_manager.add_tag(rf_tag)
    series_tag1 = Tag(
        name="cyber Legends Series", tag_type="custom",
        start_time=QTime(12,0), end_time=QTime(13,6),
        is_series=True,
        collection_videos=[
            {"file":"/p/c1.mkv","duration":35*60},{"file":"/p/c2.mkv","duration":31*60},
        ],
        start_season=1, start_episode=1, video_count=2, play_mode="sequence")
    tag_manager.add_tag(series_tag1)
    series_tag2 = Tag(
        name="Arcade hunters", tag_type="custom",
        start_time=QTime(13,0), end_time=QTime(15,15),
        is_series=True,
        collection_videos=[
            {"file":"/p/a1.mkv","duration":38*60},{"file":"/p/a2.mkv","duration":31*60},
            {"file":"/p/a3.mkv","duration":30*60},{"file":"/p/a4.mkv","duration":26*60},
        ],
        start_season=1, start_episode=1, video_count=4, play_mode="sequence")
    tag_manager.add_tag(series_tag2)
    return tag_manager

def get_tag_ranges(num_days):
    ranges = []
    for day in range(num_days):
        day_start = day * 24*60
        # Original tag times (not shifted)
        ranges.append((day_start + 12*60, day_start + 13*60 + 6, "cyber Legends Series"))
        ranges.append((day_start + 13*60, day_start + 15*60 + 15, "Arcade hunters"))
    return ranges

def check_overlaps(entries, tag_ranges):
    overlaps = []
    for entry in entries:
        for tag_start, tag_end, tag_name in tag_ranges:
            if tag_start <= entry.start_minutes < tag_end:
                overlaps.append(entry)
                break
    return overlaps

def check_overlaps(entries, tag_ranges):
    overlaps = []
    for entry in entries:
        # Skip entries that are part of the tag itself (series/custom entries)
        is_tag_entry = any(tag_name in entry.video_name for _, _, tag_name in tag_ranges)
        if is_tag_entry:
            continue
        for tag_start, tag_end, tag_name in tag_ranges:
            if tag_start <= entry.start_minutes < tag_end:
                overlaps.append((entry, tag_name))
                break
    return overlaps

tg = create_test_data()
sg = ScheduleGenerator(tg)
modes = ["find_replace", "linear", "early_fill", "late_fill", "priority", "best_fit", "round_robin", "linear_spanning", "exhaustive"]
tag_ranges = get_tag_ranges(7)
for mode in modes:
    try:
        entries = sg.apply_approximate(num_days=7, mode=mode)
        ov = check_overlaps(entries, tag_ranges)
        print(f"Mode {mode:15s}: {len(entries)} entries, overlaps: {len(ov)}")
        if ov:
            # Show first 3 unique days
            shown = 0
            for e, tname in ov:
                day = e.start_minutes // (24*60) + 1
                print(f"    Day {day} {e.start_minutes//60:02d}:{e.start_minutes%60:02d} - {e.video_name} (inside {tname})")
                shown += 1
                if shown >= 5:
                    break
    except Exception as e:
        print(f"Mode {mode}: ERROR {e}")
        import traceback; traceback.print_exc()
