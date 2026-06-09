#!/usr/bin/env python3
"""
Test the overlap resolution combobox strategies (fragment/skip/gap-fill/compact).

Reproduces the bug scenario: custom tag (09:00-23:19) + random fill (00:00-23:59, fill_24h)
in approximate find-replace mode. Verifies each strategy produces valid output.

Expected behavior for each strategy:
  fragment:  head/tail fragments (FRAGMENT_TAG_TYPE), full 24h coverage
  skip:      no fragments, gaps where overlapped entries removed
  compact:   no fragments, entries shifted to close gaps at tag boundaries
"""
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
random.seed(42)

from PySide6.QtCore import QTime
from models import ScheduleGenerator, TagManager, Tag
from data_models import FRAGMENT_TAG_TYPE


def make_video(name: str, dur_min: int) -> dict:
    return {"path": f"/p/{name}.mp4", "duration": dur_min * 60}


def build_tag_manager() -> TagManager:
    tg = TagManager()

    # Random fill — 24h fill, 6 videos
    tg.add_tag(Tag(
        name="Random Fill", tag_type="random_fill",
        start_time=QTime(0, 0), end_time=QTime(23, 59),
        is_random_fill=True, fill_24h=True,
        collection_videos=[make_video(f"video_{c}", 90) for c in "ABCDEF"],
    ))

    # Custom tag — 09:00-23:19, 6 videos (same as Custom test.ini)
    tg.add_tag(Tag(
        name="Custom Test", tag_type="custom",
        start_time=QTime(9, 0), end_time=QTime(23, 19),
        randomize_videos=True, video_count=6,
        collection_videos=[make_video(f"custom_{i}", 90) for i in range(1, 7)],
    ))

    return tg


def check_entry_continuity(entries, title: str, day_start=0, day_end=86400):
    """Check for gaps and overlaps between consecutive entries."""
    day_entries = [e for e in entries if e.start_seconds < day_end and e.end_seconds > day_start]
    day_entries.sort(key=lambda e: e.start_seconds)

    gaps = 0
    overlaps = 0
    prev_end = day_start
    for e in day_entries:
        if e.start_seconds > prev_end + 1:
            gaps += 1
        if e.start_seconds < prev_end - 1:
            overlaps += 1
        prev_end = max(prev_end, e.end_seconds)

    return gaps, overlaps


def test_strategy(mode: str = "find_replace", overlap_strategy: str = "fragment"):
    tg = build_tag_manager()
    sg = ScheduleGenerator(tg)
    entries = sg.apply_approximate(num_days=2, mode=mode, overlap_strategy=overlap_strategy)

    fragments = sum(1 for e in entries if e.tag_type == FRAGMENT_TAG_TYPE)
    total_sec = sum(e.end_seconds - e.start_seconds for e in entries)

    # Check each day for gaps and overlaps
    total_gaps = 0
    total_overlaps = 0
    for day in range(2):
        day_start = day * 86400
        day_end = day_start + 86400
        g, o = check_entry_continuity(entries, f"Day {day+1}", day_start, day_end)
        total_gaps += g
        total_overlaps += o

    return entries, fragments, total_sec, total_gaps, total_overlaps


def print_entry(e):
    sh, sm = (e.start_seconds // 3600) % 24, (e.start_seconds % 3600) // 60
    eh, em = (e.end_seconds // 3600) % 24, (e.end_seconds % 3600) // 60
    tag = " FRAG" if e.tag_type == FRAGMENT_TAG_TYPE else ""
    return f"  {sh:02d}:{sm:02d}-{eh:02d}:{em:02d} {e.video_name}{tag}"


def run_tests():
    print("=" * 70)
    print("Overlap Resolution Strategy Tests")
    print("=" * 70)

    modes = ["find_replace", "early_fill", "late_fill", "priority", "best_fit", "linear_spanning"]
    strategies = ["fragment", "skip", "compact"]

    all_pass = True
    for mode in modes:
        print(f"\n--- Mode: {mode} ---")
        for strat in strategies:
            entries, frags, total_sec, gaps, overlaps = test_strategy(mode, strat)
            cov_h = total_sec // 3600
            cov_m = (total_sec % 3600) // 60
            print(f"  {strat:>10}: {len(entries):2d} entries, {frags:2d} fragments, "
                  f"{cov_h:2d}h{cov_m:02d}m coverage, {gaps} gaps, {overlaps} overlaps")

            if gaps > 0 or overlaps > 0:
                all_pass = False
                for e in entries:
                    print(print_entry(e))

    # Detailed test with the exact user scenario (find_replace)
    print(f"\n{'='*70}")
    print("Detailed output — find_replace, all 3 strategies")
    print(f"{'='*70}")
    for strat in strategies:
        entries, frags, total_sec, gaps, overlaps = test_strategy("find_replace", strat)
        cov_h = total_sec // 3600
        cov_m = (total_sec % 3600) // 60
        print(f"\n{strat.upper()} ({len(entries)} entries, {frags} frags, "
              f"{cov_h}h{cov_m}m, {gaps} gaps, {overlaps} overlaps)")
        for e in entries:
            print(print_entry(e))

    print(f"\n{'='*70}")
    if all_pass:
        print("ALL STRATEGIES PASSED — no gaps or overlaps")
    else:
        print("SOME STRATEGIES HAVE GAPS/OVERLAPS (expected for 'skip')")
    print(f"{'='*70}")
    return all_pass


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
