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
    """Ask questions to the user, in order to enrich the plan of the whole report."""
    message: Optional[str] = ""
    report_id: Optional[str] = None  # string type, support MongoDB ObjectId
    template_id: Optional[str] = None  # template ID

class UpdateQuestion(BaseModel):
    """Update the question to the user, in order to enrich the plan of the whole report."""
    report_id: Optional[str] = None  # string type, support MongoDB ObjectId
    message: Optional[str] = ""

class LLMMessage(BaseModel):
    """大模型请求模型"""
    message: Optional[str] = ""
    report_id: Optional[str] = None  # 改为字符串类型，支持MongoDB ObjectId

class UpdatePlan(BaseModel):
    """大模型请求模型"""
    report_id: Optional[str] = None  # 改为字符串类型，支持MongoDB ObjectId
    plan_id: Optional[str] = None  # 改为字符串类型，支持MongoDB ObjectId
    plan: Optional[str] = ""

class SearchRequest(BaseModel):
    """搜索请求模型"""
    query: str
    max_results: Optional[int] = 10
    include_images: Optional[bool] = True
    country: Optional[str] = "china"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    include_domains: Optional[List[str]] = None
    exclude_domains: Optional[List[str]] = None

class SearchResult(BaseModel):
    """单个搜索结果模型"""
    title: Optional[str] = None
    url: Optional[str] = None
    content: Optional[str] = None
    score: Optional[float] = None
    # raw_content: Optional[str] = None

class SearchImageResult(BaseModel):
    """单个搜索结果模型"""
    url: Optional[str] = None
    description: Optional[str] = None
    # title: Optional[str] = None

class SearchResponse(BaseModel):
    """搜索响应模型"""
    images: List[SearchImageResult]
    sources: List[SearchResult]

class TavilySearchRequest(BaseModel):
    """Tavily搜索请求模型"""
    query: str
    search_depth: Optional[str] = "basic"  # "basic" or "advanced"
    include_answer: Optional[bool] = True
    include_raw_content: Optional[bool] = False
    max_results: Optional[int] = 5
    include_domains: Optional[List[str]] = None
    exclude_domains: Optional[List[str]] = None
    include_images: Optional[bool] = False
    include_image_descriptions: Optional[bool] = False

class TavilyImageResult(BaseModel):
    """Tavily图片结果模型"""
    url: str
    description: Optional[str] = None

class TavilySearchResponse(BaseModel):
    """Tavily搜索响应模型"""
    answer: Optional[str] = None
    query: str
    response_time: float
    images: Optional[List[TavilyImageResult]] = None
    results: List[Dict[str, Any]]
    follow_up_questions: Optional[List[str]] = None

class TavilyKey(Base):
    """Tavily API Key表模型"""
    __tablename__ = "tavily_key"
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment="自增主键")
    api_key = Column(String(255), nullable=False, comment="apikey")
    usage_count = Column(Integer, nullable=False, default=0, comment="已使用的次数")
    remaining = Column(Integer, nullable=False, default=1000, comment="未使用的次数")
    is_available = Column(Boolean, nullable=False, default=True, comment="是否可用")

class TavilyKeyResponse(BaseModel):
    id: int
    api_key: str
    usage_count: int
    remaining: int
    is_available: bool

class LLMMessageFinal(BaseModel):
    """最终报告请求模型"""
    report_id: str  # 报告ID
    split_id: str   # 分割ID
    requirement: Optional[str] = ""  # 要求字段保持不变
