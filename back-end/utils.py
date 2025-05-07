# utils.py - Utility functions
import os
import random
import subprocess
import logging
import time
import json
from typing import List, Dict, Optional, Any, Union
from concurrent.futures import ThreadPoolExecutor

# Configure logging
logger = logging.getLogger("utils")

# Base data directory
DATA_DIR = os.getenv("DATA_DIR", "./data")

# Ensure the data directory exists
os.makedirs(DATA_DIR, exist_ok=True)

def save_to_file(text: str, path: str) -> bool:
    """Save given text to the specified file path"""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        logger.info(f"Saved {len(text)} characters to {path}")
        return True
    except Exception as e:
        logger.error(f"Error saving to file {path}: {e}")
        return False

def read_from_file(path: str, default: str = "") -> str:
    """Read and return the contents of the file at path"""
    if not os.path.exists(path):
        logger.warning(f"File not found: {path}")
        return default
        
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        logger.info(f"Read {len(content)} characters from {path}")
        return content
    except Exception as e:
        logger.error(f"Error reading file {path}: {e}")
        return default

def get_random_user_agent() -> str:
    """Return a random user-agent string for HTTP requests"""
    agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0"
    ]
    return random.choice(agents)

def check_ffmpeg() -> bool:
    """Check if ffmpeg is installed and accessible"""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=5
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError):
        return False

def clean_directory(dir_path: str) -> bool:
    """Remove all files in the given directory"""
    if not os.path.exists(dir_path):
        os.makedirs(dir_path, exist_ok=True)
        return True
        
    try:
        file_count = 0
        for filename in os.listdir(dir_path):
            file_path = os.path.join(dir_path, filename)
            if os.path.isfile(file_path):
                os.remove(file_path)
                file_count += 1
                
        logger.info(f"Cleaned {file_count} files from {dir_path}")
        return True
    except Exception as e:
        logger.error(f"Error cleaning directory {dir_path}: {e}")
        return False

def batch_process_files(file_paths: List[str], process_func: callable, 
                       max_workers: Optional[int] = None) -> List[Any]:
    """Process multiple files in parallel"""
    if not file_paths:
        return []
        
    # Determine optimal worker count if not specified
    if max_workers is None:
        max_workers = min(os.cpu_count() or 4, len(file_paths))
    
    logger.info(f"Processing {len(file_paths)} files with {max_workers} workers")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(process_func, file_paths))
        
    return results

def load_json_file(file_path: str, default: Any = None) -> Any:
    """Load and parse a JSON file with error handling"""
    if not os.path.exists(file_path):
        logger.warning(f"JSON file not found: {file_path}")
        return default
        
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except Exception as e:
        logger.error(f"Error loading JSON file {file_path}: {e}")
        return default

def save_json_file(file_path: str, data: Any, ensure_ascii: bool = False) -> bool:
    """Save data to a JSON file"""
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=ensure_ascii, indent=2)
        logger.info(f"Saved JSON data to {file_path}")
        return True
    except Exception as e:
        logger.error(f"Error saving JSON file {file_path}: {e}")
        return False

def generate_uid(prefix: str = "") -> str:
    """Generate a unique ID with optional prefix"""
    import uuid
    unique_id = uuid.uuid4().hex[:8]
    if prefix:
        return f"{prefix}_{unique_id}"
    return unique_id

def get_file_size(file_path: str) -> int:
    """Get file size in bytes"""
    if not os.path.exists(file_path):
        return 0
        
    try:
        return os.path.getsize(file_path)
    except Exception as e:
        logger.error(f"Error getting file size for {file_path}: {e}")
        return 0

def format_file_size(size_bytes: int) -> str:
    """Format file size from bytes to human-readable string"""
    if size_bytes < 0:
        return "0 B"
        
    units = ["B", "KB", "MB", "GB", "TB"]
    unit_index = 0
    
    while size_bytes >= 1024 and unit_index < len(units) - 1:
        size_bytes /= 1024
        unit_index += 1
        
    return f"{size_bytes:.1f} {units[unit_index]}"