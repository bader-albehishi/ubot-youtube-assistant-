# audio_processing.py - Audio processing module
import subprocess
import os
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict
from utils import clean_directory, check_ffmpeg

# Configure logging
logger = logging.getLogger("audio_processing")

# Define constants
SEGMENTS_DIR = os.path.join("data", "segments")
os.makedirs(SEGMENTS_DIR, exist_ok=True)

def get_audio_duration(input_file: str) -> float:
    """Get the duration of an audio file in seconds using ffprobe"""
    if not os.path.exists(input_file):
        logger.error(f"Audio file not found: {input_file}")
        return 0
        
    try:
        cmd = [
            "ffprobe", "-v", "error", 
            "-show_entries", "format=duration", 
            "-of", "default=noprint_wrappers=1:nokey=1", 
            input_file
        ]
        result = subprocess.check_output(cmd).decode('utf-8').strip()
        return float(result)
    except Exception as e:
        logger.error(f"Error getting audio duration: {e}")
        return 0

def split_audio(input_file: str, max_seconds: int = 30, is_long_video: bool = False) -> List[str]:
    """Split audio into segments for processing with optimizations for long videos"""
    if not check_ffmpeg():
        logger.error("FFMPEG not found in path. Audio processing will fail.")
        return []
        
    if not os.path.exists(input_file):
        logger.error(f"Input audio file not found: {input_file}")
        return []
    
    start_time = time.time()
    logger.info(f"Splitting audio file: {input_file}")
    
    # Auto-detect if this is likely a long video based on file size
    if not is_long_video and os.path.getsize(input_file) > 50 * 1024 * 1024:  # > 50 MB
        is_long_video = True
        logger.info("Large audio file detected, using long video optimizations")
    
    # Create a unique segments directory for this file to avoid conflicts
    file_hash = os.path.basename(input_file).split('.')[0]
    segments_dir = os.path.join(SEGMENTS_DIR, file_hash)
    os.makedirs(segments_dir, exist_ok=True)
    
    # Get audio duration
    duration = get_audio_duration(input_file)
    if duration <= 0:
        logger.error("Could not determine audio duration")
        return []
    
    logger.info(f"Audio duration: {duration:.2f} seconds")
    
    # Adjust max_seconds based on video length for better efficiency
    if is_long_video:
        if duration > 7200:  # > 2 hours
            max_seconds = max(max_seconds, 180)  # Use 3-minute segments
        elif duration > 3600:  # > 1 hour
            max_seconds = max(max_seconds, 120)  # Use 2-minute segments
        logger.info(f"Using longer segments for long video: {max_seconds} seconds")
    
    # Calculate segments
    segments_count = max(1, int(duration / max_seconds))
    logger.info(f"Creating {segments_count} segments")
    
    # Optimize number of parallel processes based on system resources and video length
    cpu_count = os.cpu_count() or 2
    if is_long_video and segments_count > 100:
        # For very long videos, limit parallelism to avoid memory issues
        max_workers = min(cpu_count, 4)
    else:
        max_workers = min(cpu_count, 8)
        
    logger.info(f"Using {max_workers} parallel workers for audio segmentation")
    
    # Function to process a single segment with optimized settings
    def process_segment(index: int) -> str:
        start = index * max_seconds
        output_segment = os.path.join(segments_dir, f"segment_{index:03d}.mp3")
        
        try:
            # Optimize encoding quality and settings based on video length
            q_value = "7" if is_long_video else "4"  # Lower quality (higher value) for long videos
            sample_rate = "16000" if is_long_video else "22050"  # Lower sample rate for long videos
            
            cmd = [
                "ffmpeg", "-y", "-i", input_file, 
                "-ss", str(start), 
                "-t", str(max_seconds),
                "-acodec", "libmp3lame",  # Use MP3 codec for compatibility
                "-q:a", q_value,  # Adjusted quality
                "-ac", "1",  # Convert to mono for better transcription
                "-ar", sample_rate,  # Sample rate
                output_segment
            ]
            
            # Run ffmpeg process with minimal output
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            return output_segment
        except Exception as e:
            logger.error(f"Error processing segment {index}: {e}")
            return ""
    
    # Process segments in parallel with batching for long videos
    segment_indices = list(range(segments_count))
    valid_segments = []
    
    # For very long videos, process in batches to avoid memory issues
    if is_long_video and segments_count > 50:
        batch_size = 20  # Process 20 segments at a time
        for i in range(0, segments_count, batch_size):
            batch_indices = segment_indices[i:i+batch_size]
            logger.info(f"Processing batch {i//batch_size + 1}/{(segments_count+batch_size-1)//batch_size}")
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                batch_segments = list(executor.map(process_segment, batch_indices))
                
            # Add valid segments from this batch
            valid_segments.extend([path for path in batch_segments if path and os.path.exists(path)])
    else:
        # Process all segments in one go for shorter videos
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            segment_paths = list(executor.map(process_segment, segment_indices))
            valid_segments = [path for path in segment_paths if path and os.path.exists(path)]
    
    elapsed_time = time.time() - start_time
    logger.info(f"Split audio into {len(valid_segments)} segments in {elapsed_time:.2f} seconds")
    
    return valid_segments

def optimize_audio(input_file: str, output_file: str, is_long_video: bool = False) -> str:
    """Optimize audio file for transcription (new function for long videos)"""
    if not check_ffmpeg() or not os.path.exists(input_file):
        return ""
    
    try:
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        # Optimize settings based on whether this is a long video
        if is_long_video:
            sample_rate = "16000"  # Lower sample rate
            bitrate = "64k"  # Lower bitrate
        else:
            sample_rate = "22050"  # Standard sample rate
            bitrate = "128k"  # Standard bitrate
        
        cmd = [
            "ffmpeg", "-y", "-i", input_file,
            "-vn",  # No video
            "-ar", sample_rate,  # Adjusted sample rate
            "-ac", "1",  # Mono for better transcription
            "-b:a", bitrate,  # Adjusted bitrate
            "-filter:a", "loudnorm",  # Normalize audio (helps with transcription)
            output_file
        ]
        
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        
        if os.path.exists(output_file):
            logger.info(f"Optimized audio for transcription: {output_file}")
            return output_file
    except Exception as e:
        logger.error(f"Error optimizing audio: {e}")
    
    return ""

def convert_audio_format(input_file: str, output_file: str, format: str = "mp3") -> str:
    """Convert audio file to a different format using ffmpeg"""
    if not check_ffmpeg() or not os.path.exists(input_file):
        return ""
    
    try:
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        cmd = [
            "ffmpeg", "-y", "-i", input_file,
            "-vn",  # No video
            "-ar", "44100",  # Audio sample rate
            "-ac", "1" if format != "mp3" else "2",  # Channels
            "-b:a", "128k",  # Bitrate
            output_file
        ]
        
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        
        if os.path.exists(output_file):
            logger.info(f"Converted audio to {format}: {output_file}")
            return output_file
    except Exception as e:
        logger.error(f"Error converting audio: {e}")
    
    return ""