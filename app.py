# app.py - Main FastAPI application with optimizations for long videos
from fastapi import FastAPI, Request, HTTPException, Response, BackgroundTasks, Depends
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
import os, json, re, hashlib, logging, time, traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv


# Import project modules
from youtube_handler import get_video_info, download_audio, extract_video_id
from audio_processing import split_audio, get_audio_duration
from transcription import transcribe_segments
from qa_system import ask_question, ask_question_streaming
from utils import save_to_file, read_from_file, clean_directory, format_file_size
from rag_pipeline import split_text, embed_and_store, extract_keywords

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("app")

# Load environment variables
load_dotenv(override=True)

ffmpeg_path = r"C:\\Users\\STARS\\Desktop\\SDA_Final_project (v2)\\ffmpeg-7.1.1-essentials_build\\bin"
if os.path.exists(ffmpeg_path):
    os.environ["PATH"] += os.pathsep + ffmpeg_path

# Define directories
DATA_DIR = "data"
AUDIO_DIR = os.path.join(DATA_DIR, "audio")
TRANSCRIPT_DIR = os.path.join(DATA_DIR, "transcripts")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
VIDEO_INFO_DIR = os.path.join(DATA_DIR, "videos")
CHROMA_DIR = os.path.join(DATA_DIR, "chroma")
TEMP_DIR = os.path.join(DATA_DIR, "temp")  # New directory for partial processing

# Create required directories
for directory in [AUDIO_DIR, TRANSCRIPT_DIR, CACHE_DIR, VIDEO_INFO_DIR, CHROMA_DIR, TEMP_DIR]:
    os.makedirs(directory, exist_ok=True)

# Initialize FastAPI app
app = FastAPI(title="YouTube AI Assistant", description="Processes YouTube videos and answers questions")

# Configure CORS
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, 
                  allow_methods=["*"], allow_headers=["*"])

# Add session middleware for conversation tracking
app.add_middleware(SessionMiddleware, secret_key="your-secret-key-here")

# Mount static files for frontend
app.mount("/static", StaticFiles(directory="static"), name="static")

# Conversation history storage
conversation_histories = {}

# Get conversation history
def get_conversation_history(request: Request, video_id: str):
    """Get or create conversation history for the current session"""
    session_id = request.session.get("session_id")
    if not session_id:
        session_id = f"{video_id}_{int(time.time())}"
        request.session["session_id"] = session_id
        
    if session_id not in conversation_histories:
        conversation_histories[session_id] = []
        
    return conversation_histories[session_id]

# Global progress tracking - enhanced for long videos
progress_status = {
    "message": "Ready", 
    "percentage": 0, 
    "video_id": None,
    "processing_type": "standard",  # standard or chunked
    "chunks_total": 0,
    "chunks_completed": 0,
    "estimated_time_remaining": None,
    "started_at": None
}

