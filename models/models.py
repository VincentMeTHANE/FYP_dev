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
