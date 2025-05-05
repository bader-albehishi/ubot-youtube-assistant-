# rag_pipeline.py - RAG (Retrieval Augmented Generation) pipeline
import os
import re
import time
import logging
import numpy as np
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor
from chromadb import PersistentClient
from langsmith import traceable
from dotenv import load_dotenv

# Setup logging
logger = logging.getLogger("rag_pipeline")

# Load environment variables
load_dotenv(override=True)

# Constants
CHROMA_PATH = os.getenv("CHROMA_PATH", os.path.join("data", "chroma"))
COLLECTION_NAME = "youtube_transcripts"
CHUNK_SIZE = 500  # Default chunk size
CHUNK_OVERLAP = 100  # Default overlap between chunks

# OpenAI configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMBEDDING_MODEL = "text-embedding-ada-002"  # OpenAI's embedding model

# Initialize OpenAI client
from openai import OpenAI
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Thread local storage for OpenAI clients
import threading
_thread_local = threading.local()

def get_openai_client():
    """Get thread-local OpenAI client for thread safety"""
    if not hasattr(_thread_local, 'openai_client'):
        _thread_local.openai_client = OpenAI(api_key=OPENAI_API_KEY)
    return _thread_local.openai_client

def clean_text(text: str) -> str:
    """Clean and normalize text for better processing"""
    if not text:
        return ""
    
    # Convert text to string if needed
    if not isinstance(text, str):
        text = str(text)
    
    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text)
    
    # Fix spacing after punctuation
    text = re.sub(r'([.,?!;:])\s*', r'\1 ', text)
    
    # Trim whitespace
    return text.strip()

def split_text(text: str, chunk_size: int = CHUNK_SIZE, 
              overlap: int = CHUNK_OVERLAP) -> List[str]:
    """Split text into chunks with specified size and overlap"""
    if not text:
        logger.warning("No text to split")
        return []
        
    # Clean the text first
    text = clean_text(text)
    
    # Split by paragraphs first
    paragraphs = text.split('\n\n')
    if len(paragraphs) <= 1:
        # If no clear paragraphs, try splitting by sentences
        sentences = re.split(r'(?<=[.!?])\s+', text)
        paragraphs = sentences
    
    chunks = []
    current_chunk = ""
    
    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue
            
        # If adding this paragraph would exceed chunk_size, save current chunk and start a new one
        if len(current_chunk) + len(paragraph) > chunk_size:
            if current_chunk:
                chunks.append(current_chunk.strip())
            
            # Include overlap from previous chunk
            if current_chunk and len(current_chunk) > overlap:
                words = current_chunk.split()
                if len(words) > 5:
                    current_chunk = ' '.join(words[-5:]) + " " + paragraph
                else:
                    current_chunk = paragraph
            else:
                current_chunk = paragraph
        else:
            if current_chunk:
                current_chunk += " " + paragraph
            else:
                current_chunk = paragraph
    
    # Add the final chunk if it's not empty
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    # Ensure no empty chunks
    chunks = [c for c in chunks if c.strip()]
    
    logger.info(f"Split text into {len(chunks)} chunks")
    return chunks

def create_embeddings(texts: List[str]) -> List[List[float]]:
    """Create embeddings using OpenAI's embedding model"""
    if not texts:
        logger.warning("No texts to embed")
        return []
    
    start_time = time.time()
    client = get_openai_client()
    
    all_embeddings = []
    batch_size = 20  # Adjust based on rate limits
    
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        
        try:
            # Call OpenAI's embedding API
            response = client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=batch
            )
            
            # Extract embeddings from response
            batch_embeddings = [item.embedding for item in response.data]
            all_embeddings.extend(batch_embeddings)
            
        except Exception as e:
            logger.error(f"Error creating embeddings for batch: {e}")
            
            # Add empty embeddings as placeholders
            for _ in range(len(batch)):
                all_embeddings.append([0.0] * 1536)  # OpenAI ada embeddings are 1536 dimensions
    
    total_time = time.time() - start_time
    logger.info(f"Created {len(all_embeddings)} embeddings in {total_time:.2f}s")
    
    return all_embeddings

