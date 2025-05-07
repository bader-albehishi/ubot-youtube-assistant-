# qa_system.py - Updated with fully integrated agent functionality
import os
import re
import logging
import time
import json
import hashlib
import chromadb
from typing import List, Dict, Tuple, Optional, Any, Generator
from concurrent.futures import ThreadPoolExecutor
from openai import OpenAI
from dotenv import load_dotenv
from langchain.agents import initialize_agent, Tool, AgentType
from langchain_openai import ChatOpenAI
from langchain.tools import tool
from langsmith import traceable

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("qa_system")

# Load environment variables
load_dotenv(override=True)

# Define constants
DATA_DIR = os.path.join("data")
CHROMA_DIR = os.path.join(DATA_DIR, "chroma")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
TRANSCRIPT_DIR = os.path.join(DATA_DIR, "transcripts")
VIDEO_INFO_DIR = os.path.join(DATA_DIR, "videos")

# Create directories if they don't exist
for directory in [CHROMA_DIR, CACHE_DIR, TRANSCRIPT_DIR, VIDEO_INFO_DIR]:
    os.makedirs(directory, exist_ok=True)

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
if not client.api_key:
    raise ValueError("OPENAI_API_KEY environment variable not set")

# Memory cache for faster repeat access
_memory_cache = {}

def is_video_related_question(question: str, video_title: str = None) -> bool:
    """
    Determine if a question is related to a video or is just casual conversation
    """
    # Common video-related question indicators
    video_indicators = [
        "in the video", "the video", "this video",
        "transcript", "in it", "they say", "mention",
        "talk about", "discuss", "explain", "show",
        "demonstrate", "what does", "where is", "when does",
        "how many", "why did", "who is",
        
        # Add summary-related phrases
        "summary", "summarize", "summarized", "summry", "summrized", 
        "recap", "overview", "sum up", "synopsis",
        "main points", "key points", "highlights",
        "long summary", "short summary", "brief summary",
        "detailed summary", "full summary", "quick summary"
    ]
    
    # Casual conversation or unrelated question indicators
    casual_indicators = [
        "hello", "hi there", "thank you", "thanks",
        "how are you", "good morning", "good afternoon",
        "i want", "please get me", "give me", "i need",
        "can i have", "bring me", "i would like"
    ]
    
    # Exception list - phrases that contain casual indicators but should be treated as video related
    exceptions = [
        "i need summary", "i need a summary", "i need the summary",
        "i need long", "i need a long", "i need the long",
        "i need short", "i need a short", "i need the short",
        "give me summary", "give me a summary", "give me the summary",
        "i want summary", "i want a summary", "i want the summary"
    ]
    
    # Normalize question
    question_lower = question.lower()
    
    # First check for exceptions - these take precedence
    for exception in exceptions:
        if exception in question_lower:
            return True
    
    # Check if contains video-related terms
    for indicator in video_indicators:
        if indicator in question_lower:
            return True
    
    # Then check if this is clearly a casual query
    for indicator in casual_indicators:
        if indicator in question_lower:
            # Make sure this isn't part of a longer phrase about summaries
            if "summary" in question_lower or "summarize" in question_lower or "recap" in question_lower:
                return True
            return False
    
    # If video title is provided, check if question mentions any part of the title
    if video_title:
        title_words = [word.lower() for word in video_title.split() if len(word) > 3]
        for word in title_words:
            if word in question_lower:
                return True
    
    # Default: For ambiguous questions without clear indicators, assume it might be video-related
    return True

def is_followup_question(question: str) -> bool:
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
        if re.search(pattern, question.lower()):
            return True
            
    return False

def get_video_title(video_id: str) -> str:
    """Get video title from stored video info"""
    try:
        video_info_path = os.path.join(VIDEO_INFO_DIR, f"{video_id}.json")
        if os.path.exists(video_info_path):
            with open(video_info_path, "r", encoding="utf-8") as f:
                video_info = json.load(f)
                return video_info.get("title", f"Video {video_id}")
        return f"Video {video_id}"
    except Exception as e:
        logger.error(f"Error getting video title: {e}")
        return f"Video {video_id}"

