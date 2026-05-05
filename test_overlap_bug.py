#!/usr/bin/env python3
"""
Test script to reproduce the overlapping bug in Find-Replace approximate.

Bug: When Approximate is ON (find-replace mode), random fill entries appear
inside custom/series tag time slots, starting at the same time as episodes.

Example from user's output:
  - Arcade hunters series tag: 13:00 - 15:15 (video_count=4)
  - Random entry "The Dark Legacy.mp4" starts at 13:19 (same as first episode)
    and runs 13:19-15:31, overlapping multiple episodes.

Expected: No random entries should overlap any custom/series tag times.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QTime
from models import ScheduleGenerator, TagManager, Tag, ScheduleEntry


def create_test_data():
    """Create test tags matching user's scenario."""
    tag_manager = TagManager()

    # Random fill tag with 24h fill using videos of varying durations
    rf_tag = Tag(
        name="Movie collection 01",
        tag_type="random_fill",
        start_time=QTime(0, 0),
        end_time=QTime(23, 59),
        is_random_fill=True,
        fill_24h=True,
        collection_videos=[
            # Simulate varying durations to generate the specific sequence
            {"file": "/path/to/Shadow Legacy.mp4", "duration": 130 * 60},    # 130 min → 00:59-03:09
            {"file": "/path/to/Sacred Justice.mp4", "duration": 113 * 60},   # 113 min → 03:09-06:02
            {"file": "/path/to/Cosmic Alliance Redemption.mp4", "duration": 103 * 60},  # 06:02-08:45
            {"file": "/path/to/Cosmic Galaxy Redemption.mp4", "duration": 171 * 60},    # 08:45-11:36
            {"file": "/path/to/Cyber Legends S02E02.mkv", "duration": 35 * 60}, # part of series, not random
            {"file": "/path/to/Cyber Legends S02E03.mkv", "duration": 31 * 60}, # part of series
            {"file": "/path/to/The Rising Paradox Part II.mp4", "duration": 37 * 60},   # 12:42-13:19
            {"file": "/path/to/The Dark Legacy.mp4", "duration": 132 * 60},  # 13:19-15:31 (BUG: should not appear)
            {"file": "/path/to/Cosmic Horizon The Final Chapter.mp4", "duration": 160 * 60}, # 15:34-18:14? but shown 15:34-17:58
            {"file": "/path/to/The Eternal Requiem Redemption.mp4", "duration": 148 * 60}, # 17:58-20:26
            {"file": "/path/to/The Shadow Legacy.mp4", "duration": 120 * 60}, # 20:26-22:36
            {"file": "/path/to/The Sacred Justice.mp4", "duration": 173 * 60}, # 22:36-01:29+1
        ]
    )
    tag_manager.add_tag(rf_tag)

    # Series tag 1: cyber Legends Series
    series_tag1 = Tag(
        name="cyber Legends Series",
        tag_type="custom",
        start_time=QTime(12, 0),
        end_time=QTime(13, 6),
        is_series=True,
        collection_videos=[
            {"file": "/path/to/cyber Legends S02E02.mkv", "duration": 35 * 60},
            {"file": "/path/to/cyber Legends S02E03.mkv", "duration": 31 * 60},
        ],
        start_season=1,
        start_episode=1,
        video_count=2,
        play_mode="sequence"
    )
    tag_manager.add_tag(series_tag1)

    # Series tag 2: Arcade hunters
    series_tag2 = Tag(
        name="Arcade hunters",
        tag_type="custom",
        start_time=QTime(13, 0),
        end_time=QTime(15, 15),
        is_series=True,
        collection_videos=[
            {"file": "/path/to/Arcade Hunters S02E05.mkv", "duration": 38 * 60},
            {"file": "/path/to/Arcade Hunters S02E08.mkv", "duration": 31 * 60},
            {"file": "/path/to/Arcade Hunters S01E01.mkv", "duration": 34 * 60},
            {"file": "/path/to/Arcade Hunters S01E09.mkv", "duration": 32 * 60},
        ],
        start_season=1,
        start_episode=1,
        video_count=4,
        play_mode="sequence"
    )
    tag_manager.add_tag(series_tag2)

    return tag_manager


