// Enhanced and optimized app.js for UBot - YouTube AI Assistant
let videoId = "";
let progressInterval = null;
let videoCache = {};
let currentLanguage = 'en'; // Default language

// Document ready handler - initialize everything when the page loads
document.addEventListener('DOMContentLoaded', function() {
    // Initialize language from localStorage if available
    currentLanguage = localStorage.getItem('ubotLanguage') || 'en';
    setLanguage(currentLanguage);
    
    // Initialize menu functionality
    initializeMenu();
    
    // Initialize chat history
    initializeChatHistory();
    
    // Load video history
    loadVideoHistory();
    
    // Setup event listeners
    setupEventListeners();
    
    // Initialize sidebar immediately
    initializeSidebar();
});

// Function to initialize sidebar
function initializeSidebar() {
    // Get sidebar elements
    const sidebar = document.querySelector('.chat-history-sidebar');
    const toggleBtn = document.querySelector('.toggle-sidebar-btn');
    
    if (!sidebar || !toggleBtn) return;
    
    // Toggle button click event - opens the sidebar
    toggleBtn.addEventListener('click', function() {
        // Remove inline styles first
        sidebar.style.transform = '';
        
        // Update classes
        document.body.classList.remove('sidebar-closed');
        document.body.classList.add('sidebar-open');
    });
    
    // Create and add collapse button
    createCollapseButton();
}

// Function to create collapse button with the correct icon
function createCollapseButton() {
    const sidebarHeader = document.querySelector('.sidebar-header');
    if (!sidebarHeader) return;
    
    // Remove any existing button first
    const existingBtn = sidebarHeader.querySelector('.collapse-sidebar-btn');
    if (existingBtn) {
        existingBtn.remove();
    }
    
    // Create new button
    const collapseBtn = document.createElement('button');
    collapseBtn.className = 'collapse-sidebar-btn';
    collapseBtn.title = currentLanguage === 'ar' ? "إخفاء" : "Collapse";
    
    // Create icon element
    const icon = document.createElement('i');
    icon.className = currentLanguage === 'ar' ? 'fas fa-chevron-right' : 'fas fa-chevron-left';
    collapseBtn.appendChild(icon);
    
    // Add to header
    sidebarHeader.appendChild(collapseBtn);
    
    // Add event listener
    collapseBtn.addEventListener('click', function() {
        // Update classes
        document.body.classList.add('sidebar-closed');
        document.body.classList.remove('sidebar-open');
        
        // Manually set transform for immediate effect
        const sidebar = document.querySelector('.chat-history-sidebar');
        if (sidebar) {
            if (currentLanguage === 'ar') {
                sidebar.style.transform = 'translateX(100%)';
            } else {
                sidebar.style.transform = 'translateX(-100%)';
            }
        }
    });
}

// Call this after language changes
function updateSidebarAfterLanguageChange() {
    createCollapseButton();
}

// Function to set up all event listeners in one place
function setupEventListeners() {
    // Toggle sidebar button
    const toggleSidebarBtn = document.querySelector('.toggle-sidebar-btn');
    const sidebar = document.querySelector('.chat-history-sidebar');
    if (toggleSidebarBtn && sidebar) {
        toggleSidebarBtn.addEventListener('click', function() {
            // Show sidebar
            sidebar.style.transform = ''; // Reset any inline transform
            document.body.classList.remove('sidebar-closed');
            document.body.classList.add('sidebar-open');
            sidebar.classList.add('active');
            
            // Hide the toggle button when sidebar is open on desktop
            if (window.innerWidth > 768) {
                toggleSidebarBtn.style.display = 'none';
            }
        });
    }
    
    // New chat button
    const newChatBtn = document.getElementById('new-chat-btn');
    if (newChatBtn) {
        newChatBtn.addEventListener('click', function() {
            if (window.chatHistory && window.chatHistory.createNewChatSession) {
                window.chatHistory.createNewChatSession();
                showToast(
                    currentLanguage === 'ar' ? "تم إنشاء محادثة جديدة" : "New chat created",
                    "success"
                );
            }
        });
    }
    
    // Process video button
    const processButton = document.getElementById('processButton');
    if (processButton) {
        processButton.addEventListener('click', processVideo);
    }
    
    // Ask button
    const askButton = document.getElementById('askButton');
    if (askButton) {
        askButton.addEventListener('click', sendQuestion);
    }
    
    // Question input - press Enter to send
    const questionInput = document.getElementById('questionInput');
    if (questionInput) {
        questionInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                sendQuestion();
            }
        });
    }
    
    // URL input - press Enter to process
    const urlInput = document.getElementById('youtubeUrl');
    if (urlInput) {
        urlInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                processVideo();
            }
        });
    }
    
    // Language selectors
    const langOptions = document.querySelectorAll('.language-option');
    if (langOptions) {
        langOptions.forEach(option => {
            option.addEventListener('click', function() {
                setLanguage(this.getAttribute('data-lang'));
            });
        });
    }
}

// Function to initialize menu system
function initializeMenu() {
    const menuToggle = document.querySelector('.menu-toggle');
    const menuDropdown = document.querySelector('.menu-dropdown');

    if (menuToggle && menuDropdown) {
        // Replace menu icon with more distinctive icons
        menuToggle.innerHTML = '<i class="fas fa-ellipsis-v"></i>';
        
        // Update menu item icons
        const downloadItem = document.getElementById('download-chat');
        const aboutItem = document.getElementById('about');
        
        if (downloadItem) {
            downloadItem.innerHTML = '<i class="fas fa-download"></i> <span id="download-text-en">Download Chat</span><span id="download-text-ar" style="display:none;">تنزيل المحادثة</span>';
            downloadItem.addEventListener('click', downloadChat);
        }
        
        if (aboutItem) {
            aboutItem.innerHTML = '<i class="fas fa-info-circle"></i> <span id="about-text-en">About</span><span id="about-text-ar" style="display:none;">حول</span>';
            aboutItem.addEventListener('click', showAboutModal);
        }
        
        // Toggle menu
        menuToggle.addEventListener('click', function() {
            menuDropdown.classList.toggle('active');
        });

        // Close menu when clicking outside
        document.addEventListener('click', function(event) {
            if (!menuToggle.contains(event.target) && !menuDropdown.contains(event.target)) {
                menuDropdown.classList.remove('active');
            }
        });
    }
}

// Function to check progress during processing
function checkProgress() {
    fetch("/progress")
        .then(response => response.json())
        .then(data => {
            updateProgress(data.message, data.percentage);
            
            // If processing is complete, stop checking
            if (data.percentage >= 100) {
                clearInterval(progressInterval);
                setTimeout(() => {
                    document.getElementById("progress-bar").style.display = "none";
                    
                    // Re-enable process button with animation
                    const processButton = document.getElementById("processButton");
                    if (processButton) {
                        processButton.disabled = false;
                        processButton.classList.add("success-animation");
                        
                        // Update button text
                        processButton.innerHTML = currentLanguage === 'ar' 
                            ? '<i class="fas fa-check"></i> <span>تم المعالجة</span>' 
                            : '<i class="fas fa-check"></i> <span>Processed</span>';
                        
                        // Reset button after 2 seconds
                        setTimeout(() => {
                            processButton.classList.remove("success-animation");
                            processButton.innerHTML = currentLanguage === 'ar' 
                                ? '<i class="fas fa-robot"></i> <span>معالجة الفيديو</span>' 
                                : '<i class="fas fa-robot"></i> <span>Transcribe Video</span>';
                        }, 2000);
                    }
                }, 500);
            }
        })
        .catch(error => {
            console.error("Error checking progress:", error);
        });
}

// Update progress bar
function updateProgress(message, percentage) {
    const progressBar = document.getElementById("progress");
    const progressText = document.getElementById("progress-text");
    
    if (!progressBar || !progressText) return;
    
    if (percentage !== null) {
        progressBar.style.width = `${percentage}%`;
    }
    
    if (message) {
        progressText.textContent = message;
    }
}

