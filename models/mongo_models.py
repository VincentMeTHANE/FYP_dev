"""
MongoDB data model definitions
"""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from datetime import datetime
from bson import ObjectId

class PyObjectId(ObjectId):
    """Custom ObjectId type for Pydantic serialization"""
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v, validation_info=None):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid objectid")
        return ObjectId(v)

    @classmethod
    def __get_pydantic_json_schema__(cls, field_schema):
        field_schema.update(type="string")
        return field_schema

class StepStatus(BaseModel):
    """Step status model"""
    completed: bool = False
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    execution_time: Optional[float] = None
    status: str = "pending"  # pending, processing, completed, failed
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None

class ReportSteps(BaseModel):
    """Report step statuses"""
    ask_questions: StepStatus = Field(default_factory=StepStatus)
    plan: StepStatus = Field(default_factory=StepStatus)
    serp: StepStatus = Field(default_factory=StepStatus)
    search: StepStatus = Field(default_factory=StepStatus)
    search_summary: StepStatus = Field(default_factory=StepStatus)
    final_report: StepStatus = Field(default_factory=StepStatus)
    summary_generation: StepStatus = Field(default_factory=StepStatus)

class MongoReport(BaseModel):
    """MongoDB report model"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    user_id: Optional[str] = Field(None, description="User ID")
    tenant_id: Optional[str] = Field(None, description="Tenant ID")
    message: str = Field(..., description="User input query content")
    title: Optional[str] = Field(None, description="Report title")
    
    # Overall status
    status: str = Field(default="created", description="Overall status: created, processing, completed, failed")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    
    # Step statuses
    steps: ReportSteps = Field(default_factory=ReportSteps)
    
    # Statistics
    total_steps: int = Field(default=0, description="Total number of steps")
    completed_steps: int = Field(default=0, description="Number of completed steps")
    progress_percentage: float = Field(default=0.0, description="Progress percentage")
    locked: bool = Field(default=False, description="Whether locked")
    
    # Template related fields
    template_status: bool = Field(default=False, description="Whether using template")
    template_id: Optional[str] = Field(None, description="Template ID used")
    template: str = Field(default="", description="Template ID, stores template ID from report_plan_template collection")
    is_replace: bool = Field(default=False, description="Whether to replace template")
    
    # Final report completion status
    isFinalReportCompleted: bool = Field(default=False, description="Whether final report is completed")
    
    # Report summary
    summary: Optional[str] = Field(None, description="Report summary content")
    
    # Extra data
    metadata: Dict[str, Any] = Field(default_factory=dict)

class ReportCreateRequest(BaseModel):
    """Create report request model"""
    message: str = Field(..., description="User query content")
    title: Optional[str] = Field(None, description="Report title")

class ReportResponse(BaseModel):
    """Report response model"""
    id: str = Field(..., description="Report ID")
    message: str = Field(..., description="User query content")
    title: Optional[str] = Field(None, description="Report title")
    status: str = Field(..., description="Overall status")
    created_at: datetime = Field(..., description="Created time")
    updated_at: datetime = Field(..., description="Updated time")
    steps: ReportSteps = Field(..., description="Step statuses")
    total_steps: int = Field(..., description="Total steps")
    completed_steps: int = Field(..., description="Completed steps")
    progress_percentage: float = Field(..., description="Progress percentage")
    locked: bool = Field(..., description="Whether locked")
    isFinalReportCompleted: bool = Field(default=False, description="Whether final report is completed")
    template: str = Field(default="", description="Template ID, stores template ID from report_plan_template collection")
    is_replace: bool = Field(None, description="Whether to replace template")

class ReportListResponse(BaseModel):
    """Report list response model"""
    total: int = Field(..., description="Total count")
    page: int = Field(..., description="Current page")
    page_size: int = Field(..., description="Page size")
    total_pages: int = Field(..., description="Total pages")
    reports: List[ReportResponse] = Field(..., description="Report list")

class ReportLockRequest(BaseModel):
    """Report lock request model"""
    report_id: str = Field(..., description="Report ID")
    locked: bool = Field(..., description="Lock status")