def update_progress(message, percentage=None, video_id=None, processing_type=None, 
                   chunks_total=None, chunks_completed=None, started_at=None):
    """Update global progress status with enhanced tracking for long videos"""
    global progress_status
    progress_status["message"] = message
    
    if percentage is not None:
        progress_status["percentage"] = percentage
    
    if video_id is not None:
        progress_status["video_id"] = video_id
    
    if processing_type is not None:
        progress_status["processing_type"] = processing_type
    
    if chunks_total is not None:
        progress_status["chunks_total"] = chunks_total
    
    if chunks_completed is not None:
        progress_status["chunks_completed"] = chunks_completed
        if chunks_total and chunks_completed <= chunks_total:
            progress_percentage = int((chunks_completed / chunks_total) * 100)
            progress_status["percentage"] = progress_percentage
    
    if started_at is not None:
        progress_status["started_at"] = started_at
            
    # Calculate estimated time remaining
    if progress_status["started_at"] and progress_status["chunks_completed"] > 0 and progress_status["chunks_total"] > 0:
        elapsed = time.time() - progress_status["started_at"]
        time_per_chunk = elapsed / progress_status["chunks_completed"]
        remaining_chunks = progress_status["chunks_total"] - progress_status["chunks_completed"]
        est_time_remaining = time_per_chunk * remaining_chunks
        
        # Format as minutes and seconds
        minutes = int(est_time_remaining // 60)
        seconds = int(est_time_remaining % 60)
        progress_status["estimated_time_remaining"] = f"{minutes}m {seconds}s"

def clean_video_data(video_id):
    """Clean all data associated with a specific video"""
    try:
        # Track files to be removed
        removed_files = []
        
        # Clear transcript
        video_transcript_path = os.path.join(TRANSCRIPT_DIR, f"{video_id}.txt")
        if os.path.exists(video_transcript_path):
            os.remove(video_transcript_path)
            removed_files.append(video_transcript_path)
            
        # Clear cache
        cache_path = os.path.join(CACHE_DIR, f"{video_id}.json")
        if os.path.exists(cache_path):
            os.remove(cache_path)
            removed_files.append(cache_path)
            
        # Audio files
        audio_path = os.path.join(AUDIO_DIR, f"{video_id}.mp3")
        if os.path.exists(audio_path):
            os.remove(audio_path)
            removed_files.append(audio_path)
            
        # Clear temporary files
        temp_files = [f for f in os.listdir(TEMP_DIR) if f.startswith(f"{video_id}_")]
        for temp_file in temp_files:
            temp_path = os.path.join(TEMP_DIR, temp_file)
            os.remove(temp_path)
            removed_files.append(temp_path)
            
        # Clear ChromaDB collection
        try:
            from chromadb import PersistentClient
            client = PersistentClient(path=CHROMA_DIR)
            collection_name = f"youtube_transcript_{video_id}"
            
            try:
                client.delete_collection(collection_name)
                logger.info(f"Deleted collection {collection_name}")
            except Exception as e:
                logger.info(f"Collection {collection_name} might not exist: {e}")
        except Exception as e:
            logger.error(f"Error cleaning ChromaDB: {e}")
        
        # Clear conversation history
        to_remove = []
        for session_id in conversation_histories:
            if session_id.startswith(f"{video_id}_"):
                to_remove.append(session_id)
        
        for session_id in to_remove:
            del conversation_histories[session_id]
            
        logger.info(f"Cleaned {len(removed_files)} files and {len(to_remove)} conversation histories for video {video_id}")
        return True
    except Exception as e:
        logger.error(f"Error in clean_video_data: {e}")
        logger.error(traceback.format_exc())
        return False

# Function to detect follow-up questions
def is_followup_question(query: str) -> bool:
    """Detect if a question is likely a follow-up"""
    # Check for pronouns without clear referents
    followup_indicators = [
        r'\b(it|this|that|these|those)\b',
        r'\b(he|she|they)\b',
        r'^(and|but|so|because)\b',
        r'^(what about|how about)\b',
        r'^(why|when|where|how)\b'
    ]
    
    for pattern in followup_indicators:
        if re.search(pattern, query.lower()):
            return True
            
    return False

# Function to extract transcript segment based on timestamps
def extract_transcript_segment(transcript: str, start_time_sec: float, end_time_sec: float, video_duration: float) -> str:
    """Extract portion of transcript between start and end timestamps"""
    if not transcript:
        return ""
        
    # For very short segments, return whole transcript
    if end_time_sec - start_time_sec < 60:
        return transcript
        
    # Look for timestamp patterns like [MM:SS]
    segments = []
    current_time = 0
    current_text = ""
    
    # Split by potential timestamp markers
    lines = transcript.split('\n')
    
    for line in lines:
        # Try to find timestamp markers like [01:23] or [~01:23]
        match = re.search(r'\[(?:~)?(\d+):(\d+)\]', line)
        
        if match:
            minutes = int(match.group(1))
            seconds = int(match.group(2))
            timestamp = minutes * 60 + seconds
            
            # If we have accumulated text and timestamp
            if current_text and current_time > 0:
                # Add the previous segment
                segments.append((current_time, current_text.strip()))
            
            # Update for this segment
            current_time = timestamp
            current_text = re.sub(r'\[(?:~)?(\d+):(\d+)\]', '', line)
        else:
            # Continue accumulating text
            if current_text:
                current_text += " " + line
            else:
                current_text = line
    
    # Add the final segment
    if current_text and current_time > 0:
        segments.append((current_time, current_text.strip()))
    
    # If no proper segments were found, return the full transcript
    if not segments:
        return transcript
    
    # Find segments within the time range with some padding
    padding = 30  # 30 seconds before and after
    start_with_padding = max(0, start_time_sec - padding)
    end_with_padding = min(video_duration, end_time_sec + padding)
    
    relevant_segments = []
    
    for time_sec, text in segments:
        if start_with_padding <= time_sec <= end_with_padding:
            relevant_segments.append(f"[{time_sec//60}:{time_sec%60:02d}] {text}")
    
    # If no relevant segments found, use the closest ones
    if not relevant_segments and segments:
        # Find closest segment to start time
        closest_start = min(segments, key=lambda x: abs(x[0] - start_time_sec))
        
        # Find closest segment to end time
        closest_end = min(segments, key=lambda x: abs(x[0] - end_time_sec))
        
        # Collect all segments between closest_start and closest_end
        start_idx = segments.index(closest_start)
        end_idx = segments.index(closest_end)
        
        if start_idx > end_idx:
            start_idx, end_idx = end_idx, start_idx
        
        for i in range(start_idx, end_idx + 1):
            time_sec, text = segments[i]
            relevant_segments.append(f"[{time_sec//60}:{time_sec%60:02d}] {text}")
    
    if relevant_segments:
        return "\n\n".join(relevant_segments)
    
    # Fallback to full transcript
    return transcript

# API Routes
@app.get("/progress")
async def get_progress():
    """Return current progress status"""
    return progress_status

@app.get("/")
async def read_index():
    """Serve frontend page"""
    index_path = os.path.join("frontend", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return Response(content="<h1>Frontend Not Found</h1>", media_type="text/html")

@app.get("/videos")
async def list_videos():
    """Return a list of processed videos"""
    try:
        videos = []
        if os.path.exists(VIDEO_INFO_DIR):
            # Use ThreadPoolExecutor for faster file reading
            with ThreadPoolExecutor(max_workers=8) as executor:
                video_files = [f for f in os.listdir(VIDEO_INFO_DIR) if f.endswith(".json")]
                
                def read_video_file(file):
                    try:
                        with open(os.path.join(VIDEO_INFO_DIR, file), "r", encoding="utf-8") as f:
                            video_info = json.load(f)
                            
                            # Add file size information for better UI
                            transcript_path = video_info.get("transcript_path", "")
                            if os.path.exists(transcript_path):
                                transcript_size = os.path.getsize(transcript_path)
                                video_info["transcript_size"] = format_file_size(transcript_size)
                                
                            # Add processing status for long videos
                            video_info["processing_status"] = "complete"
                            if video_info.get("is_long_video", False):
                                chunks_total = video_info.get("chunks_total", 0)
                                chunks_completed = video_info.get("chunks_completed", 0)
                                if chunks_completed < chunks_total:
                                    video_info["processing_status"] = "in_progress"
                                    video_info["completion_percentage"] = int((chunks_completed / chunks_total) * 100)
                                
                            return video_info
                    except Exception as e:
                        logger.warning(f"Error reading video info file {file}: {e}")
                        return None
                
                # Process files in parallel
                results = list(executor.map(read_video_file, video_files))
                videos = [v for v in results if v]
            
        return {"videos": videos}
    except Exception as e:
        logger.error(f"Error listing videos: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(500, f"Error listing videos: {e}")

@app.post("/videos/process")
async def process(req: Request, background_tasks: BackgroundTasks):
    """Download, split, and transcribe YouTube video with long-video optimization"""
    start_time = time.time()
    try:
        data = await req.json()
        url = data.get("url")
        language = data.get("language", None)
        force_chunked = data.get("force_chunked", False)  # Option to force chunked processing

        if not url:
            raise HTTPException(400, "Missing URL")

        # Extract video ID
        video_id = extract_video_id(url)
        if not video_id:
            raise HTTPException(400, "Invalid YouTube URL")

        logger.info(f"Processing video: {video_id} with language: {language}")
        
        # Reset progress
        update_progress("Starting process...", 0, video_id, started_at=time.time())
        
        # Clean up any existing data for this video
        clean_video_data(video_id)
        logger.info(f"Cleaned existing data for video: {video_id}")

        # Define video-specific paths
        video_audio_path = os.path.join(AUDIO_DIR, f"{video_id}.mp3")
        video_transcript_path = os.path.join(TRANSCRIPT_DIR, f"{video_id}.txt")
        
        # Parallel execution for faster processing
        with ThreadPoolExecutor(max_workers=2) as executor:
            # Start video info fetch in parallel with directory creation
            info_future = executor.submit(get_video_info, url)
            
            # Create necessary directories
            os.makedirs(os.path.dirname(video_audio_path), exist_ok=True)
            os.makedirs(os.path.dirname(video_transcript_path), exist_ok=True)
            
            # Get video info
            update_progress("Getting video information...", 10, video_id)
            info = info_future.result()
        
        # Check if this is a long video (>30 minutes)
        video_duration = info.get("duration", 0)
        is_long_video = video_duration > 1800 or force_chunked
        
        # For very long videos, use chunked processing
        if is_long_video:
            # Save initial video info with long video flag
            initial_video_info = {
                "video_id": video_id,
                "title": info.get("title", "Unknown"),
                "duration": video_duration,
                "channel": info.get("channel", "Unknown"),
                "language": language,
                "keywords": [],
                "transcript_path": video_transcript_path,
                "is_long_video": True,
                "chunks_total": 0,  # Will be updated later
                "chunks_completed": 0,
                "processed_at": time.time(),
                "processing_status": "initializing"
            }
            
            with open(os.path.join(VIDEO_INFO_DIR, f"{video_id}.json"), "w", encoding="utf-8") as f:
                json.dump(initial_video_info, f, ensure_ascii=False)
            
            # Start background processing for long video
            background_tasks.add_task(
                process_long_video,
                url,
                video_id,
                video_audio_path,
                video_transcript_path,
                language,
                info
            )
            
            # Return initial response immediately
            return {
                "video_id": video_id,
                "title": info.get("title", "Unknown"),
                "duration": video_duration,
                "is_long_video": True,
                "processing_mode": "chunked",
                "status": "processing_started"
            }
        
        # Regular processing for shorter videos
        # Download audio
        update_progress("Downloading audio...", 25, video_id)
        audio_path = download_audio(url, video_audio_path)
        if not audio_path:
            error_msg = "Failed to download audio"
            raise HTTPException(500, error_msg)

        # Determine optimal segment size based on video duration
        max_segment_seconds = 120  # Default
        if video_duration > 3600:  # > 1 hour
            max_segment_seconds = 60  # Use longer segments
        
        # Split audio into segments
        update_progress("Processing audio...", 40, video_id)
        segments = split_audio(audio_path, max_seconds=max_segment_seconds)
        if not segments:
            error_msg = "Failed to split audio"
            raise HTTPException(500, error_msg)

        # Transcribe segments
        update_progress("Transcribing audio...", 60, video_id)
        transcript = transcribe_segments(segments, language)
        if not transcript.strip():
            error_msg = "Failed to transcribe audio"
            raise HTTPException(500, error_msg)

        # Auto-detect language if not provided
        detected_language = language
        if not detected_language:
            try:
                from langdetect import detect as detect_lang
                detected_language = detect_lang(transcript[:500])
                logger.info(f"Detected language: {detected_language}")
            except Exception as e:
                logger.warning(f"Language detection failed: {e}")
                detected_language = "en"

        # Save transcript
        save_to_file(transcript, video_transcript_path)

        # Extract keywords from transcript
        keywords = extract_keywords(transcript, max_keywords=10)
        logger.info(f"Extracted keywords: {keywords}")

        # Optimize chunk size for embedding based on transcript length
        chunk_size = 350
        if len(transcript) > 200000:  # Very long transcript
            chunk_size = 500
        
        # Create video-specific ChromaDB collection
        update_progress("Building semantic index...", 80, video_id)
        chunks = split_text(transcript, chunk_size=chunk_size, overlap=50)
        collection_name = f"youtube_transcript_{video_id}"
        embed_and_store(chunks, collection_name)

        # Save video info with transcript path
        video_info = {
            "video_id": video_id,
            "title": info.get("title", "Unknown"),
            "duration": info.get("duration", 0),
            "channel": info.get("channel", "Unknown"),
            "language": detected_language,
            "keywords": keywords,  # Add extracted keywords
            "transcript_path": video_transcript_path,
            "processed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "is_long_video": False
        }

        with open(os.path.join(VIDEO_INFO_DIR, f"{video_id}.json"), "w", encoding="utf-8") as f:
            json.dump(video_info, f, ensure_ascii=False)

        update_progress("Processing complete!", 100, video_id)
        
        processing_time = time.time() - start_time
        logger.info(f"Video {video_id} processed in {processing_time:.2f} seconds")

        return {
            "video_id": video_id, 
            "title": info.get("title", "Unknown"), 
            "transcript_preview": transcript[:500] + "..." if len(transcript) > 500 else transcript,
            "language": detected_language,
            "keywords": keywords,  # Return keywords in response
            "processing_time": f"{processing_time:.2f} seconds",
            "is_long_video": False
        }
    except HTTPException as he:
        # Pass through HTTP exceptions
        logger.error(f"HTTP Exception in process: {he}")
        raise he
    except Exception as e:
        # Log unexpected errors
        logger.error(f"Unexpected error in process: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(500, f"Processing error: {e}")

@app.post("/videos/{video_id}/question")
async def ask(video_id: str, req: Request):
    """Answer a question about the transcript with better casual conversation handling"""
    start_time = time.time()
    try:
        data = await req.json()
        question = data.get("query")
        language = data.get("language", "en")
        use_agent = data.get("use_agent", True)
        
        # New parameters 
        start_time_sec = data.get("start_time", None)  # Optional timestamp in seconds
        end_time_sec = data.get("end_time", None)      # Optional timestamp in seconds
        is_followup = data.get("is_followup", None)    # Optional explicit follow-up flag

        logger.info(f"Question request: '{question}' for video: {video_id} "
                   f"in language: {language} (agent={use_agent})")

        if not question:
            msg = "الرجاء طرح سؤال" if language=="ar" else "Please ask a question."
            return JSONResponse({"answer": msg})

        # Get video info for checking status and to extract title
        video_info_path = os.path.join(VIDEO_INFO_DIR, f"{video_id}.json")
        if not os.path.exists(video_info_path):
            msg = "فيديو غير موجود" if language=="ar" else "Video not found."
            return JSONResponse({"answer": msg})
            
        with open(video_info_path, "r", encoding="utf-8") as f:
            video_info = json.load(f)
            
        # Extract video title for better question relevance detection
        video_title = video_info.get("title", "")
            
        # Check if video is still processing (for long videos)
        if video_info.get("is_long_video", False) and video_info.get("processing_status") != "complete":
            chunks_total = video_info.get("chunks_total", 0)
            chunks_completed = video_info.get("chunks_completed", 0)
            
            if chunks_completed < chunks_total:
                completion_percentage = int((chunks_completed / chunks_total) * 100)
                if language == "ar":
                    msg = f"جاري معالجة الفيديو ({completion_percentage}% مكتمل). يرجى المحاولة لاحقًا."
                else:
                    msg = f"Video is still processing ({completion_percentage}% complete). Please try again later."
                return JSONResponse({"answer": msg, "processing_status": "in_progress"})

        # Load transcript
        video_path = os.path.join(TRANSCRIPT_DIR, f"{video_id}.txt")
        if not os.path.exists(video_path):
            msg = "لا يوجد نص متاح..." if language=="ar" else "No transcript available..."
            return JSONResponse({"answer": msg})
        
        # Get conversation history for this video session
        conversation_history = get_conversation_history(req, video_id)
        
        # If not explicitly specified, detect if this is a follow-up question
        if is_followup is None:
            is_followup = is_followup_question(question) and len(conversation_history) > 0
            
        logger.info(f"Question classified as follow-up: {is_followup}")
        
        # For time-based questions, extract only the relevant portion of the transcript
        if start_time_sec is not None or end_time_sec is not None:
            with open(video_path, "r", encoding="utf-8") as f:
                full_transcript = f.read()
                
            # Find the relevant portion of the transcript based on timestamps
            segment_transcript = extract_transcript_segment(
                full_transcript, 
                start_time_sec or 0, 
                end_time_sec or video_info.get("duration", 0),
                video_info.get("duration", 0)
            )
            
            # Check cache for this specific time segment
            time_segment_hash = hashlib.md5(
                f"{question}_{language}_{start_time_sec}_{end_time_sec}".encode()
            ).hexdigest()
            
            cache_file = os.path.join(CACHE_DIR, f"{video_id}_segments.json")
            cached_answer = None
            
            if os.path.exists(cache_file):
                try:
                    with open(cache_file, "r", encoding="utf-8") as f:
                        cached_answer = json.load(f).get(time_segment_hash)
                except Exception as e:
                    logger.error(f"Error reading segment cache: {e}")
                    
            if cached_answer:
                logger.info(f"Cache hit for time segment question hash: {time_segment_hash}")
                
                # Add this to conversation history even though it was cached
                conversation_history.append((question, cached_answer))
                if len(conversation_history) > 10:  # Limit history length
                    conversation_history.pop(0)
                    
                return {"answer": cached_answer, "cached": True, "time": f"{time.time()-start_time:.2f}s"}
            
            # If not in cache, process the question with the segment transcript and conversation history
            answer = ask_question(
                question, 
                segment_transcript, 
                video_id, 
                language, 
                use_agent=use_agent,
                conversation_history=conversation_history if is_followup else None,
                video_title=video_title  # Pass video title
            )
            
            # Add timestamp context to the answer
            start_min = int((start_time_sec or 0) // 60)
            start_sec = int((start_time_sec or 0) % 60)
            end_min = int((end_time_sec or video_info.get("duration", 0)) // 60)
            end_sec = int((end_time_sec or video_info.get("duration", 0)) % 60)
            
            # Add timestamp prefix based on language
            if language == "ar":
                time_prefix = f"[{start_min}:{start_sec:02d} - {end_min}:{end_sec:02d}] "
            else:
                time_prefix = f"[{start_min}:{start_sec:02d} - {end_min}:{end_sec:02d}] "
                
            answer = time_prefix + answer
            
            # Cache the segment answer
            os.makedirs(os.path.dirname(cache_file), exist_ok=True)
            
            segment_cache = {}
            if os.path.exists(cache_file):
                with open(cache_file, "r", encoding="utf-8") as f:
                    segment_cache = json.load(f)
                    
            segment_cache[time_segment_hash] = answer
            
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(segment_cache, f, ensure_ascii=False)
                
            # Add to conversation history
            conversation_history.append((question, answer))
            if len(conversation_history) > 10:  # Limit history length
                conversation_history.pop(0)
                
            return {"answer": answer, "cached": False, "time": f"{time.time()-start_time:.2f}s"}
                    
        # For regular questions, load the full transcript
        with open(video_path, "r", encoding="utf-8") as f:
            transcript = f.read()

        # Check cache key
        clean_q = re.sub(r'[^\w\s]', '', question.lower())
        q_hash = hashlib.md5(f"{clean_q}_{language}_{is_followup}".encode()).hexdigest()
        cache_file = os.path.join(CACHE_DIR, f"{video_id}.json")

        # Cache lookup
        cached = None
        if os.path.exists(cache_file) and not is_followup:  # Don't use cache for follow-ups
            with open(cache_file, "r", encoding="utf-8") as f:
                cached = json.load(f).get(q_hash)
                
        if cached:
            logger.info(f"Cache hit for question hash: {q_hash}")
            
            # Add to conversation history even if cached
            conversation_history.append((question, cached))
            if len(conversation_history) > 10:
                conversation_history.pop(0)
                
            return {"answer": cached, "cached": True, "time": f"{time.time()-start_time:.2f}s"}

        # Ask via QA or Agent with conversation history for follow-ups
        answer = ask_question(
            question, 
            transcript, 
            video_id, 
            language, 
            use_agent=use_agent,
            conversation_history=conversation_history if is_followup else None,
            video_title=video_title  # Pass video title
        )

        # If Arabic + agent, strip the English "Final Answer:" prefix
        if language == "ar" and use_agent:
            answer = re.sub(r'(?i)^final\s+answer\s*:\s*', '', answer).strip()

        # Save to cache (only for non-follow-up questions)
        if not is_followup:
            os.makedirs(CACHE_DIR, exist_ok=True)
            data_cache = {}
            if os.path.exists(cache_file):
                with open(cache_file, "r", encoding="utf-8") as f:
                    data_cache = json.load(f)
            data_cache[q_hash] = answer
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data_cache, f, ensure_ascii=False)

        # Add to conversation history
        conversation_history.append((question, answer))
        if len(conversation_history) > 10:  # Limit history length
            conversation_history.pop(0)

        return {"answer": answer, "cached": False, "time": f"{time.time()-start_time:.2f}s"}
    except Exception as e:
        logger.error(traceback.format_exc())
        return JSONResponse({"answer": f"Error: {e}"}, status_code=500)

@app.get("/videos/{video_id}/status")
async def get_video_status(video_id: str):
    """Get detailed processing status for a video"""
    try:
        # Check if the video is currently being processed
        if progress_status.get("video_id") == video_id:
            return progress_status
        
        # Check if it's already processed
        video_info_path = os.path.join(VIDEO_INFO_DIR, f"{video_id}.json")
        if os.path.exists(video_info_path):
            with open(video_info_path, "r", encoding="utf-8") as f:
                info = json.load(f)
            
            # Check for transcript
            transcript_path = info.get("transcript_path", "")
            has_transcript = os.path.exists(transcript_path)
            
            # Get transcript size if available
            transcript_size = 0
            if has_transcript:
                transcript_size = os.path.getsize(transcript_path)
            
            # Check ChromaDB collection
            chunks_count = 0
            try:
                from chromadb import PersistentClient
                client = PersistentClient(path=CHROMA_DIR)
                collection_name = f"youtube_transcript_{video_id}"
                collection = client.get_collection(name=collection_name)
                chunks_count = collection.count()
            except Exception:
                pass
            
            # Return status info
            return {
                "status": info.get("processing_status", "complete" if has_transcript else "unknown"),
                "video_id": video_id,
                "title": info.get("title", "Unknown"),
                "duration": info.get("duration", 0),
                "is_long_video": info.get("is_long_video", False),
                "chunks_total": info.get("chunks_total", 0),
                "chunks_completed": info.get("chunks_completed", 0),
                "transcript_available": has_transcript,
                "transcript_size": format_file_size(transcript_size),
                "chunks_indexed": chunks_count,
                "processed_at": info.get("processed_at", ""),
                "language": info.get("language", "en")
            }
        
        return {"status": "not_found", "video_id": video_id}
    except Exception as e:
        logger.error(f"Error getting video status: {e}")
        return {"status": "error", "message": str(e)}

# Add the DELETE endpoint for videos
@app.delete("/videos/{video_id}")
async def delete_video(video_id: str):
    """Delete a video and all associated data"""
    try:
        # First check if the video exists
        video_info_path = os.path.join(VIDEO_INFO_DIR, f"{video_id}.json")
        if not os.path.exists(video_info_path):
            raise HTTPException(404, "Video not found")
        
        # Clean all video data
        success = clean_video_data(video_id)
        
        # Delete video info file
        if os.path.exists(video_info_path):
            os.remove(video_info_path)
            
        if success:
            return {"status": "success", "message": f"Video {video_id} deleted successfully"}
        else:
            raise HTTPException(500, "Error deleting video data")
    except HTTPException as he:
        # Pass through HTTP exceptions
        raise he
    except Exception as e:
        logger.error(f"Error deleting video: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(500, f"Error deleting video: {e}")

# Add endpoint to update video language preference
@app.post("/videos/{video_id}/language")
async def update_video_language(video_id: str, req: Request):
    """Update the language preference for a video"""
    try:
        data = await req.json()
        language = data.get("language")
        
        if not language:
            raise HTTPException(400, "Language parameter is required")
            
        # Check if video exists
        video_info_path = os.path.join(VIDEO_INFO_DIR, f"{video_id}.json")
        if not os.path.exists(video_info_path):
            raise HTTPException(404, "Video not found")
            
        # Update language in video info
        with open(video_info_path, "r", encoding="utf-8") as f:
            video_info = json.load(f)
            
        video_info["language"] = language
        
        with open(video_info_path, "w", encoding="utf-8") as f:
            json.dump(video_info, f, ensure_ascii=False)
            
        return {"status": "success", "language": language}
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error updating language: {e}")
        raise HTTPException(500, f"Error updating language: {e}")

async def process_long_video(url, video_id, audio_path, transcript_path, language, video_info):
    """Background task to process very long videos in chunks"""
    try:
        start_time = time.time()
        duration = video_info.get("duration", 0)
        
        # Calculate optimal chunk size based on video duration
        # For very long videos (2+ hours), use larger chunks
        chunk_duration = 1200  # 10 minutes default
        if duration > 7200:  # > 2 hours
            chunk_duration = 1800  # 15 minutes
        
        # Calculate number of chunks
        total_chunks = max(1, int(duration / chunk_duration) + (1 if duration % chunk_duration > 0 else 0))
        
        # Update progress and video info
        update_progress(
            "Starting chunked processing for long video...", 
            5, 
            video_id, 
            processing_type="chunked",
            chunks_total=total_chunks,
            chunks_completed=0
        )
        
        # Update video info with chunk information
        video_info_path = os.path.join(VIDEO_INFO_DIR, f"{video_id}.json")
        with open(video_info_path, "r", encoding="utf-8") as f:
            current_info = json.load(f)
        
        current_info["chunks_total"] = total_chunks
        current_info["chunks_completed"] = 0
        current_info["processing_status"] = "downloading"
        
        with open(video_info_path, "w", encoding="utf-8") as f:
            json.dump(current_info, f, ensure_ascii=False)
        
        # Step 1: Download the full audio first
        logger.info(f"Downloading full audio for long video: {video_id}")
        update_progress("Downloading audio...", 10, video_id, chunks_total=total_chunks)
        
        full_audio_path = download_audio(url, audio_path)
        if not full_audio_path or not os.path.exists(full_audio_path):
            raise Exception("Failed to download audio for long video")
        
        # Get actual audio duration
        actual_duration = get_audio_duration(full_audio_path)
        if actual_duration > 0:
            # Recalculate chunks based on actual duration
            total_chunks = max(1, int(actual_duration / chunk_duration) + (1 if actual_duration % chunk_duration > 0 else 0))
            
            # Update progress and video info
            update_progress(
                "Audio downloaded, processing in chunks...", 
                15, 
                video_id, 
                chunks_total=total_chunks
            )
            
            # Update video info
            with open(video_info_path, "r", encoding="utf-8") as f:
                current_info = json.load(f)
            
            current_info["chunks_total"] = total_chunks
            current_info["duration"] = actual_duration
            current_info["processing_status"] = "transcribing"
            
            with open(video_info_path, "w", encoding="utf-8") as f:
                json.dump(current_info, f, ensure_ascii=False)
        
        # Process each chunk
        all_transcripts = []
        
        for chunk_idx in range(total_chunks):
            chunk_start = chunk_idx * chunk_duration
            chunk_end = min((chunk_idx + 1) * chunk_duration, actual_duration)
            
            update_progress(
                f"Processing chunk {chunk_idx + 1}/{total_chunks}...",
                None,  # Will be calculated from chunks
                video_id,
                chunks_completed=chunk_idx
            )
            
            # Create a temporary chunk file
            chunk_file = os.path.join(TEMP_DIR, f"{video_id}_chunk_{chunk_idx}.mp3")
            
            try:
                # Extract chunk from the full audio
                import subprocess
                cmd = [
                    "ffmpeg", "-y", "-i", full_audio_path, 
                    "-ss", str(chunk_start), 
                    "-to", str(chunk_end),
                    "-acodec", "libmp3lame",
                    "-q:a", "6",
                    "-ac", "16000",
                    chunk_file
                ]
                
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                
                # Split chunk into smaller segments for transcription
                max_segment_seconds = 60  # Larger segments for efficiency
                segments = split_audio(chunk_file, max_seconds=max_segment_seconds, is_long_video=True)

                
                # Transcribe segments
                chunk_transcript = transcribe_segments(segments, language)
                
                # Save chunk transcript to temporary file
                temp_transcript_path = os.path.join(TEMP_DIR, f"{video_id}_transcript_{chunk_idx}.txt")
                save_to_file(chunk_transcript, temp_transcript_path)
                
                # Add to full transcript with timestamp
                minutes = int(chunk_start / 60)
                seconds = int(chunk_start % 60)
                timestamp = f"[{minutes:02d}:{seconds:02d}]"
                
                all_transcripts.append(f"{timestamp} {chunk_transcript}")
                
                # Update progress
                update_progress(
                    f"Completed chunk {chunk_idx + 1}/{total_chunks}",
                    None,
                    video_id,
                    chunks_completed=chunk_idx + 1
                )
                
                # Update video info
                with open(video_info_path, "r", encoding="utf-8") as f:
                    current_info = json.load(f)
                
                current_info["chunks_completed"] = chunk_idx + 1
                
                with open(video_info_path, "w", encoding="utf-8") as f:
                    json.dump(current_info, f, ensure_ascii=False)
                
                # Clean up segment files to save space
                os.remove(chunk_file)
                for segment in segments:
                    if os.path.exists(segment):
                        os.remove(segment)
                
            except Exception as e:
                logger.error(f"Error processing chunk {chunk_idx}: {e}")
                # Continue with next chunk
        
        # Combine all transcripts
        full_transcript = "\n\n".join(all_transcripts)
        
        # Save combined transcript
        save_to_file(full_transcript, transcript_path)
        
        # Extract keywords from the full transcript
        keywords = extract_keywords(full_transcript, max_keywords=10)
        logger.info(f"Extracted keywords from long video: {keywords}")
        
        # Update progress
        update_progress(
            "Building semantic index...",
            90,
            video_id,
            chunks_completed=total_chunks
        )
        
        # Create ChromaDB collection using optimized chunk size for long videos
        chunks = split_text(full_transcript, chunk_size=750, overlap=30)
        collection_name = f"youtube_transcript_{video_id}"
        embed_and_store(chunks, collection_name)
        
        # Auto-detect language if not provided
        detected_language = language
        if not detected_language:
            try:
                from langdetect import detect as detect_lang
                detected_language = detect_lang(full_transcript[:500])
            except Exception:
                detected_language = "en"
        
        # Finalize video info
        final_info = {
            "video_id": video_id,
            "title": video_info.get("title", "Unknown"),
            "duration": actual_duration,
            "channel": video_info.get("channel", "Unknown"),
            "language": detected_language,
            "keywords": keywords,  # Add extracted keywords
            "transcript_path": transcript_path,
            "is_long_video": True,
            "chunks_total": total_chunks,
            "chunks_completed": total_chunks,
            "processing_status": "complete",
            "processed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "processing_time": f"{time.time() - start_time:.2f} seconds"
        }
        
        with open(video_info_path, "w", encoding="utf-8") as f:
            json.dump(final_info, f, ensure_ascii=False)
        
        update_progress(
            "Processing complete!",
            100,
            video_id,
            chunks_completed=total_chunks
        )
        
        logger.info(f"Long video {video_id} processed in {time.time() - start_time:.2f} seconds")
        
    except Exception as e:
        logger.error(f"Error processing long video {video_id}: {e}")
        logger.error(traceback.format_exc())
        
        # Update video info with error status
        try:
            video_info_path = os.path.join(VIDEO_INFO_DIR, f"{video_id}.json")
            if os.path.exists(video_info_path):
                with open(video_info_path, "r", encoding="utf-8") as f:
                    current_info = json.load(f)
                
                current_info["processing_status"] = "error"
                current_info["error_message"] = str(e)
                
                with open(video_info_path, "w", encoding="utf-8") as f:
                    json.dump(current_info, f, ensure_ascii=False)
        except Exception as e2:
            logger.error(f"Error updating video info after failure: {e2}")