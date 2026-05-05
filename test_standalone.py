#!/usr/bin/env python3
import sys
import os
import random

os.chdir('/home/akira/akira/day2')
sys.path.insert(0, '/home/akira/akira/day2')

from PySide6.QtCore import QTime
from models import ScheduleGenerator, TagManager, Tag, ScheduleEntry


def create_test_custom_tag_at_zero():
    """Test scenario: Custom tag at 00:00"""
    tag_manager = TagManager()

    # Random fill
    rf_tag = Tag(
        name="AkiraTV",
        tag_type="random_fill",
        start_time=QTime(0, 0),
        end_time=QTime(23, 59),
        is_random_fill=True,
        fill_24h=True,
        collection_videos=[
            {"file": "/path/to/A.mp4", "duration": 89 * 60},
            {"file": "/path/to/B.mp4", "duration": 90 * 60},
        ]
    )
    tag_manager.add_tag(rf_tag)

    # Custom tag at 00:00
    custom_tag = Tag(
        name="Horror_custom",
        tag_type="custom",
        start_time=QTime(0, 0),
        end_time=QTime(5, 9),
        collection_videos=[
            {"file": "/path/to/H1.mp4", "duration": 92 * 60},
            {"file": "/path/to/H2.mp4", "duration": 123 * 60},
            {"file": "/path/to/H3.mp4", "duration": 94 * 60},
        ],
        video_count=3
    )
    tag_manager.add_tag(custom_tag)
    return tag_manager


def create_test_series_at_zero():
    """Test scenario: Series tag at 00:00"""
    tag_manager = TagManager()

    # Random fill
    rf_tag = Tag(
        name="AkiraTV",
        tag_type="random_fill",
        start_time=QTime(0, 0),
        end_time=QTime(23, 59),
        is_random_fill=True,
        fill_24h=True,
        collection_videos=[
            {"file": "/path/to/A.mp4", "duration": 89 * 60},
            {"file": "/path/to/B.mp4", "duration": 90 * 60},
        ]
    )
    tag_manager.add_tag(rf_tag)

    # Series tag at 00:00
    series_tag = Tag(
        name="Avatar Series",
        tag_type="custom",
        start_time=QTime(0, 0),
        end_time=QTime(2, 0),
        is_series=True,
        collection_videos=[
            {"file": "/path/to/S1.mp4", "duration": 60 * 60},
        ],
        start_season=1,
        start_episode=1,
        video_count=1,
        play_mode="sequence"
    )
    tag_manager.add_tag(series_tag)
    return tag_manager


def print_schedule(entries, title="Schedule"):
    print(f"\n{'='*60}")
    print(f"{title}")
    print(f"{'='*60}")
    for entry in entries:
        start_h = entry.start_minutes // 60
        start_m = entry.start_minutes % 60
        end_h = entry.end_minutes // 60
        end_m = entry.end_minutes % 60
        duration = entry.end_minutes - entry.start_minutes
        print(f"  {start_h:02d}:{start_m:02d} - {end_h:02d}:{end_m:02d} ({duration:3d} min) | {entry.video_name}")
    print()


if __name__ == "__main__":
    print("=" * 70)
    print("TEST 1: Custom tag at 00:00")
    print("=" * 70)

    tag_manager = create_test_custom_tag_at_zero()
    generator = ScheduleGenerator(tag_manager)

    print("\n--- LINEAR MODE ---")
    entries = generator.apply_approximate(num_days=1, mode="linear")
    print_schedule(entries, "linear mode")
    print("Expected: Random continues after custom tag ends (5:09)")

    print("\n" + "=" * 70)
    print("TEST 2: Series tag at 00:00")
    print("=" * 70)

    tag_manager2 = create_test_series_at_zero()
    generator2 = ScheduleGenerator(tag_manager2)

    print("\n--- LINEAR MODE ---")
    entries2 = generator2.apply_approximate(num_days=1, mode="linear")
    print_schedule(entries2, "linear mode")
    print("Expected: Random continues after series ends (2:00)")