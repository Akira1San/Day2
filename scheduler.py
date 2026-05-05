#!/usr/bin/env python3
"""ScheduleGenerator and core scheduling engine for the daypart scheduler.

This module contains the main ScheduleGenerator class with all placement helpers,
approximate-mode dispatcher, and private scheduling algorithms.
"""

from __future__ import annotations
import random
import logging
from typing import List
from PySide6.QtCore import QTime

from utils import (
    qtime_to_minutes,
    get_video_display_name,
    parse_videos_for_series,
)
from data_models import Tag, MultiSeriesTag, ScheduleEntry, TagManager
from strategies import (
    CustomTagMergeStrategy,
    FindReplaceApproximateStrategy,
    LinearApproximateStrategy,
    EarlyFillApproximateStrategy,
    LateFillApproximateStrategy,
    PriorityApproximateStrategy,
    BestFitApproximateStrategy,
    RoundRobinApproximateStrategy,
    LinearSpanningApproximateStrategy,
    ExhaustiveApproximateStrategy,
)

logger = logging.getLogger(__name__)


class ScheduleGenerator:
    def __init__(self, tag_manager: TagManager):
        self.tag_manager = tag_manager

    def _create_video_entry(self, pos: int, duration: int, name: str, tag_name: str = "") -> ScheduleEntry:
        video_name = f"{tag_name} - {name}" if tag_name else name
        return ScheduleEntry(1, pos, pos + duration, video_name)

    def _select_series_videos(self, tag_or_config, day_offset: int) -> List[dict]:
        """Select videos for a series tag (Tag object or config dict) for given day_offset.
        Returns list of dicts with keys 'video', 'season', 'episode', matching parse_videos_for_series output.
        Handles 'season_sequence' mode with season metadata, and falls back to regular sequence/random.
        """
        is_dict = isinstance(tag_or_config, dict)
        collection_videos = tag_or_config.get('collection_videos') if is_dict else getattr(tag_or_config, 'collection_videos', [])
        if not collection_videos:
            return []

        video_count = tag_or_config.get('video_count') if is_dict else getattr(tag_or_config, 'video_count', 1)
        play_mode = tag_or_config.get('play_mode') if is_dict else getattr(tag_or_config, 'play_mode', 'sequence')
        start_season = tag_or_config.get('start_season') if is_dict else getattr(tag_or_config, 'start_season', 1)
        start_episode = tag_or_config.get('start_episode') if is_dict else getattr(tag_or_config, 'start_episode', 1)

        has_season_tags = tag_or_config.get('_has_season_tags', False) if is_dict else getattr(tag_or_config, '_has_season_tags', False)

        if play_mode == 'season_sequence' and has_season_tags:
            # Get the flat ordered list of all season episodes
            flat = tag_or_config['_flat_ordered'] if is_dict else tag_or_config._flat_ordered

            # Find the starting index based on start_season and start_episode
            start_idx = 0
            found = False
            for i, v in enumerate(flat):
                s = v.get('_meta_season')
                e = v.get('_parsed_episode')
                if s is None:
                    continue
                if s > start_season or (s == start_season and e >= start_episode):
                    start_idx = i
                    found = True
                    break

            if not found:
                return []  # No episodes match start criteria

            # Compute global index for this day
            effective_idx = start_idx + day_offset * video_count
            if effective_idx >= len(flat):
                return []  # Beyond available episodes

            take = min(video_count, len(flat) - effective_idx)
            selected = flat[effective_idx : effective_idx + take]
            return [{'video': v, 'season': v.get('_meta_season'), 'episode': v.get('_parsed_episode')} for v in selected]
        else:
            # Regular sequence/random with wrap-around of start_episode
            raw_episode = start_episode + (day_offset * video_count)
            total_episodes = len(collection_videos)
            if total_episodes > 0:
                effective_episode = ((raw_episode - 1) % total_episodes) + 1
            else:
                effective_episode = raw_episode
            videos_to_use, _ = parse_videos_for_series(
                collection_videos,
                start_season,
                effective_episode,
                play_mode,
                video_count
            )
            return videos_to_use

    def _place_tag_videos(self, ct, start: int, end: int, final: List[ScheduleEntry], day_offset: int = 0) -> int:
        """Place custom/series/multi-series tag videos into final schedule. Returns new current_pos."""
        # Handle MultiSeriesTag
        if getattr(ct, 'is_multi_series', False):
            pos = start
            for series_config in ct.series_list:
                collection_videos = series_config.get('collection_videos', [])
                start_season = series_config.get('start_season', 1)
                start_episode = series_config.get('start_episode', 1)
                play_mode = series_config.get('play_mode', 'sequence')
                video_count = series_config.get('video_count', 1)
                series_name = series_config.get('name', 'Series')

                if not collection_videos:
                    if pos >= end:
                        break
                    final.append(self._create_video_entry(pos, 60, series_name, ct.name))
                    pos += 60
                    continue

                # Use unified video selection (season_sequence or regular)
                videos_to_use = self._select_series_videos(series_config, day_offset)

                for v in videos_to_use:
                    if pos >= end:
                        break
                    video = v['video']
                    video_name = get_video_display_name(video)
                    duration = int(video.get('duration', 90)) // 60
                    if duration < 1:
                        duration = 1
                    # Truncate if would exceed slot end
                    if pos + duration > end:
                        duration = end - pos
                        if duration < 1:
                            break
                    final.append(self._create_video_entry(pos, duration, video_name, series_name))
                    pos += duration
            return pos

        if ct.collection_videos:
            video_count = getattr(ct, 'video_count', 1)
            videos = ct.collection_videos.copy()

            # Series tag (single-series) with sequence mode: compute incrementing start_episode
            if getattr(ct, 'is_series', False):
                base_start_episode = getattr(ct, 'start_episode', 1)
                raw_episode = base_start_episode + (day_offset * video_count)
                total_episodes = len(videos)
                if total_episodes > 0:
                    start_episode = ((raw_episode - 1) % total_episodes) + 1
                else:
                    start_episode = raw_episode
                videos_to_use, _ = parse_videos_for_series(
                    videos,
                    getattr(ct, 'start_season', 1),
                    start_episode,
                    getattr(ct, 'play_mode', 'sequence'),
                    video_count
                )
                ordered_videos = [v['video'] for v in videos_to_use]
            else:
                random.shuffle(videos)
                ordered_videos = videos

            pos = start
            vid_idx = 0
            while pos < end and vid_idx < video_count and vid_idx < len(ordered_videos):
                video = ordered_videos[vid_idx]
                video_name = get_video_display_name(video)
                duration = int(video.get('duration', 90)) // 60
                if duration < 1:
                    duration = 1
                duration = min(duration, end - pos)
                if duration < 1:
                    break
                final.append(self._create_video_entry(pos, duration, video_name, ct.name))
                pos += duration
                vid_idx += 1
            return pos
        else:
            final.append(ScheduleEntry(1, start, end, ct.name))
            return end

    def _build_random_entries(self, videos: List[dict], start_pos: int, end_pos: int, tag_name: str = "") -> List[ScheduleEntry]:
        """Build schedule entries by cycling through videos from start_pos to end_pos."""
        entries = []
        pos = start_pos
        if not videos:
            placeholder = f"{tag_name} - No videos" if tag_name else "No videos"
            entries.append(ScheduleEntry(1, pos, pos + 60, placeholder))
            return entries
        videos = videos.copy()
        random.shuffle(videos)
        vid_idx = 0
        while pos < end_pos:
            video = videos[vid_idx % len(videos)]
            video_name = get_video_display_name(video)
            duration = int(video.get('duration', 90)) // 60
            if duration < 1:
                duration = 1
            name = f"{tag_name} - {video_name}" if tag_name else video_name
            entries.append(ScheduleEntry(1, pos, pos + duration, name))
            pos += duration
            vid_idx += 1
        return entries

    def _get_all_videos(self, tags: List[Tag]) -> List[dict]:
        videos = []
        for tag in tags:
            if tag.collection_videos:
                videos.extend(tag.collection_videos)
        return videos

    def generate_random_fill(self, remaining_minutes: int = 24 * 60) -> List[ScheduleEntry]:
        all_tags = self.tag_manager.get_all_tags()
        collection_videos = self._get_all_videos(all_tags)

        if not collection_videos:
            return []

        entries = []
        random.shuffle(collection_videos)
        video_index = 0
        current_minute = 0
        current_day = 1

        while current_minute < remaining_minutes:
            video = collection_videos[video_index % len(collection_videos)]
            video_name = get_video_display_name(video)
            duration = int(video.get('duration', 90)) // 60
            if duration < 1:
                duration = 90
            end_minute = min(current_minute + duration, remaining_minutes)

            entries.append(ScheduleEntry(current_day, current_minute, end_minute, video_name))
            current_minute = end_minute
            video_index += 1

        return entries

    def _process_custom_tag(self, ct: Tag, custom_entries: List[ScheduleEntry], occupied: set, start_offset: int = 0):
        start_min = qtime_to_minutes(ct.start_time)
        end_min = qtime_to_minutes(ct.end_time)

        start_min += start_offset
        end_min += start_offset

        if start_min >= end_min:
            return

        if ct.collection_videos:
            for m in range(start_min, end_min):
                occupied.add(m)
            video_count = getattr(ct, 'video_count', 1)
            videos = ct.collection_videos.copy()
            random.shuffle(videos)
            pos = start_min
            vid_idx = 0
            while pos < end_min and vid_idx < video_count and vid_idx < len(videos):
                video = videos[vid_idx % len(videos)]
                video_name = get_video_display_name(video)
                duration = int(video.get('duration', 90)) // 60
                if duration < 1:
                    duration = 1
                duration = min(duration, end_min - pos)
                if duration < 1:
                    break
                custom_entries.append(self._create_video_entry(pos, duration, video_name, ct.name))
                pos += duration
                vid_idx += 1
        else:
            custom_entries.append(ScheduleEntry(1, start_min, end_min, ct.name))
            for m in range(start_min, end_min):
                occupied.add(m)

    def _process_series_tag(self, st: Tag, series_entries: List[ScheduleEntry], occupied: set, day_offset: int = 0, start_offset: int = 0):
        start_min = qtime_to_minutes(st.start_time)
        end_min = qtime_to_minutes(st.end_time)

        start_min += start_offset
        end_min += start_offset

        if start_min >= end_min:
            return

        if st.collection_videos:
            for m in range(start_min, end_min):
                occupied.add(m)

            videos_to_use = self._select_series_videos(st, day_offset)

            pos = start_min
            for v in videos_to_use:
                if pos >= end_min:
                    break
                video = v['video']
                video_name = get_video_display_name(video)
                duration = int(video.get('duration', 90)) // 60
                if duration < 1:
                    duration = 1
                duration = min(duration, end_min - pos)
                if duration < 1:
                    break
                series_entries.append(self._create_video_entry(pos, duration, video_name, st.name))
                pos += duration
        else:
            series_entries.append(ScheduleEntry(1, start_min, end_min, st.name))
            for m in range(start_min, end_min):
                occupied.add(m)

    def _process_multi_series_tag(self, mst, entries: List[ScheduleEntry], occupied: set, day_offset: int = 0, start_offset: int = 0) -> int:
        """Expand a MultiSeriesTag into individual episode entries, marking the whole block as occupied. Returns actual end position."""
        start_min = qtime_to_minutes(mst.start_time) + start_offset
        end_min = qtime_to_minutes(mst.end_time) + start_offset

        if start_min >= end_min:
            return start_min

        # Mark full block as occupied
        for m in range(start_min, end_min):
            occupied.add(m)

        # Place videos using shared truncation logic; returns actual end position
        actual_end = self._place_tag_videos(mst, start_min, end_min, entries)
        return actual_end

    def _process_random_fill_tag(self, rf: Tag, fill_entries: List[ScheduleEntry], merged_ranges: List[tuple] = None, start_vid_idx: int = 0, start_offset: int = 0, continuation_pos: int = None):
        rf_fill_24h = getattr(rf, 'fill_24h', False)

        if rf_fill_24h:
            rf_videos = rf.collection_videos.copy() if rf.collection_videos else []
            if not rf_videos:
                return
            random.shuffle(rf_videos)

            gaps = []
            if merged_ranges:
                prev_end = start_offset
                for start, end in merged_ranges:
                    adj_start = start + start_offset
                    adj_end = end + start_offset
                    if adj_start > prev_end:
                        gaps.append((prev_end, adj_start))
                    prev_end = max(prev_end, adj_end)
                if prev_end < start_offset + 24 * 60:
                    gaps.append((prev_end, start_offset + 24 * 60))
            else:
                gaps = [(start_offset, start_offset + 24 * 60)]

            vid_idx = start_vid_idx
            for gap_start, gap_end in gaps:
                pos = gap_start
                while pos < gap_end:
                    video = rf_videos[vid_idx % len(rf_videos)]
                    video_name = get_video_display_name(video)
                    duration = int(video.get('duration', 90)) // 60
                    if duration < 1:
                        duration = 1
                    duration = min(duration, gap_end - pos)
                    if duration < 1:
                        break
                    fill_entries.append(self._create_video_entry(pos, duration, video_name, rf.name))
                    pos += duration
                    vid_idx += 1
        else:
            rf_start = qtime_to_minutes(rf.start_time)
            rf_end = qtime_to_minutes(rf.end_time)

            rf_start += start_offset
            rf_end += start_offset

            if rf_start >= rf_end:
                return

            pos = rf_start
            if continuation_pos > rf_start:
                pos = continuation_pos
            elif continuation_pos > 0:
                pos = continuation_pos

            rf_videos = rf.collection_videos.copy() if rf.collection_videos else []
            if rf_videos:
                random.shuffle(rf_videos)
            vid_idx = 0

            while pos < rf_end or (continuation_pos is not None and pos < continuation_pos + (rf_end - rf_start)):
                if not rf_videos:
                    fill_entries.append(ScheduleEntry(1, pos, pos + 60, f"{rf.name} - No videos"))
                    break
                video = rf_videos[vid_idx % len(rf_videos)]
                video_name = get_video_display_name(video)
                duration = int(video.get('duration', 90)) // 60
                if duration < 1:
                    duration = 1
                fill_entries.append(self._create_video_entry(pos, duration, video_name, rf.name))
                pos += duration
                vid_idx += 1

    def apply_custom_tags(self, use_cache: bool = True, num_days: int = 1) -> List[ScheduleEntry]:
        cached = self.tag_manager.get_cached_random_entries()
        strategy = CustomTagMergeStrategy(self)
        if use_cache and cached is not None:
            return strategy.inject_into_random(cached)
        entries = strategy.generate(num_days)
        self.tag_manager.set_cached_random_entries(entries)
        return entries

    def apply_approximate(self, num_days: int = 1, mode: str = "find_replace") -> List[ScheduleEntry]:
        """Dispatch to the appropriate approximate scheduling strategy."""
        logger.info(f"[APPROX] Using mode: {mode}")
        if mode == "linear":
            return LinearApproximateStrategy(self).generate(num_days)
        elif mode == "find_replace":
            return FindReplaceApproximateStrategy(self).generate(num_days)
        elif mode == "early_fill":
            return EarlyFillApproximateStrategy(self).generate(num_days)
        elif mode == "late_fill":
            return LateFillApproximateStrategy(self).generate(num_days)
        elif mode == "priority":
            return PriorityApproximateStrategy(self).generate(num_days)
        elif mode == "best_fit":
            return BestFitApproximateStrategy(self).generate(num_days)
        elif mode == "round_robin":
            return RoundRobinApproximateStrategy(self).generate(num_days)
        elif mode == "linear_spanning":
            return LinearSpanningApproximateStrategy(self).generate(num_days)
        elif mode == "exhaustive":
            return ExhaustiveApproximateStrategy(self).generate(num_days)
        else:
            raise ValueError(f"Unknown approximate mode: {mode}")

    def _consume_overlapping_tail(
        self,
        slot_start: int,
        slot_end: int,
        current_pos: int,
        day_unused: list,
        random_entries: list,
        used_random: set,
        final: list,
        day_offset: int,
        min_end_threshold: int,
        scheduled_slots: list = None,
        label: str = "",
    ) -> int:
        """Consume the portion of a random entry that overlaps the tag slot.

        Finds any random entry in day_unused that intersects [slot_start, slot_end)
        and has end_minutes > min_end_threshold, marks it as used, removes it from
        day_unused, and appends its remaining tail (from after the slot_end to entry end)
        to final, provided it doesn't overlap other scheduled slots. Returns updated current_pos.
        """
        for re in day_unused[:]:
            if re.start_minutes < slot_end and re.end_minutes > min_end_threshold:
                for idx, orig_re in enumerate(random_entries):
                    if orig_re is re and idx not in used_random:
                        used_random.add(idx)
                        # Place head portion (before tag slot) if available and non-overlapping
                        if re.start_minutes < slot_start:
                            head_start = re.start_minutes
                            head_end = slot_start
                            if head_end > head_start:
                                if scheduled_slots and any(head_start < s_end and head_end > s_start for s_start, s_end in scheduled_slots):
                                    logger.debug(f"[APPROX day={day_offset+1}]   HEAD SKIPPED due to overlap: {head_start//60%24:02d}:{head_start%60:02d}-{head_end//60%24:02d}:{head_end%60:02d}")
                                else:
                                    final.append(ScheduleEntry(1, head_start, head_end, re.video_name))
                        # Determine tail start after the tag's content ends
                        tail_start = current_pos
                        tail_end = re.end_minutes
                        if tail_end > tail_start:
                            if scheduled_slots and any(tail_start < s_end and tail_end > s_start for s_start, s_end in scheduled_slots):
                                logger.debug(f"[APPROX day={day_offset+1}]   TAIL SKIPPED due to overlap: {tail_start//60%24:02d}:{tail_start%60:02d}-{tail_end//60%24:02d}:{tail_end%60:02d}")
                            else:
                                final.append(ScheduleEntry(1, tail_start, tail_end, re.video_name))
                                current_pos = tail_end
                        # Remove entry from day_unused
                        if re in day_unused:
                            day_unused.remove(re)
                        break
        return current_pos

    def _approximate_finalize_day(self, random_entries, used_random, final, day_offset, day_start, scheduled_slots, current_pos):
        day_end = day_start + 1440
        # Recompute day_unused: random entries not yet used that intersect the day
        day_unused = [e for i, e in enumerate(random_entries)
                      if i not in used_random
                      and e.start_minutes < day_end
                      and e.end_minutes > day_start]
        day_unused.sort(key=lambda e: e.start_minutes)
        logger.debug(f"[APPROX day={day_offset+1}] POST-TAGS current_pos={current_pos//60%24:02d}:{current_pos%60:02d} day_unused={len(day_unused)}")
        # Build occupied ranges from placed entries and scheduled slots
        occupied_ranges = [(e.start_minutes, e.end_minutes) for e in final if e.start_minutes < day_end and e.end_minutes > day_start]
        # Only include scheduled slots that intersect this day
        for slot_start, slot_end in scheduled_slots:
            if slot_start < day_end and slot_end > day_start:
                occupied_ranges.append((slot_start, slot_end))

        for rand_e in day_unused:
            if rand_e.start_minutes >= current_pos:
                continue
            # Skip if overlaps any occupied range (tag slots or already placed entries)
            if any(rand_e.start_minutes < occ_end and rand_e.end_minutes > occ_start for occ_start, occ_end in occupied_ranges):
                continue
            if rand_e.end_minutes <= current_pos:
                final.append(rand_e)
                occupied_ranges.append((rand_e.start_minutes, rand_e.end_minutes))
                for idx, re in enumerate(random_entries):
                    if re is rand_e and idx not in used_random:
                        used_random.add(idx)
                        break
                current_pos = rand_e.end_minutes
            elif rand_e.start_minutes < current_pos < rand_e.end_minutes:
                dur = rand_e.end_minutes - current_pos
                if dur > 0:
                    final.append(ScheduleEntry(1, current_pos, rand_e.end_minutes, rand_e.video_name))
                    for idx, re in enumerate(random_entries):
                        if re is rand_e and idx not in used_random:
                            used_random.add(idx)
                            break
                    current_pos = rand_e.end_minutes

        # Add remaining unused random entries starting from current_pos
        day_unused2 = [e for i, e in enumerate(random_entries)
                       if i not in used_random
                       and e.start_minutes < day_end
                       and e.end_minutes > day_start]
        day_unused2.sort(key=lambda e: e.start_minutes)
        for rand_e in day_unused2:
            if rand_e.start_minutes >= current_pos:
                # Skip if this entry would overlap any scheduled tag slot
                if not any(rand_e.start_minutes < slot_end and rand_e.end_minutes > slot_start
                           for slot_start, slot_end in scheduled_slots):
                    final.append(rand_e)
                    for idx, re in enumerate(random_entries):
                        if re is rand_e and idx not in used_random:
                            used_random.add(idx)
                            break
                    current_pos = rand_e.end_minutes
        return current_pos

    def _apply_approximate_find_replace(self, num_days: int, custom_tags: list, series_tags: list, multi_series_tags: list, random_fill_tags: list, has_24h_fill: bool) -> List[ScheduleEntry]:
        """Find-and-replace algorithm: Don't truncate random fill, move custom tags instead."""
        rf_sorted = sorted(random_fill_tags, key=lambda t: qtime_to_minutes(t.start_time))

        if not rf_sorted:
            return LinearApproximateStrategy(self).generate(num_days)

        rf_name = rf_sorted[0].name
        rf_videos = rf_sorted[0].collection_videos.copy() if rf_sorted and rf_sorted[0].collection_videos else []
        if rf_videos:
            random.shuffle(rf_videos)

        total_minutes = num_days * 24 * 60
        random_entries = self._build_random_entries(rf_videos, 0, total_minutes, rf_name)

        final = []
        APPROXIMATE_THRESHOLD = 60

        all_custom_sorted = sorted(custom_tags + series_tags + multi_series_tags, key=lambda t: qtime_to_minutes(t.start_time))

        used_random = set()

        for day_offset in range(num_days):
            day_start = day_offset * 24 * 60
            day_end = (day_offset + 1) * 24 * 60

            # Get fresh list of unused random entries for this day
            day_unused = [e for i, e in enumerate(random_entries)
                          if i not in used_random
                          and e.start_minutes < day_end
                          and e.end_minutes > day_start]
            day_unused.sort(key=lambda e: e.start_minutes)

            day_customs = []
            for ct in all_custom_sorted:
                orig_start = qtime_to_minutes(ct.start_time)
                orig_end = qtime_to_minutes(ct.end_time)
                custom_start = orig_start + day_start
                custom_end = orig_end + day_start
                day_customs.append((ct, orig_start, orig_end, custom_start, custom_end))
            day_customs.sort(key=lambda x: x[3])

            current_pos = day_start

            scheduled_slots = []

            for ct, orig_start, orig_end, custom_start, custom_end in day_customs:
                THRESHOLD_AFTER = 30   # max minutes past custom_start a random video can end
                # Snap to the last random video ending before custom_start but not before current_pos
                before_candidates = [e for e in day_unused if e.end_minutes <= custom_start and e.end_minutes >= current_pos]
                # Only entries that START at/after custom_start and end within threshold (clean snap forward)
                close_after = [e for e in day_unused if e.start_minutes >= custom_start and e.end_minutes < custom_start + THRESHOLD_AFTER]
                # Overlapping entries that span custom_start — just remove them
                overlapping = [e for e in day_unused if e.start_minutes < custom_start and e.end_minutes > custom_start]

                # Best before = the one ending closest to (but not after) custom_start
                best_before = max(before_candidates, key=lambda e: e.end_minutes) if before_candidates else None
                anchor_candidates = ([best_before] if best_before else []) + close_after

                logger.debug(f"[APPROX day={day_offset+1}] tag='{ct.name}' wanted={custom_start//60%24:02d}:{custom_start%60:02d} current_pos={current_pos//60%24:02d}:{current_pos%60:02d} day_unused={len(day_unused)} before={len(before_candidates)} close_after={len(close_after)} overlapping={len(overlapping)} best_before={'%02d:%02d'%(best_before.end_minutes//60%24,best_before.end_minutes%60) if best_before else 'none'}")

                if anchor_candidates:
                    best_rand = None
                    best_gap = float('inf')
                    best_idx = -1

                    for rand_e in anchor_candidates:
                        gap = abs(rand_e.end_minutes - custom_start)
                        if gap < best_gap:
                            best_gap = gap
                            best_rand = rand_e
                            for idx, re in enumerate(random_entries):
                                if re is rand_e and idx not in used_random:
                                    best_idx = idx
                                    break

                    if best_rand and best_idx >= 0:
                        logger.debug(f"[APPROX day={day_offset+1}]   BEST end={best_rand.end_minutes//60%24:02d}:{best_rand.end_minutes%60:02d} gap={best_gap} -> tag at {best_rand.end_minutes//60%24:02d}:{best_rand.end_minutes%60:02d}")
                        # Add the random entry to final before placing custom tag
                        if current_pos <= best_rand.start_minutes:
                            final.append(best_rand)
                            used_random.add(best_idx)
                            if best_rand in day_unused:
                                day_unused.remove(best_rand)
                            current_pos = best_rand.end_minutes
                        elif current_pos < best_rand.end_minutes:
                            final.append(ScheduleEntry(1, current_pos, best_rand.end_minutes, best_rand.video_name))
                            used_random.add(best_idx)
                            if best_rand in day_unused:
                                day_unused.remove(best_rand)
                            current_pos = best_rand.end_minutes
                        else:
                            used_random.add(best_idx)
                            if best_rand in day_unused:
                                day_unused.remove(best_rand)

                        slot_start = best_rand.end_minutes
                        slot_end = slot_start + (orig_end - orig_start)

                        actual_end = self._place_tag_videos(ct, slot_start, slot_end, final, day_offset)
                        current_pos = actual_end
                        scheduled_slots.append((slot_start, actual_end))
                        logger.debug(f"[APPROX day={day_offset+1}]   placed -> current_pos={current_pos//60%24:02d}:{current_pos%60:02d}")

                        # Consume overlapping random entry tails
                        current_pos = self._consume_overlapping_tail(
                            slot_start, slot_end, current_pos, day_unused, random_entries, used_random, final, day_offset,
                            min_end_threshold=slot_start,
                            scheduled_slots=scheduled_slots,
                        )
                else:
                    logger.debug(f"[APPROX day={day_offset+1}]   no best_rand -> fallback {custom_start//60%24:02d}:{custom_start%60:02d}")
                    # No valid anchor found, place at current_pos if past custom_start
                    if custom_start < current_pos:
                        custom_start = current_pos
                        custom_end = custom_start + (orig_end - orig_start)
                    slot_start = custom_start
                    slot_end = custom_end

                    actual_end = self._place_tag_videos(ct, slot_start, slot_end, final, day_offset)
                    current_pos = actual_end
                    scheduled_slots.append((slot_start, actual_end))
                    logger.debug(f"[APPROX day={day_offset+1}]   placed -> current_pos={current_pos//60%24:02d}:{current_pos%60:02d}")

                    # Consume overlapping random entry tails
                    current_pos = self._consume_overlapping_tail(
                        slot_start, slot_end, current_pos, day_unused, random_entries, used_random, final, day_offset,
                        min_end_threshold=slot_start,
                        scheduled_slots=scheduled_slots,
                        label="fallback",
                    )
            # Next custom tag iteration continues here

            # Add unused random entries from day_start to current_pos
            day_unused = [e for i, e in enumerate(random_entries)
                          if i not in used_random
                          and e.start_minutes < day_end
                          and e.end_minutes > day_start]
            day_unused.sort(key=lambda e: e.start_minutes)
            logger.debug(f"[APPROX day={day_offset+1}] POST-TAGS current_pos={current_pos//60%24:02d}:{current_pos%60:02d} day_unused={len(day_unused)}")
            for e in day_unused:
                logger.debug(f"[APPROX day={day_offset+1}]   unused: {e.start_minutes//60%24:02d}:{e.start_minutes%60:02d}-{e.end_minutes//60%24:02d}:{e.end_minutes%60%60:02d}")

            # Build occupied ranges from already-placed entries this day
            occupied_ranges = [(e.start_minutes, e.end_minutes) for e in final if e.start_minutes >= day_start]
            occupied_ranges.extend(scheduled_slots)
            # DEBUG: Log occupied ranges summary
            logger.debug(f"[APPROX day={day_offset+1}] OCCUPIED RANGES count={len(occupied_ranges)}")
            for i, (os, oe) in enumerate(occupied_ranges):
                logger.debug(f"[APPROX day={day_offset+1}]   occ[{i}]: {os//60%24:02d}:{os%60:02d} - {oe//60%24:02d}:{oe%60:02d}")

            for rand_e in day_unused:
                if rand_e.start_minutes >= current_pos:
                    continue
                # Skip if this entry overlaps any already-placed entry
                overlaps = any(rand_e.start_minutes < occ_end and rand_e.end_minutes > occ_start
                               for occ_start, occ_end in occupied_ranges)
                if not overlaps:  # DEBUG: print when NOT overlapping
                    logger.debug(f"[APPROX day={day_offset+1}]   APPROVING {rand_e.start_minutes//60%24:02d}:{rand_e.end_minutes%60:02d} -> no overlap, current_pos={current_pos//60%24:02d}:{current_pos%60:02d}")
                if overlaps:
                    logger.debug(f"[APPROX day={day_offset+1}]   SKIPPING {rand_e.start_minutes//60%24:02d}:{rand_e.end_minutes%60:02d} due to overlap, current_pos={current_pos//60%24:02d}:{current_pos%60:02d}")
                    continue
                if rand_e.end_minutes <= current_pos:
                    final.append(rand_e)
                    occupied_ranges.append((rand_e.start_minutes, rand_e.end_minutes))
                    for idx, re in enumerate(random_entries):
                        if re is rand_e and idx not in used_random:
                            used_random.add(idx)
                            break
                    current_pos = rand_e.end_minutes
                elif rand_e.start_minutes < current_pos < rand_e.end_minutes:
                    dur = rand_e.end_minutes - current_pos
                    if dur > 0:
                        final.append(ScheduleEntry(1, current_pos, rand_e.end_minutes, rand_e.video_name))
                        for idx, re in enumerate(random_entries):
                            if re is rand_e and idx not in used_random:
                                used_random.add(idx)
                                break
                        current_pos = rand_e.end_minutes

            # Add remaining unused random entries
            day_unused2 = [e for i, e in enumerate(random_entries)
                           if i not in used_random
                           and e.start_minutes < day_end
                           and e.end_minutes > day_start]
            day_unused2.sort(key=lambda e: e.start_minutes)

            for rand_e in day_unused2:
                if rand_e.start_minutes >= current_pos:
                    # Check if this entry would overlap any scheduled tag slot
                    if not any(rand_e.start_minutes < slot_end and rand_e.end_minutes > slot_start
                               for slot_start, slot_end in scheduled_slots):
                        final.append(rand_e)
                        for idx, re in enumerate(random_entries):
                            if re is rand_e and idx not in used_random:
                                used_random.add(idx)
                                break
                        current_pos = rand_e.end_minutes

        final.sort(key=lambda e: e.start_minutes)

        return final

    def _apply_approximate_linear(self, num_days: int, custom_tags: list, series_tags: list, multi_series_tags: list, random_fill_tags: list, has_24h_fill: bool) -> List[ScheduleEntry]:
        """Linear placement: Truncate random fill to make room for custom/multi-series tags."""
        # Tags are provided by caller; no need to recompute.

        rf_24h_tags = [t for t in random_fill_tags if getattr(t, 'fill_24h', False)]

        if rf_24h_tags and not custom_tags and not series_tags and not multi_series_tags:
            return self.generate_random_fill(24 * 60 * num_days)

        has_24h_fill = bool(rf_24h_tags)

        if has_24h_fill:
            base_entries = []
        else:
            base_entries = self.generate_random_fill(24 * 60) if (custom_tags or series_tags or multi_series_tags) else []

        if not custom_tags and not series_tags and not multi_series_tags and not random_fill_tags:
            return base_entries

        # Sort tags by start time for chronological processing
        custom_sorted = sorted(custom_tags, key=lambda t: qtime_to_minutes(t.start_time))
        series_sorted = sorted(series_tags, key=lambda t: qtime_to_minutes(t.start_time))
        multi_sorted = sorted(multi_series_tags, key=lambda t: qtime_to_minutes(t.start_time))

        # Sort tags by start time for chronological processing
        custom_sorted = sorted(custom_tags, key=lambda t: qtime_to_minutes(t.start_time))
        series_sorted = sorted(series_tags, key=lambda t: qtime_to_minutes(t.start_time))
        multi_sorted = sorted(multi_series_tags, key=lambda t: qtime_to_minutes(t.start_time))

        scheduled_ranges = []
        for ct in custom_sorted:
            scheduled_ranges.append((qtime_to_minutes(ct.start_time), qtime_to_minutes(ct.end_time)))
        for st in series_sorted:
            scheduled_ranges.append((qtime_to_minutes(st.start_time), qtime_to_minutes(st.end_time)))
        for mst in multi_sorted:
            scheduled_ranges.append((qtime_to_minutes(mst.start_time), qtime_to_minutes(mst.end_time)))

        for rf in random_fill_tags:
            rf_fill_24h = getattr(rf, 'fill_24h', False)
            if not rf_fill_24h:
                rf_start = qtime_to_minutes(rf.start_time)
                rf_end = qtime_to_minutes(rf.end_time)
                if rf_start < rf_end:
                    scheduled_ranges.append((rf_start, rf_end))

        scheduled_ranges.sort()

        merged_ranges = []
        for start, end in scheduled_ranges:
            if merged_ranges and start <= merged_ranges[-1][1]:
                merged_ranges[-1] = (merged_ranges[-1][0], max(merged_ranges[-1][1], end))
            else:
                merged_ranges.append((start, end))

        occupied = set()
        final = []
        rand_idx = 0
        current_pos = 0
        next_custom_pos = 0

        # Track actual placed ranges for 24h fill mode
        actual_placed_ranges = []

        custom_sorted = sorted(custom_tags, key=lambda t: qtime_to_minutes(t.start_time))
        series_sorted = sorted(series_tags, key=lambda t: qtime_to_minutes(t.start_time))
        multi_sorted = sorted(multi_series_tags, key=lambda t: qtime_to_minutes(t.start_time))

        if not has_24h_fill:
            for day_offset in range(num_days):
                day_offset_minutes = day_offset * 24 * 60
                for ct in custom_sorted:
                    original_start = qtime_to_minutes(ct.start_time)
                    original_end = qtime_to_minutes(ct.end_time)

                    custom_start = max(original_start, next_custom_pos) + day_offset_minutes
                    custom_end = custom_start + (original_end - original_start)

                    if ct.collection_videos:
                        for m in range(custom_start, custom_end):
                            occupied.add(m)
                        video_count = getattr(ct, 'video_count', 1)
                        videos = ct.collection_videos.copy()
                        random.shuffle(videos)
                        pos = custom_start
                        vid_idx = 0
                        actual_end = custom_start
                        while pos < custom_end and vid_idx < video_count and vid_idx < len(videos):
                            video = videos[vid_idx % len(videos)]
                            video_name = get_video_display_name(video)
                            duration = int(video.get('duration', 90)) // 60
                            if duration < 1:
                                duration = 1
                            duration = min(duration, custom_end - pos)
                            if duration < 1:
                                break
                            final.append(self._create_video_entry(pos, duration, video_name, ct.name))
                            actual_end = pos + duration
                            pos += duration
                            vid_idx += 1
                        current_pos = actual_end
                        next_custom_pos = actual_end
                        if has_24h_fill:
                            actual_placed_ranges.append((custom_start, custom_end))
                    else:
                        if custom_start < current_pos:
                            custom_start = current_pos
                            custom_end = custom_start + (original_end - original_start)
                        final.append(ScheduleEntry(1, custom_start, custom_end, ct.name))
                        current_pos = custom_end

                next_custom_pos = current_pos
                while rand_idx < len(base_entries) and base_entries[rand_idx].start_minutes < current_pos:
                    rand_idx += 1
        else:
            # Process custom tags for 24h fill mode
            for day_offset in range(num_days):
                day_offset_minutes = day_offset * 24 * 60
                for ct in custom_sorted:
                    original_start = qtime_to_minutes(ct.start_time)
                    original_end = qtime_to_minutes(ct.end_time)

                    custom_start = original_start + day_offset_minutes
                    custom_end = original_end + day_offset_minutes

                    if ct.collection_videos:
                        for m in range(custom_start, custom_end):
                            occupied.add(m)
                        video_count = getattr(ct, 'video_count', 1)
                        videos = ct.collection_videos.copy()
                        random.shuffle(videos)
                        pos = custom_start
                        vid_idx = 0
                        actual_end = custom_start
                        while pos < custom_end and vid_idx < video_count and vid_idx < len(videos):
                            video = videos[vid_idx % len(videos)]
                            video_name = get_video_display_name(video)
                            duration = int(video.get('duration', 90)) // 60
                            if duration < 1:
                                duration = 1
                            duration = min(duration, custom_end - pos)
                            if duration < 1:
                                break
                            final.append(self._create_video_entry(pos, duration, video_name, ct.name))
                            actual_end = pos + duration
                            pos += duration
                            vid_idx += 1
                            actual_placed_ranges.append((custom_start, custom_end))
                    else:
                        final.append(ScheduleEntry(1, custom_start, custom_end, ct.name))
                        actual_placed_ranges.append((custom_start, custom_end))

        # Series tags processing (outside if/else to handle both cases)
        for day_offset in range(num_days):
            day_offset_minutes = day_offset * 24 * 60
            for st in series_sorted:
                original_start = qtime_to_minutes(st.start_time)
                original_end = qtime_to_minutes(st.end_time)
                if original_start >= original_end:
                    continue

                series_start = max(original_start, next_custom_pos) + day_offset_minutes
                series_end = series_start + (original_end - original_start)

                videos_to_use = []
                if st.collection_videos:
                    for m in range(series_start, series_end):
                        occupied.add(m)

                    videos_to_use = self._select_series_videos(st, day_offset)

                    pos = series_start
                    actual_end = series_start
                    for v in videos_to_use:
                        if pos >= series_end:
                            break
                        video = v['video']
                        video_name = get_video_display_name(video)
                        duration = int(video.get('duration', 90)) // 60
                        if duration < 1:
                            duration = 1
                        duration = min(duration, series_end - pos)
                        if duration < 1:
                            break
                        final.append(self._create_video_entry(pos, duration, video_name, st.name))
                        actual_end = pos + duration
                        pos += duration
                    current_pos = actual_end
                    next_custom_pos = actual_end
                    if has_24h_fill:
                        actual_placed_ranges.append((series_start, series_end))
                else:
                    final.append(ScheduleEntry(1, series_start, series_end, st.name))
                    actual_placed_ranges.append((series_start, series_end))
                    actual_end = series_end
                    current_pos = actual_end
                    next_custom_pos = actual_end

        # Multi-Series tags processing
        for day_offset in range(num_days):
            day_offset_minutes = day_offset * 24 * 60
            for mst in multi_sorted:
                original_start = qtime_to_minutes(mst.start_time)
                original_end = qtime_to_minutes(mst.end_time)
                if original_start >= original_end:
                    continue

                mst_start = max(original_start, next_custom_pos) + day_offset_minutes
                mst_end = mst_start + (original_end - original_start)

                start_offset = mst_start - original_start
                actual_end = self._process_multi_series_tag(mst, final, occupied, day_offset, start_offset)
                current_pos = actual_end
                next_custom_pos = actual_end
                if has_24h_fill:
                    actual_placed_ranges.append((mst_start, mst_end))

        rf_sorted = sorted(random_fill_tags, key=lambda t: qtime_to_minutes(t.start_time))

        if not has_24h_fill:
            rf_start = qtime_to_minutes(rf_sorted[0].start_time) if rf_sorted else 0
            rf_end = qtime_to_minutes(rf_sorted[0].end_time) if rf_sorted else 24 * 60

            rf_videos = rf_sorted[0].collection_videos.copy() if rf_sorted and rf_sorted[0].collection_videos else []
            if rf_videos:
                random.shuffle(rf_videos)

            total_minutes = num_days * 24 * 60
            final.extend(self._build_random_entries(rf_videos, rf_start, total_minutes, rf_sorted[0].name if rf_sorted else ""))
        else:
            for day_offset in range(num_days):
                day_offset_minutes = day_offset * 24 * 60
                for rf in rf_sorted:
                    ranges_to_use = merged_ranges
                    self._process_random_fill_tag(rf, final, ranges_to_use, 0, day_offset_minutes)

        if len(final) == 0 and not has_24h_fill:
            while current_pos < 24 * 60 * num_days and rand_idx < len(base_entries):
                dur = min(90, base_entries[rand_idx].end_minutes - base_entries[rand_idx].start_minutes)
                final.append(ScheduleEntry(1, current_pos, current_pos + dur, base_entries[rand_idx].video_name))
                current_pos += dur
                rand_idx += 1

        final.sort(key=lambda e: e.start_minutes)

        unique_entries = []
        seen_times = set()
        for entry in final:
            key = (entry.start_minutes, entry.end_minutes)
            if key not in seen_times:
                seen_times.add(key)
                unique_entries.append(entry)

        return unique_entries
