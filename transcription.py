# transcription.py - Audio transcription with OpenAI Whisper
from openai import OpenAI
import os
import time
import logging
import asyncio
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Optional, AsyncGenerator
from langsmith import traceable

# Setup logging
logger = logging.getLogger("transcription")

# Load environment variables
load_dotenv(override=True)

# Initialize OpenAI client
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Thread local storage for clients
import threading
_thread_local = threading.local()

def get_openai_client():
    """Get thread-local OpenAI client for thread safety"""
    if not hasattr(_thread_local, 'openai_client'):
        _thread_local.openai_client = OpenAI(api_key=OPENAI_API_KEY)
    return _thread_local.openai_client

def transcribe_single_segment(segment: str, whisper_language: Optional[str] = None) -> str:
    """Transcribe a single audio segment"""
    if not os.path.exists(segment):
        logger.error(f"Segment file not found: {segment}")
        return ""
        
    start_time = time.time()
    logger.info(f"Transcribing segment: {segment}")
    
    # Get thread-local client
    client = get_openai_client()
    
    try:
        with open(segment, "rb") as f:
            # Prepare transcription options
            transcription_options = {
                "model": "whisper-1",
                "file": f,
                "response_format": "text"
            }
            
            # Add language parameter if specified
            if whisper_language:
                transcription_options["language"] = whisper_language
            
            # Make the API call
            response = client.audio.transcriptions.create(**transcription_options)
            
            # Log success
            elapsed = time.time() - start_time
            text = response.text if hasattr(response, 'text') else response
            logger.info(f"Transcribed {os.path.basename(segment)} in {elapsed:.2f}s: {len(text)} chars")
            
            return text
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"Error transcribing {segment} after {elapsed:.2f}s: {e}")
        return ""

@traceable()
def transcribe_segments(segments: List[str], language: Optional[str] = None) -> str:
    """Transcribe multiple audio segments in parallel"""
    if not segments:
        logger.warning("No segments to transcribe")
        return ""
    
    # Track total transcription time
    start_time = time.time()
    
    # Adjust max workers based on segment count
    max_workers = min(5, len(segments))
    logger.info(f"Starting transcription of {len(segments)} segments with {max_workers} workers")
    
    # Use multithreading for parallel API calls
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Map function to transcribe segments with language parameter
        transcribe_func = lambda seg: transcribe_single_segment(seg, language)
        results = list(executor.map(transcribe_func, segments))
    
    # Post-process results
    # Count successful segments
    successful = sum(1 for r in results if r)
    logger.info(f"Transcribed {successful}/{len(segments)} segments successfully")
    
    # Combine results intelligently
    transcript = ""
    for i, segment_text in enumerate(results):
        if not segment_text:
            continue
            
        # Smart text joining logic
        if i > 0 and segment_text:
            # If this segment starts with lowercase and previous segment didn't end with sentence-ending punctuation
            if (segment_text[0].islower() and transcript and 
                    transcript[-1] not in '.!?'):
                transcript = transcript.rstrip() + " " + segment_text
            else:
                transcript += segment_text + "\n"
        else:
            transcript += segment_text + "\n"
    
    # Clean up extra newlines and whitespace
    transcript = "\n".join(line for line in transcript.split("\n") if line.strip())
    
    # Add RTL marker for Arabic content
    if language == "ar":
        transcript = "\u202B" + transcript
    elif not language:
        # Try to auto-detect language if not specified
        try:
            from langdetect import detect
            sample_text = transcript[:min(500, len(transcript))]
            detected_language = detect(sample_text)
            if detected_language == "ar":
                transcript = "\u202B" + transcript
                logger.info("Added RTL marker for detected Arabic content")
        except Exception as e:
            logger.warning(f"Language detection failed: {e}")
    
    # Log total time
    total_time = time.time() - start_time
    logger.info(f"Total transcription time: {total_time:.2f}s for {len(transcript)} characters")
    
    return transcript

async def transcribe_streaming(segments: List[str], language: Optional[str] = None) -> AsyncGenerator[str, None]:
    """Transcribe segments and yield results as they complete for streaming UI"""
    if not segments:
        yield "No audio segments to transcribe"
        return
        
    loop = asyncio.get_event_loop()
    pending_segments = segments.copy()
    completed_segments = {}
    
    # Create a thread pool
    with ThreadPoolExecutor(max_workers=3) as executor:
        # Submit initial batch of tasks
        futures = {}
        batch_size = min(3, len(pending_segments))
        
        for i in range(batch_size):
            segment = pending_segments.pop(0)
            future = loop.run_in_executor(
                executor, 
                transcribe_single_segment, 
                segment, 
                language
            )
            futures[future] = segment
        
        # Process futures as they complete
        while futures:
            # Wait for a future to complete
            done, _ = await asyncio.wait(
                futures.keys(), 
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # Process completed futures
            for future in done:
                segment = futures.pop(future)
                try:
                    result = future.result()
                    segment_index = segments.index(segment)
                    completed_segments[segment_index] = result
                    
                    # Yield any consecutive completed segments
                    i = 0
                    while i in completed_segments:
                        yield completed_segments.pop(i)
                        i += 1
                        
                    # If there are pending segments, submit a new task
                    if pending_segments:
                        next_segment = pending_segments.pop(0)
                        new_future = loop.run_in_executor(
                            executor, 
                            transcribe_single_segment, 
                            next_segment, 
                            language
                        )
                        futures[new_future] = next_segment
                except Exception as e:
                    logger.error(f"Error processing segment {segment}: {e}")
                    yield f"Error: {str(e)}"
        
        # Yield any remaining segments in order
        indices = sorted(completed_segments.keys())
        for i in indices:
            yield completed_segments[i]