def retrieve_relevant_context(question: str, video_id: str, top_k: int = 5) -> List[str]:
    """Retrieve most relevant context from ChromaDB"""
    try:
        chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)
        collection_name = f"youtube_transcript_{video_id}"
        
        try:
            collection = chroma_client.get_collection(name=collection_name)
        except ValueError:
            logger.error(f"Collection {collection_name} does not exist")
            return []
        
        # Get embeddings for the question using OpenAI
        response = client.embeddings.create(
            model="text-embedding-ada-002",
            input=question
        )
        
        # Updated API response structure
        question_embedding = response.data[0].embedding
        
        # Query ChromaDB for most relevant chunks
        results = collection.query(
            query_embeddings=[question_embedding],
            n_results=top_k
        )
        
        if not results or not results.get('documents'):
            return []
            
        return results['documents'][0]
    except Exception as e:
        logger.error(f"Error retrieving context: {e}")
        return []

def get_cached_answer(hash_key: str, video_id: str) -> Optional[str]:
    """Get cached answer from memory or disk"""
    # Check memory cache first
    if video_id in _memory_cache and hash_key in _memory_cache[video_id]:
        logger.info(f"Memory cache hit for {hash_key}")
        return _memory_cache[video_id][hash_key]
    
    # Check disk cache
    cache_file = os.path.join(CACHE_DIR, f"{video_id}.json")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cache = json.load(f)
                answer = cache.get(hash_key)
                
                # Add to memory cache for future
                if answer:
                    if video_id not in _memory_cache:
                        _memory_cache[video_id] = {}
                    _memory_cache[video_id][hash_key] = answer
                
                return answer
        except Exception as e:
            logger.error(f"Error reading cache: {e}")
    
    return None

def save_to_cache(hash_key: str, answer: str, video_id: str) -> None:
    """Save answer to both memory and disk cache"""
    # Save to memory cache
    if video_id not in _memory_cache:
        _memory_cache[video_id] = {}
    _memory_cache[video_id][hash_key] = answer
    
    # Save to disk cache
    cache_file = os.path.join(CACHE_DIR, f"{video_id}.json")
    data = {}
    
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"Error reading cache for saving: {e}")
    
    data[hash_key] = answer
    
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error saving to cache: {e}")

def generate_prompt(question: str, context: List[str], language: str = "en", conversation_history: List[Tuple[str, str]] = None) -> dict:
    """Generate a prompt for the standard QA mode"""
    
    # Join context chunks with separators
    context_text = "\n\n---\n\n".join(context)
    
    # Base system prompt with language adaptation
    if language == "ar":
        system_prompt = """أنت مساعد ذكي، ومهمتك هي الإجابة على الأسئلة حول نص مقطع من فيديو بناءً على المقتطفات المقدمة من النص.
        
قواعد هامة:
1. إذا كانت المقتطفات النصية لا تحتوي على معلومات كافية للإجابة على السؤال، قل "لا أستطيع الإجابة على هذا السؤال بناءً على نص الفيديو."
2. لا تختلق إجابات أو تفترض معلومات غير موجودة في المقتطفات.
3. استند في إجاباتك فقط على محتوى المقتطفات، وليس على معرفتك الخاصة.
4. كن دقيقًا ومباشرًا في إجاباتك.
5. إذا كان السؤال خارج سياق الفيديو أو غير ذي صلة، فوضح ذلك للمستخدم بطريقة مهذبة.

سيتم تقديم مقتطفات من نص الفيديو، والمطلوب منك الإجابة عن أسئلة المستخدم اعتمادًا على هذه المقتطفات فقط."""
    else:
        system_prompt = """You are an intelligent assistant. Your task is to answer questions about a video transcript based on the provided transcript excerpts.

Important rules:
1. If the transcript excerpts don't contain enough information to answer the question, say "I cannot answer this question based on the video transcript."
2. Don't make up answers or assume information not present in the excerpts.
3. Base your answers only on the content of the excerpts, not on your own knowledge.
4. Be concise and direct in your answers.
5. If the question is outside the context of the video or irrelevant, politely clarify this to the user.

You will be given excerpts from the video transcript, and you need to answer the user's questions based solely on these excerpts."""

    # Add conversation history if available
    conversation_context = ""
    if conversation_history and len(conversation_history) > 0:
        if language == "ar":
            conversation_context = "\n\nسياق المحادثة السابقة:\n"
        else:
            conversation_context = "\n\nPrevious conversation context:\n"
            
        for i, (q, a) in enumerate(conversation_history):
            if language == "ar":
                conversation_context += f"سؤال {i+1}: {q}\n"
                conversation_context += f"إجابة {i+1}: {a}\n\n"
            else:
                conversation_context += f"Question {i+1}: {q}\n"
                conversation_context += f"Answer {i+1}: {a}\n\n"

    # User message with question and context
    if language == "ar":
        user_message = f"""سؤال: {question}

مقتطفات من نص الفيديو:
{context_text}

{conversation_context}

الرجاء الإجابة على السؤال بدقة استنادًا فقط إلى مقتطفات النص المقدمة."""
    else:
        user_message = f"""Question: {question}

Transcript excerpts:
{context_text}

{conversation_context}

Please answer the question accurately based only on the provided transcript excerpts."""

    return {"system": system_prompt, "user": user_message}

