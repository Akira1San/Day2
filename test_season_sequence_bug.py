#!/usr/bin/env python3
"""
Test the season_sequence bug fix in _place_tag_videos.

Bug: For single-series tags with play_mode='season_sequence', _place_tag_videos
used modulo-wrapping on episode numbers, causing episodes to repeat or skip
after the first season when scheduled across multiple days.

Expected: Episodes should follow the flat ordering across seasons: S1E1, S1E2, S1E3, S2E1, S2E2...
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QTime
from scheduler import ScheduleGenerator
from data_models import TagManager, Tag


def create_test_data():
    """Create a series tag with season_sequence and a 24h random fill."""
    tag_manager = TagManager()

    # 24h random fill (required by approximate modes)
    rf_tag = Tag(
        name="Random Fill",
        tag_type="random_fill",
        start_time=QTime(0, 0),
        end_time=QTime(23, 59),
        is_random_fill=True,
        fill_24h=True,
        collection_videos=[
            {"path": "/path/to/Random1.mp4", "duration": 90 * 60},
            {"path": "/path/to/Random2.mp4", "duration": 90 * 60},
        ]
    )
    tag_manager.add_tag(rf_tag)

    # Series tag with season_sequence mode
    series_tag = Tag(
        name="Test Series",
        tag_type="custom",
        start_time=QTime(12, 0),
        end_time=QTime(13, 0),  # 60 minutes, fits exactly 1 episode (video_count=1)
        is_series=True,
        collection_videos=[
            {"path": "/path/to/Test Series S01E01.mkv", "duration": 60 * 60, "_meta_season": 1},
            {"path": "/path/to/Test Series S01E02.mkv", "duration": 60 * 60, "_meta_season": 1},
            {"path": "/path/to/Test Series S01E03.mkv", "duration": 60 * 60, "_meta_season": 1},
            {"path": "/path/to/Test Series S02E01.mkv", "duration": 60 * 60, "_meta_season": 2},
            {"path": "/path/to/Test Series S02E02.mkv", "duration": 60 * 60, "_meta_season": 2},
        ],
        start_season=1,
        start_episode=1,
        video_count=1,
        play_mode="season_sequence"
    )
    tag_manager.add_tag(series_tag)

    return tag_manager


def parse_season_episode(filename):
    """Extract season and episode numbers from filename like 'Test Series S01E01.mkv'."""
    import re
    match = re.search(r'S(\d+)E(\d+)', filename)
    if match:
        return int(match.group(1)), int(match.group(2))
    return None, None


def test_season_sequence_bug():
    """Test that season_sequence schedules episodes in flat order across days."""
    print("=" * 70)
    print("TEST: season_sequence bug in _place_tag_videos")
    print("=" * 70)
    print("\nScenario:")
    print("  - Series tag with play_mode='season_sequence', video_count=1")
    print("  - Episodes: S1E1, S1E2, S1E3, S2E1, S2E2")
    print("  - 24h random fill tag present")
    print("  - Running apply_approximate(mode='find_replace') for 5 days")
    print("\nExpected episode order: Day1=S1E1, Day2=S1E2, Day3=S1E3, Day4=S2E1, Day5=S2E2")
    print("Bug (before fix): Wrapping within season 1, repeats or wrong episodes")

    tag_manager = create_test_data()
    generator = ScheduleGenerator(tag_manager)

    # Run approximate for 5 days
    entries = generator.apply_approximate(num_days=5, mode="find_replace")

    # Extract series entries for each day (day 1-5)
    day_series_entries = {}
    for entry in entries:
        day = entry.start_minutes // (24 * 60) + 1
        if 1 <= day <= 5 and "Test Series" in entry.video_name:
            day_series_entries.setdefault(day, []).append(entry)

    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    observed = []
    for day in range(1, 6):
        entries_today = day_series_entries.get(day, [])
        if entries_today:
            # Should be exactly 1 entry per day (video_count=1)
            entry = entries_today[0]
            season, episode = parse_season_episode(entry.video_name)
            print(f"  Day {day}: {entry.video_name} -> S{season}E{episode}")
            observed.append((season, episode))
        else:
            print(f"  Day {day}: No series entry found")
            observed.append(None)

    # Check expected order: S1E1, S1E2, S1E3, S2E1, S2E2
    expected = [(1,1), (1,2), (1,3), (2,1), (2,2)]

    print("\n" + "=" * 70)
    print("VERIFICATION")
    print("=" * 70)
    passed = True
    for day in range(1, 6):
        obs = observed[day-1]
        exp = expected[day-1]
        if obs == exp:
            print(f"  Day {day}: PASS (got S{obs[0]}E{obs[1]})")
        else:
            print(f"  Day {day}: FAIL (expected S{exp[0]}E{exp[1]}, got {obs})")
            passed = False

    if passed:
        print("\nTest PASSED: Season sequence order is correct across all days.")
    else:
        print("\nTest FAILED: Season sequence order is incorrect.")

    return passed


if __name__ == "__main__":
    success = test_season_sequence_bug()
    sys.exit(0 if success else 1)
