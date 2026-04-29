#!/usr/bin/env python3
from __future__ import annotations
import random
from typing import List, Optional
from PySide6.QtCore import QTime

from utils import (
    qtime_to_minutes, get_video_display_name, parse_videos_for_series
)


class Tag:
    def __init__(self, tag_type: str, name: str = "Random Fill",
                 start_time: Optional[QTime] = None,
                 end_time: Optional[QTime] = None,
                 collection_videos: Optional[List[dict]] = None,
                 collection_path: str = "",
                 randomize_videos: bool = False,
                 video_count: int = 1,
                 is_random_fill: bool = False,
                 blacklist: List[dict] = None,
                 blacklist_path: str = "",
                 is_series: bool = False,
                 start_season: int = 1,
                 start_episode: int = 1,
                 play_mode: str = "sequence",
                 fill_24h: bool = False,
                 collection_profile: str = "",
                 blacklist_profile: str = ""):
        self.tag_type = tag_type
        self.name = name
        self.start_time = start_time or QTime(0, 0)
        self.end_time = end_time or QTime(0, 0)
        self.is_random_fill = is_random_fill
        self.collection_videos = collection_videos or []
        self.collection_path = collection_path
        self.randomize_videos = randomize_videos
        self.video_count = video_count
        self.blacklist = blacklist or []
        self.blacklist_path = blacklist_path
        self.is_series = is_series
        self.start_season = start_season
        self.start_episode = start_episode
        self.play_mode = play_mode
        self.fill_24h = fill_24h
        self.collection_profile = collection_profile
        self.blacklist_profile = blacklist_profile

    def to_display_string(self) -> str:
        if self.tag_type == "random" or self.is_random_fill:
            fill_24h = getattr(self, 'fill_24h', False)
            collection_profile = getattr(self, 'collection_profile', '')
            blacklist_profile = getattr(self, 'blacklist_profile', '')
            profile_info = []
            if collection_profile:
                profile_info.append(f"col:{collection_profile}")
            if blacklist_profile:
                profile_info.append(f"blk:{blacklist_profile}")
            profile_str = f" ({', '.join(profile_info)})" if profile_info else ""
            if fill_24h:
                return f"[R] {self.name} (24h Fill){profile_str}"
            return f"[R] {self.name} ({self.start_time.toString('HH:mm')}-{self.end_time.toString('HH:mm')}){profile_str}"
        if self.is_series:
            collection_profile = getattr(self, 'collection_profile', '')
            blacklist_profile = getattr(self, 'blacklist_profile', '')
            profile_info = []
            if collection_profile:
                profile_info.append(f"col:{collection_profile}")
            if blacklist_profile:
                profile_info.append(f"blk:{blacklist_profile}")
            profile_str = f" ({', '.join(profile_info)})" if profile_info else ""
            return f"[S] {self.name} ({self.start_time.toString('HH:mm')}-{self.end_time.toString('HH:mm')}){profile_str}"
        if self.randomize_videos:
            return f"[C] {self.name} ({self.start_time.toString('HH:mm')}-{self.end_time.toString('HH:mm')}) x{self.video_count}"
        return f"[C] {self.name} ({self.start_time.toString('HH:mm')}-{self.end_time.toString('HH:mm')})"