def generate_agent_prompt(question: str, context: List[str], language: str = "en", conversation_history: List[Tuple[str, str]] = None) -> dict:
    """Generate a prompt for the ReAct agent approach"""
    
    # Join context chunks with separators
    context_text = "\n\n---\n\n".join(context)
    
    # Base system prompt with language adaptation
    if language == "ar":
        system_prompt = """أنت مساعد ذكي يستخدم نهج التفكير خطوة بخطوة. مهمتك هي الإجابة على الأسئلة حول نص مقطع فيديو.

عند تحليل السؤال، فكر أولاً في:
1. ما هي المعلومات الرئيسية المطلوبة؟
2. هل توجد هذه المعلومات في مقتطفات النص المقدمة؟
3. ما هي الأجزاء الأكثر صلة من النص للإجابة على هذا السؤال؟

من ثم قم بإنشاء إجابة:
1. استند فقط على المعلومات الموجودة في مقتطفات النص.
2. تجنب اختلاق معلومات أو افتراضات خارج النص.
3. إذا كانت المعلومات غير متوفرة، اعترف بذلك بوضوح.

استخدم هذا التنسيق:
الفكر: [تحليلك للسؤال وكيفية الإجابة عليه، وذكر الأدلة من النص]
الإجابة النهائية: [إجابتك المباشرة على السؤال]"""
    else:
        system_prompt = """You are an intelligent assistant using a step-by-step reasoning approach. Your task is to answer questions about a video transcript.

When analyzing the question, first think about:
1. What key information is being asked for?
2. Is this information present in the provided transcript excerpts?
3. Which parts of the transcript are most relevant to answering this question?

Then formulate an answer:
1. Base your answer solely on information in the transcript excerpts.
2. Avoid making up information or assumptions beyond the transcript.
3. If information is not available, clearly acknowledge this.

Use this format:
Thought: [your analysis of the question and how to answer it, citing evidence from the transcript]
Final Answer: [your direct answer to the question]"""

    # Add conversation history if available
    conversation_context = ""
    if conversation_history and len(conversation_history) > 0:
        if language == "ar":
            conversation_context = "\n\nسياق المحادثة السابقة:\n"
        else:
            conversation_context = "\n\nPrevious conversation context:\n"
            
        for i, (q, a) in enumerate(conversation_history):
            if language == "ar":
                conversation_context += f"سؤال {i+1}: {q}\n"
                conversation_context += f"إجابة {i+1}: {a}\n\n"
            else:
                conversation_context += f"Question {i+1}: {q}\n"
                conversation_context += f"Answer {i+1}: {a}\n\n"

    # User message with question and context
    if language == "ar":
        user_message = f"""سؤال: {question}

مقتطفات من نص الفيديو:
{context_text}

{conversation_context}

الرجاء التفكير خطوة بخطوة ثم تقديم إجابتك النهائية."""
    else:
        user_message = f"""Question: {question}

Transcript excerpts:
{context_text}

{conversation_context}

Please think step-by-step and then provide your final answer."""

    return {"system": system_prompt, "user": user_message}

