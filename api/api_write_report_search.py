"""
深度研究 - 搜索服务
"""

import logging
import datetime
import asyncio
import aiohttp
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends  # type: ignore
from sqlalchemy.orm import Session
from bson import ObjectId

from models.models import SearchRequest, SearchResponse, TavilySearchRequest
from services.tavily_service import tavily_service
from services.report_service import report_service
from services.task_service import get_task_info
from utils.database import mongo_db, get_db
from services.mongo_api_service_manager import mongo_api_service_manager
from utils.exception_handler import ErrorCode
from utils.response_models import Result, BizError
from services.image_service import image_service

logger = logging.getLogger(__name__)

router = APIRouter()


class SearchRequestWithTaskId(SearchRequest):
    """搜索请求模型 - 使用task_id"""
    task_id: str


async def _store_search_results(
    task_id: str,
    report_id: str,  # 添加report_id参数
    plan_id: str,  # 添加plan_id参数
    query: str,
    tavily_response,
    mongo_database
) -> int:
    """
    将Tavily搜索结果存储到MongoDB
    
    Args:
        task_id: 任务ID
        report_id: 报告ID
        plan_id: 计划ID
        query: 搜索查询
        tavily_response: Tavily搜索响应
        mongo_database: MongoDB数据库实例
        
    Returns:
        int: 存储的记录数量
    """
    try:
        collection = mongo_database.search_results
        stored_count = 0
        
        # 根据task_id删除search_results表中的对应数据
        delete_result = collection.delete_many({"task_id": task_id})
        logger.info(f"已删除task_id为 {task_id} 的 {delete_result.deleted_count} 条搜索结果记录")
        
        # 查询同一report_id的最大result_index，实现累加
        max_index_doc = collection.find_one(
            {"report_id": report_id},
            sort=[("result_index", -1)]  # 降序排列，获取最大值
        )
        
        # 确定起始索引
        start_index = 0 if max_index_doc is None else max_index_doc["result_index"] + 1
        logger.info(f"Report ID {report_id} 的起始索引: {start_index}")
        
        # 处理图片，上传到OSS
        processed_images = []
        if tavily_response.images:
            logger.info(f"开始处理 {len(tavily_response.images)} 张图片")
            processed_images = await image_service.validate_and_upload_images([
                {"url": img.url, "description": img.description or ""} 
                for img in tavily_response.images
            ])
            logger.info(f"图片处理完成，成功上传 {len(processed_images)} 张图片到OSS")
        
        # 为每个搜索结果创建一条MongoDB记录
        for idx, result in enumerate(tavily_response.results):
            document = {
                "task_id": task_id,
                "report_id": report_id,
                "plan_id": plan_id,
                "type": "online",
                "query": query,
                "result_index": start_index + idx,
                "title": result.get("title", ""),
                "url": result.get("url", ""),
                "content": result.get("content", ""),
                "raw_content": result.get("raw_content", ""),
                "score": result.get("score"),
                "published_date": result.get("published_date"),
                "tavily_answer": tavily_response.answer,
                "response_time": tavily_response.response_time,
                "follow_up_questions": tavily_response.follow_up_questions,
                "images": processed_images,  # 使用处理后的图片
                "is_web": True,
                "status": "完成",
                "created_at": datetime.datetime.now(datetime.timezone.utc),
            }
            
            # 插入文档
            collection.insert_one(document)
            stored_count += 1
            
        logger.info(f"成功存储 {stored_count} 条搜索结果")
        return stored_count
        
    except Exception as e:
        logger.error(f"存储搜索结果失败: {str(e)}")
        raise


async def _store_response_data(
    task_id: str,
    response_data: dict,
    mongo_database
) -> ObjectId:
    """
    存储响应数据到MongoDB
    
    Args:
        task_id: 任务ID
        response_data: 响应数据
        mongo_database: MongoDB数据库实例
        
    Returns:
        ObjectId: 插入文档的ID
    """
    try:
        collection = mongo_database.report_search
        
        # 构造文档
        document = {
            "task_id": task_id,
            "query": response_data.get("query", ""),
            "response": response_data.get("response"),
            "images": response_data.get("images", []),
            "sources": response_data.get("sources", []),
            "created_at": datetime.datetime.now(datetime.timezone.utc)
        }
        
        # 插入文档
        result = collection.insert_one(document)
        logger.info(f"成功存储响应数据，ID: {result.inserted_id}")
        return result.inserted_id
        
    except Exception as e:
        logger.error(f"存储响应数据失败: {str(e)}")
        raise


