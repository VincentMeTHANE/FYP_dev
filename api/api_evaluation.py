"""
Report Evaluation API Router
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
    """Evaluation request model"""
    report_id: str


class EvaluateResponse(BaseModel):
    """Evaluation response model"""
    success: bool
    message: str
    report_id: str
    evaluation_id: str = ""


@router.post("/evaluate/{report_id}", response_model=EvaluateResponse)
async def evaluate_report(report_id: str) -> Dict[str, Any]:
    """
    Trigger report evaluation

    Args:
        report_id: Report ID

    Returns:
        Evaluation result summary
    """
    try:
        logger.info(f"Received report evaluation request: {report_id}")

        eval_result = await report_evaluation_service.run_evaluation(report_id)

        return {
            "success": True,
            "message": "Evaluation completed",
            "report_id": report_id,
            "evaluation_id": f"eval_{report_id}",
            "context_precision": eval_result.get("context_precision", 0.0),
            "content_quality_score": eval_result.get("content_quality_score", 0),
            "total_chapters": eval_result.get("total_chapters", 0),
            "execution_time_seconds": eval_result.get("execution_time_seconds", 0)
        }

    except Exception as e:
        logger.error(f"Report evaluation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {str(e)}")


@router.get("/evaluation/{report_id}")
async def get_evaluation_result(report_id: str) -> Dict[str, Any]:
    """
    Get existing evaluation results for a report

    Args:
        report_id: Report ID

    Returns:
        Evaluation results
    """
    try:
        from utils.database import mongo_db

        report = mongo_db["reports"].find_one({"_id": ObjectId(report_id)})

        if not report:
            raise HTTPException(status_code=404, detail="Report does not exist")

        evaluations = report.get("evaluations", None)

        if not evaluations:
            raise HTTPException(status_code=404, detail="This report has not been evaluated yet")

        return {
            "success": True,
            "report_id": report_id,
            "evaluations": evaluations
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get evaluation results: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get evaluation results: {str(e)}")