def generate_agent_prompt(question: str, context: List[str], language: str = "en", conversation_history: List[Tuple[str, str]] = None) -> dict:
    """Generate a prompt for the ReAct agent approach"""
    
    # Join context chunks with separators
    context_text = "\n\n---\n\n".join(context)
    
    # Base system prompt with language adaptation
    if language == "ar":
        system_prompt = """أنت مساعد ذكي يستخدم نهج التفكير خطوة بخطوة. مهمتك هي الإجابة على الأسئلة حول نص مقطع فيديو.

عند تحليل السؤال، فكر أولاً في:
1. ما هي المعلومات الرئيسية المطلوبة؟
2. هل توجد هذه المعلومات في مقتطفات النص المقدمة؟
3. ما هي الأجزاء الأكثر صلة من النص للإجابة على هذا السؤال؟

من ثم قم بإنشاء إجابة:
1. استند فقط على المعلومات الموجودة في مقتطفات النص.
2. تجنب اختلاق معلومات أو افتراضات خارج النص.
3. إذا كانت المعلومات غير متوفرة، اعترف بذلك بوضوح.

استخدم هذا التنسيق:
الفكر: [تحليلك للسؤال وكيفية الإجابة عليه، وذكر الأدلة من النص]
الإجابة النهائية: [إجابتك المباشرة على السؤال]"""
    else:
        system_prompt = """You are an intelligent assistant using a step-by-step reasoning approach. Your task is to answer questions about a video transcript.

When analyzing the question, first think about:
1. What key information is being asked for?
2. Is this information present in the provided transcript excerpts?
3. Which parts of the transcript are most relevant to answering this question?

Then formulate an answer:
1. Base your answer solely on information in the transcript excerpts.
2. Avoid making up information or assumptions beyond the transcript.
3. If information is not available, clearly acknowledge this.

Use this format:
Thought: [your analysis of the question and how to answer it, citing evidence from the transcript]
Final Answer: [your direct answer to the question]"""

    # Add conversation history if available
    conversation_context = ""
    if conversation_history and len(conversation_history) > 0:
        if language == "ar":
            conversation_context = "\n\nسياق المحادثة السابقة:\n"
        else:
            conversation_context = "\n\nPrevious conversation context:\n"
            
        for i, (q, a) in enumerate(conversation_history):
            if language == "ar":
                conversation_context += f"سؤال {i+1}: {q}\n"
                conversation_context += f"إجابة {i+1}: {a}\n\n"
            else:
                conversation_context += f"Question {i+1}: {q}\n"
                conversation_context += f"Answer {i+1}: {a}\n\n"

    # User message with question and context
    if language == "ar":
        user_message = f"""سؤال: {question}

مقتطفات من نص الفيديو:
{context_text}

{conversation_context}

الرجاء التفكير خطوة بخطوة ثم تقديم إجابتك النهائية."""
    else:
        user_message = f"""Question: {question}

Transcript excerpts:
{context_text}

{conversation_context}

Please think step-by-step and then provide your final answer."""

    return {"system": system_prompt, "user": user_message}

def is_summary_request(query: str) -> bool:
    """Check if the query is requesting a summary of the video"""
    query_lower = query.lower()
    summary_terms = [
        "summary", "summarize", "summarized", "summarization", "sum up",
        "brief", "overview", "recap", "synopsis", "tldr", "main points", "key points",
        "ملخص", "لخص", "تلخيص", "موجز", "نبذة", "أهم النقاط"
    ]
    
    for term in summary_terms:
        if term in query_lower:
            return True
    
    return False

