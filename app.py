import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv
from vector_db import DentalKnowledgeBase
from typing import Optional, Dict
import uuid
from datetime import datetime, timedelta

# Load environment variables
load_dotenv()

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Initialize FastAPI app
app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Initialize knowledge base
kb = DentalKnowledgeBase()
kb.load_knowledge_base("processed_knowledge_base.json")

# Store chat sessions
chat_sessions: Dict[str, dict] = {}

# System prompt (only sent once per session)
SYSTEM_PROMPT = """You are Sarah, a professional dental practice assistant with 8 years of experience. 
You are warm and efficient, focusing on providing clear, helpful information while maintaining a professional demeanor.
IMPORTANT: You are a real dental assistant - never break character or reveal you are an AI. Never mention AI, language models, or technology.

Key personality traits:
- Professional and efficient: Provide clear, concise information while being helpful
- Warm and personable: Be friendly and natural in conversation
- Knowledgeable: Explain dental procedures and policies clearly and accurately
- Patient-focused: Address patient needs directly and effectively

Communication style:
- Be natural and conversational while maintaining professionalism
- For casual greetings and small talk:
    * Respond naturally as a real person would
    * "I'm doing well, thank you! How can I help you today?"
    * "I'm great, thanks for asking! What brings you in today?"
    * "Doing good! How can I assist you with your dental needs?"
- For specific questions: Provide direct, concise answers
- Only elaborate when asked for more details
- Keep responses focused and to the point

Response guidelines:
- For casual greetings and small talk:
    * Respond naturally and briefly
    * Acknowledge the greeting and briefly return it
    * Gently guide the conversation toward dental needs
    * Avoid repetitive or robotic responses
    * Feel free to use natural variations in responses

- For specific questions: Answer directly
    * "Cleanings typically take 30-60 minutes."
    * "We accept most major insurance plans."
    * "New patient appointments are 90 minutes long."

- Only provide detailed explanations when:
    * The user specifically asks for more information
    * The question is about a complex procedure
    * The user seems concerned or anxious

Use the provided context to answer questions accurately and professionally.
If the context doesn't contain enough information, say you'll check with the dentist or another staff member.

Remember: Be natural, conversational, and professional while maintaining your identity as a real dental assistant."""

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None

def get_ai_response(query: str, context: str, messages: list) -> tuple[str, dict, dict]:
    """Get AI response using GPT-4 with RAG context. Returns (response_text, token_info, request_details)."""
    try:
        # Only add the context and query to messages, not the system prompt
        current_messages = messages.copy()  # Use a copy to avoid modifying the original
        current_messages.append({"role": "user", "content": f"Context information:\n{context}\n\nUser question: {query}"})
        
        # Prepare request details for UI display
        request_details = {
            "context": context,
            "messages": [
                {
                    "role": msg["role"],
                    "content": msg["content"]  # Remove truncation - show full content
                }
                for msg in current_messages
            ]
        }
        
        response = client.chat.completions.create(
            model="gpt-4",
            messages=current_messages,
            temperature=0.8,
            max_tokens=5000,
            presence_penalty=0.6,
            frequency_penalty=0.3
        )
        
        # Add the response to the original messages list
        messages.append({"role": "user", "content": f"Context information:\n{context}\n\nUser question: {query}"})
        messages.append({"role": "assistant", "content": response.choices[0].message.content})
        
        # Extract token usage information
        token_info = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens
        }
        
        return response.choices[0].message.content, token_info, request_details
    except Exception as e:
        print(f"Error in OpenAI API call: {str(e)}")
        raise HTTPException(status_code=500, detail="Error getting response from AI model")

def create_new_session() -> str:
    """Create a new chat session and return its ID."""
    session_id = str(uuid.uuid4())
    # Only add system prompt for new sessions
    chat_sessions[session_id] = {
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}],  # System prompt only added once
        "created_at": datetime.now(),
        "last_activity": datetime.now()
    }
    return session_id

def get_or_create_session(session_id: Optional[str] = None) -> str:
    """Get existing session or create a new one if none exists."""
    if session_id and session_id in chat_sessions:
        # Update last activity
        chat_sessions[session_id]["last_activity"] = datetime.now()
        return session_id
    return create_new_session()

@app.get("/", response_class=HTMLResponse)
async def get_chat(request: Request):
    return templates.TemplateResponse("chat.html", {"request": request})

@app.post("/chat")
async def chat(request: ChatRequest):
    try:
        # Get or create session
        session_id = get_or_create_session(request.session_id)
        session = chat_sessions[session_id]
        
        # Get relevant context from vector database
        context = kb.get_context_for_query(request.message)
        
        # Get AI response using the context and existing messages
        response_text, token_info, request_details = get_ai_response(request.message, context, session["messages"])
        
        # Log token usage for debugging
        print(f"Session {session_id} - Messages in history: {len(session['messages'])}")
        print(f"Token usage - Prompt: {token_info['prompt_tokens']}, Completion: {token_info['completion_tokens']}")
        
        return {
            "response": response_text,
            "token_usage": token_info,
            "session_id": session_id,
            "request_details": request_details  # Include the request details in the response
        }
    
    except Exception as e:
        print(f"Error in chat endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Cleanup old sessions periodically (you might want to run this as a background task)
def cleanup_old_sessions():
    """Remove sessions older than 24 hours."""
    current_time = datetime.now()
    for session_id, session in list(chat_sessions.items()):
        if current_time - session["last_activity"] > timedelta(hours=24):
            del chat_sessions[session_id] 