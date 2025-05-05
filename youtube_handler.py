# youtube_handler.py - YouTube video handling
import yt_dlp
import os
import urllib.request
import urllib.parse
import json
import logging
import time
from urllib.parse import urlparse, parse_qs
from concurrent.futures import ThreadPoolExecutor
from utils import get_random_user_agent, check_ffmpeg

# Configure logging
logger = logging.getLogger("youtube_handler")

def extract_video_id(url: str) -> str:
    """Extract video ID from various YouTube URL formats"""
    if not url:
        return ""
        
    parsed_url = urlparse(url)
    
    # Standard youtube.com/watch?v=ID format
    if 'youtube.com' in parsed_url.netloc and '/watch' in parsed_url.path:
        query = parse_qs(parsed_url.query)
        return query.get('v', [''])[0]
    
    # Short youtu.be/ID format
    if 'youtu.be' in parsed_url.netloc:
        return parsed_url.path.lstrip('/')
    
    # Embed youtube.com/embed/ID format
    if 'youtube.com' in parsed_url.netloc and '/embed/' in parsed_url.path:
        path_parts = parsed_url.path.split('/')
        if len(path_parts) > 2:
            return path_parts[2]
            
    # Handle YouTube shorts
    if 'youtube.com' in parsed_url.netloc and '/shorts/' in parsed_url.path:
        path_parts = parsed_url.path.split('/')
        if len(path_parts) > 2:
            return path_parts[2]
    
    return ''

def get_video_info(url: str) -> dict:
    """Get video information from YouTube"""
    video_id = extract_video_id(url)
    if not video_id:
        logger.warning(f"Could not extract video ID from URL: {url}")
        return {"title": "Unknown", "duration": 0, "channel": "Unknown"}
    
    logger.info(f"Getting info for video: {video_id}")
    start_time = time.time()
    
    # Try with yt-dlp - Optimized for speed
    try:
        with yt_dlp.YoutubeDL({
            "quiet": True, 
            "user_agent": get_random_user_agent(),
            "extractor_args": {"youtube": {"player_skip": ["js", "configs", "webpage"]}},
            "skip_download": True,  # Definitely skip download for info
            "noplaylist": True,     # Skip playlist processing
            "format": None,         # Don't need format info for metadata only
            "socket_timeout": 10,   # Faster timeout for metadata
        }) as ydl:
            info = ydl.extract_info(url, download=False)
            logger.info(f"Got video info via yt-dlp in {time.time() - start_time:.2f}s")
            return {
                "title": info.get("title"),
                "duration": info.get("duration"),
                "channel": info.get("uploader"),
                "upload_date": info.get("upload_date"),
                "view_count": info.get("view_count"),
                "thumbnail": info.get("thumbnail")
            }
    except Exception as e:
        logger.warning(f"yt-dlp extraction failed: {e}, trying fallback...")
        
    # Fallback to YouTube oEmbed API
    try:
        oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
        with urllib.request.urlopen(oembed_url, timeout=5) as response:
            data = json.loads(response.read().decode())
            logger.info(f"Got video info via oEmbed API in {time.time() - start_time:.2f}s")
            return {
                "title": data.get("title"),
                "duration": 0,  # oEmbed doesn't provide duration
                "channel": data.get("author_name", "Unknown"),
                "thumbnail": data.get("thumbnail_url")
            }
    except Exception as e2:
        logger.warning(f"YouTube oEmbed API fallback failed: {e2}")
        
    # Last resort: Use video ID as title
    logger.warning(f"All methods failed. Using video ID as title for {video_id}")
    return {
        "title": f"YouTube Video {video_id}",
        "duration": 0,
        "channel": "Unknown",
        "video_id": video_id
    }

def is_long_video(url: str) -> bool:
    """Check if a video is considered 'long' (over 30 minutes)"""
    try:
        # Quick check with minimal data
        with yt_dlp.YoutubeDL({
            "quiet": True,
            "skip_download": True,
            "noplaylist": True,
            "socket_timeout": 10,
            "extractor_args": {"youtube": {"player_skip": ["js", "configs", "webpage"]}},
        }) as ydl:
            info = ydl.extract_info(url, download=False)
            duration = info.get("duration", 0)
            logger.info(f"Video duration: {duration} seconds")
            
            # Over 30 minutes is considered long
            return duration > 1800
    except Exception as e:
        logger.warning(f"Error checking video length: {e}")
        # Assume not long if we can't determine
        return False

