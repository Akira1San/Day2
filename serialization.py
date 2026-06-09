import json
import configparser
from typing import List, Any, Optional, Dict
from pathlib import Path

from utils import load_collection_videos_only, load_blacklist_json, get_config_paths


def serialize_tag_to_string(tag) -> str:
    lines = ["[Tag]"]
    
    if getattr(tag, 'is_multi_series', False):
        lines.append(f"type = multi_series")
        lines.append(f"name = {tag.name}")
        lines.append(f"start_time = {tag.start_time.toString('HH:mm')}")
        lines.append(f"end_time = {tag.end_time.toString('HH:mm')}")
        # Remove collection_videos to avoid bloating the ini file; keep only paths and metadata
        clean_series_list = [
            {k: v for k, v in s.items() if k != 'collection_videos'}
            for s in tag.series_list
        ]
        lines.append(f"series_list = {json.dumps(clean_series_list)}")
        lines.append(f"blacklist_profile = {getattr(tag, 'blacklist_profile', '')}")
        lines.append(f"blacklist = {json.dumps(getattr(tag, 'blacklist', []))}")
        active_days = getattr(tag, 'active_days', None)
        lines.append(f"active_days = {','.join(str(d) for d in active_days) if active_days else ''}")
    
    elif getattr(tag, 'is_series', False):
        lines.append(f"type = series")
        lines.append(f"name = {tag.name}")
        lines.append(f"start_time = {tag.start_time.toString('HH:mm')}")
        lines.append(f"end_time = {tag.end_time.toString('HH:mm')}")
        lines.append(f"start_season = {getattr(tag, 'start_season', 1)}")
        lines.append(f"start_episode = {getattr(tag, 'start_episode', 1)}")
        lines.append(f"play_mode = {getattr(tag, 'play_mode', 'sequence')}")
        lines.append(f"video_count = {getattr(tag, 'video_count', 1)}")
        lines.append(f"series_end_behavior = {getattr(tag, 'series_end_behavior', 'stop')}")
        lines.append(f"series_repeat_season = {getattr(tag, 'series_repeat_season', 0)}")
        lines.append(f"series_random_season = {getattr(tag, 'series_random_season', 0)}")
        # Bug 2: also save collection_path so the cold-load fallback in
        # _process_series_tag can find the videos without a Save
        # round-trip. (collection_profile is also saved below; one of
        # the two is enough for the lazy-load to work.)
        lines.append(f"collection_path = {getattr(tag, 'collection_path', '')}")
        lines.append(f"collection_profile = {getattr(tag, 'collection_profile', '')}")
        lines.append(f"blacklist_profile = {getattr(tag, 'blacklist_profile', '')}")
        active_days = getattr(tag, 'active_days', None)
        lines.append(f"active_days = {','.join(str(d) for d in active_days) if active_days else ''}")
    
    elif getattr(tag, 'is_random_fill', False):
        lines.append(f"type = random")
        lines.append(f"name = {tag.name}")
        lines.append(f"start_time = {tag.start_time.toString('HH:mm')}")
        lines.append(f"end_time = {tag.end_time.toString('HH:mm')}")
        lines.append(f"collection_path = {getattr(tag, 'collection_path', '')}")
        lines.append(f"blacklist_path = {getattr(tag, 'blacklist_path', '')}")
        lines.append(f"fill_24h = {'true' if getattr(tag, 'fill_24h', False) else 'false'}")
        lines.append(f"collection_profile = {getattr(tag, 'collection_profile', '')}")
        lines.append(f"blacklist_profile = {getattr(tag, 'blacklist_profile', '')}")
        marathon_mode = getattr(tag, 'marathon_mode', False)
        if marathon_mode:
            lines.append(f"marathon_mode = true")
            marathon_tag_name = getattr(tag, 'marathon_tag_name', '')
            if marathon_tag_name:
                lines.append(f"marathon_tag_name = {marathon_tag_name}")
    
    else:
        lines.append(f"type = custom")
        lines.append(f"name = {tag.name}")
        lines.append(f"start_time = {tag.start_time.toString('HH:mm')}")
        lines.append(f"end_time = {tag.end_time.toString('HH:mm')}")
        lines.append(f"randomize_videos = {'true' if getattr(tag, 'randomize_videos', False) else 'false'}")
        lines.append(f"video_count = {getattr(tag, 'video_count', 1)}")
        lines.append(f"collection_path = {getattr(tag, 'collection_path', '')}")
        lines.append(f"collection_profile = {getattr(tag, 'collection_profile', '')}")
        lines.append(f"blacklist_profile = {getattr(tag, 'blacklist_profile', '')}")
        active_days = getattr(tag, 'active_days', None)
        lines.append(f"active_days = {','.join(str(d) for d in active_days) if active_days else ''}")
    
    return '\n'.join(lines)


def save_tags_to_ini(tags: List[Any], filepath: str = "tags.ini"):
    config = configparser.ConfigParser()
    config['Tags'] = {}
    
    for i, tag in enumerate(tags):
        key = f"tag{i}"
        config['Tags'][key] = serialize_tag_to_string(tag)
    
    with open(filepath, 'w') as f:
        config.write(f)


