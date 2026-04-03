"""
报告评估 API 路由
"""

import logging
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

from bson import ObjectId
from services.report_evaluation_service import report_evaluation_service

logger = logging.getLogger(__name__)

router = APIRouter()


class EvaluateRequest(BaseModel):
    """评估请求模型"""
    report_id: str


class EvaluateResponse(BaseModel):
    """评估响应模型"""
    success: bool
    message: str
    report_id: str
    evaluation_id: str = ""


@router.post("/evaluate/{report_id}", response_model=EvaluateResponse)
async def evaluate_report(report_id: str) -> Dict[str, Any]:
    """
    触发报告评估

    Args:
        report_id: 报告ID

    Returns:
        评估结果摘要
    """
    try:
        logger.info(f"收到报告评估请求: {report_id}")

        # 执行完整评估流程
        eval_result = await report_evaluation_service.run_evaluation(report_id)

        return {
            "success": True,
            "message": "评估完成",
            "report_id": report_id,
            "evaluation_id": f"eval_{report_id}",
            "context_precision": eval_result.get("context_precision", 0.0),
            "content_quality_score": eval_result.get("content_quality_score", 0),
            "total_chapters": eval_result.get("total_chapters", 0),
            "execution_time_seconds": eval_result.get("execution_time_seconds", 0)
        }

    except Exception as e:
        logger.error(f"报告评估失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"评估失败: {str(e)}")


@router.get("/evaluation/{report_id}")
async def get_evaluation_result(report_id: str) -> Dict[str, Any]:
    """
    获取报告已有的评估结果

    Args:
        report_id: 报告ID

    Returns:
        评估结果
    """
    try:
        from utils.database import mongo_db

        # 从 reports 集合获取评估结果
        report = mongo_db["reports"].find_one({"_id": ObjectId(report_id)})

        if not report:
            raise HTTPException(status_code=404, detail="报告不存在")

        evaluations = report.get("evaluations", None)

        if not evaluations:
            raise HTTPException(status_code=404, detail="该报告尚未完成评估")

        return {
            "success": True,
            "report_id": report_id,
            "evaluations": evaluations
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取评估结果失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取评估结果失败: {str(e)}")