// Function to append messages to chat
function appendMessage(text, sender) {
    const chatbox = document.getElementById("chatbox");
    if (!chatbox) return;
    
    const msg = document.createElement("div");
    msg.classList.add("message", sender === "user" ? "user-message" : "bot-message");
    
    // Support for RTL languages like Arabic
    if (currentLanguage === 'ar') {
        msg.setAttribute("dir", "rtl");
    } else {
        msg.removeAttribute("dir");
    }
    
    // Create a container for the message content and buttons
    const messageContainer = document.createElement("div");
    messageContainer.style.display = "flex";
    messageContainer.style.width = "100%";
    
    // Add appropriate icon
    const icon = document.createElement("i");
    icon.classList.add("fas", sender === "user" ? "fa-user" : "fa-robot");
    icon.style.marginRight = "8px";
    icon.style.opacity = "0.8";
    
    // Create message content
    const content = document.createElement("span");
    content.innerHTML = text;
    content.style.flex = "1";
    
    // Add icon and content to container
    messageContainer.appendChild(icon);
    messageContainer.appendChild(content);
    
    // Add the container to the message
    msg.appendChild(messageContainer);
    
    // Only add copy button to bot messages
    if (sender === "bot") {
        // Create copy button
        const copyBtn = document.createElement("button");
        copyBtn.innerHTML = '<i class="fas fa-copy"></i>';
        copyBtn.title = currentLanguage === 'ar' ? "نسخ الرسالة" : "Copy message";
        copyBtn.classList.add("copy-button");
        copyBtn.style.background = "transparent";
        copyBtn.style.border = "none";
        copyBtn.style.color = "#fff";
        copyBtn.style.cursor = "pointer";
        copyBtn.style.fontSize = "14px";
        copyBtn.style.padding = "4px";
        copyBtn.style.marginLeft = "8px";
        
        // Add copy functionality
        copyBtn.addEventListener('click', () => {
            // Create a temporary element to strip HTML tags
            const tempDiv = document.createElement("div");
            tempDiv.innerHTML = text;
            const textToCopy = tempDiv.textContent || tempDiv.innerText;
            
            navigator.clipboard.writeText(textToCopy)
                .then(() => {
                    // Show copied toast
                    showToast(
                        currentLanguage === 'ar' ? "تم نسخ النص!" : "Text copied!",
                        "success"
                    );
                    
                    // Visual feedback
                    copyBtn.innerHTML = '<i class="fas fa-check"></i>';
                    setTimeout(() => {
                        copyBtn.innerHTML = '<i class="fas fa-copy"></i>';
                    }, 1500);
                })
                .catch(err => {
                    console.error('Error copying text: ', err);
                    showToast(
                        currentLanguage === 'ar' ? "فشل في نسخ النص" : "Failed to copy text",
                        "error"
                    );
                });
        });
        
        // Add button to message
        messageContainer.appendChild(copyBtn);
    }
    
    chatbox.appendChild(msg);
    
    // Scroll to the new message with smooth animation
    msg.scrollIntoView({ behavior: 'smooth', block: 'end' });
    
    return msg;
}

// Function to display keywords
// Function to display keywords
function displayKeywords(keywords) {
    const keywordsContainer = document.getElementById("video-keywords");
    if (!keywordsContainer) return;
    
    keywordsContainer.innerHTML = "";
    
    if (!keywords || keywords.length === 0) {
        const noKeywords = document.createElement("span");
        noKeywords.classList.add("keyword");
        noKeywords.textContent = currentLanguage === 'ar' ? "لا توجد كلمات مفتاحية" : "No keywords available";
        keywordsContainer.appendChild(noKeywords);
        return;
    }
    
    keywords.forEach(keyword => {
        const keywordElement = document.createElement("span");
        keywordElement.classList.add("keyword");
        keywordElement.textContent = keyword;
        
        // Make it clickable
        keywordElement.style.cursor = "pointer";
        keywordElement.onclick = function() {
            // When clicked, put the keyword in the question input
            const questionInput = document.getElementById("questionInput");
            if (!questionInput) return;
            
            // If in Arabic mode, add appropriate prefix
            if (currentLanguage === 'ar') {
                questionInput.value = `ما هي معلومات الفيديو عن "${keyword}"؟`;
            } else {
                questionInput.value = `What does the video say about "${keyword}"?`;
            }
            
            // Focus the input
            questionInput.focus();
            
            // Auto-send the question
            sendQuestion();
        };
        
        keywordsContainer.appendChild(keywordElement);
    });
}

// Function to extract video ID from YouTube URL
function extractVideoIdFromUrl(url) {
    const regExp = /^.*(youtu.be\/|v\/|u\/\w\/|embed\/|watch\?v=|&v=)([^#&?]*).*/;
    const match = url.match(regExp);
    return (match && match[2].length === 11) ? match[2] : null;
}

// Process video function
async function processVideo() {
    const urlInput = document.getElementById("youtubeUrl");
    if (!urlInput) return;
    
    const url = urlInput.value.trim();
    
    if (!url) {
        showToast(currentLanguage === 'ar' ? "الرجاء إدخال رابط يوتيوب!" : "Please enter a YouTube URL!");
        return;
    }

    // Check if video is in cache
    const videoIdFromUrl = extractVideoIdFromUrl(url);
    if (videoIdFromUrl && videoCache[videoIdFromUrl]) {
        // Load from cache
        loadVideo(videoIdFromUrl);
        return;
    }

    // Show progress bar
    const progressBar = document.getElementById("progress-bar");
    if (progressBar) {
        progressBar.style.display = "block";
    }
    
    updateProgress(currentLanguage === 'ar' ? "جارٍ بدء المعالجة..." : "Starting processing...", 5);
    
    // Disable process button
    const processButton = document.getElementById("processButton");
    if (processButton) {
        processButton.disabled = true;
        processButton.innerHTML = currentLanguage === 'ar' 
            ? '<i class="fas fa-spinner fa-spin"></i> <span>جارٍ المعالجة...</span>' 
            : '<i class="fas fa-spinner fa-spin"></i> <span>Processing...</span>';
    }
    
    appendMessage(currentLanguage === 'ar' ? "جارٍ معالجة الفيديو..." : "Processing video...", "bot");

    // Start polling for progress updates
    if (progressInterval) {
        clearInterval(progressInterval);
    }
    progressInterval = setInterval(checkProgress, 1000);

    try {
        const response = await fetch("/videos/process", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ 
                url: url,
                language: currentLanguage 
            })
        });

        if (response.ok) {
            const data = await response.json();
            videoId = data.video_id;
            
            // Update video info UI
            updateVideoInfo(data);
            
            // Cache the video data
            videoCache[data.video_id] = {
                title: data.title,
                thumbnail: `https://img.youtube.com/vi/${data.video_id}/0.jpg`,
                keywords: data.keywords || [],
                language: data.language,
                channel: data.channel || "Unknown"
            };
            
            appendMessage(
                currentLanguage === 'ar' 
                    ? `<b>تمت معالجة الفيديو!</b> يمكنك الآن طرح أسئلة حول: "${data.title}"` 
                    : `<b>Video processed!</b> You can now ask questions about: "${data.title}"`, 
                "bot"
            );
            
            // Update video history
            await loadVideoHistory();
            
            // Clear input field
            urlInput.value = "";
            
            // Focus the question input for better UX
            const questionInput = document.getElementById("questionInput");
            if (questionInput) questionInput.focus();
        } else {
            let errorMessage = currentLanguage === 'ar' ? "فشل في معالجة الفيديو" : "Failed to process video";
            try {
                const error = await response.json();
                errorMessage = currentLanguage === 'ar' 
                    ? `<b>خطأ:</b> فشل في معالجة الفيديو: ${error.detail || "خطأ غير معروف"}` 
                    : `<b>Error:</b> Failed to process video: ${error.detail || "Unknown error"}`;
            } catch {
                // If can't parse JSON response
            }
            appendMessage(errorMessage, "bot");
        }
    } catch (error) {
        appendMessage(
            currentLanguage === 'ar' 
                ? `<b>خطأ:</b> خطأ في الاتصال بالخادم. يرجى المحاولة مرة أخرى.` 
                : `<b>Error:</b> Connection error. Please try again.`, 
            "bot"
        );
        console.error("Error:", error);
    } finally {
        // Clear interval and hide progress bar
        clearInterval(progressInterval);
        const progressBar = document.getElementById("progress-bar");
        if (progressBar) {
            progressBar.style.display = "none";
        }
        
        // Re-enable process button
        if (processButton) {
            processButton.disabled = false;
            processButton.innerHTML = currentLanguage === 'ar' 
                ? '<i class="fas fa-robot"></i> <span>معالجة الفيديو</span>' 
                : '<i class="fas fa-robot"></i> <span>Transcribe Video</span>';
        }
    }
}

