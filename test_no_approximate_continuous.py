#!/usr/bin/env python3
"""
Regression test for: Approximate OFF + random fill only + multi-day should
produce a continuous schedule, matching Approximate ON behavior.

Bug history: Previously, with Approximate OFF and a single fill_24h random
fill tag, each day was reset to 00:00 instead of continuing from the previous
day's end. The fix adds the missing fast-path in
CustomTagMergeStrategy.generate() so that the random-fill-only case delegates
to ScheduleGenerator.generate_random_fill(num_days*24*3600), producing a
single continuous stream from 0 to num_days*24*3600.

This test asserts:
  * total entries cover exactly num_days * 24 * 3600 seconds (no gaps)
  * the first entry starts at second 0
  * the last entry ends at second num_days * 24 * 3600
  * the schedule is continuous (each entry.end == next entry.start)
  * there are no overlapping entries
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QTime
from models import ScheduleGenerator, TagManager, Tag


def make_random_fill_tag():
    return Tag(
        name="RandomFill",
        tag_type="random_fill",
        start_time=QTime(0, 0),
        end_time=QTime(23, 59),
        is_random_fill=True,
        fill_24h=True,
        collection_videos=[
            {"file": "/tmp/v1.mp4", "duration": 90 * 60},
            {"file": "/tmp/v2.mp4", "duration": 120 * 60},
        ],
    )


def test_random_fill_only_3_days_continuous():
    """Approximate OFF + 1 fill_24h random fill + 3 days -> continuous schedule."""
    tm = TagManager()
    tm.add_tag(make_random_fill_tag())

    sg = ScheduleGenerator(tm)
    entries = sg.apply_custom_tags(num_days=3)

    assert len(entries) > 0, "Schedule should not be empty"

    # First entry starts at 0
    assert entries[0].start_seconds == 0, (
        f"First entry should start at 0, got {entries[0].start_seconds}"
    )

    # Last entry ends at num_days * 24 * 3600
    expected_end = 3 * 24 * 3600
    assert entries[-1].end_seconds == expected_end, (
        f"Last entry should end at {expected_end}, got {entries[-1].end_seconds}"
    )

    # Continuity: each entry.end == next entry.start
    for i in range(len(entries) - 1):
        e1 = entries[i]
        e2 = entries[i + 1]
        assert e1.end_seconds == e2.start_seconds, (
            f"Gap or overlap at entry {i}: "
            f"end={e1.end_seconds}, next_start={e2.start_seconds}"
        )
        assert e1.end_seconds > e1.start_seconds, (
            f"Zero-length entry at {i}: {e1.start_seconds}..{e1.end_seconds}"
        )

    # No overlaps: every entry is strictly after the previous
    for i in range(1, len(entries)):
        assert entries[i].start_seconds >= entries[i - 1].end_seconds, (
            f"Overlap at entry {i}: prev end={entries[i-1].end_seconds}, "
            f"this start={entries[i].start_seconds}"
        )

    # Total coverage equals num_days * 24 * 3600
    total_coverage = sum(e.end_seconds - e.start_seconds for e in entries)
    assert total_coverage == expected_end, (
        f"Total coverage {total_coverage} != expected {expected_end}"
    )

    print(f"PASS: 3-day random-fill-only schedule is continuous "
          f"({len(entries)} entries, full {expected_end // 3600}h coverage)")


def test_random_fill_only_1_day_continuous():
    """Approximate OFF + 1 fill_24h random fill + 1 day -> continuous schedule."""
    tm = TagManager()
    tm.add_tag(make_random_fill_tag())

    sg = ScheduleGenerator(tm)
    entries = sg.apply_custom_tags(num_days=1)

    assert len(entries) > 0, "Schedule should not be empty"
    assert entries[0].start_seconds == 0
    assert entries[-1].end_seconds == 24 * 3600

    for i in range(len(entries) - 1):
        e1 = entries[i]
        e2 = entries[i + 1]
        assert e1.end_seconds == e2.start_seconds, (
            f"Gap at entry {i}: end={e1.end_seconds}, next_start={e2.start_seconds}"
        )

    total = sum(e.end_seconds - e.start_seconds for e in entries)
    assert total == 24 * 3600

    print(f"PASS: 1-day random-fill-only schedule is continuous "
          f"({len(entries)} entries, full 24h coverage)")


def test_random_fill_only_7_days_continuous():
    """Approximate OFF + 1 fill_24h random fill + 7 days -> continuous schedule."""
    tm = TagManager()
    tm.add_tag(make_random_fill_tag())

    sg = ScheduleGenerator(tm)
    entries = sg.apply_custom_tags(num_days=7)

    assert len(entries) > 0
    assert entries[0].start_seconds == 0
    assert entries[-1].end_seconds == 7 * 24 * 3600

    for i in range(len(entries) - 1):
        e1 = entries[i]
        e2 = entries[i + 1]
        assert e1.end_seconds == e2.start_seconds, (
            f"Gap at entry {i}: end={e1.end_seconds}, next_start={e2.start_seconds}"
        )

    total = sum(e.end_seconds - e.start_seconds for e in entries)
    assert total == 7 * 24 * 3600

    print(f"PASS: 7-day random-fill-only schedule is continuous "
          f"({len(entries)} entries, full 7*24h coverage)")


def test_no_reset_at_day_boundary():
    """Approximate OFF: schedule should NOT reset to 00:00 each day.

    In the buggy version, day 1 ended at e.g. 22:30-00:30 and day 2 then had
    a separate block starting at 00:00, causing two overlapping entries near
    the day boundary. The fix produces a single continuous stream where no
    entry other than the very first one starts at a multiple of 86400.
    """
    tm = TagManager()
    tm.add_tag(make_random_fill_tag())

    sg = ScheduleGenerator(tm)
    entries = sg.apply_custom_tags(num_days=3)

    # First entry legitimately starts at 0. After that, no entry should
    # start exactly at a day boundary — that would indicate a reset.
    for i, e in enumerate(entries[1:], start=1):
        assert e.start_seconds % 86400 != 0, (
            f"Entry {i} starts at {e.start_seconds}s, which is a day boundary "
            f"(={e.start_seconds // 3600}h). This indicates the schedule was "
            f"reset to 00:00 at the day boundary instead of continuing."
        )

    # And the schedule should remain continuous across the day boundary.
    for i in range(len(entries) - 1):
        assert entries[i].end_seconds == entries[i + 1].start_seconds, (
            f"Discontinuity at entry {i}: end={entries[i].end_seconds}, "
            f"next_start={entries[i+1].start_seconds}"
        )

    print("PASS: schedule does not reset to 00:00 at any day boundary")


if __name__ == "__main__":
    test_random_fill_only_1_day_continuous()
    test_random_fill_only_3_days_continuous()
    test_random_fill_only_7_days_continuous()
    test_no_reset_at_day_boundary()
    print("\nAll regression tests passed.")
