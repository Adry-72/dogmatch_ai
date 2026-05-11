from typing import List
from pydantic import BaseModel, Field


class HistoryMessage(BaseModel):
    role: str  # 'user' | 'assistant'
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., max_length=500)
    user_id: str
    context: str  # pre-built system prompt from Node.js backend
    history: List[HistoryMessage] = []


class ChatResponse(BaseModel):
    risposta: str