// Function to update video info in UI
function updateVideoInfo(data) {
    // Show video info container with animation
    const videoInfoContainer = document.getElementById("video-info-container");
    if (!videoInfoContainer) return;
    
    videoInfoContainer.style.display = "block";
    videoInfoContainer.classList.add("fade-in");
    setTimeout(() => videoInfoContainer.classList.remove("fade-in"), 1000);
    
    // Update thumbnail
    const thumbnail = document.getElementById("video-thumbnail");
    if (thumbnail) {
        thumbnail.src = `https://img.youtube.com/vi/${data.video_id}/0.jpg`;
        thumbnail.alt = data.title || "Video thumbnail";
    }
    
    // Update title and channel
    const titleElement = document.getElementById("video-title");
    if (titleElement) {
        titleElement.textContent = data.title || "Unknown Title";
    }
    
    const channelElement = document.getElementById("video-channel");
    if (channelElement && channelElement.querySelector) {
        const span = channelElement.querySelector("span");
        if (span) span.textContent = data.channel || "Unknown";
    }
    
    // Display keywords
    displayKeywords(data.keywords || []);
    
    // Add new chat button for current video if not exists
    addNewChatForVideoButton();
}

// Function to display toast notifications
function showToast(message, type = "info") {
    // Create toast container if it doesn't exist
    let toastContainer = document.getElementById("toast-container");
    if (!toastContainer) {
        toastContainer = document.createElement("div");
        toastContainer.id = "toast-container";
        toastContainer.style.position = "fixed";
        toastContainer.style.bottom = "20px";
        toastContainer.style.right = "20px";
        toastContainer.style.zIndex = "1000";
        document.body.appendChild(toastContainer);
    }
    
    // Create toast
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.style.backgroundColor = type === "error" ? "var(--danger)" : 
                                type === "success" ? "var(--success)" : "var(--primary)";
    toast.style.color = "white";
    toast.style.padding = "12px 20px";
    toast.style.borderRadius = "8px";
    toast.style.marginTop = "10px";
    toast.style.boxShadow = "0 4px 12px rgba(0,0,0,0.15)";
    toast.style.animation = "fade-in 0.3s, fade-out 0.3s 2.7s";
    toast.style.minWidth = "200px";
    
    // Icon based on type
    const icon = document.createElement("i");
    icon.className = `fas ${type === "error" ? "fa-exclamation-circle" : 
                         type === "success" ? "fa-check-circle" : "fa-info-circle"}`;
    icon.style.marginRight = "8px";
    
    // Message text
    const text = document.createElement("span");
    text.textContent = message;
    
    // Append to toast
    toast.appendChild(icon);
    toast.appendChild(text);
    toastContainer.appendChild(toast);
    
    // For RTL support
    if (currentLanguage === 'ar') {
        toast.setAttribute('dir', 'rtl');
        toastContainer.style.right = 'auto';
        toastContainer.style.left = '20px';
    } else {
        toast.removeAttribute('dir');
        toastContainer.style.right = '20px';
        toastContainer.style.left = 'auto';
    }
    
    // Remove after 3 seconds
    setTimeout(() => {
        if (toast.parentNode === toastContainer) {
            toastContainer.removeChild(toast);
        }
    }, 3000);
}

// Function to send a question to the AI
async function sendQuestion() {
    const questionInput = document.getElementById("questionInput");
    if (!questionInput) return;
    
    const question = questionInput.value.trim();
    
    if (!question) {
        showToast(currentLanguage === 'ar' ? "الرجاء إدخال سؤال!" : "Please enter a question!", "error");
        return;
    }
    
    if (!videoId) {
        appendMessage(
            currentLanguage === 'ar' 
                ? "<b>تنبيه:</b> الرجاء معالجة فيديو أولاً!" 
                : "<b>Alert:</b> Please process a video first!", 
            "bot"
        );
        return;
    }

    // Disable ask button
    const askButton = document.getElementById("askButton");
    if (askButton) {
        askButton.disabled = true;
        askButton.innerHTML = currentLanguage === 'ar'
            ? '<i class="fas fa-spinner fa-spin"></i> <span>جاري البحث...</span>'
            : '<i class="fas fa-spinner fa-spin"></i> <span>Searching...</span>';
    }
    
    // Add user message
    appendMessage(question, "user");
    
    // Add thinking indicator
    const thinkingMsg = document.createElement("div");
    thinkingMsg.classList.add("message", "bot-message");
    
    if (currentLanguage === 'ar') {
        thinkingMsg.setAttribute("dir", "rtl");
    }
    
    const botIcon = document.createElement("i");
    botIcon.classList.add("fas", "fa-robot");
    botIcon.style.marginRight = "8px";
    botIcon.style.opacity = "0.8";
    
    const thinkingContent = document.createElement("div");
    thinkingContent.style.display = "inline-block";
    
    const thinkingText = document.createElement("span");
    thinkingText.textContent = currentLanguage === 'ar' ? "جاري التفكير " : "Thinking ";
    
    const dots = document.createElement("span");
    dots.classList.add("thinking-dots");
    dots.innerHTML = `<span></span><span></span><span></span>`;
    
    thinkingContent.appendChild(thinkingText);
    thinkingContent.appendChild(dots);
    
    thinkingMsg.appendChild(botIcon);
    thinkingMsg.appendChild(thinkingContent);
    
    const chatbox = document.getElementById("chatbox");
    if (chatbox) {
        chatbox.appendChild(thinkingMsg);
        thinkingMsg.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
    
    // Handle timeout
    let timeoutId = setTimeout(() => {
        if (thinkingMsg.parentNode) {
            // If still thinking after 20 seconds, update the message
            thinkingContent.innerHTML = currentLanguage === 'ar' 
                ? "جاري معالجة سؤالك، يرجى الانتظار قليلاً..." 
                : "Processing your question, please wait a moment...";
        }
    }, 20000);
    
    try {
        // Pass user's preferred language regardless of the interface language
        // This allows users to ask questions in Arabic even when the UI is in English
        let queryLanguage = detectLanguage(question);
        
        const response = await fetch(`/videos/${videoId}/question`, {
            method: "POST",
            headers: { 
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ 
                query: question,
                language: queryLanguage // Use the detected language for the query
            })
        });

        // Clear timeout
        clearTimeout(timeoutId);

        if (response.ok) {
            const data = await response.json();
            
            // Remove thinking message
            if (thinkingMsg.parentNode && chatbox) {
                chatbox.removeChild(thinkingMsg);
            }
            
            // Add answer to chat
            let answer = data.answer;
            
            // Add cache indicator if needed
            if (data.cached) {
                const cacheTag = currentLanguage === 'ar' 
                    ? "<small style='opacity:0.7;'>(من الذاكرة المؤقتة)</small> " 
                    : "<small style='opacity:0.7;'>(from cache)</small> ";
                answer = cacheTag + answer;
            }
            
            // Create answer message with proper RTL/LTR direction
            const msgElement = appendMessage(answer, "bot");
            if (queryLanguage === 'ar') {
                msgElement.setAttribute("dir", "rtl");
            } else {
                msgElement.removeAttribute("dir");
            }
        } else {
            // Remove thinking message
            if (thinkingMsg.parentNode && chatbox) {
                chatbox.removeChild(thinkingMsg);
            }
            
            // Try to get error details
            let errorMessage;
            try {
                const error = await response.json();
                errorMessage = currentLanguage === 'ar' 
                    ? `<b>خطأ:</b> ${error.detail || "فشل في الحصول على إجابة"}` 
                    : `<b>Error:</b> ${error.detail || "Failed to get answer"}`;
            } catch {
                errorMessage = currentLanguage === 'ar'
                    ? "<b>خطأ:</b> حدث خطأ أثناء معالجة سؤالك. سيتم إصلاح هذه المشكلة تلقائيًا عند تحميل فيديو آخر."
                    : "<b>Error:</b> An error occurred while processing your question. This will be fixed automatically when you load another video.";
            }
            
            appendMessage(errorMessage, "bot");
            
            if (question.toLowerCase().includes("summar") || 
                question.toLowerCase().includes("ملخص") || 
                question.toLowerCase().includes("لخص")) {
                
                // For summary requests, try direct approach
                handleFallbackSummary(question);
            }
        }
    } catch (error) {
        // Clear timeout
        clearTimeout(timeoutId);
        
        // Remove thinking message
        if (thinkingMsg.parentNode && chatbox) {
            chatbox.removeChild(thinkingMsg);
        }
        
        console.error("Error sending question:", error);
        
        const errorMsg = currentLanguage === 'ar'
            ? "<b>خطأ في الاتصال:</b> حدث خطأ في الاتصال. سنحاول استخدام طريقة بديلة..."
            : "<b>Connection Error:</b> An error occurred. Trying alternative approach...";
        
        appendMessage(errorMsg, "bot");
        
        // Try fallback for summary requests
        if (question.toLowerCase().includes("summar") || 
            question.toLowerCase().includes("ملخص") || 
            question.toLowerCase().includes("لخص")) {
            
            handleFallbackSummary(question);
        } else {
            appendMessage(
                currentLanguage === 'ar' 
                    ? "لم نتمكن من معالجة سؤالك. يرجى المحاولة مرة أخرى."
                    : "We couldn't process your question. Please try again.",
                "bot"
            );
        }
    } finally {
        // Clear input and re-enable button
        questionInput.value = "";
        if (askButton) {
            askButton.disabled = false;
            askButton.innerHTML = currentLanguage === 'ar'
                ? '<i class="fas fa-paper-plane"></i> <span>اسأل</span>'
                : '<i class="fas fa-paper-plane"></i> <span>Ask</span>';
        }

        // Focus on the input field again
        questionInput.focus();
    }
}
// Simple language detection function
function detectLanguage(text) {
    // Check for Arabic characters
    const arabicPattern = /[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]/;
    if (arabicPattern.test(text)) {
        return 'ar';
    }
    
    // Default to interface language or English
    return currentLanguage || 'en';
}

