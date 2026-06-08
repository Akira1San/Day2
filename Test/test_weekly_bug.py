#!/usr/bin/env python3
"""
Comprehensive weekly test to reproduce the schedule timing bug.

This test recreates the user's exact scenario with multiple series
and varying video durations to expose overlap issues in find_replace mode.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import random
random.seed(42)  # For reproducible results

from PySide6.QtCore import QTime
from models import ScheduleGenerator, TagManager, Tag, ScheduleEntry
import logging

# Enable DEBUG logging
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')


def create_test_data():
    """Create test tags matching user's exact scenario."""
    tag_manager = TagManager()

    # Random fill tag "Movie collection 01" with 24h coverage
    # Durations from user output (approximate):
    #   Cosmic Horizon The Final Chapter: 160 min
    #   Cyber Legends S03E05: not in random (it's a separate series)
    #   Cyber Legends S02E05: not in random (separate series)
    #   Eternal Requiem Redemption: 148 min
    #   Cosmic Galaxy Redemption: 171 min
    #   The Rising Paradox Part II: ~37 min
    #   The Dark Legacy.mp4: 132 min (BUG: appears inside Arcade hunters)
    #   Cosmic Alliance Redemption: 103 min
    rf_tag = Tag(
        name="Movie collection 01",
        tag_type="random_fill",
        start_time=QTime(0, 0),
        end_time=QTime(23, 59),
        is_random_fill=True,
        fill_24h=True,
        collection_videos=[
            {"file": "/path/to/Cosmic Horizon The Final Chapter.mp4", "duration": 160 * 60},
            {"file": "/path/to/Cosmic Galaxy Redemption.mp4", "duration": 171 * 60},
            {"file": "/path/to/Eternal Requiem Redemption.mp4", "duration": 148 * 60},
            {"file": "/path/to/Cosmic Alliance Redemption.mp4", "duration": 103 * 60},
            {"file": "/path/to/The Rising Paradox Part II.mp4", "duration": 37 * 60},
            {"file": "/path/to/The Dark Legacy.mp4", "duration": 132 * 60},  # BUG culprit
            {"file": "/path/to/Shadow Legacy.mp4", "duration": 120 * 60},
            {"file": "/path/to/Sacred Justice.mp4", "duration": 113 * 60},
            # Add a few more to fill the week realistically
            {"file": "/path/to/Another Movie 1.mp4", "duration": 95 * 60},
            {"file": "/path/to/Another Movie 2.mp4", "duration": 105 * 60},
            {"file": "/path/to/Another Movie 3.mp4", "duration": 88 * 60},
            {"file": "/path/to/Another Movie 4.mp4", "duration": 142 * 60},
        ]
    )
    tag_manager.add_tag(rf_tag)

    # Series 1: cyber Legends Series 12:00 - 13:06 (2 episodes)
    series_tag1 = Tag(
        name="cyber Legends Series",
        tag_type="custom",
        start_time=QTime(12, 0),
        end_time=QTime(13, 6),
        is_series=True,
        collection_videos=[
            {"file": "/path/to/cyber Legends S02E02.mkv", "duration": 35 * 60},
            {"file": "/path/to/cyber Legends S02E03.mkv", "duration": 31 * 60},
            # Add some more to test episode cycling
            {"file": "/path/to/cyber Legends S03E05.mkv", "duration": 33 * 60},
        ],
        start_season=1,
        start_episode=1,
        video_count=2,
        play_mode="sequence"
    )
    tag_manager.add_tag(series_tag1)

    # Series 2: Arcade hunters 13:00 - 15:15 (4 episodes)
    series_tag2 = Tag(
        name="Arcade hunters",
        tag_type="custom",
        start_time=QTime(13, 0),
        end_time=QTime(15, 15),
        is_series=True,
        collection_videos=[
            {"file": "/path/to/Arcade Hunters S02E02.mkv", "duration": 38 * 60},
            {"file": "/path/to/Arcade Hunters S02E05.mkv", "duration": 31 * 60},
            {"file": "/path/to/Arcade Hunters S01E06.mkv", "duration": 30 * 60},
            {"file": "/path/to/Arcade Hunters S02E11.mkv", "duration": 26 * 60},
        ],
        start_season=1,
        start_episode=1,
        video_count=4,
        play_mode="sequence"
    )
    tag_manager.add_tag(series_tag2)

    return tag_manager


