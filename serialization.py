import configparser
from typing import List, Any, Optional, Dict
from pathlib import Path

from utils import load_collection_videos_only, load_blacklist_json


def serialize_tag_to_string(tag) -> str:
    lines = ["[Tag]"]
    
    if getattr(tag, 'is_series', False):
        lines.append(f"type = series")
        lines.append(f"name = {tag.name}")
        lines.append(f"start_time = {tag.start_time.toString('HH:mm')}")
        lines.append(f"end_time = {tag.end_time.toString('HH:mm')}")
        lines.append(f"start_season = {getattr(tag, 'start_season', 1)}")
        lines.append(f"start_episode = {getattr(tag, 'start_episode', 1)}")
        lines.append(f"play_mode = {getattr(tag, 'play_mode', 'sequence')}")
        lines.append(f"video_count = {getattr(tag, 'video_count', 1)}")
        lines.append(f"collection_profile = {getattr(tag, 'collection_profile', '')}")
        lines.append(f"blacklist_profile = {getattr(tag, 'blacklist_profile', '')}")
    
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
        
        return tag_class('custom', name, qtime_from_string(start, 'HH:mm'), qtime_from_string(end, 'HH:mm'), 
                        collection_videos, collection_path, video_count=video_count, 
                        is_series=True, start_season=start_season, start_episode=start_episode, 
                        play_mode=play_mode, collection_profile=collection_profile,
                        blacklist_profile=blacklist_profile)
    
    elif tag_type == 'random':
        blacklist_path = tag_section.get('blacklist_path', '')
        fill_24h = tag_section.get('fill_24h', 'false') == 'true'
        collection_profile = tag_section.get('collection_profile', '')
        blacklist_profile = tag_section.get('blacklist_profile', '')
        
        blacklist = []
        if blacklist_path:
            blacklist = load_blacklist_json(blacklist_path)
        
        return tag_class('random', name, qtime_from_string(start, 'HH:mm'), qtime_from_string(end, 'HH:mm'),
                        collection_videos, collection_path, is_random_fill=True,
                        blacklist=blacklist, blacklist_path=blacklist_path, fill_24h=fill_24h,
                        collection_profile=collection_profile, blacklist_profile=blacklist_profile)
    
    else:
        is_random_videos = tag_section.get('randomize_videos', 'false') == 'true'
        video_count = int(tag_section.get('video_count', 1))
        collection_profile = tag_section.get('collection_profile', '')
        blacklist_profile = tag_section.get('blacklist_profile', '')
        
        return tag_class('custom', name, qtime_from_string(start, 'HH:mm'), qtime_from_string(end, 'HH:mm'),
                        collection_videos, collection_path, is_random_videos, video_count,
                        collection_profile=collection_profile, blacklist_profile=blacklist_profile)


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
