#!/usr/bin/env python3
"""Data models for the daypart scheduler.

This module contains pure data structures: Tag, MultiSeriesTag, ScheduleEntry,
and TagManager. No scheduling algorithms are defined here.
"""

from __future__ import annotations
import logging
from typing import List, Optional
from PySide6.QtCore import QTime
from PySide6.QtGui import QColor

from utils import (
    get_video_display_name,
    parse_videos_for_series,
    filter_videos_by_blacklist,
    parse_series_episode,
)

logger = logging.getLogger(__name__)


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
                  blacklist_profile: str = "",
                   series_end_behavior: str = "stop",
                   series_repeat_season: int = 0,
                   series_random_season: int = 0,
                   active_days: Optional[List[int]] = None,
                   marathon_mode: bool = False,
                   marathon_tag_name: str = ""):
        self.tag_type = tag_type
        self.name = name
        self.start_time = start_time or QTime(0, 0)
        self.end_time = end_time or QTime(0, 0)
        self.is_random_fill = is_random_fill
        self.marathon_mode = marathon_mode
        self.marathon_tag_name = marathon_tag_name
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
        self.series_end_behavior = series_end_behavior
        self.series_repeat_season = series_repeat_season
        self.series_random_season = series_random_season
        self.active_days = active_days
        
        # Apply blacklist filtering if both collection_videos and blacklist are present
        if self.collection_videos and self.blacklist:
            self.collection_videos = filter_videos_by_blacklist(self.collection_videos, self.blacklist)

        # Precompute season grouping for series tags with season metadata
        if self.is_series and self.collection_videos:
            self._season_groups = {}          # season -> list[video] sorted by episode
            self._sorted_seasons = []         # ascending list of seasons
            self._season_episode_counts = {}  # season -> count
            self._has_season_tags = False
            self._derived_series_name = None

            # Build groups by extracting season from video metadata
            for vid in self.collection_videos:
                season = vid.get('_meta_season')
                if season is None:
                    continue
                self._has_season_tags = True
                self._season_groups.setdefault(season, []).append(vid)

            if self._has_season_tags:
                # Sort videos within each season by episode (parse from path)
                for s, vlist in self._season_groups.items():
                    for v in vlist:
                        _, ep = parse_series_episode(v.get('path', ''))
                        v['_parsed_episode'] = ep
                    vlist.sort(key=lambda v: v['_parsed_episode'])
                    self._season_episode_counts[s] = len(vlist)

                self._sorted_seasons = sorted(self._season_groups.keys())

                # Derive series name if meta_series consistent across all videos
                series_names = {vid.get('_meta_series') for vid in self.collection_videos if vid.get('_meta_series')}
                if len(series_names) == 1:
                    self._derived_series_name = next(iter(series_names))

                # Store flat ordered list (season order, then episode order)
                self._flat_ordered = [v for s in self._sorted_seasons for v in self._season_groups[s]]

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

    @property
    def tag_color(self) -> Optional[QColor]:
        if self.tag_type == "random" or self.is_random_fill:
            return None
        if self.is_series or getattr(self, 'is_multi_series', False):
            return QColor("#7c3aed")
        if self.randomize_videos or self.tag_type == "custom":
            return QColor("#059669")
        return None