// Fallback function to generate summary directly
async function handleFallbackSummary(question) {
    // Get video info
    let title = "the video";
    let videoInfo = videoCache[videoId];
    if (videoInfo) {
        title = videoInfo.title;
    }

    const thinkingMsg = appendMessage(
        currentLanguage === 'ar'
            ? "<i class='fas fa-sync fa-spin'></i> جاري إنشاء ملخص بديل..."
            : "<i class='fas fa-sync fa-spin'></i> Generating alternative summary...",
        "bot"
    );

    try {
        // Use OpenAI API directly if available
        const response = await fetch(`/videos/${videoId}/summary`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ 
                length: "short",
                language: detectLanguage(question) // Use detected language
            })
        });

        if (response.ok) {
            const data = await response.json();
            
            // Remove thinking message if it exists
            if (thinkingMsg.parentNode) {
                thinkingMsg.remove();
            }
            
            // Display summary
            appendMessage(data.summary, "bot");
        } else {
            throw new Error("Failed to generate summary");
        }
    } catch (error) {
        console.error("Error generating fallback summary:", error);

        // If we couldn't generate a summary, provide a generic one
        let fallbackSummary;
        if (currentLanguage === 'ar') {
            fallbackSummary = `<b>عذرًا:</b> لم نتمكن من إنشاء ملخص تفصيلي لـ "${title}". يرجى محاولة معالجة الفيديو مرة أخرى أو طرح أسئلة محددة حول محتواه.`;
        } else {
            fallbackSummary = `<b>Sorry:</b> We couldn't generate a detailed summary for "${title}". Please try processing the video again or asking specific questions about its content.`;
        }

        // Remove thinking message if it exists
        if (thinkingMsg.parentNode) {
            thinkingMsg.remove();
        }

        appendMessage(fallbackSummary, "bot");
    }
}

// Function to load video history
async function loadVideoHistory() {
    const videoHistory = document.getElementById("video-history");
    if (!videoHistory) return;

    try {
        const response = await fetch("/videos");

        if (response.ok) {
            const data = await response.json();
            
            if (data.videos && data.videos.length > 0) {
                // Show video history section
                videoHistory.style.display = "block";
                
                // Clear existing list
                const videoList = document.getElementById("video-list");
                if (videoList) {
                    videoList.innerHTML = "";
                    
                    // Add videos to list
                    data.videos.forEach(video => {
                        // Cache the video data
                        videoCache[video.video_id] = {
                            title: video.title,
                            thumbnail: `https://img.youtube.com/vi/${video.video_id}/0.jpg`,
                            keywords: video.keywords || [],
                            language: video.language,
                            channel: video.channel || "Unknown"
                        };
                        
                        const videoItem = document.createElement("div");
                        videoItem.classList.add("video-item");
                        
                        const titleElement = document.createElement("div");
                        titleElement.classList.add("video-title");
                        titleElement.textContent = video.title;
                        
                        const buttonsContainer = document.createElement("div");
                        buttonsContainer.classList.add("video-buttons");
                        
                        const loadButton = document.createElement("button");
                        loadButton.classList.add("load-button");
                        loadButton.innerHTML = currentLanguage === 'ar' 
                            ? '<i class="fas fa-play"></i> <span>تحميل</span>' 
                            : '<i class="fas fa-play"></i> <span>Load</span>';
                        loadButton.onclick = function() {
                            loadVideo(video.video_id);
                        };
                        
                        const deleteButton = document.createElement("button");
                        deleteButton.classList.add("delete-button");
                        deleteButton.innerHTML = currentLanguage === 'ar' 
                            ? '<i class="fas fa-trash"></i> <span>حذف</span>' 
                            : '<i class="fas fa-trash"></i> <span>Delete</span>';
                        deleteButton.onclick = function() {
                            deleteVideo(video.video_id);
                        };
                        
                        buttonsContainer.appendChild(loadButton);
                        buttonsContainer.appendChild(deleteButton);
                        
                        videoItem.appendChild(titleElement);
                        videoItem.appendChild(buttonsContainer);
                        
                        videoList.appendChild(videoItem);
                    });
                }
            } else {
                // Hide video history section
                videoHistory.style.display = "none";
            }
        }
    } catch (error) {
        console.error("Error loading video history:", error);
        showToast(
            currentLanguage === 'ar' 
                ? "تعذر تحميل سجل الفيديو" 
                : "Failed to load video history",
            "error"
        );
    }
}

