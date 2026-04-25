"""
Deep Research - Search Service
"""

import logging
import datetime
import asyncio
import aiohttp
from typing import List, Optional, Dict

from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from bson import ObjectId

from models.models import SearchResponse, TavilySearchRequest
from services.tavily_service import tavily_service
from services.report_service import report_service
from services.task_service import get_task_info
from utils.database import mongo_db, get_db
from services.mongo_api_service_manager import mongo_api_service_manager
from utils.exception_handler import ErrorCode
from utils.response_models import Result, BizError
from services.image_service import image_service
from utils.distributed_lock import create_async_lock
from services.rag_service import rag_service
from services.search_enhancement_service import enhanced_search_service

logger = logging.getLogger(__name__)

router = APIRouter()


class SearchRequestWithTaskId(BaseModel):
    """Search request model - uses only task_id, optional search parameters"""
    task_id: str
    max_results: Optional[int] = 10
    include_images: Optional[bool] = True
    include_domains: Optional[List[str]] = None
    exclude_domains: Optional[List[str]] = None
    use_rag: Optional[bool] = True


async def _store_search_results(
    task_id: str,
    report_id: str,
    plan_id: str,
    query: str,
    tavily_response,
    mongo_database
) -> int:
    """
    Store Tavily search results to MongoDB

    Args:
        task_id: Task ID
        report_id: Report ID
        plan_id: Plan ID
        query: Search query
        tavily_response: Tavily search response
        mongo_database: MongoDB database instance

    Returns:
        int: Number of stored records
    """
    try:
        collection = mongo_database.search_results
        stored_count = 0

        delete_result = collection.delete_many({"task_id": task_id})
        logger.info(f"Deleted {delete_result.deleted_count} search result records for task_id: {task_id}")

        max_index_doc = collection.find_one(
            {"report_id": report_id},
            sort=[("result_index", -1)]
        )

        start_index = 0 if max_index_doc is None else max_index_doc["result_index"] + 1
        logger.info(f"Start index for Report ID {report_id}: {start_index}")

        processed_images = []
        logger.info(f"Checking image data, tavily_response.images: {tavily_response.images}")
        if tavily_response.images:
            logger.info(f"Detected {len(tavily_response.images)} original images")
            first_img = tavily_response.images[0] if tavily_response.images else None
            if isinstance(first_img, dict):
                logger.info(f"Image format: dict format, first image: {first_img}")
                processed_images = await image_service.validate_and_upload_images(tavily_response.images)
            else:
                logger.info(f"Image format: object format")
                processed_images = await image_service.validate_and_upload_images([
                    {"url": img.url, "description": img.description or ""}
                    for img in tavily_response.images
                ])
            logger.info(f"Image processing completed, {len(processed_images)} images uploaded to OSS")
        else:
            logger.warning("tavily_response.images is empty or None, skipping image processing")

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
                "images": processed_images,
                "is_web": True,
                "status": "completed",
                "created_at": datetime.datetime.now(datetime.timezone.utc),
            }

            collection.insert_one(document)
            stored_count += 1

        logger.info(f"Successfully stored {stored_count} search results")
        return stored_count

    except Exception as e:
        logger.error(f"Failed to store search results: {str(e)}")
        raise


async def _store_search_results_with_images(
    task_id: str,
    report_id: str,
    plan_id: str,
    query: str,
    tavily_response,
    mongo_database,
    processed_images: List[Dict] = None,
    result_type: str = "online"
) -> int:
    """
    Store Tavily search results to MongoDB (with pre-processed images)

    Args:
        task_id: Task ID
        report_id: Report ID
        plan_id: Plan ID
        query: Search query
        tavily_response: Tavily search response
        mongo_database: MongoDB database instance
        processed_images: Pre-processed image list
        result_type: Result type ("online" or "knowledge")

    Returns:
        int: Number of stored records
    """
    try:
        collection = mongo_database.search_results
        stored_count = 0

        delete_result = collection.delete_many({"task_id": task_id})
        logger.info(f"Deleted {delete_result.deleted_count} search result records for task_id: {task_id}")

        max_index_doc = collection.find_one(
            {"report_id": report_id},
            sort=[("result_index", -1)]
        )

        start_index = 0 if max_index_doc is None else max_index_doc["result_index"] + 1
        logger.info(f"Start index for Report ID {report_id}: {start_index}")

        for idx, result in enumerate(tavily_response.results):
            document = {
                "task_id": task_id,
                "report_id": report_id,
                "plan_id": plan_id,
                "type": result_type,
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
                "images": processed_images if processed_images else [],
                "is_web": result_type == "online",
                "status": "completed",
                "created_at": datetime.datetime.now(datetime.timezone.utc),
            }

            collection.insert_one(document)
            stored_count += 1

        logger.info(f"Successfully stored {stored_count} search results")
        return stored_count

    except Exception as e:
        logger.error(f"Failed to store search results: {str(e)}")
        raise


