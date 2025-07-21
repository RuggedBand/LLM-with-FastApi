from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel

class ArticleRequest(BaseModel):
    user_query: str
    model: str = "gemini-1.5-flash"
    name: str
    userid : str

class QueuedArticleResponse(BaseModel):
    request_id: str
    status: str
    estimated_completion_time_minutes: int
    message: str

class RAGQuery(BaseModel):
    query: str
    similarity_threshold: float = 0.7

class RAGResponse(BaseModel):
    answer: str
    response_type: str
    sources: Optional[list] = None

class RequestStatusResponse(BaseModel):
    status: Optional[str] = None
    user_query: Optional[str] = None
    model: Optional[str] = None
    name: Optional[str] = None
    userid: Optional[str] = None
    request_id: Optional[str] = None
    timestamp: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None