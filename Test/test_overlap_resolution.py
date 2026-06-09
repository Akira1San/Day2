#!/usr/bin/env python3
"""
Test the overlap resolution combobox strategies (fragment/skip/gap-fill/compact).

Reproduces the bug scenario: custom tag (Custom test.ini: 09:00-23:19)
+ random fill (Movies 3.ini: 00:00-23:59, fill_24h) in approximate find-replace mode.

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
from serialization import load_single_tag_from_ini


def make_video(name: str, dur_min: int) -> dict:
    return {"path": f"/p/{name}.mp4", "duration": dur_min * 60}


def load_tags_from_ini(ini_path: str) -> Tag:
    """Load a tag from an .ini file using the serialization loader."""
    return load_single_tag_from_ini(ini_path, Tag, QTime.fromString)


def build_tag_manager(use_real_files: bool = False) -> TagManager:
    tg = TagManager()

    if use_real_files:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        rf = load_tags_from_ini(os.path.join(base, "Tags", "Movies 3.ini"))
        ct = load_tags_from_ini(os.path.join(base, "Tags", "Custom test.ini"))
        rf.is_random_fill = True
        rf.fill_24h = True
        ct.randomize_videos = True
        from utils import load_collection_videos_only
        rf.collection_videos = load_collection_videos_only(rf.collection_path) or []
        ct.collection_videos = load_collection_videos_only(ct.collection_path) or []
        print(f"  Loaded '{rf.name}': {len(rf.collection_videos)} videos"
              f"  Loaded '{ct.name}': {len(ct.collection_videos)} videos")
        tg.add_tag(rf)
        tg.add_tag(ct)
    else:
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
    """Check for gaps and overlaps between consecutive entries.

    Correctly handles entries that cross midnight by clipping their
    effective start to day_start.
    """
    day_entries = [e for e in entries if e.start_seconds < day_end and e.end_seconds > day_start]
    day_entries.sort(key=lambda e: e.start_seconds)

    gaps = 0
    overlaps = 0
    prev_end = day_start
    for e in day_entries:
        effective_start = max(e.start_seconds, day_start)
        effective_end = min(e.end_seconds, day_end)
        if effective_start > prev_end + 1:
            gaps += 1
        if effective_start < prev_end - 1:
            overlaps += 1
        prev_end = max(prev_end, effective_end)

    return gaps, overlaps


def test_strategy(mode: str = "find_replace", overlap_strategy: str = "fragment", use_real_files: bool = False):
    tg = build_tag_manager(use_real_files)
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

    for label, use_real in [("Synthetic data", False), ("Real .ini files", True)]:
        print(f"\n{'='*70}")
        print(f"  {label}")
        print(f"{'='*70}")
        for mode in modes:
            print(f"\n--- Mode: {mode} ---")
            for strat in strategies:
                try:
                    entries, frags, total_sec, gaps, overlaps = test_strategy(mode, strat, use_real)
                except Exception as e:
                    print(f"  {strat:>10}: ERROR — {e}")
                    continue
                cov_h = total_sec // 3600
                cov_m = (total_sec % 3600) // 60
                print(f"  {strat:>10}: {len(entries):2d} entries, {frags:2d} fragments, "
                      f"{cov_h:2d}h{cov_m:02d}m coverage, {gaps} gaps, {overlaps} overlaps")

    # Detailed output for find_replace with real files
    print(f"\n{'='*70}")
    print("Detailed — find_replace with Real .ini files")
    print(f"{'='*70}")
    for strat in strategies:
        entries, frags, total_sec, gaps, overlaps = test_strategy("find_replace", strat, True)
        cov_h = total_sec // 3600
        cov_m = (total_sec % 3600) // 60
        print(f"\n{strat.upper()} ({len(entries)} entries, {frags} frags, "
              f"{cov_h}h{cov_m}m, {gaps} gaps, {overlaps} overlaps)")
        for e in entries:
            print(print_entry(e))

    # Validation: fragment must have full coverage, compact must have no gaps
    print(f"\n{'='*70}")
    print("VALIDATION")
    print(f"{'='*70}")
    all_ok = True
    for use_real in [False, True]:
        label = "real files" if use_real else "synthetic"
        for strat in strategies:
            mode = "find_replace"
            entries, frags, total_sec, gaps, overlaps = test_strategy(mode, strat, use_real)
            if strat == "fragment":
                if gaps > 0 or overlaps > 0:
                    print(f"  FAIL [{label}] fragment: has {gaps} gaps, {overlaps} overlaps")
                    all_ok = False
            elif strat == "compact":
                if gaps > 0 or overlaps > 0:
                    print(f"  FAIL [{label}] compact: has {gaps} gaps, {overlaps} overlaps")
                    all_ok = False
            else:
                # skip: gaps are expected
                pass
        if use_real:
            print(f"  OK [{label}] all strategies ran without errors")
        else:
            print(f"  OK [{label}] all strategies ran without errors")

    print(f"\n{'='*70}")
    if all_ok:
        print("ALL CHECKS PASSED")
    else:
        print("SOME CHECKS FAILED — see above")
    print(f"{'='*70}")
    return all_ok


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