async def _store_knowledge_results(
    task_id: str,
    report_id: str,
    plan_id: str,
    query: str,
    knowledge_chunks: list,
    mongo_database
) -> int:
    """
    Store knowledge base retrieval results to MongoDB

    Args:
        task_id: Task ID
        report_id: Report ID
        plan_id: Plan ID
        query: Search query
        knowledge_chunks: Knowledge base retrieval results
        mongo_database: MongoDB database instance

    Returns:
        int: Number of stored records
    """
    try:
        collection = mongo_database.search_results

        max_index_doc = collection.find_one(
            {"report_id": report_id},
            sort=[("result_index", -1)]
        )

        start_index = 0 if max_index_doc is None else max_index_doc["result_index"] + 1

        existing_kb_count = collection.count_documents({
            "task_id": task_id,
            "type": "knowledge"
        })
        start_index = start_index - existing_kb_count

        stored_count = 0

        for idx, chunk in enumerate(knowledge_chunks):
            document = {
                "task_id": task_id,
                "report_id": report_id,
                "plan_id": plan_id,
                "type": "knowledge",
                "query": query,
                "result_index": start_index + idx,
                "title": chunk.document_name or "Knowledge Base Document",
                "url": f"knowledge_base://{chunk.document_name}",
                "content": chunk.content,
                "raw_content": chunk.content,
                "score": chunk.score,
                "published_date": None,
                "tavily_answer": None,
                "response_time": 0,
                "follow_up_questions": [],
                "images": [],
                "is_web": False,
                "document_type": chunk.document_type,
                "status": "completed",
                "created_at": datetime.datetime.now(datetime.timezone.utc),
            }

            collection.insert_one(document)
            stored_count += 1

        logger.info(f"Successfully stored {stored_count} knowledge base results")
        return stored_count

    except Exception as e:
        logger.error(f"Failed to store knowledge base results: {str(e)}")
        raise


async def _store_response_data(
    task_id: str,
    response_data: dict,
    mongo_database
) -> ObjectId:
    """
    Store response data to MongoDB
    
    Args:
        task_id: Task ID
        response_data: Response data
        mongo_database: MongoDB database instance
        
    Returns:
        ObjectId: Inserted document ID
    """
    try:
        collection = mongo_database.report_search
        
        document = {
            "task_id": task_id,
            "query": response_data.get("query", ""),
            "response": response_data.get("response"),
            "images": response_data.get("images", []),
            "sources": response_data.get("sources", []),
            "created_at": datetime.datetime.now(datetime.timezone.utc)
        }
        
        result = collection.insert_one(document)
        logger.info(f"Successfully stored response data, ID: {result.inserted_id}")
        return result.inserted_id
        
    except Exception as e:
        logger.error(f"Failed to store response data: {str(e)}")
        raise


