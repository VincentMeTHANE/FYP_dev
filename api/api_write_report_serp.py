"""
深度研究 写大纲
"""

import logging, json ,re
import datetime
import asyncio
import uuid
from typing import Any,List, Dict

from fastapi import APIRouter, HTTPException # type: ignore
from pydantic import BaseModel
from bson import ObjectId
from utils.database import mongo_db
from services.llm_service import llm_service
from services.mongo_api_service_manager import mongo_api_service_manager
from services.report_service import report_service
from services.step_record_service import step_record_service
from fastapi.responses import StreamingResponse # type: ignore
from utils.exception_handler import ErrorCode
from utils.response_models import Result, BizError


logger = logging.getLogger(__name__)

router = APIRouter()


class SerpRequest(BaseModel):
    """SERP请求模型"""
    split_id: str  # 章节拆分ID
    report_id: str   # 报告计划ID


@router.post("/stream")
async def chat_stream(
    dto: SerpRequest
):
    """生成SERP查询列表 - stream模式，需要有效的split_id和plan_id"""
    start_time = datetime.datetime.now()
    
    try:
        # 1. 验证split_id和plan_id
        if not dto.split_id or not dto.report_id:
            raise BizError(code=ErrorCode.get_code(ErrorCode.SERP_NEED_EFFECTIVE),
                           message=ErrorCode.get_message(ErrorCode.SERP_NEED_EFFECTIVE))

        # 2. 从MongoDB查询章节内容
        split_collection = mongo_db["report_plan_split"]
        plan_collection = mongo_db["report_plan"]
        
        # 查询章节内容
        split_doc = split_collection.find_one({"_id": ObjectId(dto.split_id)})
        if not split_doc:
            raise BizError(code=ErrorCode.get_code(ErrorCode.SERP_CHAPTER_NOT_EXIST),
                           message=ErrorCode.get_message(ErrorCode.SERP_CHAPTER_NOT_EXIST))

        # 查询计划内容
        plan_records = step_record_service.get_records_by_report_id(dto.report_id, "plan")
        if not plan_records or not plan_records.get("plan"):
            raise BizError(code=ErrorCode.get_code(ErrorCode.PLAN_NOT_EXIST),
                           message=ErrorCode.get_message(ErrorCode.PLAN_NOT_EXIST))

        # 获取最新的计划记录
        plan_doc = plan_records["plan"][0] if plan_records["plan"] else None
        if not plan_doc:
            raise BizError(code=ErrorCode.get_code(ErrorCode.PLAN_NOT_EXIST),
                           message=ErrorCode.get_message(ErrorCode.PLAN_NOT_EXIST))

        # 提取章节内容和计划内容
        chapter_content = split_doc.get("response", {}).get("content", [])[0]
        plan_content = plan_doc.get("response", {}).get("plan", "")
        
        # 构建查询文本
        query_text = f"基于计划：{plan_content} 的 {chapter_content} 部分"
        
        # 3. 获取report_id
        report_id = split_doc.get("report_id")
        if not report_id:
            raise BizError(code=ErrorCode.get_code(ErrorCode.SERP_LACK_REPORT_ID),
                           message=ErrorCode.get_message(ErrorCode.SERP_LACK_REPORT_ID))
        report_info = report_service.get_report_response(report_id)
        # logger.info(f"report_info: {report_info}")
        title = report_info.title
        # logger.info(f"title: {title}")
        
        # 4. 删除该split_id下的所有现有SERP记录，确保只有一套
        serp_collection = mongo_db["report_serp"]
        serp_task_collection = mongo_db["serp_task"]
        
        # 删除所有相同split_id的SERP记录
        delete_result = serp_collection.delete_many({"split_id": dto.split_id})
        if delete_result.deleted_count > 0:
            logger.info(f"删除了 {delete_result.deleted_count} 条相同split_id的SERP记录，split_id: {dto.split_id}")
        
        # 删除所有相同split_id的SERP任务记录
        task_delete_result = serp_task_collection.delete_many({"split_id": dto.split_id})
        if task_delete_result.deleted_count > 0:
            logger.info(f"删除了 {task_delete_result.deleted_count} 条相同split_id的SERP任务记录，split_id: {dto.split_id}")
        
        # 删除该split_id下的所有搜索相关数据
        search_delete_results = mongo_api_service_manager.delete_search_data_by_split_id(dto.split_id)
        if search_delete_results and search_delete_results.get("total_deleted", 0) > 0:
            logger.info(f"删除了split_id {dto.split_id} 下的 {search_delete_results['total_deleted']} 条搜索相关记录")
        
        # 删除report_final集合内对应report_id的记录
        final_delete_result = step_record_service.final_collection.delete_many({"report_id": report_id})
        logger.info(f"删除report_final集合记录完成，删除了 {final_delete_result.deleted_count} 条记录")
        
        # 5. 开始步骤并创建步骤记录
        # report_service.start_step(report_id, "serp")
        only_key = str(uuid.uuid4())
        stream_step_record_id = step_record_service.create_serp_record(
            report_id, 
            dto.split_id, 
            query_text, 
            plan_content, 
            chapter_content,
            only_key=only_key
        )

        # 6. 创建流式响应生成器，包含内容收集和存储逻辑
        async def stream_with_content_collection():
            chunks = []
            full_content = ""

            try:
                # 获取流式响应
                async for chunk in mongo_api_service_manager.stream_service.llm_service.stream(
                    message=write_report_plan_prompt(title, plan_content, chapter_content),model="serp"
                ):
                    # 解析SSE行为JSON对象
                    parsed_chunk = mongo_api_service_manager.stream_service._parse_sse_chunk(chunk)
                    if parsed_chunk:
                        chunks.append(parsed_chunk)
                        yield f"data: {json.dumps(parsed_chunk)}\n\n"
                    else:
                        # 直接传递原始chunk（如果解析失败）
                        yield chunk

                # 发送结束信号
                yield "data: [DONE]\n\n"

                # 收集完整内容
                full_content = mongo_api_service_manager.stream_service._collect_content_from_chunks(chunks)

                # 7. 在后台异步处理内容存储
                async def process_content_and_store():
                    try:
                        logger.info(f"收集完整内容full_content: {full_content} -----split_id:{dto.split_id}")
                        if full_content:
                            # 提取SERP查询列表
                            serp_queries = extract_serp_queries_from_response({"content": full_content})
                            
                            # 创建独立的serp_task记录
                            logger.info(f"收集完整内容serp_queries: {serp_queries} -----split_id:{dto.split_id}")
                            if serp_queries:
                                task_ids = step_record_service.create_serp_task_records(
                                    stream_step_record_id, report_id, dto.split_id, serp_queries
                                )
                                
                                # 在serp_queries中添加task_id
                                for i, task in enumerate(serp_queries):
                                    task["task_id"] = task_ids[i]

                            # 计算执行时间
                            end_time = datetime.datetime.now()
                            execution_time = (end_time - start_time).total_seconds()

                            # 构造标准的LLM响应格式（与completion接口保持一致）
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

                            # 更新步骤记录，存储完整的SERP查询内容
                            step_record_service.update_serp_record(
                                stream_step_record_id, "completed",
                                response=llm_response,
                                execution_time=execution_time,
                                tasks=serp_queries
                            )

                            # 完成步骤
                            # report_service.complete_step(
                            #     report_id, "serp",
                            #     result=llm_response,
                            #     execution_time=execution_time
                            # )
                    except Exception as e:
                        logger.error(f"收集完整内容 后台处理流式内容失败: {str(e)}")
                        # 标记步骤失败
                        end_time = datetime.datetime.now()
                        execution_time = (end_time - start_time).total_seconds()

                        # report_service.fail_step(
                        #     report_id, "serp",
                        #     error_message=str(e),
                        #     execution_time=execution_time
                        # )

                        # 更新步骤记录状态
                        step_record_service.update_serp_record(
                            stream_step_record_id, "failed",
                            error_message=str(e),
                            execution_time=execution_time
                        )

                # 启动后台任务处理内容存储
                asyncio.create_task(process_content_and_store())

            except Exception as e:
                logger.error(f"收集完整内容 流式处理失败: {str(e)}")
                # 标记步骤失败
                end_time = datetime.datetime.now()
                execution_time = (end_time - start_time).total_seconds()

                # report_service.fail_step(
                #     report_id, "serp",
                #     error_message=str(e),
                #     execution_time=execution_time
                # )

                # 更新步骤记录状态
                step_record_service.update_serp_record(
                    stream_step_record_id, "failed",
                    error_message=str(e),
                    execution_time=execution_time
                )

                # 发送错误信息
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
                yield "data: [DONE]\n\n"
        
        return StreamingResponse(
            stream_with_content_collection(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
        )
        
    except Exception as e:
        # 标记步骤失败
        if 'report_id' in locals():
            end_time = datetime.datetime.now()
            execution_time = (end_time - start_time).total_seconds()
            
            report_service.fail_step(
                report_id, "serp",
                error_message=str(e),
                execution_time=execution_time
            )
        
        logger.error(f"收集完整内容 流式SERP查询API失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"流式生成SERP查询失败: {str(e)}")


@router.get("/detail/{report_id}", response_model=Result)
async def get_detail(
    report_id: str  # 改为字符串类型，支持ObjectId
):
    """
    根据报告ID获取详细信息 - 直接返回LLM的完整数据（如有多条记录返回最新的）
    """
    return Result.success(mongo_api_service_manager.get_detail_by_report_id(report_id))


@router.get("/list/{report_id}", response_model=Result)
async def get_list(
    report_id: str
):
    """
    根据report_id获取所有的计划章节，包含每个task的知识库数据
    """
    try:
        # 获取基础的章节列表
        task_list = mongo_api_service_manager.get_serp_list_by_report_id(report_id)
        
        # 为每个task添加知识库数据
        enhanced_task_list = []
        for task in task_list:
            task_id = task.get("task_id", "")
            if task_id:
                # 查询该task_id对应的knowledgeBaseData和knowledgeData以及is_web
                knowledgeBaseData, knowledgeData, is_web = _query_and_merge_kn_data_by_task_id(task_id, mongo_db)
                
                # 添加知识库数据到task中
                task["knowledgeBaseData"] = knowledgeBaseData
                task["knowledgeData"] = knowledgeData
                task["knowledgeBaseData_count"] = len(knowledgeBaseData)
                task["knowledgeData_count"] = len(knowledgeData)
                task["is_web"] = is_web
            else:
                # 如果没有task_id，硬编码is_web为True
                task["is_web"] = True
            
            enhanced_task_list.append(task)

        logger.info(f"总条数: {len(enhanced_task_list)}")
        return Result.success(enhanced_task_list)
        
    except Exception as e:
        logger.error(f"获取章节列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取章节列表失败: {str(e)}")

@router.get("/history/{report_id}", response_model=Result)
async def get_history(
    report_id: str,  # 改为字符串类型，支持ObjectId
    limit: int = 10
):
    """
    根据报告ID获取历史记录列表
    """
    return Result.success(mongo_api_service_manager.get_history_by_report_id(report_id,limit))

@router.get("/get_task_id/{split_id}", response_model=Result)
async def get_task_id(
    split_id: str
):
    """
    根据split_id获取储存在write_report_serp接口的tasks字段中的数组
    """
    try:
        # 查询report_serp集合中的记录
        serp_collection = mongo_db["report_serp"]
        serp_task_collection = mongo_db["serp_task"]
        
        # 获取最新的SERP记录
        serp_record = serp_collection.find_one(
            {"split_id": split_id},
            sort=[("created_at", -1)]
        )
        
        if not serp_record:
            return Result.success([])

        # 获取对应的任务记录
        serp_record_id = str(serp_record["_id"])
        task_cursor = serp_task_collection.find(
            {"serp_record_id": serp_record_id}
        ).sort("task_index", 1)
        
        tasks = []
        for task_doc in task_cursor:
            task_id = str(task_doc["_id"])
            
            # 查询该task_id对应的knowledgeBaseData和knowledgeData以及is_web
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
        logger.error(f"获取任务ID列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取任务ID列表失败: {str(e)}")


@router.delete("/delete/{task_id}", response_model=Result)
async def delete_serp_task(
    task_id: str
):
    """
    根据serp_task的_id删除单条任务记录及其相关数据
    """
    try:
        # 验证task_id格式
        if not task_id:
            raise BizError(code=ErrorCode.get_code(ErrorCode.TASK_ID_NOT_EMPTY),
                           message=ErrorCode.get_message(ErrorCode.TASK_ID_NOT_EMPTY))
        
        # 验证ObjectId格式
        try:
            object_id = ObjectId(task_id)
        except Exception:
            raise BizError(code=ErrorCode.get_code(ErrorCode.DATA_FORMAT_ERROR),
                           message=ErrorCode.get_message(ErrorCode.DATA_FORMAT_ERROR))
        
        # 查询serp_task集合
        serp_task_collection = mongo_db["serp_task"]
        
        # 查找要删除的任务记录
        task_record = serp_task_collection.find_one({"_id": object_id})
        if not task_record:
            raise BizError(code=ErrorCode.get_code(ErrorCode.TASK_NOT_EXIST),
                           message=ErrorCode.get_message(ErrorCode.TASK_NOT_EXIST))
        
        # 获取任务相关信息
        serp_record_id = task_record.get("serp_record_id")
        split_id = task_record.get("split_id")
        report_id = task_record.get("report_id")
        
        # 删除该task_id下的所有搜索相关数据
        search_delete_results = mongo_api_service_manager.delete_search_data_by_task_id(task_id)
        if search_delete_results and search_delete_results.get("total_deleted", 0) > 0:
            logger.info(f"删除了task_id {task_id} 下的 {search_delete_results['total_deleted']} 条搜索相关记录")
        
        # 删除serp_task记录本身
        task_delete_result = serp_task_collection.delete_one({"_id": object_id})
        
        if task_delete_result.deleted_count == 0:
            raise BizError(code=ErrorCode.get_code(ErrorCode.TASK_DELETE_FAIL),
                           message=ErrorCode.get_message(ErrorCode.TASK_DELETE_FAIL))
        
        logger.info(f"成功删除任务记录，ID: {task_id}")
        
        return Result.success({
            "message": "任务记录删除成功",
            "deleted_task_id": task_id,
            "deleted_search_count": search_delete_results.get("total_deleted", 0),
            "deleted_counts": search_delete_results.get("deleted_counts", {})
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除任务记录失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"删除任务记录失败: {str(e)}")

# 提示词
def write_report_plan_prompt(query:str, plan_content: str, chapter_content: str) -> str:
    return f"""
这是用户的原始诉求：{query}

这是用户确认后的报告计划：
<计划>
{plan_content}
</计划>
基于报告计划的{chapter_content}部分，
生成SERP查询列表以进一步研究该主题。 
确保每个查询都是唯一的，彼此不相似。
要查询的内容要简洁明了，不要遗漏任何内容，不要提出疑问句。
必须使用离当前时间最近的数据，不要使用过时的数据。
生成数量不要超过10个，不要少于5个。

请严格按照样例格式返回，不要有任何其他内容。
条目数量不限，希望更多条目能将需要的内容展示全。
如果用户声明查询日期则使用这个日期。
不要输出【样例】之外的任何内容

样例：
```json
[
    {{
        "query": "需要查询的内容。",
        "researchGoal": "查询这个内容的原因。"
    }},
    {{
        "query": "需要查询的内容。",
        "researchGoal": "查询这个内容的原因。"
    }},
    {{
        "query": "需要查询的内容。",
        "researchGoal": "查询这个内容的原因。"
    }}
]
```
请严格校验输出的json结构，必须保证json结构正确
    """


def extract_serp_queries_from_response(response: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    从LLM响应对象中提取SERP查询数组

    Args:
        response: LLM返回的完整响应对象

    Returns:
        List[Dict[str, str]]: SERP查询数组，每个元素包含query和researchGoal
    """
    try:
        # 从响应对象中提取content
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

        # 清理内容，移除可能的markdown代码块标记
        content = content.strip()
        if content.startswith('```json'):
            content = content[7:]  # 移除 ```json
        if content.startswith('```'):
            content = content[3:]   # 移除 ```
        if content.endswith('```'):
            content = content[:-3]  # 移除结尾的 ```
        content = content.strip()

        # 提取JSON内容
        # 1. 首先尝试查找代码块中的JSON数组
        json_match = re.search(r'(?:json)?\s*(\[[\s\S]*?\])\s*', content)
        if json_match:
            json_str = json_match.group(1)
            return json.loads(json_str)

        # 2. 如果没有找到代码块，尝试查找任何方括号包围的JSON数组
        array_match = re.search(r'(\[[\s\S]*\])', content)
        if array_match:
            return json.loads(array_match.group(1))

        # 3. 如果还是找不到，尝试直接解析整个内容
        return json.loads(content)
    except json.JSONDecodeError as e:
        logger.error(f"收集完整内容 JSON解析失败: {str(e)}")
        logger.error(f"JSON解析失败: {str(e)}")
        logger.error(f"原始内容: {content[:500]}...")  # 记录前500个字符用于调试
        return []
    except Exception as e:
        logger.error(f"收集完整内容 提取SERP查询时出错: {str(e)}")
        logger.error(f"提取SERP查询时出错: {str(e)}")
        return []


def _query_and_merge_kn_data_by_task_id(task_id: str, mongo_database) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], bool]:
    """根据task_id查询并合并knowledgeBaseData和knowledgeData数组，同时返回is_web字段"""
    try:
        # 查询search_results集合中所有包含该task_id的文档
        search_results_collection = mongo_database.search_results
        search_docs = list(search_results_collection.find({"task_id": task_id}))
        
        # 查询search_response_data集合中所有包含该task_id的文档
        response_data_collection = mongo_database.search_response_data
        response_docs = list(response_data_collection.find({"task_id": task_id}))
        
        logger.info(f"找到 {len(search_docs)} 条search_results记录和 {len(response_docs)} 条search_response_data记录")
        
        # 合并knowledgeBaseData数组
        merged_knowledgeBaseData = []
        for doc in search_docs + response_docs:
            knowledgeBaseData = doc.get("knowledgeBaseData", [])
            if isinstance(knowledgeBaseData, list):
                merged_knowledgeBaseData.extend(knowledgeBaseData)
        
        # 合并knowledgeData数组
        merged_knowledgeData = []
        for doc in search_docs + response_docs:
            knowledgeData = doc.get("knowledgeData", [])
            if isinstance(knowledgeData, list):
                merged_knowledgeData.extend(knowledgeData)
        
        # 从数据库中读取is_web字段，如果所有记录的is_web都为True则返回True，否则返回False
        is_web_values = []
        for doc in search_docs + response_docs:
            is_web_value = doc.get("is_web", True)  # 默认为True
            is_web_values.append(is_web_value)
        
        # 如果所有记录的is_web都为True，则返回True，否则返回False
        is_web = all(is_web_values) if is_web_values else True
        
        # 去重处理 - 基于字典内容的去重
        merged_knowledgeBaseData = _remove_duplicate_dicts(merged_knowledgeBaseData)
        merged_knowledgeData = _remove_duplicate_dicts(merged_knowledgeData)
        
        logger.info(f"合并后knowledgeBaseData数量: {len(merged_knowledgeBaseData)}, knowledgeData数量: {len(merged_knowledgeData)}, is_web: {is_web}")
        
        return merged_knowledgeBaseData, merged_knowledgeData, is_web
        
    except Exception as e:
        logger.error(f"查询和合并知识数据失败: {str(e)}")
        return [], [], False


def _remove_duplicate_dicts(dict_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """去除字典列表中的重复项"""
    seen = set()
    unique_list = []
    
    for item in dict_list:
        # 将字典转换为可哈希的元组进行去重比较
        item_tuple = tuple(sorted(item.items())) if isinstance(item, dict) else item
        if item_tuple not in seen:
            seen.add(item_tuple)
            unique_list.append(item)
    
    return unique_list
