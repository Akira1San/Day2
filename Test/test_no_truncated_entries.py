#!/usr/bin/env python3
"""
Verify that approximate find-replace mode does NOT create truncated entries — 
every video's scheduled duration must match its collection duration.
"""
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
random.seed(42)

from PySide6.QtCore import QTime
from models import ScheduleGenerator, TagManager, Tag

def make_video(name, dur_min):
    return {"path": f"/p/{name}.mp4", "duration": dur_min * 60}

def test_no_truncated_entries():
    tg = TagManager()

    # Random fill tag — 24h fill, 6 videos (90 min each = 5400s)
    rf_tag = Tag(
        name="Random Fill", tag_type="random_fill",
        start_time=QTime(0, 0), end_time=QTime(23, 59),
        is_random_fill=True, fill_24h=True,
        collection_videos=[
            make_video("video_A", 90),
            make_video("video_B", 90),
            make_video("video_C", 90),
            make_video("video_D", 90),
            make_video("video_E", 90),
            make_video("video_F", 90),
        ])
    tg.add_tag(rf_tag)

    # Custom tag — placed in the middle of the day, overlapping random fill
    # Uses distinct video names so debug lookup never collides
    custom_tag = Tag(
        name="Custom Block", tag_type="custom",
        start_time=QTime(9, 0), end_time=QTime(12, 0),  # 3h slot
        collection_videos=[
            make_video("custom_one", 45),
            make_video("custom_two", 50),
            make_video("custom_three", 55),
        ])
    tg.add_tag(custom_tag)

    sg = ScheduleGenerator(tg)
    entries = sg.apply_approximate(num_days=1, mode="find_replace")

    # Build lookup of collection durations from ALL tags
    lookup = {}
    for tag in tg.tags:
        for v in (tag.collection_videos or []):
            name = v.get("path", "").split("/")[-1]
            lookup[name] = int(v["duration"])

    print(f"\n{'='*60}")
    print(f"Testing {len(entries)} schedule entries for duration mismatches")
    print(f"{'='*60}")

    mismatches = []
    for i, e in enumerate(entries):
        scheduled = e.end_seconds - e.start_seconds
        # Extract video name from entry (strip tag prefix)
        video_key = e.video_name
        if " - " in video_key:
            video_key = video_key.split(" - ", 1)[1]
        # Remove path prefix if present
        video_key = video_key.split("/")[-1]

        expected = lookup.get(video_key)
        if expected is None:
            print(f"  #{i+1}: {e.video_name} — UNKNOWN (not in lookup)")
            continue

        if scheduled != expected:
            mismatches.append((i, e, scheduled, expected))
            print(f"  #{i+1}: {e.video_name} — MISMATCH scheduled={scheduled}s expected={expected}s")
        else:
            print(f"  #{i+1}: {e.video_name} — OK ({scheduled}s)")

    if mismatches:
        print(f"\n*** FAILED: {len(mismatches)} mismatches found ***")
        for i, e, sched, exp in mismatches:
            start_h = (e.start_seconds // 3600) % 24
            start_m = (e.start_seconds % 3600) // 60
            end_h = (e.end_seconds // 3600) % 24
            end_m = (e.end_seconds % 3600) // 60
            print(f"  {start_h:02d}:{start_m:02d}-{end_h:02d}:{end_m:02d} {e.video_name}: {sched}s vs {exp}s")
        return False
    else:
        print(f"\n*** PASSED: All {len(entries)} entries have correct durations ***")
        return True


if __name__ == "__main__":
    success = test_no_truncated_entries()
    sys.exit(0 if success else 1)