def deserialize_tag_from_string(data: str, tag_class, qtime_from_string):
    config = configparser.ConfigParser()
    
    try:
        config.read_string(data)
    except configparser.Error:
        return deserialize_tag_legacy(data, tag_class, qtime_from_string)
    
    if 'Tag' not in config:
        return deserialize_tag_legacy(data, tag_class, qtime_from_string)
    
    tag_section = config['Tag']
    tag_type = tag_section.get('type', 'custom')
    name = tag_section.get('name', 'Unnamed')
    start = tag_section.get('start_time', '00:00')
    end = tag_section.get('end_time', '00:00')
    
    collection_videos = []
    collection_path = tag_section.get('collection_path', '')
    
    if collection_path:
        collection_videos = load_collection_videos_only(collection_path)
    
    if tag_type == 'series':
        start_season = int(tag_section.get('start_season', 1))
        start_episode = int(tag_section.get('start_episode', 1))
        play_mode = tag_section.get('play_mode', 'sequence')
        video_count = int(tag_section.get('video_count', 1))
        collection_profile = tag_section.get('collection_profile', '')
        blacklist_profile = tag_section.get('blacklist_profile', '')
        
        # Load blacklist based on blacklist_profile
        blacklist = []
        if blacklist_profile:
            _, blacklist_path_dir = get_config_paths()
            blacklist_file = Path(blacklist_path_dir) / blacklist_profile
            if blacklist_file.exists():
                blacklist = load_blacklist_json(str(blacklist_file))
        
        series_end_behavior = tag_section.get('series_end_behavior', 'stop')
        series_repeat_season = int(tag_section.get('series_repeat_season', 0))
        series_random_season = int(tag_section.get('series_random_season', 0))
        active_days_str = tag_section.get('active_days', '')
        active_days = [int(d) for d in active_days_str.split(',') if d.strip().isdigit()] if active_days_str.strip() else None
        
        return tag_class('custom', name, qtime_from_string(start, 'HH:mm'), qtime_from_string(end, 'HH:mm'), 
                        collection_videos, collection_path, video_count=video_count, 
                        is_series=True, start_season=start_season, start_episode=start_episode, 
                        play_mode=play_mode, collection_profile=collection_profile,
                        blacklist_profile=blacklist_profile, blacklist=blacklist,
                        series_end_behavior=series_end_behavior,
                        series_repeat_season=series_repeat_season,
                        series_random_season=series_random_season,
                        active_days=active_days)
    
    elif tag_type == 'multi_series':
        series_list_str = tag_section.get('series_list', '[]')
        try:
            series_list = json.loads(series_list_str)
        except:
            series_list = []
        # Populate collection_videos from collection_path for each series (if available)
        for series in series_list:
            coll_path = series.get('collection_path', '')
            if coll_path:
                try:
                    series['collection_videos'] = load_collection_videos_only(coll_path)
                except Exception:
                    series['collection_videos'] = []
            else:
                series['collection_videos'] = []
        
        blacklist_profile = tag_section.get('blacklist_profile', '')
        blacklist_str = tag_section.get('blacklist', '[]')
        try:
            blacklist = json.loads(blacklist_str)
        except:
            blacklist = []
        
        active_days_str = tag_section.get('active_days', '')
        active_days = [int(d) for d in active_days_str.split(',') if d.strip().isdigit()] if active_days_str.strip() else None
        
        from models import MultiSeriesTag
        return MultiSeriesTag(
            name=name,
            start_time=qtime_from_string(start, 'HH:mm'),
            end_time=qtime_from_string(end, 'HH:mm'),
            series_list=series_list,
            blacklist=blacklist,
            blacklist_profile=blacklist_profile,
            active_days=active_days
        )
    
    elif tag_type == 'random':
        blacklist_path = tag_section.get('blacklist_path', '')
        fill_24h = tag_section.get('fill_24h', 'false') == 'true'
        collection_profile = tag_section.get('collection_profile', '')
        blacklist_profile = tag_section.get('blacklist_profile', '')
        marathon_mode = tag_section.get('marathon_mode', 'false') == 'true'
        marathon_tag_name = tag_section.get('marathon_tag_name', '')
        
        blacklist = []
        if blacklist_path:
            blacklist = load_blacklist_json(blacklist_path)
        
        return tag_class('random', name, qtime_from_string(start, 'HH:mm'), qtime_from_string(end, 'HH:mm'),
                        collection_videos, collection_path, is_random_fill=True,
                        blacklist=blacklist, blacklist_path=blacklist_path, fill_24h=fill_24h,
                        collection_profile=collection_profile, blacklist_profile=blacklist_profile,
                        marathon_mode=marathon_mode, marathon_tag_name=marathon_tag_name)
    
    else:
        is_random_videos = tag_section.get('randomize_videos', 'false') == 'true'
        video_count = int(tag_section.get('video_count', 1))
        collection_profile = tag_section.get('collection_profile', '')
        blacklist_profile = tag_section.get('blacklist_profile', '')
        
        # Load blacklist based on blacklist_profile
        blacklist = []
        if blacklist_profile:
            _, blacklist_path_dir = get_config_paths()
            blacklist_file = Path(blacklist_path_dir) / blacklist_profile
            if blacklist_file.exists():
                blacklist = load_blacklist_json(str(blacklist_file))
        
        active_days_str = tag_section.get('active_days', '')
        active_days = [int(d) for d in active_days_str.split(',') if d.strip().isdigit()] if active_days_str.strip() else None
        
        return tag_class('custom', name, qtime_from_string(start, 'HH:mm'), qtime_from_string(end, 'HH:mm'),
                        collection_videos, collection_path, is_random_videos, video_count,
                        collection_profile=collection_profile, blacklist_profile=blacklist_profile,
                        blacklist=blacklist, active_days=active_days)


