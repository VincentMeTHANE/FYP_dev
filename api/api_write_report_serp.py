"""
Deep Research - SERP Query Generation
"""

import logging, json ,re
import datetime
import asyncio
import uuid
from typing import Any,List, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from bson import ObjectId
from utils.database import mongo_db
from services.llm_service import llm_service
from services.mongo_api_service_manager import mongo_api_service_manager
from services.report_service import report_service
from services.step_record_service import step_record_service
from fastapi.responses import StreamingResponse
from utils.exception_handler import ErrorCode
from utils.response_models import Result, BizError


logger = logging.getLogger(__name__)

router = APIRouter()


class SerpRequest(BaseModel):
    """SERP request model"""
    split_id: str
    report_id: str


@router.post("/stream")
async def chat_stream(
    dto: SerpRequest
):
    """Generate SERP query list - stream mode, requires valid split_id and plan_id"""
    start_time = datetime.datetime.now()
    
    try:
        if not dto.split_id or not dto.report_id:
            raise BizError(code=ErrorCode.get_code(ErrorCode.SERP_NEED_EFFECTIVE),
                           message=ErrorCode.get_message(ErrorCode.SERP_NEED_EFFECTIVE))

        split_collection = mongo_db["report_plan_split"]
        plan_collection = mongo_db["report_plan"]
        
        split_doc = split_collection.find_one({"_id": ObjectId(dto.split_id)})
        if not split_doc:
            raise BizError(code=ErrorCode.get_code(ErrorCode.SERP_CHAPTER_NOT_EXIST),
                           message=ErrorCode.get_message(ErrorCode.SERP_CHAPTER_NOT_EXIST))

        plan_records = step_record_service.get_records_by_report_id(dto.report_id, "plan")
        if not plan_records or not plan_records.get("plan"):
            raise BizError(code=ErrorCode.get_code(ErrorCode.PLAN_NOT_EXIST),
                           message=ErrorCode.get_message(ErrorCode.PLAN_NOT_EXIST))

        plan_doc = plan_records["plan"][0] if plan_records["plan"] else None
        if not plan_doc:
            raise BizError(code=ErrorCode.get_code(ErrorCode.PLAN_NOT_EXIST),
                           message=ErrorCode.get_message(ErrorCode.PLAN_NOT_EXIST))

        chapter_content = split_doc.get("response", {}).get("content", [])[0]
        plan_content = plan_doc.get("response", {}).get("plan", "")
        
        query_text = f"Based on plan: {plan_content}, section: {chapter_content}"
        
        report_id = split_doc.get("report_id")
        if not report_id:
            raise BizError(code=ErrorCode.get_code(ErrorCode.SERP_LACK_REPORT_ID),
                           message=ErrorCode.get_message(ErrorCode.SERP_LACK_REPORT_ID))
        report_info = report_service.get_report_response(report_id)
        title = report_info.title
        
        serp_collection = mongo_db["report_serp"]
        serp_task_collection = mongo_db["serp_task"]
        
        delete_result = serp_collection.delete_many({"split_id": dto.split_id})
        if delete_result.deleted_count > 0:
            logger.info(f"Deleted {delete_result.deleted_count} SERP records with same split_id: {dto.split_id}")
        
        task_delete_result = serp_task_collection.delete_many({"split_id": dto.split_id})
        if task_delete_result.deleted_count > 0:
            logger.info(f"Deleted {task_delete_result.deleted_count} SERP task records with same split_id: {dto.split_id}")
        
        search_delete_results = mongo_api_service_manager.delete_search_data_by_split_id(dto.split_id)
        if search_delete_results and search_delete_results.get("total_deleted", 0) > 0:
            logger.info(f"Deleted {search_delete_results['total_deleted']} search-related records for split_id {dto.split_id}")
        
        final_delete_result = step_record_service.final_collection.delete_many({"report_id": report_id})
        logger.info(f"Deleted report_final records: {final_delete_result.deleted_count} records")
        
        only_key = str(uuid.uuid4())
        stream_step_record_id = step_record_service.create_serp_record(
            report_id, 
            dto.split_id, 
            query_text, 
            plan_content, 
            chapter_content,
            only_key=only_key
        )

        async def stream_with_content_collection():
            chunks = []
            full_content = ""

            try:
                async for chunk in mongo_api_service_manager.stream_service.llm_service.stream(
                    message=write_report_plan_prompt(title, plan_content, chapter_content),model="serp"
                ):
                    parsed_chunk = mongo_api_service_manager.stream_service._parse_sse_chunk(chunk)
                    if parsed_chunk:
                        chunks.append(parsed_chunk)
                        yield f"data: {json.dumps(parsed_chunk)}\n\n"
                    else:
                        yield chunk

                yield "data: [DONE]\n\n"

                full_content = mongo_api_service_manager.stream_service._collect_content_from_chunks(chunks)

                async def process_content_and_store():
                    try:
                        logger.info(f"Collected content: {full_content} -----split_id:{dto.split_id}")
                        if full_content:
                            serp_queries = extract_serp_queries_from_response({"content": full_content})
                            
                            logger.info(f"Extracted serp_queries: {serp_queries} -----split_id:{dto.split_id}")
                            if serp_queries:
                                task_ids = step_record_service.create_serp_task_records(
                                    stream_step_record_id, report_id, dto.split_id, serp_queries
                                )
                                
                                for i, task in enumerate(serp_queries):
                                    task["task_id"] = task_ids[i]

                            end_time = datetime.datetime.now()
                            execution_time = (end_time - start_time).total_seconds()

                            llm_response = {
                                "id": f"stream-{report_id}",
                                "object": "chat.completion",
                                "created": int(start_time.timestamp()),
                                "model": "stream-model",
                                "choices": [{
                                    "index": 0,
                                    "message": {
                                        "role": "assistant",
                                        "content": full_content
                                    },
                                    "finish_reason": "stop"
                                }],
                                "usage": {
                                    "prompt_tokens": len(write_report_plan_prompt(title, plan_content, chapter_content).split()),
                                    "completion_tokens": len(full_content.split()),
                                    "total_tokens": len(write_report_plan_prompt(title, plan_content, chapter_content).split()) + len(full_content.split())
                                }
                            }

                            step_record_service.update_serp_record(
                                stream_step_record_id, "completed",
                                response=llm_response,
                                execution_time=execution_time,
                                tasks=serp_queries
                            )
                    except Exception as e:
                        logger.error(f"Background processing failed: {str(e)}")
                        end_time = datetime.datetime.now()
                        execution_time = (end_time - start_time).total_seconds()

                        step_record_service.update_serp_record(
                            stream_step_record_id, "failed",
                            error_message=str(e),
                            execution_time=execution_time
                        )

                asyncio.create_task(process_content_and_store())

            except Exception as e:
                logger.error(f"Streaming failed: {str(e)}")
                end_time = datetime.datetime.now()
                execution_time = (end_time - start_time).total_seconds()

                step_record_service.update_serp_record(
                    stream_step_record_id, "failed",
                    error_message=str(e),
                    execution_time=execution_time
                )

                yield f"data: {json.dumps({'error': str(e)})}\n\n"
                yield "data: [DONE]\n\n"
        
        return StreamingResponse(
            stream_with_content_collection(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
        )
        
    except Exception as e:
        if 'report_id' in locals():
            end_time = datetime.datetime.now()
            execution_time = (end_time - start_time).total_seconds()
            
            report_service.fail_step(
                report_id, "serp",
                error_message=str(e),
                execution_time=execution_time
            )
        
        logger.error(f"Stream SERP API failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Stream SERP generation failed: {str(e)}")


@router.get("/detail/{report_id}", response_model=Result)
async def get_detail(
    report_id: str
):
    """
    Get details by report_id - return LLM complete data (latest if multiple records)
    """
    return Result.success(mongo_api_service_manager.get_detail_by_report_id(report_id))


@router.get("/list/{report_id}", response_model=Result)
async def get_list(
    report_id: str
):
    """
    Get all plan chapters by report_id, including knowledge base data for each task
    """
    try:
        task_list = mongo_api_service_manager.get_serp_list_by_report_id(report_id)
        
        enhanced_task_list = []
        for task in task_list:
            task_id = task.get("task_id", "")
            if task_id:
                knowledgeBaseData, knowledgeData, is_web = _query_and_merge_kn_data_by_task_id(task_id, mongo_db)
                
                task["knowledgeBaseData"] = knowledgeBaseData
                task["knowledgeData"] = knowledgeData
                task["knowledgeBaseData_count"] = len(knowledgeBaseData)
                task["knowledgeData_count"] = len(knowledgeData)
                task["is_web"] = is_web
            else:
                task["is_web"] = True
            
            enhanced_task_list.append(task)

        logger.info(f"Total count: {len(enhanced_task_list)}")
        return Result.success(enhanced_task_list)
        
    except Exception as e:
        logger.error(f"Failed to get chapter list: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get chapter list: {str(e)}")

@router.get("/history/{report_id}", response_model=Result)
async def get_history(
    report_id: str,
    limit: int = 10
):
    """
    Get history list by report_id
    """
    return Result.success(mongo_api_service_manager.get_history_by_report_id(report_id,limit))

@router.get("/get_task_id/{split_id}", response_model=Result)
async def get_task_id(
    split_id: str
):
    """
    Get array stored in tasks field by split_id
    """
    try:
        serp_collection = mongo_db["report_serp"]
        serp_task_collection = mongo_db["serp_task"]
        
        serp_record = serp_collection.find_one(
            {"split_id": split_id},
            sort=[("created_at", -1)]
        )
        
        if not serp_record:
            return Result.success([])

        serp_record_id = str(serp_record["_id"])
        task_cursor = serp_task_collection.find(
            {"serp_record_id": serp_record_id}
        ).sort("task_index", 1)
        
        tasks = []
        for task_doc in task_cursor:
            task_id = str(task_doc["_id"])
            
            knowledgeBaseData, knowledgeData, is_web = _query_and_merge_kn_data_by_task_id(task_id, mongo_db)
            
            task = {
                "query": task_doc.get("query", ""),
                "researchGoal": task_doc.get("research_goal", ""),
                "task_id": task_id,
                "knowledgeBaseData": knowledgeBaseData,
                "knowledgeData": knowledgeData,
                "knowledgeBaseData_count": len(knowledgeBaseData),
                "knowledgeData_count": len(knowledgeData),
                "is_web": is_web
            }
            tasks.append(task)

        return Result.success(tasks)

    except Exception as e:
        logger.error(f"Failed to get task ID list: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get task ID list: {str(e)}")


@router.delete("/delete/{task_id}", response_model=Result)
async def delete_serp_task(
    task_id: str
):
    """
    Delete task record and related data by serp_task _id
    """
    try:
        if not task_id:
            raise BizError(code=ErrorCode.get_code(ErrorCode.TASK_ID_NOT_EMPTY),
                           message=ErrorCode.get_message(ErrorCode.TASK_ID_NOT_EMPTY))
        
        try:
            object_id = ObjectId(task_id)
        except Exception:
            raise BizError(code=ErrorCode.get_code(ErrorCode.DATA_FORMAT_ERROR),
                           message=ErrorCode.get_message(ErrorCode.DATA_FORMAT_ERROR))
        
        serp_task_collection = mongo_db["serp_task"]
        
        task_record = serp_task_collection.find_one({"_id": object_id})
        if not task_record:
            raise BizError(code=ErrorCode.get_code(ErrorCode.TASK_NOT_EXIST),
                           message=ErrorCode.get_message(ErrorCode.TASK_NOT_EXIST))
        
        serp_record_id = task_record.get("serp_record_id")
        split_id = task_record.get("split_id")
        report_id = task_record.get("report_id")
        
        search_delete_results = mongo_api_service_manager.delete_search_data_by_task_id(task_id)
        if search_delete_results and search_delete_results.get("total_deleted", 0) > 0:
            logger.info(f"Deleted {search_delete_results['total_deleted']} search-related records for task_id {task_id}")
        
        task_delete_result = serp_task_collection.delete_one({"_id": object_id})
        
        if task_delete_result.deleted_count == 0:
            raise BizError(code=ErrorCode.get_code(ErrorCode.TASK_DELETE_FAIL),
                           message=ErrorCode.get_message(ErrorCode.TASK_DELETE_FAIL))
        
        logger.info(f"Successfully deleted task record, ID: {task_id}")
        
        return Result.success({
            "message": "Task record deleted successfully",
            "deleted_task_id": task_id,
            "deleted_search_count": search_delete_results.get("total_deleted", 0),
            "deleted_counts": search_delete_results.get("deleted_counts", {})
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete task record: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete task record: {str(e)}")


def write_report_plan_prompt(query:str, plan_content: str, chapter_content: str) -> str:
    return f"""
User's original request: {query}

User's confirmed report plan:
<Plan>
{plan_content}
</Plan>
Based on the {chapter_content} section of the report plan,
generate a SERP query list for further research on this topic.
Ensure each query is unique and not similar to each other.
Queries should be concise and clear, covering all necessary content without asking questions.
Must use the most recent data available, do not use outdated data.
Generate 2-3 queries, no more than 3.

Strictly follow the sample format, no other content.
No limit on the number of items, more items are welcome to fully display the required content.
If user specifies a date, use that date.
Do not output any content outside of the 【SAMPLE】format.

Sample:
```json
[
    {{
        "query": "Content to search.",
        "researchGoal": "Reason for searching this content."
    }},
    {{
        "query": "Content to search.",
        "researchGoal": "Reason for searching this content."
    }},
    {{
        "query": "Content to search.",
        "researchGoal": "Reason for searching this content."
    }}
]
```
Strictly validate the output JSON structure, must ensure JSON structure is correct
    """


def extract_serp_queries_from_response(response: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Extract SERP query array from LLM response object

    Args:
        response: Complete LLM response object

    Returns:
        List[Dict[str, str]]: SERP query array, each element contains query and researchGoal
    """
    try:
        content = ""
        if isinstance(response, dict):
            if "choices" in response and len(response["choices"]) > 0:
                choice = response["choices"][0]
                if "message" in choice and "content" in choice["message"]:
                    content = choice["message"]["content"]
                elif "content" in choice:
                    content = choice["content"]
            elif "content" in response:
                content = response["content"]

        if not content:
            return []

        content = content.strip()
        if content.startswith('```json'):
            content = content[7:]
        if content.startswith('```'):
            content = content[3:]
        if content.endswith('```'):
            content = content[:-3]
        content = content.strip()

        json_match = re.search(r'(?:json)?\s*(\[[\s\S]*?\])\s*', content)
        if json_match:
            json_str = json_match.group(1)
            return json.loads(json_str)

        array_match = re.search(r'(\[[\s\S]*\])', content)
        if array_match:
            return json.loads(array_match.group(1))

        return json.loads(content)
    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing failed: {str(e)}")
        logger.error(f"JSON parsing failed: {str(e)}")
        logger.error(f"Raw content: {content[:500]}...")
        return []
    except Exception as e:
        logger.error(f"Error extracting SERP queries: {str(e)}")
        logger.error(f"Error extracting SERP queries: {str(e)}")
        return []


def _query_and_merge_kn_data_by_task_id(task_id: str, mongo_database) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], bool]:
    """Query and merge knowledgeBaseData and knowledgeData arrays by task_id, return is_web field"""
    try:
        search_results_collection = mongo_database.search_results
        search_docs = list(search_results_collection.find({"task_id": task_id}))
        
        response_data_collection = mongo_database.search_response_data
        response_docs = list(response_data_collection.find({"task_id": task_id}))
        
        logger.info(f"Found {len(search_docs)} search_results records and {len(response_docs)} search_response_data records")
        
        merged_knowledgeBaseData = []
        for doc in search_docs + response_docs:
            knowledgeBaseData = doc.get("knowledgeBaseData", [])
            if isinstance(knowledgeBaseData, list):
                merged_knowledgeBaseData.extend(knowledgeBaseData)
        
        merged_knowledgeData = []
        for doc in search_docs + response_docs:
            knowledgeData = doc.get("knowledgeData", [])
            if isinstance(knowledgeData, list):
                merged_knowledgeData.extend(knowledgeData)
        
        is_web_values = []
        for doc in search_docs + response_docs:
            is_web_value = doc.get("is_web", True)
            is_web_values.append(is_web_value)
        
        is_web = all(is_web_values) if is_web_values else True
        
        merged_knowledgeBaseData = _remove_duplicate_dicts(merged_knowledgeBaseData)
        merged_knowledgeData = _remove_duplicate_dicts(merged_knowledgeData)
        
        logger.info(f"Merged knowledgeBaseData count: {len(merged_knowledgeBaseData)}, knowledgeData count: {len(merged_knowledgeData)}, is_web: {is_web}")
        
        return merged_knowledgeBaseData, merged_knowledgeData, is_web
        
    except Exception as e:
        logger.error(f"Failed to query and merge knowledge data: {str(e)}")
        return [], [], False


def _remove_duplicate_dicts(dict_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove duplicate items from dictionary list"""
    seen = set()
    unique_list = []
    
    for item in dict_list:
        item_tuple = tuple(sorted(item.items())) if isinstance(item, dict) else item
        if item_tuple not in seen:
            seen.add(item_tuple)
            unique_list.append(item)
    
    return unique_list