def download_audio(url: str, output_path: str, is_long: bool = None) -> str:
    """Download audio from YouTube video with optimizations for long videos"""
    video_id = extract_video_id(url)
    if not video_id:
        logger.error(f"Invalid YouTube URL: {url}")
        return ""
    
    if not check_ffmpeg():
        logger.error("FFMPEG not found in path. Audio processing will fail.")
        return ""
    
    logger.info(f"Downloading audio for video: {video_id}")
    start_time = time.time()
    
    # Create necessary directories
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Auto-detect if this is a long video if not specified
    if is_long is None:
        is_long = is_long_video(url)
    
    # Method 1: Try with yt-dlp with optimized settings
    try:
        # Optimize settings based on video length
        if is_long:
            # For long videos, use lower quality and faster settings
            audio_quality = "96"  # Lower quality for faster download
            format_preference = "worstaudio/worst" # Prefer lower quality for speed
            logger.info("Using optimized download settings for long video")
        else:
            # Standard quality for regular videos
            audio_quality = "128"
            format_preference = "bestaudio/best"
        
        ydl_opts = {
            "format": format_preference,
            "outtmpl": output_path.replace('.mp3', '.%(ext)s'),
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": audio_quality,
            }],
            "user_agent": get_random_user_agent(),
            "quiet": False,
            "no_warnings": False,
            # Speed optimizations
            "socket_timeout": 30,
            "retries": 3,
            "fragment_retries": 3,
            "skip_download": False,
            "noplaylist": True,
            # Additional optimizations for faster downloads
            "nocheckcertificate": True,  # Skip SSL verification
            "concurrent_fragment_downloads": 4,  # Download fragments in parallel
            "buffersize": 1024,  # Smaller buffer size
        }
        
        # For very long videos, use even more aggressive optimizations
        if is_long and "duration" in locals() and duration > 7200:  # > 2 hours
            ydl_opts["format"] = "worstaudio/worst"  # Always use worst audio
            ydl_opts["postprocessors"][0]["preferredquality"] = "64"  # Even lower quality
            logger.info("Using extra-optimized settings for very long video")
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            download_time = time.time() - start_time
            logger.info(f"Downloaded audio with yt-dlp in {download_time:.2f}s")
            return output_path
    except Exception as e:
        logger.warning(f"yt-dlp download failed: {e}")
    
    # All methods failed
    logger.error("All download methods failed")
    return ""

def download_audio_section(url: str, output_path: str, start_time_sec: int, end_time_sec: int) -> str:
    """Download only a specific section of a video (useful for sampling long videos)"""
    video_id = extract_video_id(url)
    if not video_id:
        logger.error(f"Invalid YouTube URL: {url}")
        return ""
    
    if not check_ffmpeg():
        logger.error("FFMPEG not found in path. Audio processing will fail.")
        return ""
    
    logger.info(f"Downloading section {start_time_sec}-{end_time_sec}s from video: {video_id}")
    
    # Create necessary directories
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Calculate duration
    duration = end_time_sec - start_time_sec
    if duration <= 0:
        logger.error("Invalid time range")
        return ""
    
    # Method: Use yt-dlp to download the section directly
    try:
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": output_path.replace('.mp3', '.%(ext)s'),
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "128",
            }],
            "user_agent": get_random_user_agent(),
            "quiet": True,
            "noplaylist": True,
            "download_ranges": {
                "download_ranges_str": f"{start_time_sec}-{end_time_sec}"
            },
            "force_keyframes_at_cuts": True,
            "external_downloader_args": ["ffmpeg", "-ss", str(start_time_sec), "-t", str(duration)]
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            logger.info(f"Downloaded audio section successfully")
            return output_path
    except Exception as e:
        logger.warning(f"Section download failed: {e}")
        return ""