@traceable()
def ask_question(
    question: str, 
    transcript: str, 
    video_id: str = None,
    language: str = "en",
    use_agent: bool = False,
    conversation_history: list = None,
    video_title: str = None
) -> str:
    """
    Ask a question about the transcript with intelligent conversation handling
    """
    start_time = time.time()
    
    # Get video title if not provided
    if not video_title and video_id:
        video_title = get_video_title(video_id)
        
    # If no conversation history or not a follow-up, check if question is video-related
    if not conversation_history or len(conversation_history) == 0 or not is_followup_question(question):
        if not is_video_related_question(question, video_title):
            # If question is not video-related, return a polite explanation
            if language == "ar":
                return "الرجاء طرح سؤال متعلق بالفيديو."
            else:
                return "Please ask a question related to the video transcript."
    
    logger.info(f"Processing question: {question}")

    # Handle empty transcript
    if not transcript or len(transcript.strip()) < 10:
        if language == "ar":
            return "عذراً، لا يوجد نص متاح لهذا الفيديو."
        else:
            return "Sorry, there is no transcript available for this video."
    
    # Check if this is a summary request
    if is_summary_request(question):
        logger.info(f"Detected summary request: {question}")
        return summarize_transcript(transcript, "medium", language)

    # Calculate hash for caching (include language and agent mode)
    clean_q = re.sub(r'[^\w\s]', '', question.lower())
    is_followup_str = "followup" if is_followup_question(question) else "direct"
    q_hash = hashlib.md5(f"{clean_q}_{language}_{is_followup_str}_{use_agent}".encode()).hexdigest()
    
    # Check cache for non-followup questions
    if not is_followup_question(question) or not conversation_history:
        cached_answer = get_cached_answer(q_hash, video_id)
        if cached_answer:
            logger.info(f"Cache hit for question hash: {q_hash}")
            return cached_answer

    # Retrieve relevant context if we have video_id
    context = []
    if video_id:
        context = retrieve_relevant_context(question, video_id)
    
    # If no context found or no video_id, use the whole transcript but limit it
    if not context:
        # Split transcript into chunks of ~1000 characters
        max_chunk_size = 1000
        chunks = []
        
        # Handle potential very long transcripts
        if len(transcript) > 10000:
            # For very long transcripts, use a sliding window approach
            transcript_lines = transcript.split('\n')
            current_chunk = []
            current_size = 0
            
            for line in transcript_lines:
                if current_size + len(line) > max_chunk_size and current_chunk:
                    chunks.append('\n'.join(current_chunk))
                    # Overlap with previous chunk for context continuity
                    overlap_size = min(3, len(current_chunk))
                    current_chunk = current_chunk[-overlap_size:] if overlap_size > 0 else []
                    current_size = sum(len(line) for line in current_chunk)
                
                current_chunk.append(line)
                current_size += len(line)
            
            if current_chunk:
                chunks.append('\n'.join(current_chunk))
        else:
            # For shorter transcripts, simply split by paragraphs
            paragraphs = transcript.split('\n\n')
            current_chunk = []
            current_size = 0
            
            for para in paragraphs:
                if current_size + len(para) > max_chunk_size and current_chunk:
                    chunks.append('\n\n'.join(current_chunk))
                    current_chunk = []
                    current_size = 0
                
                current_chunk.append(para)
                current_size += len(para) + 2  # +2 for the '\n\n'
            
            if current_chunk:
                chunks.append('\n\n'.join(current_chunk))
        
        # Limit to a reasonable number of chunks for context
        max_chunks = 5
        if len(chunks) > max_chunks:
            # If we have too many chunks, use the first and last few chunks
            # This captures the beginning and end of the transcript
            context = chunks[:max_chunks//2] + chunks[-max_chunks//2:]
        else:
            context = chunks
    
    # Generate prompt based on approach
    if use_agent:
        prompt = generate_agent_prompt(question, context, language, conversation_history)
    else:
        prompt = generate_prompt(question, context, language, conversation_history)
    
    try:
        # Get response from OpenAI with new client API
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": prompt["system"]},
                {"role": "user", "content": prompt["user"]}
            ],
            temperature=0.3,  # Lower temperature for more factual responses
            max_tokens=500
        )
        
        answer = response.choices[0].message.content.strip()
        
        # Log processing time
        processing_time = time.time() - start_time
        logger.info(f"Processed question in {processing_time:.2f}s")
        
        # If using agent format, extract the final answer
        if use_agent and "Final Answer:" in answer:
            print("\n=== AGENT THINKING PROCESS ===")
            print(answer)
            print("===========================\n")
            final_answer_match = re.search(r'Final Answer:(.*?)(?:$|\n\n)', answer, re.DOTALL)
            if final_answer_match:
                answer = final_answer_match.group(1).strip()
        
        # Cache the result for non-followup questions
        if not is_followup_question(question) or not conversation_history:
            save_to_cache(q_hash, answer, video_id)
        
        return answer
    except Exception as e:
        logger.error(f"Error in ask_question: {e}")
        if language == "ar":
            return "عذراً، حدث خطأ أثناء معالجة السؤال. الرجاء المحاولة مرة أخرى."
        else:
            return "Sorry, an error occurred while processing your question. Please try again."

