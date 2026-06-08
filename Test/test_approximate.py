#!/usr/bin/env python3
"""
Test script to reproduce the Approximate algorithm bug.

Bug: When Approximate is ON, the random fill video before a custom/series tag
gets truncated incorrectly. For example:
- Series tag: 13:00 - 14:46
- Expected: Random fill should span 00:00 - 13:00 (or continue through)
- Actual: Random fill shows as 12:55 - 13:00 (only 5 minutes!)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QTime
from models import ScheduleGenerator, TagManager, Tag, ScheduleEntry


def create_test_data():
    """Create test tags to reproduce the bug."""
    tag_manager = TagManager()

    # Create a random fill tag with 24h fill - full day coverage
    rf_tag = Tag(
        name="AkiraTV",
        tag_type="random_fill",
        start_time=QTime(0, 0),
        end_time=QTime(23, 59),
        is_random_fill=True,
        fill_24h=True,  # Full 24h fill
        collection_videos=[
            {"file": "/path/to/video1.mkv", "duration": 90 * 60},  # 90 min
            {"file": "/path/to/video2.mkv", "duration": 90 * 60},
            {"file": "/path/to/video3.mkv", "duration": 90 * 60},
        ]
    )
    tag_manager.add_tag(rf_tag)

    # Create a series tag at 13:00 - 14:46
    series_tag = Tag(
        name="Avatar Series",
        tag_type="custom",
        start_time=QTime(13, 0),
        end_time=QTime(14, 46),
        is_series=True,
        collection_videos=[
            {"file": "/path/to/avatar1.mkv", "duration": 21 * 60},
            {"file": "/path/to/avatar2.mkv", "duration": 21 * 60},
            {"file": "/path/to/avatar3.mkv", "duration": 21 * 60},
            {"file": "/path/to/avatar4.mkv", "duration": 21 * 60},
            {"file": "/path/to/avatar5.mkv", "duration": 21 * 60},
            {"file": "/path/to/avatar6.mkv", "duration": 21 * 60},
        ],
        start_season=1,
        start_episode=1,
        video_count=6,
        play_mode="sequence"
    )
    tag_manager.add_tag(series_tag)

    return tag_manager


def print_schedule(entries, title="Schedule"):
    """Print schedule entries in readable format."""
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


def test_approximate_bug():
    """Test the approximate algorithm to reproduce the bug."""
    print("=" * 70)
    print("TEST: Approximate Algorithm Bug Reproduction")
    print("=" * 70)
    print("\nSetup:")
    print("  - Random fill tag (AkiraTV): 12:30 - 02:00, has ~90min videos")
    print("  - Series tag (Avatar): 13:00 - 14:46")
    print("\nExpected behavior when Approximate is OFF:")
    print("  - Leave overlaps as-is: random 12:30-14:00, series 13:00-14:46 (overlap)")
    print("\nExpected behavior when Approximate is ON (Linear placement):")
    print("  - Series at 13:00, random fills around it without overlap")
    print("  - Random 12:30-13:00 (30 min), series 13:00-14:46, random continues after")

    tag_manager = create_test_data()
    generator = ScheduleGenerator(tag_manager)

    # Test with Approximate OFF (apply_custom_tags)
    print("\n" + "=" * 70)
    print("Running apply_custom_tags() - Approximate OFF")
    print("=" * 70)
    entries_off = generator.apply_custom_tags(num_days=1)
    print_schedule(entries_off, "Approximate OFF (apply_custom_tags)")

    # Analyze OFF results
    print("ANALYSIS - Approximate OFF:")
    off_before = None
    off_after = None
    for entry in entries_off:
        if "AkiraTV" in entry.video_name:
            if entry.start_minutes < 13*60:  # before 13:00
                if off_before is None or entry.start_minutes > off_before.start_minutes:
                    off_before = entry
            if entry.end_minutes > 14*60+46:  # after 14:46
                if off_after is None or entry.start_minutes < off_after.start_minutes:
                    off_after = entry
    if off_before:
        print(f"  Random fill before 13:00: {off_before.start_minutes//60}:{off_before.start_minutes%60:02d} - {off_before.end_minutes//60}:{off_before.end_minutes%60:02d} ({off_before.end_minutes-off_before.start_minutes}min)")
    if off_after:
        print(f"  Random fill after 14:46: {off_after.start_minutes//60}:{off_after.start_minutes%60:02d} - {off_after.end_minutes//60}:{off_after.end_minutes%60:02d} ({off_after.end_minutes-off_after.start_minutes}min)")

    # Test with Approximate ON - Find and Replace mode
    print("\n" + "=" * 70)
    print("Running apply_approximate() - Find and Replace mode")
    print("=" * 70)
    entries_on = generator.apply_approximate(num_days=1, mode="find_replace")
    print_schedule(entries_on, "Approximate ON (find_replace)")

    # Test with Approximate ON - Linear mode
    print("\n" + "=" * 70)
    print("Running apply_approximate() - Linear mode")
    print("=" * 70)
    entries_linear = generator.apply_approximate(num_days=1, mode="linear")
    print_schedule(entries_linear, "Approximate ON (linear)")

    # Analyze ON results
    print("ANALYSIS - Approximate ON:")
    on_before = None
    on_after = None
    for entry in entries_on:
        if "AkiraTV" in entry.video_name:
            if entry.start_minutes < 13*60:  # before 13:00
                if on_before is None or entry.start_minutes > on_before.start_minutes:
                    on_before = entry
            if entry.end_minutes > 14*60+46:  # after 14:46
                if on_after is None or entry.start_minutes < on_after.start_minutes:
                    on_after = entry
    if on_before:
        print(f"  Random fill before 13:00: {on_before.start_minutes//60}:{on_before.start_minutes%60:02d} - {on_before.end_minutes//60}:{on_before.end_minutes%60:02d} ({on_before.end_minutes-on_before.start_minutes}min)")
    if on_after:
        print(f"  Random fill after 14:46: {on_after.start_minutes//60}:{on_after.start_minutes%60:02d} - {on_after.end_minutes//60}:{on_after.end_minutes%60:02d} ({on_after.end_minutes-on_after.start_minutes}min)")

    # Check if bug exists
    print("\n" + "=" * 70)
    print("BUG CHECK")
    print("=" * 70)
    if on_before and (on_before.end_minutes - on_before.start_minutes) < 30:
        print(f"*** BUG DETECTED! ***")
        print(f"  Random fill before series is only {on_before.end_minutes - on_before.start_minutes} min")
        print(f"  Expected: ~30 min (from 12:30 to 13:00)")
        return False
    elif off_before and on_before:
        dur_off = off_before.end_minutes - off_before.start_minutes
        dur_on = on_before.end_minutes - on_before.start_minutes
        if dur_off != dur_on:
            print(f"  Difference detected:")
            print(f"    OFF:  {dur_off} min")
            print(f"    ON:   {dur_on} min")
    else:
        print("  No obvious bug detected in this test case")

    print("\n" + "=" * 70)
    print("TEST COMPLETE")
    print("=" * 70)
    return True


if __name__ == "__main__":
    success = test_approximate_bug()
    sys.exit(0 if success else 1)