import json
import os
import re
import configparser
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
from PySide6.QtCore import QTime


def load_collection_json(file_path: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    collection_videos = []
    collection_info = {}

    if not file_path or not Path(file_path).exists():
        return collection_videos, collection_info

    try:
        with open(file_path, 'r') as f:
            data = json.load(f)

        collections = data.get('collections', [])
        # Build mapping: collection_id -> collection_info
        collection_info = {}
        for coll in collections:
            coll_id = coll.get('id', '')
            if coll_id:
                collection_info[coll_id] = {
                    'name': coll.get('name', ''),
                    'cover': coll.get('cover', ''),
                    'description': coll.get('description', ''),
                    'genre': coll.get('genre', []),
                    'year': coll.get('year', ''),
                    'tags': coll.get('tags', [])
                }

        for coll in collections:
            coll_id = coll.get('id', '')
            coll_tags = coll.get('tags', [])
            series_name = _extract_tag_value(coll_tags, 'Series:')
            season_str = _extract_tag_value(coll_tags, 'Season:')
            season = None
            if season_str and season_str.isdigit():
                season = int(season_str)
            movie_num, part_num = _extract_movie_tag(coll_tags)
            for video in coll.get('videos', []):
                video_copy = video.copy()
                video_copy['collection_id'] = coll_id
                video_copy['_meta_series'] = series_name
                video_copy['_meta_season'] = season
                video_copy['_meta_movie'] = movie_num
                video_copy['_meta_part'] = part_num
                video_copy['_meta_tags'] = coll_tags
                collection_videos.append(video_copy)
    except Exception:
        pass

    return collection_videos, collection_info


def _extract_tag_value(tags: List[str], prefix: str) -> Optional[str]:
    """Extract first tag value with given prefix like 'Series:' or 'Season:'."""
    if not tags:
        return None
    for tag in tags:
        if tag.startswith(prefix):
            value = tag[len(prefix):].strip()
            return value if value else None
    return None


def _extract_movie_tag(tags: List[str]) -> Tuple[Optional[int], Optional[int]]:
    """Scan tags for movie sequence identifiers.

    Returns: (movie_number, part_number) or (None, None) if no movie tag found.

    Tag formats matched:
    - Purely numeric: "3" -> movie=3
    - "Movie: N", "Movie N", "movie N" -> movie=N
    - "Part: N", "Part N", "part N" -> part=N
    """
    movie = None
    part = None

    for tag in tags:
        tag_stripped = tag.strip()

        # Purely numeric tag -> movie number
        if tag_stripped.isdigit():
            movie = int(tag_stripped)
            continue

        # Check for "Movie: N" or "movie N" etc. (anywhere in the tag, e.g. "video movie 1")
        m = re.search(r'\b(?:movie|film)[:\s]*(\d+)', tag_stripped, re.IGNORECASE)
        if m:
            movie = int(m.group(1))
            continue

        # Check for "Part: N" or "part N" etc. (anywhere in the tag, with word boundary
        # so we don't false-match "transport 7" -> part=7)
        m = re.search(r'\bpart[:\s]*(\d+)', tag_stripped, re.IGNORECASE)
        if m:
            part = int(m.group(1))
            continue

    return (movie, part)  # either or both may be None


def load_collection_videos_only(file_path: str) -> List[Dict[str, Any]]:
    if not file_path or not Path(file_path).exists():
        return []

    try:
        with open(file_path, 'r') as f:
            data = json.load(f)

        collections = data.get('collections', [])
        if not collections:
            return []

        videos = []
        for coll in collections:
            coll_id = coll.get('id', '')
            coll_tags = coll.get('tags', [])
            series_name = _extract_tag_value(coll_tags, 'Series:')
            season_str = _extract_tag_value(coll_tags, 'Season:')
            season = None
            if season_str and season_str.isdigit():
                season = int(season_str)
            movie_num, part_num = _extract_movie_tag(coll_tags)

            for video in coll.get('videos', []):
                video_copy = video.copy()
                video_copy['collection_id'] = coll_id
                video_copy['_meta_series'] = series_name
                video_copy['_meta_season'] = season
                video_copy['_meta_movie'] = movie_num
                video_copy['_meta_part'] = part_num
                video_copy['_meta_tags'] = coll_tags
                videos.append(video_copy)

        return videos
    except Exception:
        return []


def parse_series_episode(path: str) -> Tuple[int, int]:
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
        else:
            match = re.match(r'(\d+)\s', name)
            if match:
                episode = int(match.group(1))

    return season, episode


def parse_videos_for_series(videos: List[Dict[str, Any]], start_season: int = 1,
                            start_episode: int = 1, play_mode: str = "sequence",
                            video_count: int = 1) -> Tuple[List[Dict[str, Any]], int]:
    parsed_videos = []
    for idx, vid in enumerate(videos):
        path = vid.get('path', '')
        season, episode = parse_series_episode(path)
        parsed_videos.append({
            'video': vid,
            'season': season,
            'episode': episode,
            'path': path,
            'name': path.split('/')[-1] if '/' in path else path,
            'index': idx
        })

    filtered = [v for v in parsed_videos
                if v['season'] > start_season or (v['season'] == start_season and v['episode'] >= start_episode)]

    if play_mode == 'random':
        import random
        random.shuffle(filtered)
    else:
        filtered.sort(key=lambda v: (v['season'], v['episode'], v['index']))
    
    return filtered[:video_count], len(filtered)


def load_blacklist_json(file_path: str) -> List[Dict[str, Any]]:
    blacklist = []
    
    if not file_path or not Path(file_path).exists():
        return blacklist
    
    try:
        if file_path.endswith('.ini'):
            bc = configparser.ConfigParser()
            bc.read(file_path)
            if 'Blacklist' in bc:
                for key in bc['Blacklist']:
                    value = bc['Blacklist'][key]
                    paths = [p.strip() for p in value.split('\n') if p.strip()]
                    for path in paths:
                        blacklist.append({'path': path})
        else:
            with open(file_path, 'r') as f:
                blacklist = json.load(f).get('blacklist', [])
    except Exception:
        pass
    
    return blacklist


def qtime_to_minutes(qtime: QTime) -> int:
    return qtime.hour() * 60 + qtime.minute()


def qtime_to_seconds(qtime: QTime) -> int:
    return qtime.hour() * 3600 + qtime.minute() * 60 + qtime.second()


def minutes_to_qtime(minutes: int) -> QTime:
    return QTime(minutes // 60, minutes % 60)


def seconds_to_qtime(seconds: int) -> QTime:
    return QTime(seconds // 3600, (seconds % 3600) // 60, seconds % 60)


def get_video_display_name(video: Dict[str, Any]) -> str:
    path = video.get('path', '')
    return path.split('/')[-1] if '/' in path else path


def format_duration(duration_seconds: int) -> str:
    return f"{int(duration_seconds)}s"


def get_config_paths(config_file: str = "config.ini") -> Tuple[str, str]:
    try:
        config = configparser.ConfigParser()
        config.read(config_file)
        collection_path = config.get('Paths', 'collection_path', fallback='/home/akira/akira/AkiraTV_NEW/user/collections')
        blacklist_path = config.get('Paths', 'blacklist_path', fallback='/home/akira/akira/AkiraTV_NEW/user/collections')
    except Exception:
        collection_path = '/home/akira/akira/AkiraTV_NEW/user/collections'
        blacklist_path = '/home/akira/akira/AkiraTV_NEW/user/collections'
    
    return collection_path, blacklist_path


def get_schedule_profiles(config_file: str = "config.ini") -> List[str]:
    try:
        config = configparser.ConfigParser()
        config.read(config_file)
        profiles = config.get('ScheduleProfiles', 'profiles', fallback='')
        if profiles:
            return [p.strip() for p in profiles.split(',') if p.strip()]
    except Exception:
        pass
    return []


def is_video_in_blacklist(video: Dict[str, Any], blacklist: List[Dict[str, Any]]) -> bool:
    """Check if a video matches any blacklist entry by path or basename.

    Matches by exact path first. If that fails, matches by basename (filename)
    to catch cases where files were moved between directories.
    """
    vpath = video.get('path', '')
    if not vpath:
        return False
    vname = os.path.basename(vpath)
    for b in blacklist:
        bpath = b.get('path', '')
        if bpath == vpath:
            return True
        if bpath and os.path.basename(bpath) == vname:
            return True
    return False


def filter_videos_by_blacklist(videos: List[Dict[str, Any]], blacklist: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [v for v in videos if not is_video_in_blacklist(v, blacklist)]


def get_randomfill_config(config_file: str = "config.ini") -> bool:
    """Read auto_add setting from [RandomFill] section. Default False."""
    try:
        config = configparser.ConfigParser()
        config.read(config_file)
        if 'RandomFill' in config:
            val = config['RandomFill'].get('auto_add', 'false').lower()
            return val in ('true', '1', 'yes', 'on')
    except Exception:
        pass
    return False


def get_covers_path(config_file: str = "config.ini") -> Optional[Path]:
    """Read covers_path from [Paths] section. Returns None if not set."""
    try:
        config = configparser.ConfigParser()
        config.read(config_file)
        if 'Paths' in config:
            p = config['Paths'].get('covers_path', '').strip()
            if p:
                return Path(p)
    except Exception:
        pass
    return None


def extract_movie_sequence_key(video_or_path) -> Tuple[int, int]:
    """Extract (movie_number, part_number) from a video dict or path string.
    
    If given a dict, first checks for explicit movie metadata (_meta_movie).
    If _meta_movie is set, returns it immediately with _meta_part (default 0).
    Otherwise falls back to parsing 'name' or 'path' from the dict (or the
    string itself when given a path string).
    
    Patterns matched (in order of precedence):
    1. _meta_movie / _meta_part from video dict (if present) -> return immediately
    2. Filename parsing: existing behavior
       1. Explicit movie/film markers: "Movie 1", "Film 1" -> movie from marker
          Part can be indicated by "Part 2" or "x2" suffix.
       2. Standalone "Part N" at start indicates movie number (e.g., "Part 7" -> movie 7, part 0).
       3. Leading number: "1 - Video Name" -> movie=1, part=0.
       4. Two number groups: "1x02" or "S01E02" -> movie=first, part=second.
    
    Returns: (movie_num, part_num) with defaults (1, 0)
    """
    # 1. Explicit movie metadata from dict (set by _extract_movie_tag via collection JSON tags)
    if isinstance(video_or_path, dict):
        meta_movie = video_or_path.get('_meta_movie')
        if meta_movie is not None:
            meta_part = video_or_path.get('_meta_part', 0) or 0
            return (meta_movie, meta_part)
        # else: fall through to filename parsing

    # Determine source string
    if isinstance(video_or_path, dict):
        name = video_or_path.get('name', '')
        if not name:
            name = video_or_path.get('path', '')
    else:
        name = str(video_or_path)
    
    # Strip extension if this looks like a file path
    if '/' in name or ('.' in name and '\\' not in name):
        name = Path(name).stem
    
    # 1. Check for explicit movie/film markers
    movie_match = re.search(r'(?:movie|film)\s*(\d+)', name, re.IGNORECASE)
    if movie_match:
        movie = int(movie_match.group(1))
        # Look for explicit part number: "Part N" or "xN"
        part_match = re.search(r'part\s*(\d+)', name, re.IGNORECASE)
        if part_match:
            part = int(part_match.group(1))
        else:
            x_match = re.search(r'x(\d+)', name, re.IGNORECASE)
            part = int(x_match.group(1)) if x_match else 0
        return (movie, part)
    
    # 2. Standalone "Part N" at start indicates movie number
    part_only_match = re.match(r'part\s*(\d+)', name, re.IGNORECASE)
    if part_only_match:
        movie = int(part_only_match.group(1))
        return (movie, 0)
    
    # 3. Extract all number sequences
    numbers = [int(n) for n in re.findall(r'\d+', name)]
    if not numbers:
        return (1, 0)
    if len(numbers) == 1:
        return (numbers[0], 0)
    return (numbers[0], numbers[1])


def group_videos_by_movie(videos: List[Dict]) -> Dict[int, List[Dict]]:
    """Group videos into movie buckets sorted by movie number.
    Within each group, sort by part number then preserve original order.
    Returns: {movie_num: [video1, video2, ...]} sorted by movie_num ascending.
    
    Duplicate videos (same id) are removed to prevent scheduling the same
    video multiple times within a single day. Falls back to path if id is missing.
    """
    # Deduplicate by id to avoid showing same video multiple times
    seen_ids = set()
    seen_paths = set()
    unique_videos = []
    for v in videos:
        vid_id = v.get('id')
        if vid_id is not None:
            if vid_id not in seen_ids:
                seen_ids.add(vid_id)
                unique_videos.append(v)
        else:
            # Fallback to path if id not present
            path = v.get('path', '')
            if path not in seen_paths:
                seen_paths.add(path)
                unique_videos.append(v)
    
    groups = {}
    for v in unique_videos:
        movie_num, part_num = extract_movie_sequence_key(v)
        groups.setdefault(movie_num, []).append((part_num, v))
    
    result = {}
    for movie_num in sorted(groups.keys()):
        # Sort by part number, then by original order
        items = sorted(groups[movie_num], key=lambda x: x[0])
        result[movie_num] = [v for _, v in items]
    return result


def load_gap_collections(collections_config: List[Dict]) -> List[Dict]:
    """Load and pool all videos from a gap tag's collection configs.

    Each entry in collections_config should have:
        {"path": "/path/to/file.json", "type": "trailer"}

    The type field is stored for display only; all videos are pooled together.
    Returns a flat list of video dicts.
    """
    all_videos = []
    seen_paths = set()
    for entry in collections_config:
        path = entry.get("path", "")
        if not path:
            continue
        videos = load_collection_videos_only(path)
        for v in videos:
            vpath = v.get("path", "")
            if vpath not in seen_paths:
                seen_paths.add(vpath)
                all_videos.append(v)
    return all_videos


def normalize_tag_time_range(tag) -> Tuple[int, int]:
    """Get (start_seconds, end_seconds) from a tag, normalizing midnight wrap.

    When a tag's end_time is before its start_time (e.g. 18:00-00:19),
    adds 86400 to end_seconds so the range represents the correct duration.
    """
    start_sec = qtime_to_seconds(tag.start_time)
    end_sec = qtime_to_seconds(tag.end_time)
    if end_sec <= start_sec:
        end_sec += 86400
    return start_sec, end_sec
