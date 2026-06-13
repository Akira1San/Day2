#!/usr/bin/env python3
"""Test all approximate modes with custom tag + random fill scenario (2 days)."""
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
random.seed(42)

from PySide6.QtCore import QTime
from models import ScheduleGenerator, TagManager, Tag
from data_models import FRAGMENT_TAG_TYPE

def make_video(name, dur_min):
    return {"path": f"/p/{name}.mp4", "duration": dur_min * 60}

MODES = [
    "find_replace", "linear", "early_fill", "late_fill",
    "priority", "best_fit", "round_robin", "linear_spanning", "exhaustive", "no_overlap",
]

def run_test(mode, num_days=2):
    tg = TagManager()
    rf_tag = Tag(
        name="Random Fill", tag_type="random_fill",
        start_time=QTime(0, 0), end_time=QTime(23, 59),
        is_random_fill=True, fill_24h=True,
        collection_videos=[
            make_video("video_A", 90), make_video("video_B", 90),
            make_video("video_C", 90), make_video("video_D", 90),
            make_video("video_E", 90), make_video("video_F", 90),
        ])
    tg.add_tag(rf_tag)
    custom_tag = Tag(
        name="Custom Block", tag_type="custom",
        start_time=QTime(9, 0), end_time=QTime(12, 0),
        collection_videos=[
            make_video("custom_one", 45), make_video("custom_two", 50),
            make_video("custom_three", 55),
        ])
    tg.add_tag(custom_tag)
    sg = ScheduleGenerator(tg)
    entries = sg.apply_approximate(num_days=num_days, mode=mode)

    errors = []
    fragments = 0
    for i, e in enumerate(entries):
        if e.tag_type == FRAGMENT_TAG_TYPE:
            fragments += 1
            continue
        expected_dur = e.end_seconds - e.start_seconds
        # Check for negative/zero duration
        if expected_dur <= 0:
            errors.append(f"  #{i+1}: {e.video_name} — zero/negative duration ({expected_dur}s)")
            continue
        # Check for time outside day range for day 1
        day = e.start_seconds // 86400
        if day >= num_days or day < 0:
            errors.append(f"  #{i+1}: {e.video_name} — out of range day={day+1} ({e.start_seconds}s)")
    return entries, errors, fragments

print(f"{'='*70}")
print(f"{'Mode':<20} {'Entries':>8} {'Errors':>8} {'Fragments':>10}")
print(f"{'='*70}")

results = {}
for mode in MODES:
    entries, errors, fragments = run_test(mode, num_days=2)
    results[mode] = (entries, errors, fragments)
    status = "OK" if not errors else "ISSUES"
    print(f"{mode:<20} {len(entries):>8} {len(errors):>8} {fragments:>10}  {status}")
    for err in errors[:5]:
        print(f"  {err}")
    if len(errors) > 5:
        print(f"  ... and {len(errors)-5} more errors")

print(f"\n{'='*70}")
print("Detailed round_robin output:")
print(f"{'='*70}")
entries, errors, fragments = results["round_robin"]
for i, e in enumerate(entries):
    day = (e.start_seconds // 86400) + 1
    start_h = (e.start_seconds // 3600) % 24
    start_m = (e.start_seconds % 3600) // 60
    end_h = (e.end_seconds // 3600) % 24
    end_m = (e.end_seconds % 3600) // 60
    expected_dur = e.end_seconds - e.start_seconds
    tag = " [FRAGMENT]" if e.tag_type == FRAGMENT_TAG_TYPE else ""
    if day > 2 or e.start_seconds < 0:
        print(f"  #{i+1}: Day {day} {start_h:02d}:{start_m:02d}-{end_h:02d}:{end_m:02d} {e.video_name} — OUT OF RANGE{tag}")
    elif expected_dur <= 0:
        print(f"  #{i+1}: Day {day} {start_h:02d}:{start_m:02d}-{end_h:02d}:{end_m:02d} {e.video_name} — ZERO DUR{tag}")
    else:
        print(f"  #{i+1}: Day {day} {start_h:02d}:{start_m:02d}-{end_h:02d}:{end_m:02d} {e.video_name}{tag}")
