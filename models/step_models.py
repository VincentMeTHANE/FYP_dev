"""
Step record MongoDB model definitions
"""

from typing import Optional, Dict, Any,List
from pydantic import BaseModel, Field
from datetime import datetime
from bson import ObjectId
from models.mongo_models import PyObjectId


class BaseStepRecord(BaseModel):
    """Base step record model"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    report_id: str = Field(..., description="Associated report ID")
    query: str = Field(..., description="User query content")
    status: str = Field(default="processing", description="Processing status: processing, completed, failed")
    response: Optional[Dict[str, Any]] = Field(None, description="Execution result")
    execution_time: Optional[float] = Field(None, description="Execution time (seconds)")
    error_message: Optional[str] = Field(None, description="Error message")
    # Token statistics fields
    prompt_tokens: Optional[int] = Field(None, description="Input token count")
    completion_tokens: Optional[int] = Field(None, description="Output token count")
    total_tokens: Optional[int] = Field(None, description="Total token count")
    created_at: datetime = Field(default_factory=datetime.now, description="Created time")
    updated_at: datetime = Field(default_factory=datetime.now, description="Updated time")

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class ReportAskQuestions(BaseStepRecord):
    """Ask questions step record"""
    message: Optional[str] = Field(None, description="User's ideas")
    pass


class ReportPlan(BaseStepRecord):
    """Report plan step record"""
    index: Optional[int] = Field(None, description="Chapter index")
    pass


class ReportSerp(BaseStepRecord):
    """SERP query step record"""
    split_id: str = Field(..., description="Associated chapter split ID")
    tasks: Optional[List[Dict[str, Any]]] = Field(None, description="Returned data")
    plan: Optional[str] = Field(None, description="Plan content")
    current: Optional[str] = Field(None, description="Current processing section")
    only_key: str = Field(..., description="Unique identifier for a batch")


class SerpTask(BaseModel):
    """SERP task model"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    serp_record_id: str = Field(..., description="Associated SERP record ID")
    report_id: str = Field(..., description="Associated report ID")
    split_id: str = Field(..., description="Associated chapter split ID")
    query: str = Field(..., description="Query content")
    research_goal: str = Field(..., description="Research goal")
    search_type: str = Field(default="online",description="Search type: online=online, knowledge=knowledge base")
    search_state: str = Field(default="unprocessed", description="Search state: unprocessed=not started, searchFailed=search failed, searchCompleted=search succeeded, completed=success, failed=failed")
    task_index: int = Field(..., description="Task index in array")
    created_at: datetime = Field(default_factory=datetime.now, description="Created time")
    updated_at: datetime = Field(default_factory=datetime.now, description="Updated time")

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class ReportSearch(BaseStepRecord):
    """Search step record"""
    search_id: str = Field(..., description="Search ID")
    max_results: Optional[int] = Field(None, description="Maximum number of results")
    include_images: Optional[bool] = Field(None, description="Whether to include images")
    results_count: Optional[int] = Field(None, description="Actual number of results")


class ReportSearchSummary(BaseStepRecord):
    """Search summary step record"""
    task_id: str = Field(..., description="Task ID")
    split_id: str = Field(..., description="Chapter split ID")

class finalReport(BaseModel):
    """finalReport model"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    report_id: str = Field(..., description="Associated report ID")
    split_id: str = Field(..., description="Associated chapter split ID")
    chapter_index: Optional[int] = Field(None, description="Chapter index")
    query: Optional[str] = Field(None, description="Query content")
    current: str = Field(..., description="Result")
    created_at: datetime = Field(default_factory=datetime.now, description="Created time")
    updated_at: datetime = Field(default_factory=datetime.now, description="Updated time")