def ask_question_streaming(
    question: str, 
    transcript: str, 
    video_id: str = None,
    language: str = "en",
    use_agent: bool = False,
    conversation_history: list = None,
    video_title: str = None
) -> Generator[str, None, None]:
    """
    Ask a question with streaming response
    """
    # Get video title if not provided
    if not video_title and video_id:
        video_title = get_video_title(video_id)
        
    # First check if question is video-related
    if not conversation_history or len(conversation_history) == 0 or not is_followup_question(question):
        if not is_video_related_question(question, video_title):
            # If question is not video-related, return a polite explanation
            if language == "ar":
                yield "الرجاء طرح سؤال متعلق بالفيديو."
                return
            else:
                yield "Please ask a question related to the video transcript."
                return
                
    start_time = time.time()
    logger.info(f"Processing streaming question: {question}")

    # Handle empty transcript
    if not transcript or len(transcript.strip()) < 10:
        if language == "ar":
            yield "عذراً، لا يوجد نص متاح لهذا الفيديو."
        else:
            yield "Sorry, there is no transcript available for this video."
        return

    # Retrieve relevant context if we have video_id
    context = []
    if video_id:
        context = retrieve_relevant_context(question, video_id)
    
    # If no context found or no video_id, use the whole transcript but limit it
    if not context:
        # Split transcript into manageable chunks
        max_chunk_size = 1000
        chunks = []
        
        # Handle long transcripts with sliding window
        if len(transcript) > 10000:
            transcript_lines = transcript.split('\n')
            current_chunk = []
            current_size = 0
            
            for line in transcript_lines:
                if current_size + len(line) > max_chunk_size and current_chunk:
                    chunks.append('\n'.join(current_chunk))
                    # Overlap with previous chunk
                    overlap_size = min(3, len(current_chunk))
                    current_chunk = current_chunk[-overlap_size:] if overlap_size > 0 else []
                    current_size = sum(len(line) for line in current_chunk)
                
                current_chunk.append(line)
                current_size += len(line)
            
            if current_chunk:
                chunks.append('\n'.join(current_chunk))
        else:
            # Simple paragraph splitting for shorter transcripts
            paragraphs = transcript.split('\n\n')
            current_chunk = []
            current_size = 0
            
            for para in paragraphs:
                if current_size + len(para) > max_chunk_size and current_chunk:
                    chunks.append('\n\n'.join(current_chunk))
                    current_chunk = []
                    current_size = 0
                
                current_chunk.append(para)
                current_size += len(para) + 2
            
            if current_chunk:
                chunks.append('\n\n'.join(current_chunk))
        
        # Limit to a reasonable number of chunks
        max_chunks = 5
        if len(chunks) > max_chunks:
            context = chunks[:max_chunks//2] + chunks[-max_chunks//2:]
        else:
            context = chunks
    
    # Generate prompt based on approach
    if use_agent:
        prompt = generate_agent_prompt(question, context, language, conversation_history)
    else:
        prompt = generate_prompt(question, context, language, conversation_history)
    
    try:
        # Get streaming response from OpenAI with new client API
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": prompt["system"]},
                {"role": "user", "content": prompt["user"]}
            ],
            temperature=0.3,
            max_tokens=500,
            stream=True
        )
        
        # Initialize variables for streaming
        collected_messages = []
        in_final_answer = False
        
        for chunk in response:
            content = chunk.choices[0].delta.content or ""
            if not content:
                continue
                
            collected_messages.append(content)
            
            # Check if we're in the final answer section
            if use_agent and "Final Answer:" in content:
                in_final_answer = True
                # Don't yield the "Final Answer:" marker
                content = content.replace("Final Answer:", "")
                
            # For agent, only stream the final answer part
            if use_agent:
                if in_final_answer:
                    yield content
            else:
                # For regular mode, stream everything
                yield content
        
        # Log processing time
        processing_time = time.time() - start_time
        logger.info(f"Processed streaming question in {processing_time:.2f}s")
        
        # Calculate hash for caching
        clean_q = re.sub(r'[^\w\s]', '', question.lower())
        is_followup_str = "followup" if is_followup_question(question) else "direct"
        q_hash = hashlib.md5(f"{clean_q}_{language}_{is_followup_str}_{use_agent}".encode()).hexdigest()
        
        # Cache the complete response for non-follow-up questions
        if (not is_followup_question(question) or not conversation_history) and video_id:
            full_response = "".join(collected_messages)
            save_to_cache(q_hash, full_response, video_id)
        
    except Exception as e:
        logger.error(f"Error in ask_question_streaming: {e}")
        if language == "ar":
            yield "عذراً، حدث خطأ أثناء معالجة السؤال. الرجاء المحاولة مرة أخرى."
        else:
            yield "Sorry, an error occurred while processing your question. Please try again."