class MultiSeriesTag(Tag):
    """Tag that combines multiple series into one contiguous block."""
    def __init__(self, name: str = "Multi-Series",
                 series_list: List[dict] = None,
                 start_time: Optional[QTime] = None,
                 end_time: Optional[QTime] = None,
                 blacklist: List[dict] = None,
                 blacklist_profile: str = "",
                 active_days: Optional[List[int]] = None):
        super().__init__(
            tag_type="multi_series",
            name=name,
            start_time=start_time or QTime(0, 0),
            end_time=end_time or QTime(0, 0),
            blacklist=blacklist or [],
            blacklist_profile=blacklist_profile,
            active_days=active_days
        )
        self.series_list = series_list or []
        self.is_multi_series = True

        # Precompute season grouping for each series config that has collection_videos
        for config in self.series_list:
            coll_vids = config.get('collection_videos', [])
            if not coll_vids:
                config['_has_season_tags'] = False
                continue

            season_groups = {}
            has_season_tags = False

            for vid in coll_vids:
                season = vid.get('_meta_season')
                if season is None:
                    continue
                has_season_tags = True
                season_groups.setdefault(season, []).append(vid)

            if has_season_tags:
                # Sort videos within each season by parsed episode
                for s, vlist in season_groups.items():
                    for v in vlist:
                        _, ep = parse_series_episode(v.get('path', ''))
                        v['_parsed_episode'] = ep
                    vlist.sort(key=lambda v: v['_parsed_episode'])

                sorted_seasons = sorted(season_groups.keys())
                season_episode_counts = {s: len(season_groups[s]) for s in sorted_seasons}
                flat_ordered = [v for s in sorted_seasons for v in season_groups[s]]

                config['_season_groups'] = season_groups
                config['_sorted_seasons'] = sorted_seasons
                config['_season_episode_counts'] = season_episode_counts
                config['_has_season_tags'] = True
                config['_flat_ordered'] = flat_ordered
            else:
                config['_has_season_tags'] = False

    def to_display_string(self) -> str:
        base = f"[M] {self.name}"
        if self.series_list:
            total_series = len(self.series_list)
            base += f" ({total_series} series)"
        if self.start_time and self.end_time:
            base += f" ({self.start_time.toString('HH:mm')}-{self.end_time.toString('HH:mm')})"
        return base

    def calculate_schedule(self, start_time_seconds: int) -> List[ScheduleEntry]:
        """Calculate contiguous episode schedule starting at given second offset.
        Returns list of ScheduleEntry objects with day=1 (absolute seconds)."""
        entries = []
        pos = start_time_seconds

        for series_config in self.series_list:
            collection_videos = series_config.get('collection_videos', [])
            start_season = series_config.get('start_season', 1)
            start_episode = series_config.get('start_episode', 1)
            play_mode = series_config.get('play_mode', 'sequence')
            video_count = series_config.get('video_count', 1)
            series_name = series_config.get('name', 'Series')

            if not collection_videos:
                # Add placeholder entry (1 hour)
                entries.append(self._create_video_entry(pos, 3600, series_name, self.name))
                pos += 3600
                continue

            # Determine videos to use, with season_sequence support
            if play_mode == 'season_sequence' and series_config.get('_has_season_tags', False):
                flat = series_config.get('_flat_ordered', [])
                # Compute start offset based on start_season/start_episode
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
                    videos_to_use = []
                else:
                    selected = flat[start_idx : start_idx + video_count]
                    videos_to_use = [{'video': v, 'season': v.get('_meta_season'), 'episode': v.get('_parsed_episode')} for v in selected]
            else:
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
                duration = int(video.get('duration', 90))
                if duration < 1:
                    duration = 90
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

            if play_mode == 'season_sequence' and series_config.get('_has_season_tags', False):
                flat = series_config.get('_flat_ordered', [])
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
                    videos_to_use = []
                else:
                    selected = flat[start_idx : start_idx + video_count]
                    videos_to_use = [{'video': v, 'season': v.get('_meta_season'), 'episode': v.get('_parsed_episode')} for v in selected]
            else:
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
    def __init__(self, day: int, start_seconds: int, end_seconds: int, video_name: str, tag_type: str = ""):
        self.day = day
        self.start_seconds = start_seconds
        self.end_seconds = end_seconds
        self.video_name = video_name
        self.tag_type = tag_type

    @property
    def start_minutes(self) -> int:
        return self.start_seconds // 60

    @property
    def end_minutes(self) -> int:
        return self.end_seconds // 60

    def format_time(self, seconds: int, day: int) -> str:
        hours = (seconds // 3600) % 24
        mins = (seconds % 3600) // 60
        return f"Day {day}\n{hours:02d}:{mins:02d}"

    def to_display_string(self) -> str:
        start_day = (self.start_seconds // (24 * 3600)) + 1
        end_day = (self.end_seconds // (24 * 3600)) + 1
        start_h = (self.start_seconds // 3600) % 24
        start_m = (self.start_seconds % 3600) // 60
        end_h = (self.end_seconds // 3600) % 24
        end_m = (self.end_seconds % 3600) // 60
        if self.start_seconds < 24 * 3600:
            return f"Day {start_day}\n{start_h:02d}:{start_m:02d} - {end_h:02d}:{end_m:02d} - {self.video_name}"
        elif start_day == end_day:
            return f"Day {start_day}\n{start_h:02d}:{start_m:02d} - {end_h:02d}:{end_m:02d} - {self.video_name}"
        else:
            return f"Day {start_day} {start_h:02d}:{start_m:02d} - Day {end_day} {end_h:02d}:{end_m:02d} - {self.video_name}"

    @property
    def tag_color(self) -> Optional[QColor]:
        if self.tag_type:
            if self.tag_type in ("series", "multi_series"):
                return QColor("#7c3aed")
            if self.tag_type == "custom":
                return QColor("#059669")
            if self.tag_type in ("random", "random_fill"):
                return None
        video_name = self.video_name or ""
        prefix = video_name.split(" - ", 1)[0] if " - " in video_name else video_name
        tag_prefix = prefix.strip().upper()
        if tag_prefix in ("[S]", "[M]"):
            return QColor("#7c3aed")
        if tag_prefix == "[C]":
            return QColor("#059669")
        return None

    def to_copy_string(self) -> str:
        start_day = (self.start_seconds // (24 * 3600)) + 1
        end_day = (self.end_seconds // (24 * 3600)) + 1
        start_h = (self.start_seconds // 3600) % 24
        start_m = (self.start_seconds % 3600) // 60
        end_h = (self.end_seconds // 3600) % 24
        end_m = (self.end_seconds % 3600) // 60
        if start_day == end_day:
            return f"Day {start_day} {start_h:02d}:{start_m:02d} - {end_h:02d}:{end_m:02d} - {self.video_name}"
        return f"Day {start_day} {start_h:02d}:{start_m:02d} - Day {end_day} {end_h:02d}:{end_m:02d} - {self.video_name}"

    def color_tag_name_in_text(self, text: str) -> str:
        color = self.tag_color
        if not color:
            return text
        video_name = self.video_name or ""
        if " - " in video_name:
            tag_name, rest = video_name.split(" - ", 1)
            colored_tag = f'<span style="color:{color.name()}">{tag_name}</span>'
            colored_video = f"{colored_tag} - {rest}" if rest else colored_tag
        else:
            colored_video = f'<span style="color:{color.name()}">{video_name}</span>'
        return text.replace(video_name, colored_video, 1)


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
                    randomize_videos: bool = False,
                    series_end_behavior: str = "stop",
                    series_repeat_season: int = 0,
                    series_random_season: int = 0,
                    active_days: Optional[List[int]] = None,
                    marathon_mode: bool = False,
                    marathon_tag_name: str = "") -> bool:
        if 0 <= index < len(self.tags):
            t = self.tags[index]
            t.name = name
            t.start_time = start_time
            t.end_time = end_time
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
            t.series_end_behavior = series_end_behavior
            t.series_repeat_season = series_repeat_season
            t.series_random_season = series_random_season
            t.active_days = active_days
            t.marathon_mode = marathon_mode
            t.marathon_tag_name = marathon_tag_name
            # Apply blacklist filtering to collection_videos
            t.collection_videos = collection_videos or []
            if t.collection_videos and t.blacklist:
                t.collection_videos = filter_videos_by_blacklist(t.collection_videos, t.blacklist)
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