def embed_and_store(chunks: List[str], collection_name: str = COLLECTION_NAME) -> bool:
    """Create embeddings and store in ChromaDB"""
    if not chunks:
        logger.warning("No chunks to embed")
        return False
        
    logger.info(f"Embedding and storing {len(chunks)} chunks in collection '{collection_name}'...")
    
    # Create ChromaDB directories
    os.makedirs(CHROMA_PATH, exist_ok=True)
    
    try:
        # Initialize ChromaDB client
        client = PersistentClient(path=CHROMA_PATH)
        
        # Get or create collection
        try:
            collection = client.get_collection(name=collection_name)
            logger.info(f"Using existing collection: {collection_name}")
        except Exception:
            collection = client.create_collection(name=collection_name)
            logger.info(f"Created new collection: {collection_name}")
        
        # Process in optimized batches
        batch_size = min(50, len(chunks))
        
        for i in range(0, len(chunks), batch_size):
            batch_chunks = chunks[i:i+batch_size]
            
            # Create embeddings for this batch
            embeddings = create_embeddings(batch_chunks)
            
            if not embeddings or len(embeddings) != len(batch_chunks):
                logger.error(f"Embedding creation failed for batch {i//batch_size + 1}")
                continue
            
            # Create IDs and metadata with context information
            ids = [f"chunk-{i + j}" for j in range(len(batch_chunks))]
            metadatas = [{
                "chunk": i + j,
                "content_preview": chunk[:100] + "..." if len(chunk) > 100 else chunk,
                "length": len(chunk)
            } for j, chunk in enumerate(batch_chunks)]
            
            # Add to collection
            collection.add(
                embeddings=embeddings,
                documents=batch_chunks,
                metadatas=metadatas,
                ids=ids
            )
        
        logger.info(f"Successfully embedded and stored {len(chunks)} chunks")
        return True
        
    except Exception as e:
        logger.error(f"Error in embed_and_store: {e}")
        return False

def load_chroma_collection(collection_name: str = COLLECTION_NAME):
    """Load ChromaDB collection"""
    try:
        os.makedirs(CHROMA_PATH, exist_ok=True)
        client = PersistentClient(path=CHROMA_PATH)
        collection = client.get_or_create_collection(name=collection_name)
        
        # Get collection statistics
        collection_count = collection.count()
        logger.info(f"Loaded collection '{collection_name}' with {collection_count} documents")
        
        return collection
    except Exception as e:
        logger.error(f"Error loading ChromaDB collection '{collection_name}': {e}")
        return None

def retrieve_relevant_chunks(query: str, collection_name: str = COLLECTION_NAME, 
                           top_k: int = 5) -> List[Dict[str, Any]]:
    """Retrieve relevant chunks for a query using semantic search"""
    start_time = time.time()
    logger.info("###"*40 +f"Retrieving relevant chunks for query: '{query}'")
    
    try:
        # Create query embedding
        query_embedding = create_embeddings([query])
        if not query_embedding:
            logger.error("Failed to create query embedding")
            return []
        
        # Load collection
        collection = load_chroma_collection(collection_name)
        if not collection:
            logger.error(f"Failed to load collection: {collection_name}")
            return []
        
        # Query collection
        results = collection.query(
            query_embeddings=query_embedding,
            n_results=top_k,
            include=["documents", "metadatas", "distances"]
        )
        
        # Extract and format results
        chunks = []
        if results["documents"] and len(results["documents"]) > 0:
            documents = results["documents"][0]
            metadatas = results["metadatas"][0]
            distances = results["distances"][0] if "distances" in results else [0] * len(documents)
            
            for i, (doc, meta, dist) in enumerate(zip(documents, metadatas, distances)):
                chunks.append({
                    "text": doc,
                    "metadata": meta,
                    "relevance_score": 1 - dist,
                    "chunk_index": meta.get("chunk", i)
                })
        # print("&%###"*20)
        # print(chunks)
        # print("&%###"*20)

        return chunks

    except Exception as e:
        logger.error(f"Error retrieving relevant chunks: {e}")
        return []

def extract_keywords(text: str, max_keywords: int = 5) -> List[str]:
    """Extract important keywords from text using simple frequency analysis"""
    # Clean and normalize text
    clean = clean_text(text).lower()
    
    # Tokenize
    words = re.findall(r'\b\w+\b', clean)
    
    # Count frequency
    word_counts = {}
    for word in words:
        if len(word) > 3:  # Ignore very short words
            if word in word_counts:
                word_counts[word] += 1
            else:
                word_counts[word] = 1
    
    # Remove common stop words
    stop_words = {
        'the', 'and', 'but', 'not', 'what', 'where', 'when', 'who', 'how', 'why', 
        'this', 'that', 'these', 'those', 'with', 'from', 'have', 'will', 'would'
    }
    
    for word in stop_words:
        if word in word_counts:
            del word_counts[word]
    
    # Sort by frequency
    sorted_words = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)
    
    # Return top keywords
    keywords = [word for word, _ in sorted_words[:max_keywords]]
    
    return keywords