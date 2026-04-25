from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime, func, JSON, Float
from utils.database import Base
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class LLMRequest(BaseModel):
    """LLM request model"""
    messages: List[Dict[str, str]]
    model: Optional[str] = None
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 120000
    stream: Optional[bool] = True
    use_mcp: Optional[bool] = False
    tools: Optional[List[str]] = None
    mcp_tools: Optional[List[str]] = None
    auto_select_tools: Optional[bool] = True

class LLMMessageAskQuestions(BaseModel):
    """Ask questions to enrich the report plan."""
    message: Optional[str] = ""
    report_id: Optional[str] = None
    template_id: Optional[str] = None

class UpdateQuestion(BaseModel):
    """Update the question for report plan enrichment."""
    report_id: Optional[str] = None
    message: Optional[str] = ""

class LLMMessage(BaseModel):
    """LLM request model"""
    message: Optional[str] = ""
    report_id: Optional[str] = None

class UpdatePlan(BaseModel):
    """Plan update model"""
    report_id: Optional[str] = None
    plan_id: Optional[str] = None
    plan: Optional[str] = ""

class SearchRequest(BaseModel):
    """Search request model"""
    query: str
    max_results: Optional[int] = 10
    include_images: Optional[bool] = True
    country: Optional[str] = "china"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    include_domains: Optional[List[str]] = None
    exclude_domains: Optional[List[str]] = None

class SearchResult(BaseModel):
    """Single search result model"""
    title: Optional[str] = None
    url: Optional[str] = None
    content: Optional[str] = None
    score: Optional[float] = None

class SearchImageResult(BaseModel):
    """Search image result model"""
    url: Optional[str] = None
    description: Optional[str] = None

class SearchResponse(BaseModel):
    """Search response model"""
    images: List[SearchImageResult]
    sources: List[SearchResult]

class TavilySearchRequest(BaseModel):
    """Tavily search request model"""
    query: str
    search_depth: Optional[str] = "basic"
    include_answer: Optional[bool] = True
    include_raw_content: Optional[bool] = False
    max_results: Optional[int] = 5
    include_domains: Optional[List[str]] = None
    exclude_domains: Optional[List[str]] = None
    include_images: Optional[bool] = False
    include_image_descriptions: Optional[bool] = False

class TavilyImageResult(BaseModel):
    """Tavily image result model"""
    url: str
    description: Optional[str] = None

class TavilySearchResponse(BaseModel):
    """Tavily search response model"""
    answer: Optional[str] = None
    query: str
    response_time: float
    images: Optional[List[TavilyImageResult]] = None
    results: List[Dict[str, Any]]
    follow_up_questions: Optional[List[str]] = None

class TavilyKey(Base):
    """Tavily API Key table model"""
    __tablename__ = "tavily_key"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="Auto-increment primary key")
    api_key = Column(String(255), nullable=False, comment="API key")
    usage_count = Column(Integer, nullable=False, default=0, comment="Usage count")
    remaining = Column(Integer, nullable=False, default=1000, comment="Remaining quota")
    is_available = Column(Boolean, nullable=False, default=True, comment="Availability status")

class TavilyKeyResponse(BaseModel):
    id: int
    api_key: str
    usage_count: int
    remaining: int
    is_available: bool

class LLMMessageFinal(BaseModel):
    """Final report request model"""
    report_id: str
    split_id: str
    requirement: Optional[str] = ""

class LLMMessage1(BaseModel):
    """LLM request model"""
    plan: Optional[str] = ""
    current: Optional[str] = ""
    report_id: Optional[str] = None

class LLMMessageSearchSummary(BaseModel):
    """Search summary request model"""
    report_id: Optional[str] = None
    search_id: Optional[str] = ""
    task_id: Optional[str] = ""
