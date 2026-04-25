#!/usr/bin/env python3
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

    def _place_tag_videos(self, ct, start: int, end: int, final: List[ScheduleEntry]) -> int:
        """Place custom/series tag videos into final schedule. Returns new current_pos."""
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

        start_min += day_offset * 24 * 60 + start_offset
        end_min += day_offset * 24 * 60 + start_offset

        if start_min >= end_min:
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
        all_tags = self.tag_manager.get_all_tags()

        cached = self.tag_manager.get_cached_random_entries()
        if use_cache and cached is not None:
            return self._inject_custom_tags(cached)

        custom_tags = [t for t in all_tags if t.tag_type == "custom" and not t.is_random_fill and not t.is_series]
        series_tags = [t for t in all_tags if t.is_series]
        random_fill_tags = [t for t in all_tags if t.is_random_fill]

        if not custom_tags and not series_tags and not random_fill_tags:
            entries = self.generate_random_fill(24 * 60 * num_days)
            self.tag_manager.set_cached_random_entries(entries)
            return entries

        occupied = set()
        custom_entries = []
        series_entries = []
        fill_entries = []
        continuation_pos = None
        
        for day_offset in range(num_days):
            day_offset_minutes = day_offset * 24 * 60
            for ct in custom_tags:
                self._process_custom_tag(ct, custom_entries, occupied, day_offset_minutes)

            for st in series_tags:
                self._process_series_tag(st, series_entries, occupied, day_offset, day_offset_minutes)

        rf_sorted = sorted(random_fill_tags, key=lambda t: qtime_to_minutes(t.start_time))
        
        if any(getattr(rf, 'fill_24h', False) for rf in rf_sorted):
            for day_offset in range(num_days):
                day_offset_minutes = day_offset * 24 * 60
                for rf in rf_sorted:
                    if getattr(rf, 'fill_24h', False):
                        merged = [(e.start_minutes, e.end_minutes) for e in custom_entries + series_entries]
                        self._process_random_fill_tag(rf, fill_entries, merged, 0, day_offset_minutes)
        else:
            rf_start = qtime_to_minutes(rf_sorted[0].start_time) if rf_sorted else 0
            rf_end = qtime_to_minutes(rf_sorted[0].end_time) if rf_sorted else 24 * 60
            
            rf_videos = rf_sorted[0].collection_videos.copy() if rf_sorted and rf_sorted[0].collection_videos else []
            if rf_videos:
                random.shuffle(rf_videos)
            
            total_minutes = num_days * 24 * 60
            fill_entries.extend(self._build_random_entries(rf_videos, rf_start, total_minutes, rf_sorted[0].name))

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
                            merged = [(e.start_minutes, e.end_minutes) for e in custom_entries + series_entries]
                            self._process_random_fill_tag(rf, fill_entries, merged, start_vid_idx, day_offset_minutes)

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

    def apply_approximate(self, num_days: int = 1, mode: str = "find_replace") -> List[ScheduleEntry]:
        all_tags = self.tag_manager.get_all_tags()
        
        custom_tags = [t for t in all_tags if t.tag_type == "custom" and not t.is_random_fill and not t.is_series]
        series_tags = [t for t in all_tags if t.is_series]
        random_fill_tags = [t for t in all_tags if t.is_random_fill]
        
        rf_24h_tags = [t for t in random_fill_tags if getattr(t, 'fill_24h', False)]
        
        if rf_24h_tags and not custom_tags and not series_tags:
            return self.generate_random_fill(24 * 60 * num_days)
        
        has_24h_fill = bool(rf_24h_tags)
        
        if has_24h_fill:
            base_entries = []
        else:
            base_entries = self.generate_random_fill(24 * 60) if (custom_tags or series_tags) else []

        if not custom_tags and not series_tags and not random_fill_tags:
            return base_entries

        if mode == "linear":
            return self._apply_approximate_linear(num_days, custom_tags, series_tags, random_fill_tags, has_24h_fill)
        else:
            return self._apply_approximate_find_replace(num_days, custom_tags, series_tags, random_fill_tags, has_24h_fill)

    def _apply_approximate_find_replace(self, num_days: int, custom_tags: list, series_tags: list, random_fill_tags: list, has_24h_fill: bool) -> List[ScheduleEntry]:
        """Find-and-replace algorithm: Don't truncate random fill, move custom tags instead."""
        rf_sorted = sorted(random_fill_tags, key=lambda t: qtime_to_minutes(t.start_time))
        
        if not rf_sorted:
            return self._apply_approximate_linear(num_days, custom_tags, series_tags, random_fill_tags, has_24h_fill)
        
        rf_name = rf_sorted[0].name
        rf_videos = rf_sorted[0].collection_videos.copy() if rf_sorted and rf_sorted[0].collection_videos else []
        if rf_videos:
            random.shuffle(rf_videos)
        
        total_minutes = num_days * 24 * 60
        random_entries = self._build_random_entries(rf_videos, 0, total_minutes, rf_name)
        
        final = []
        APPROXIMATE_THRESHOLD = 40
        
        all_custom_sorted = sorted(custom_tags + series_tags, key=lambda t: qtime_to_minutes(t.start_time))
        
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
            
            for ct, orig_start, orig_end, custom_start, custom_end in day_customs:
                # Find random entries that overlap OR end close to custom start
                overlapping = [e for e in day_unused if e.start_minutes < custom_end and e.end_minutes > custom_start]
                close_before = [e for e in day_unused if e.end_minutes <= custom_start and e.end_minutes > custom_start - APPROXIMATE_THRESHOLD]
                randoms_in_range = overlapping + close_before
                
                if randoms_in_range:
                    best_rand = None
                    best_gap = float('inf')
                    best_idx = -1
                    
                    for rand_e in randoms_in_range:
                        gap = abs(rand_e.end_minutes - custom_start)
                        if gap < best_gap and gap <= APPROXIMATE_THRESHOLD:
                            best_gap = gap
                            best_rand = rand_e
                            for idx, re in enumerate(random_entries):
                                if re is rand_e and (idx not in used_random):
                                    best_idx = idx
                                    break
                    
                    if best_rand and best_idx >= 0:
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
                        
                        new_start = best_rand.end_minutes
                        new_end = new_start + (orig_end - orig_start)
                        
                        current_pos = self._place_tag_videos(ct, new_start, new_end, final)
                        
                        # Mark random entries that overlap with placed custom tag as used, add remaining portion to final
                        for re in day_unused[:]:
                            if re.start_minutes < current_pos and re.end_minutes > new_start:
                                for idx, orig_re in enumerate(random_entries):
                                    if orig_re is re and idx not in used_random:
                                        used_random.add(idx)
                                        remaining_start = current_pos
                                        remaining_end = re.end_minutes
                                        if remaining_end > remaining_start:
                                            final.append(ScheduleEntry(1, remaining_start, remaining_end, re.video_name))
                                        break
                    else:
                        if custom_start < current_pos:
                            custom_start = current_pos
                            custom_end = custom_start + (orig_end - orig_start)
                        
                        # Remove overlapping random entries from day_unused
                        for re in day_unused[:]:
                            if re.start_minutes < custom_end and re.end_minutes > custom_start:
                                for idx, orig_re in enumerate(random_entries):
                                    if orig_re is re and idx not in used_random:
                                        used_random.add(idx)
                                        day_unused.remove(re)
                                        break
                        
                        current_pos = self._place_tag_videos(ct, custom_start, custom_end, final)
                else:
                    if custom_start < current_pos:
                        custom_start = current_pos
                        custom_end = custom_start + (orig_end - orig_start)
                    
                    # Remove overlapping random entries from day_unused
                    for re in day_unused[:]:
                        if re.start_minutes < custom_end and re.end_minutes > custom_start:
                            for idx, orig_re in enumerate(random_entries):
                                if orig_re is re and idx not in used_random:
                                    used_random.add(idx)
                                    day_unused.remove(re)
                                    break
                    
                    current_pos = self._place_tag_videos(ct, custom_start, custom_end, final)
            
            # Add unused random entries from day_start to current_pos
            day_unused = [e for i, e in enumerate(random_entries) 
                              if i not in used_random 
                              and e.start_minutes < day_end 
                              and e.end_minutes > day_start]
            day_unused.sort(key=lambda e: e.start_minutes)
            
            for rand_e in day_unused:
                if rand_e.start_minutes >= current_pos:
                    continue
                if rand_e.end_minutes <= current_pos:
                    final.append(rand_e)
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

    def _apply_approximate_linear(self, num_days: int, custom_tags: list, series_tags: list, random_fill_tags: list, has_24h_fill: bool) -> List[ScheduleEntry]:
        """Linear placement: Truncate random fill to make room for custom tags."""
        all_tags = self.tag_manager.get_all_tags()
        
        custom_tags = [t for t in all_tags if t.tag_type == "custom" and not t.is_random_fill and not t.is_series]
        series_tags = [t for t in all_tags if t.is_series]
        random_fill_tags = [t for t in all_tags if t.is_random_fill]
        
        rf_24h_tags = [t for t in random_fill_tags if getattr(t, 'fill_24h', False)]
        
        if rf_24h_tags and not custom_tags and not series_tags:
            return self.generate_random_fill(24 * 60 * num_days)
        
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
                current_pos = actual_end

        rf_sorted = sorted(random_fill_tags, key=lambda t: qtime_to_minutes(t.start_time))
        
        if not has_24h_fill:
            rf_start = qtime_to_minutes(rf_sorted[0].start_time) if rf_sorted else 0
            rf_end = qtime_to_minutes(rf_sorted[0].end_time) if rf_sorted else 24 * 60
            
            rf_videos = rf_sorted[0].collection_videos.copy() if rf_sorted and rf_sorted[0].collection_videos else []
            if rf_videos:
                random.shuffle(rf_videos)
            
            total_minutes = num_days * 24 * 60
            final.extend(self._build_random_entries(rf_videos, rf_start, total_minutes, rf_sorted[0].name))
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