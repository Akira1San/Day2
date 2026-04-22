#!/usr/bin/env python3
import sys
import random
import configparser
from typing import List, Optional
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QListWidgetItem, QPushButton, QDialog, QLineEdit,
    QLabel, QTimeEdit, QMessageBox, QScrollArea, QCheckBox, QRadioButton, QButtonGroup,
    QFileDialog, QSpinBox, QComboBox
)
from PySide6.QtCore import Qt, QTime
from PySide6.QtGui import QClipboard, QFont

from utils import (
    load_collection_json, load_collection_videos_only, load_blacklist_json,
    parse_series_episode, parse_videos_for_series, qtime_to_minutes,
    get_video_display_name, format_duration, get_config_paths, filter_videos_by_blacklist,
    get_schedule_profiles
)


APPROXIMATE_THRESHOLD_MINUTES = 40


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
                 channel: str = ""):
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
        self.channel = channel

    def to_display_string(self) -> str:
        if self.tag_type == "random" or self.is_random_fill:
            fill_24h = getattr(self, 'fill_24h', False)
            if fill_24h:
                return f"[R] {self.name} (24h Fill)"
            return f"[R] {self.name} ({self.start_time.toString('HH:mm')}-{self.end_time.toString('HH:mm')})"
        if self.is_series:
            return f"[S] {self.name} ({self.start_time.toString('HH:mm')}-{self.end_time.toString('HH:mm')})"
        if self.randomize_videos:
            return f"[C] {self.name} ({self.start_time.toString('HH:mm')}-{self.end_time.toString('HH:mm')}) x{self.video_count}"
        return f"[C] {self.name} ({self.start_time.toString('HH:mm')}-{self.end_time.toString('HH:mm')})"


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
        start_h = (self.start_minutes // 60) % 24
        start_m = self.start_minutes % 60
        end_h = (self.end_minutes // 60) % 24
        end_m = self.end_minutes % 60
        if self.start_minutes == 0:
            return f"Day {self.day}\n{start_h:02d}:{start_m:02d} - {end_h:02d}:{end_m:02d} - {self.video_name}"
        return f"{start_h:02d}:{start_m:02d} - {end_h:02d}:{end_m:02d} - {self.video_name}"

    def to_copy_string(self) -> str:
        start_h = (self.start_minutes // 60) % 24
        start_m = self.start_minutes % 60
        end_h = (self.end_minutes // 60) % 24
        end_m = self.end_minutes % 60
        return f"Day {self.day} {start_h:02d}:{start_m:02d} - Day {self.day} {end_h:02d}:{end_m:02d} - {self.video_name}"


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
                 blacklist_path: str = "", fill_24h: bool = False, channel: str = "") -> bool:
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
            t.channel = channel
            return True
        return False

    def get_custom_tags(self) -> List[Tag]:
        return [t for t in self.tags if t.tag_type == "custom" and not t.is_series]

    def get_series_tags(self) -> List[Tag]:
        return [t for t in self.tags if t.is_series]

    def get_random_tags(self) -> List[Tag]:
        return [t for t in self.tags if t.tag_type == "random" or t.is_random_fill]

    def get_all_tags(self) -> List[Tag]:
        return list(self.tags)


class ScheduleGenerator:
    def __init__(self, tag_manager: TagManager):
        self.tag_manager = tag_manager

    def _create_video_entry(self, pos: int, duration: int, name: str, tag_name: str = "") -> ScheduleEntry:
        video_name = f"{tag_name} - {name}" if tag_name else name
        return ScheduleEntry(1, pos, pos + duration, video_name)

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

    def _process_custom_tag(self, ct: Tag, custom_entries: List[ScheduleEntry], occupied: set):
        start_min = qtime_to_minutes(ct.start_time)
        end_min = qtime_to_minutes(ct.end_time)
        
        if start_min >= end_min or start_min >= 24 * 60 or end_min > 24 * 60:
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

    def _process_series_tag(self, st: Tag, series_entries: List[ScheduleEntry], occupied: set, day_offset: int = 0):
        start_min = qtime_to_minutes(st.start_time)
        end_min = qtime_to_minutes(st.end_time)

        if start_min >= end_min or start_min >= 24 * 60 or end_min > 24 * 60:
            return

        base_start_episode = getattr(st, 'start_episode', 1)
        video_count = getattr(st, 'video_count', 1)
        start_episode = base_start_episode + (day_offset * video_count)

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

    def _process_random_fill_tag(self, rf: Tag, fill_entries: List[ScheduleEntry], merged_ranges: List[tuple] = None, start_vid_idx: int = 0):
        rf_fill_24h = getattr(rf, 'fill_24h', False)

        if rf_fill_24h:
            rf_videos = rf.collection_videos.copy() if rf.collection_videos else []
            if not rf_videos:
                return
            random.shuffle(rf_videos)

            gaps = []
            if merged_ranges:
                prev_end = 0
                for start, end in merged_ranges:
                    if start > prev_end:
                        gaps.append((prev_end, start))
                    prev_end = max(prev_end, end)
                if prev_end < 24 * 60:
                    gaps.append((prev_end, 24 * 60))
            else:
                gaps = [(0, 24 * 60)]

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
            
            if rf_start >= rf_end or rf_start >= 24 * 60 or rf_end > 24 * 60:
                return
            
            rf_videos = rf.collection_videos.copy() if rf.collection_videos else []
            pos = rf_start
            if rf_videos:
                random.shuffle(rf_videos)
            vid_idx = 0
            
            while pos < rf_end:
                if not rf_videos:
                    fill_entries.append(ScheduleEntry(1, pos, rf_end, f"{rf.name} - No videos"))
                    break
                video = rf_videos[vid_idx % len(rf_videos)]
                video_name = get_video_display_name(video)
                duration = int(video.get('duration', 90)) // 60
                if duration < 1:
                    duration = 1
                duration = min(duration, rf_end - pos)
                if duration < 1:
                    break
                fill_entries.append(self._create_video_entry(pos, duration, video_name, rf.name))
                pos += duration
                vid_idx += 1

    def apply_custom_tags(self, use_cache: bool = True, num_days: int = 1) -> List[ScheduleEntry]:
        all_tags = self.tag_manager.get_all_tags()

        cached = self.tag_manager.get_cached_random_entries()
        if use_cache and cached is not None:
            return self._inject_custom_tags(cached)

        custom_tags = [t for t in all_tags if t.tag_type == "custom" and not t.is_random_fill and not t.is_series]
        series_tags = [t for t in all_tags if t.is_series]
        random_fill_tags = [t for t in all_tags if t.is_random_fill]

        if not custom_tags and not series_tags and not random_fill_tags:
            entries = self.generate_random_fill(24 * 60)
            self.tag_manager.set_cached_random_entries(entries)
            return entries

        occupied = set()
        custom_entries = []
        series_entries = []
        fill_entries = []
        
        for ct in custom_tags:
            self._process_custom_tag(ct, custom_entries, occupied)

        for day_offset in range(num_days):
            for st in series_tags:
                self._process_series_tag(st, series_entries, occupied, day_offset)

        rf_sorted = sorted(random_fill_tags, key=lambda t: qtime_to_minutes(t.start_time))
        for rf in rf_sorted:
            merged = [(e.start_minutes, e.end_minutes) for e in custom_entries + series_entries]
            self._process_random_fill_tag(rf, fill_entries, merged if getattr(rf, 'fill_24h', False) else None)

        if fill_entries and getattr(rf, 'fill_24h', False):
            fill_entries.sort(key=lambda e: e.start_minutes)
            total_duration = sum(e.end_minutes - e.start_minutes for e in fill_entries)
            rf_videos = rf_sorted[0].collection_videos.copy() if rf_sorted else []
            if rf_videos:
                total_mins = sum(int(v.get('duration', 90) // 60) for v in rf_videos)
                avg_duration = total_mins // len(rf_videos) if rf_videos else 0
                if avg_duration > 0:
                    start_vid_idx = (total_duration // avg_duration) % len(rf_videos)
                    for rf in rf_sorted[1:]:
                        merged = [(e.start_minutes, e.end_minutes) for e in custom_entries + series_entries]
                        self._process_random_fill_tag(rf, fill_entries, merged, start_vid_idx)

        entries = custom_entries + series_entries + fill_entries
        entries.sort(key=lambda e: e.start_minutes)
        self.tag_manager.set_cached_random_entries(entries)
        return entries

    def _inject_custom_tags(self, random_entries: List[ScheduleEntry]) -> List[ScheduleEntry]:
        custom_tags = self.tag_manager.get_custom_tags()
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

    def apply_approximate(self, num_days: int = 1) -> List[ScheduleEntry]:
        all_tags = self.tag_manager.get_all_tags()
        
        custom_tags = [t for t in all_tags if t.tag_type == "custom" and not t.is_random_fill and not t.is_series]
        series_tags = [t for t in all_tags if t.is_series]
        random_fill_tags = [t for t in all_tags if t.is_random_fill]
        
        rf_24h_tags = [t for t in random_fill_tags if getattr(t, 'fill_24h', False)]
        
        if rf_24h_tags and not custom_tags and not series_tags:
            return self.generate_random_fill(24 * 60)
        
        has_24h_fill = bool(rf_24h_tags)
        
        if has_24h_fill:
            base_entries = []
        else:
            base_entries = self.generate_random_fill(24 * 60) if (custom_tags or series_tags) else []

        if not custom_tags and not series_tags and not random_fill_tags:
            return base_entries

        scheduled_ranges = []
        for ct in custom_tags:
            scheduled_ranges.append((qtime_to_minutes(ct.start_time), qtime_to_minutes(ct.end_time)))
        
        for st in series_tags:
            scheduled_ranges.append((qtime_to_minutes(st.start_time), qtime_to_minutes(st.end_time)))
        
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
        
        custom_sorted = sorted(custom_tags, key=lambda t: qtime_to_minutes(t.start_time))

        if not has_24h_fill:
            for day_offset in range(num_days):
                for ct in custom_sorted:
                    original_start = qtime_to_minutes(ct.start_time)
                    original_end = qtime_to_minutes(ct.end_time)

                    custom_start = max(original_start, next_custom_pos)
                    custom_end = custom_start + (original_end - original_start)

                    if ct.collection_videos:
                        for m in range(custom_start, custom_end):
                            occupied.add(m)
                        video_count = getattr(ct, 'video_count', 1)
                        videos = ct.collection_videos.copy()
                        random.shuffle(videos)
                    pos = custom_start
                    vid_idx = 0
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
                        pos += duration
                        vid_idx += 1
                    current_pos = custom_end
                else:
                    if custom_start < current_pos:
                        custom_start = current_pos
                        custom_end = custom_start + (original_end - original_start)
                    final.append(ScheduleEntry(1, custom_start, custom_end, ct.name))
                    current_pos = custom_end

                next_custom_pos = current_pos
                while rand_idx < len(base_entries) and base_entries[rand_idx].start_minutes < current_pos:
                    rand_idx += 1

            for day_offset in range(num_days):
                for st in series_tags:
                    original_start = qtime_to_minutes(st.start_time)
                    original_end = qtime_to_minutes(st.end_time)
                    if original_start >= original_end or original_start >= 24 * 60 or original_end > 24 * 60:
                        continue

                    series_start = max(original_start, next_custom_pos)
                    series_end = series_start + (original_end - original_start)

                    base_start_episode = getattr(st, 'start_episode', 1)
                    video_count = getattr(st, 'video_count', 1)
                    start_episode = base_start_episode + (day_offset * video_count)

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
                        pos += duration
                    current_pos = series_end
                else:
                    final.append(ScheduleEntry(1, series_start, series_end, st.name))
                    current_pos = series_end

                next_custom_pos = current_pos
                while rand_idx < len(base_entries) and base_entries[rand_idx].start_minutes < current_pos:
                    rand_idx += 1
        else:
            for ct in custom_sorted:
                original_start = qtime_to_minutes(ct.start_time)
                original_end = qtime_to_minutes(ct.end_time)

                if ct.collection_videos:
                    for m in range(original_start, original_end):
                        occupied.add(m)
                    video_count = getattr(ct, 'video_count', 1)
                    videos = ct.collection_videos.copy()
                    random.shuffle(videos)
                    pos = original_start
                    vid_idx = 0
                    while pos < original_end and vid_idx < video_count and vid_idx < len(videos):
                        video = videos[vid_idx % len(videos)]
                        video_name = get_video_display_name(video)
                        duration = int(video.get('duration', 90)) // 60
                        if duration < 1:
                            duration = 1
                        duration = min(duration, original_end - pos)
                        if duration < 1:
                            break
                        final.append(self._create_video_entry(pos, duration, video_name, ct.name))
                        pos += duration
                        vid_idx += 1
                else:
                    final.append(ScheduleEntry(1, original_start, original_end, ct.name))

            for st in series_tags:
                original_start = qtime_to_minutes(st.start_time)
                original_end = qtime_to_minutes(st.end_time)
                if original_start >= original_end or original_start >= 24 * 60 or original_end > 24 * 60:
                    continue

                if st.collection_videos:
                    for m in range(original_start, original_end):
                        occupied.add(m)

                    videos_to_use, _ = parse_videos_for_series(
                        st.collection_videos,
                        getattr(st, 'start_season', 1),
                        getattr(st, 'start_episode', 1),
                        getattr(st, 'play_mode', 'sequence'),
                        getattr(st, 'video_count', 1)
                    )
                    
                    pos = original_start
                    for v in videos_to_use:
                        if pos >= original_end:
                            break
                        video = v['video']
                        video_name = get_video_display_name(video)
                        duration = int(video.get('duration', 90)) // 60
                        if duration < 1:
                            duration = 1
                        duration = min(duration, original_end - pos)
                        if duration < 1:
                            break
                        final.append(self._create_video_entry(pos, duration, video_name, st.name))
                        pos += duration
                else:
                    final.append(ScheduleEntry(1, original_start, original_end, st.name))

        rf_sorted = sorted(random_fill_tags, key=lambda t: qtime_to_minutes(t.start_time))
        for rf in rf_sorted:
            self._process_random_fill_tag(rf, final, merged_ranges if has_24h_fill else None)

        if len(final) == 0 and not has_24h_fill:
            while current_pos < 24 * 60 and rand_idx < len(base_entries):
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


class BaseTagDialog(QDialog):
    def __init__(self, parent=None, tag: Optional[Tag] = None):
        super().__init__(parent)
        self.collection_videos = []
        self.blacklist = []

    def _setup_time_inputs(self, layout: QHBoxLayout, start_time: QTime = None, end_time: QTime = None):
        start_time = start_time or QTime(0, 0)
        end_time = end_time or QTime(1, 0)
        
        layout.addWidget(QLabel("Start Time:"))
        self.start_time_edit = QTimeEdit()
        self.start_time_edit.setDisplayFormat("HH:mm")
        self.start_time_edit.setTime(start_time)
        layout.addWidget(self.start_time_edit)

        layout.addWidget(QLabel("End Time:"))
        self.end_time_edit = QTimeEdit()
        self.end_time_edit.setDisplayFormat("HH:mm")
        self.end_time_edit.setTime(end_time)
        layout.addWidget(self.end_time_edit)

    def _load_collection_to_list(self, file_path: str, list_widget: QListWidget):
        collection_videos, _ = load_collection_json(file_path)
        self.collection_videos = collection_videos
        for video in collection_videos:
            path = video.get('path', '')
            duration = video.get('duration', 0)
            display_name = get_video_display_name(video)
            list_widget.addItem(f"{display_name} ({format_duration(duration)})")


class TagDialog(BaseTagDialog):
    def __init__(self, parent=None, tag: Optional[Tag] = None):
        super().__init__(parent, tag)
        self.setWindowTitle("Edit Tag" if tag else "Add Custom Tag")
        self.setModal(True)
        self.setup_ui()
        self.load_available_collection_profiles()
        self.load_channels()
        if tag:
            self.name_input.setText(tag.name)
            self.start_time_edit.setTime(tag.start_time)
            self.end_time_edit.setTime(tag.end_time)
            if tag.collection_videos:
                self.collection_videos = tag.collection_videos.copy()
                for video in self.collection_videos:
                    path = video.get('path', '')
                    duration = video.get('duration', 0)
                    display_name = get_video_display_name(video)
                    self.videos_list.addItem(f"{display_name} ({format_duration(duration)})")
            if hasattr(tag, 'randomize_videos') and tag.randomize_videos:
                self.randomize_videos_check.setChecked(True)
            if hasattr(tag, 'video_count'):
                self.video_count_spin.setValue(tag.video_count)
            if hasattr(tag, 'collection_path') and tag.collection_path:
                self.collection_path.setText(tag.collection_path)
                if tag.collection_videos:
                    self.videos_list.clear()
                    self.collection_videos = tag.collection_videos.copy()
                    for video in self.collection_videos:
                        path = video.get('path', '')
                        duration = video.get('duration', 0)
                        display_name = get_video_display_name(video)
                        self.videos_list.addItem(f"{display_name} ({format_duration(duration)})")

    def setup_ui(self):
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Name:"))
        self.name_input = QLineEdit()
        layout.addWidget(self.name_input)

        collection_layout = QHBoxLayout()
        collection_layout.addWidget(QLabel("Collection:"))
        self.collection_path = QLineEdit()
        self.collection_path.setPlaceholderText("Select collections_name.json...")
        self.collection_path.setReadOnly(True)
        collection_layout.addWidget(self.collection_path)

        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self.browse_collection)
        collection_layout.addWidget(browse_btn)
        layout.addLayout(collection_layout)

        profile_layout = QHBoxLayout()
        profile_layout.addWidget(QLabel("Collection Profile:"))
        self.collection_profile_combo = QComboBox()
        self.collection_profile_combo.currentIndexChanged.connect(self.profile_selected)
        profile_layout.addWidget(self.collection_profile_combo)
        
        profile_layout.addWidget(QLabel("Blacklist Profile:"))
        self.blacklist_profile_combo = QComboBox()
        self.blacklist_profile_combo.currentIndexChanged.connect(self.blacklist_profile_selected)
        profile_layout.addWidget(self.blacklist_profile_combo)
        
        profile_layout.addStretch()
        layout.addLayout(profile_layout)

        channel_layout = QHBoxLayout()
        channel_layout.addWidget(QLabel("Channel:"))
        self.channel_combo = QComboBox()
        self.channel_combo.setEditable(True)
        self.load_channels()
        channel_layout.addWidget(self.channel_combo)
        channel_layout.addStretch()
        layout.addLayout(channel_layout)

        layout.addWidget(QLabel("Videos in Collection:"))
        self.videos_list = QListWidget()
        self.videos_list.setMinimumHeight(150)
        layout.addWidget(self.videos_list)

        randomize_layout = QHBoxLayout()
        self.randomize_videos_check = QCheckBox("Randomize Videos")
        randomize_layout.addWidget(self.randomize_videos_check)
        randomize_layout.addWidget(QLabel("Video Count:"))
        self.video_count_spin = QSpinBox()
        self.video_count_spin.setMinimum(1)
        self.video_count_spin.setValue(1)
        randomize_layout.addWidget(self.video_count_spin)
        randomize_layout.addStretch()
        layout.addLayout(randomize_layout)

        calc_layout = QHBoxLayout()
        self.auto_calc_btn = QPushButton("Auto Calc End Time")
        self.auto_calc_btn.clicked.connect(self.auto_calc_end_time)
        calc_layout.addWidget(self.auto_calc_btn)
        calc_layout.addStretch()
        layout.addLayout(calc_layout)

        time_layout = QHBoxLayout()
        self._setup_time_inputs(time_layout)
        layout.addLayout(time_layout)

        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def browse_collection(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Collection File", "",
            "JSON Files (*.json);;All Files (*)"
        )
        if file_path:
            self.load_collection(file_path)

    def load_collection(self, file_path: str):
        self.collection_path.setText(file_path)
        self.videos_list.clear()
        self.collection_videos.clear()

        collection_videos, _ = load_collection_json(file_path)
        self.collection_videos = collection_videos

        for video in collection_videos:
            path = video.get('path', '')
            duration = video.get('duration', 0)
            display_name = get_video_display_name(video)
            self.videos_list.addItem(f"{display_name} ({format_duration(duration)})")

    def load_available_collection_profiles(self):
        collection_path, blacklist_path = get_config_paths()

        self.collection_profile_combo.addItem("-- None --")
        self.blacklist_profile_combo.addItem("-- None --")

        coll_path = Path(collection_path)
        if coll_path.exists():
            for json_file in sorted(coll_path.glob("*.json")):
                self.collection_profile_combo.addItem(json_file.name)

        blck_path = Path(blacklist_path)
        if blck_path.exists():
            for ini_file in sorted(blck_path.glob("*_blacklist.ini")):
                self.blacklist_profile_combo.addItem(ini_file.name)
            for ini_file in sorted(blck_path.glob("*blacklist*.ini")):
                self.blacklist_profile_combo.addItem(ini_file.name)
        
        if blck_path != Path('.'):
            for ini_file in sorted(Path('.').glob("*blacklist*.ini")):
                self.blacklist_profile_combo.addItem(ini_file.name)

    def profile_selected(self, index):
        if index <= 0:
            return
        file_name = self.collection_profile_combo.currentText()
        collection_path, _ = get_config_paths()
        file_path = Path(collection_path) / file_name
        if file_path.exists():
            self.load_collection(str(file_path))

    def blacklist_profile_selected(self, index):
        if index <= 0:
            return
        file_name = self.blacklist_profile_combo.currentText()
        _, blacklist_path = get_config_paths()
        file_path = Path(blacklist_path) / file_name
        if file_path.exists():
            self.load_blacklist_file(str(file_path))

    def load_blacklist_file(self, file_path: str):
        self.blacklist = load_blacklist_json(file_path)

    def load_channels(self):
        profiles = get_schedule_profiles()
        self.channel_combo.clear()
        self.channel_combo.addItem("")
        for profile in profiles:
            self.channel_combo.addItem(profile)
        if hasattr(self, 'tag') and self.tag and hasattr(self.tag, 'channel') and self.tag.channel:
            index = self.channel_combo.findText(self.tag.channel)
            if index >= 0:
                self.channel_combo.setCurrentIndex(index)
            else:
                self.channel_combo.setCurrentText(self.tag.channel)

    def get_tag(self) -> Tag:
        return Tag(
            tag_type="custom",
            name=self.name_input.text() or "Custom Video",
            start_time=self.start_time_edit.time(),
            end_time=self.end_time_edit.time(),
            collection_videos=self.collection_videos.copy(),
            collection_path=self.collection_path.text(),
            video_count=self.video_count_spin.value(),
            blacklist=self.blacklist.copy(),
            channel=self.channel_combo.currentText()
        )

    def auto_calc_end_time(self):
        if not self.collection_videos:
            QMessageBox.warning(self, "No Videos", "Please load a collection first.")
            return

        if not self.randomize_videos_check.isChecked():
            selected = self.videos_list.currentRow()
            if selected < 0:
                QMessageBox.warning(self, "No Selection", "Please select a video from the list.")
                return
            duration = self.collection_videos[selected].get('duration', 0)
        else:
            count = self.video_count_spin.value()
            total_duration = sum(self.collection_videos[i].get('duration', 0) for i in range(min(count, len(self.collection_videos))))
            duration = total_duration

        start_time = self.start_time_edit.time()
        start_mins = qtime_to_minutes(start_time)
        end_mins = (start_mins + int(duration // 60)) % (24 * 60)
        self.end_time_edit.setTime(QTime(end_mins // 60, end_mins % 60))


class RandomFillDialog(BaseTagDialog):
    def __init__(self, parent=None, tag: Optional[Tag] = None):
        super().__init__(parent, tag)
        self.setWindowTitle("Add Random Fill Tag" if not tag else "Edit Random Fill Tag")
        self.setModal(True)
        self.added_videos = []
        self.blacklist_path = ""
        self.setup_ui()
        self.load_channels()
        
        if tag:
            self.name_input.setText(tag.name)
            self.start_time_edit.setTime(tag.start_time)
            self.end_time_edit.setTime(tag.end_time)
            self.blacklist = tag.blacklist.copy() if hasattr(tag, 'blacklist') and tag.blacklist else []
            fill_24h = getattr(tag, 'fill_24h', False)
            self.fill_24h_check.setChecked(fill_24h)
            
            if tag.collection_videos and tag.collection_path:
                self.load_collection(tag.collection_path)

    def setup_ui(self):
        main_layout = QHBoxLayout(self)
        
        info_panel = QWidget()
        info_layout = QVBoxLayout(info_panel)
        info_layout.addWidget(QLabel("<b>Collection Info</b>"))
        
        self.info_name = QLabel("Name: -")
        info_layout.addWidget(self.info_name)
        
        self.info_desc = QLabel("Description:")
        self.info_desc.setWordWrap(True)
        info_layout.addWidget(self.info_desc)
        
        self.info_genre = QLabel("Genre: -")
        info_layout.addWidget(self.info_genre)
        
        self.info_year = QLabel("Year: -")
        info_layout.addWidget(self.info_year)
        
        info_layout.addWidget(QLabel("<b>Video Info</b>"))
        self.video_info = QLabel("Select a video to see details")
        self.video_info.setWordWrap(True)
        info_layout.addWidget(self.video_info)
        
        main_layout.addWidget(info_panel)
        
        lists_panel = QWidget()
        lists_layout = QVBoxLayout(lists_panel)
        
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Name:"))
        self.name_input = QLineEdit()
        name_layout.addWidget(self.name_input)
        
        name_layout.addWidget(QLabel("Channel:"))
        self.channel_combo = QComboBox()
        self.channel_combo.setEditable(True)
        name_layout.addWidget(self.channel_combo)
        name_layout.addStretch()
        
        coll_layout = QHBoxLayout()
        coll_layout.addWidget(QLabel("Collection:"))
        self.collection_path = QLineEdit()
        self.collection_path.setPlaceholderText("Select collections_name.json...")
        self.collection_path.setReadOnly(True)
        coll_layout.addWidget(self.collection_path)

        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self.browse_collection)
        coll_layout.addWidget(browse_btn)
        
        lists_layout.addLayout(name_layout)
        lists_layout.addLayout(coll_layout)
        
        lists_container = QWidget()
        lists_inner = QHBoxLayout(lists_container)
        
        collection_widget = self._create_video_list_section("Videos in Collection", True)
        self.videos_list = collection_widget.videos_list
        self.videos_count_label = collection_widget.count_label
        
        added_widget = self._create_video_list_section("Added Videos", False)
        self.added_list = added_widget.videos_list
        self.added_count_label = added_widget.count_label
        
        blacklist_widget = self._create_blacklist_section()
        self.blacklist_list = blacklist_widget.blacklist_list
        self.blacklist_count_label = blacklist_widget.count_label
        
        lists_inner.addWidget(collection_widget.widget)
        lists_inner.addWidget(added_widget.widget)
        lists_inner.addWidget(blacklist_widget.widget)
        
        lists_layout.addWidget(lists_container)
        
        time_layout = QHBoxLayout()
        self._setup_time_inputs(time_layout)

        self.calc_btn = QPushButton("Auto Calc")
        self.calc_btn.clicked.connect(self.auto_calc_end_time)
        time_layout.addWidget(self.calc_btn)
        lists_layout.addLayout(time_layout)

        self.fill_24h_check = QCheckBox("Fill 24 Hours (loop videos to fill full day)")
        self.fill_24h_check.setChecked(True)
        lists_layout.addWidget(self.fill_24h_check)

        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        lists_layout.addLayout(btn_layout)
        
        main_layout.addWidget(lists_panel)

    def _create_video_list_section(self, title: str, with_buttons: bool):
        widget = QWidget()
        vbox = QVBoxLayout(widget)
        vbox.addWidget(QLabel(title))
        
        count_label = QLabel("Count: 0")
        vbox.addWidget(count_label)
        
        videos_list = QListWidget()
        videos_list.setMinimumHeight(200)
        if with_buttons:
            videos_list.setSelectionMode(QListWidget.MultiSelection)
            videos_list.itemClicked.connect(self.on_video_selected)
        vbox.addWidget(videos_list)
        
        btn_layout = QHBoxLayout()
        if with_buttons:
            select_all_btn = QPushButton("Select All")
            select_all_btn.clicked.connect(self.select_all_videos)
            btn_layout.addWidget(select_all_btn)
            
            clear_sel_btn = QPushButton("Clear")
            clear_sel_btn.clicked.connect(self.clear_selection)
            btn_layout.addWidget(clear_sel_btn)
            
            add_btn = QPushButton("Add >>")
            add_btn.clicked.connect(self.add_selected_videos)
            btn_layout.addWidget(add_btn)
        else:
            remove_btn = QPushButton("<< Remove")
            remove_btn.clicked.connect(self.remove_selected_added)
            btn_layout.addWidget(remove_btn)
            
            remove_all_btn = QPushButton("Remove All")
            remove_all_btn.clicked.connect(self.remove_all_added)
            btn_layout.addWidget(remove_all_btn)
            
            blacklist_btn = QPushButton("Add to Blacklist >>")
            blacklist_btn.clicked.connect(self.add_to_blacklist)
            btn_layout.addWidget(blacklist_btn)
        
        vbox.addLayout(btn_layout)
        
        section = type('VideoSection', (), {
            'widget': widget, 'videos_list': videos_list, 'count_label': count_label
        })()
        return section

    def _create_blacklist_section(self):
        widget = QWidget()
        vbox = QVBoxLayout(widget)
        vbox.addWidget(QLabel("Blacklist"))
        
        count_label = QLabel("Count: 0")
        vbox.addWidget(count_label)
        
        blacklist_list = QListWidget()
        blacklist_list.setMinimumHeight(200)
        vbox.addWidget(blacklist_list)
        
        btn_layout = QHBoxLayout()
        remove_blacklist_btn = QPushButton("<< Remove")
        remove_blacklist_btn.clicked.connect(self.remove_from_blacklist)
        btn_layout.addWidget(remove_blacklist_btn)
        
        load_blacklist_btn = QPushButton("Load")
        load_blacklist_btn.clicked.connect(self.load_blacklist_file)
        btn_layout.addWidget(load_blacklist_btn)
        
        save_blacklist_btn = QPushButton("Save")
        save_blacklist_btn.clicked.connect(self.save_blacklist_file)
        btn_layout.addWidget(save_blacklist_btn)
        
        vbox.addLayout(btn_layout)
        
        section = type('BlacklistSection', (), {
            'widget': widget, 'blacklist_list': blacklist_list, 'count_label': count_label
        })()
        return section

    def browse_collection(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Collection File", "",
            "JSON Files (*.json);;All Files (*)"
        )
        if file_path:
            self.load_collection(file_path)

    def load_collection(self, file_path: str):
        collection_videos, collection_info = load_collection_json(file_path)
        self.collection_path.setText(file_path)
        self.videos_list.clear()
        self.collection_videos = []
        self.added_videos = []
        self.blacklist = []

        collection_dir = Path(file_path).parent
        collection_stem = Path(file_path).stem
        
        blacklist_data = []
        for search_dir in [collection_dir, Path.cwd()]:
            for bl_file in search_dir.glob(f"{collection_stem}_blacklist.*"):
                blacklist_data = load_blacklist_json(str(bl_file))
                break
            if blacklist_data:
                break

        self.info_name.setText(f"Name: {collection_info.get('name', '-')}")
        self.info_desc.setText(f"Description: {collection_info.get('description', '-')}")
        self.info_genre.setText(f"Genre: {', '.join(collection_info.get('genre', []))}")
        self.info_year.setText(f"Year: {collection_info.get('year', '-')}")
        
        for video in collection_videos:
            path = video.get('path', '')
            duration = video.get('duration', 0)
            video_data = {'path': path, 'duration': duration, 'name': get_video_display_name(video)}
            self.collection_videos.append(video_data)
            self.videos_list.addItem(f"{video_data['name']} ({format_duration(duration)})")
            
            if any(b.get('path') == path for b in blacklist_data):
                self.blacklist.append(video_data)
        
        for bl_video in blacklist_data:
            if bl_video not in self.blacklist:
                self.blacklist.append(bl_video)
        
        self.added_videos = []
        self.refresh_added_list()
        self.refresh_blacklist_list()

    def on_video_selected(self, item):
        row = self.videos_list.row(item)
        if 0 <= row < len(self.collection_videos):
            video = self.collection_videos[row]
            info = f"Name: {video.get('name', '-')}\nPath: {video.get('path', '-')}\nDuration: {int(video.get('duration', 0))}s"
            self.video_info.setText(info)

    def select_all_videos(self):
        self.videos_list.selectAll()

    def clear_selection(self):
        self.videos_list.clearSelection()

    def add_selected_videos(self):
        for item in self.videos_list.selectedItems():
            row = self.videos_list.row(item)
            if 0 <= row < len(self.collection_videos):
                video = self.collection_videos[row]
            else:
                text = item.text()
                video_name = text.split(' (')[0]
                video = {'path': f"/home/akira/Videos/Akiratv/{video_name}"}
            if video not in self.added_videos:
                self.added_videos.append(video)
        self.refresh_added_list()

    def remove_selected_added(self):
        for item in self.added_list.selectedItems():
            video_name = item.text().split(' (')[0]
            self.added_videos = [v for v in self.added_videos if v.get('path', '').split('/')[-1] != video_name]
        self.refresh_added_list()

    def remove_all_added(self):
        self.added_videos = []
        self.refresh_added_list()

    def add_to_blacklist(self):
        for item in self.added_list.selectedItems():
            video_name = item.text().split(' (')[0]
            for v in self.collection_videos:
                if v.get('path', '').split('/')[-1] == video_name:
                    if v not in self.blacklist:
                        self.blacklist.append(v)
                    break
        self.refresh_added_list()
        self.refresh_blacklist_list()

    def remove_from_blacklist(self):
        for item in self.blacklist_list.selectedItems():
            row = self.blacklist_list.row(item)
            if 0 <= row < len(self.blacklist):
                self.blacklist.pop(row)
        self.refresh_blacklist_list()

    def refresh_added_list(self):
        sorted_added = sorted(self.added_videos, key=lambda v: v.get('path', '').split('/')[-1])
        self.added_list.clear()
        for video in sorted_added:
            self.added_list.addItem(f"{get_video_display_name(video)} ({format_duration(video.get('duration', 0))})")
        self.update_counts()

    def refresh_blacklist_list(self):
        self.blacklist_list.clear()
        sorted_blacklist = sorted(self.blacklist, key=lambda v: v.get('path', '').split('/')[-1])
        for video in sorted_blacklist:
            self.blacklist_list.addItem(get_video_display_name(video))
        self.update_counts()

    def update_counts(self):
        self.videos_count_label.setText(f"Count: {len(self.collection_videos)}")
        self.added_count_label.setText(f"Count: {len(self.added_videos)}")
        self.blacklist_count_label.setText(f"Count: {len(self.blacklist)}")

    def load_blacklist_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Blacklist File", "", "INI Files (*.ini);;JSON Files (*.json);;All Files (*)"
        )
        if not file_path:
            return
        
        blacklist_data = load_blacklist_json(file_path)
        self.blacklist = blacklist_data
        self.blacklist_path = file_path
        
        self.added_videos = filter_videos_by_blacklist(self.added_videos, self.blacklist)
        
        self.refresh_blacklist_list()
        self.refresh_added_list()

    def save_blacklist_file(self):
        if not self.collection_path.text():
            return
        
        import json
        blacklist_path = self.collection_path.text().replace('.json', '_blacklist.json')
        
        blacklist_data = {'blacklist': self.blacklist}
        
        with open(blacklist_path, 'w') as f:
            json.dump(blacklist_data, f, indent=2)
        
        QMessageBox.warning(self, "Saved", f"Blacklist saved to {blacklist_path}")

    def load_channels(self):
        profiles = get_schedule_profiles()
        self.channel_combo.clear()
        self.channel_combo.addItem("")
        for profile in profiles:
            self.channel_combo.addItem(profile)
        if hasattr(self, 'tag') and self.tag and hasattr(self.tag, 'channel') and self.tag.channel:
            index = self.channel_combo.findText(self.tag.channel)
            if index >= 0:
                self.channel_combo.setCurrentIndex(index)
            else:
                self.channel_combo.setCurrentText(self.tag.channel)

    def auto_calc_end_time(self):
        if not self.added_videos:
            QMessageBox.warning(self, "No Videos", "Please add videos first.")
            return
        
        total_duration = sum(v.get('duration', 0) for v in self.added_videos)
        total_mins = int(total_duration // 60)
        
        start_time = self.start_time_edit.time()
        start_mins = qtime_to_minutes(start_time)
        end_mins = (start_mins + total_mins) % (24 * 60)
        
        self.end_time_edit.setTime(QTime(end_mins // 60, end_mins % 60))

    def get_tag(self) -> Optional[Tag]:
        if not self.added_videos:
            QMessageBox.warning(self, "No Videos", "Please add at least one video.")
            return None
        
        fill_24h = self.fill_24h_check.isChecked()
        
        if fill_24h:
            self.start_time_edit.setTime(QTime(0, 0))
            self.end_time_edit.setTime(QTime(23, 59))
        
        return Tag(
            tag_type="random",
            name=self.name_input.text() or "Random Fill",
            start_time=self.start_time_edit.time(),
            end_time=self.end_time_edit.time(),
            collection_videos=self.added_videos.copy(),
            collection_path=self.collection_path.text(),
            blacklist=self.blacklist.copy(),
            blacklist_path=self.blacklist_path,
            is_random_fill=True,
            fill_24h=fill_24h,
            channel=self.channel_combo.currentText()
        )


class ConfigDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Config Settings")
        self.setModal(True)
        self.config_path = "config.ini"
        self.setup_ui()
        self.load_config()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Collection Path:"))
        collection_layout = QHBoxLayout()
        self.collection_path_edit = QLineEdit()
        self.collection_path_edit.setPlaceholderText("/home/akira/akira/AkiraTV_NEW/user/collections/")
        collection_layout.addWidget(self.collection_path_edit)
        
        browse_col_btn = QPushButton("Browse")
        browse_col_btn.clicked.connect(self.browse_collection_path)
        collection_layout.addWidget(browse_col_btn)
        layout.addLayout(collection_layout)

        layout.addWidget(QLabel("Blacklist Path:"))
        blacklist_layout = QHBoxLayout()
        self.blacklist_path_edit = QLineEdit()
        self.blacklist_path_edit.setPlaceholderText("/home/akira/akira/AkiraTV_NEW/user/blacklists/")
        blacklist_layout.addWidget(self.blacklist_path_edit)
        
        browse_bl_btn = QPushButton("Browse")
        browse_bl_btn.clicked.connect(self.browse_blacklist_path)
        blacklist_layout.addWidget(browse_bl_btn)
        layout.addLayout(blacklist_layout)

        layout.addWidget(QLabel("Schedule Profiles (comma-separated names):"))
        self.schedule_profiles_edit = QLineEdit()
        self.schedule_profiles_edit.setPlaceholderText("akiratv, superman, horror")
        layout.addWidget(self.schedule_profiles_edit)

        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.save_config)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def browse_collection_path(self):
        path = QFileDialog.getExistingDirectory(self, "Select Collection Directory", "")
        if path:
            self.collection_path_edit.setText(path)

    def browse_blacklist_path(self):
        path = QFileDialog.getExistingDirectory(self, "Select Blacklist Directory", "")
        if path:
            self.blacklist_path_edit.setText(path)

    def load_config(self):
        if Path(self.config_path).exists():
            config = configparser.ConfigParser()
            config.read(self.config_path)
            if 'Paths' in config:
                self.collection_path_edit.setText(config['Paths'].get('collection_path', ''))
                self.blacklist_path_edit.setText(config['Paths'].get('blacklist_path', ''))
            if 'ScheduleProfiles' in config:
                self.schedule_profiles_edit.setText(config['ScheduleProfiles'].get('profiles', ''))

    def save_config(self):
        config = configparser.ConfigParser()
        config['Paths'] = {
            'collection_path': self.collection_path_edit.text(),
            'blacklist_path': self.blacklist_path_edit.text()
        }
        profiles = self.schedule_profiles_edit.text().strip()
        if profiles:
            config['ScheduleProfiles'] = {
                'profiles': profiles
            }
        with open(self.config_path, 'w') as f:
            config.write(f)
        self.accept()


class SeriesDialog(BaseTagDialog):
    def __init__(self, parent=None, tag: Optional[Tag] = None):
        super().__init__(parent, tag)
        self.setWindowTitle("Edit Series Tag" if tag else "Add Series Tag")
        self.setModal(True)
        self.setup_ui()
        if tag:
            self.name_input.setText(tag.name)
            self.start_time_edit.setTime(tag.start_time)
            self.end_time_edit.setTime(tag.end_time)
            self.start_season_spin.setValue(getattr(tag, 'start_season', 1))
            self.start_episode_spin.setValue(getattr(tag, 'start_episode', 1))
            self.video_count_spin.setValue(tag.video_count)
            if hasattr(tag, 'play_mode') and tag.play_mode:
                index = self.play_mode_combo.findText(tag.play_mode)
                if index >= 0:
                    self.play_mode_combo.setCurrentIndex(index)
            if tag.collection_videos:
                self.collection_videos = tag.collection_videos.copy()
                for video in self.collection_videos:
                    path = video.get('path', '')
                    duration = video.get('duration', 0)
                    display_name = get_video_display_name(video)
                    self.videos_list.addItem(f"{display_name} ({format_duration(duration)})")
            if hasattr(tag, 'collection_path') and tag.collection_path:
                self.collection_path.setText(tag.collection_path)

    def setup_ui(self):
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Name:"))
        self.name_input = QLineEdit()
        layout.addWidget(self.name_input)

        collection_layout = QHBoxLayout()
        collection_layout.addWidget(QLabel("Collection:"))
        self.collection_path = QLineEdit()
        self.collection_path.setPlaceholderText("Select collections_name.json...")
        self.collection_path.setReadOnly(True)
        collection_layout.addWidget(self.collection_path)

        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self.browse_collection)
        collection_layout.addWidget(browse_btn)
        layout.addLayout(collection_layout)

        layout.addWidget(QLabel("Videos in Collection:"))
        self.videos_list = QListWidget()
        self.videos_list.setMinimumHeight(150)
        layout.addWidget(self.videos_list)

        series_layout = QHBoxLayout()
        series_layout.addWidget(QLabel("Start Season:"))
        self.start_season_spin = QSpinBox()
        self.start_season_spin.setMinimum(1)
        self.start_season_spin.setValue(1)
        series_layout.addWidget(self.start_season_spin)

        series_layout.addWidget(QLabel("Start Episode:"))
        self.start_episode_spin = QSpinBox()
        self.start_episode_spin.setMinimum(1)
        self.start_episode_spin.setValue(1)
        series_layout.addWidget(self.start_episode_spin)

        series_layout.addWidget(QLabel("Video Count:"))
        self.video_count_spin = QSpinBox()
        self.video_count_spin.setMinimum(1)
        self.video_count_spin.setValue(1)
        series_layout.addWidget(self.video_count_spin)

        series_layout.addWidget(QLabel("Play Mode:"))
        self.play_mode_combo = QComboBox()
        self.play_mode_combo.addItems(["sequence", "random"])
        series_layout.addWidget(self.play_mode_combo)
        series_layout.addStretch()
        layout.addLayout(series_layout)

        calc_layout = QHBoxLayout()
        self.auto_calc_btn = QPushButton("Auto Calc End Time")
        self.auto_calc_btn.clicked.connect(self.auto_calc_end_time)
        calc_layout.addWidget(self.auto_calc_btn)
        calc_layout.addStretch()
        layout.addLayout(calc_layout)

        time_layout = QHBoxLayout()
        self._setup_time_inputs(time_layout)
        layout.addLayout(time_layout)

        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def browse_collection(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Collection File", "",
            "JSON Files (*.json);;All Files (*)"
        )
        if file_path:
            self.load_collection(file_path)

    def load_collection(self, file_path: str):
        collection_videos, _ = load_collection_json(file_path)
        self.collection_path.setText(file_path)
        self.videos_list.clear()
        self.collection_videos = collection_videos

        for video in collection_videos:
            path = video.get('path', '')
            duration = video.get('duration', 0)
            display_name = get_video_display_name(video)
            self.videos_list.addItem(f"{display_name} ({format_duration(duration)})")

    def auto_calc_end_time(self):
        if not self.collection_videos:
            return
        
        start_season = self.start_season_spin.value()
        start_episode = self.start_episode_spin.value()
        
        videos_to_use, _ = parse_videos_for_series(
            self.collection_videos,
            start_season,
            start_episode,
            self.play_mode_combo.currentText(),
            self.video_count_spin.value()
        )
        
        total_duration = sum(v['video'].get('duration', 0) for v in videos_to_use)
        total_mins = int(total_duration / 60)

        start_time = self.start_time_edit.time()
        start_mins = qtime_to_minutes(start_time)
        end_mins = (start_mins + total_mins) % (24 * 60)

        self.end_time_edit.setTime(QTime(end_mins // 60, end_mins % 60))

    def get_tag(self) -> Optional[Tag]:
        if not self.name_input.text():
            QMessageBox.warning(self, "No Name", "Please enter a name.")
            return None
        
        self.auto_calc_end_time()
        return Tag(
            tag_type="custom",
            name=self.name_input.text(),
            start_time=self.start_time_edit.time(),
            end_time=self.end_time_edit.time(),
            collection_videos=self.collection_videos.copy(),
            collection_path=self.collection_path.text(),
            video_count=self.video_count_spin.value(),
            is_series=True,
            start_season=self.start_season_spin.value(),
            start_episode=self.start_episode_spin.value(),
            play_mode=self.play_mode_combo.currentText()
        )


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Daypart Scheduler")
        self.resize(1000, 600)
        self.tag_manager = TagManager()
        self.schedule_generator = ScheduleGenerator(self.tag_manager)
        self.schedule_entries: List[ScheduleEntry] = []
        self.approximate_enabled = False
        self.statusBar().showMessage("Approximate: OFF")
        self.setup_ui()
        self.load_default_tags()
        self.refresh_preview()

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)

        self.tags_panel = QWidget()
        self.tags_panel.setFixedWidth(400)
        tags_layout = QVBoxLayout(self.tags_panel)

        tags_title = QLabel("Daypart Tags")
        tags_title.setFont(QFont("", 16, QFont.Bold))
        tags_layout.addWidget(tags_title)

        self.tags_list = QListWidget()
        self.tags_list.setAlternatingRowColors(True)
        tags_layout.addWidget(self.tags_list)

        btn_layout = QHBoxLayout()
        self.add_btn = QPushButton("Add Custom")
        self.add_btn.clicked.connect(self.add_custom_tag)
        btn_layout.addWidget(self.add_btn)

        self.add_random_btn = QPushButton("Add Random Fill")
        self.add_random_btn.clicked.connect(self.add_random_fill_tag)
        btn_layout.addWidget(self.add_random_btn)

        self.add_series_btn = QPushButton("Add Series")
        self.add_series_btn.clicked.connect(self.add_series_tag)
        btn_layout.addWidget(self.add_series_btn)

        self.edit_btn = QPushButton("Edit")
        self.edit_btn.clicked.connect(self.edit_tag)
        btn_layout.addWidget(self.edit_btn)

        self.delete_btn = QPushButton("Delete")
        self.delete_btn.clicked.connect(self.delete_tag)
        btn_layout.addWidget(self.delete_btn)

        tags_layout.addLayout(btn_layout)

        save_load_layout = QHBoxLayout()
        self.save_btn = QPushButton("Save All")
        self.save_btn.clicked.connect(self.save_tags)
        save_load_layout.addWidget(self.save_btn)

        self.load_btn = QPushButton("Load All")
        self.load_btn.clicked.connect(self.load_tags)
        save_load_layout.addWidget(self.load_btn)

        self.save_single_btn = QPushButton("Save Tag")
        self.save_single_btn.clicked.connect(self.save_single_tag)
        save_load_layout.addWidget(self.save_single_btn)

        self.load_single_btn = QPushButton("Load Tag")
        self.load_single_btn.clicked.connect(self.load_single_tag)
        save_load_layout.addWidget(self.load_single_btn)

        self.config_btn = QPushButton("Config")
        self.config_btn.clicked.connect(self.open_config)
        save_load_layout.addWidget(self.config_btn)

        tags_layout.addLayout(save_load_layout)

        main_layout.addWidget(self.tags_panel)

        self.preview_panel = QWidget()
        preview_layout = QVBoxLayout(self.preview_panel)

        self.preview_title = QLabel("24-Hour Schedule Preview")
        self.preview_title.setFont(QFont("", 16, QFont.Bold))
        preview_layout.addWidget(self.preview_title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.preview_list = QListWidget()
        scroll.setWidget(self.preview_list)
        preview_layout.addWidget(scroll)

        bottom_btn_layout = QHBoxLayout()
        
        self.view_group = QButtonGroup(self)
        self.daily_radio = QRadioButton("Daily")
        self.daily_radio.setChecked(True)
        self.weekly_radio = QRadioButton("Weekly (7 days)")
        self.monthly_radio = QRadioButton("Calendar (30 days)")
        self.view_group.addButton(self.daily_radio)
        self.view_group.addButton(self.weekly_radio)
        self.view_group.addButton(self.monthly_radio)
        bottom_btn_layout.addWidget(self.daily_radio)
        bottom_btn_layout.addWidget(self.weekly_radio)
        bottom_btn_layout.addWidget(self.monthly_radio)
        
        self.copy_btn = QPushButton("Copy Preview")
        self.copy_btn.clicked.connect(self.copy_preview)
        bottom_btn_layout.addWidget(self.copy_btn)

        self.generate_btn = QPushButton("Generate Preview")
        self.generate_btn.clicked.connect(self.generate_new_preview)
        bottom_btn_layout.addWidget(self.generate_btn)

        self.save_schedule_btn = QPushButton("Save Schedule")
        self.save_schedule_btn.clicked.connect(self.save_schedule)
        bottom_btn_layout.addWidget(self.save_schedule_btn)

        self.schedule_profile_combo = QComboBox()
        self.schedule_profile_combo.setEditable(True)
        self.load_schedule_profiles()
        bottom_btn_layout.addWidget(QLabel("Profile:"))
        bottom_btn_layout.addWidget(self.schedule_profile_combo)

        bottom_btn_layout.addStretch()

        self.approx_btn = QPushButton("Approximate OFF")
        self.approx_btn.setStyleSheet("background-color: #4a4a5e; color: #a0a0b0; font-weight: bold; padding: 10px 20px; border-radius: 6px;")
        self.approx_btn.clicked.connect(self.run_approximate)
        bottom_btn_layout.addWidget(self.approx_btn)

        preview_layout.addLayout(bottom_btn_layout)

        main_layout.addWidget(self.preview_panel)

        self.apply_styles()

    def apply_styles(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #1e1e2e; }
            QWidget { color: #f8f8f2; }
            QLabel { color: #f8f8f2; }
            QListWidget {
                background-color: #2a2a3e;
                border: 1px solid #3a3a4e;
                border-radius: 6px;
                padding: 8px;
                selection-background-color: #7c3aed;
                show-decoration-selected: 1;
            }
            QListWidget::item {
                padding: 8px;
                margin: 2px;
                border: 1px solid transparent;
            }
            QListWidget::item:selected {
                background-color: #7c3aed;
                border: 2px solid #a78bfa;
                color: white;
            }
            QListWidget::item:hover {
                background-color: #3a3a4e;
            }
            QPushButton {
                background-color: #2a2a3e;
                color: #f8f8f2;
                border: 1px solid #3a3a4e;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #3a3a4e; }
            QPushButton:pressed { background-color: #4a4a5e; }
            QLineEdit, QTimeEdit {
                background-color: #2a2a3e;
                color: #f8f8f2;
                border: 1px solid #3a3a4e;
                border-radius: 4px;
                padding: 8px;
            }
            QDialog { background-color: #1e1e2e; }
        """)
        self.tags_list.setSelectionMode(QListWidget.SingleSelection)
        self.tags_list.setFocusPolicy(Qt.StrongFocus)

    def load_default_tags(self):
        self.refresh_tags_list()

    def refresh_tags_list(self):
        self.tags_list.clear()
        for tag in self.tag_manager.tags:
            item = QListWidgetItem(tag.to_display_string())
            self.tags_list.addItem(item)

    def refresh_preview(self):
        self.preview_list.clear()
        if self.approximate_enabled:
            entries = self.schedule_generator.apply_approximate()
            self.preview_title.setText("24-Hour Schedule Preview [APPROXIMATE ON]")
            self.approx_btn.setText("APPROXIMATE ON")
            self.approx_btn.setStyleSheet("background-color: #22c55e; color: white; font-weight: bold; padding: 10px 20px; border-radius: 6px;")
            self.statusBar().showMessage("Approximate: ON")
        else:
            entries = self.schedule_generator.apply_custom_tags()
            self.preview_title.setText("24-Hour Schedule Preview [Approximate OFF]")
            self.approx_btn.setText("Approximate OFF")
            self.approx_btn.setStyleSheet("background-color: #4a4a5e; color: #a0a0b0; font-weight: bold; padding: 10px 20px; border-radius: 6px;")
            self.statusBar().showMessage("Approximate: OFF")
        self.schedule_entries = entries

        for entry in entries:
            self.preview_list.addItem(entry.to_display_string())

    def generate_new_preview(self):
        self.tag_manager.clear_cache()
        
        if self.weekly_radio.isChecked():
            self.generate_weekly_preview()
        elif self.monthly_radio.isChecked():
            self.generate_monthly_preview()
        else:
            self.refresh_preview()

    def generate_weekly_preview(self):
        self.preview_list.clear()
        self.preview_title.setText("Weekly Schedule Preview (7 Days)")
        
        from datetime import date
        start_date = date.today()
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        
        for day_offset in range(7):
            current_date = start_date + __import__('datetime').timedelta(days=day_offset)
            day_name = days[current_date.weekday()]
            self.preview_list.addItem(f"=== {current_date} - {day_name} ===")
            self.tag_manager.clear_cache()
            entries = self.schedule_generator.apply_custom_tags(num_days=7) if not self.approximate_enabled else self.schedule_generator.apply_approximate(num_days=7)
            for entry in entries:
                start_h = (entry.start_minutes // 60) % 24
                start_m = entry.start_minutes % 60
                end_h = (entry.end_minutes // 60) % 24
                end_m = entry.end_minutes % 60
                if entry.start_minutes == 0:
                    self.preview_list.addItem(f"Day {day_offset + 1}\n{start_h:02d}:{start_m:02d} - {end_h:02d}:{end_m:02d} - {entry.video_name}")
                else:
                    self.preview_list.addItem(f"{start_h:02d}:{start_m:02d} - {end_h:02d}:{end_m:02d} - {entry.video_name}")

    def generate_monthly_preview(self):
        self.preview_list.clear()
        self.preview_title.setText("Calendar Schedule Preview (30 Days)")
        
        from datetime import date
        start_date = date.today()
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        
        for day_offset in range(30):
            current_date = start_date + __import__('datetime').timedelta(days=day_offset)
            day_name = days[current_date.weekday()]
            self.preview_list.addItem(f"=== {current_date} - {day_name} ===")
            self.tag_manager.clear_cache()
            entries = self.schedule_generator.apply_custom_tags() if not self.approximate_enabled else self.schedule_generator.apply_approximate()
            for entry in entries:
                start_h = (entry.start_minutes // 60) % 24
                start_m = entry.start_minutes % 60
                end_h = (entry.end_minutes // 60) % 24
                end_m = entry.end_minutes % 60
                if entry.start_minutes == 0:
                    self.preview_list.addItem(f"Day {day_offset + 1}\n{start_h:02d}:{start_m:02d} - {end_h:02d}:{end_m:02d} - {entry.video_name}")
                else:
                    self.preview_list.addItem(f"{start_h:02d}:{start_m:02d} - {end_h:02d}:{end_m:02d} - {entry.video_name}")

    def save_tags(self):
        self.tag_manager.save_tags("tags.ini")
        self.statusBar().showMessage("Tags saved to tags.ini")

    def load_tags(self):
        if self.tag_manager.load_tags("tags.ini"):
            self.refresh_tags_list()
            self.refresh_preview()
            self.statusBar().showMessage("Tags loaded from tags.ini")
        else:
            self.statusBar().showMessage("No tags.ini found")

    def open_config(self):
        dialog = ConfigDialog(self)
        dialog.exec()

    def add_custom_tag(self):
        dialog = TagDialog(self)
        if dialog.exec():
            tag = dialog.get_tag()
            self.tag_manager.add_tag(tag)
            self.refresh_tags_list()
            self.refresh_preview()

    def add_random_fill_tag(self):
        dialog = RandomFillDialog(self)
        if dialog.exec():
            tag = dialog.get_tag()
            if tag is None:
                return
            self.tag_manager.add_tag(tag)
            self.refresh_tags_list()
            self.refresh_preview()

    def add_series_tag(self):
        dialog = SeriesDialog(self)
        if dialog.exec():
            tag = dialog.get_tag()
            if tag is None:
                return
            self.tag_manager.add_tag(tag)
            self.refresh_tags_list()
            self.refresh_preview()

    def edit_tag(self):
        current_row = self.tags_list.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "No Selection", "Please select a tag to edit.")
            return

        tag = self.tag_manager.tags[current_row]
        if tag.is_random_fill:
            dialog = RandomFillDialog(self, tag)
        elif tag.is_series:
            dialog = SeriesDialog(self, tag)
        else:
            dialog = TagDialog(self, tag)
        
        if dialog.exec():
            new_tag = dialog.get_tag()
            self.tag_manager.edit_tag(
                current_row, new_tag.name,
                new_tag.start_time, new_tag.end_time,
                new_tag.collection_videos,
                new_tag.collection_path,
                new_tag.video_count,
                new_tag.is_series,
                new_tag.start_season,
                new_tag.start_episode,
                new_tag.play_mode,
                new_tag.is_random_fill if hasattr(new_tag, 'is_random_fill') else False,
                new_tag.blacklist if hasattr(new_tag, 'blacklist') else [],
                new_tag.blacklist_path if hasattr(new_tag, 'blacklist_path') else '',
                new_tag.fill_24h if hasattr(new_tag, 'fill_24h') else False,
                new_tag.channel if hasattr(new_tag, 'channel') else ''
            )
            self.refresh_tags_list()
            self.refresh_preview()

    def delete_tag(self):
        current_row = self.tags_list.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "No Selection", "Please select a tag to delete.")
            return

        reply = QMessageBox.question(self, "Confirm Delete", "Are you sure you want to delete this tag?")
        if reply == QMessageBox.Yes:
            self.tag_manager.remove_tag(current_row)
            self.refresh_tags_list()
            self.refresh_preview()

    def copy_preview(self):
        text = "\n".join(entry.to_copy_string() for entry in self.schedule_entries)
        clipboard = QApplication.instance().clipboard()
        clipboard.setText(text)
        QMessageBox.information(self, "Copied", "Schedule copied to clipboard!")

    def load_schedule_profiles(self):
        profiles = get_schedule_profiles()
        self.schedule_profile_combo.clear()
        for profile in profiles:
            self.schedule_profile_combo.addItem(profile)

    def save_schedule(self):
        profile_name = self.schedule_profile_combo.currentText().strip()
        if not profile_name:
            QMessageBox.warning(self, "No Profile", "Please select or enter a schedule profile name.")
            return

        import json
        from datetime import date, timedelta

        collection_cache = {}

        def get_collection_info(collection_path):
            if collection_path in collection_cache:
                return collection_cache[collection_path]
            if not Path(collection_path).exists():
                return {}
            try:
                with open(collection_path, 'r') as f:
                    data = json.load(f)
                collections = data.get('collections', [])
                if collections:
                    coll = collections[0]
                    file_stem = Path(collection_path).stem
                    if file_stem.startswith('collections_'):
                        channel = file_stem.replace('collections_', '')
                    else:
                        channel = file_stem
                    info = {
                        'channel': channel,
                        'id': coll.get('id', channel)
                    }
                    collection_cache[collection_path] = info
                    return info
            except Exception:
                pass
            return {}

        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

        schedule_data = {
            "weekly": {},
            "calendar": {}
        }

        def get_schedule_entries_for_day(entries):
            schedule_entries = []
            for entry in entries:
                start_h = (entry.start_minutes // 60) % 24
                start_m = entry.start_minutes % 60
                time_str = f"{start_h:02d}:{start_m:02d}:00"

                video_name = entry.video_name

                video_info = {'time': time_str, 'file': '', 'collection_id': '', 'channel': '', 'source': 'random'}

                matched = False
                for tag in self.tag_manager.get_all_tags():
                    collection_path = getattr(tag, 'collection_path', '')
                    if collection_path and tag.collection_videos:
                        coll_info = get_collection_info(collection_path)
                        channel = coll_info.get('channel', '')
                        coll_id = coll_info.get('id', '')

                        for vid in tag.collection_videos:
                            vid_name = get_video_display_name(vid)
                            if vid_name in video_name or video_name in vid_name:
                                video_info['file'] = vid.get('path', '')
                                video_info['channel'] = channel
                                video_info['collection_id'] = coll_id
                                matched = True
                                break
                        if matched:
                            break

                if not video_info['file'] and ' - ' in video_name:
                    parts = video_name.split(' - ')
                    video_info['file'] = f"/home/akira/Videos/Akiratv/{parts[-1].strip()}"
                    video_info['channel'] = parts[0].strip()
                    video_info['collection_id'] = parts[0].strip()

                schedule_entries.append(video_info)
            return schedule_entries

        start_date = date.today()

        if self.weekly_radio.isChecked():
            num_days = 7
            save_key = "weekly"
        elif self.monthly_radio.isChecked():
            num_days = 30
            save_key = "calendar"
        else:
            num_days = 1
            save_key = "calendar"

        for day_offset in range(num_days):
            current_date = start_date + timedelta(days=day_offset)
            date_str = current_date.strftime("%Y-%m-%d")
            day_name = days[current_date.weekday()]
            key = f"{date_str}_{day_name.lower()}"

            entries = self.schedule_entries if self.schedule_entries else (self.schedule_generator.apply_custom_tags() if not self.approximate_enabled else self.schedule_generator.apply_approximate())

            schedule_entries = get_schedule_entries_for_day(entries)

            schedule_data[save_key][key] = {
                "date": date_str,
                "day": day_name,
                "description": "Auto-generated schedule",
                "entries": schedule_entries
            }

        file_path = f"schedule_{profile_name}.json"
        with open(file_path, 'w') as f:
            json.dump(schedule_data, f, indent=2)

        QMessageBox.information(self, "Saved", f"Schedule saved to {file_path}")
        self.statusBar().showMessage(f"Schedule saved to {file_path}")

    def run_approximate(self):
        self.approximate_enabled = not self.approximate_enabled
        self.tag_manager.clear_cache()
        if self.approximate_enabled:
            self.schedule_entries = self.schedule_generator.apply_approximate()
            self.preview_title.setText("24-Hour Schedule Preview [APPROXIMATE ON]")
            self.approx_btn.setText("APPROXIMATE ON")
            self.approx_btn.setStyleSheet("background-color: #22c55e; color: white; font-weight: bold; padding: 10px 20px; border-radius: 6px;")
            self.statusBar().showMessage("Approximate: ON")
        else:
            self.schedule_entries = self.schedule_generator.apply_custom_tags()
            self.preview_title.setText("24-Hour Schedule Preview [Approximate OFF]")
            self.approx_btn.setText("Approximate OFF")
            self.approx_btn.setStyleSheet("background-color: #4a4a5e; color: #a0a0b0; font-weight: bold; padding: 10px 20px; border-radius: 6px;")
            self.statusBar().showMessage("Approximate: OFF")
        self.preview_list.clear()
        for entry in self.schedule_entries:
            self.preview_list.addItem(entry.to_display_string())

    def save_single_tag(self):
        current_row = self.tags_list.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "No Selection", "Please select a tag to save.")
            return

        tag = self.tag_manager.tags[current_row]
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Tag", "", "INI Files (*.ini);;All Files (*)")
        if file_path:
            from serialization import save_single_tag_to_ini
            save_single_tag_to_ini(tag, file_path)
            self.statusBar().showMessage(f"Tag saved to {file_path}")

    def load_single_tag(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Load Tag", "", "INI Files (*.ini);;All Files (*)")
        if not file_path:
            return

        from serialization import load_single_tag_from_ini
        tag = load_single_tag_from_ini(file_path, Tag, QTime.fromString)
        if tag:
            self.tag_manager.add_tag(tag)
            self.refresh_tags_list()
            self.refresh_preview()
            self.statusBar().showMessage(f"Tag loaded from {file_path}")
        else:
            QMessageBox.warning(self, "Error", "Failed to load tag.")


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