def print_schedule(entries, title="Schedule", day_filter=None):
    """Print schedule entries in readable format."""
    print(f"\n{'='*70}")
    print(f"{title}")
    print(f"{'='*70}")
    count = 0
    for entry in entries:
        # Filter by day if requested
        if day_filter is not None:
            entry_day = entry.start_minutes // (24 * 60)
            if entry_day != day_filter:
                continue
        count += 1
        start_h = entry.start_minutes // 60
        start_m = entry.start_minutes % 60
        end_h = entry.end_minutes // 60
        end_m = entry.end_minutes % 60
        duration = entry.end_minutes - entry.start_minutes
        day = (entry.start_minutes // (24 * 60)) + 1
        marker = ""
        if "Movie collection" in entry.video_name and day <= 7:
            # Check if this random entry would overlap any tag
            marker = " [RANDOM]"
        elif any(series in entry.video_name for series in ["cyber Legends", "Arcade hunters"]):
            marker = " [SERIES]"
        print(f"  Day {day} {start_h:02d}:{start_m:02d} - {end_h:02d}:{end_m:02d} ({duration:3d} min) | {entry.video_name}{marker}")
    if count == 0:
        print("  (no entries)")
    print()


def check_for_overlaps(entries, num_days=7):
    """
    Check if any random entry (whose name does NOT match a custom tag name)
    starts within any custom/series tag's time range on any day.
    Returns list of overlap details.
    """
    # Define tag names (series tags only - random fill has different name)
    tag_names = ["cyber Legends Series", "Arcade hunters"]
    
    overlaps = []
    for day in range(num_days):
        day_start = day * 24 * 60
        day_end = day_start + 24 * 60
        
        # Get all custom/series tag ranges for this day
        # We need to re-derive from config since tags are time-based
        # For this test, we know the tag times: 12:00-13:06 and 13:00-15:15
        tag_ranges = [
            (day_start + 12*60, day_start + 13*60 + 6, "cyber Legends Series"),
            (day_start + 13*60, day_start + 15*60 + 15, "Arcade hunters"),
        ]
        
        for entry in entries:
            entry_start = entry.start_minutes
            entry_end = entry.end_minutes
            
            # Skip if not on this day
            if entry_start >= day_end or entry_end <= day_start:
                continue
                
            # Skip if it's a series entry (it's allowed to be in its slot)
            if any(name in entry.video_name for name in tag_names):
                continue
                
            # Check if entry starts within any tag range
            for tag_start, tag_end, tag_name in tag_ranges:
                if tag_start <= entry_start < tag_end:
                    overlaps.append({
                        'day': day + 1,
                        'entry': entry,
                        'tag_name': tag_name,
                        'tag_start': tag_start,
                        'tag_end': tag_end,
                    })
    return overlaps


def main():
    print("=" * 80)
    print("WEEKLY SCHEDULE BUG REPRODUCTION TEST")
    print("=" * 80)
    print("\nScenario: Approximate mode (find_replace) over 7 days")
    print("  Random fill: Movie collection 01 (24h)")
    print("  Series tags:")
    print("    - cyber Legends Series: 12:00 - 13:06 (video_count=2)")
    print("    - Arcade hunters:        13:00 - 15:15 (video_count=4)")
    print("\nExpected: No random entry should start inside any series time slot")
    print("Bug: Random entry 'The Dark Legacy.mp4' appears at 13:19 inside Arcade hunters")
    print()
    
    tag_manager = create_test_data()
    generator = ScheduleGenerator(tag_manager)
    
    # Run find_replace for 7 days
    print("\n" + "=" * 80)
    print("GENERATING 7-DAY SCHEDULE (find_replace mode)")
    print("=" * 80)
    
    entries = generator.apply_approximate(num_days=7, mode="find_replace")
    
    print(f"\nTotal entries generated: {len(entries)}")
    
    # Print each day separately
    for day in range(7):
        day_entries = [e for e in entries if e.start_minutes // (24*60) == day]
        print_schedule(day_entries, f"Day {day+1} Schedule")
    
    # Check for overlaps
    print("\n" + "=" * 80)
    print("OVERLAP ANALYSIS")
    print("=" * 80)
    
    overlaps = check_for_overlaps(entries, num_days=7)
    
    if overlaps:
        print(f"*** BUG DETECTED: {len(overlaps)} overlap(s) found! ***\n")
        for ov in overlaps[:10]:  # Show first 10
            entry = ov['entry']
            start_h = entry.start_minutes // 60
            start_m = entry.start_minutes % 60
            end_h = entry.end_minutes // 60
            end_m = entry.end_minutes % 60
            tag_start_h = ov['tag_start'] // 60
            tag_start_m = ov['tag_start'] % 60
            tag_end_h = ov['tag_end'] // 60
            tag_end_m = ov['tag_end'] % 60
            print(f"  Day {ov['day']}: Random entry '{entry.video_name}'")
            print(f"    Starts at {start_h:02d}:{start_m:02d} - inside '{ov['tag_name']}' ({tag_start_h:02d}:{tag_start_m:02d}-{tag_end_h:02d}:{tag_end_m:02d})")
            print()
        return False
    else:
        print("  ✓ No overlaps detected. Test PASSED.")
        return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