def summarize_transcript(transcript: str, length: str = "medium", language: str = "en") -> str:
    """
    Summarize the transcript with variable length
    """
    if not transcript or len(transcript.strip()) < 50:
        if language == "ar":
            return "النص قصير جدًا للتلخيص."
        else:
            return "The transcript is too short to summarize."
    
    # Adjust token count based on desired summary length
    if length == "short":
        max_tokens = 150
        summary_type = "concise"
    elif length == "long":
        max_tokens = 500
        summary_type = "comprehensive"
    else:  # medium
        max_tokens = 300
        summary_type = "balanced"
    
    # Generate system prompt based on language
    if language == "ar":
        system_prompt = f"""أنت مساعد ذكي متخصص في تلخيص محتوى الفيديو. قم بإنشاء ملخص {summary_type} لنص الفيديو المقدم.
        
قواعد التلخيص:
1. ركز على النقاط والمعلومات الرئيسية.
2. تضمين العناوين الفرعية إذا كان ذلك مناسبًا.
3. الحفاظ على تسلسل منطقي للأفكار.
4. تجنب التفاصيل غير الضرورية.
5. الاختصار مع الحفاظ على المعنى الكامل."""
    else:
        system_prompt = f"""You are an intelligent assistant specialized in summarizing video content. Create a {summary_type} summary of the provided video transcript.
        
Summarization rules:
1. Focus on key points and information.
2. Include subheadings if appropriate.
3. Maintain a logical flow of ideas.
4. Omit unnecessary details.
5. Be concise while preserving full meaning."""

    # Handle long transcripts by chunking
    if len(transcript) > 10000:
        chunks = []
        chunk_size = 4000  # Adjust based on performance
        overlap = 500
        
        # Create overlapping chunks
        for i in range(0, len(transcript), chunk_size - overlap):
            end_idx = min(i + chunk_size, len(transcript))
            chunks.append(transcript[i:end_idx])
            
            if end_idx == len(transcript):
                break
        
        # Process each chunk separately
        summaries = []
        for idx, chunk in enumerate(chunks):
            try:
                if language == "ar":
                    user_message = f"""جزء {idx+1}/{len(chunks)} من نص الفيديو:

{chunk}

قم بتلخيص هذا الجزء من النص، مع التركيز على النقاط الرئيسية والمعلومات المهمة."""
                else:
                    user_message = f"""Part {idx+1}/{len(chunks)} of the video transcript:

{chunk}

Summarize this portion of the transcript, focusing on the main points and important information."""
                
                response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message}
                    ],
                    temperature=0.3,
                    max_tokens=max(100, max_tokens // len(chunks))
                )
                
                summary = response.choices[0].message.content.strip()
                summaries.append(summary)
            except Exception as e:
                logger.error(f"Error summarizing chunk {idx}: {e}")
                if language == "ar":
                    summaries.append(f"[خطأ في تلخيص الجزء {idx+1}]")
                else:
                    summaries.append(f"[Error summarizing part {idx+1}]")
        
        # Combine chunk summaries
        combined_summaries = "\n\n".join(summaries)
        
        # Generate final combined summary
        try:
            if language == "ar":
                final_prompt = f"""فيما يلي ملخصات لأجزاء مختلفة من نص الفيديو:

{combined_summaries}

قم بدمج هذه الملخصات في ملخص {summary_type} واحد متماسك للفيديو بأكمله، مع إزالة أي تكرار وضمان تدفق المعلومات بشكل منطقي."""
            else:
                final_prompt = f"""Below are summaries of different parts of the video transcript:

{combined_summaries}

Combine these summaries into one coherent {summary_type} summary of the entire video, removing any repetition and ensuring a logical flow of information."""
            
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": final_prompt}
                ],
                temperature=0.3,
                max_tokens=max_tokens
            )
            
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Error in final summary combination: {e}")
            if language == "ar":
                return "عذراً، حدث خطأ أثناء إنشاء الملخص النهائي."
            else:
                return "Sorry, an error occurred while creating the final summary."
    else:
        # For shorter transcripts, process in one go
        try:
            if language == "ar":
                user_message = f"""نص الفيديو:

{transcript}

قم بإنشاء ملخص {summary_type} لهذا الفيديو، مع التركيز على النقاط الرئيسية والمعلومات المهمة."""
            else:
                user_message = f"""Video transcript:

{transcript}

Create a {summary_type} summary of this video, focusing on the main points and important information."""
            
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.3,
                max_tokens=max_tokens
            )
            
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Error in summarize_transcript: {e}")
            if language == "ar":
                return "عذراً، حدث خطأ أثناء تلخيص النص. الرجاء المحاولة مرة أخرى."
            else:
                return "Sorry, an error occurred while summarizing the transcript. Please try again."

