#!/usr/bin/env python3
"""
任务服务模块 - 提供任务相关的查询功能
"""

import logging
from typing import Dict, Optional
from fastapi import HTTPException  # type: ignore
from bson import ObjectId
from utils.database import mongo_db

logger = logging.getLogger(__name__)


async def get_task_info(task_id: str) -> Dict[str, str]:
    """
    通过task_id从MongoDB查询任务信息
    
    Args:
        task_id: 任务ID
        
    Returns:
        Dict: 包含query、research_goal、report_id和plan_id的字典
        
    Raises:
        HTTPException: 当task_id不存在时
    """
    try:
        # 查询serp_task集合
        serp_task_collection = mongo_db["serp_task"]
        task_doc = serp_task_collection.find_one({"_id": ObjectId(task_id)})
        
        if not task_doc:
            raise HTTPException(status_code=404, detail=f"指定的task_id不存在: {task_id}")
        
        return {
            "query": task_doc.get("query", ""),
            "research_goal": task_doc.get("research_goal", ""),
            "report_id": task_doc.get("report_id", ""),
            "plan_id": task_doc.get("plan_id", ""),
            "split_id": task_doc.get("split_id", ""),
            "task_id": task_id,
            "task_index": task_doc.get("task_index", "")
        }
    except Exception as e:
        logger.error(f"查询任务信息失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"查询任务信息失败: {str(e)}") 