@router.post("/search/original", response_model=Result)
async def search(
    request: SearchRequestWithTaskId,
    db: Session = Depends(get_db)
):
    """
    Execute Tavily search + RAG knowledge base retrieval (hybrid search)

    Args:
        request: Search request
        db: Database session

    Returns:
        Result: Search results
    """
    lock_key = f"search_task_{request.task_id}"
    lock = create_async_lock(lock_key, timeout=30, retry_interval=0.1)

    if not await lock.acquire(blocking=True, timeout=5):
        logger.warning(f"Failed to acquire distributed lock, task_id: {request.task_id} is being processed by another request")
        raise HTTPException(status_code=429, detail="Task is being processed, please retry later")

    try:
        logger.info(f"Starting search execution, task_id: {request.task_id}, use_rag: {request.use_rag}")

        task_info = await get_task_info(request.task_id)
        if not task_info:
            raise BizError(
                code=ErrorCode.get_code(ErrorCode.TASK_NOT_EXIST),
                message=ErrorCode.get_message(ErrorCode.TASK_NOT_EXIST)
            )

        query = task_info.get("query", "")
        if not query:
            raise BizError(
                code=ErrorCode.get_code(ErrorCode.PARAM_ERROR),
                message="Query statement not included in task"
            )

        report_id = task_info["report_id"]
        plan_id = task_info["plan_id"]

        knowledge_chunks = []
        if request.use_rag:
            try:
                logger.info(f"Starting knowledge base retrieval, query: {query}")
                knowledge_chunks = await rag_service.retrieve(
                    query=query,
                    top_k=5,
                    score_threshold=0.5
                )
                logger.info(f"Knowledge base retrieval completed, got {len(knowledge_chunks)} results")
            except Exception as e:
                logger.warning(f"Knowledge base retrieval failed: {str(e)}, will continue with web search")
                knowledge_chunks = []

        tavily_request = TavilySearchRequest(
            query=query,
            search_depth="advanced" if request.max_results > 5 else "basic",
            include_answer=True,
            include_raw_content=request.include_images,
            max_results=request.max_results,
            include_images=request.include_images,
            include_image_descriptions=True,
            include_domains=request.include_domains,
            exclude_domains=request.exclude_domains
        )

        tavily_response = await tavily_service.search(tavily_request)

        stored_count = await _store_search_results(
            request.task_id,
            report_id,
            plan_id,
            query,
            tavily_response,
            mongo_db
        )

        if knowledge_chunks:
            kb_stored_count = await _store_knowledge_results(
                request.task_id,
                report_id,
                plan_id,
                query,
                knowledge_chunks,
                mongo_db
            )
            logger.info(f"Knowledge base results stored, {kb_stored_count} records")

        mongo_api_service_manager.update_serp_task_search_state(request.task_id, "searchCompleted")

        response_data = {
            "task_id": request.task_id,
            "query": query,
            "response_time": tavily_response.response_time,
            "images": [img.model_dump() if hasattr(img, 'model_dump') else {"url": img.url, "description": img.description}
                      for img in (tavily_response.images or [])],
            "sources": tavily_response.results or [],
            "knowledge_count": len(knowledge_chunks) if knowledge_chunks else 0,
            "web_count": len(tavily_response.results) if tavily_response.results else 0
        }

        await _store_response_data(request.task_id, response_data, mongo_db)

        logger.info(f"Search completed, task_id: {request.task_id}, web results: {stored_count}, knowledge results: {len(knowledge_chunks)}")
        return Result.success(response_data)

    except BizError as e:
        mongo_api_service_manager.update_serp_task_search_state(request.task_id, "searchFailed")
        logger.error(f"Business error: {e.message}")
        raise HTTPException(status_code=400, detail=e.message)

    except Exception as e:
        mongo_api_service_manager.update_serp_task_search_state(request.task_id, "searchFailed")
        logger.error(f"Search failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

    finally:
        try:
            await lock.release()
            logger.info(f"Released distributed lock successfully, task_id: {request.task_id}")
        except Exception as e:
            logger.error(f"Failed to release distributed lock: {str(e)}")


@router.get("/detail/{task_id}", response_model=Result)
async def get_detail(
    task_id: str
):
    """
    Get details by task ID (returns latest if multiple records)
    """
    search_summary = mongo_api_service_manager.get_search_summary(task_id)
    sources = mongo_api_service_manager.get_results_task_id(task_id)

    images = []
    for source in sources:
        source["raw_content"] = ""
        source["content"] = ""
        source_images = source.get("images", [])
        logger.info(f"Source images: {source_images}")
        images.extend(source_images)

    logger.info(f"Total images collected: {images}")

    response_data = {
        "task_id": task_id,
        "images": images,
        "sources": sources
    }

    if search_summary and "response" in search_summary:
        response_data_val = search_summary["response"]
        if isinstance(response_data_val, dict) and "choices" in response_data_val:
            choices = response_data_val["choices"]
            if isinstance(choices, list) and len(choices) > 0:
                choice = choices[0]
                if isinstance(choice, dict) and "message" in choice:
                    message = choice["message"]
                    if isinstance(message, dict) and "content" in message:
                        response_data["content"] = message["content"]

    return Result.success(response_data)


class EnhancedSearchRequest(BaseModel):
    """Enhanced search request model"""
    task_id: str
    use_expansion: bool = True
    use_rerank: bool = True
    use_intent: bool = True
    max_results: int = 10
    include_images: bool = True
    relevance_threshold: float = 0.3


@router.post("/search", response_model=Result)
async def enhanced_search(
    request: EnhancedSearchRequest,
    db: Session = Depends(get_db)
):
    """
    Execute enhanced search - Integration of Query Expansion + Re-ranking + RRF Fusion

    Workflow:
    1. Query Expansion - Expand single query into multiple sub-queries
    2. Parallel Search - Execute search for each sub-query
    3. RRF Fusion - Merge multiple search results
    4. Re-ranking - Re-rank results using LLM

    Expected Effects:
    - Precision improved by 20-40%
    - NDCG improved by 15-30%

    Args:
        request: Enhanced search request
        db: Database session

    Returns:
        Result: Enhanced search results
    """
    lock_key = f"enhanced_search_task_{request.task_id}"
    lock = create_async_lock(lock_key, timeout=30, retry_interval=0.1)

    if not await lock.acquire(blocking=True, timeout=5):
        raise HTTPException(status_code=429, detail="Task is being processed, please retry later")

    try:
        logger.info(f"Starting enhanced search execution, task_id: {request.task_id}, "
                   f"expansion={request.use_expansion}, rerank={request.use_rerank}")

        task_info = await get_task_info(request.task_id)
        if not task_info:
            raise BizError(
                code=ErrorCode.get_code(ErrorCode.TASK_NOT_EXIST),
                message=ErrorCode.get_message(ErrorCode.TASK_NOT_EXIST)
            )

        query = task_info.get("query", "")
        research_goal = task_info.get("research_goal", "")
        report_id = task_info["report_id"]
        plan_id = task_info["plan_id"]

        if not query:
            raise BizError(
                code=ErrorCode.get_code(ErrorCode.PARAM_ERROR),
                message="Query statement not included in task"
            )

        knowledge_chunks = []
        try:
            logger.info(f"Starting knowledge base retrieval, query: {query}")
            knowledge_chunks = await rag_service.retrieve(
                query=query,
                top_k=5,
                score_threshold=0.5
            )
            logger.info(f"Knowledge base retrieval completed, got {len(knowledge_chunks)} results")
        except Exception as e:
            logger.warning(f"Knowledge base retrieval failed: {str(e)}, will continue with web search")
            knowledge_chunks = []

        enhanced_results, enhanced_images = await enhanced_search_service.enhanced_search(
            query=query,
            research_goal=research_goal,
            use_expansion=request.use_expansion,
            use_rerank=request.use_rerank,
            use_intent=request.use_intent,
            max_results=request.max_results,
            include_images=request.include_images,
            relevance_threshold=request.relevance_threshold
        )

        logger.info(f"Enhanced search completed, results: {len(enhanced_results)}, images: {len(enhanced_images) if enhanced_images else 0}")

        tavily_response = type('obj', (object,), {
            'results': [
                {
                    'title': r.title,
                    'url': r.url,
                    'content': r.content,
                    'raw_content': r.raw_content,
                    'score': r.score
                }
                for r in enhanced_results
            ],
            'images': enhanced_images,
            'answer': None,
            'follow_up_questions': [],
            'response_time': 0
        })()

        stored_count = await _store_search_results(
            request.task_id,
            report_id,
            plan_id,
            query,
            tavily_response,
            mongo_db
        )

        if knowledge_chunks:
            kb_stored_count = await _store_knowledge_results(
                request.task_id,
                report_id,
                plan_id,
                query,
                knowledge_chunks,
                mongo_db
            )
            logger.info(f"Knowledge base results stored, {kb_stored_count} records")

        mongo_api_service_manager.update_serp_task_search_state(request.task_id, "searchCompleted")

        response_data = {
            "task_id": request.task_id,
            "query": query,
            "response_time": tavily_response.response_time,
            "images": tavily_response.images,
            "sources": tavily_response.results or [],
            "knowledge_count": len(knowledge_chunks) if knowledge_chunks else 0,
            "web_count": len(tavily_response.results) if tavily_response.results else 0
        }

        await _store_response_data(request.task_id, response_data, mongo_db)

        logger.info(f"Enhanced search completed, task_id: {request.task_id}, "
                   f"web results: {stored_count}, knowledge results: {len(knowledge_chunks)}")

        return Result.success(response_data)

    except BizError as e:
        mongo_api_service_manager.update_serp_task_search_state(request.task_id, "searchFailed")
        raise HTTPException(status_code=400, detail=e.message)

    except Exception as e:
        logger.error(f"Enhanced search failed: {str(e)}")
        mongo_api_service_manager.update_serp_task_search_state(request.task_id, "searchFailed")
        raise HTTPException(status_code=500, detail=f"Enhanced search failed: {str(e)}")

    finally:
        try:
            await lock.release()
        except Exception as e:
            logger.error(f"Failed to release distributed lock: {str(e)}")
