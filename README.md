# UBot - YouTube AI Assistant
![f1](https://github.com/user-attachments/assets/b113f3f1-66b1-427c-b3b1-4b06cad444b0)


![f2](https://github.com/user-attachments/assets/b1fe1665-9acc-4053-bc51-53132eb760ba)

![f3](https://github.com/user-attachments/assets/3c15a6cc-a47a-45ab-8cb0-bb702fe4f170)

![f6](https://github.com/user-attachments/assets/e8397bb0-56cd-4379-adfc-54162f70cc07)



UBot is an advanced YouTube AI Assistant that helps users understand video content through transcription, Q&A, and summarization. The application downloads audio from YouTube videos, transcribes it, and enables natural language conversations about the video content.

## Features

- **YouTube Video Processing**: Extract audio from YouTube videos and transcribe it using OpenAI's Whisper
- **Intelligent Question Answering**: Ask natural language questions about video content
- **Semantic Search**: Uses embeddings and vector search to find relevant context for answers
- **Bilingual Support**: Complete English/Arabic interface with RTL support
- **Conversational Memory**: Tracks conversation history and handles follow-up questions
- **Keyword Extraction**: Automatically identifies important topics in videos
- **Chat History Management**: Save, reload, and manage multiple chat sessions
- **Long Video Support**: Optimized processing for videos over 30 minutes

## Architecture Overview

UBot is built with a FastAPI backend and a modern, responsive web frontend:

### Backend Components

- **FastAPI Application (`app.py`)**: Main coordinator for all operations
- **YouTube Handling (`youtube_handler.py`)**: Extracts video information and downloads audio
- **Audio Processing (`audio_processing.py`)**: Splits audio files for efficient processing
- **Transcription (`transcription.py`)**: Uses OpenAI's Whisper for audio transcription
- **RAG Pipeline (`rag_pipeline.py`)**: Implements text chunking and embedding creation
- **QA System (`qa_system.py`)**: Retrieves context and generates answers
- **Utilities (`utils.py`)**: Helper functions for file operations

### Frontend Components

- **HTML (`index.html`)**: Responsive design with sidebar for chat history
- **JavaScript (`app.js`)**: Client-side interactions and state management
- **CSS (`style.css`)**: Modern UI with animations and RTL support

## Installation

### Prerequisites

- Python 3.8+
- FFmpeg (for audio processing)
- OpenAI API key

### Setup Instructions

1. Clone the repository:
   ```bash
   git clone https://github.com/bader-albehishi/ubot.git
   cd ubot
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install required packages:
   ```bash
   pip install -r requirements.txt
   ```

4. Create a `.env` file in the project root with your OpenAI API key:
   ```
   OPENAI_API_KEY=your_api_key_here
   ```

5. Install FFmpeg (required for audio processing):

   **Windows**:
   - Download the FFmpeg build from [ffmpeg.org](https://ffmpeg.org/download.html) or [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) (recommended)
   - Extract the ZIP file to a location on your computer (e.g., `C:\ffmpeg`)
   - Add the `bin` folder to your system PATH:
     - Right-click on "This PC" or "My Computer" → Properties → Advanced system settings → Environment Variables
     - Under System Variables, find "Path" and click Edit
     - Add the path to the FFmpeg bin folder (e.g., `C:\ffmpeg\bin`)
     - Click OK to save

   **macOS** (using Homebrew):
   ```bash
   brew install ffmpeg
   ```

   **Ubuntu/Debian**:
   ```bash
   sudo apt update
   sudo apt install ffmpeg
   ```

   **Verify installation**:
   ```bash
   ffmpeg -version
   ```

6. Create necessary directories:
   ```bash
   mkdir -p data/audio data/transcripts data/chroma data/cache data/videos data/temp
   ```

7. Start the application:
   ```bash
   uvicorn app:app --reload
   ```

8. Open your browser and navigate to http://localhost:8000

## Usage Guide

1. **Process a Video**:
   - Enter a YouTube URL in the input field
   - Click "Transcribe Video" button
   - Wait for processing to complete

2. **Ask Questions**:
   - Type your question in the input field
   - Click "Ask" button or press Enter
   - View the AI's response in the chat area

3. **Language Selection**:
   - Click on the language options at the top of the screen
   - UI and responses will adapt to the selected language

4. **Manage Chat Sessions**:
   - Use the sidebar to view and manage chat history
   - Create new chats with the "+" button
   - Delete or rename chats as needed

5. **Video History**:
   - Previously processed videos appear in the history section
   - Click "Load" to quickly reload a video without reprocessing

## Technical Details

### RAG (Retrieval Augmented Generation) Pipeline

UBot implements a RAG approach for question answering:

1. **Chunking**: Transcripts are split into manageable chunks
2. **Embedding**: Text chunks are converted to vector embeddings using OpenAI
3. **Storage**: Embeddings are stored in ChromaDB for semantic retrieval
4. **Retrieval**: When a question is asked, the most relevant chunks are retrieved
5. **Generation**: OpenAI's GPT models generate answers based on the retrieved context

### Optimization for Long Videos

Videos longer than 30 minutes are processed with special optimization:
- Chunked processing to avoid memory issues
- Background tasks for asynchronous handling
- Progress tracking with estimated completion time
- Lower quality audio processing for faster transcription

### Conversation Handling

UBot intelligently manages conversations:
- Detects when questions are follow-ups to previous questions
- Maintains conversation context for more coherent responses
- Distinguishes between video-related questions and casual conversation

## Project Structure

```
/
├── app.py                # Main FastAPI application
├── youtube_handler.py    # YouTube video processing
├── audio_processing.py   # Audio splitting and optimization
├── transcription.py      # Whisper transcription logic
├── rag_pipeline.py       # Text chunking and embedding creation
├── qa_system.py          # Question answering system
├── utils.py              # Helper functions
├── requirements.txt      # Python dependencies
├── .env                  # API keys and configuration settings
├── data/                 # Data directories
│   ├── audio/            # Downloaded YouTube audio files
│   ├── segments/         # Audio chunks after splitting
│   ├── transcripts/      # Final transcript text files
│   ├── chroma/           # ChromaDB database storage
│   ├── cache/            # Saved answers for faster response
│   └── temp/             # Temporary processing files
└── frontend/             # Web interface
    ├── index.html        # Main frontend interface
    └── static/           # Static assets
        ├── css/          # CSS stylesheets
        └── js/           # JavaScript files
```

## API Endpoints

UBot exposes the following API endpoints:

- `GET /`: Serve the frontend interface
- `POST /videos/process`: Process a new YouTube video
- `POST /videos/{video_id}/question`: Ask a question about a video
- `GET /videos`: List processed videos
- `GET /progress`: Check processing progress
- `DELETE /videos/{video_id}`: Delete a processed video
- `POST /videos/{video_id}/language`: Update language preference

## Performance Considerations

- Processing time depends on video length and complexity
- Long videos (>30min) may take several minutes to process
- First-time questions may take longer than subsequent similar questions (caching)
- Consider server resources when deploying for multi-user environments

## Future Improvements

- Voice input support for asking questions
- Embedded YouTube player with timestamp navigation
- Mobile application version
- Support for additional video platforms
- Extended language support

## Acknowledgments

- OpenAI for Whisper and GPT models
- ChromaDB for vector storage
- FastAPI for the web framework
- yt-dlp for YouTube video processing

  Deom video: https://drive.google.com/drive/folders/1Oacjg-v6TY8gdhn_7a4DCG01IFj6mFIx?usp=drive_link
## Author

Developed by [Bader Albehishi](https://github.com/bader-albehishi)
