#!/usr/bin/env python3
"""ScheduleGenerator and core scheduling engine for the daypart scheduler.

This module contains the main ScheduleGenerator class with all placement helpers,
approximate-mode dispatcher, and private scheduling algorithms.
"""

from __future__ import annotations
import copy
import os
import random
import logging
from typing import List
from PySide6.QtCore import QTime

from utils import (
    qtime_to_seconds,
    get_video_display_name,
    parse_videos_for_series,
    parse_series_episode,
    group_videos_by_movie,
    extract_movie_sequence_key,
    normalize_tag_time_range,
)
from data_models import Tag, MultiSeriesTag, ScheduleEntry, TagManager, FRAGMENT_TAG_TYPE
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
    NoOverlapApproximateStrategy,
    GroupApproximateStrategy,
)

logger = logging.getLogger(__name__)


class ScheduleGenerator:
    def __init__(self, tag_manager: TagManager):
        self.tag_manager = tag_manager
        self.video_order_mode = "random"  # "random" | "movie_sequence"
        # Bug 3 fix: counter that rotates the starting movie on each Generate click
        # so re-Generate produces visibly different previews in movie_sequence mode.
        # Reset only by explicit re-initialization; not bumped by per-tag/cached calls.
        self._generate_count = 0
        self._compact_carryover = 0
        self._prev_day_last_end = 0
        from datetime import date
        self.schedule_start_weekday = date.today().weekday()  # 0=Monday, 6=Sunday

    def _create_video_entry(self, pos: int, duration: int, name: str, tag_name: str = "", tag_type: str = "") -> ScheduleEntry:
        video_name = f"{tag_name} - {name}" if tag_name else name
        return ScheduleEntry(1, pos, pos + duration, video_name, tag_type)

    def _resolve_series_collection_path(self, st) -> str:
        """Resolve a series tag's collection to an absolute file path.

        Tries, in order:
          1. st.collection_path (full path set by the file picker)
          2. st.collection_profile (a bare file name in the collections
             directory; this is what's saved for series tags by
             serialize_tag_to_string)
          3. The first existing matching .json file in the collections
             directory (handles the "old .ini" case where neither field
             is set but the user expects a known collection to be used)

        Returns the path string if a resolvable file exists, or '' if
        no candidate is found.
        """
        # 1. Direct path
        direct = getattr(st, 'collection_path', '') or ''
        if direct and os.path.isfile(direct):
            return direct

        # 2. Profile name → collections_dir / profile_name
        from utils import get_config_paths
        coll_dir, _ = get_config_paths()
        profile = getattr(st, 'collection_profile', '') or ''
        if profile:
            candidate = os.path.join(coll_dir, profile)
            if os.path.isfile(candidate):
                return candidate

        # 3. Fallback: scan collections dir for any matching json
        if profile and os.path.isdir(coll_dir):
            base = os.path.splitext(profile)[0]
            for ext in (".json",):
                candidate = os.path.join(coll_dir, base + ext)
                if os.path.isfile(candidate):
                    return candidate
            # Last resort: any collections_*.json that contains the
            # base name (handles the 'collections_<name>.json' vs '<name>.json'
            # naming variations the user may have on disk).
            for entry in os.listdir(coll_dir):
                if entry.endswith(".json") and base in entry:
                    return os.path.join(coll_dir, entry)

        return ''

    def _is_tag_active_on_day(self, tag, day_offset: int) -> bool:
        active_days = getattr(tag, 'active_days', None)
        if not active_days:
            return True
        real_weekday = (self.schedule_start_weekday + day_offset) % 7  # 0=Monday
        return (real_weekday + 1) in active_days  # convert to 1-based (1=Monday)

    def _get_marathon_videos(self, tag, day_offset: int) -> List[dict]:
        """Filter collection_videos to only those whose collection tags
        include marathon_tag_name.
        Returns filtered list; repeats to fill the full day window is handled
        by the caller's fill_24h loop."""
        if not getattr(tag, 'marathon_mode', False) or not getattr(tag, 'marathon_tag_name', ''):
            return tag.collection_videos or []
        target = tag.marathon_tag_name
        filtered = [
            v for v in (tag.collection_videos or [])
            if target in v.get('_meta_tags', [])
        ]
        if not filtered:
            filtered = tag.collection_videos or []
        return filtered

    def _select_series_videos(self, tag_or_config, day_offset: int) -> List[dict]:
        """Select videos for a series tag (Tag object or config dict) for given day_offset.
        Supports end-behavior: stop (default), repeat, random.
        Returns list of dicts with keys 'video', 'season', 'episode'.
        """
        is_dict = isinstance(tag_or_config, dict)
        def _get(key, default=None):
            return tag_or_config.get(key, default) if is_dict else getattr(tag_or_config, key, default)

        collection_videos = _get('collection_videos', [])
        if not collection_videos:
            return []

        video_count = _get('video_count', 1)
        play_mode = _get('play_mode', 'sequence')
        start_season = _get('start_season', 1)
        start_episode = _get('start_episode', 1)
        has_season_tags = _get('_has_season_tags', False)
        end_behavior = _get('series_end_behavior', 'stop')
        repeat_season = _get('series_repeat_season', 0)
        random_season = _get('series_random_season', 0)

        # Build the eligible video list with consistent ordering
        if play_mode == 'season_sequence' and has_season_tags:
            flat = _get('_flat_ordered')
            if not flat:
                return []
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
                return []
            # Normalize to parsed format for uniform handling below
            eligible = [{'video': v, 'season': v.get('_meta_season'), 'episode': v.get('_parsed_episode')} for v in flat[start_idx:]]
        else:
            # Build sorted eligible list from collection videos
            parsed = []
            for idx, vid in enumerate(collection_videos):
                path = vid.get('path', '')
                season, episode = parse_series_episode(path)
                if season > start_season or (season == start_season and episode >= start_episode):
                    parsed.append({'video': vid, 'season': season, 'episode': episode, 'index': idx})

            if not parsed:
                return []

            # Deterministic ordering: sort by (season, episode)
            parsed.sort(key=lambda v: (v['season'], v['episode'], v['index']))

            # For random play mode, apply deterministic shuffle to the ordering
            if play_mode == 'random':
                seed = f"{_get('collection_path', '')}_{_get('name', '')}_ordering"
                rng = random.Random(seed)
                rng.shuffle(parsed)

            # Keep full parsed structure (video + season + episode) for return
            eligible = parsed

        total_eligible = len(eligible)
        if total_eligible == 0:
            return []

        effective_idx = day_offset * video_count

        # Random end-behavior: shuffle pool, cycle without repeats
        if end_behavior == 'random':
            if random_season == 0:
                pool_idx = list(range(total_eligible))
            else:
                pool_idx = [i for i in range(total_eligible)
                            if eligible[i]['season'] == random_season]
            if not pool_idx:
                return []
            pool_size = len(pool_idx)
            seed_str = f"{_get('collection_path', '')}_{_get('name', '')}_random"
            cycle_num = effective_idx // pool_size
            local_idx = effective_idx % pool_size
            rng = random.Random(f"{seed_str}_cycle_{cycle_num}")
            shuffled_idx = list(pool_idx)
            rng.shuffle(shuffled_idx)
            selected_idx = shuffled_idx[local_idx : local_idx + video_count]
            return [eligible[i] for i in selected_idx]

        # Check if past the eligible range
        if effective_idx + video_count > total_eligible:
            if end_behavior == 'stop':
                return []
            if end_behavior == 'repeat':
                if repeat_season == 0:
                    wrap_idx = 0
                else:
                    wrap_idx = 0
                    for i in range(total_eligible):
                        s = eligible[i]['season']
                        if s is not None and s >= repeat_season:
                            wrap_idx = i
                            break
                wrap_range = total_eligible - wrap_idx
                if wrap_range <= 0:
                    return []
                idx_in_range = (effective_idx - wrap_idx) % wrap_range
                selected = []
                for i in range(video_count):
                    selected.append(eligible[wrap_idx + (idx_in_range + i) % wrap_range])
                return selected

        # Normal: within eligible range
        take = min(video_count, total_eligible - effective_idx)
        return eligible[effective_idx : effective_idx + take]

    def _get_videos_for_day(self, videos: List[dict], day_offset: int) -> List[dict]:
        """Select videos according to global video_order_mode for a given day.

        Args:
            videos: Full list of collection videos
            day_offset: 0-based day index (0=day1, 1=day2, ...)

        Returns:
            Ordered list of videos to use for this day
        """
        if not videos:
            return []

        if self.video_order_mode == 'movie_sequence':
            groups = group_videos_by_movie(videos)
            if not groups:
                return videos.copy()
            movie_numbers = sorted(groups.keys())
            # Bug 3 fix: rotate the starting movie by _generate_count so re-Generate
            # gives a visibly different preview while preserving day→movie mapping.
            num_movies = len(movie_numbers)
            effective_day = (day_offset + self._generate_count) % num_movies
            selected_movie = movie_numbers[effective_day]
            day_videos = groups[selected_movie].copy()
            return day_videos
        else:
            # Random mode: shuffle
            shuffled = videos.copy()
            random.shuffle(shuffled)
            return shuffled

    def _place_tag_videos(self, ct, start: int, end: int, final: List[ScheduleEntry], day_offset: int = 0) -> int:
        """Place custom/series/multi-series tag videos into final schedule. Returns new current_pos."""
        logger.debug(f"[PLACE] tag='{ct.name}' play_mode={getattr(ct,'play_mode','?')} day_offset={day_offset} is_series={getattr(ct,'is_series',False)} has_season={getattr(ct,'_has_season_tags',False)}")

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
                    final.append(self._create_video_entry(pos, 3600, series_name, ct.name, "multi_series"))
                    pos += 3600
                    continue

                # Use unified video selection (season_sequence or regular)
                videos_to_use = self._select_series_videos(series_config, day_offset)

                for v in videos_to_use:
                    if pos >= end:
                        break
                    video = v['video']
                    video_name = get_video_display_name(video)
                    duration = int(video.get('duration', 90))
                    if duration < 1:
                        duration = 90
                    # Skip if video doesn't fit in remaining slot space
                    if pos + duration > end:
                        continue
                    final.append(self._create_video_entry(pos, duration, video_name, series_name, "multi_series"))
                    pos += duration
            return pos

        if ct.collection_videos:
            video_count = getattr(ct, 'video_count', 1)
            is_series = getattr(ct, 'is_series', False)
            play_mode = getattr(ct, 'play_mode', 'sequence')
            has_season_tags = getattr(ct, '_has_season_tags', False)

            if is_series:
                logger.debug(f"[PLACE]   -> using _select_series_videos")
                videos_to_use = self._select_series_videos(ct, day_offset)
                ordered_videos = [v['video'] for v in videos_to_use]
                logger.debug(f"[PLACE]   selected {len(videos_to_use)} videos")
            else:
                # For non-series custom tags: use day-aware selection
                day_offset = start // 86400  # start is absolute seconds
                ordered_videos = self._get_videos_for_day(ct.collection_videos, day_offset)
                if getattr(ct, 'randomize_videos', False):
                    random.shuffle(ordered_videos)

            pos = start
            vid_idx = 0
            while pos <= end and vid_idx < video_count and vid_idx < len(ordered_videos):
                video = ordered_videos[vid_idx]
                video_name = get_video_display_name(video)
                duration = int(video.get('duration', 90))
                if duration < 1:
                    duration = 90
                if pos + duration > end:
                    end = pos + duration
                final.append(self._create_video_entry(pos, duration, video_name, ct.name, "custom"))
                pos += duration
                vid_idx += 1
            return pos
        else:
            final.append(ScheduleEntry(1, start, end, ct.name, ct.tag_type))
            return end

    def _build_random_entries(self, videos: List[dict], start_pos: int, end_pos: int, tag_name: str = "") -> List[ScheduleEntry]:
        """Build schedule entries by cycling through videos from start_pos to end_pos, respecting day boundaries in movie_sequence mode."""
        entries = []
        if not videos:
            placeholder = f"{tag_name} - No videos" if tag_name else "No videos"
            entries.append(ScheduleEntry(1, start_pos, start_pos + 3600, placeholder))
            return entries

        if self.video_order_mode != 'movie_sequence':
            # Original random behavior: single shuffle, continuous across range
            vids = videos.copy()
            random.shuffle(vids)
            pos = start_pos
            vid_idx = 0
            while pos < end_pos:
                video = vids[vid_idx % len(vids)]
                video_name = get_video_display_name(video)
                duration = int(video.get('duration', 90))
                if duration < 1:
                    duration = 90
                name = f"{tag_name} - {video_name}" if tag_name else video_name
                entries.append(ScheduleEntry(1, pos, pos + duration, name))
                pos += duration
                vid_idx += 1
            return entries

        # movie_sequence mode: build continuous ordered list (movies in sequence) across all days
        vids = videos.copy()
        groups = group_videos_by_movie(vids)
        ordered = []
        if groups:
            movie_numbers = sorted(groups.keys())
            for mnum in movie_numbers:
                ordered.extend(groups[mnum])
        else:
            ordered = vids
        # Bug 3 fix: rotate the cycle start so re-Generate produces a visibly
        # different ordering. Pure rotation preserves part-order within each group.
        if ordered:
            rotation = self._generate_count % len(ordered)
            ordered = ordered[rotation:] + ordered[:rotation]
        pos = start_pos
        vid_idx = 0
        while pos < end_pos:
            video = ordered[vid_idx % len(ordered)]
            video_name = get_video_display_name(video)
            duration = int(video.get('duration', 90))
            if duration < 1:
                duration = 90
            entry_end = min(pos + duration, end_pos)
            name = f"{tag_name} - {video_name}" if tag_name else video_name
            entries.append(ScheduleEntry(1, pos, entry_end, name))
            pos = entry_end
            vid_idx += 1
        return entries

    def _get_all_videos(self, tags: List[Tag]) -> List[dict]:
        videos = []
        for tag in tags:
            if tag.collection_videos:
                videos.extend(tag.collection_videos)
        return videos

    def generate_random_fill(self, remaining_seconds: int = 24 * 3600) -> List[ScheduleEntry]:
        all_tags = self.tag_manager.get_all_tags()
        collection_videos = self._get_all_videos(all_tags)

        if not collection_videos:
            return []

        entries = []

        if self.video_order_mode == 'movie_sequence':
            # Build continuous ordered list (movies in sequence) across all days
            vids = collection_videos.copy()
            groups = group_videos_by_movie(vids)
            ordered = []
            if groups:
                movie_numbers = sorted(groups.keys())
                for mnum in movie_numbers:
                    ordered.extend(groups[mnum])
            else:
                ordered = vids
            # Bug 3 fix: rotate the cycle start so re-Generate produces a visibly
            # different ordering. Pure rotation preserves part-order within each group.
            if ordered:
                rotation = self._generate_count % len(ordered)
                ordered = ordered[rotation:] + ordered[:rotation]
            current_second = 0
            video_index = 0
            while current_second < remaining_seconds:
                video = ordered[video_index % len(ordered)]
                video_name = get_video_display_name(video)
                duration = int(video.get('duration', 90))
                if duration < 1:
                    duration = 90
                end_second = min(current_second + duration, remaining_seconds)
                entries.append(ScheduleEntry(1, current_second, end_second, video_name))
                current_second = end_second
                video_index += 1
        else:
            # Random mode: single shuffle across entire span
            shuffled = collection_videos.copy()
            random.shuffle(shuffled)
            current_second = 0
            video_index = 0
            while current_second < remaining_seconds:
                video = shuffled[video_index % len(shuffled)]
                video_name = get_video_display_name(video)
                duration = int(video.get('duration', 90))
                if duration < 1:
                    duration = 90
                end_second = min(current_second + duration, remaining_seconds)
                entries.append(ScheduleEntry(1, current_second, end_second, video_name))
                current_second = end_second
                video_index += 1

        return entries

    def _process_custom_tag(self, ct: Tag, custom_entries: List[ScheduleEntry], occupied: set, start_offset: int = 0,
                            adjusted_start: Optional[QTime] = None,
                            adjusted_end: Optional[QTime] = None):
        if adjusted_start is not None:
            start_sec = qtime_to_seconds(adjusted_start)
        else:
            start_sec = qtime_to_seconds(ct.start_time)
        if adjusted_end is not None:
            end_sec = qtime_to_seconds(adjusted_end)
        else:
            end_sec = qtime_to_seconds(ct.end_time)

        if end_sec <= start_sec:
            end_sec += 86400

        start_sec += start_offset
        end_sec += start_offset

        if start_sec >= end_sec:
            return

        if ct.collection_videos:
            for s in range(start_sec, end_sec):
                occupied.add(s)
            video_count = getattr(ct, 'video_count', 1)
            # Compute day offset from start_sec (absolute seconds)
            day_offset = start_sec // 86400
            videos = self._get_videos_for_day(ct.collection_videos, day_offset)
            # Honor randomize_videos flag: if true, shuffle within the day's selection
            if getattr(ct, 'randomize_videos', False):
                random.shuffle(videos)
            pos = start_sec
            vid_idx = 0
            while pos <= end_sec and vid_idx < video_count and vid_idx < len(videos):
                video = videos[vid_idx % len(videos)]
                video_name = get_video_display_name(video)
                duration = int(video.get('duration', 90))
                if duration < 1:
                    duration = 90
                if pos + duration > end_sec:
                    end_sec = pos + duration
                custom_entries.append(self._create_video_entry(pos, duration, video_name, ct.name, "custom"))
                pos += duration
                vid_idx += 1
        else:
            custom_entries.append(ScheduleEntry(1, start_sec, end_sec, ct.name, "custom"))
            for s in range(start_sec, end_sec):
                occupied.add(s)

    def _process_series_tag(self, st: Tag, series_entries: List[ScheduleEntry], occupied: set, day_offset: int = 0, start_offset: int = 0):
        start_sec = qtime_to_seconds(st.start_time)
        end_sec = qtime_to_seconds(st.end_time)

        if end_sec <= start_sec:
            end_sec += 86400

        start_sec += start_offset
        end_sec += start_offset

        if start_sec >= end_sec:
            return

        # Cold-load recovery (Bug 2): if collection_videos is empty, try
        # to resolve the collection from:
        #   1. collection_path (full path, set when the user picks the
        #      file in the file picker; saved for random/custom tags but
        #      NOT for series tags — see Bug 2 note below)
        #   2. collection_profile (a file name in the collections
        #      directory; this is what's saved for series tags)
        # If either resolves to a real file, lazy-load the videos from
        # it. This mirrors what serialization.py does on disk-load and
        # replaces the user workaround of opening the edit dialog and
        # clicking Save to populate the in-memory list.
        if not st.collection_videos:
            resolved_path = self._resolve_series_collection_path(st)
            if resolved_path:
                try:
                    from utils import load_collection_videos_only
                    loaded = load_collection_videos_only(resolved_path)
                    if loaded:
                        st.collection_videos = loaded
                        # Also set collection_path so subsequent code
                        # (and any debugging) sees the resolved path.
                        st.collection_path = resolved_path
                except Exception:
                    pass

        if st.collection_videos:
            for s in range(start_sec, end_sec):
                occupied.add(s)

            videos_to_use = self._select_series_videos(st, day_offset)

            pos = start_sec
            placed = 0
            for v in videos_to_use:
                video = v['video']
                video_name = get_video_display_name(video)
                duration = int(video.get('duration', 90))
                if duration < 1:
                    duration = 90
                if pos + duration > end_sec:
                    # Soft-hint: extend the window just enough for this video
                    extended_end = pos + duration
                    for s in range(end_sec, extended_end):
                        occupied.add(s)
                    end_sec = extended_end
                series_entries.append(self._create_video_entry(pos, duration, video_name, st.name, "series"))
                pos += duration
                placed += 1

            # The soft-hint logic above now handles per-video overflow by
            # extending the occupied window as needed. The old fallback for
            # placed==0 is preserved only as a safety net for the edge case
            # where a single video is longer than the entire initial window.
            if placed == 0 and videos_to_use:
                first_video = videos_to_use[0]['video']
                first_name = get_video_display_name(first_video)
                first_duration = int(first_video.get('duration', 90))
                if first_duration < 1:
                    first_duration = 90
                extended_end = start_sec + first_duration
                for s in range(end_sec, extended_end):
                    occupied.add(s)
                series_entries.append(
                    self._create_video_entry(start_sec, first_duration, first_name, st.name, "series")
                )
        else:
            series_entries.append(ScheduleEntry(1, start_sec, end_sec, st.name, "series"))
            for s in range(start_sec, end_sec):
                occupied.add(s)

    def _process_multi_series_tag(self, mst, entries: List[ScheduleEntry], occupied: set, day_offset: int = 0, start_offset: int = 0) -> int:
        """Expand a MultiSeriesTag into individual episode entries, marking the whole block as occupied. Returns actual end position."""
        start_sec = qtime_to_seconds(mst.start_time)
        end_sec = qtime_to_seconds(mst.end_time)

        if end_sec <= start_sec:
            end_sec += 86400

        start_sec += start_offset
        end_sec += start_offset

        if start_sec >= end_sec:
            return start_sec

        # Mark full block as occupied
        for s in range(start_sec, end_sec):
            occupied.add(s)

        # Place videos using shared truncation logic; returns actual end position
        actual_end = self._place_tag_videos(mst, start_sec, end_sec, entries, day_offset)
        return actual_end

    def _process_random_fill_tag(self, rf: Tag, fill_entries: List[ScheduleEntry], merged_ranges: List[tuple] = None, start_vid_idx: int = 0, start_offset: int = 0, continuation_pos: int = None):
        rf_fill_24h = getattr(rf, 'fill_24h', False)

        if rf_fill_24h:
            # Marathon mode: filter to specific tag/series, check active days
            marathon_mode = getattr(rf, 'marathon_mode', False)
            if marathon_mode:
                day_offset = start_offset // 86400
                if self._is_tag_active_on_day(rf, day_offset):
                    rf_videos_base = self._get_marathon_videos(rf, day_offset)
                else:
                    rf_videos_base = rf.collection_videos.copy() if rf.collection_videos else []
            else:
                rf_videos_base = rf.collection_videos.copy() if rf.collection_videos else []
            if not rf_videos_base:
                return
            day_offset = start_offset // 86400
            rf_videos = self._get_videos_for_day(rf_videos_base, day_offset)
            gaps = []
            if merged_ranges:
                prev_end = start_offset
                for start, end in merged_ranges:
                    adj_start = start + start_offset
                    adj_end = end + start_offset
                    if adj_start > prev_end:
                        gaps.append((prev_end, adj_start))
                    prev_end = max(prev_end, adj_end)
                if prev_end < start_offset + 24 * 3600:
                    gaps.append((prev_end, start_offset + 24 * 3600))
            else:
                gaps = [(start_offset, start_offset + 24 * 3600)]

            vid_idx = start_vid_idx
            for gap_start, gap_end in gaps:
                pos = gap_start
                skips_since_progress = 0
                while pos < gap_end:
                    video = rf_videos[vid_idx % len(rf_videos)]
                    video_name = get_video_display_name(video)
                    duration = int(video.get('duration', 90))
                    if duration < 1:
                        duration = 90
                    if pos + duration > gap_end:
                        vid_idx += 1
                        skips_since_progress += 1
                        if skips_since_progress >= len(rf_videos):
                            break
                        continue
                    fill_entries.append(self._create_video_entry(pos, duration, video_name, rf.name, "random_fill"))
                    pos += duration
                    skips_since_progress = 0
                    vid_idx += 1
        else:
            rf_start = qtime_to_seconds(rf.start_time)
            rf_end = qtime_to_seconds(rf.end_time)

            rf_start += start_offset
            rf_end += start_offset

            if rf_start >= rf_end:
                return

            rf_videos_base = rf.collection_videos.copy() if rf.collection_videos else []
            if not rf_videos_base:
                return
            if self.video_order_mode == 'movie_sequence':
                groups = group_videos_by_movie(rf_videos_base)
                rf_videos = []
                if groups:
                    movie_numbers = sorted(groups.keys())
                    for mnum in movie_numbers:
                        rf_videos.extend(groups[mnum])
                else:
                    rf_videos = rf_videos_base
            else:
                rf_videos = rf_videos_base

            pos = rf_start
            if continuation_pos > rf_start:
                pos = continuation_pos
            elif continuation_pos > 0:
                pos = continuation_pos

            vid_idx = 0

            while pos < rf_end or (continuation_pos is not None and pos < continuation_pos + (rf_end - rf_start)):
                if not rf_videos:
                    fill_entries.append(ScheduleEntry(1, pos, pos + 3600, f"{rf.name} - No videos"))
                    break
                video = rf_videos[vid_idx % len(rf_videos)]
                video_name = get_video_display_name(video)
                duration = int(video.get('duration', 90))
                if duration < 1:
                    duration = 90
                fill_entries.append(self._create_video_entry(pos, duration, video_name, rf.name, "random_fill"))
                pos += duration
                vid_idx += 1

    def apply_custom_tags(self, use_cache: bool = True, num_days: int = 1) -> List[ScheduleEntry]:
        # Bug 3 fix: bump rotation counter so re-Generate produces a different preview
        # in movie_sequence mode. We bump it even on cache hits, so the user gets
        # a fresh cycle start each click.
        self._generate_count += 1
        cached = self.tag_manager.get_cached_random_entries()
        strategy = CustomTagMergeStrategy(self)
        if use_cache and cached is not None:
            return strategy.inject_into_random(cached)
        entries = strategy.generate(num_days)
        self.tag_manager.set_cached_random_entries(entries)
        return entries

    def apply_approximate(self, num_days: int = 1, mode: str = "find_replace", overlap_strategy: str = "fragment") -> List[ScheduleEntry]:
        """Dispatch to the appropriate approximate scheduling strategy."""
        # Bug 3 fix: same rotation behavior in approximate mode.
        self._generate_count += 1
        self._overlap_strategy = overlap_strategy
        logger.info(f"[APPROX] Using mode: {mode}, overlap_strategy={overlap_strategy}")
        if mode == "linear":
            entries = LinearApproximateStrategy(self).generate(num_days)
        elif mode == "find_replace":
            entries = FindReplaceApproximateStrategy(self).generate(num_days)
        elif mode == "early_fill":
            entries = EarlyFillApproximateStrategy(self).generate(num_days)
        elif mode == "late_fill":
            entries = LateFillApproximateStrategy(self).generate(num_days)
        elif mode == "priority":
            entries = PriorityApproximateStrategy(self).generate(num_days)
        elif mode == "best_fit":
            entries = BestFitApproximateStrategy(self).generate(num_days)
        elif mode == "round_robin":
            entries = RoundRobinApproximateStrategy(self).generate(num_days)
        elif mode == "linear_spanning":
            entries = LinearSpanningApproximateStrategy(self).generate(num_days)
        elif mode == "exhaustive":
            entries = ExhaustiveApproximateStrategy(self).generate(num_days)
        elif mode == "no_overlap":
            entries = NoOverlapApproximateStrategy(self).generate(num_days)
        elif mode == "group_approximate":
            entries = GroupApproximateStrategy(self).generate(num_days)
        else:
            raise ValueError(f"Unknown approximate mode: {mode}")

        # Post-process: fill remaining gaps with gap tag videos
        gap_tags = [t for t in self.tag_manager.get_all_tags() if t.is_gap_filler]
        if gap_tags:
            dummy_strategy = CustomTagMergeStrategy(self)
            gap_entries = dummy_strategy._fill_gap_fillers(
                gap_tags, entries, [], [], [], num_days
            )
            if gap_entries:
                entries = entries + gap_entries
                entries.sort(key=lambda e: e.start_seconds)

        return entries

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
        and has end_seconds > min_end_threshold, marks it as used, removes it from
        day_unused, and handles overlap according to the current overlap_strategy.

        Strategies:
          "fragment" — current behavior (head/tail entries with FRAGMENT_TAG_TYPE)
          "skip"     — remove entry, no head/tail, don't advance current_pos
          "gap_fill" — same as skip
          "compact"  — same as skip, but shift remaining unused entries left to fill the gap
        """
        overlap_strategy = getattr(self, '_overlap_strategy', 'fragment')

        if overlap_strategy == 'compact':
            # Compact: remove ALL overlapped entries in one pass, then shift remaining
            # entries that start after the slot to start at current_pos.
            day_end = (day_offset + 1) * 86400
            overlapped_indices = set()
            for re in day_unused[:]:
                if re.start_seconds < slot_end and re.end_seconds > min_end_threshold:
                    for idx, orig_re in enumerate(random_entries):
                        if orig_re is re and idx not in used_random:
                            used_random.add(idx)
                            overlapped_indices.add(idx)
                            if re in day_unused:
                                day_unused.remove(re)
                            break
            if overlapped_indices:
                # Shift remaining entries that start after the slot within THIS day only
                post_slot = [e for i, e in enumerate(random_entries)
                             if i not in used_random and e.start_seconds >= slot_end and e.start_seconds < day_end]
                if post_slot:
                    first_post = min(post_slot, key=lambda e: e.start_seconds)
                    shift = first_post.start_seconds - current_pos
                    if shift != 0:
                        for ci, later_re in enumerate(random_entries):
                            if ci not in used_random and later_re.start_seconds >= first_post.start_seconds and later_re.start_seconds < day_end:
                                later_re.start_seconds -= shift
                                later_re.end_seconds -= shift
            return current_pos

        # Single-entry overlap handling for fragment/skip/gap_fill
        for re in day_unused[:]:
            if re.start_seconds < slot_end and re.end_seconds > min_end_threshold:
                for idx, orig_re in enumerate(random_entries):
                    if orig_re is re and idx not in used_random:
                        used_random.add(idx)

                        if overlap_strategy == 'fragment':
                            # Place head portion (before tag slot) if available and non-overlapping
                            if re.start_seconds < slot_start:
                                head_start = re.start_seconds
                                head_end = slot_start
                                if head_end > head_start:
                                    if scheduled_slots and any(head_start < s_end and head_end > s_start for s_start, s_end in scheduled_slots):
                                        logger.debug(f"[APPROX day={day_offset+1}]   HEAD SKIPPED due to overlap: {head_start//3600%24:02d}:{(head_start%3600)//60:02d}:{head_start%60:02d}-{head_end//3600%24:02d}:{(head_end%3600)//60:02d}:{head_end%60:02d}")
                                    else:
                                        final.append(ScheduleEntry(1, head_start, head_end, re.video_name, FRAGMENT_TAG_TYPE))
                            # Determine tail start after the tag's content ends
                            tail_start = current_pos
                            tail_end = re.end_seconds
                            if tail_end > tail_start:
                                if scheduled_slots and any(tail_start < s_end and tail_end > s_start for s_start, s_end in scheduled_slots):
                                    logger.debug(f"[APPROX day={day_offset+1}]   TAIL SKIPPED due to overlap: {tail_start//3600%24:02d}:{(tail_start%3600)//60:02d}:{tail_start%60:02d}-{tail_end//3600%24:02d}:{(tail_end%3600)//60:02d}:{tail_end%60:02d}")
                                else:
                                    final.append(ScheduleEntry(1, tail_start, tail_end, re.video_name, FRAGMENT_TAG_TYPE))
                                    current_pos = tail_end
                        elif overlap_strategy == 'skip' or overlap_strategy == 'gap_fill':
                            # Remove entry entirely — no head/tail fragments
                            pass

                        # Remove entry from day_unused
                        if re in day_unused:
                            day_unused.remove(re)
                        break
        return current_pos

    def _approximate_finalize_day(self, random_entries, used_random, final, day_offset, day_start, scheduled_slots, current_pos):
        day_end = day_start + 86400
        overlap_strategy = getattr(self, '_overlap_strategy', 'fragment')
        # Recompute day_unused: random entries not yet used that intersect the day
        day_unused = [e for i, e in enumerate(random_entries)
                      if i not in used_random
                      and e.start_seconds < day_end
                      and e.end_seconds > day_start]
        day_unused.sort(key=lambda e: e.start_seconds)
        logger.debug(f"[APPROX day={day_offset+1}] POST-TAGS current_pos={current_pos//3600%24:02d}:{(current_pos%3600)//60:02d}:{current_pos%60:02d} day_unused={len(day_unused)}")
        # Build occupied ranges from placed entries and scheduled slots
        occupied_ranges = [(e.start_seconds, e.end_seconds) for e in final if e.start_seconds < day_end and e.end_seconds > day_start]
        # Only include scheduled slots that intersect this day
        for slot_start, slot_end in scheduled_slots:
            if slot_start < day_end and slot_end > day_start:
                occupied_ranges.append((slot_start, slot_end))

        for rand_e in day_unused:
            if rand_e.start_seconds >= current_pos:
                continue
            # Skip if overlaps any occupied range (tag slots or already placed entries)
            if any(rand_e.start_seconds < occ_end and rand_e.end_seconds > occ_start for occ_start, occ_end in occupied_ranges):
                continue
            if rand_e.end_seconds <= current_pos:
                final.append(rand_e)
                occupied_ranges.append((rand_e.start_seconds, rand_e.end_seconds))
                for idx, re in enumerate(random_entries):
                    if re is rand_e and idx not in used_random:
                        used_random.add(idx)
                        break
                current_pos = rand_e.end_seconds
            elif rand_e.start_seconds < current_pos < rand_e.end_seconds:
                dur = rand_e.end_seconds - current_pos
                if dur > 0:
                    if overlap_strategy == 'fragment':
                        final.append(ScheduleEntry(1, current_pos, rand_e.end_seconds, rand_e.video_name, FRAGMENT_TAG_TYPE))
                    for idx, re in enumerate(random_entries):
                        if re is rand_e and idx not in used_random:
                            used_random.add(idx)
                            break
                    if overlap_strategy == 'fragment':
                        current_pos = rand_e.end_seconds

        # Add remaining unused random entries starting from current_pos
        day_unused2 = [e for i, e in enumerate(random_entries)
                       if i not in used_random
                       and e.start_seconds < day_end
                       and e.end_seconds > day_start]
        day_unused2.sort(key=lambda e: e.start_seconds)
        for rand_e in day_unused2:
            if rand_e.start_seconds >= current_pos:
                # Skip if this entry would overlap any scheduled tag slot
                if not any(rand_e.start_seconds < slot_end and rand_e.end_seconds > slot_start
                           for slot_start, slot_end in scheduled_slots):
                    final.append(rand_e)
                    for idx, re in enumerate(random_entries):
                        if re is rand_e and idx not in used_random:
                            used_random.add(idx)
                            break
                    current_pos = rand_e.end_seconds
        return current_pos

    def _apply_approximate_find_replace(self, num_days: int, custom_tags: list, series_tags: list, multi_series_tags: list, random_fill_tags: list, has_24h_fill: bool) -> List[ScheduleEntry]:
        """Find-and-replace algorithm: Don't truncate random fill, move custom tags instead."""
        overlap_strategy = getattr(self, '_overlap_strategy', 'fragment')
        rf_sorted = sorted(random_fill_tags, key=lambda t: qtime_to_seconds(t.start_time))

        if not rf_sorted:
            return LinearApproximateStrategy(self).generate(num_days)

        rf_name = rf_sorted[0].name
        rf_videos = rf_sorted[0].collection_videos.copy() if rf_sorted and rf_sorted[0].collection_videos else []
        if rf_videos:
            random.shuffle(rf_videos)

        total_seconds = num_days * 24 * 3600
        random_entries = self._build_random_entries(rf_videos, 0, total_seconds, rf_name)

        final = []
        APPROXIMATE_THRESHOLD = 60

        all_custom_sorted = sorted(custom_tags + series_tags + multi_series_tags, key=lambda t: qtime_to_seconds(t.start_time))

        used_random = set()
        self._compact_carryover = 0
        self._gap_video_idx = len(random_entries) % len(rf_videos) if rf_videos else 0

        for day_offset in range(num_days):
            day_start = day_offset * 24 * 3600
            day_end = (day_offset + 1) * 24 * 3600

            # Build per-day independent copies — compact shifts never leak to other days
            day_indices = sorted(i for i, e in enumerate(random_entries)
                                if i not in used_random
                                and e.start_seconds < day_end
                                and e.end_seconds > day_start)
            day_entries = [copy.copy(random_entries[i]) for i in day_indices]
            day_to_global = dict(enumerate(day_indices))
            used_day = set()

            # Apply carryover from previous day: shift entries left to close the gap
            # between the previous day's last entry end and the first entry on this day.
            if overlap_strategy == 'compact':
                day_first = min((e for e in day_entries if e.start_seconds >= day_start),
                                key=lambda e: e.start_seconds, default=None)
                if day_first:
                    gap = day_first.start_seconds - self._prev_day_last_end
                    if gap > 1:
                        for e in day_entries:
                            e.start_seconds -= gap
                            e.end_seconds -= gap
                        # Also update random_entries so subsequent days use corrected positions
                        for local_idx, e in enumerate(day_entries):
                            global_idx = day_to_global[local_idx]
                            re = random_entries[global_idx]
                            re.start_seconds = e.start_seconds
                            re.end_seconds = e.end_seconds
                self._compact_carryover = 0

            day_unused = [e for e in day_entries
                          if e.start_seconds < day_end and e.end_seconds > day_start]
            day_unused.sort(key=lambda e: e.start_seconds)

            day_customs = []
            for ct in all_custom_sorted:
                if not self._is_tag_active_on_day(ct, day_offset):
                    continue
                orig_start, orig_end = normalize_tag_time_range(ct)
                custom_start = orig_start + day_start
                custom_end = orig_end + day_start
                day_customs.append((ct, orig_start, orig_end, custom_start, custom_end))
            day_customs.sort(key=lambda x: x[3])

            current_pos = day_start

            scheduled_slots = []

            for ct, orig_start, orig_end, custom_start, custom_end in day_customs:
                THRESHOLD_AFTER = 30 * 60  # 1800 seconds
                # Snap to the last random video ending before custom_start but not before current_pos
                before_candidates = [e for e in day_unused if e.end_seconds <= custom_start and e.end_seconds >= current_pos]
                # Only entries that START at/after custom_start and end within threshold (clean snap forward)
                close_after = [e for e in day_unused if e.start_seconds >= custom_start and e.end_seconds < custom_start + THRESHOLD_AFTER]
                # Overlapping entries that span custom_start — just remove them
                overlapping = [e for e in day_unused if e.start_seconds < custom_start and e.end_seconds > custom_start]

                # Best before = the one ending closest to (but not after) custom_start
                best_before = max(before_candidates, key=lambda e: e.end_seconds) if before_candidates else None
                anchor_candidates = ([best_before] if best_before else []) + close_after

                if best_before:
                    best_before_str = f"{best_before.end_seconds//3600%24:02d}:{(best_before.end_seconds%3600)//60:02d}:{best_before.end_seconds%60:02d}"
                else:
                    best_before_str = 'none'
                logger.debug(f"[APPROX day={day_offset+1}] tag='{ct.name}' wanted={custom_start//3600%24:02d}:{(custom_start%3600)//60:02d}:{custom_start%60:02d} current_pos={current_pos//3600%24:02d}:{(current_pos%3600)//60:02d}:{current_pos%60:02d} day_unused={len(day_unused)} before={len(before_candidates)} close_after={len(close_after)} overlapping={len(overlapping)} best_before={best_before_str}")

                if anchor_candidates:
                    best_rand = None
                    best_gap = float('inf')
                    best_idx = -1

                    for rand_e in anchor_candidates:
                        gap = abs(rand_e.end_seconds - custom_start)
                        if gap < best_gap:
                            best_gap = gap
                            best_rand = rand_e
                            for idx, re in enumerate(day_entries):
                                if re is rand_e and idx not in used_day:
                                    best_idx = idx
                                    break

                    if best_rand and best_idx >= 0:
                        logger.debug(f"[APPROX day={day_offset+1}]   BEST end={best_rand.end_seconds//3600%24:02d}:{(best_rand.end_seconds%3600)//60:02d}:{best_rand.end_seconds%60:02d} gap={best_gap} -> tag at {best_rand.end_seconds//3600%24:02d}:{(best_rand.end_seconds%3600)//60:02d}:{best_rand.end_seconds%60:02d}")
                        # Add the random entry to final before placing custom tag
                        if current_pos <= best_rand.start_seconds:
                            final.append(best_rand)
                            used_day.add(best_idx)
                            if best_rand in day_unused:
                                day_unused.remove(best_rand)
                            current_pos = best_rand.end_seconds
                        elif current_pos < best_rand.end_seconds:
                            if overlap_strategy == 'fragment':
                                final.append(ScheduleEntry(1, current_pos, best_rand.end_seconds, best_rand.video_name, FRAGMENT_TAG_TYPE))
                            used_day.add(best_idx)
                            if best_rand in day_unused:
                                day_unused.remove(best_rand)
                            if overlap_strategy == 'fragment':
                                current_pos = best_rand.end_seconds
                        else:
                            used_day.add(best_idx)
                            if best_rand in day_unused:
                                day_unused.remove(best_rand)

                        slot_start = best_rand.end_seconds
                        slot_end = slot_start + (orig_end - orig_start)

                        actual_end = self._place_tag_videos(ct, slot_start, slot_end, final, day_offset)
                        current_pos = actual_end
                        scheduled_slots.append((slot_start, actual_end))
                        logger.debug(f"[APPROX day={day_offset+1}]   placed -> current_pos={current_pos//3600%24:02d}:{(current_pos%3600)//60:02d}:{current_pos%60:02d}")

                        # Consume overlapping random entry tails
                        current_pos = self._consume_overlapping_tail(
                            slot_start, slot_end, current_pos, day_unused, day_entries, used_day, final, day_offset,
                            min_end_threshold=slot_start,
                            scheduled_slots=scheduled_slots,
                        )
                else:
                    logger.debug(f"[APPROX day={day_offset+1}]   no best_rand -> fallback {custom_start//3600%24:02d}:{(custom_start%3600)//60:02d}:{custom_start%60:02d}")
                    # No valid anchor found, place at current_pos if past custom_start
                    if custom_start < current_pos:
                        custom_start = current_pos
                        custom_end = custom_start + (orig_end - orig_start)
                    slot_start = custom_start
                    slot_end = custom_end

                    actual_end = self._place_tag_videos(ct, slot_start, slot_end, final, day_offset)
                    current_pos = actual_end
                    scheduled_slots.append((slot_start, actual_end))
                    logger.debug(f"[APPROX day={day_offset+1}]   placed -> current_pos={current_pos//3600%24:02d}:{(current_pos%3600)//60:02d}:{current_pos%60:02d}")

                    # Consume overlapping random entry tails
                    current_pos = self._consume_overlapping_tail(
                        slot_start, slot_end, current_pos, day_unused, day_entries, used_day, final, day_offset,
                        min_end_threshold=slot_start,
                        scheduled_slots=scheduled_slots,
                        label="fallback",
                    )
            # Next custom tag iteration continues here

            # Add unused random entries from day_start to current_pos
            day_unused = [e for i, e in enumerate(day_entries)
                          if i not in used_day
                          and e.start_seconds < day_end
                          and e.end_seconds > day_start]
            day_unused.sort(key=lambda e: e.start_seconds)
            logger.debug(f"[APPROX day={day_offset+1}] POST-TAGS current_pos={current_pos//3600%24:02d}:{(current_pos%3600)//60:02d}:{current_pos%60:02d} day_unused={len(day_unused)}")
            for e in day_unused:
                logger.debug(f"[APPROX day={day_offset+1}]   unused: {e.start_seconds//3600%24:02d}:{(e.start_seconds%3600)//60:02d}:{e.start_seconds%60:02d}-{e.end_seconds//3600%24:02d}:{(e.end_seconds%3600)//60:02d}:{e.end_seconds%60:02d}")

            # Build occupied ranges from already-placed entries this day
            occupied_ranges = [(e.start_seconds, e.end_seconds) for e in final if e.start_seconds >= day_start]
            occupied_ranges.extend(scheduled_slots)
            # DEBUG: Log occupied ranges summary
            logger.debug(f"[APPROX day={day_offset+1}] OCCUPIED RANGES count={len(occupied_ranges)}")
            for i, (os, oe) in enumerate(occupied_ranges):
                logger.debug(f"[APPROX day={day_offset+1}]   occ[{i}]: {os//3600%24:02d}:{(os%3600)//60:02d}:{os%60:02d} - {oe//3600%24:02d}:{(oe%3600)//60:02d}:{oe%60:02d}")

            for rand_e in day_unused:
                if rand_e.start_seconds >= current_pos:
                    continue
                # Skip if this entry overlaps any already-placed entry
                overlaps = any(rand_e.start_seconds < occ_end and rand_e.end_seconds > occ_start
                               for occ_start, occ_end in occupied_ranges)
                if not overlaps:  # DEBUG: print when NOT overlapping
                    logger.debug(f"[APPROX day={day_offset+1}]   APPROVING {rand_e.start_seconds//3600%24:02d}:{(rand_e.start_seconds%3600)//60:02d}:{rand_e.start_seconds%60:02d}-{rand_e.end_seconds//3600%24:02d}:{(rand_e.end_seconds%3600)//60:02d}:{rand_e.end_seconds%60:02d} -> no overlap, current_pos={current_pos//3600%24:02d}:{(current_pos%3600)//60:02d}:{current_pos%60:02d}")
                if overlaps:
                    logger.debug(f"[APPROX day={day_offset+1}]   SKIPPING {rand_e.start_seconds//3600%24:02d}:{(rand_e.start_seconds%3600)//60:02d}:{rand_e.start_seconds%60:02d}-{rand_e.end_seconds//3600%24:02d}:{(rand_e.end_seconds%3600)//60:02d}:{rand_e.end_seconds%60:02d} due to overlap, current_pos={current_pos//3600%24:02d}:{(current_pos%3600)//60:02d}:{current_pos%60:02d}")
                    continue
                if rand_e.end_seconds <= current_pos:
                    final.append(rand_e)
                    occupied_ranges.append((rand_e.start_seconds, rand_e.end_seconds))
                    for idx, re in enumerate(day_entries):
                        if re is rand_e and idx not in used_day:
                            used_day.add(idx)
                            break
                    current_pos = rand_e.end_seconds
                elif rand_e.start_seconds < current_pos < rand_e.end_seconds:
                    dur = rand_e.end_seconds - current_pos
                    if dur > 0:
                        if overlap_strategy == 'fragment':
                            final.append(ScheduleEntry(1, current_pos, rand_e.end_seconds, rand_e.video_name, FRAGMENT_TAG_TYPE))
                        for idx, re in enumerate(day_entries):
                            if re is rand_e and idx not in used_day:
                                used_day.add(idx)
                                break
                        if overlap_strategy == 'fragment':
                            current_pos = rand_e.end_seconds

            # Add remaining unused random entries
            day_unused2 = [e for i, e in enumerate(day_entries)
                           if i not in used_day
                           and e.start_seconds < day_end
                           and e.end_seconds > day_start]
            day_unused2.sort(key=lambda e: e.start_seconds)

            for rand_e in day_unused2:
                if rand_e.start_seconds >= current_pos:
                    # Check if this entry would overlap any scheduled tag slot
                    if not any(rand_e.start_seconds < slot_end and rand_e.end_seconds > slot_start
                               for slot_start, slot_end in scheduled_slots):
                        final.append(rand_e)
                        for idx, re in enumerate(day_entries):
                            if re is rand_e and idx not in used_day:
                                used_day.add(idx)
                                break
                        current_pos = rand_e.end_seconds

            # Fill remaining intra-day gaps with videos from the pool
            if overlap_strategy == 'compact' and rf_videos:
                blocked = sorted(
                    [(e.start_seconds, e.end_seconds) for e in final
                     if e.start_seconds < day_end and e.end_seconds > day_start],
                    key=lambda x: x[0]
                )
                merged = []
                for start, end in blocked:
                    if merged and start <= merged[-1][1]:
                        merged[-1] = (merged[-1][0], max(merged[-1][1], end))
                    else:
                        merged.append((start, end))
                gap_pos = day_start
                while gap_pos < day_end:
                    in_blocked = False
                    for ms, me in merged:
                        if ms <= gap_pos < me:
                            gap_pos = me
                            in_blocked = True
                            break
                    if in_blocked:
                        continue
                    nearest_stop = day_end
                    for ms, me in merged:
                        if gap_pos < me and ms > gap_pos:
                            nearest_stop = min(nearest_stop, ms)
                    space = nearest_stop - gap_pos
                    if space <= 0:
                        break
                    placed = False
                    for _ in range(len(rf_videos)):
                        idx = self._gap_video_idx % len(rf_videos)
                        video = rf_videos[idx]
                        dur = int(video.get('duration', 90))
                        if dur < 1:
                            dur = 90
                        if dur <= space:
                            self._gap_video_idx += 1
                            video_name = get_video_display_name(video)
                            name = f"{rf_name} - {video_name}" if rf_name else video_name
                            e = ScheduleEntry(1, gap_pos, gap_pos + dur, name)
                            e.problem = "gap"
                            final.append(e)
                            gap_pos += dur
                            placed = True
                            break
                        self._gap_video_idx += 1
                    if not placed:
                        if space > 2:
                            gap_pos = nearest_stop
                        else:
                            break

            # Sync per-day usage back to global tracking
            for local_idx in used_day:
                used_random.add(day_to_global[local_idx])

            # Track last entry end and carryover for next day's gap calculation
            if final:
                last_on_day = max((e for e in final if e.start_seconds >= day_start),
                                  key=lambda e: e.end_seconds, default=None)
                if last_on_day:
                    self._prev_day_last_end = last_on_day.end_seconds
                    if overlap_strategy == 'compact' and last_on_day.end_seconds > day_end:
                        self._compact_carryover = max(self._compact_carryover,
                                                       last_on_day.end_seconds - day_end)

        final.sort(key=lambda e: e.start_seconds)

        return final

    def _apply_approximate_linear(self, num_days: int, custom_tags: list, series_tags: list, multi_series_tags: list, random_fill_tags: list, has_24h_fill: bool) -> List[ScheduleEntry]:
        """Linear placement: Truncate random fill to make room for custom/multi-series tags."""
        # Tags are provided by caller; no need to recompute.

        rf_24h_tags = [t for t in random_fill_tags if getattr(t, 'fill_24h', False)]

        if rf_24h_tags and not custom_tags and not series_tags and not multi_series_tags:
            return self.generate_random_fill(24 * 3600 * num_days)

        has_24h_fill = bool(rf_24h_tags)

        if has_24h_fill:
            base_entries = []
        else:
            base_entries = self.generate_random_fill(24 * 3600) if (custom_tags or series_tags or multi_series_tags) else []

        if not custom_tags and not series_tags and not multi_series_tags and not random_fill_tags:
            return base_entries

        # Sort tags by start time for chronological processing
        custom_sorted = sorted(custom_tags, key=lambda t: qtime_to_seconds(t.start_time))
        series_sorted = sorted(series_tags, key=lambda t: qtime_to_seconds(t.start_time))
        multi_sorted = sorted(multi_series_tags, key=lambda t: qtime_to_seconds(t.start_time))

        scheduled_ranges = []
        for ct in custom_sorted:
            scheduled_ranges.append(normalize_tag_time_range(ct))
        for st in series_sorted:
            scheduled_ranges.append(normalize_tag_time_range(st))
        for mst in multi_sorted:
            scheduled_ranges.append(normalize_tag_time_range(mst))

        for rf in random_fill_tags:
            rf_fill_24h = getattr(rf, 'fill_24h', False)
            if not rf_fill_24h:
                rf_start = qtime_to_seconds(rf.start_time)
                rf_end = qtime_to_seconds(rf.end_time)
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

        custom_sorted = sorted(custom_tags, key=lambda t: qtime_to_seconds(t.start_time))
        series_sorted = sorted(series_tags, key=lambda t: qtime_to_seconds(t.start_time))
        multi_sorted = sorted(multi_series_tags, key=lambda t: qtime_to_seconds(t.start_time))

        if not has_24h_fill:
            for day_offset in range(num_days):
                day_offset_seconds = day_offset * 24 * 3600
                for ct in custom_sorted:
                    if not self._is_tag_active_on_day(ct, day_offset):
                        continue
                    original_start, original_end = normalize_tag_time_range(ct)

                    next_custom_within_day = next_custom_pos - day_offset_seconds
                    custom_start = max(original_start, next_custom_within_day) + day_offset_seconds
                    custom_end = custom_start + (original_end - original_start)

                    if ct.collection_videos:
                        for s in range(custom_start, custom_end):
                            occupied.add(s)
                        video_count = getattr(ct, 'video_count', 1)
                        videos = self._get_videos_for_day(ct.collection_videos, day_offset)
                        if getattr(ct, 'randomize_videos', False):
                            random.shuffle(videos)
                        pos = custom_start
                        vid_idx = 0
                        actual_end = custom_start
                        while pos <= custom_end and vid_idx < video_count and vid_idx < len(videos):
                            video = videos[vid_idx % len(videos)]
                            video_name = get_video_display_name(video)
                            duration = int(video.get('duration', 90))
                            if duration < 1:
                                duration = 90
                            if pos + duration > custom_end:
                                custom_end = pos + duration
                            final.append(self._create_video_entry(pos, duration, video_name, ct.name, "custom"))
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
                while rand_idx < len(base_entries) and base_entries[rand_idx].start_seconds < current_pos:
                    rand_idx += 1
        else:
            # Process custom tags for 24h fill mode
            for day_offset in range(num_days):
                day_offset_seconds = day_offset * 24 * 3600
                for ct in custom_sorted:
                    if not self._is_tag_active_on_day(ct, day_offset):
                        continue
                    original_start, original_end = normalize_tag_time_range(ct)

                    custom_start = original_start + day_offset_seconds
                    custom_end = original_end + day_offset_seconds

                    if ct.collection_videos:
                        for s in range(custom_start, custom_end):
                            occupied.add(s)
                        video_count = getattr(ct, 'video_count', 1)
                        # Use day-aware video selection
                        videos = self._get_videos_for_day(ct.collection_videos, day_offset)
                        if getattr(ct, 'randomize_videos', False):
                            random.shuffle(videos)
                        pos = custom_start
                        vid_idx = 0
                        actual_end = custom_start
                    while pos <= custom_end and vid_idx < video_count and vid_idx < len(videos):
                        video = videos[vid_idx % len(videos)]
                        video_name = get_video_display_name(video)
                        duration = int(video.get('duration', 90))
                        if duration < 1:
                            duration = 90
                        if pos + duration > custom_end:
                            custom_end = pos + duration
                        final.append(self._create_video_entry(pos, duration, video_name, ct.name, "custom"))
                        actual_end = pos + duration
                        pos += duration
                        vid_idx += 1
                        actual_placed_ranges.append((custom_start, custom_end))
                    else:
                        final.append(ScheduleEntry(1, custom_start, custom_end, ct.name))
                        actual_placed_ranges.append((custom_start, custom_end))

        # Series tags processing (outside if/else to handle both cases)
        for day_offset in range(num_days):
            day_offset_seconds = day_offset * 24 * 3600
            for st in series_sorted:
                if not self._is_tag_active_on_day(st, day_offset):
                    continue
                original_start, original_end = normalize_tag_time_range(st)

                # next_custom_pos is in absolute seconds; normalize to
                # within-day offset so a previous day's extended end time
                # doesn't cascade into the next day's start time.
                next_custom_within_day = next_custom_pos - day_offset_seconds
                series_start = max(original_start, next_custom_within_day) + day_offset_seconds
                series_end = series_start + (original_end - original_start)

                if st.collection_videos:
                    for s in range(series_start, series_end):
                        occupied.add(s)

                    videos_to_use = self._select_series_videos(st, day_offset)

                    pos = series_start
                    actual_end = series_start
                    for v in videos_to_use:
                        video = v['video']
                        video_name = get_video_display_name(video)
                        duration = int(video.get('duration', 90))
                        if duration < 1:
                            duration = 90
                        if pos + duration > series_end:
                            series_end = pos + duration
                        final.append(self._create_video_entry(pos, duration, video_name, st.name, "series"))
                        actual_end = pos + duration
                        pos += duration
                    current_pos = actual_end
                    next_custom_pos = actual_end
                    if has_24h_fill:
                        actual_placed_ranges.append((series_start, series_end))
                else:
                    final.append(ScheduleEntry(1, series_start, series_end, st.name, "series"))
                    actual_placed_ranges.append((series_start, series_end))
                    actual_end = series_end
                    current_pos = actual_end
                    next_custom_pos = actual_end

        # Multi-Series tags processing
        for day_offset in range(num_days):
            day_offset_seconds = day_offset * 24 * 3600
            for mst in multi_sorted:
                if not self._is_tag_active_on_day(mst, day_offset):
                    continue
                original_start, original_end = normalize_tag_time_range(mst)

                mst_start = max(original_start, next_custom_pos) + day_offset_seconds
                mst_end = mst_start + (original_end - original_start)

                start_offset = mst_start - original_start
                actual_end = self._process_multi_series_tag(mst, final, occupied, day_offset, start_offset)
                current_pos = actual_end
                next_custom_pos = actual_end
                if has_24h_fill:
                    actual_placed_ranges.append((mst_start, mst_end))

        rf_sorted = sorted(random_fill_tags, key=lambda t: qtime_to_seconds(t.start_time))

        if not has_24h_fill:
            rf_start = qtime_to_seconds(rf_sorted[0].start_time) if rf_sorted else 0
            rf_end = qtime_to_seconds(rf_sorted[0].end_time) if rf_sorted else 24 * 3600

            rf_videos = rf_sorted[0].collection_videos.copy() if rf_sorted and rf_sorted[0].collection_videos else []
            if rf_videos:
                random.shuffle(rf_videos)

            if rf_videos:
                total_seconds = num_days * 24 * 3600
                final.extend(self._build_random_entries(rf_videos, rf_start, total_seconds, rf_sorted[0].name if rf_sorted else ""))
        else:
            for day_offset in range(num_days):
                day_offset_seconds = day_offset * 24 * 3600
                for rf in rf_sorted:
                    ranges_to_use = merged_ranges
                    self._process_random_fill_tag(rf, final, ranges_to_use, 0, day_offset_seconds)

        if len(final) == 0 and not has_24h_fill:
            while current_pos < 24 * 3600 * num_days and rand_idx < len(base_entries):
                dur = min(90, base_entries[rand_idx].end_seconds - base_entries[rand_idx].start_seconds)
                final.append(ScheduleEntry(1, current_pos, current_pos + dur, base_entries[rand_idx].video_name))
                current_pos += dur
                rand_idx += 1

        final.sort(key=lambda e: e.start_seconds)

        unique_entries = []
        seen_times = set()
        for entry in final:
            key = (entry.start_seconds, entry.end_seconds)
            if key not in seen_times:
                seen_times.add(key)
                unique_entries.append(entry)

        return unique_entries