// Function to load a specific video
async function loadVideo(id) {
    videoId = id;

    // Use cached data if available
    if (videoCache[id]) {
        const cachedVideo = videoCache[id];

        // Update UI with cached data
        const videoInfoContainer = document.getElementById("video-info-container");
        if (videoInfoContainer) {
            videoInfoContainer.style.display = "block";
            videoInfoContainer.classList.add("fade-in");
            setTimeout(() => videoInfoContainer.classList.remove("fade-in"), 1000);
        }

        const thumbnail = document.getElementById("video-thumbnail");
        if (thumbnail) thumbnail.src = cachedVideo.thumbnail;
        
        const videoTitle = document.getElementById("video-title");
        if (videoTitle) videoTitle.textContent = cachedVideo.title;
        
        const channelElement = document.getElementById("video-channel");
        if (channelElement && channelElement.querySelector) {
            const span = channelElement.querySelector("span");
            if (span) span.textContent = cachedVideo.channel;
        }

        // Display keywords
        displayKeywords(cachedVideo.keywords || []);

        appendMessage(
            currentLanguage === 'ar' 
                ? `<b>تم تحميل الفيديو!</b> يمكنك الآن طرح أسئلة حول: "${cachedVideo.title}"` 
                : `<b>Video loaded!</b> You can now ask questions about: "${cachedVideo.title}"`, 
            "bot"
        );

        // Show loading success toast
        showToast(
            currentLanguage === 'ar' 
                ? "تم تحميل الفيديو بنجاح" 
                : "Video loaded successfully"
        );

        // Focus on question input
        const questionInput = document.getElementById("questionInput");
        if (questionInput) questionInput.focus();

        // Add new chat button for video
        addNewChatForVideoButton();

        return;
    }

    // If not in cache, load from server
    try {
        // Show loading toast
        showToast(
            currentLanguage === 'ar' 
                ? "جاري تحميل الفيديو..." 
                : "Loading video...",
            "info"
        );

        const response = await fetch("/videos");

        if (response.ok) {
            const data = await response.json();
            
            if (data.videos) {
                const video = data.videos.find(v => v.video_id === id);
                if (video) {
                    // Update video info UI
                    const videoInfoContainer = document.getElementById("video-info-container");
                    if (videoInfoContainer) {
                        videoInfoContainer.style.display = "block";
                        videoInfoContainer.classList.add("fade-in");
                        setTimeout(() => videoInfoContainer.classList.remove("fade-in"), 1000);
                    }
                    
                    const thumbnail = document.getElementById("video-thumbnail");
                    if (thumbnail) thumbnail.src = `https://img.youtube.com/vi/${id}/0.jpg`;
                    
                    const videoTitle = document.getElementById("video-title");
                    if (videoTitle) videoTitle.textContent = video.title;
                    
                    const channelElement = document.getElementById("video-channel");
                    if (channelElement && channelElement.querySelector) {
                        const span = channelElement.querySelector("span");
                        if (span) span.textContent = video.channel || "Unknown";
                    }
                    
                    // Display keywords
                    displayKeywords(video.keywords || []);
                    
                    // Cache the video data
                    videoCache[id] = {
                        title: video.title,
                        thumbnail: `https://img.youtube.com/vi/${id}/0.jpg`,
                        keywords: video.keywords || [],
                        language: video.language,
                        channel: video.channel || "Unknown"
                    };
                    
                    appendMessage(
                        currentLanguage === 'ar' 
                            ? `<b>تم تحميل الفيديو!</b> يمكنك الآن طرح أسئلة حول: "${video.title}"` 
                            : `<b>Video loaded!</b> You can now ask questions about: "${video.title}"`, 
                        "bot"
                    );
                    
                    // Focus on question input
                    const questionInput = document.getElementById("questionInput");
                    if (questionInput) questionInput.focus();
                    
                    // Add new chat button for video
                    addNewChatForVideoButton();
                }
            }
        }
    } catch (error) {
        console.error("Error loading video:", error);
        appendMessage(
            currentLanguage === 'ar' 
                ? "<b>خطأ:</b> حدث خطأ أثناء تحميل الفيديو." 
                : "<b>Error:</b> An error occurred while loading the video.", 
            "bot"
        );

        showToast(
            currentLanguage === 'ar' 
                ? "تعذر تحميل الفيديو" 
                : "Failed to load video",
            "error"
        );
    }
}

// Function to delete a video
async function deleteVideo(id) {
    if (confirm(currentLanguage === 'ar' 
    ? "هل أنت متأكد من أنك تريد حذف هذا الفيديو؟" 
    : "Are you sure you want to delete this video?")) {
        try {
            // Show loading toast
            showToast(
                currentLanguage === 'ar' 
                    ? "جاري حذف الفيديو..." 
                    : "Deleting video...",
                "info"
            );
            
            const response = await fetch(`/videos/${id}`, {
                method: "DELETE"
            });
            
            if (response.ok) {
                // Remove from cache
                if (videoCache[id]) {
                    delete videoCache[id];
                }
                
                // Show success toast
                showToast(
                    currentLanguage === 'ar' 
                        ? "تم حذف الفيديو بنجاح" 
                        : "Video deleted successfully"
                );
                
                // Reload video history
                await loadVideoHistory();
                
                // If this was the current video, clear it
                if (videoId === id) {
                    videoId = "";
                    
                    // Hide video info
                    const videoInfoContainer = document.getElementById("video-info-container");
                    if (videoInfoContainer) {
                        videoInfoContainer.style.display = "none";
                    }
                    
                    appendMessage(
                        currentLanguage === 'ar' 
                            ? "<b>تنبيه:</b> تم حذف الفيديو الحالي." 
                            : "<b>Alert:</b> The current video has been deleted.", 
                        "bot"
                    );
                }
            } else {
                showToast(
                    currentLanguage === 'ar' 
                        ? "فشل في حذف الفيديو" 
                        : "Failed to delete video",
                    "error"
                );
                console.error("Error response:", await response.text());
            }
        } catch (error) {
            console.error("Error deleting video:", error);
            showToast(
                currentLanguage === 'ar' 
                    ? "خطأ في الاتصال بالخادم" 
                    : "Error connecting to server",
                "error"
            );
        }
    }
}

