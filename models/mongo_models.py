"""
MongoDB数据模型定义
"""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from datetime import datetime
from bson import ObjectId

class PyObjectId(ObjectId):
    """自定义ObjectId类型，用于Pydantic序列化"""
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
    """步骤状态模型"""
    completed: bool = False
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    execution_time: Optional[float] = None
    status: str = "pending"  # pending, processing, completed, failed
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None

class ReportSteps(BaseModel):
    """报告各步骤状态"""
    ask_questions: StepStatus = Field(default_factory=StepStatus)
    plan: StepStatus = Field(default_factory=StepStatus)
    serp: StepStatus = Field(default_factory=StepStatus)
    search: StepStatus = Field(default_factory=StepStatus)
    search_summary: StepStatus = Field(default_factory=StepStatus)
    final_report: StepStatus = Field(default_factory=StepStatus)
    summary_generation: StepStatus = Field(default_factory=StepStatus)

class MongoReport(BaseModel):
    """MongoDB报告模型"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    user_id: Optional[str] = Field(None, description="用户ID")
    tenant_id: Optional[str] = Field(None, description="租户ID")
    message: str = Field(..., description="用户输入的查询内容")
    title: Optional[str] = Field(None, description="报告标题")
    
    # 整体状态
    status: str = Field(default="created", description="整体状态: created, processing, completed, failed")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    
    # 各步骤状态
    steps: ReportSteps = Field(default_factory=ReportSteps)
    
    # 统计信息
    total_steps: int = Field(default=0, description="总步骤数")
    completed_steps: int = Field(default=0, description="已完成步骤数")
    progress_percentage: float = Field(default=0.0, description="完成进度百分比")
    locked: bool = Field(default=False, description="是否锁定")
    
    # 模板相关字段
    template_status: bool = Field(default=False, description="是否使用模板")
    template_id: Optional[str] = Field(None, description="使用的模板ID")
    template: str = Field(default="", description="模板ID，存储report_plan_template集合中的模板ID")
    is_replace: bool = Field(default=False, description="是否替换模板")
    
    # 最终报告完成状态
    isFinalReportCompleted: bool = Field(default=False, description="最终报告是否已完成")
    
    # 报告总结
    summary: Optional[str] = Field(None, description="报告总结内容")
    
    # 额外数据
    metadata: Dict[str, Any] = Field(default_factory=dict)

class ReportCreateRequest(BaseModel):
    """创建报告请求模型"""
    message: str = Field(..., description="用户查询内容")
    title: Optional[str] = Field(None, description="报告标题")

class ReportResponse(BaseModel):
    """报告响应模型"""
    id: str = Field(..., description="报告ID")
    message: str = Field(..., description="用户查询内容")
    title: Optional[str] = Field(None, description="报告标题")
    status: str = Field(..., description="整体状态")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")
    steps: ReportSteps = Field(..., description="各步骤状态")
    total_steps: int = Field(..., description="总步骤数")
    completed_steps: int = Field(..., description="已完成步骤数")
    progress_percentage: float = Field(..., description="完成进度百分比")
    locked: bool = Field(..., description="是否锁定")
    isFinalReportCompleted: bool = Field(default=False, description="最终报告是否已完成")
    template: str = Field(default="", description="模板ID，存储report_plan_template集合中的模板ID")
    is_replace: bool = Field(None, description="是否替换模板")

class ReportListResponse(BaseModel):
    """报告列表响应模型"""
    total: int = Field(..., description="总记录数")
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页大小")
    total_pages: int = Field(..., description="总页数")
    reports: List[ReportResponse] = Field(..., description="报告列表")

class ReportLockRequest(BaseModel):
    """报告锁定请求模型"""
    report_id: str = Field(..., description="报告ID")
    locked: bool = Field(..., description="锁定状态")