class MultiSeriesTag(Tag):
    """Tag that combines multiple series into one contiguous block."""
    def __init__(self, name: str = "Multi-Series",
                 series_list: List[dict] = None,
                 start_time: Optional[QTime] = None,
                 end_time: Optional[QTime] = None):
        super().__init__(
            tag_type="multi_series",
            name=name,
            start_time=start_time or QTime(0, 0),
            end_time=end_time or QTime(0, 0)
        )
        self.series_list = series_list or []
        self.is_multi_series = True

    def to_display_string(self) -> str:
        base = f"[M] {self.name}"
        if self.series_list:
            total_series = len(self.series_list)
            base += f" ({total_series} series)"
        if self.start_time and self.end_time:
            base += f" ({self.start_time.toString('HH:mm')}-{self.end_time.toString('HH:mm')})"
        return base

    def calculate_schedule(self, start_time_minutes: int) -> List[ScheduleEntry]:
        """Calculate contiguous episode schedule starting at given minute offset.
        Returns list of ScheduleEntry objects with day=1 (absolute minutes)."""
        entries = []
        pos = start_time_minutes

        for series_config in self.series_list:
            collection_videos = series_config.get('collection_videos', [])
            start_season = series_config.get('start_season', 1)
            start_episode = series_config.get('start_episode', 1)
            play_mode = series_config.get('play_mode', 'sequence')
            video_count = series_config.get('video_count', 1)
            series_name = series_config.get('name', 'Series')

            if not collection_videos:
                # Add placeholder entry
                entries.append(self._create_video_entry(pos, 60, series_name, self.name))
                pos += 60
                continue

            videos_to_use, _ = parse_videos_for_series(
                collection_videos,
                start_season,
                start_episode,
                play_mode,
                video_count
            )

            for v in videos_to_use:
                video = v['video']
                video_name = get_video_display_name(video)
                duration = int(video.get('duration', 90)) // 60
                if duration < 1:
                    duration = 1
                entries.append(self._create_video_entry(pos, duration, video_name, series_name))
                pos += duration

        return entries

    def _create_video_entry(self, pos: int, duration: int, name: str, tag_name: str = "") -> ScheduleEntry:
        video_name = f"{tag_name} - {name}" if tag_name else name
        return ScheduleEntry(1, pos, pos + duration, video_name)

    def calculate_total_duration(self) -> int:
        """Calculate total duration in minutes for all series episodes."""
        total = 0
        for series_config in self.series_list:
            collection_videos = series_config.get('collection_videos', [])
            start_season = series_config.get('start_season', 1)
            start_episode = series_config.get('start_episode', 1)
            play_mode = series_config.get('play_mode', 'sequence')
            video_count = series_config.get('video_count', 1)

            if not collection_videos:
                total += 60
                continue

            videos_to_use, _ = parse_videos_for_series(
                collection_videos,
                start_season,
                start_episode,
                play_mode,
                video_count
            )

            for v in videos_to_use:
                video = v['video']
                duration = int(video.get('duration', 90)) // 60
                if duration < 1:
                    duration = 1
                total += duration

        return total


