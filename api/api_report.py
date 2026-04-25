"""
Report Management API Router Module
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Depends, Request
from models.mongo_models import (
    ReportCreateRequest, ReportResponse, ReportListResponse, ReportLockRequest
)
from services.report_service import report_service
from utils.exception_handler import ErrorCode
from utils.response_models import Result, BizError


logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/create", response_model=Result)
async def create_report(request: Request):
    """
    Create a new report
        
    Returns:
        dict: Response containing report_id
    """
    user_id = "default_user"
    tenant_id = "1"

    logger.info(f"user_id: {user_id}, tenant_id: {tenant_id}")
    report_id = report_service.create_report(user_id, tenant_id)

    return Result.success(report_id, "Report created successfully")

@router.get("/detail/{report_id}", response_model=Result)
async def get_report_detail(report_id: str):
    """
    Get report details
    
    Args:
        report_id: Report ID
        
    Returns:
        ReportResponse: Report details
    """
    try:
        report = report_service.get_report_response(report_id)
        if not report:
            raise BizError(code=ErrorCode.get_code(ErrorCode.REPORT_NOT_EXIST), message=ErrorCode.get_message(ErrorCode.REPORT_NOT_EXIST))
        return Result.success(report)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get report details: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get report details: {str(e)}")


@router.get("/list", response_model=Result)
async def list_reports(
    page: int = Query(1, ge=1, description="Page number, starting from 1"),
    page_size: int = Query(20, ge=1, le=100, description="Page size, maximum 100"),
    status: Optional[str] = Query(None, description="Status filter")
):
    """
    Paginated report list query
    
    Args:
        page: Page number
        page_size: Page size
        status: Status filter
        
    Returns:
        ReportListResponse: Paginated report list
    """
    try:
        data= report_service.list_reports(
            page=page,
            page_size=page_size,
            status=status
        )
        return Result.success(data)
        
    except Exception as e:
        logger.error(f"Failed to query report list: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to query report list: {str(e)}")


@router.get("/history", response_model=Result)
async def get_reports_history(
    page: int = Query(1, ge=1, description="Page number, starting from 1"),
    page_size: int = Query(10, ge=1, le=50, description="Page size, maximum 50")
):
    """
    Get report history (sorted by creation time descending)
    
    Args:
        page: Page number
        page_size: Page size
        
    Returns:
        ReportListResponse: History list
    """
    try:
        user_id = "default_user"
        tenant_id = "1"

        logger.info(f"user_id: {user_id}, tenant_id: {tenant_id}, page: {page}, page_size: {page_size}")
        data= report_service.list_reports(
            user_id=user_id,
            tenant_id=tenant_id,
            page=page,
            page_size=page_size
        )
        return Result.success(data)
        
    except Exception as e:
        logger.error(f"Failed to get report history: {e}")
        raise ValueError(f"Failed to get report history: {str(e)}")


@router.get("/progress/{report_id}", response_model=Result)
async def get_report_progress(report_id: str):
    """
    Get report execution progress
    
    Args:
        report_id: Report ID
        
    Returns:
        dict: Progress information
    """
    try:
        report = report_service.get_report(report_id)
        if not report:
            raise BizError(code=ErrorCode.get_code(ErrorCode.REPORT_NOT_EXIST),
                           message=ErrorCode.get_message(ErrorCode.REPORT_NOT_EXIST))
        data= {
            "report_id": report_id,
            "status": report.status,
            "progress_percentage": report.progress_percentage,
            "completed_steps": report.completed_steps,
            "total_steps": report.total_steps,
            "steps": {
                "ask_questions": {
                    "status": report.steps.ask_questions.status,
                    "completed": report.steps.ask_questions.completed
                },
                "plan": {
                    "status": report.steps.plan.status,
                    "completed": report.steps.plan.completed
                },
                "serp": {
                    "status": report.steps.serp.status,
                    "completed": report.steps.serp.completed
                },
                "search": {
                    "status": report.steps.search.status,
                    "completed": report.steps.search.completed
                },
                "search_summary": {
                    "status": report.steps.search_summary.status,
                    "completed": report.steps.search_summary.completed
                }
            }
        }
        return Result.success(data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get report progress: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get report progress: {str(e)}")


@router.get("/step-result/{report_id}/{step_name}", response_model=Result)
async def get_step_result(report_id: str, step_name: str):
    """
    Get execution result for specified step

    Args:
        report_id: Report ID
        step_name: Step name

    Returns:
        dict: Step result
    """
    try:
        report = report_service.get_report(report_id)
        if not report:
            raise BizError(code=ErrorCode.get_code(ErrorCode.REPORT_NOT_EXIST),
                           message=ErrorCode.get_message(ErrorCode.REPORT_NOT_EXIST))

        step_mapping = {
            "ask_questions": report.steps.ask_questions,
            "plan": report.steps.plan,
            "serp": report.steps.serp,
            "search": report.steps.search,
            "search_summary": report.steps.search_summary
        }

        if step_name not in step_mapping:
            raise BizError(code=ErrorCode.get_code(ErrorCode.REPORT_INVALID_STEPS),
                           message=ErrorCode.get_message(ErrorCode.REPORT_INVALID_STEPS))

        step = step_mapping[step_name]

        data= {
            "report_id": report_id,
            "step_name": step_name,
            "status": step.status,
            "completed": step.completed,
            "started_at": step.started_at,
            "completed_at": step.completed_at,
            "execution_time": step.execution_time,
            "result": step.result,
            "error_message": step.error_message
        }
        return Result.success(data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get step result: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get step result: {str(e)}")


@router.get("/token-stats/{report_id}", response_model=Result)
async def get_token_stats(report_id: str):
    """
    Get token statistics for report

    Args:
        report_id: Report ID

    Returns:
        dict: Token statistics
    """
    try:
        from bson import ObjectId
        from utils.database import mongo_db

        collections_to_check = [
            "report_ask_questions",
            "report_plan",
            "report_serp",
            "report_search",
            "report_search_summary"
        ]

        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_tokens = 0
        step_stats = []

        for collection_name in collections_to_check:
            collection = mongo_db[collection_name]
            records = list(collection.find({"report_id": report_id}))

            for record in records:
                prompt_tokens = record.get("prompt_tokens") or 0
                completion_tokens = record.get("completion_tokens") or 0
                tokens = record.get("total_tokens") or 0

                total_prompt_tokens += prompt_tokens
                total_completion_tokens += completion_tokens
                total_tokens += tokens

                if prompt_tokens > 0 or completion_tokens > 0 or tokens > 0:
                    step_stats.append({
                        "collection": collection_name,
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": tokens,
                        "execution_time": record.get("execution_time")
                    })

        data = {
            "report_id": report_id,
            "total_prompt_tokens": total_prompt_tokens,
            "total_completion_tokens": total_completion_tokens,
            "total_tokens": total_tokens,
            "step_stats": step_stats
        }
        return Result.success(data)

    except Exception as e:
        logger.error(f"Failed to get token statistics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get token statistics: {str(e)}")


@router.post("/lock", response_model=Result)
async def lock_report(request: ReportLockRequest):
    """
    Lock or unlock report
    
    Args:
        request: Request containing report_id and locked status
        
    Returns:
        dict: Operation result
    """
    try:
        report = report_service.get_report(request.report_id)
        if not report:
            raise BizError(code=ErrorCode.get_code(ErrorCode.REPORT_NOT_EXIST),
                           message=ErrorCode.get_message(ErrorCode.REPORT_NOT_EXIST))

        success = report_service.lock_report(request.report_id, request.locked)
        
        if success:
            action = "Lock" if request.locked else "Unlock"
            return Result.success(True, f"Report {action.lower()}ed successfully")
        else:
            action = "lock" if request.locked else "unlock"
            raise BizError(code=ErrorCode.get_code(ErrorCode.REPORT_UPDATE_FAILED),
                           message=f"Failed to {action} report")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to lock/unlock report: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to lock/unlock report: {str(e)}")


@router.delete("/{report_id}", response_model=Result)
async def delete_report(report_id: str):
    """
    Delete report
    
    Args:
        report_id: Report ID
        
    Returns:
        dict: Delete result
    """
    try:
        report = report_service.get_report(report_id)
        if not report:
            raise BizError(code=ErrorCode.get_code(ErrorCode.REPORT_NOT_EXIST),
                           message=ErrorCode.get_message(ErrorCode.REPORT_NOT_EXIST))

        from bson import ObjectId
        from utils.database import mongo_db
        result = mongo_db.reports.delete_one({"_id": ObjectId(report_id)})
        
        if result.deleted_count > 0:
            return Result.success(True, "Report deleted successfully")
        else:
            raise BizError(code=ErrorCode.get_code(ErrorCode.REPORT_DELETE_FAILED),
                           message=ErrorCode.get_message(ErrorCode.REPORT_DELETE_FAILED))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete report: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete report: {str(e)}")