@tool
def search_transcript_tool(question: str, transcript: str) -> str:
    """Search the transcript and answer the question based on its content."""
    # You can plug in your semantic search logic here if needed
    return ask_question(question, transcript, video_id="dummy", language="en", use_agent=False)

@traceable()
def get_qa_agent(transcript: str, video_id: str, language: str = "en"):
    """
    Build a LangChain agent that answers questions 
    in the desired language using your TranscriptQA tool.
    """
    # 1) Define the tool as before
    def transcript_qa_tool(question: str) -> str:
        return ask_question(question, transcript, video_id, language, use_agent=False)

    tools = [
        Tool(
            name="TranscriptQA",
            func=transcript_qa_tool,
            description="Answer questions based on the video transcript"
        )
    ]

    # 2) Pick your LLM
    llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0)

    # 3) Build a language‐aware prefix
    lang_name = "Arabic" if language == "ar" else "English"
    prefix = (
        f"You are a helpful assistant.  "
        f"Answer the user's question about the video transcript **in {lang_name} only**.  "
        f"If the user asked in Arabic, respond completely in Arabic; "
        f"otherwise, respond in English."
    )

    # 4) Initialize the agent with that prefix
    return initialize_agent(
        tools=tools,
        llm=llm,
        agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
        verbose=True,
        agent_kwargs={"prefix": prefix}
    )