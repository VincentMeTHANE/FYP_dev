"""
MongoDB API服务管理器 - 统一处理所有API的标准流程，使用纯MongoDB存储
"""

import logging,re
import datetime
import json
from typing import Dict, Any, Optional, Callable, Union, List
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from bson import ObjectId

from services.llm_service import LLMService
from services.mongo_stream_storage_service import MongoStreamStorageService
from utils.database import mongo_db
from utils.exception_handler import ErrorCode
from utils.response_models import BizError

logger = logging.getLogger(__name__)


class MongoAPIServiceManager:
    """MongoDB API服务管理器 - 使用纯MongoDB存储的统一API处理"""
    
    def __init__(self):
        self.llm_service = LLMService()
        self.stream_service = MongoStreamStorageService()
    
    async def execute_completion_api(
        self,
        query: str,
        query_type: str,
        title_prefix: str,
        service_call: Callable,
        additional_data: Optional[Dict[str, Any]] = None,
        report_id: Optional[str] = None  # 改为字符串类型，支持ObjectId
    ) -> Dict[str, Any]:
        """
        执行completion API的统一流程（纯MongoDB版本）
        
        Args:
            query: 用户查询
            query_type: 查询类型
            title_prefix: 标题前缀
            service_call: LLM服务调用函数
            additional_data: 额外数据
            report_id: 现有报告ID（可选，支持ObjectId字符串）
            
        Returns:
            包含LLM响应的字典
        """
        collection_name = "reports"  # 统一使用reports集合
        
        report_doc = None
        start_time = datetime.datetime.now()
        
        try:
            # 1. 获取或创建MongoDB报告文档
            collection = mongo_db[collection_name]
            
            if report_id:
                # 使用现有报告
                try:
                    object_id = ObjectId(report_id)
                    report_doc = collection.find_one({"_id": object_id})
                    
                    if not report_doc:
                        raise BizError(code=ErrorCode.get_code(ErrorCode.DATA_FORMAT_ERROR),
                               message=ErrorCode.get_message(ErrorCode.DATA_FORMAT_ERROR))
                    
                    # 更新状态为processing
                    collection.update_one(
                        {"_id": object_id},
                        {
                            "$set": {
                                "status": "processing",
                                "updated_at": start_time,
                                "start_time": start_time
                            }
                        }
                    )
                    report_doc["_id"] = object_id
                    
                except Exception as e:
                    raise BizError(code=ErrorCode.get_code(ErrorCode.DATA_FORMAT_ERROR),
                               message=ErrorCode.get_message(ErrorCode.DATA_FORMAT_ERROR))
            else:
                # 创建新报告记录
                report_doc = self._create_mongo_report(
                    query=query,
                    query_type=query_type,
                    title_prefix=title_prefix,
                    start_time=start_time
                )
            
            logger.info(f"开始执行{query_type}服务，报告ID: {report_doc['_id']}")
            
            # 2. 执行LLM服务调用
            result = await service_call()
            end_time = datetime.datetime.now()
            execution_time = (end_time - start_time).total_seconds()
            
            # 3. 更新报告状态和结果
            # 提取内容预览
            content_preview = ""
            if result and "choices" in result and result["choices"]:
                content = result["choices"][0].get("message", {}).get("content", "")
                content_preview = content[:100] if content else ""
            
            update_data = {
                "updated_at": end_time,
                "end_time": end_time,
                "execution_time": execution_time,
                "llm_response": result,
                "content_preview": content_preview
            }
            # 注意：不在这里设置 status，让 report_service 来管理整体状态
            
            if additional_data:
                update_data["additional_data"] = additional_data
            
            # 添加调试日志
            # logger.info(f"准备更新报告状态，报告ID: {report_doc['_id']}, 更新数据: {update_data}")
            
            try:
                update_result = collection.update_one(
                    {"_id": report_doc["_id"]},
                    {"$set": update_data}
                )
                logger.info(f"更新操作结果: matched_count={update_result.matched_count}, modified_count={update_result.modified_count}")
            except Exception as update_error:
                logger.error(f"更新操作失败: {str(update_error)}")
                raise BizError(code=ErrorCode.get_code(ErrorCode.DATA_FORMAT_ERROR),
                               message=ErrorCode.get_message(ErrorCode.DATA_FORMAT_ERROR))
            
            logger.info(f"{query_type}服务执行成功，报告ID: {report_doc['_id']}")
            
            # 4. 返回结果，包含MongoDB的_id作为报告ID
            return {
                "report_id": str(report_doc["_id"]),
                "llm_response": result,
                "mongo_document_id": str(report_doc["_id"])
            }
        
        except Exception as e:
            error_msg = str(e)
            logger.error(f"{query_type}服务执行失败: {error_msg}")
            
            # 更新失败状态
            if report_doc:
                end_time = datetime.datetime.now()
                execution_time = (end_time - start_time).total_seconds()
                
                collection = mongo_db[collection_name]
                
                fail_update_data = {
                    "updated_at": end_time,
                    "end_time": end_time,
                    "execution_time": execution_time,
                    "error_message": error_msg
                }
                # 注意：不在这里设置 status，让 report_service 来管理整体状态
                
                logger.info(f"准备更新失败状态，报告ID: {report_doc['_id']}, 错误: {error_msg}")
                
                try:
                    fail_update_result = collection.update_one(
                        {"_id": report_doc["_id"]},
                        {"$set": fail_update_data}
                    )
                    logger.info(f"失败状态更新结果: matched_count={fail_update_result.matched_count}, modified_count={fail_update_result.modified_count}")
                except Exception as fail_update_error:
                    logger.error(f"更新失败状态操作失败: {str(fail_update_error)}")
            
            # 返回错误响应
            error_response = self._create_error_response(error_msg, query)
            return {
                "report_id": str(report_doc["_id"]) if report_doc else None,
                "llm_response": error_response,
                "mongo_document_id": str(report_doc["_id"]) if report_doc else None
            }
    
    async def execute_stream_api(
        self,
        query: str,
        query_type: str,
        title_prefix: str,
        prompt_builder: Callable,
        use_mcp: bool = False,
        report_id: Optional[str] = None,
        model: Optional[str] = None
    ) -> StreamingResponse:
        """
        执行stream API的统一流程（纯MongoDB版本）
        """
        collection_name = "reports"  # 统一使用reports集合
        start_time = datetime.datetime.now()
        
        try:
            # 1. 获取或创建MongoDB报告文档
            collection = mongo_db[collection_name]
            
            if report_id:
                # 使用现有报告
                try:
                    object_id = ObjectId(report_id)
                    report_doc = collection.find_one({"_id": object_id})
                    
                    if not report_doc:
                        raise BizError(code=ErrorCode.get_code(ErrorCode.REPORT_NOT_EXIST),
                               message=ErrorCode.get_message(ErrorCode.REPORT_NOT_EXIST))
                    
                    # 更新状态为processing
                    collection.update_one(
                        {"_id": object_id},
                        {
                            "$set": {
                                "status": "processing",
                                "updated_at": start_time,
                                "start_time": start_time
                            }
                        }
                    )
                    
                except Exception as e:
                    raise BizError(code=ErrorCode.get_code(ErrorCode.DATA_FORMAT_ERROR),
                               message=ErrorCode.get_message(ErrorCode.DATA_FORMAT_ERROR))
            else:
                # 创建新报告
                report_doc = self._create_mongo_report(
                    query=query,
                    query_type=f"{query_type}_stream",
                    title_prefix=f"流式{title_prefix}",
                    start_time=start_time
                )
                object_id = report_doc["_id"]
            
            logger.info(f"开始执行流式{query_type}服务，报告ID: {object_id}")
            
            # 2. 创建流式响应
            return self.stream_service.create_stream_response(
                query=query,
                query_type=query_type,
                prompt_builder=prompt_builder,
                report_id=str(object_id),  # 传递字符串格式的ObjectId
                use_mcp=use_mcp,
                model = model
            )
        
        except Exception as e:
            error_msg = str(e)
            logger.error(f"流式{query_type}服务执行失败: {error_msg}")
            
            # 返回错误的流式响应
            async def error_generator():
                yield f"data: {json.dumps({'error': error_msg})}\n\n"
            
            return StreamingResponse(
                error_generator(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
            )
    
    def _create_mongo_report(
        self,
        query: str,
        query_type: str,
        title_prefix: str,
        start_time: datetime.datetime
    ) -> Dict[str, Any]:
        """在MongoDB中创建新的报告文档"""
        
        title = f"{title_prefix}: {query}"
        
        report_doc = {
            "title": title,
            "message": query,  # 修复：使用 message 而不是 query
            "query_type": query_type,
            "status": "processing",
            "created_at": start_time,
            "updated_at": start_time,
            "start_time": start_time
        }
        
        collection = mongo_db["reports"]  # 统一使用reports集合
        result = collection.insert_one(report_doc)
        
        report_doc["_id"] = result.inserted_id
        logger.info(f"创建新报告成功，ID: {result.inserted_id}")
        
        return report_doc

    def get_detail_by_report_final_id(
            self,
            report_id: str  # 改为字符串类型
    ) -> str:
        """
        根据report_id获取详细信息（纯MongoDB版本）

        Args:
            report_id: 报告ID（ObjectId字符串）

        Returns:
            LLM的完整响应数据
        """
        try:
            logger.info(f"开始获取详情，报告ID: {report_id}")

            collection = mongo_db["report_final"]  # 统一使用reports集合

            # 查找报告文档
            # 查找报告文档
            cursor = collection.find(
                {"report_id": report_id}
            ).sort("chapter_index", 1)

            records = ""
            if cursor:
                for doc in cursor:
                    records += doc.get("current", "") + "\n" + "\n"
            logger.info(f"成功获取历史记录，报告ID: {report_id}, 记录数: {len(records)}")
            return records

        except HTTPException:
            raise
        except Exception as e:
            error_msg = f"获取详情时发生错误: {str(e)}"
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)

    def get_report_message_by_report_id(
            self,
            report_id: str  # 改为字符串类型
    ) -> str:
        """
        根据report_id获取详细信息（纯MongoDB版本）

        Args:
            report_id: 报告ID（ObjectId字符串）

        Returns:
            LLM的完整响应数据
        """
        try:
            logger.info(f"开始获取详情，报告ID: {report_id}")

            collection = mongo_db["reports"]  # 统一使用reports集合

            object_id = ObjectId(report_id)
            report_doc = collection.find_one({"_id": object_id})

            if not report_doc:
                raise BizError(code=ErrorCode.get_code(ErrorCode.REPORT_NOT_EXIST),
                               message=ErrorCode.get_message(ErrorCode.REPORT_NOT_EXIST))

            return report_doc.get("title", "")

        except HTTPException:
            raise
        except Exception as e:
            error_msg = f"获取详情时发生错误: {str(e)}"
            logger.error(error_msg)
            raise BizError(code=ErrorCode.get_code(ErrorCode.DATA_FORMAT_ERROR),
                               message=ErrorCode.get_message(ErrorCode.DATA_FORMAT_ERROR))
    
    def get_detail_by_report_id(
        self,
        report_id: str  # 改为字符串类型
    ) -> Dict[str, Any]:
        """
        根据report_id获取详细信息（纯MongoDB版本）
        
        Args:
            report_id: 报告ID（ObjectId字符串）
            
        Returns:
            LLM的完整响应数据
        """
        try:
            logger.info(f"开始获取详情，报告ID: {report_id}")
            
            # 转换为ObjectId
            try:
                object_id = ObjectId(report_id)
            except Exception:
                raise BizError(code=ErrorCode.get_code(ErrorCode.DATA_FORMAT_ERROR),
                               message=ErrorCode.get_message(ErrorCode.DATA_FORMAT_ERROR))
            
            collection = mongo_db["reports"]  # 统一使用reports集合
            
            # 查找报告文档
            report_doc = collection.find_one({"_id": object_id})
            
            if not report_doc:
                raise BizError(code=ErrorCode.get_code(ErrorCode.REPORT_NOT_EXIST),
                               message=ErrorCode.get_message(ErrorCode.REPORT_NOT_EXIST))
            
            # 提取LLM响应数据
            llm_response = report_doc.get("llm_response")
            if not llm_response:
                raise BizError(code=ErrorCode.get_code(ErrorCode.DATA_FORMAT_ERROR),
                               message=ErrorCode.get_message(ErrorCode.DATA_FORMAT_ERROR))
            
            logger.info(f"成功获取详情，报告ID: {report_id}")
            return llm_response
        
        except HTTPException:
            raise
        except Exception as e:
            error_msg = f"获取详情时发生错误: {str(e)}"
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)

    def get_ask_detail(
            self,
            report_id: str  # 改为字符串类型
    ) -> Dict[str, Any]:
        """
        根据report_id获取详细信息（纯MongoDB版本）
        """
        try:
            logger.info(f"开始获取详情，报告ID: {report_id}")

            collection = mongo_db["report_ask_questions"]  # 统一使用reports集合

            # 查找报告文档
            result = collection.find(
                {"report_id": report_id}
            ).sort("created_at", -1).limit(1)

            # 将游标转换为列表以获取实际结果
            result_list = list(result)

            if not result_list:
                raise BizError(code=ErrorCode.get_code(ErrorCode.REPORT_NOT_EXIST),
                               message=ErrorCode.get_message(ErrorCode.REPORT_NOT_EXIST))

            logger.info(f"成功获取详情，报告ID: {report_id}")

            # 确保返回的是可序列化的字典对象
            document = result_list[0]
            # 转换 ObjectId 为字符串（如果存在）
            if "_id" in document:
                document["_id"] = str(document["_id"])
            return document

        except HTTPException:
            raise
        except Exception as e:
            error_msg = f"获取详情时发生错误: {str(e)}"
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)

    def get_plan_by_report_id(
            self,
            report_id: str  # 改为字符串类型
    ) -> Dict[str, Any]:
        """
        根据report_id获取详细信息（纯MongoDB版本）
        """
        try:
            logger.info(f"开始获取详情，报告ID: {report_id}")

            collection = mongo_db["report_plan"]  # 统一使用reports集合

            # 查找报告文档
            result = collection.find(
                {"report_id": report_id}
            ).sort("created_at", 1).limit(1)

            # 将游标转换为列表以获取实际结果
            result_list = list(result)

            if not result_list:
                raise BizError(code=ErrorCode.get_code(ErrorCode.REPORT_NOT_EXIST),
                               message=ErrorCode.get_message(ErrorCode.REPORT_NOT_EXIST))

            logger.info(f"成功获取详情，报告ID: {report_id}")

            # 确保返回的是可序列化的字典对象
            document = result_list[0]
            # 转换 ObjectId 为字符串（如果存在）
            if "_id" in document:
                document["_id"] = str(document["_id"])
            return document

        except HTTPException:
            raise
        except Exception as e:
            error_msg = f"获取详情时发生错误: {str(e)}"
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)

    def get_results_search_id(
            self,
            search_id: str
    ) -> Dict[str, Any]:

        try:
            logger.info(f"开始获取历史记录，ID: {search_id}")

            collection = mongo_db["search_results"]

            # 查找该报告的所有记录（可能有多条）
            cursor = collection.find(
                {"task_id": search_id}
            ).sort("created_at", -1)

            records = []
            for doc in cursor:
                record = {
                    "mongo_id": str(doc["_id"]),
                    "task_id": doc.get("task_id", ""),
                    "report_id": doc.get("report_id", ""),
                    "type": doc.get("type", ""),
                    "query": doc.get("query", ""),
                    "result_index": doc.get("result_index", ""),
                    "title": doc.get("title", ""),
                    "url": doc.get("url", ""),
                    "content": doc.get("content", ""),
                    "published_date": doc.get("published_date", ""),
                    # "score": doc.get("score", ""),
                    "raw_content": doc.get("raw_content", ""),
                    "tavily_answer": doc.get("tavily_answer", ""),
                    "response_time": doc.get("response_time", ""),
                    "follow_up_questions": doc.get("follow_up_questions", ""),
                    "images": doc.get("images", []),  # 修复：从 message 字段获取查询内容
                    "sources": doc.get("sources", []),
                    "created_at": doc.get("created_at")
                }
                records.append(record)

            logger.info(f"成功获取历史记录，任务ID: {search_id}, 记录数: {len(records)}")
            return records[0]

        except HTTPException:
            raise
        except Exception as e:
            error_msg = f"获取数据发生错误: {str(e)}"
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)

    def get_results_report_id(
            self,
            report_id: str
    ) -> list[dict[str, Any]]:

        try:
            logger.info(f"开始获取历史记录，ID: {report_id}")

            collection = mongo_db["search_results"]

            # 查找该报告的所有记录（可能有多条）
            cursor = collection.find(
                {"report_id": report_id}
            ).sort("created_at", -1)

            records = []
            for doc in cursor:
                record = {
                    "mongo_id": str(doc["_id"]),
                    "task_id": doc.get("task_id", ""),
                    "report_id": doc.get("report_id", ""),
                    "type": doc.get("type", ""),
                    "query": doc.get("query", ""),
                    "result_index": doc.get("result_index", ""),
                    "title": doc.get("title", ""),
                    "url": doc.get("url", ""),
                    "content": doc.get("content", ""),
                    "published_date": doc.get("published_date", ""),
                    # "score": doc.get("score", ""),
                    "raw_content": doc.get("raw_content", ""),
                    "tavily_answer": doc.get("tavily_answer", ""),
                    "response_time": doc.get("response_time", ""),
                    "follow_up_questions": doc.get("follow_up_questions", ""),
                    "images": doc.get("images", []),  # 修复：从 message 字段获取查询内容
                    "sources": doc.get("sources", []),
                    "created_at": doc.get("created_at")
                }
                records.append(record)

            logger.info(f"成功获取历史记录，任务ID: {report_id}, 记录数: {len(records)}")
            return records

        except HTTPException:
            raise
        except Exception as e:
            error_msg = f"获取数据发生错误: {str(e)}"
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)

    def get_results_task_id(
            self,
            task_id: str
    ) -> list[dict[str, Any]]:

        try:
            logger.info(f"开始获取历史记录，ID: {task_id}")

            collection = mongo_db["search_results"]

            # 查找该报告的所有记录（可能有多条）
            cursor = collection.find(
                {"task_id": task_id}
            ).sort("created_at", -1)

            records = []
            for doc in cursor:
                record = {
                    "mongo_id": str(doc["_id"]),
                    "task_id": doc.get("task_id", ""),
                    "report_id": doc.get("report_id", ""),
                    "type": doc.get("type", ""),
                    "query": doc.get("query", ""),
                    "result_index": doc.get("result_index", ""),
                    "title": doc.get("title", ""),
                    "url": doc.get("url", ""),
                    "content": doc.get("content", ""),
                    "published_date": doc.get("published_date", ""),
                    "score": doc.get("score", 0),
                    "raw_content": doc.get("raw_content", ""),
                    "tavily_answer": doc.get("tavily_answer", ""),
                    "response_time": doc.get("response_time", ""),
                    "follow_up_questions": doc.get("follow_up_questions", ""),
                    "images": doc.get("images", []),  # 修复：从 message 字段获取查询内容
                    # "sources": doc.get("sources", []),
                    "created_at": doc.get("created_at")
                }
                records.append(record)

            logger.info(f"成功获取历史记录，任务ID: {task_id}, 记录数: {len(records)}")
            return records

        except HTTPException:
            raise
        except Exception as e:
            error_msg = f"获取数据发生错误: {str(e)}"
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)

    def get_search_summary(
            self,
            task_id: str
    ) -> Dict[str, Any]:

        try:
            logger.info(f"开始获取历史记录，ID: {task_id}")

            collection = mongo_db["report_search_summary"]

            # 查找该报告的所有记录（可能有多条）
            cursor = collection.find(
                {"task_id": task_id}
            ).sort("created_at", -1)

            records = []
            for doc in cursor:
                record = {
                    "mongo_id": str(doc["_id"]),
                    "response": doc.get("response", {}),
                    "query": doc.get("query", '')
                }
                records.append(record)

            logger.info(f"成功获取历史记录，报告ID: {task_id}, 记录数: {len(records)}")
            return records[0]

        except HTTPException:
            raise
        except Exception as e:
            error_msg = f"获取数据发生错误: {str(e)}"
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)

    def get_search_response_data(
            self,
            search_id: str
    ) -> Dict[str, Any]:

        try:
            logger.info(f"开始获取历史记录，ID: {search_id}")

            collection = mongo_db["search_response_data"]

            # 查找该报告的所有记录（可能有多条）
            cursor = collection.find(
                {"task_id": search_id}
            ).sort("created_at", -1)

            records = []
            for doc in cursor:
                record = {
                    "mongo_id": str(doc["_id"]),
                    "task_id": doc.get("task_id", ""),
                    "report_id": doc.get("report_id", ""),
                    "type": doc.get("type", ""),
                    "images": doc.get("images", []),  # 修复：从 message 字段获取查询内容
                    "sources": doc.get("sources", []),
                    "created_at": doc.get("created_at")
                }
                records.append(record)

            logger.info(f"成功获取历史记录，任务ID: {search_id}, 记录数: {len(records)}")
            return records[0]

        except HTTPException:
            raise
        except Exception as e:
            error_msg = f"获取数据发生错误: {str(e)}"
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)

    def get_history_by_report_id(
        self,
        report_id: str,  # 改为字符串类型  
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        根据report_id获取历史记录列表（纯MongoDB版本）
        
        Args:
            report_id: 报告ID（ObjectId字符串）
            limit: 返回记录数限制
            
        Returns:
            历史记录列表
        """
        try:
            logger.info(f"开始获取历史记录，报告ID: {report_id}")
            
            # 转换为ObjectId
            try:
                object_id = ObjectId(report_id)
            except Exception:
                raise BizError(code=ErrorCode.get_code(ErrorCode.DATA_FORMAT_ERROR),
                               message=ErrorCode.get_message(ErrorCode.DATA_FORMAT_ERROR))
            
            collection = mongo_db["reports"]  # 统一使用reports集合
            
            # 查找该报告的所有记录（可能有多条）
            cursor = collection.find(
                {"_id": object_id}
            ).sort("created_at", -1).limit(limit)
            
            history_records = []
            for doc in cursor:
                record = {
                    "mongo_id": str(doc["_id"]),
                    "title": doc.get("title", ""),
                    "query": doc.get("message", ""),  # 修复：从 message 字段获取查询内容
                    "query_type": doc.get("query_type", ""),
                    "status": doc.get("status", ""),
                    "created_at": doc.get("created_at"),
                    "updated_at": doc.get("updated_at"),
                    "execution_time": doc.get("execution_time"),
                    "content_preview": doc.get("content_preview", "")
                }
                history_records.append(record)
            
            logger.info(f"成功获取历史记录，报告ID: {report_id}, 记录数: {len(history_records)}")
            return history_records
        
        except HTTPException:
            raise
        except Exception as e:
            error_msg = f"获取历史记录时发生错误: {str(e)}"
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)
    
    def _create_error_response(self, error_msg: str, query: str = "") -> Dict[str, Any]:
        """创建错误响应"""
        return {
            "id": "error-response",
            "object": "chat.completion",
            "created": int(datetime.datetime.now().timestamp()),
            "model": "error",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": f"服务暂时不可用。您的查询 '{query}' 已记录，请稍后重试。错误: {error_msg}"
                }
            }]
        }

    def get_serp_list_by_report_id(
            self,
            report_id: str
    ) -> List[Dict[str, Any]]:
        try:
            logger.info(f"开始获取章节列表，ID: {report_id}")

            collection = mongo_db["report_serp"]  # report_serp
            serp_task_collection = mongo_db["serp_task"]  # serp_task

            # 查找该报告的所有记录（可能有多条） -1 - 降序排列（最新的在前），如果是 1 则为升序
            cursor = collection.find(
                {"report_id": report_id}
            ).sort("created_at", 1)

            # 使用集合来存储唯一的任务，避免重复
            seen_task_ids = set()
            task_list = []
            
            for doc in cursor:
                # 获取该SERP记录对应的所有task记录
                serp_record_id = str(doc["_id"])
                task_cursor = serp_task_collection.find(
                    {"serp_record_id": serp_record_id}
                ).sort("task_index", 1)
                
                for task_doc in task_cursor:
                    task_id = str(task_doc["_id"])
                    
                    # 避免重复添加相同的任务
                    if task_id in seen_task_ids:
                        continue
                    seen_task_ids.add(task_id)

                    try:
                        report_plan_split_collection = mongo_db["report_plan_split"]  # report_serp
                        split_id = task_doc.get("split_id", "")
                        object_id = ObjectId(split_id)
                        split_doc = report_plan_split_collection.find_one(
                            {"_id": object_id}
                        )
                        section_title=split_doc.get("section_title", "")
                    except Exception as e:
                        logger.warning(f"提取章节标题失败: {str(e)}")
                        section_title = "未知章节"
                    
                    task = {
                        "sectionTitle": section_title,
                        "current": doc.get("current", ""),
                        "query": task_doc.get("query", ""),
                        "researchGoal": task_doc.get("research_goal", ""),
                        "task_id": task_id,
                        "search_state": task_doc.get("search_state", ""),
                        "split_id": task_doc.get("split_id", ""),
                        "search_type": task_doc.get("search_type", ""),
                        "serp_record_id": serp_record_id,
                        "created_at": task_doc.get("created_at"),
                        "updated_at": task_doc.get("updated_at")
                    }
                    task_list.append(task)

            logger.info(f"成功获取章节列表，计划ID: {report_id}, 任务数: {len(task_list)}")
            return task_list

        except HTTPException:
            raise
        except Exception as e:
            error_msg = f"获取章节列表时发生错误: {str(e)}"
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)

    def get_serp_by_report_id(
            self,
            report_id: str
    ) -> List[Dict[str, Any]]:
        try:
            logger.info(f"开始获取章节列表，ID: {report_id}")

            collection = mongo_db["report_serp"]  # report_serp

            # 查找该报告的所有记录（可能有多条） -1 - 降序排列（最新的在前），如果是 1 则为升序
            cursor = collection.find(
                {"report_id": report_id}
            ).sort("created_at", 1)

            records = []
            for doc in cursor:
                record = {
                    "mongo_id": str(doc["_id"]),
                    "current": doc.get("current", "")
                }
                records.append(record)

            logger.info(f"成功记录，报告ID: {report_id}, 记录数: {len(records)}")
            return records

        except HTTPException:
            raise
        except Exception as e:
            error_msg = f"获取章节列表时发生错误: {str(e)}"
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)

    def get_report_plan_split_by_id(
            self,
            id: str
    ) -> Dict[str, Any]:
        try:
            logger.info(f"开始获取章节列表，ID: {id}")

            collection = mongo_db["report_plan_split"]
            object_id = ObjectId(id)

            return collection.find_one({"_id": object_id})

        except HTTPException:
            raise
        except Exception as e:
            error_msg = f"获取章节列表时发生错误: {str(e)}"
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)

    def update_serp_task_search_state(
            self,
            task_id: str,
            search_state: str
    ) -> bool:
        """
        更新serp_task表的search_state字段

        Args:
            task_id: 任务ID（ObjectId字符串）
            search_state: 搜索状态值

        Returns:
            bool: 更新是否成功
        """
        try:
            logger.info(f"开始更新serp_task搜索状态，任务ID: {task_id}, 状态: {search_state}")

            # 验证task_id格式
            if not task_id:
                raise BizError(code=ErrorCode.get_code(ErrorCode.DATA_FORMAT_ERROR),
                               message=ErrorCode.get_message(ErrorCode.DATA_FORMAT_ERROR))

            try:
                object_id = ObjectId(task_id)
            except Exception:
                raise BizError(code=ErrorCode.get_code(ErrorCode.DATA_FORMAT_ERROR),
                               message=ErrorCode.get_message(ErrorCode.DATA_FORMAT_ERROR))

            collection = mongo_db["serp_task"]

            # 更新search_state字段
            update_data = {
                "search_state": search_state,
                "updated_at": datetime.datetime.now()
            }

            result = collection.update_one(
                {"_id": object_id},
                {"$set": update_data}
            )

            if result.matched_count > 0:
                logger.info(f"成功更新serp_task搜索状态，任务ID: {task_id}, 状态: {search_state}")
                return True
            else:
                logger.warning(f"未找到对应的serp_task记录，任务ID: {task_id}")
                return False

        except HTTPException:
            raise
        except Exception as e:
            error_msg = f"更新serp_task搜索状态时发生错误: {str(e)}"
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)

    def update_serp_task_search_type(
            self,
            task_id: str,
            search_type: str
    ) -> bool:
        """
        更新serp_task表的search_state字段

        Args:
            task_id: 任务ID（ObjectId字符串）
            search_type: 搜索状态值

        Returns:
            bool: 更新是否成功
        """
        try:
            logger.info(f"开始更新serp_task搜索类型，任务ID: {task_id}, 类型: {search_type}")

            # 验证task_id格式
            if not task_id:
                raise BizError(code=ErrorCode.get_code(ErrorCode.TASK_ID_NOT_EMPTY),
                               message=ErrorCode.get_message(ErrorCode.TASK_ID_NOT_EMPTY))

            try:
                object_id = ObjectId(task_id)
            except Exception:
                raise BizError(code=ErrorCode.get_code(ErrorCode.DATA_FORMAT_ERROR),
                               message=ErrorCode.get_message(ErrorCode.DATA_FORMAT_ERROR))

            collection = mongo_db["serp_task"]

            # 更新search_state字段
            update_data = {
                "search_type": search_type,
                "updated_at": datetime.datetime.now()
            }

            result = collection.update_one(
                {"_id": object_id},
                {"$set": update_data}
            )

            if result.matched_count > 0:
                logger.info(f"成功更新serp_task搜索类型，任务ID: {task_id}, 检索类型: {search_type}")
                return True
            else:
                logger.warning(f"未找到对应的serp_task记录，任务ID: {task_id}")
                return False

        except HTTPException:
            raise
        except Exception as e:
            error_msg = f"更新serp_task搜索类型时发生错误: {str(e)}"
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)

    def update_report_plan( self, plan_id: ObjectId, plan: str ) -> bool:
        """
        更新report_plan表的response字段中的plan子字段

        Args:
            plan_id: 计划ID（ObjectId字符串）
            plan: 新的计划内容

        Returns:
            bool: 更新是否成功
        """
        try:
            logger.info(f"开始更新report_plan的response.plan字段，计划ID: {plan_id}")

            # 验证plan_id格式
            if not plan_id:
                raise BizError(code=ErrorCode.get_code(ErrorCode.PLAN_ID_NOT_EMPTY),
                               message=ErrorCode.get_message(ErrorCode.PLAN_ID_NOT_EMPTY))

            try:
                object_id = ObjectId(plan_id)
            except Exception:
                raise BizError(code=ErrorCode.get_code(ErrorCode.DATA_FORMAT_ERROR),
                               message=ErrorCode.get_message(ErrorCode.DATA_FORMAT_ERROR))

            # 验证plan_content参数
            if plan is None:
                raise BizError(code=ErrorCode.get_code(ErrorCode.PLAN_NOT_EXIST),
                               message=ErrorCode.get_message(ErrorCode.PLAN_NOT_EXIST))

            collection = mongo_db["report_plan"]

            # 使用点号表示法更新response对象中的plan字段
            update_data = {
                "response.plan": plan,
                "updated_at": datetime.datetime.now()
            }

            result = collection.update_one(
                {"_id": object_id},
                {"$set": update_data}
            )

            if result.matched_count > 0:
                logger.info(f"成功更新report_plan的response.plan字段，计划ID: {object_id}")
                return True
            else:
                logger.warning(f"未找到对应的report_plan记录，计划ID: {object_id}")
                return False

        except HTTPException:
            raise
        except Exception as e:
            error_msg = f"更新report_plan的response.plan字段时发生错误: {str(e)}"
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)

    def delete_search_results_by_task_id(
            self,
            task_id: str
    ) -> bool:
        """
        根据task_id删除search_results表中的对应数据

        Args:
            task_id: 任务ID

        Returns:
            bool: 删除是否成功
        """
        try:
            logger.info(f"开始删除search_results数据，任务ID: {task_id}")

            # 验证task_id参数
            if not task_id:
                raise BizError(code=ErrorCode.get_code(ErrorCode.TASK_ID_NOT_EMPTY),
                               message=ErrorCode.get_message(ErrorCode.TASK_ID_NOT_EMPTY))

            collection = mongo_db["search_results"]

            # 删除对应task_id的数据
            result = collection.delete_many(
                {"task_id": task_id}
            )

            logger.info(f"成功删除search_results数据，任务ID: {task_id}, 删除记录数: {result.deleted_count}")
            return result.deleted_count > 0

        except HTTPException:
            raise
        except Exception as e:
            error_msg = f"删除search_results数据时发生错误: {str(e)}"
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)

    def delete_response_data_by_task_id(
            self,
            task_id: str
    ) -> bool:
        """
        根据task_id删除search_response_data表中的对应数据

        Args:
            task_id: 任务ID

        Returns:
            bool: 删除是否成功
        """
        try:
            logger.info(f"开始删除search_response_data数据，任务ID: {task_id}")

            # 验证task_id参数
            if not task_id:
                raise BizError(code=ErrorCode.get_code(ErrorCode.TASK_ID_NOT_EMPTY),
                               message=ErrorCode.get_message(ErrorCode.TASK_ID_NOT_EMPTY))

            collection = mongo_db["search_response_data"]

            # 删除对应task_id的数据
            result = collection.delete_many(
                {"task_id": task_id}
            )

            logger.info(f"成功删除search_response_data数据，任务ID: {task_id}, 删除记录数: {result.deleted_count}")
            return result.deleted_count > 0

        except HTTPException:
            raise
        except Exception as e:
            error_msg = f"删除search_response_data数据时发生错误: {str(e)}"
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)

    def delete_search_summary_by_task_id(
            self,
            task_id: str
    ) -> bool:
        """
        根据task_id删除search_response_data表中的对应数据

        Args:
            task_id: 任务ID

        Returns:
            bool: 删除是否成功
        """
        try:
            logger.info(f"开始删除report_search_summary数据，任务ID: {task_id}")

            # 验证task_id参数
            if not task_id:
                raise BizError(code=ErrorCode.get_code(ErrorCode.TASK_ID_NOT_EMPTY),
                               message=ErrorCode.get_message(ErrorCode.TASK_ID_NOT_EMPTY))

            collection = mongo_db["report_search_summary"]

            # 删除对应task_id的数据
            result = collection.delete_many(
                {"task_id": task_id}
            )

            logger.info(f"成功删除report_search_summary数据，任务ID: {task_id}, 删除记录数: {result.deleted_count}")
            return result.deleted_count > 0

        except HTTPException:
            raise
        except Exception as e:
            error_msg = f"删除report_search_summary数据时发生错误: {str(e)}"
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)
    
    def delete_search_data_by_split_id(
            self,
            split_id: str
    ) -> dict:
        """
        根据split_id获取task_id，然后删除这些task_id下的所有搜索相关数据

        Args:
            split_id: 章节拆分ID

        Returns:
            dict: 删除结果统计
        """
        try:
            logger.info(f"开始根据split_id {split_id} 删除搜索相关数据")

            # 验证split_id参数
            if not split_id:
                raise BizError(code=ErrorCode.get_code(ErrorCode.SPLIT_ID_NOT_EMPTY),
                               message=ErrorCode.get_message(ErrorCode.SPLIT_ID_NOT_EMPTY))

            # 1. 根据split_id获取所有相关的task_id
            serp_task_collection = mongo_db["serp_task"]
            task_docs = serp_task_collection.find({"split_id": split_id})
            task_ids = [str(doc["_id"]) for doc in task_docs]

            if not task_ids:
                logger.info(f"未找到split_id {split_id} 相关的task_id")
                return {"message": "未找到相关的任务ID", "deleted_counts": {}}

            logger.info(f"找到split_id {split_id} 相关的task_id: {task_ids}")

            delete_results = {}
            
            # 要删除的集合列表
            collections_to_delete = [
                "search_results",
                "search_response_data",
                "report_search_summary"
            ]
            
            for collection_name in collections_to_delete:
                try:
                    collection = mongo_db[collection_name]
                    
                    # 删除对应task_id的数据
                    result = collection.delete_many(
                        {"task_id": {"$in": task_ids}}
                    )
                    
                    delete_results[collection_name] = result.deleted_count
                    logger.info(f"从集合 {collection_name} 中删除了 {result.deleted_count} 条记录，task_ids: {task_ids}")
                    
                except Exception as e:
                    logger.error(f"删除集合 {collection_name} 中的记录失败: {e}")
                    delete_results[collection_name] = 0
            
            total_deleted = sum(delete_results.values())
            logger.info(f"成功删除split_id {split_id} 相关的搜索数据，总计删除 {total_deleted} 条记录")
            
            return {
                "split_id": split_id,
                "task_ids": task_ids,
                "deleted_counts": delete_results,
                "total_deleted": total_deleted
            }

        except HTTPException:
            raise
        except Exception as e:
            error_msg = f"删除split_id {split_id} 的搜索相关数据时发生错误: {str(e)}"
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)

    def delete_search_data_by_task_id(
            self,
            task_id: str
    ) -> dict:
        """
        根据task_id删除单个任务的所有相关数据

        Args:
            task_id: 任务ID

        Returns:
            dict: 删除结果统计
        """
        try:
            logger.info(f"开始根据task_id {task_id} 删除搜索相关数据")

            # 验证task_id参数
            if not task_id:
                raise BizError(code=ErrorCode.get_code(ErrorCode.TASK_ID_NOT_EMPTY),
                               message=ErrorCode.get_message(ErrorCode.TASK_ID_NOT_EMPTY))

            # 验证task_id是否存在
            serp_task_collection = mongo_db["serp_task"]
            task_doc = serp_task_collection.find_one({"_id": ObjectId(task_id)})
            if not task_doc:
                raise BizError(code=ErrorCode.get_code(ErrorCode.TASK_NOT_EXIST),
                               message=ErrorCode.get_message(ErrorCode.TASK_NOT_EXIST))

            delete_results = {}
            
            # 要删除的集合列表
            collections_to_delete = [
                "search_results",
                "search_response_data",
                "report_search_summary"
            ]
            
            for collection_name in collections_to_delete:
                try:
                    collection = mongo_db[collection_name]
                    
                    # 删除对应task_id的数据
                    result = collection.delete_many(
                        {"task_id": task_id}
                    )
                    
                    delete_results[collection_name] = result.deleted_count
                    logger.info(f"从集合 {collection_name} 中删除了 {result.deleted_count} 条记录，task_id: {task_id}")
                    
                except Exception as e:
                    logger.error(f"删除集合 {collection_name} 中的记录失败: {e}")
                    delete_results[collection_name] = 0
            
            total_deleted = sum(delete_results.values())
            logger.info(f"成功删除task_id {task_id} 相关的搜索数据，总计删除 {total_deleted} 条记录")
            
            return {
                "task_id": task_id,
                "deleted_counts": delete_results,
                "total_deleted": total_deleted
            }

        except HTTPException:
            raise
        except Exception as e:
            error_msg = f"删除task_id {task_id} 的搜索相关数据时发生错误: {str(e)}"
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)

    # 模板管理相关方法
    def create_plan_template(self, template) -> str:
        """创建报告大纲模板"""
        try:
            collection = mongo_db["report_plan_template"]
            template_dict = template.dict()
            template_dict["_id"] = ObjectId()
            result = collection.insert_one(template_dict)
            return str(result.inserted_id)
        except Exception as e:
            logger.error(f"创建模板失败: {str(e)}")
            raise HTTPException(status_code=500, detail=f"创建模板失败: {str(e)}")

    def get_all_plan_templates(self) -> List[Dict[str, Any]]:
        """获取所有模板列表"""
        try:
            collection = mongo_db["report_plan_template"]
            cursor = collection.find({}).sort("created_at", -1)
            templates = list(cursor)
            return templates
        except Exception as e:
            logger.error(f"获取模板列表失败: {str(e)}")
            raise HTTPException(status_code=500, detail=f"获取模板列表失败: {str(e)}")

    def get_all__plan_template_split(self, parent_id: str) -> List[Dict[str, Any]]:
        """获取所有模板列表"""
        try:
            collection = mongo_db["report_plan_template_split"]
            cursor = collection.find({"parent_id": parent_id}).sort("created_at", -1)
            templates = list(cursor)
            return templates
        except Exception as e:
            logger.error(f"获取模板列表失败: {str(e)}")
            raise HTTPException(status_code=500, detail=f"获取模板列表失败: {str(e)}")

    def get_all_variable_mapping(self, parent_id: str) -> List[Dict[str, Any]]:
        """获取所有模板列表"""
        try:
            collection = mongo_db["variable_mapping"]
            cursor = collection.find({"parent_id": parent_id}).sort("created_at", -1)
            templates = list(cursor)
            return templates
        except Exception as e:
            logger.error(f"获取关系映射列表失败: {str(e)}")
            raise HTTPException(status_code=500, detail=f"获取关系映射列表失败: {str(e)}")

    def get_plan_template_by_id(self, template_id: str) -> Optional[Dict[str, Any]]:
        """根据ID获取模板"""
        try:
            collection = mongo_db["report_plan_template"]
            template = collection.find_one({"_id": ObjectId(template_id)})
            return template
        except Exception as e:
            logger.error(f"获取模板详情失败: {str(e)}")
            raise HTTPException(status_code=500, detail=f"获取模板详情失败: {str(e)}")

    def update_plan_template(self, template_id: str, update_data: Dict[str, Any]) -> bool:
        """更新模板"""
        try:
            collection = mongo_db["report_plan_template"]
            result = collection.update_one(
                {"_id": ObjectId(template_id)},
                {"$set": update_data}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"更新模板失败: {str(e)}")
            raise HTTPException(status_code=500, detail=f"更新模板失败: {str(e)}")

    def delete_plan_template(self, template_id: str) -> bool:
        """删除模板"""
        try:
            collection = mongo_db["report_plan_template"]
            result = collection.delete_one({"_id": ObjectId(template_id)})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"删除模板失败: {str(e)}")
            raise HTTPException(status_code=500, detail=f"删除模板失败: {str(e)}")


    def update_report_template_status(self, report_id: str, template_status: bool, template_id: str = None) -> bool:
        """更新报告的模板状态"""
        try:
            collection = mongo_db["reports"]
            update_data = {
                "template_status": template_status,
                "updated_at": datetime.datetime.now()
            }
            if template_id:
                update_data["template_id"] = template_id
            
            result = collection.update_one(
                {"_id": ObjectId(report_id)},
                {"$set": update_data}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"更新报告模板状态失败: {str(e)}")
            raise HTTPException(status_code=500, detail=f"更新报告模板状态失败: {str(e)}")

    def update_report_introduction(self, report_id: str,introduction: str = None) -> bool:
        """更新报告的模板状态"""
        try:
            collection = mongo_db["reports"]
            update_data = {
                "introduction": introduction,
                "updated_at": datetime.datetime.now()
            }
            if introduction:
                update_data["introduction"] = introduction

            result = collection.update_one(
                {"_id": ObjectId(report_id)},
                {"$set": update_data}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"更新报告引言失败: {str(e)}")
            raise HTTPException(status_code=500, detail=f"更新报告引言失败: {str(e)}")

    def get_introduction(self,report_id: str) -> str:
        try:
            logger.info(f"开始获取introduction，报告ID: {report_id}")

            # 转换为ObjectId
            try:
                object_id = ObjectId(report_id)
            except Exception:
                raise BizError(code=ErrorCode.get_code(ErrorCode.DATA_FORMAT_ERROR),
                               message=ErrorCode.get_message(ErrorCode.DATA_FORMAT_ERROR))

            collection = mongo_db["reports"]  # 统一使用reports集合

            # 查找报告文档
            report_doc = collection.find_one({"_id": object_id})

            if not report_doc:
                raise BizError(code=ErrorCode.get_code(ErrorCode.REPORT_NOT_EXIST),
                               message=ErrorCode.get_message(ErrorCode.REPORT_NOT_EXIST))

            # 提取LLM响应数据
            introduction = report_doc.get("introduction", "")
            logger.info(f"成功获取introduction，报告ID: {report_id}")
            return introduction

        except HTTPException:
            raise
        except Exception as e:
            error_msg = f"获取introduction时发生错误: {str(e)}"
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)

    def get_report_summary(self,report_id: str) -> str:
        try:
            logger.info(f"开始获取report_summary，报告ID: {report_id}")

            # 转换为ObjectId
            try:
                object_id = ObjectId(report_id)
            except Exception:
                raise BizError(code=ErrorCode.get_code(ErrorCode.DATA_FORMAT_ERROR),
                               message=ErrorCode.get_message(ErrorCode.DATA_FORMAT_ERROR))

            collection = mongo_db["reports"]  # 统一使用reports集合

            # 查找报告文档
            report_doc = collection.find_one({"_id": object_id})

            if not report_doc:
                raise BizError(code=ErrorCode.get_code(ErrorCode.REPORT_NOT_EXIST),
                               message=ErrorCode.get_message(ErrorCode.REPORT_NOT_EXIST))

            # 提取LLM响应数据
            summary = report_doc.get("summary", "")
            logger.info(f"成功获取report_summary，报告ID: {report_id}")
            return summary

        except HTTPException:
            raise
        except Exception as e:
            error_msg = f"获取report_summary时发生错误: {str(e)}"
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)


# 创建全局实例
mongo_api_service_manager = MongoAPIServiceManager()