def deserialize_tag_legacy(data: str, tag_class, qtime_from_string):
    parts = data.split('|')
    if len(parts) < 4:
        return None
    
    tag_type = parts[0]
    name = parts[1]
    start = parts[2]
    end = parts[3]
    
    collection_videos = []
    collection_path = ""
    blacklist = []
    blacklist_path = ""
    
    if tag_type == 'series':
        start_season = int(parts[4]) if len(parts) >= 5 and parts[4].isdigit() else 1
        start_episode = int(parts[5]) if len(parts) >= 6 and parts[5].isdigit() else 1
        play_mode = parts[6] if len(parts) >= 7 else "sequence"
        video_count = int(parts[7]) if len(parts) >= 8 and parts[7].isdigit() else 1
        
        if len(parts) >= 10:
            collection_profile = parts[8] if parts[8] else ""
            blacklist_profile = parts[9] if parts[9] else ""
            collection_path = ""
        else:
            collection_profile = ""
            blacklist_profile = ""
            collection_path = parts[8] if len(parts) >= 9 else ""
        
        if collection_path:
            collection_videos = load_collection_videos_only(collection_path)
        
        return tag_class('custom', name, qtime_from_string(start, 'HH:mm'), qtime_from_string(end, 'HH:mm'), 
                        collection_videos, collection_path, video_count=video_count, 
                        is_series=True, start_season=start_season, start_episode=start_episode, 
                        play_mode=play_mode, collection_profile=collection_profile,
                        blacklist_profile=blacklist_profile)
    
    elif tag_type == 'random':
        collection_path = parts[4] if len(parts) >= 5 else ""
        blacklist_path = parts[5] if len(parts) >= 6 else ""
        fill_24h = len(parts) >= 7 and parts[6] == "1"
        collection_profile = parts[7] if len(parts) >= 8 else ""
        blacklist_profile = parts[8] if len(parts) >= 9 else ""
        
        if collection_path:
            collection_videos = load_collection_videos_only(collection_path)
        
        if blacklist_path:
            blacklist = load_blacklist_json(blacklist_path)
        
        return tag_class('random', name, qtime_from_string(start, 'HH:mm'), qtime_from_string(end, 'HH:mm'),
                        collection_videos, collection_path, is_random_fill=True,
                        blacklist=blacklist, blacklist_path=blacklist_path, fill_24h=fill_24h,
                        collection_profile=collection_profile, blacklist_profile=blacklist_profile)
    
    else:
        is_random_videos = len(parts) >= 5 and parts[4] == "1"
        video_count = int(parts[5]) if len(parts) >= 6 and parts[5].isdigit() else 1
        collection_path = parts[6] if len(parts) >= 7 else ""
        
        if len(parts) >= 9:
            collection_profile = parts[7] if parts[7] else ""
            blacklist_profile = parts[8] if parts[8] else ""
        else:
            collection_profile = ""
            blacklist_profile = ""
        
        if collection_path:
            collection_videos = load_collection_videos_only(collection_path)
        
        return tag_class('custom', name, qtime_from_string(start, 'HH:mm'), qtime_from_string(end, 'HH:mm'),
                        collection_videos, collection_path, is_random_videos, video_count,
                        collection_profile=collection_profile, blacklist_profile=blacklist_profile)


def load_tags_from_ini(filepath: str, tag_class, qtime_from_string) -> List[Any]:
    if not Path(filepath).exists():
        return []
    
    config = configparser.ConfigParser()
    config.read(filepath)
    
    if 'Tags' not in config:
        return []
    
    tags = []
    for key in config['Tags']:
        tag = deserialize_tag_from_string(config['Tags'][key], tag_class, qtime_from_string)
        if tag:
            tags.append(tag)
    
    return tags


def save_single_tag_to_ini(tag, filepath: str):
    config = configparser.ConfigParser()
    config['Tag'] = {'data': serialize_tag_to_string(tag)}
    
    with open(filepath, 'w') as f:
        config.write(f)


def load_single_tag_from_ini(filepath: str, tag_class, qtime_from_string) -> Optional[Any]:
    if not Path(filepath).exists():
        return None
    
    config = configparser.ConfigParser()
    config.read(filepath)
    
    if 'Tag' not in config:
        return None
    
    return deserialize_tag_from_string(config['Tag']['data'], tag_class, qtime_from_string)