// Function to download chat conversation
function downloadChat() {
    const chatbox = document.getElementById('chatbox');
    if (!chatbox) return;

    let content = '';
    const title = currentLanguage === 'ar' ? "محادثة UBot" : "UBot Conversation";

    // Get video title if available
    let videoTitle = "Unknown Video";
    const videoTitleElement = document.getElementById('video-title');
    if (videoTitleElement) {
        videoTitle = videoTitleElement.textContent;
    }

    // Add header
    content += `# ${title}\n`;
    content += `## ${currentLanguage === 'ar' ? "فيديو" : "Video"}: ${videoTitle}\n`;
    content += `## ${currentLanguage === 'ar' ? "تاريخ" : "Date"}: ${new Date().toLocaleString()}\n\n`;

    // Add messages
    const messages = chatbox.querySelectorAll('.message');
    messages.forEach(message => {
        const isUser = message.classList.contains('user-message');
        const text = message.textContent.trim();

        content += `**${isUser ? (currentLanguage === 'ar' ? "أنت" : "You") : "UBot"}**: ${text}\n\n`;
    });

    // Add footer
    content += `\n---\n${currentLanguage === 'ar' ? "تم إنشاؤه بواسطة UBot - مساعد يوتيوب الذكي" : "Generated by UBot - YouTube AI Assistant"}\n`;
    content += `${currentLanguage === 'ar' ? "تم تطويره بواسطة" : "Developed by"} Bader Albehishi\n`;

    // Create download link
    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `UBot-Chat-${new Date().toISOString().slice(0, 10)}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    // Show toast confirmation
    showToast(
        currentLanguage === 'ar' ? "تم تنزيل المحادثة" : "Chat downloaded", 
        "success"
    );
    
    // Close menu dropdown
    const menuDropdown = document.querySelector('.menu-dropdown');
    if (menuDropdown) menuDropdown.classList.remove('active');
}

// Function to show about modal
function showAboutModal() {
    // Create modal if it doesn't exist
    let modal = document.getElementById('about-modal');

    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'about-modal';
        modal.className = 'modal';

        const modalContent = document.createElement('div');
        modalContent.className = 'modal-content';

        // Close button
        const closeBtn = document.createElement('div');
        closeBtn.className = 'modal-close';
        closeBtn.innerHTML = '&times;';
        closeBtn.onclick = function() {
            modal.classList.remove('active');
        };

        // Title
        const title = document.createElement('h2');
        title.className = 'modal-title';
        title.textContent = 'About UBot';

        // Content
        const body = document.createElement('div');
        body.className = 'modal-body';

        // About content with both languages
        const englishContent = document.createElement('div');
        englishContent.id = 'about-content-en';
        englishContent.innerHTML = `
            <p>UBot is an advanced YouTube AI Assistant that helps users understand video content through transcription, Q&A, and summarization.</p>
            <p>The application downloads audio from YouTube videos, transcribes it, and enables natural language conversations about the content.</p>
            <p><strong>Key Features:</strong></p>
            <ul>
                <li>Extract and transcribe audio from YouTube videos</li>
                <li>Smart Q&A system based on video content</li>
                <li>Automatic keyword extraction</li>
                <li>Bilingual support (English/Arabic)</li>
                <li>Conversation management tools</li>
            </ul>
            <p><strong>Developed by:</strong> Bader Albehishi</p>
        `;

        const arabicContent = document.createElement('div');
        arabicContent.id = 'about-content-ar';
        arabicContent.style.display = 'none';
        arabicContent.dir = 'rtl';
        arabicContent.innerHTML = `
            <p>UBot هو مساعد ذكاء اصطناعي متقدم ليوتيوب يساعد المستخدمين على فهم محتوى الفيديو من خلال النسخ والأسئلة والإجابات والتلخيص.</p>
            <p>يقوم التطبيق بتنزيل الصوت من فيديوهات يوتيوب ونسخه وتمكين المحادثات باللغة الطبيعية حول المحتوى.</p>
            <p><strong>الميزات الرئيسية:</strong></p>
            <ul>
                <li>استخراج ونسخ الصوت من فيديوهات يوتيوب</li>
                <li>نظام أسئلة وأجوبة ذكي بناءً على محتوى الفيديو</li>
                <li>استخراج تلقائي للكلمات المفتاحية</li>
                <li>دعم لغتين (الإنجليزية/العربية)</li>
                <li>أدوات إدارة المحادثات</li>
            </ul>
            <p><strong>تم تطويره بواسطة:</strong> بدر البهيشي </p>
        `;

        body.appendChild(englishContent);
        body.appendChild(arabicContent);

        // Social links
        const socialLinks = document.createElement('div');
        socialLinks.className = 'social-links';

        // GitHub link - Updated with your actual GitHub
        const githubLink = document.createElement('a');
        githubLink.href = 'https://github.com/bader-albehishi';
        githubLink.target = '_blank';
        githubLink.className = 'social-link';
        githubLink.innerHTML = '<i class="fab fa-github"></i>';
        githubLink.title = 'GitHub';

        // LinkedIn link - Updated with your actual LinkedIn
        const linkedinLink = document.createElement('a');
        linkedinLink.href = 'https://www.linkedin.com/in/bader-albehishi-994218255';
        linkedinLink.target = '_blank';
        linkedinLink.className = 'social-link';
        linkedinLink.innerHTML = '<i class="fab fa-linkedin"></i>';
        linkedinLink.title = 'LinkedIn';

        // Add links to container
        socialLinks.appendChild(githubLink);
        socialLinks.appendChild(linkedinLink);

        // Assemble modal
        modalContent.appendChild(closeBtn);
        modalContent.appendChild(title);
        modalContent.appendChild(body);
        modalContent.appendChild(socialLinks);
        modal.appendChild(modalContent);

        // Add to document
        document.body.appendChild(modal);

        // Close when clicking outside
        modal.addEventListener('click', function(event) {
            if (event.target === modal) {
                modal.classList.remove('active');
            }
        });
    }

    // Update content based on current language
    document.getElementById('about-content-en').style.display = currentLanguage === 'ar' ? 'none' : 'block';
    document.getElementById('about-content-ar').style.display = currentLanguage === 'ar' ? 'block' : 'none';

    // Show modal
    modal.classList.add('active');
    
    // Close menu dropdown
    const menuDropdown = document.querySelector('.menu-dropdown');
    if (menuDropdown) menuDropdown.classList.remove('active');
}

// Function to set language and update UI text
function setLanguage(lang) {
    // Store previous language
    const previousLanguage = currentLanguage;
    
    // Update current language
    currentLanguage = lang;
    
    // Save language preference to localStorage
    localStorage.setItem('ubotLanguage', lang);

    // Update active state of language selector
    document.querySelectorAll('.language-option').forEach(option => {
        if (option.getAttribute('data-lang') === lang) {
            option.classList.add('active');
        } else {
            option.classList.remove('active');
        }
    });

    // Update document direction
    document.documentElement.dir = lang === 'ar' ? "rtl" : "ltr";

    // Update UI text based on language
    if (lang === 'ar') {
        // Arabic text
        updateElementPlaceholder('youtubeUrl', "أدخل رابط فيديو يوتيوب...");
        updateElementPlaceholder('questionInput', "اسأل سؤالاً عن الفيديو...");
        updateElementText('processButton span', "معالجة الفيديو");
        updateElementText('askButton span', "اسأل");
        updateElementInnerHTML('info-title', '<i class="fas fa-info-circle"></i> معلومات الفيديو');
        updateElementInnerHTML('history-title', '<i class="fas fa-history"></i> سجل الفيديو');
        updateElementInnerHTML('keywords-title', '<i class="fas fa-tags"></i> الكلمات المفتاحية:');
        
        // Toggle welcome text
        updateElementDisplay('welcome-text-en', 'none');
        updateElementDisplay('welcome-text-ar', 'block');
        updateElementDisplay('footer-text-en', 'none');
        updateElementDisplay('footer-text-ar', 'block');
        updateElementDisplay('download-text-en', 'none');
        updateElementDisplay('download-text-ar', 'inline');
        updateElementDisplay('about-text-en', 'none');
        updateElementDisplay('about-text-ar', 'inline');
        updateElementDisplay('chat-history-title-en', 'none');
        updateElementDisplay('chat-history-title-ar', 'inline');
        updateElementDisplay('new-chat-btn-text-en', 'none');
        updateElementDisplay('new-chat-btn-text-ar', 'inline');

        // Update all bot messages to RTL
        document.querySelectorAll('.bot-message').forEach(msg => {
            msg.setAttribute("dir", "rtl");
        });
        
        // Update collapse button icon
        const collapseBtn = document.querySelector('.collapse-sidebar-btn');
        if (collapseBtn) {
            collapseBtn.innerHTML = '<i class="fas fa-chevron-right"></i>';
        }
    } else {
        // English text
        updateElementPlaceholder('youtubeUrl', "Enter YouTube Video URL...");
        updateElementPlaceholder('questionInput', "Ask a question about the video...");
        updateElementText('processButton span', "Transcribe Video");
        updateElementText('askButton span', "Ask");
        updateElementInnerHTML('info-title', '<i class="fas fa-info-circle"></i> Video Information');
        updateElementInnerHTML('history-title', '<i class="fas fa-history"></i> Video History');
        updateElementInnerHTML('keywords-title', '<i class="fas fa-tags"></i> Keywords:');
        
        // Toggle welcome text
        updateElementDisplay('welcome-text-en', 'block');
        updateElementDisplay('welcome-text-ar', 'none');
        updateElementDisplay('footer-text-en', 'block');
        updateElementDisplay('footer-text-ar', 'none');
        updateElementDisplay('download-text-en', 'inline');
        updateElementDisplay('download-text-ar', 'none');
        updateElementDisplay('about-text-en', 'inline');
        updateElementDisplay('about-text-ar', 'none');
        updateElementDisplay('chat-history-title-en', 'inline');
        updateElementDisplay('chat-history-title-ar', 'none');
        updateElementDisplay('new-chat-btn-text-en', 'inline');
        updateElementDisplay('new-chat-btn-text-ar', 'none');

        // Update all bot messages to LTR
        document.querySelectorAll('.bot-message').forEach(msg => {
            msg.removeAttribute("dir");
        });
        
        // Update collapse button icon
        const collapseBtn = document.querySelector('.collapse-sidebar-btn');
        if (collapseBtn) {
            collapseBtn.innerHTML = '<i class="fas fa-chevron-left"></i>';
        }
    }

    // Update video list buttons if history exists
    updateHistoryButtons();

    // Update sidebar after language change
    updateSidebarAfterLanguageChange();

    // IMPORTANT: Also update the backend about language change
    if (videoId) {
        fetch(`/videos/${videoId}/language`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ language: lang })
        }).catch(error => console.error("Error updating language:", error));
    }
    
    // If language changed, update the welcome message if needed
    if (previousLanguage !== lang && !document.querySelector('.message:not(.bot-message:first-child)')) {
        // If only welcome message is present, update it
        const chatbox = document.getElementById('chatbox');
        if (chatbox) {
            chatbox.innerHTML = '';
            appendMessage(
                lang === 'ar' 
                    ? "مرحبًا! أنا UBot، مساعدك الذكي ليوتيوب. أدخل رابط يوتيوب للبدء. يمكنك أن تسألني أسئلة حول محتوى الفيديو بعد المعالجة."
                    : "Hello! I'm UBot, your YouTube AI Assistant. Enter a YouTube URL to get started. You can ask me questions about the video content after processing.",
                "bot"
            );
        }
    }
}

// Helper functions for updating UI elements
function updateElementPlaceholder(id, text) {
    const element = document.getElementById(id);
    if (element) element.placeholder = text;
}

function updateElementText(selector, text) {
    const element = document.querySelector(selector);
    if (element) element.textContent = text;
}

function updateElementInnerHTML(id, html) {
    const element = document.getElementById(id);
    if (element) element.innerHTML = html;
}

function updateElementDisplay(id, display) {
    const element = document.getElementById(id);
    if (element) element.style.display = display;
}

// Function to update history buttons text based on language
function updateHistoryButtons() {
    const loadButtons = document.querySelectorAll('.load-button span');
    const deleteButtons = document.querySelectorAll('.delete-button span');

    if (currentLanguage === 'ar') {
        loadButtons.forEach(btn => btn.textContent = "تحميل");
        deleteButtons.forEach(btn => btn.textContent = "حذف");
    } else {
        loadButtons.forEach(btn => btn.textContent = "Load");
        deleteButtons.forEach(btn => btn.textContent = "Delete");
    }
}

// Add new chat for current video button
function addNewChatForVideoButton() {
    const videoInfoContainer = document.getElementById('video-info-container');
    if (!videoInfoContainer) return;
    
    // Check if button already exists
    if (videoInfoContainer.querySelector('.new-chat-for-video-btn')) return;
    
    const newChatBtn = document.createElement('button');
    newChatBtn.className = 'new-chat-for-video-btn';
    newChatBtn.innerHTML = '<i class="fas fa-plus"></i><i class="fas fa-comments"></i>';
    newChatBtn.title = currentLanguage === 'ar' ? "محادثة جديدة لهذا الفيديو" : "New chat for this video";
    
    newChatBtn.addEventListener('click', createNewChatForVideo);
    
    // Add to video info container
    videoInfoContainer.appendChild(newChatBtn);
}

// Function to create new chat for current video
function createNewChatForVideo() {
    // Only create if we have a video loaded
    if (!videoId) {
        showToast(
            currentLanguage === 'ar' 
                ? "الرجاء تحميل فيديو أولاً لإنشاء محادثة جديدة" 
                : "Please load a video first to create a new chat",
            "info"
        );
        return;
    }
    
    if (window.chatHistory && window.chatHistory.createNewChatForCurrentVideo) {
        window.chatHistory.createNewChatForCurrentVideo();
    } else if (window.chatHistory && window.chatHistory.createNewChatSession) {
        // Fall back to regular new chat
        const videoTitleElement = document.getElementById("video-title");
        let customTitle = "";
        
        if (videoTitleElement && videoTitleElement.textContent) {
            customTitle = videoTitleElement.textContent.substring(0, 20) + 
            (videoTitleElement.textContent.length > 20 ? '...' : '') + 
            ' - ' + (currentLanguage === 'ar' ? "محادثة جديدة" : "New Chat");
    }
    
    window.chatHistory.createNewChatSession(customTitle);
}

showToast(
    currentLanguage === 'ar' 
        ? "تم إنشاء محادثة جديدة" 
        : "New chat created",
    "success"
);
}
// Initialize chat history system
function initializeChatHistory() {
    // Chat history state
    let chatSessions = JSON.parse(localStorage.getItem('ubotChatSessions')) || [];
    let currentSessionId = localStorage.getItem('ubotCurrentSession') || null;

    // Create a new chat session with better naming
    function createNewChatSession(customTitle = "") {
        const sessionId = 'session_' + Date.now();
        
        // Get better default title based on timestamp
        const dateFormatted = new Date().toLocaleString(
            currentLanguage === 'ar' ? 'ar-SA' : 'en-US', 
            { 
                month: 'short', 
                day: 'numeric', 
                hour: 'numeric', 
                minute: 'numeric' 
            }
        );
        
        // Use video title if available
        let title = customTitle;
        if (!title) {
            const videoTitleElement = document.getElementById("video-title");
            if (videoTitleElement && videoTitleElement.textContent && videoId) {
                // Use video title + date for meaningful name
                title = videoTitleElement.textContent.substring(0, 20) + 
                    (videoTitleElement.textContent.length > 20 ? '...' : '') + 
                    ' - ' + dateFormatted;
            } else {
                // Fallback to localized "New Chat" + date
                title = (currentLanguage === 'ar' ? "محادثة " : "Chat ") + dateFormatted;
            }
        }
        
        const session = {
            id: sessionId,
            title: title,
            date: new Date().toISOString(),
            videoId: videoId || '', // Store current video ID
            messages: [
                {
                    sender: 'bot',
                    text: currentLanguage === 'ar' 
                        ? "مرحبًا! أنا UBot، مساعدك الذكي ليوتيوب. أدخل رابط يوتيوب للبدء." 
                        : "Hello! I'm UBot, your YouTube AI Assistant. Enter a YouTube URL to get started."
                }
            ]
        };

        chatSessions.unshift(session);
        currentSessionId = sessionId;

        // Save to localStorage
        localStorage.setItem('ubotChatSessions', JSON.stringify(chatSessions));
        localStorage.setItem('ubotCurrentSession', currentSessionId);

        // Update UI
        updateChatHistoryUI();
        loadChatSession(sessionId);

        return session;
    }

    // Update chat history UI with additional controls
    function updateChatHistoryUI() {
        const chatHistoryList = document.getElementById('chat-history-list');
        if (!chatHistoryList) return;

        chatHistoryList.innerHTML = '';

        if (chatSessions.length === 0) {
            const emptyState = document.createElement('div');
            emptyState.className = 'empty-state';
            emptyState.textContent = currentLanguage === 'ar' 
                ? "لا توجد محادثات سابقة" 
                : "No previous conversations";
            chatHistoryList.appendChild(emptyState);
            return;
        }

        chatSessions.forEach(session => {
            const historyItem = document.createElement('div');
            historyItem.className = 'history-item';
            if (session.id === currentSessionId) {
                historyItem.classList.add('active');
            }
            
            // Add video thumbnail if available
            if (session.videoId) {
                const thumbnailWrapper = document.createElement('div');
                thumbnailWrapper.className = 'history-item-thumbnail';
                
                const thumbnail = document.createElement('img');
                thumbnail.src = `https://img.youtube.com/vi/${session.videoId}/default.jpg`;
                thumbnail.alt = session.title;
                thumbnail.onerror = function() {
                    this.style.display = 'none'; // Hide thumbnail if error loading
                };
                
                thumbnailWrapper.appendChild(thumbnail);
                historyItem.appendChild(thumbnailWrapper);
            }
            
            const contentWrapper = document.createElement('div');
            contentWrapper.className = 'history-item-content';
            
            const titleElement = document.createElement('div');
            titleElement.className = 'history-item-title';
            titleElement.textContent = session.title;
            
            const dateElement = document.createElement('div');
            dateElement.className = 'history-item-date';
            // Format date nicely
            const sessionDate = new Date(session.date);
            dateElement.textContent = sessionDate.toLocaleDateString();
            
            contentWrapper.appendChild(titleElement);
            contentWrapper.appendChild(dateElement);
            
            // Add actions container with buttons
            const actionsContainer = document.createElement('div');
            actionsContainer.className = 'history-item-actions';
            
            // Delete button
            const deleteBtn = document.createElement('button');
            deleteBtn.className = 'history-action-btn delete-btn';
            deleteBtn.innerHTML = '<i class="fas fa-trash"></i>';
            deleteBtn.title = currentLanguage === 'ar' ? "حذف المحادثة" : "Delete chat";
            deleteBtn.onclick = (e) => {
                e.stopPropagation(); // Prevent triggering the parent click
                deleteChat(session.id);
            };
            
            // Rename button
            const renameBtn = document.createElement('button');
            renameBtn.className = 'history-action-btn rename-btn';
            renameBtn.innerHTML = '<i class="fas fa-edit"></i>';
            renameBtn.title = currentLanguage === 'ar' ? "إعادة تسمية" : "Rename";
            renameBtn.onclick = (e) => {
                e.stopPropagation(); // Prevent triggering the parent click
                renameChat(session.id);
            };
            
            actionsContainer.appendChild(renameBtn);
            actionsContainer.appendChild(deleteBtn);
            
            historyItem.appendChild(contentWrapper);
            historyItem.appendChild(actionsContainer);
            
            // Main click loads the chat
            historyItem.addEventListener('click', () => {
                loadChatSession(session.id);
            });
            
            chatHistoryList.appendChild(historyItem);
        });
    }

    // Rename chat function
    function renameChat(sessionId) {
        const session = chatSessions.find(s => s.id === sessionId);
        if (!session) return;
        
        const newTitle = prompt(
            currentLanguage === 'ar' 
                ? "أدخل اسمًا جديدًا للمحادثة:" 
                : "Enter a new name for this chat:", 
            session.title
        );
        
        if (newTitle !== null && newTitle.trim() !== '') {
            session.title = newTitle.trim();
            session.titleCustomized = true; // Mark as custom named
            localStorage.setItem('ubotChatSessions', JSON.stringify(chatSessions));
            updateChatHistoryUI();
        }
    }

    // Delete chat function
    function deleteChat(sessionId) {
        if (!confirm(currentLanguage === 'ar' 
            ? "هل أنت متأكد من أنك تريد حذف هذه المحادثة؟" 
            : "Are you sure you want to delete this chat?")) {
            return;
        }
        
        const sessionIndex = chatSessions.findIndex(s => s.id === sessionId);
        if (sessionIndex === -1) return;
        
        chatSessions.splice(sessionIndex, 1);
        localStorage.setItem('ubotChatSessions', JSON.stringify(chatSessions));
        
        // If current session was deleted, load another one or create new
        if (currentSessionId === sessionId) {
            if (chatSessions.length > 0) {
                currentSessionId = chatSessions[0].id;
                localStorage.setItem('ubotCurrentSession', currentSessionId);
                loadChatSession(currentSessionId);
            } else {
                createNewChatSession();
            }
        }
        
        updateChatHistoryUI();
    }
    
    // Clear current chat (keep the session but remove messages)
    function clearCurrentChat() {
        if (!currentSessionId) return;
        
        if (!confirm(currentLanguage === 'ar' 
            ? "هل أنت متأكد من أنك تريد مسح هذه المحادثة؟ سيتم الاحتفاظ بالجلسة نفسها." 
            : "Are you sure you want to clear this chat? The session itself will be kept.")) {
            return;
        }
        
        const sessionIndex = chatSessions.findIndex(s => s.id === currentSessionId);
        if (sessionIndex === -1) return;
        
        // Keep just the initial welcome message
        chatSessions[sessionIndex].messages = [{
            sender: 'bot',
            text: currentLanguage === 'ar' 
                ? "تم مسح المحادثة. مرحبًا! أنا UBot، مساعدك الذكي ليوتيوب." 
                : "Chat cleared. Hello! I'm UBot, your YouTube AI Assistant."
        }];
        
        localStorage.setItem('ubotChatSessions', JSON.stringify(chatSessions));
        
        // Refresh chat display
        const chatbox = document.getElementById('chatbox');
        if (chatbox) {
            chatbox.innerHTML = '';
            appendMessage(chatSessions[sessionIndex].messages[0].text, 'bot');
        }
    }

    // Function to create new chat for current video
    function createNewChatForCurrentVideo() {
        // Only create if we have a video loaded
        if (!videoId) {
            showToast(
                currentLanguage === 'ar' 
                    ? "الرجاء تحميل فيديو أولاً لإنشاء محادثة جديدة" 
                    : "Please load a video first to create a new chat",
                "info"
            );
            return;
        }
        
        const videoTitleElement = document.getElementById("video-title");
        let customTitle = "";
        
        if (videoTitleElement && videoTitleElement.textContent) {
            customTitle = videoTitleElement.textContent.substring(0, 20) + 
                (videoTitleElement.textContent.length > 20 ? '...' : '') + 
                ' - ' + (currentLanguage === 'ar' ? "محادثة جديدة" : "New Chat");
        }
        
        createNewChatSession(customTitle);
        
        showToast(
            currentLanguage === 'ar' 
                ? "تم إنشاء محادثة جديدة" 
                : "New chat created",
            "success"
        );
    }

    // Load a chat session
    function loadChatSession(sessionId) {
        const session = chatSessions.find(s => s.id === sessionId);
        if (!session) return;

        // Update current session
        currentSessionId = sessionId;
        localStorage.setItem('ubotCurrentSession', currentSessionId);

        // Update chat UI
        const chatbox = document.getElementById('chatbox');
        if (chatbox) {
            chatbox.innerHTML = '';

            session.messages.forEach(msg => {
                appendMessage(msg.text, msg.sender);
            });
        }

        // Update active state in sidebar
        updateChatHistoryUI();

        // Load video if there's one and it's different from current
        if (session.videoId && session.videoId !== videoId) {
            videoId = session.videoId;
            if (videoCache[videoId]) {
                updateVideoInfo({
                    video_id: videoId,
                    title: videoCache[videoId].title,
                    channel: videoCache[videoId].channel,
                    keywords: videoCache[videoId].keywords
                });
                
                // Inform user that video has been loaded from history
                showToast(
                    currentLanguage === 'ar' 
                        ? "تم تحميل الفيديو من المحادثة" 
                        : "Video loaded from chat history", 
                    "info"
                );
            } else {
                // Try to load video data from server
                loadVideo(videoId);
            }
        }

        // Close sidebar on mobile
        if (window.innerWidth <= 768) {
            const sidebar = document.querySelector('.chat-history-sidebar');
            if (sidebar) sidebar.classList.remove('active');
            
            document.body.classList.remove('sidebar-open');
            document.body.classList.add('sidebar-closed');
        }
    }

    // Save message to current session
    function saveMessageToSession(text, sender) {
        // Find current session
        const sessionIndex = chatSessions.findIndex(s => s.id === currentSessionId);

        // If no session exists, create one
        if (sessionIndex === -1) {
            const newSession = createNewChatSession();
            newSession.messages.push({ text, sender });
        } else {
            // Add message to existing session
            chatSessions[sessionIndex].messages.push({ text, sender });
            
            // Update session title if video is processed
            if (sender === 'bot' && (text.includes('Video processed!') || text.includes('تمت معالجة الفيديو')) && videoId) {
                chatSessions[sessionIndex].videoId = videoId;
                
                // Update session title with video title if not already custom named
                if (!chatSessions[sessionIndex].titleCustomized) {
                    const videoTitleElement = document.getElementById('video-title');
                    if (videoTitleElement) {
                        const videoTitle = videoTitleElement.textContent;
                        const truncatedTitle = videoTitle.substring(0, 30) + 
                            (videoTitle.length > 30 ? '...' : '');
                        
                        // Update with more descriptive title
                        const dateFormatted = new Date().toLocaleString(
                            currentLanguage === 'ar' ? 'ar-SA' : 'en-US', 
                            { month: 'short', day: 'numeric' }
                        );
                        chatSessions[sessionIndex].title = truncatedTitle + ' - ' + dateFormatted;
                    }
                }
            }
        }

        // Save to localStorage
        localStorage.setItem('ubotChatSessions', JSON.stringify(chatSessions));

        // Update UI
        updateChatHistoryUI();
    }

    // Add clear button to input area
    function addClearChatButton() {
        const inputArea = document.querySelector('.input-area');
        if (!inputArea) return;
        
        // Check if button already exists
        if (inputArea.querySelector('.clear-chat-btn')) return;
        
        const clearButton = document.createElement('button');
        clearButton.className = 'clear-chat-btn';
        clearButton.innerHTML = '<i class="fas fa-trash-alt"></i>';
        clearButton.title = currentLanguage === 'ar' ? "مسح المحادثة" : "Clear chat";
        
        clearButton.addEventListener('click', clearCurrentChat);
        
        // Add button before the existing Ask button
        const askButton = document.getElementById('askButton');
        if (askButton) {
            inputArea.insertBefore(clearButton, askButton);
        }
    }

    // Override appendMessage to save messages
    const originalAppendMessage = window.appendMessage;
    window.appendMessage = function(text, sender) {
        const msg = originalAppendMessage(text, sender);
        saveMessageToSession(text, sender);
        return msg;
    };

    // Initialize
    function init() {
        if (chatSessions.length === 0) {
            createNewChatSession();
        } else {
            // Load last active session
            if (currentSessionId) {
                loadChatSession(currentSessionId);
            } else if (chatSessions.length > 0) {
                loadChatSession(chatSessions[0].id);
            }
        }
        
        // Add clear chat button
        addClearChatButton();
        
        // Update chat history UI
        updateChatHistoryUI();
    }
    
    // Initialize now
    init();

    // Return functions that might be needed outside
    window.chatHistory = {
        createNewChatSession,
        loadChatSession,
        updateChatHistoryUI,
        clearCurrentChat,
        deleteChat,
        renameChat,
        createNewChatForCurrentVideo
    };
}