class ScheduleEntry:
    def __init__(self, day: int, start_minutes: int, end_minutes: int, video_name: str):
        self.day = day
        self.start_minutes = start_minutes
        self.end_minutes = end_minutes
        self.video_name = video_name

    def format_time(self, minutes: int, day: int) -> str:
        hours = (minutes // 60) % 24
        mins = minutes % 60
        return f"Day {day}\n{hours:02d}:{mins:02d}"

    def to_display_string(self) -> str:
        start_day = (self.start_minutes // (24 * 60)) + 1
        end_day = (self.end_minutes // (24 * 60)) + 1
        start_h = (self.start_minutes // 60) % 24
        start_m = self.start_minutes % 60
        end_h = (self.end_minutes // 60) % 24
        end_m = self.end_minutes % 60
        if self.start_minutes < 24 * 60:
            return f"Day {start_day}\n{start_h:02d}:{start_m:02d} - {end_h:02d}:{end_m:02d} - {self.video_name}"
        elif start_day == end_day:
            return f"Day {start_day}\n{start_h:02d}:{start_m:02d} - {end_h:02d}:{end_m:02d} - {self.video_name}"
        else:
            return f"Day {start_day} {start_h:02d}:{start_m:02d} - Day {end_day} {end_h:02d}:{end_m:02d} - {self.video_name}"

    def to_copy_string(self) -> str:
        start_day = (self.start_minutes // (24 * 60)) + 1
        end_day = (self.end_minutes // (24 * 60)) + 1
        start_h = (self.start_minutes // 60) % 24
        start_m = self.start_minutes % 60
        end_h = (self.end_minutes // 60) % 24
        end_m = self.end_minutes % 60
        if start_day == end_day:
            return f"Day {start_day} {start_h:02d}:{start_m:02d} - {end_h:02d}:{end_m:02d} - {self.video_name}"
        return f"Day {start_day} {start_h:02d}:{start_m:02d} - Day {end_day} {end_h:02d}:{end_m:02d} - {self.video_name}"


class TagManager:
    def __init__(self):
        self.tags: List[Tag] = []
        self._cached_random_entries: Optional[List[ScheduleEntry]] = None

    def get_cached_random_entries(self) -> Optional[List[ScheduleEntry]]:
        return self._cached_random_entries

    def set_cached_random_entries(self, entries: List[ScheduleEntry]):
        self._cached_random_entries = entries

    def clear_cache(self):
        self._cached_random_entries = None

    def save_tags(self, filepath: str = "tags.ini"):
        from serialization import save_tags_to_ini
        save_tags_to_ini(self.tags, filepath)

    def load_tags(self, filepath: str = "tags.ini") -> bool:
        from serialization import load_tags_from_ini
        loaded = load_tags_from_ini(filepath, Tag, QTime.fromString)
        if loaded:
            self.tags = loaded
            return True
        return False

    def add_tag(self, tag: Tag):
        self.tags.append(tag)

    def remove_tag(self, index: int) -> bool:
        if 0 <= index < len(self.tags):
            self.tags.pop(index)
            return True
        return False

    def edit_tag(self, index: int, name: str, start_time: QTime, end_time: QTime,
             collection_videos: List[dict] = None, collection_path: str = "",
             video_count: int = 1, is_series: bool = False,
             start_season: int = 1, start_episode: int = 1, play_mode: str = "sequence",
             is_random_fill: bool = False, blacklist: List[dict] = None,
                    blacklist_path: str = "", fill_24h: bool = False,
                    collection_profile: str = "", blacklist_profile: str = "",
                    randomize_videos: bool = False) -> bool:
        if 0 <= index < len(self.tags):
            t = self.tags[index]
            t.name = name
            t.start_time = start_time
            t.end_time = end_time
            t.collection_videos = collection_videos or []
            t.collection_path = collection_path
            t.video_count = video_count
            t.is_series = is_series
            t.start_season = start_season
            t.start_episode = start_episode
            t.play_mode = play_mode
            t.is_random_fill = is_random_fill
            t.blacklist = blacklist or []
            t.blacklist_path = blacklist_path
            t.fill_24h = fill_24h
            t.collection_profile = collection_profile
            t.blacklist_profile = blacklist_profile
            t.randomize_videos = randomize_videos
            return True
        return False

    def get_custom_tags(self) -> List[Tag]:
        return [t for t in self.tags if t.tag_type == "custom" and not t.is_series]

    def get_series_tags(self) -> List[Tag]:
        return [t for t in self.tags if t.is_series]

    def get_multi_series_tags(self) -> List[Tag]:
        return [t for t in self.tags if getattr(t, 'is_multi_series', False)]

    def get_random_tags(self) -> List[Tag]:
        return [t for t in self.tags if t.tag_type == "random" or t.is_random_fill]

    def get_all_tags(self) -> List[Tag]:
        return list(self.tags)


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
            entries = self.sg.generate_random_fill(24 * 60 * num_days)
            return entries

        occupied = set()
        custom_entries = []
        series_entries = []
        multi_series_entries = []
        fill_entries = []

        for day_offset in range(num_days):
            day_offset_minutes = day_offset * 24 * 60
            for ct in custom_tags:
                self.sg._process_custom_tag(ct, custom_entries, occupied, day_offset_minutes)

            for st in series_tags:
                self.sg._process_series_tag(st, series_entries, occupied, day_offset, day_offset_minutes)

            for mst in multi_series_tags:
                self.sg._process_multi_series_tag(mst, multi_series_entries, occupied, day_offset, day_offset_minutes)

        rf_sorted = sorted(random_fill_tags, key=lambda t: qtime_to_minutes(t.start_time))

        if rf_sorted and any(getattr(rf, 'fill_24h', False) for rf in rf_sorted):
            for day_offset in range(num_days):
                day_offset_minutes = day_offset * 24 * 60
                for rf in rf_sorted:
                    if getattr(rf, 'fill_24h', False):
                        merged = [(e.start_minutes, e.end_minutes) for e in custom_entries + series_entries + multi_series_entries]
                        self.sg._process_random_fill_tag(rf, fill_entries, merged, 0, day_offset_minutes)
        elif rf_sorted:
            rf_start = qtime_to_minutes(rf_sorted[0].start_time)
            rf_videos = rf_sorted[0].collection_videos.copy() if rf_sorted[0].collection_videos else []
            if rf_videos:
                random.shuffle(rf_videos)
            total_minutes = num_days * 24 * 60
            fill_entries.extend(self.sg._build_random_entries(rf_videos, rf_start, total_minutes, rf_sorted[0].name))

        rf_24h_tags = [rf for rf in rf_sorted if getattr(rf, 'fill_24h', False)]
        if fill_entries and rf_24h_tags:
            fill_entries.sort(key=lambda e: e.start_minutes)
            total_duration = sum(e.end_minutes - e.start_minutes for e in fill_entries)
            rf_videos = rf_sorted[0].collection_videos.copy() if rf_sorted else []
            if rf_videos:
                total_mins = sum(int(v.get('duration', 90) // 60) for v in rf_videos)
                avg_duration = total_mins // len(rf_videos) if rf_videos else 0
                if avg_duration > 0:
                    start_vid_idx = (total_duration // avg_duration) % len(rf_videos)
                    for day_offset in range(1, num_days):
                        day_offset_minutes = day_offset * 24 * 60
                        for rf in rf_sorted[1:]:
                            merged = [(e.start_minutes, e.end_minutes) for e in custom_entries + series_entries + multi_series_entries]
                            self.sg._process_random_fill_tag(rf, fill_entries, merged, start_vid_idx, day_offset_minutes)

        entries = custom_entries + series_entries + multi_series_entries + fill_entries
        entries.sort(key=lambda e: e.start_minutes)
        return entries

    def inject_into_random(self, random_entries: List[ScheduleEntry]) -> List[ScheduleEntry]:
        """Inject custom tags into existing random entries."""
        custom_tags = self.sg.tag_manager.get_custom_tags()
        if not custom_tags:
            return list(random_entries)

        final = []
        rand_idx = 0
        custom_sorted = sorted(custom_tags, key=lambda t: qtime_to_minutes(t.start_time))

        for ct in custom_sorted:
            start = qtime_to_minutes(ct.start_time)
            end = qtime_to_minutes(ct.end_time)
            if start >= end or start >= 24 * 60:
                continue

            while rand_idx < len(random_entries) and random_entries[rand_idx].end_minutes <= start:
                final.append(random_entries[rand_idx])
                rand_idx += 1

            if rand_idx < len(random_entries) and random_entries[rand_idx].start_minutes < start:
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
                    duration = int(video.get('duration', 90)) // 60
                    if duration < 1:
                        duration = 1
                    duration = min(duration, end - pos)
                    if duration < 1:
                        break
                    final.append(ScheduleEntry(1, pos, pos + duration, video_name))
                    pos += duration
                    vid_idx += 1
            else:
                final.append(ScheduleEntry(1, start, end, ct.name))

            while rand_idx < len(random_entries) and random_entries[rand_idx].start_minutes < end:
                rand_idx += 1

        while rand_idx < len(random_entries):
            final.append(random_entries[rand_idx])
            rand_idx += 1

        final.sort(key=lambda e: e.start_minutes)
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
            return self.sg.generate_random_fill(24 * 60 * num_days)

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
            return self.sg.generate_random_fill(24 * 60 * num_days)

        has_24h_fill = bool(rf_24h_tags)

        if has_24h_fill:
            base_entries = []
        else:
            base_entries = self.sg.generate_random_fill(24 * 60) if (custom_tags or series_tags or multi_series_tags) else []

        if not custom_tags and not series_tags and not multi_series_tags and not random_fill_tags:
            return base_entries

        return self.sg._apply_approximate_linear(num_days, custom_tags, series_tags, multi_series_tags, random_fill_tags, has_24h_fill)


class ScheduleGenerator:
    def __init__(self, tag_manager: TagManager):
        self.tag_manager = tag_manager

    def _create_video_entry(self, pos: int, duration: int, name: str, tag_name: str = "") -> ScheduleEntry:
        video_name = f"{tag_name} - {name}" if tag_name else name
        return ScheduleEntry(1, pos, pos + duration, video_name)

    def _place_tag_videos(self, ct, start: int, end: int, final: List[ScheduleEntry]) -> int:
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
                
                videos_to_use, _ = parse_videos_for_series(
                    collection_videos,
                    start_season,
                    start_episode,
                    play_mode,
                    video_count
                )
                
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
            random.shuffle(videos)
            pos = start
            vid_idx = 0
            while pos < end and vid_idx < video_count and vid_idx < len(videos):
                video = videos[vid_idx % len(videos)]
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

        base_start_episode = getattr(st, 'start_episode', 1)
        video_count = getattr(st, 'video_count', 1)
        raw_episode = base_start_episode + (day_offset * video_count)

        # Wrap episode index so series cycles across days
        if st.collection_videos:
            total_episodes = len(st.collection_videos)
            if total_episodes > 0:
                start_episode = ((raw_episode - 1) % total_episodes) + 1
            else:
                start_episode = raw_episode
        else:
            start_episode = raw_episode

        if st.collection_videos:
            for m in range(start_min, end_min):
                occupied.add(m)

            videos_to_use, _ = parse_videos_for_series(
                st.collection_videos,
                getattr(st, 'start_season', 1),
                start_episode,
                getattr(st, 'play_mode', 'sequence'),
                video_count
            )

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
        if mode == "linear":
            return LinearApproximateStrategy(self).generate(num_days)
        return FindReplaceApproximateStrategy(self).generate(num_days)

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
        label: str = "",
    ) -> int:
        """Consume the portion of a random entry that overlaps the tag slot.

        Finds any random entry in day_unused that intersects [slot_start, slot_end)
        and has end_minutes > min_end_threshold, marks it as used, removes it from
        day_unused, and appends its remaining tail (from current_pos to entry end)
        to final. Returns updated current_pos.

        Args:
            min_end_threshold: entries must have re.end_minutes > this to be processed.
                For anchored placement, use slot_start; for fallback, use current_pos.
            label: optional suffix for debug print (e.g., "fallback").
        """
        for re in day_unused[:]:
            if re.start_minutes < slot_end and re.end_minutes > min_end_threshold:
                for idx, orig_re in enumerate(random_entries):
                    if orig_re is re and idx not in used_random:
                        used_random.add(idx)
                        remaining_start = current_pos
                        remaining_end = re.end_minutes
                        if label:
                            print(f"[APPROX day={day_offset+1}]   remaining portion ({label}): {remaining_start//60%24:02d}:{remaining_start%60:02d}-{remaining_end//60%24:02d}:{remaining_end%60:02d}")
                        else:
                            print(f"[APPROX day={day_offset+1}]   remaining portion: {remaining_start//60%24:02d}:{remaining_start%60:02d}-{remaining_end//60%24:02d}:{remaining_end%60:02d} from re={re.start_minutes//60%24:02d}:{re.start_minutes%60:02d}-{re.end_minutes//60%24:02d}:{re.end_minutes%60:02d}")
                        if remaining_end > remaining_start:
                            final.append(ScheduleEntry(1, remaining_start, remaining_end, re.video_name))
                            current_pos = remaining_end
                        if re in day_unused:
                            day_unused.remove(re)
                        break
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
            
            # Track scheduled slots for full occupied ranges
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

                print(f"[APPROX day={day_offset+1}] tag='{ct.name}' wanted={custom_start//60%24:02d}:{custom_start%60:02d} current_pos={current_pos//60%24:02d}:{current_pos%60:02d} day_unused={len(day_unused)} before={len(before_candidates)} close_after={len(close_after)} overlapping={len(overlapping)} best_before={'%02d:%02d'%(best_before.end_minutes//60%24,best_before.end_minutes%60) if best_before else 'none'}")

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
                        print(f"[APPROX day={day_offset+1}]   BEST end={best_rand.end_minutes//60%24:02d}:{best_rand.end_minutes%60:02d} gap={best_gap} -> tag at {best_rand.end_minutes//60%24:02d}:{best_rand.end_minutes%60:02d}")
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
                        
                        # Reserve the full slot
                        scheduled_slots.append((slot_start, slot_end))
                        actual_end = self._place_tag_videos(ct, slot_start, slot_end, final)
                        current_pos = actual_end
                        print(f"[APPROX day={day_offset+1}]   placed -> current_pos={current_pos//60%24:02d}:{current_pos%60:02d}")

                        # Consume overlapping random entry tails
                        current_pos = self._consume_overlapping_tail(
                            slot_start, slot_end, current_pos, day_unused, random_entries, used_random, final, day_offset,
                            min_end_threshold=slot_start,
                        )
                else:
                    print(f"[APPROX day={day_offset+1}]   no best_rand -> fallback {custom_start//60%24:02d}:{custom_start%60:02d}")
                    # No valid anchor found, place at current_pos if past custom_start
                    if custom_start < current_pos:
                        custom_start = current_pos
                        custom_end = custom_start + (orig_end - orig_start)
                    slot_start = custom_start
                    slot_end = custom_end
                    
                    # Reserve the full slot
                    scheduled_slots.append((slot_start, slot_end))
                    actual_end = self._place_tag_videos(ct, slot_start, slot_end, final)
                    current_pos = actual_end
                    print(f"[APPROX day={day_offset+1}]   placed -> current_pos={current_pos//60%24:02d}:{current_pos%60:02d}")

                    # Consume overlapping random entry tails
                    current_pos = self._consume_overlapping_tail(
                        slot_start, slot_end, current_pos, day_unused, random_entries, used_random, final, day_offset,
                        min_end_threshold=current_pos,
                        label="fallback",
                    )
            # Next custom tag iteration continues here
            
            # Add unused random entries from day_start to current_pos
            day_unused = [e for i, e in enumerate(random_entries) 
                              if i not in used_random 
                              and e.start_minutes < day_end 
                              and e.end_minutes > day_start]
            day_unused.sort(key=lambda e: e.start_minutes)
            print(f"[APPROX day={day_offset+1}] POST-TAGS current_pos={current_pos//60%24:02d}:{current_pos%60:02d} day_unused={len(day_unused)}")
            for e in day_unused:
                print(f"[APPROX day={day_offset+1}]   unused: {e.start_minutes//60%24:02d}:{e.start_minutes%60:02d}-{e.end_minutes//60%24:02d}:{e.end_minutes%60:02d}")

            # Build occupied ranges from already-placed entries this day
            occupied_ranges = [(e.start_minutes, e.end_minutes) for e in final if e.start_minutes >= day_start]
            occupied_ranges.extend(scheduled_slots)

            for rand_e in day_unused:
                if rand_e.start_minutes >= current_pos:
                    continue
                # Skip if this entry overlaps any already-placed entry
                if any(rand_e.start_minutes < occ_end and rand_e.end_minutes > occ_start
                       for occ_start, occ_end in occupied_ranges):
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

        scheduled_ranges = []
        for ct in custom_tags:
            scheduled_ranges.append((qtime_to_minutes(ct.start_time), qtime_to_minutes(ct.end_time)))
        
        for st in series_tags:
            scheduled_ranges.append((qtime_to_minutes(st.start_time), qtime_to_minutes(st.end_time)))
        for mst in multi_series_tags:
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
                            actual_placed_ranges.append((custom_start, actual_end))
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
                        actual_placed_ranges.append((custom_start, actual_end))
                    else:
                        final.append(ScheduleEntry(1, custom_start, custom_end, ct.name))
                        actual_placed_ranges.append((custom_start, custom_end))

        # Series tags processing (outside if/else to handle both cases)
        for day_offset in range(num_days):
            day_offset_minutes = day_offset * 24 * 60
            for st in series_tags:
                original_start = qtime_to_minutes(st.start_time)
                original_end = qtime_to_minutes(st.end_time)
                if original_start >= original_end:
                    continue

                series_start = max(original_start, next_custom_pos) + day_offset_minutes
                series_end = series_start + (original_end - original_start)

                base_start_episode = getattr(st, 'start_episode', 1)
                video_count = getattr(st, 'video_count', 1)
                start_episode = base_start_episode + (day_offset * video_count)

                videos_to_use = []
                if st.collection_videos:
                    for m in range(series_start, series_end):
                        occupied.add(m)

                    videos_to_use, _ = parse_videos_for_series(
                        st.collection_videos,
                        getattr(st, 'start_season', 1),
                        start_episode,
                        getattr(st, 'play_mode', 'sequence'),
                        video_count
                    )
                    
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
                        actual_placed_ranges.append((series_start, actual_end))
                else:
                    final.append(ScheduleEntry(1, series_start, series_end, st.name))
                    actual_placed_ranges.append((series_start, series_end))
                    actual_end = series_end
                    current_pos = actual_end
                    next_custom_pos = actual_end

        # Multi-Series tags processing
        for day_offset in range(num_days):
            day_offset_minutes = day_offset * 24 * 60
            for mst in multi_series_tags:
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
                    actual_placed_ranges.append((mst_start, actual_end))

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
                    ranges_to_use = actual_placed_ranges if actual_placed_ranges else merged_ranges
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