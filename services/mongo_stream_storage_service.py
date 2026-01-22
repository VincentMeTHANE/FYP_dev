"""
MongoDB流式输出存储服务 - 统一处理流式输出、内容收集和MongoDB存储（纯MongoDB版本）
"""

import logging
import datetime
import json
import asyncio
from typing import AsyncGenerator, Dict, Any, Optional, Callable
from fastapi.responses import StreamingResponse
from bson import ObjectId

from services.llm_service import LLMService
from utils.database import mongo_db

logger = logging.getLogger(__name__)


class MongoStreamStorageService:
    """MongoDB流式输出存储服务（纯MongoDB版本）"""
    
    def __init__(self):
        self.llm_service = LLMService()
    
    def create_stream_response(
        self,
        query: str,
        query_type: str,
        prompt_builder: Callable,
        report_id: str,  # ObjectId字符串
        use_mcp: bool = False,
        model: Optional[str] = None
    ) -> StreamingResponse:
        """
        创建流式响应，自动处理内容收集和MongoDB存储（纯MongoDB版本）
        
        Args:
            query: 用户查询内容
            query_type: 查询类型
            prompt_builder: 提示词构建函数
            report_id: 报告ID（ObjectId字符串）
            use_mcp: 是否使用MCP功能
            model: 指定使用的LLM模型名称，如果为None则使用默认模型
            
        Returns:
            StreamingResponse: 流式响应对象
        """
        collection_name = "reports"  # 统一使用reports集合
            
        try:
            # 转换为ObjectId
            object_id = ObjectId(report_id)
            
            # 构建提示词
            if isinstance(prompt_builder, str):
                system_prompt = prompt_builder
            else:
                system_prompt = prompt_builder(query)
            
            logger.info(f"开始创建流式响应，报告ID: {report_id}, 查询类型: {query_type}")
            
            # 创建流式生成器
            async_generator = self._create_stream_generator(
                query=query,
                system_prompt=system_prompt,
                object_id=object_id,
                query_type=query_type,
                collection_name=collection_name,
                use_mcp=use_mcp,
                model=model
            )
            
            return StreamingResponse(
                async_generator,
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
            )
            
        except Exception as e:
            error_msg = f"创建流式响应失败: {str(e)}"
            logger.error(error_msg)
            
            # 返回错误的流式响应
            async def error_generator():
                yield f"data: {json.dumps({'error': error_msg})}\n\n"
            
            return StreamingResponse(
                error_generator(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
            )
    
    async def _create_stream_generator(
        self,
        query: str,
        system_prompt: str,
        object_id: ObjectId,
        query_type: str,
        collection_name: str,
        use_mcp: bool = False,
        model: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """创建流式数据生成器（纯MongoDB版本）"""
        
        chunks = []
        start_time = datetime.datetime.now()
        
        try:
            # 获取流式响应
            async for chunk in self.llm_service.stream(system_prompt, use_mcp=use_mcp, model=model):
                # 解析SSE行为JSON对象
                parsed_chunk = self._parse_sse_chunk(chunk)
                if parsed_chunk:
                    chunks.append(parsed_chunk)
                    yield f"data: {json.dumps(parsed_chunk)}\n\n"
                else:
                    # 直接传递原始chunk（如果解析失败）
                    yield chunk
            
            # 发送结束信号
            yield "data: [DONE]\n\n"
            
            # 异步存储到MongoDB
            asyncio.create_task(
                self._store_to_mongodb(
                    object_id=object_id,
                    query=query,
                    query_type=query_type,
                    collection_name=collection_name,
                    chunks=chunks,
                    system_prompt=system_prompt,
                    start_time=start_time
                )
            )
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"流式生成器执行失败: {e}")
            logger.error(f"流式生成器执行失败: {error_msg}")
            
            # 更新失败状态
            try:
                end_time = datetime.datetime.now()
                execution_time = (end_time - start_time).total_seconds()
                
                collection = mongo_db[collection_name]
                collection.update_one(
                    {"_id": object_id},
                    {
                        "$set": {
                            "status": "failed",
                            "updated_at": end_time,
                            "end_time": end_time,
                            "execution_time": execution_time,
                            "error_message": error_msg
                        }
                    }
                )
            except Exception as update_error:
                logger.error(f"更新失败状态时出错: {update_error}")
            
            # 发送错误信息
            yield f"data: {json.dumps({'error': error_msg})}\n\n"
            yield "data: [DONE]\n\n"
    
    async def _store_to_mongodb(
        self,
        object_id: ObjectId,
        query: str,
        query_type: str,
        collection_name: str,
        chunks: list,
        system_prompt: str,
        start_time: datetime.datetime
    ):
        """异步存储流式内容到MongoDB（纯MongoDB版本）"""
        
        try:
            end_time = datetime.datetime.now()
            execution_time = (end_time - start_time).total_seconds()
            
            # 收集所有内容
            full_content = self._collect_content_from_chunks(chunks)
            
            # 构造标准的LLM响应格式
            llm_response = {
                "id": f"stream-{object_id}",
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
                    "prompt_tokens": len(system_prompt.split()),
                    "completion_tokens": len(full_content.split()),
                    "total_tokens": len(system_prompt.split()) + len(full_content.split())
                }
            }
            
            # 内容预览
            content_preview = full_content[:100] if full_content else ""
            
            # 更新MongoDB文档
            collection = mongo_db[collection_name]
            update_data = {
                "status": "completed",
                "updated_at": end_time,
                "end_time": end_time,
                "execution_time": execution_time,
                "llm_response": llm_response,
                "content_preview": content_preview,
                "additional_data": {
                    "prompt_used": system_prompt,
                    "chunks_count": len(chunks),
                    "stream_type": "server_sent_events"
                }
            }
            
            result = collection.update_one(
                {"_id": object_id},
                {"$set": update_data}
            )
            
            if result.modified_count > 0:
                logger.info(f"流式内容存储成功，报告ID: {object_id}, 内容长度: {len(full_content)}")
            else:
                logger.warning(f"流式内容存储可能失败，报告ID: {object_id}")
                
        except Exception as e:
            logger.error(f"流式内容存储到MongoDB失败: {str(e)}")
    
    def _collect_content_from_chunks(self, chunks: list) -> str:
        """从流式chunks中收集完整内容"""
        content_parts = []
        
        for chunk in chunks:
            if isinstance(chunk, dict):
                choices = chunk.get("choices", [])
                for choice in choices:
                    delta = choice.get("delta", {})
                    
                    # 处理普通内容
                    if "content" in delta and delta["content"]:
                        content_parts.append(delta["content"])
                    
                    # 处理推理内容（如果有）
                    if "reasoning_content" in delta and delta["reasoning_content"]:
                        content_parts.append(delta["reasoning_content"])
        
        return "".join(content_parts)
    
    def _parse_sse_chunk(self, chunk: str) -> Optional[Dict[str, Any]]:
        """解析SSE行为JSON对象"""
        try:
            # SSE格式通常是 "data: {json}\n\n"
            if chunk.startswith("data: "):
                json_str = chunk[6:].strip()  # 移除 "data: " 前缀
                if json_str and json_str != "[DONE]":
                    return json.loads(json_str)
            return None
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"解析SSE chunk失败: {chunk[:100]}..., 错误: {e}")
            return None


# 创建全局实例
mongo_stream_storage_service = MongoStreamStorageService()