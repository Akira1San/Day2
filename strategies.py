#!/usr/bin/env python3
"""Approximate scheduling strategies for the daypart scheduler.

This module contains all strategy classes that implement different algorithms
for integrating custom/series/multi-series tags with random fill.
"""

from __future__ import annotations
import random
import itertools
import logging
from typing import List
from PySide6.QtCore import QTime

from utils import (
    qtime_to_seconds,
    get_video_display_name,
    parse_videos_for_series,
    normalize_tag_time_range,
)
from data_models import ScheduleEntry

logger = logging.getLogger(__name__)


class CustomTagMergeStrategy:
    """Strategy for merging custom/series tags into random fill."""

    def __init__(self, schedule_generator: 'ScheduleGenerator'):
        self.sg = schedule_generator

    def generate(self, num_days: int = 1) -> List[ScheduleEntry]:
        """Build a schedule combining custom tags, series tags, multi-series tags, and random fill."""
        all_tags = self.sg.tag_manager.get_all_tags()

        custom_tags = [t for t in all_tags if t.tag_type == "custom" and not t.is_random_fill and not t.is_series]
        series_tags = [t for t in all_tags if t.is_series]
        multi_series_tags = [t for t in all_tags if getattr(t, 'is_multi_series', False)]
        random_fill_tags = [t for t in all_tags if t.is_random_fill]

        if not custom_tags and not series_tags and not multi_series_tags and not random_fill_tags:
            entries = self.sg.generate_random_fill(24 * 3600 * num_days)
            return entries

        # Fast-path: when only a fill_24h random fill tag is present (and no
        # custom / series / multi-series tags), build one continuous stream from
        # 0 to num_days*24*3600. This matches the Approximate modes and avoids
        # the per-day branch below, which would otherwise reset each day to
        # 00:00 and leave gaps at the end of every day.
        rf_24h_tags = [rf for rf in random_fill_tags if getattr(rf, 'fill_24h', False)]
        has_marathon = any(getattr(rf, 'marathon_mode', False) for rf in rf_24h_tags)
        if rf_24h_tags and not custom_tags and not series_tags and not multi_series_tags and not has_marathon:
            return self.sg.generate_random_fill(24 * 3600 * num_days)

        occupied = set()
        custom_entries = []
        series_entries = []
        multi_series_entries = []
        fill_entries = []

        for day_offset in range(num_days):
            day_offset_seconds = day_offset * 24 * 3600
            for ct in custom_tags:
                if not self.sg._is_tag_active_on_day(ct, day_offset):
                    continue
                self.sg._process_custom_tag(ct, custom_entries, occupied, day_offset_seconds)

            for st in series_tags:
                if not self.sg._is_tag_active_on_day(st, day_offset):
                    continue
                self.sg._process_series_tag(st, series_entries, occupied, day_offset, day_offset_seconds)

            for mst in multi_series_tags:
                if not self.sg._is_tag_active_on_day(mst, day_offset):
                    continue
                self.sg._process_multi_series_tag(mst, multi_series_entries, occupied, day_offset, day_offset_seconds)

        rf_sorted = sorted(random_fill_tags, key=lambda t: qtime_to_seconds(t.start_time))

        if rf_sorted and any(getattr(rf, 'fill_24h', False) for rf in rf_sorted):
            for day_offset in range(num_days):
                day_offset_seconds = day_offset * 24 * 3600
                for rf in rf_sorted:
                    if getattr(rf, 'fill_24h', False):
                        day_start = day_offset_seconds
                        day_end = day_offset_seconds + 24 * 3600
                        merged = [(e.start_seconds - day_offset_seconds, e.end_seconds - day_offset_seconds)
                                   for e in custom_entries + series_entries + multi_series_entries
                                   if e.start_seconds < day_end and e.end_seconds > day_start]
                        self.sg._process_random_fill_tag(rf, fill_entries, merged, 0, day_offset_seconds)
        elif rf_sorted:
            rf_first = rf_sorted[0]
            if getattr(rf_first, 'marathon_mode', False):
                rf_videos = self.sg._get_marathon_videos(rf_first, 0)
            else:
                rf_videos = rf_first.collection_videos.copy() if rf_first.collection_videos else []
            rf_start = qtime_to_seconds(rf_first.start_time)
            if rf_videos:
                random.shuffle(rf_videos)
            total_seconds = num_days * 24 * 3600
            fill_entries.extend(self.sg._build_random_entries(rf_videos, rf_start, total_seconds, rf_first.name))

        rf_24h_tags = [rf for rf in rf_sorted if getattr(rf, 'fill_24h', False)]
        if fill_entries and rf_24h_tags:
            fill_entries.sort(key=lambda e: e.start_seconds)
            total_duration = sum(e.end_seconds - e.start_seconds for e in fill_entries)
            rf_videos = rf_sorted[0].collection_videos.copy() if rf_sorted else []
            if rf_videos:
                total_secs = sum(int(v.get('duration', 90)) for v in rf_videos)
                avg_duration = total_secs // len(rf_videos) if rf_videos else 0
                if avg_duration > 0:
                    start_vid_idx = (total_duration // avg_duration) % len(rf_videos)
                    for day_offset in range(1, num_days):
                        day_offset_seconds = day_offset * 24 * 3600
                        for rf in rf_sorted[1:]:
                            day_start = day_offset_seconds
                            day_end = day_offset_seconds + 24 * 3600
                            merged = [(e.start_seconds - day_offset_seconds, e.end_seconds - day_offset_seconds)
                                       for e in custom_entries + series_entries + multi_series_entries
                                       if e.start_seconds < day_end and e.end_seconds > day_start]
                            self.sg._process_random_fill_tag(rf, fill_entries, merged, start_vid_idx, day_offset_seconds)

        entries = custom_entries + series_entries + multi_series_entries + fill_entries
        entries.sort(key=lambda e: e.start_seconds)
        return entries

    def inject_into_random(self, random_entries: List[ScheduleEntry]) -> List[ScheduleEntry]:
        """Inject custom tags into existing random entries."""
        custom_tags = self.sg.tag_manager.get_custom_tags()
        if not custom_tags:
            return list(random_entries)

        final = []
        rand_idx = 0
        custom_sorted = sorted(custom_tags, key=lambda t: qtime_to_seconds(t.start_time))

        for ct in custom_sorted:
            start, end = normalize_tag_time_range(ct)
            if start >= end or start >= 24 * 3600:
                continue

            while rand_idx < len(random_entries) and random_entries[rand_idx].end_seconds <= start:
                final.append(random_entries[rand_idx])
                rand_idx += 1

            if rand_idx < len(random_entries) and random_entries[rand_idx].start_seconds < start:
                final.append(random_entries[rand_idx])
                rand_idx += 1

            if ct.collection_videos and getattr(ct, 'randomize_videos', False):
                video_count = getattr(ct, 'video_count', 1)
                videos = ct.collection_videos.copy()
                random.shuffle(videos)
                pos = start
                vid_idx = 0
                while pos < end and vid_idx < video_count and vid_idx < len(videos):
                    video = videos[vid_idx % len(videos)]
                    video_name = get_video_display_name(video)
                    duration = int(video.get('duration', 90))
                    if duration < 1:
                        duration = 90
                    if pos + duration > end:
                        vid_idx += 1
                        continue
                    final.append(ScheduleEntry(1, pos, pos + duration, video_name, "custom"))
                    pos += duration
                    vid_idx += 1
            else:
                final.append(ScheduleEntry(1, start, end, ct.name, "custom"))

            while rand_idx < len(random_entries) and random_entries[rand_idx].start_seconds < end:
                rand_idx += 1

        while rand_idx < len(random_entries):
            final.append(random_entries[rand_idx])
            rand_idx += 1

        final.sort(key=lambda e: e.start_seconds)
        return final


class FindReplaceApproximateStrategy:
    """Strategy for find-replace approximate scheduling: moves custom tags to fit random fill boundaries."""

    def __init__(self, schedule_generator: 'ScheduleGenerator'):
        self.sg = schedule_generator

    def generate(self, num_days: int = 1) -> List[ScheduleEntry]:
        all_tags = self.sg.tag_manager.get_all_tags()

        custom_tags = [t for t in all_tags if t.tag_type == "custom" and not t.is_random_fill and not t.is_series]
        series_tags = [t for t in all_tags if t.is_series]
        multi_series_tags = [t for t in all_tags if getattr(t, 'is_multi_series', False)]
        random_fill_tags = [t for t in all_tags if t.is_random_fill]

        rf_24h_tags = [t for t in random_fill_tags if getattr(t, 'fill_24h', False)]

        if rf_24h_tags and not custom_tags and not series_tags and not multi_series_tags:
            if not any(getattr(rf, 'marathon_mode', False) for rf in rf_24h_tags):
                return self.sg.generate_random_fill(24 * 3600 * num_days)

        has_24h_fill = bool(rf_24h_tags)

        if not custom_tags and not series_tags and not multi_series_tags and not random_fill_tags:
            return []

        return self.sg._apply_approximate_find_replace(num_days, custom_tags, series_tags, multi_series_tags, random_fill_tags, has_24h_fill)


class LinearApproximateStrategy:
    """Strategy for linear approximate scheduling: truncates random fill to make room for custom tags."""

    def __init__(self, schedule_generator: 'ScheduleGenerator'):
        self.sg = schedule_generator

    def generate(self, num_days: int = 1) -> List[ScheduleEntry]:
        all_tags = self.sg.tag_manager.get_all_tags()

        custom_tags = [t for t in all_tags if t.tag_type == "custom" and not t.is_random_fill and not t.is_series]
        series_tags = [t for t in all_tags if t.is_series]
        multi_series_tags = [t for t in all_tags if getattr(t, 'is_multi_series', False)]
        random_fill_tags = [t for t in all_tags if t.is_random_fill]

        rf_24h_tags = [t for t in random_fill_tags if getattr(t, 'fill_24h', False)]

        if rf_24h_tags and not custom_tags and not series_tags and not multi_series_tags:
            if not any(getattr(rf, 'marathon_mode', False) for rf in rf_24h_tags):
                return self.sg.generate_random_fill(24 * 3600 * num_days)

        has_24h_fill = bool(rf_24h_tags)

        if has_24h_fill:
            base_entries = []
        else:
            base_entries = self.sg.generate_random_fill(24 * 3600) if (custom_tags or series_tags or multi_series_tags) else []

        if not custom_tags and not series_tags and not multi_series_tags and not random_fill_tags:
            return base_entries

        return self.sg._apply_approximate_linear(num_days, custom_tags, series_tags, multi_series_tags, random_fill_tags, has_24h_fill)


class EarlyFillApproximateStrategy:
    """Strategy for early-fill approximate scheduling: places tags as early as possible."""

    def __init__(self, schedule_generator: 'ScheduleGenerator'):
        self.sg = schedule_generator

    def generate(self, num_days: int = 1) -> List[ScheduleEntry]:
        all_tags = self.sg.tag_manager.get_all_tags()
        custom_tags = [t for t in all_tags if t.tag_type == "custom" and not t.is_random_fill and not t.is_series]
        series_tags = [t for t in all_tags if t.is_series]
        multi_series_tags = [t for t in all_tags if getattr(t, 'is_multi_series', False)]
        random_fill_tags = [t for t in all_tags if t.is_random_fill]

        rf_24h_tags = [t for t in random_fill_tags if getattr(t, 'fill_24h', False)]
        if rf_24h_tags and not custom_tags and not series_tags and not multi_series_tags:
            if not any(getattr(rf, 'marathon_mode', False) for rf in rf_24h_tags):
                return self.sg.generate_random_fill(24 * 3600 * num_days)

        if not custom_tags and not series_tags and not multi_series_tags and not random_fill_tags:
            return []

        rf_sorted = sorted(random_fill_tags, key=lambda t: qtime_to_seconds(t.start_time))
        if not rf_sorted:
            return LinearApproximateStrategy(self.sg).generate(num_days)

        rf = rf_sorted[0]
        if getattr(rf, 'marathon_mode', False):
            rf_videos = self.sg._get_marathon_videos(rf, 0)
        else:
            rf_videos = rf.collection_videos.copy() if rf.collection_videos else []
        if rf_videos:
            random.shuffle(rf_videos)
        total_seconds = num_days * 24 * 3600
        random_entries = self.sg._build_random_entries(rf_videos, 0, total_seconds, rf.name)

        used_random = set()
        final = []

        for day_offset in range(num_days):
            day_start = day_offset * 86400
            day_end = day_start + 86400

            day_unused = [e for i, e in enumerate(random_entries)
                          if i not in used_random and e.start_seconds < day_end and e.end_seconds > day_start]
            day_unused.sort(key=lambda e: e.start_seconds)

            day_tags = []
            for tag_list in (custom_tags, series_tags, multi_series_tags):
                for t in tag_list:
                    if not self.sg._is_tag_active_on_day(t, day_offset):
                        continue
                    orig_start, orig_end = normalize_tag_time_range(t)
                    abs_start = orig_start + day_start
                    abs_end = orig_end + day_start
                    duration = orig_end - orig_start
                    if duration <= 0:
                        continue
                    day_tags.append((t, abs_start, abs_end, duration))

            day_tags.sort(key=lambda x: x[1])

            current_pos = day_start
            scheduled_slots = []

            for tag, abs_start, abs_end, duration in day_tags:
                slot_start = max(abs_start, current_pos)
                slot_end = slot_start + duration
                if slot_start >= day_end:
                    continue
                if slot_end > day_end:
                    slot_end = day_end
                actual_end = self.sg._place_tag_videos(tag, slot_start, slot_end, final, day_offset)
                current_pos = actual_end
                scheduled_slots.append((slot_start, actual_end))
                current_pos = self.sg._consume_overlapping_tail(
                    slot_start, slot_end, current_pos, day_unused, random_entries, used_random, final, day_offset,
                    min_end_threshold=slot_start,
                    scheduled_slots=scheduled_slots,
                )

            current_pos = self.sg._approximate_finalize_day(
                random_entries, used_random, final, day_offset, day_start, scheduled_slots, current_pos
            )

        final.sort(key=lambda e: e.start_seconds)
        return final


class LateFillApproximateStrategy:
    """Strategy for late-fill approximate scheduling: places tags as late as possible."""

    def __init__(self, schedule_generator: 'ScheduleGenerator'):
        self.sg = schedule_generator

    def generate(self, num_days: int = 1) -> List[ScheduleEntry]:
        all_tags = self.sg.tag_manager.get_all_tags()
        custom_tags = [t for t in all_tags if t.tag_type == "custom" and not t.is_random_fill and not t.is_series]
        series_tags = [t for t in all_tags if t.is_series]
        multi_series_tags = [t for t in all_tags if getattr(t, 'is_multi_series', False)]
        random_fill_tags = [t for t in all_tags if t.is_random_fill]

        rf_24h_tags = [t for t in random_fill_tags if getattr(t, 'fill_24h', False)]
        if rf_24h_tags and not custom_tags and not series_tags and not multi_series_tags:
            if not any(getattr(rf, 'marathon_mode', False) for rf in rf_24h_tags):
                return self.sg.generate_random_fill(24 * 3600 * num_days)

        if not custom_tags and not series_tags and not multi_series_tags and not random_fill_tags:
            return []

        rf_sorted = sorted(random_fill_tags, key=lambda t: qtime_to_seconds(t.start_time))
        if not rf_sorted:
            return LinearApproximateStrategy(self.sg).generate(num_days)

        rf = rf_sorted[0]
        if getattr(rf, 'marathon_mode', False):
            rf_videos = self.sg._get_marathon_videos(rf, 0)
        else:
            rf_videos = rf.collection_videos.copy() if rf.collection_videos else []
        if rf_videos:
            random.shuffle(rf_videos)
        total_seconds = num_days * 24 * 3600
        random_entries = self.sg._build_random_entries(rf_videos, 0, total_seconds, rf.name)

        used_random = set()
        final = []

        for day_offset in range(num_days):
            day_start = day_offset * 86400
            day_end = day_start + 86400

            day_unused = [e for i, e in enumerate(random_entries)
                          if i not in used_random and e.start_seconds < day_end and e.end_seconds > day_start]
            day_unused.sort(key=lambda e: e.start_seconds)

            day_tags = []
            for tag_list in (custom_tags, series_tags, multi_series_tags):
                for t in tag_list:
                    if not self.sg._is_tag_active_on_day(t, day_offset):
                        continue
                    orig_start, orig_end = normalize_tag_time_range(t)
                    abs_start = orig_start + day_start
                    abs_end = orig_end + day_start
                    duration = orig_end - orig_start
                    if duration <= 0:
                        continue
                    day_tags.append((t, abs_start, abs_end, duration))

            # Compute slots by reverse order on end times
            day_tags_by_end = sorted(day_tags, key=lambda x: x[2], reverse=True)
            temp_slots = []
            latest_free = day_end
            for tag, abs_start, abs_end, duration in day_tags_by_end:
                slot_end = min(abs_end, latest_free)
                slot_start = slot_end - duration
                if slot_start < day_start:
                    if latest_free <= day_start:
                        continue
                    slot_start = day_start
                    slot_end = latest_free
                temp_slots.append((tag, slot_start, slot_end))
                latest_free = slot_start

            scheduled_slots_info = sorted(temp_slots, key=lambda x: x[1])
            current_pos = day_start
            scheduled_slots = []

            for tag, slot_start, slot_end in scheduled_slots_info:
                if slot_start >= day_end:
                    continue
                actual_end = self.sg._place_tag_videos(tag, slot_start, slot_end, final, day_offset)
                current_pos = actual_end
                scheduled_slots.append((slot_start, actual_end))
                current_pos = self.sg._consume_overlapping_tail(
                    slot_start, slot_end, current_pos, day_unused, random_entries, used_random, final, day_offset,
                    min_end_threshold=slot_start,
                    scheduled_slots=scheduled_slots,
                )

            current_pos = self.sg._approximate_finalize_day(
                random_entries, used_random, final, day_offset, day_start, scheduled_slots, current_pos
            )

        final.sort(key=lambda e: e.start_seconds)
        return final


class PriorityApproximateStrategy:
    """Strategy for priority-based approximate scheduling: higher priority tags placed first."""

    def __init__(self, schedule_generator: 'ScheduleGenerator'):
        self.sg = schedule_generator

    def generate(self, num_days: int = 1) -> List[ScheduleEntry]:
        all_tags = self.sg.tag_manager.get_all_tags()
        custom_tags = [t for t in all_tags if t.tag_type == "custom" and not t.is_random_fill and not t.is_series]
        series_tags = [t for t in all_tags if t.is_series]
        multi_series_tags = [t for t in all_tags if getattr(t, 'is_multi_series', False)]
        random_fill_tags = [t for t in all_tags if t.is_random_fill]

        rf_24h_tags = [t for t in random_fill_tags if getattr(t, 'fill_24h', False)]
        if rf_24h_tags and not custom_tags and not series_tags and not multi_series_tags:
            if not any(getattr(rf, 'marathon_mode', False) for rf in rf_24h_tags):
                return self.sg.generate_random_fill(24 * 3600 * num_days)

        if not custom_tags and not series_tags and not multi_series_tags and not random_fill_tags:
            return []

        rf_sorted = sorted(random_fill_tags, key=lambda t: qtime_to_seconds(t.start_time))
        if not rf_sorted:
            return LinearApproximateStrategy(self.sg).generate(num_days)

        rf = rf_sorted[0]
        if getattr(rf, 'marathon_mode', False):
            rf_videos = self.sg._get_marathon_videos(rf, 0)
        else:
            rf_videos = rf.collection_videos.copy() if rf.collection_videos else []
        if rf_videos:
            random.shuffle(rf_videos)
        total_seconds = num_days * 24 * 3600
        random_entries = self.sg._build_random_entries(rf_videos, 0, total_seconds, rf.name)

        used_random = set()
        final = []

        for day_offset in range(num_days):
            day_start = day_offset * 86400
            day_end = day_start + 86400

            day_unused = [e for i, e in enumerate(random_entries)
                          if i not in used_random and e.start_seconds < day_end and e.end_seconds > day_start]
            day_unused.sort(key=lambda e: e.start_seconds)

            day_tags = []
            for tag_list in (custom_tags, series_tags, multi_series_tags):
                for t in tag_list:
                    if not self.sg._is_tag_active_on_day(t, day_offset):
                        continue
                    orig_start, orig_end = normalize_tag_time_range(t)
                    abs_start = orig_start + day_start
                    abs_end = orig_end + day_start
                    duration = orig_end - orig_start
                    if duration <= 0:
                        continue
                    day_tags.append((t, abs_start, abs_end, duration))

            # Sort by priority descending, then by absolute start
            day_tags.sort(key=lambda x: (-getattr(x[0], 'priority', 0), x[1]))

            current_pos = day_start
            scheduled_slots = []

            for tag, abs_start, abs_end, duration in day_tags:
                THRESHOLD_AFTER = 30 * 60  # 1800 seconds
                before_candidates = [e for e in day_unused if e.end_seconds <= abs_start and e.end_seconds >= current_pos]
                close_after = [e for e in day_unused if e.start_seconds >= abs_start and e.end_seconds < abs_start + THRESHOLD_AFTER]

                best_before = max(before_candidates, key=lambda e: e.end_seconds) if before_candidates else None
                anchor_candidates = ([best_before] if best_before else []) + close_after

                if anchor_candidates:
                    best_gap = float('inf')
                    best_rand = None
                    best_idx = -1
                    for rand_e in anchor_candidates:
                        gap = abs(rand_e.end_seconds - abs_start)
                        if gap < best_gap:
                            best_gap = gap
                            best_rand = rand_e
                            for idx, re in enumerate(random_entries):
                                if re is rand_e and idx not in used_random:
                                    best_idx = idx
                                    break
                    if best_rand and best_idx >= 0:
                        logger.debug(f"[APPROX day={day_offset+1}]   BEST end={best_rand.end_seconds//3600%24:02d}:{(best_rand.end_seconds%3600)//60:02d}:{best_rand.end_seconds%60:02d} gap={best_gap} -> tag at {best_rand.end_seconds//3600%24:02d}:{(best_rand.end_seconds%3600)//60:02d}:{best_rand.end_seconds%60:02d}")
                        overlap_strategy = getattr(self.sg, '_overlap_strategy', 'fragment')
                        if current_pos <= best_rand.start_seconds:
                            final.append(best_rand)
                            used_random.add(best_idx)
                            if best_rand in day_unused:
                                day_unused.remove(best_rand)
                            current_pos = best_rand.end_seconds
                        elif current_pos < best_rand.end_seconds:
                            if overlap_strategy == 'fragment':
                                final.append(ScheduleEntry(1, current_pos, best_rand.end_seconds, best_rand.video_name, "random_fill"))
                            used_random.add(best_idx)
                            if best_rand in day_unused:
                                day_unused.remove(best_rand)
                            if overlap_strategy == 'fragment':
                                current_pos = best_rand.end_seconds
                        else:
                            used_random.add(best_idx)
                            if best_rand in day_unused:
                                day_unused.remove(best_rand)

                        slot_start = best_rand.end_seconds
                        slot_end = slot_start + duration
                actual_end = self.sg._place_tag_videos(tag, slot_start, slot_end, final, day_offset)
                current_pos = actual_end
                scheduled_slots.append((slot_start, actual_end))
                current_pos = self.sg._consume_overlapping_tail(
                    slot_start, slot_end, current_pos, day_unused, random_entries, used_random, final, day_offset,
                    min_end_threshold=slot_start,
                    scheduled_slots=scheduled_slots,
                )
                continue

            # Fallback placement
            for tag, abs_start, abs_end, duration in day_tags:
                if abs_start < current_pos:
                    abs_start = current_pos
                    abs_end = abs_start + duration
                slot_start = abs_start
                slot_end = abs_start + duration
                actual_end = self.sg._place_tag_videos(tag, slot_start, slot_end, final, day_offset)
                current_pos = actual_end
                scheduled_slots.append((slot_start, actual_end))
                current_pos = self.sg._consume_overlapping_tail(
                    slot_start, slot_end, current_pos, day_unused, random_entries, used_random, final, day_offset,
                    min_end_threshold=slot_start,
                    scheduled_slots=scheduled_slots,
                    label="fallback",
                )

            current_pos = self.sg._approximate_finalize_day(
                random_entries, used_random, final, day_offset, day_start, scheduled_slots, current_pos
            )

        final.sort(key=lambda e: e.start_seconds)
        return final


class BestFitApproximateStrategy:
    """Strategy for best-fit approximate scheduling: uses same behavior as find-replace."""

    def __init__(self, schedule_generator: 'ScheduleGenerator'):
        self.sg = schedule_generator

    def generate(self, num_days: int = 1) -> List[ScheduleEntry]:
        return FindReplaceApproximateStrategy(self.sg).generate(num_days)


class RoundRobinApproximateStrategy:
    """Strategy for round-robin approximate scheduling: interleaves tags and random fill exactly at preferred times."""

    def __init__(self, schedule_generator: 'ScheduleGenerator'):
        self.sg = schedule_generator

    def generate(self, num_days: int = 1) -> List[ScheduleEntry]:
        return LinearSpanningApproximateStrategy(self.sg).generate(num_days)


class LinearSpanningApproximateStrategy:
    """Strategy for linear approximate scheduling with day-spanning enabled."""

    def __init__(self, schedule_generator: 'ScheduleGenerator'):
        self.sg = schedule_generator

    def generate(self, num_days: int = 1) -> List[ScheduleEntry]:
        all_tags = self.sg.tag_manager.get_all_tags()
        custom_tags = [t for t in all_tags if t.tag_type == "custom" and not t.is_random_fill and not t.is_series]
        series_tags = [t for t in all_tags if t.is_series]
        multi_series_tags = [t for t in all_tags if getattr(t, 'is_multi_series', False)]
        random_fill_tags = [t for t in all_tags if t.is_random_fill]

        rf_24h_tags = [t for t in random_fill_tags if getattr(t, 'fill_24h', False)]
        if rf_24h_tags and not custom_tags and not series_tags and not multi_series_tags:
            if not any(getattr(rf, 'marathon_mode', False) for rf in rf_24h_tags):
                return self.sg.generate_random_fill(24 * 3600 * num_days)

        if not custom_tags and not series_tags and not multi_series_tags and not random_fill_tags:
            return []

        rf_sorted = sorted(random_fill_tags, key=lambda t: qtime_to_seconds(t.start_time))
        if not rf_sorted:
            return LinearApproximateStrategy(self.sg).generate(num_days)

        rf = rf_sorted[0]
        if getattr(rf, 'marathon_mode', False):
            rf_videos = self.sg._get_marathon_videos(rf, 0)
        else:
            rf_videos = rf.collection_videos.copy() if rf.collection_videos else []
        if rf_videos:
            random.shuffle(rf_videos)
        total_seconds = num_days * 24 * 3600
        random_entries = self.sg._build_random_entries(rf_videos, 0, total_seconds, rf.name)

        used_random = set()
        final = []

        # Build all tag instances across days with group ordering: custom -> series -> multi
        custom_inst = []
        series_inst = []
        multi_inst = []
        for day_offset in range(num_days):
            day_start = day_offset * 86400
            for t in custom_tags:
                if not self.sg._is_tag_active_on_day(t, day_offset):
                    continue
                os, oe = normalize_tag_time_range(t)
                custom_inst.append((t, os + day_start, oe + day_start, oe - os))
            for t in series_tags:
                if not self.sg._is_tag_active_on_day(t, day_offset):
                    continue
                os, oe = normalize_tag_time_range(t)
                series_inst.append((t, os + day_start, oe + day_start, oe - os))
            for t in multi_series_tags:
                if not self.sg._is_tag_active_on_day(t, day_offset):
                    continue
                os, oe = normalize_tag_time_range(t)
                multi_inst.append((t, os + day_start, oe + day_start, oe - os))

        custom_inst.sort(key=lambda x: x[1])
        series_inst.sort(key=lambda x: x[1])
        multi_inst.sort(key=lambda x: x[1])
        all_instances = custom_inst + series_inst + multi_inst

        current_pos = 0
        scheduled_slots = []

        for tag, abs_start, abs_end, duration in all_instances:
            slot_start = max(abs_start, current_pos)
            slot_end = slot_start + duration
            day_offset = abs_start // 86400
            actual_end = self.sg._place_tag_videos(tag, slot_start, slot_end, final, day_offset)
            current_pos = actual_end
            scheduled_slots.append((slot_start, actual_end))
            day_offset_tail = abs_start // 86400
            day_unused = [e for i, e in enumerate(random_entries) if i not in used_random]
            current_pos = self.sg._consume_overlapping_tail(
                slot_start, slot_end, current_pos, day_unused, random_entries, used_random, final, day_offset_tail,
                min_end_threshold=slot_start,
                scheduled_slots=scheduled_slots,
                label="spanning"
            )

        for day_offset in range(num_days):
            day_start = day_offset * 86400
            current_pos = self.sg._approximate_finalize_day(
                random_entries, used_random, final, day_offset, day_start, scheduled_slots, current_pos
            )

        final.sort(key=lambda e: e.start_seconds)
        return final


class ExhaustiveApproximateStrategy:
    """Strategy that exhaustively searches all tag orderings for small instances to minimize displacement."""

    def __init__(self, schedule_generator: 'ScheduleGenerator'):
        self.sg = schedule_generator

    def generate(self, num_days: int = 1) -> List[ScheduleEntry]:
        all_tags = self.sg.tag_manager.get_all_tags()
        custom_tags = [t for t in all_tags if t.tag_type == "custom" and not t.is_random_fill and not t.is_series]
        series_tags = [t for t in all_tags if t.is_series]
        multi_series_tags = [t for t in all_tags if getattr(t, 'is_multi_series', False)]
        random_fill_tags = [t for t in all_tags if t.is_random_fill]

        if not custom_tags and not series_tags and not multi_series_tags:
            if random_fill_tags:
                return self.sg.generate_random_fill(24 * 3600 * num_days)
            return []

        max_tags = 4
        total_instances = (len(custom_tags) + len(series_tags) + len(multi_series_tags)) * num_days
        if total_instances > max_tags or num_days > 2:
            return LinearApproximateStrategy(self.sg).generate(num_days)

        instances = []
        for day_offset in range(num_days):
            day_start = day_offset * 86400
            for t in custom_tags:
                if not self.sg._is_tag_active_on_day(t, day_offset):
                    continue
                os, oe = normalize_tag_time_range(t)
                instances.append((t, os + day_start, oe + day_start, oe - os))
            for t in series_tags:
                if not self.sg._is_tag_active_on_day(t, day_offset):
                    continue
                os, oe = normalize_tag_time_range(t)
                instances.append((t, os + day_start, oe + day_start, oe - os))
            for t in multi_series_tags:
                if not self.sg._is_tag_active_on_day(t, day_offset):
                    continue
                os, oe = normalize_tag_time_range(t)
                instances.append((t, os + day_start, oe + day_start, oe - os))

        best_order = None
        best_disp = None
        total_seconds_abs = num_days * 24 * 3600
        for perm in itertools.permutations(instances):
            current_pos = 0
            total_disp = 0
            valid = True
            for tag, abs_start, abs_end, duration in perm:
                slot_start = max(abs_start, current_pos)
                slot_end = slot_start + duration
                if slot_end > total_seconds_abs:
                    valid = False
                    break
                total_disp += slot_start - abs_start
                current_pos = slot_end
            if valid:
                if best_disp is None or total_disp < best_disp:
                    best_disp = total_disp
                    best_order = perm

        if best_order is None:
            return LinearApproximateStrategy(self.sg).generate(num_days)

        rf_sorted = sorted(random_fill_tags, key=lambda t: qtime_to_seconds(t.start_time))
        if not rf_sorted:
            return LinearApproximateStrategy(self.sg).generate(num_days)
        rf = rf_sorted[0]
        if getattr(rf, 'marathon_mode', False):
            rf_videos = self.sg._get_marathon_videos(rf, 0)
        else:
            rf_videos = rf.collection_videos.copy() if rf.collection_videos else []
        if rf_videos:
            random.shuffle(rf_videos)
        total_seconds = num_days * 24 * 3600
        random_entries = self.sg._build_random_entries(rf_videos, 0, total_seconds, rf.name)

        used_random = set()
        final = []
        scheduled_slots = []

        current_pos = 0

        for tag, abs_start, abs_end, duration in best_order:
            slot_start = max(abs_start, current_pos)
            slot_end = slot_start + duration
            day_offset = abs_start // 86400
            actual_end = self.sg._place_tag_videos(tag, slot_start, slot_end, final, day_offset)
            current_pos = actual_end
            scheduled_slots.append((slot_start, actual_end))
            day_offset_tail = abs_start // 86400
            day_unused = [e for i, e in enumerate(random_entries) if i not in used_random]
            current_pos = self.sg._consume_overlapping_tail(
                slot_start, slot_end, current_pos, day_unused, random_entries, used_random, final, day_offset,
                min_end_threshold=slot_start,
                scheduled_slots=scheduled_slots,
            )

        for day_offset in range(num_days):
            day_start = day_offset * 86400
            current_pos = self.sg._approximate_finalize_day(
                random_entries, used_random, final, day_offset, day_start, scheduled_slots, current_pos
            )

        final.sort(key=lambda e: e.start_seconds)
        return final