def print_schedule(entries, title="Schedule"):
    """Print schedule entries in readable format."""
    print(f"\n{'='*70}")
    print(f"{title}")
    print(f"{'='*70}")
    for entry in entries:
        start_h = entry.start_minutes // 60
        start_m = entry.start_minutes % 60
        end_h = entry.end_minutes // 60
        end_m = entry.end_minutes % 60
        duration = entry.end_minutes - entry.start_minutes
        print(f"  {start_h:02d}:{start_m:02d} - {end_h:02d}:{end_m:02d} ({duration:3d} min) | {entry.video_name}")
    print()


def get_custom_time_ranges(tags):
    """Get all custom/series tag time ranges (in minutes) for the first day."""
    ranges = []
    for tag in tags:
        if tag.tag_type == "custom" or tag.is_series:
            start = QTime(0, 0).msecsTo(tag.start_time) // 60000
            end = QTime(0, 0).msecsTo(tag.end_time) // 60000
            duration = end - start
            # Adjust for day 0
            ranges.append((start, end, tag.name, duration))
    return ranges


def check_for_overlaps(entries, custom_ranges):
    """
    Check if any random entry (whose name does NOT match a custom tag name)
    starts within any custom/series tag's time range.
    Returns list of (entry, custom_tag) overlap pairs.
    """
    overlaps = []
    for entry in entries:
        # Skip custom/series entries
        is_custom = any(ct_name in entry.video_name for _, _, ct_name, _ in custom_ranges)
        if is_custom:
            continue
        for start, end, ct_name, _ in custom_ranges:
            # If entry starts at or after custom start and before custom end
            if start <= entry.start_minutes < end:
                overlaps.append((entry, ct_name, start, end))
    return overlaps


def test_overlap_bug():
    """Test that approximate find-replace does not place random entries inside custom tags."""
    print("=" * 70)
    print("TEST: Overlap Bug in Find-Replace Approximate")
    print("=" * 70)
    print("\nScenario:")
    print("  - Random fill (24h) with varying video durations")
    print("  - Series 1: cyber Legends Series  12:00 - 13:06 (2 episodes)")
    print("  - Series 2: Arcade hunters         13:00 - 15:15 (4 episodes)")
    print("\nExpected: No random entries should start within any series time range.")
    print("Bug: Random entry 'The Dark Legacy.mp4' appears at 13:19 (inside Arcade hunters)")

    tag_manager = create_test_data()
    generator = ScheduleGenerator(tag_manager)

    # Get custom ranges for checking
    custom_tags = tag_manager.get_custom_tags() + tag_manager.get_series_tags()
    custom_ranges = get_custom_time_ranges(custom_tags)

    print("\nCustom/series tag ranges (Day 1):")
    for start, end, name, dur in custom_ranges:
        print(f"  {name}: {start//60:02d}:{start%60:02d} - {end//60:02d}:{end%60:02d} ({dur} min)")

    # Run approximate find-replace
    print("\n" + "=" * 70)
    print("Running apply_approximate(mode='find_replace') for 30 days")
    print("=" * 70)
    entries = generator.apply_approximate(num_days=30, mode="find_replace")
    print_schedule(entries, "Full 30-day schedule (first day shown below)")

    # Show only day 1 entries
    day1_entries = [e for e in entries if e.start_minutes < 24*60]
    print_schedule(day1_entries, "Day 1 entries")

    # Check for overlaps
    print("\n" + "=" * 70)
    print("OVERLAP ANALYSIS")
    print("=" * 70)
    overlaps = check_for_overlaps(day1_entries, custom_ranges)

    if overlaps:
        print(f"*** BUG DETECTED: {len(overlaps)} overlapping random entry(ies) found! ***\n")
        for entry, ct_name, ct_start, ct_end in overlaps:
            print(f"  Random entry '{entry.video_name}'")
            print(f"    Starts at {entry.start_minutes//60:02d}:{entry.start_minutes%60:02d}")
            print(f"    Inside custom tag '{ct_name}' ({ct_start//60:02d}:{ct_start%60:02d}-{ct_end//60:02d}:{ct_end%60:02d})")
            print()
        return False
    else:
        print("  No overlaps detected. Test PASSED.")
        return True


if __name__ == "__main__":
    success = test_overlap_bug()
    sys.exit(0 if success else 1)
