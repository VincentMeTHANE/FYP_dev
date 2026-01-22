"""
步骤记录的MongoDB模型定义
"""

from typing import Optional, Dict, Any,List
from pydantic import BaseModel, Field
from datetime import datetime
from bson import ObjectId
from models.mongo_models import PyObjectId


class BaseStepRecord(BaseModel):
    """步骤记录基础模型"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    report_id: str = Field(..., description="关联的报告ID")
    query: str = Field(..., description="用户查询内容")
    status: str = Field(default="processing", description="处理状态: processing, completed, failed")
    response: Optional[Dict[str, Any]] = Field(None, description="执行结果")
    execution_time: Optional[float] = Field(None, description="执行时间(秒)")
    error_message: Optional[str] = Field(None, description="错误信息")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class ReportAskQuestions(BaseStepRecord):
    """询问问题步骤记录"""
    message: Optional[str] = Field(None, description="你的想法")
    pass


class ReportPlan(BaseStepRecord):
    """报告计划步骤记录"""
    index: Optional[int] = Field(None, description="章节索引")
    pass


class ReportSerp(BaseStepRecord):
    """SERP查询步骤记录"""
    split_id: str = Field(..., description="关联的章节拆分ID")
    tasks: Optional[List[Dict[str, Any]]] = Field(None, description="返回的数据")
    plan: Optional[str] = Field(None, description="计划内容")
    current: Optional[str] = Field(None, description="当前处理部分")
    only_key: str = Field(..., description="一个批次的唯一标识")


class SerpTask(BaseModel):
    """SERP任务模型"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    serp_record_id: str = Field(..., description="关联的SERP记录ID")
    report_id: str = Field(..., description="关联的报告ID")
    split_id: str = Field(..., description="关联的章节拆分ID")
    query: str = Field(..., description="查询内容")
    research_goal: str = Field(..., description="研究目标")
    search_type: str = Field(default="online",description="检索类型 online：在线，knowledge：知识库")
    search_state: str = Field(default="unprocessed", description="检索状态 unprocessed：未开始，searchFailed：检索失败，searchCompleted：检索成功，completed: 成功，failed：失败")
    task_index: int = Field(..., description="任务在数组中的索引")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class ReportSearch(BaseStepRecord):
    """搜索步骤记录"""
    search_id: str = Field(..., description="搜索ID")
    max_results: Optional[int] = Field(None, description="最大结果数")
    include_images: Optional[bool] = Field(None, description="是否包含图片")
    results_count: Optional[int] = Field(None, description="实际结果数量")


class ReportSearchSummary(BaseStepRecord):
    """搜索总结步骤记录"""
    task_id: str = Field(..., description="任务ID")
    split_id: str = Field(..., description="章节拆分ID")

class finalReport(BaseModel):
    """finalReport模型"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    report_id: str = Field(..., description="关联的报告ID")
    split_id: str = Field(..., description="关联的章节拆分ID")
    chapter_index: Optional[int] = Field(None, description="章节索引")
    query: Optional[str] = Field(None, description="查询内容")
    current: str = Field(..., description="结果")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")