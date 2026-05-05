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

tg = create_test_data()
sg = ScheduleGenerator(tg)
entries = sg.apply_approximate(num_days=2, mode="linear")
print(f"Total entries: {len(entries)}")
for e in entries:
    day = e.start_minutes // (24*60)
    if day < 2:  # 0 and 1
        start_h = e.start_minutes // 60 % 24
        start_m = e.start_minutes % 60
        end_h = e.end_minutes // 60 % 24
        end_m = e.end_minutes % 60
        marker = ""
        if "Movie collection" in e.video_name:
            marker = " [RANDOM]"
        elif "cyber" in e.video_name or "Arcade" in e.video_name:
            marker = " [SERIES]"
        print(f"Day {day+1} {start_h:02d}:{start_m:02d} - {end_h:02d}:{end_m:02d}{marker} | {e.video_name}")
