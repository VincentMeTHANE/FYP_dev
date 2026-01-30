"""
报告管理API路由模块
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query,Depends,Request
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
    创建新报告
        
    Returns:
        dict: 包含报告ID的响应
    """
    # 移除认证，使用默认用户和租户ID
    user_id = "default_user"
    tenant_id = "1"

    logger.info(f"user_id: {user_id}, tenant_id: {tenant_id}")
    report_id = report_service.create_report(user_id, tenant_id)

    return Result.success(report_id,"报告创建成功")

@router.get("/detail/{report_id}", response_model=Result)
async def get_report_detail(report_id: str):
    """
    获取报告详情
    
    Args:
        report_id: 报告ID
        
    Returns:
        ReportResponse: 报告详情
    """
    try:
        report = report_service.get_report_response(report_id)
        if not report:
            raise BizError(code=ErrorCode.get_code(ErrorCode.REPORT_NOT_EXIST), message=ErrorCode.get_message(ErrorCode.REPORT_NOT_EXIST))
        return Result.success(report)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取报告详情失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取报告详情失败: {str(e)}")


@router.get("/list", response_model=Result)
async def list_reports(
    page: int = Query(1, ge=1, description="页码，从1开始"),
    page_size: int = Query(20, ge=1, le=100, description="每页大小，最大100"),
    status: Optional[str] = Query(None, description="状态过滤")
):
    """
    分页查询报告列表
    
    Args:
        page: 页码
        page_size: 每页大小
        status: 状态过滤
        
    Returns:
        ReportListResponse: 分页报告列表
    """
    try:
        data= report_service.list_reports(
            page=page,
            page_size=page_size,
            status=status
        )
        return Result.success(data)
        
    except Exception as e:
        logger.error(f"查询报告列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"查询报告列表失败: {str(e)}")


@router.get("/history", response_model=Result)
async def get_reports_history(
    page: int = Query(1, ge=1, description="页码，从1开始"),
    page_size: int = Query(10, ge=1, le=50, description="每页大小，最大50")
):
    """
    获取报告历史记录（按创建时间倒序）
    
    Args:
        page: 页码
        page_size: 每页大小
        
    Returns:
        ReportListResponse: 历史记录列表
    """
    try:
        # 移除认证，使用默认用户和租户ID
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
        logger.error(f"获取报告历史失败: {e}")
        raise ValueError(f"获取报告历史失败: {str(e)}")


@router.get("/progress/{report_id}", response_model=Result)
async def get_report_progress(report_id: str):
    """
    获取报告执行进度
    
    Args:
        report_id: 报告ID
        
    Returns:
        dict: 进度信息
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
        logger.error(f"获取报告进度失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取报告进度失败: {str(e)}")


@router.get("/step-result/{report_id}/{step_name}", response_model=Result)
async def get_step_result(report_id: str, step_name: str):
    """
    获取指定步骤的执行结果
    
    Args:
        report_id: 报告ID
        step_name: 步骤名称
        
    Returns:
        dict: 步骤结果
    """
    try:
        report = report_service.get_report(report_id)
        if not report:
            raise BizError(code=ErrorCode.get_code(ErrorCode.REPORT_NOT_EXIST),
                           message=ErrorCode.get_message(ErrorCode.REPORT_NOT_EXIST))

        # 获取指定步骤
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
        logger.error(f"获取步骤结果失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取步骤结果失败: {str(e)}")


@router.post("/lock", response_model=Result)
async def lock_report(request: ReportLockRequest):
    """
    锁定或解锁报告
    
    Args:
        request: 包含report_id和locked状态的请求
        
    Returns:
        dict: 操作结果
    """
    try:
        # 检查报告是否存在
        report = report_service.get_report(request.report_id)
        if not report:
            raise BizError(code=ErrorCode.get_code(ErrorCode.REPORT_NOT_EXIST),
                           message=ErrorCode.get_message(ErrorCode.REPORT_NOT_EXIST))

        # 更新锁定状态
        success = report_service.lock_report(request.report_id, request.locked)
        
        if success:
            action = "锁定" if request.locked else "解锁"
            return Result.success(True, f"报告{action}成功")
        else:
            action = "锁定" if request.locked else "解锁"
            raise BizError(code=ErrorCode.get_code(ErrorCode.REPORT_UPDATE_FAILED),
                           message=f"报告{action}失败")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"锁定/解锁报告失败: {e}")
        raise HTTPException(status_code=500, detail=f"锁定/解锁报告失败: {str(e)}")


@router.delete("/{report_id}", response_model=Result)
async def delete_report(report_id: str):
    """
    删除报告
    
    Args:
        report_id: 报告ID
        
    Returns:
        dict: 删除结果
    """
    try:
        # 检查报告是否存在
        report = report_service.get_report(report_id)
        if not report:
            raise BizError(code=ErrorCode.get_code(ErrorCode.REPORT_NOT_EXIST),
                           message=ErrorCode.get_message(ErrorCode.REPORT_NOT_EXIST))

        # 删除报告
        from bson import ObjectId
        from utils.database import mongo_db
        result = mongo_db.reports.delete_one({"_id": ObjectId(report_id)})
        
        if result.deleted_count > 0:
            return Result.success(True, "报告删除成功")
        else:
            raise BizError(code=ErrorCode.get_code(ErrorCode.REPORT_DELETE_FAILED),
                           message=ErrorCode.get_message(ErrorCode.REPORT_DELETE_FAILED))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除报告失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除报告失败: {str(e)}")