@router.post("/search", response_model=Result)
async def search(
    request: SearchRequestWithTaskId,
    db: Session = Depends(get_db)
):
    """
    执行Tavily搜索
    
    Args:
        request: 搜索请求
        db: 数据库会话
        
    Returns:
        Result: 搜索结果
    """
    try:
        logger.info(f"开始执行搜索，查询: {request.query}, task_id: {request.task_id}")
        
        # 获取任务信息
        task_info = get_task_info(request.task_id)
        if not task_info:
            raise BizError(
                code=ErrorCode.get_code(ErrorCode.TASK_NOT_EXIST),
                message=ErrorCode.get_message(ErrorCode.TASK_NOT_EXIST)
            )
        
        report_id = task_info["report_id"]
        plan_id = task_info["plan_id"]
        
        # 构造Tavily搜索请求
        tavily_request = TavilySearchRequest(
            query=request.query,
            search_depth="advanced" if request.max_results > 5 else "basic",
            include_answer=True,
            include_raw_content=request.include_images,
            max_results=request.max_results,
            include_images=request.include_images,
            include_image_descriptions=True
        )
        
        # 执行搜索
        tavily_response = await tavily_service.search(tavily_request)
        
        # 存储搜索结果到MongoDB
        stored_count = await _store_search_results(
            request.task_id,
            report_id,
            plan_id,
            request.query,
            tavily_response,
            mongo_db
        )
        
        # 更新serp_task状态为searchCompleted
        mongo_api_service_manager.update_serp_task_search_state(request.task_id, "searchCompleted")
        
        # 构造响应数据
        response_data = {
            "task_id": request.task_id,
            "query": request.query,
            "response_time": tavily_response.response_time,
            "images": tavily_response.images or [],
            "sources": tavily_response.results,
        }
        
        # 存储响应数据
        await _store_response_data(request.task_id, response_data, mongo_db)
        
        logger.info(f"搜索完成，task_id: {request.task_id}, 存储记录数: {stored_count}")
        return Result.success(response_data)
        
    except BizError as e:
        # 更新serp_task状态为searchFailed
        mongo_api_service_manager.update_serp_task_search_state(request.task_id, "searchFailed")
        logger.error(f"业务错误: {e.message}")
        raise HTTPException(status_code=400, detail=e.message)
        
    except Exception as e:
        # 更新serp_task状态为searchFailed
        mongo_api_service_manager.update_serp_task_search_state(request.task_id, "searchFailed")
        logger.error(f"搜索失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"搜索失败: {str(e)}")


@router.get("/detail/{task_id}", response_model=Result)
async def get_detail(
    task_id: str  # 改为字符串类型，支持ObjectId
):
    """
    根据任务ID获取详细信息（如有多条记录返回最新的）
    """
    search_summary = mongo_api_service_manager.get_search_summary(task_id)
    sources = mongo_api_service_manager.get_results_task_id(task_id)

    # 提取所有sources中的images，合并为一维数组
    images = []
    for source in sources:
        source["raw_content"] = ""
        source["content"] = ""
        source_images = source.get("images", [])
        logger.info(f"Source images: {source_images}")
        images.extend(source_images)

    logger.info(f"Total images collected: {images}")

    # 构建返回数据，保持与search接口相同的格式
    response_data = {
        "task_id": task_id,
        "images": images,
        "sources": sources
    }

    # 添加判断：如果search_summary不为空
    if search_summary:
        # 检查search_summary中是否有response字段
        if "response" in search_summary:
            # 将search_summary中的response值设置到response_data中
            response_data["content"] = search_summary["response"]["choices"][0]["message"]["content"]

    return Result.success(response_data)
    