#!/usr/bin/env python3
import random
import re
from typing import List

# Minimal mock classes for testing
class Tag:
    def __init__(self, tag_type: str, name: str = "Random Fill",
                 start_time=None, end_time=None,
                 collection_videos: List[dict] = None,
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
                 fill_24h: bool = False):
        self.tag_type = tag_type
        self.name = name
        self.start_time = start_time or type('obj', (object,), {'hour': lambda s: 0, 'minute': lambda s: 0})()
        self.end_time = end_time or type('obj', (object,), {'hour': lambda s: 0, 'minute': lambda s: 0})()
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

    @staticmethod
    def qtime_to_minutes(qtime) -> int:
        return qtime.hour() * 60 + qtime.minute()


class ScheduleEntry:
    def __init__(self, day: int, start_minutes: int, end_minutes: int, video_name: str):
        self.day = day
        self.start_minutes = start_minutes
        self.end_minutes = end_minutes
        self.video_name = video_name

    def to_display_string(self) -> str:
        start_h = (self.start_minutes // 60) % 24
        start_m = self.start_minutes % 60
        end_h = (self.end_minutes // 60) % 24
        end_m = self.end_minutes % 60
        return f"Day {self.day} {start_h:02d}:{start_m:02d} - Day {self.day} {end_h:02d}:{end_m:02d} - {self.video_name}"


class TagManager:
    def __init__(self):
        self.tags: List[Tag] = []
    
    def get_all_tags(self) -> List[Tag]:
        return list(self.tags)
    
    def add_tag(self, tag: Tag):
        self.tags.append(tag)


class ScheduleGenerator:
    def __init__(self, tag_manager: TagManager):
        self.tag_manager = tag_manager

    def apply_approximate(self) -> List[ScheduleEntry]:
        print("=== apply_approximate called ===")
        all_tags = self.tag_manager.get_all_tags()
        
        print(f"Total tags: {len(all_tags)}")
        
        custom_tags = [t for t in all_tags if t.tag_type == "custom" and not t.is_random_fill and not t.is_series]
        series_tags = [t for t in all_tags if t.is_series]
        random_fill_tags = [t for t in all_tags if t.is_random_fill]
        
        print(f"custom_tags: {len(custom_tags)}, series_tags: {len(series_tags)}, random_fill_tags: {len(random_fill_tags)}")
        
        for i, t in enumerate(all_tags):
            print(f"  Tag {i}: type={t.tag_type}, name={t.name}, is_series={t.is_series}, is_random_fill={t.is_random_fill}, fill_24h={getattr(t, 'fill_24h', False)}")
        
        rf_24h_tags = [t for t in random_fill_tags if getattr(t, 'fill_24h', False)]
        print(f"rf_24h_tags: {len(rf_24h_tags)}")
        
        # If only 24h fill tags exist (no custom/series), return full random fill
        if rf_24h_tags and not custom_tags and not series_tags:
            print("Returning full 24h random fill (no other tags)")
            return self.generate_random_fill(24 * 60)
        
        # If we have 24h fill tags, we only fill in gaps between explicit time ranges
        has_24h_fill = bool(rf_24h_tags)
        
        if has_24h_fill:
            # Skip base_entries generation - we'll only fill gaps
            base_entries = []
        else:
            base_entries = self.generate_random_fill(24 * 60)

        if not custom_tags and not series_tags and not random_fill_tags:
            return base_entries

        custom_sorted = sorted(custom_tags, key=lambda t: Tag.qtime_to_minutes(t.start_time))

        final = []
        rand_idx = 0
        current_pos = 0
        next_custom_pos = 0
        
        scheduled_ranges = []
        
        for ct in custom_sorted:
            original_start = Tag.qtime_to_minutes(ct.start_time)
            original_end = Tag.qtime_to_minutes(ct.end_time)
            scheduled_ranges.append((original_start, original_end))
        
        for st in series_tags:
            original_start = Tag.qtime_to_minutes(st.start_time)
            original_end = Tag.qtime_to_minutes(st.end_time)
            scheduled_ranges.append((original_start, original_end))
        
        for rf in random_fill_tags:
            rf_fill_24h = getattr(rf, 'fill_24h', False)
            if not rf_fill_24h:
                rf_start = Tag.qtime_to_minutes(rf.start_time)
                rf_end = Tag.qtime_to_minutes(rf.end_time)
                if rf_start < rf_end:
                    scheduled_ranges.append((rf_start, rf_end))
        
        scheduled_ranges.sort()
        
        print(f"scheduled_ranges: {scheduled_ranges}")
        
        merged_ranges = []
        for start, end in scheduled_ranges:
            if merged_ranges and start <= merged_ranges[-1][1]:
                merged_ranges[-1] = (merged_ranges[-1][0], max(merged_ranges[-1][1], end))
            else:
                merged_ranges.append((start, end))
        
        print(f"merged_ranges: {merged_ranges}")
        
        occupied = set()

        # With 24h fill, just process custom/series tags without pre-filling
        for ct in custom_sorted:
            original_start = Tag.qtime_to_minutes(ct.start_time)
            original_end = Tag.qtime_to_minutes(ct.end_time)

            custom_start = original_start
            custom_end = original_end

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
                    video_name = video.get('path', 'Unknown').split('/')[-1]
                    duration = int(video.get('duration', 90)) // 60
                    if duration < 1:
                        duration = 1
                    if pos + duration > custom_end:
                        duration = custom_end - pos
                    if duration < 1:
                        break
                    final.append(ScheduleEntry(1, pos, pos + duration, f"{ct.name} - {video_name}"))
                    pos += duration
                    vid_idx += 1
                    current_pos = custom_end
            else:
                final.append(ScheduleEntry(1, custom_start, custom_end, ct.name))
                current_pos = custom_end

            next_custom_pos = current_pos

        for st in series_tags:
            original_start = Tag.qtime_to_minutes(st.start_time)
            original_end = Tag.qtime_to_minutes(st.end_time)
            if original_start >= original_end:
                continue
            if original_start >= 24 * 60 or original_end > 24 * 60:
                continue

            series_start = original_start
            series_end = original_end

            if st.collection_videos:
                for m in range(series_start, series_end):
                    occupied.add(m)

                start_season = getattr(st, 'start_season', 1)
                start_episode = getattr(st, 'start_episode', 1)
                play_mode = getattr(st, 'play_mode', 'sequence')
                video_count = getattr(st, 'video_count', 1)

                parsed_videos = []
                for vid in st.collection_videos:
                    path = vid.get('path', '')
                    name = path.split('/')[-1] if '/' in path else path
                    season, episode = 1, 1
                    match = re.search(r'[Ss](\d+)[Ee](\d+)', name)
                    if match:
                        season = int(match.group(1))
                        episode = int(match.group(2))
                    else:
                        match = re.search(r'Season\s*(\d+)\s*Episode\s*(\d+)', name, re.IGNORECASE)
                        if match:
                            season = int(match.group(1))
                            episode = int(match.group(2))
                    parsed_videos.append({
                        'video': vid,
                        'season': season,
                        'episode': episode,
                        'path': path,
                        'name': name
                    })

                filtered = [v for v in parsed_videos if v['season'] > start_season or (v['season'] == start_season and v['episode'] >= start_episode)]

                if play_mode == 'random':
                    random.shuffle(filtered)
                else:
                    filtered.sort(key=lambda v: (v['season'], v['episode']))

                videos_to_use = filtered[:video_count]
                print(f"  videos_to_use: {len(videos_to_use)}")
                pos = series_start
                print(f"  Adding series entries starting at {pos}, series_end={series_end}, videos_to_use={len(videos_to_use)}")
                for v in videos_to_use:
                    if pos >= series_end:
                        print(f"    Breaking: pos={pos} >= series_end={series_end}")
                        break
                    video = v['video']
                    video_name = video.get('path', 'Unknown').split('/')[-1]
                    duration = int(video.get('duration', 90)) // 60
                    if duration < 1:
                        duration = 1
                    if pos + duration > series_end:
                        duration = series_end - pos
                    if duration < 1:
                        print(f"    Breaking: duration={duration} < 1")
                        break
                    print(f"    Appending: {st.name} - {video_name} at {pos}-{pos+duration}")
                    final.append(ScheduleEntry(1, pos, pos + duration, f"{st.name} - {video_name}"))
                    pos += duration
                print(f"  After series loop, pos={pos}")
                current_pos = series_end
            else:
                final.append(ScheduleEntry(1, series_start, series_end, st.name))
                current_pos = series_end

            next_custom_pos = current_pos

        rf_sorted = sorted(random_fill_tags, key=lambda t: Tag.qtime_to_minutes(t.start_time))
        
        for rf in rf_sorted:
            rf_fill_24h = getattr(rf, 'fill_24h', False)
            
            if rf_fill_24h:
                print(f"Processing 24h fill tag: {rf.name}")
                rf_videos = rf.collection_videos.copy() if rf.collection_videos else []
                if not rf_videos:
                    continue
                random.shuffle(rf_videos)
                
                gaps = []
                prev_end = 0
                for start, end in merged_ranges:
                    if start > prev_end:
                        gaps.append((prev_end, start))
                    prev_end = max(prev_end, end)
                if prev_end < 24 * 60:
                    gaps.append((prev_end, 24 * 60))
                
                print(f"Gaps to fill: {gaps}")
                
                for gap_start, gap_end in gaps:
                    pos = gap_start
                    vid_idx = 0
                    while pos < gap_end:
                        video = rf_videos[vid_idx % len(rf_videos)]
                        video_name = video.get('path', 'Unknown').split('/')[-1]
                        duration = int(video.get('duration', 90)) // 60
                        if duration < 1:
                            duration = 1
                        if pos + duration > gap_end:
                            duration = gap_end - pos
                        if duration < 1:
                            break
                        final.append(ScheduleEntry(1, pos, pos + duration, f"{rf.name} - {video_name}"))
                        pos += duration
                        vid_idx += 1

        print(f"After fill loop: current_pos={current_pos}, rand_idx={rand_idx}, base_entries_len={len(base_entries)}")

        final.sort(key=lambda e: e.start_minutes)
        
        unique_entries = []
        seen_times = set()
        for entry in final:
            key = (entry.start_minutes, entry.end_minutes)
            if key not in seen_times:
                seen_times.add(key)
                unique_entries.append(entry)
        
        print(f"=== Returning {len(unique_entries)} entries ===")
        return unique_entries

    def generate_random_fill(self, remaining_minutes: int = 24 * 60) -> List[ScheduleEntry]:
        all_tags = self.tag_manager.get_all_tags()
        collection_videos = []
        for tag in all_tags:
            if tag.collection_videos:
                collection_videos.extend(tag.collection_videos)
        
        if not collection_videos:
            return []
        
        entries = []
        random.shuffle(collection_videos)
        video_index = 0
        current_minute = 0
        current_day = 1

        while current_minute < remaining_minutes:
            video = collection_videos[video_index % len(collection_videos)]
            video_name = video.get('path', 'Unknown').split('/')[-1]
            duration = int(video.get('duration', 90)) // 60
            if duration < 1:
                duration = 90
            end_minute = current_minute + duration

            if end_minute > remaining_minutes:
                end_minute = remaining_minutes

            entries.append(ScheduleEntry(current_day, current_minute, end_minute, video_name))
            current_minute = end_minute
            video_index += 1

        return entries


# Mock QTime
class MockQTime:
    def __init__(self, hour, minute):
        self._hour = hour
        self._minute = minute
    
    def hour(self):
        return self._hour
    
    def minute(self):
        return self._minute
    
    @staticmethod
    def fromString(time_str, format_str):
        parts = time_str.split(':')
        return MockQTime(int(parts[0]), int(parts[1]))


# Test
print("=== Debug Test ===")

tm = TagManager()

# Add series tag (Superman Cartoon) with some collection videos
series_videos = [
    {'path': '/videos/01.avi', 'duration': 1200},
    {'path': '/videos/02.avi', 'duration': 1140},
]
series_tag = Tag('custom', 'Superman Cartoon', MockQTime(10, 0), MockQTime(10, 39), series_videos, '', video_count=2, is_series=True, start_season=1, start_episode=1, play_mode='sequence')
tm.add_tag(series_tag)
print("Added series tag: Superman Cartoon 10:00-10:39")

# Add 24h random fill tag (AkiraTV) with some collection videos
rf_videos = [
    {'path': '/videos/movie1.mp4', 'duration': 5400},
    {'path': '/videos/movie2.mp4', 'duration': 6000},
    {'path': '/videos/movie3.mp4', 'duration': 4800},
]
rf_tag = Tag('random', 'AkiraTV', MockQTime(0, 0), MockQTime(23, 59), rf_videos, '/home/akira/akira/AkiraTV_NEW/user/collections/collections_akiratv.json', is_random_fill=True, fill_24h=True)
tm.add_tag(rf_tag)
print("Added 24h fill tag: AkiraTV")

sg = ScheduleGenerator(tm)
print("\n=== Calling apply_approximate ===")
entries = sg.apply_approximate()

print(f"\n=== Result: {len(entries)} entries ===")
for i, e in enumerate(entries[:15]):
    print(f"  {i}: {e.to_display_string()}")
if len(entries) > 15:
    print(f"  ... and {len(entries) - 15} more")