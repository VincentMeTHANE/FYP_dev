#!/usr/bin/env python3
"""
深度研究 搜索总结API路由模块
"""

import logging
import datetime,json,ast
import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException  # type: ignore
from reportlab.platypus.tableofcontents import TableOfContents
from starlette.responses import StreamingResponse

from models.models import LLMMessageFinal
from services.llm_service import llm_service
from services.mongo_api_service_manager import mongo_api_service_manager
from services.report_service import report_service
from utils.database import mongo_db
from bson import ObjectId
from services.step_record_service import step_record_service
from utils.distributed_lock import create_async_lock
from config import settings
from fastapi.responses import Response




# 创建PDF
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.platypus import Paragraph, Spacer, PageBreak, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from io import BytesIO
import urllib.parse
import re
# 创建自定义样式，支持中文
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily
import httpx
# 创建带页码和目录跳转功能的文档模板
from reportlab.platypus import BaseDocTemplate, PageTemplate, Frame
from utils.exception_handler import ErrorCode
from utils.response_models import Result, BizError

from utils.ai_tool_api import convert_markdown_to_format, call_template_padding_api

logger = logging.getLogger(__name__)

router = APIRouter()

async def get_final_report_content_by_report_id(report_id: str) -> str:
    """
    根据report_id获取所有finalReport集合中的内容，按chapter_index排序
    
    Args:
        report_id: 报告ID
        
    Returns:
        str: 按章节顺序排列的完整报告内容
    """
    try:
        # 从report_final集合中获取所有该report_id的记录，按chapter_index排序
        final_report_collection = mongo_db["report_final"]
        final_docs = list(final_report_collection.find({"report_id": report_id}).sort("chapter_index", 1))
        
        if not final_docs:
            logger.warning(f"报告 {report_id} 没有找到任何report_final记录")
            return ""
        
        # 按chapter_index排序并拼接内容
        full_content = ""
        for doc in final_docs:
            content = doc.get("current", "")
            if content:
                full_content += content + "\n\n"
        
        logger.info(f"成功获取报告 {report_id} 的完整内容，共 {len(final_docs)} 个章节")
        return full_content
        
    except Exception as e:
        logger.error(f"获取报告完整内容失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取报告内容失败: {str(e)}")

async def check_and_update_final_report_completion(report_id: str, split_id: str):
    """
    检查当前split是否为最后一个章节，如果是则更新最终报告完成状态
    使用分布式锁避免并发竞争条件
    
    Args:
        report_id: 报告ID
        split_id: 分割ID
    """
    # 创建分布式锁，锁的key基于report_id，确保同一报告只有一个请求能更新完成状态
    lock_key = f"final_report_completion_{report_id}"
    lock = create_async_lock(lock_key, timeout=30, retry_interval=0.1)
    
    try:
        # 尝试获取分布式锁，最多等待5秒
        if not await lock.acquire(blocking=True, timeout=5):
            logger.warning(f"获取分布式锁失败，跳过更新最终报告完成状态: {report_id}")
            return
        
        # 1. 获取该report_id下的所有split记录
        split_collection = mongo_db["report_plan_split"]
        split_docs = list(split_collection.find({"report_id": report_id}))
        
        if not split_docs:
            logger.warning(f"报告 {report_id} 没有找到任何split记录")
            return
        
        # 2. 获取所有split的chapter_index，找到最大值
        split_chapter_indexes = [doc.get("chapter_index") for doc in split_docs if doc.get("chapter_index") is not None]
        
        if not split_chapter_indexes:
            logger.warning(f"报告 {report_id} 的split记录中没有chapter_index信息")
            return
        
        max_chapter_index = max(split_chapter_indexes)
        
        # 3. 根据split_id获取当前章节的chapter_index
        current_split_doc = split_collection.find_one({"_id": ObjectId(split_id)})
        if not current_split_doc:
            logger.warning(f"未找到split_id {split_id} 对应的记录")
            return
        
        current_chapter_index = current_split_doc.get("chapter_index")
        if current_chapter_index is None:
            logger.warning(f"split_id {split_id} 对应的记录中没有chapter_index信息")
            return
        
        # 4. 检查当前章节是否为最后一个章节
        if current_chapter_index == max_chapter_index:
            # 5. 在锁保护下更新最终报告完成状态
            now = datetime.datetime.now()
            
            # 先检查是否已经被其他请求更新了
            existing_report = mongo_db["reports"].find_one({"_id": ObjectId(report_id)})
            if existing_report and existing_report.get("isFinalReportCompleted"):
                logger.info(f"报告 {report_id} 的最终报告完成状态已被其他请求更新")
                return
            
            # 更新最终报告完成状态
            update_data = {
                "isFinalReportCompleted": True,
                "updated_at": now
            }
            
            result = mongo_db["reports"].update_one(
                {"_id": ObjectId(report_id)},
                {"$set": update_data}
            )
            
            if result.modified_count > 0:
                logger.info(f"最后一个章节已完成，更新最终报告完成状态成功: {report_id}")
            else:
                logger.warning(f"更新最终报告完成状态失败: {report_id}")
        else:
            logger.info(f"报告 {report_id} 当前章节 {current_chapter_index} 不是最后一个章节，最大章节为 {max_chapter_index}")
            
    except Exception as e:
        logger.error(f"检查最终报告完成状态失败: {str(e)}")
    finally:
        # 确保释放锁
        try:
            await lock.release()
        except Exception as e:
            logger.error(f"释放分布式锁失败: {str(e)}")

async def get_final_report_data(report_id: str, split_id: str) -> dict:
    """
    根据report_id和split_id获取最终报告所需的数据
    
    Args:
        report_id: 报告ID
        split_id: 分割ID
        
    Returns:
        dict: 包含plan, learnings, sources, images, current的数据字典
    """
    try:
        # 1. 从write_report_plan库中根据report_id查找plan内容
        plan_collection = mongo_db["report_plan"]
        plan_doc = plan_collection.find_one({"report_id": report_id})
        plan = plan_doc.get("response", {}).get("plan", "") if plan_doc else ""
        
        # 2. 根据report_id和split_id从summary库中获取summary列表
        learnings = ""
        # 根据报告和split_id从summary库中获取summary列表
        summary_collection = mongo_db["report_search_summary"]
        summary_docs = summary_collection.find({"report_id": report_id, "split_id": split_id})
        list_summary_docs = list(summary_docs)
        logger.info(f"summary_docs length: {len(list_summary_docs)}")
        for summary_doc in list_summary_docs:
            choices = summary_doc["response"].get("choices", [])
            if choices and len(choices) > 0:
                learnings += choices[0].get("message", {}).get("content", "") + "\n"
        
        # 3. 首先从serp_task库的split_id字段中搜索具有相同split_id的task_id，再根据task_id从search_results集合中搜索所有相同的task_id字段，从search_results中获取所有记录的内容
        serp_task_collection = mongo_db["serp_task"]
        serp_task_docs = serp_task_collection.find({"split_id": split_id})
        sources = []
        images = []
        for serp_task_doc in serp_task_docs:
            task_id = str(serp_task_doc["_id"])
            search_results_collection = mongo_db["search_results"]
            search_docs = search_results_collection.find({"task_id": task_id})
            for search_doc in search_docs:
                # 获取sources信息
                title = search_doc.get("title", "")
                url = search_doc.get("url", "")
                sources.append(f"{title} - {url}")
                
                # 获取images信息（现在直接从每条记录的images字段获取）
                if "images" in search_doc and isinstance(search_doc["images"], list):
                    for image in search_doc["images"]:
                        description = image.get("description", "")
                        image_url = image.get("url", "")
                        images.append(f"{description} - {image_url}")
        
        # images 按URL去重
        unique_images = []
        seen_urls = set()
        for img_str in images:
            # 从字符串中提取URL（格式：description - url）
            if " - " in img_str:
                parts = img_str.split(" - ", 1)
                if len(parts) == 2:
                    description, image_url = parts
                    if image_url not in seen_urls:
                        seen_urls.add(image_url)
                        unique_images.append(img_str)
                else:
                    # 如果格式不符合预期，直接添加
                    unique_images.append(img_str)
            else:
                # 如果格式不符合预期，直接添加
                unique_images.append(img_str)
        images = unique_images
        # 5. split_id在report_plan_split集合中对应的response.content
        split_collection = mongo_db["report_plan_split"]
        split_doc = split_collection.find_one({"_id": ObjectId(split_id)})
        current = ""
        if split_doc and "response" in split_doc:
            content_list = split_doc["response"].get("content", [])
            if content_list:
                current = content_list[0]
        
        return {
            "plan": plan,
            "learnings": learnings,
            "sources": sources,
            "images": images,
            "current": current,
            "chapter_index": split_doc.get("chapter_index", 0),

        }
        
    except Exception as e:
        logger.error(f"获取最终报告数据失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取数据失败: {str(e)}")

@router.post("/stream")
async def chat_stream(
    dto: LLMMessageFinal
):
    """
    流式搜索总结 - 需要有效的report_id和split_id
    """
    start_time = datetime.datetime.now()
    
    try:
        # 1. 验证参数
        if not dto.report_id or not dto.split_id:
            raise BizError(code=ErrorCode.get_code(ErrorCode.FINAL_NEED_EFFECTIVE),
                           message=ErrorCode.get_message(ErrorCode.FINAL_NEED_EFFECTIVE))
        
        report_id = dto.report_id
        
        # 2. 获取数据
        data = await get_final_report_data(dto.report_id, dto.split_id)
        # 根据报告id获取report的数据
        current_report = report_service.get_report(report_id)
        template_content = None
        if current_report and hasattr(current_report, 'template') and current_report.template:
            # template字段存储的是template_id，需要查询report_plan_template集合获取实际内容
            template_id = current_report.template
            template = mongo_api_service_manager.get_plan_template_by_id(template_id)
            if template:
                template_content = template.get("content", "")
                logger.info(f"使用报告中的模板内容生成流式大纲，报告ID: {report_id}, 模板ID: {template_id}")
            else:
                logger.warning(f"模板不存在，模板ID: {template_id}")
        else:
            logger.info(f"报告中没有模板ID，使用默认方式生成流式大纲，报告ID: {report_id}")

        # 3. 开始步骤
        report_service.start_step(report_id, "final_report")
        
        # 查询已经生成的报告内容
        report_content = mongo_api_service_manager.get_detail_by_report_final_id(report_id=report_id)
        # 打印prompt用于调试 - 稍后删除
        prompt_content = prompt(current_report.title, data["plan"], data["learnings"], data["sources"], data["images"], dto.requirement, data["current"], template_content, report_content)
        logger.info(f"Stream接口使用的prompt: {prompt_content}")
        
        # 异步更新完成状态的任务
        async def update_completion_status():
            await asyncio.sleep(3)  # 给流式处理一些时间
            try:
                end_time = datetime.datetime.now()
                execution_time = (end_time - start_time).total_seconds()
                
                # 检查步骤是否还在处理中，如果是则标记为完成
                if current_report and current_report.steps.final_report.status == "processing":
                    report_service.complete_step(
                        report_id, "final_report",
                        execution_time=execution_time
                    )
            except Exception as e:
                logger.error(f"更新流式处理状态失败: {str(e)}")
                # 如果更新失败，标记为失败状态
                end_time = datetime.datetime.now()
                execution_time = (end_time - start_time).total_seconds()
                report_service.fail_step(
                    report_id, "final_report",
                    error_message=str(e),
                    execution_time=execution_time
                )
        
        # 启动后台任务
        asyncio.create_task(update_completion_status())

        # 定义一个收集完整响应的变量
        chunks = []
        # 创建一个包装的流式响应生成器
        async def wrapped_stream_generator():
            nonlocal chunks
            try:
                # 获取原始流式响应
                original_response = await mongo_api_service_manager.execute_stream_api(
                    query=f"基于分割ID {dto.split_id} 的最终报告生成",
                    query_type="final_report",
                    title_prefix="搜索总结",
                    prompt_builder=prompt_content,
                    report_id=report_id,
                    model="report_final"
                )

                # 逐个yield数据块
                async for chunk in original_response.body_iterator:
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
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0
                    }
                }

                #  保存数据库记录前先判断下是否已经存在split_id的记录 存在就删除原来的 再新增
                step_record_service.delete_final_report(report_id, dto.split_id)

                # 更新数据库记录，包含完整响应
                step_record_service.create_final_report(report_id, dto.split_id,data["chapter_index"],str(full_content))
                
                # 检查当前split是否为最后一个章节，如果是则更新最终报告完成状态
                await check_and_update_final_report_completion(report_id, dto.split_id)
                
                # report_service.complete_step(
                #     report_id, "final_report",
                #     result=llm_response,
                #     execution_time=(datetime.datetime.now() - start_time).total_seconds()
                # )
            except Exception as stream_e:

                # 处理流式传输中的错误
                report_service.fail_step(
                    report_id, "final_report",
                    error_message=str(stream_e),
                    execution_time=(datetime.datetime.now() - start_time).total_seconds()
                )

                logger.error(f"流式传输过程中发生错误: {str(stream_e)}")
                raise

        # 返回包装后的流式响应
        return StreamingResponse(
            wrapped_stream_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
        )

        # return await mongo_api_service_manager.execute_stream_api(
        #     query=f"基于分割ID {dto.split_id} 的最终报告生成",
        #     query_type="final_report",
        #     title_prefix="搜索总结",
        #     prompt_builder=prompt(data["plan"], data["learnings"], data["sources"], data["images"], dto.requirement, data["current"]),
        #     report_id=report_id
        # )
        
    except Exception as e:
        # 标记步骤失败
        if 'report_id' in locals():
            end_time = datetime.datetime.now()
            execution_time = (end_time - start_time).total_seconds()
            
            report_service.fail_step(
                report_id, "final_report",
                error_message=str(e),
                execution_time=execution_time
            )
        
        logger.error(f"流式搜索总结API失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"流式搜索总结失败: {str(e)}")


@router.post("/summary/{report_id}")
async def generate_report_summary(report_id: str):
    """
    生成报告总结 - 流式输出，输入report_id生成全文总结
    """
    start_time = datetime.datetime.now()
    
    try:
        # 1. 验证参数
        if not report_id:
            raise BizError(code=ErrorCode.get_code(ErrorCode.FINAL_NEED_EFFECTIVE),
                           message=ErrorCode.get_message(ErrorCode.FINAL_NEED_EFFECTIVE))
        
        # 2. 获取完整的报告内容
        full_content = await get_final_report_content_by_report_id(report_id)
        
        if not full_content:
            raise BizError(code=ErrorCode.get_code(ErrorCode.REPORT_NOT_EXIST),
                           message="报告内容为空，无法生成总结")
        
        # 3. 开始步骤
        report_service.start_step(report_id, "summary_generation")
        
        # 打印prompt用于调试
        prompt_content = summary_prompt(full_content)
        logger.info(f"Summary接口使用的prompt: {prompt_content}")
        
        # 异步更新完成状态的任务
        async def update_completion_status():
            await asyncio.sleep(3)  # 给流式处理一些时间
            try:
                end_time = datetime.datetime.now()
                execution_time = (end_time - start_time).total_seconds()
                
                # 检查步骤是否还在处理中，如果是则标记为完成
                current_report = report_service.get_report(report_id)
                if current_report and current_report.steps.summary_generation.status == "processing":
                    report_service.complete_step(
                        report_id, "summary_generation",
                        execution_time=execution_time
                    )
            except Exception as e:
                logger.error(f"更新流式处理状态失败: {str(e)}")
                # 如果更新失败，标记为失败状态
                end_time = datetime.datetime.now()
                execution_time = (end_time - start_time).total_seconds()
                report_service.fail_step(
                    report_id, "summary_generation",
                    error_message=str(e),
                    execution_time=execution_time
                )
        
        # 启动后台任务
        asyncio.create_task(update_completion_status())

        # 定义一个收集完整响应的变量
        chunks = []
        # 创建一个包装的流式响应生成器
        async def wrapped_stream_generator():
            nonlocal chunks
            try:
                # 获取原始流式响应
                original_response = await mongo_api_service_manager.execute_stream_api(
                    query=f"基于报告ID {report_id} 的总结生成",
                    query_type="summary_generation",
                    title_prefix="报告总结",
                    prompt_builder=prompt_content,
                    report_id=report_id,
                    model="report_final"
                )

                # 逐个yield数据块
                async for chunk in original_response.body_iterator:
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

                # 构造标准的LLM响应格式（与completion接口保持一致）
                llm_response = {
                    "id": f"summary-{report_id}",
                    "object": "chat.completion",
                    "created": int(start_time.timestamp()),
                    "model": "summary-model",
                    "choices": [{
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": full_content
                        },
                        "finish_reason": "stop"
                    }],
                    "usage": {
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0
                    }
                }

                # 将总结内容存储到reports集合的summary字段
                try:
                    now = datetime.datetime.now()
                    update_data = {
                        "summary": str(full_content),
                        "updated_at": now
                    }
                    
                    # 执行更新
                    result = mongo_db["reports"].update_one(
                        {"_id": ObjectId(report_id)},
                        {"$set": update_data}
                    )
                    
                    if result.modified_count > 0:
                        logger.info(f"成功保存报告总结到数据库: {report_id}")
                    else:
                        logger.warning(f"保存报告总结失败: {report_id}")
                        
                except Exception as e:
                    logger.error(f"保存报告总结到数据库失败: {str(e)}")
                
            except Exception as stream_e:
                # 处理流式传输中的错误
                report_service.fail_step(
                    report_id, "summary_generation",
                    error_message=str(stream_e),
                    execution_time=(datetime.datetime.now() - start_time).total_seconds()
                )

                logger.error(f"流式传输过程中发生错误: {str(stream_e)}")
                raise

        # 返回包装后的流式响应
        return StreamingResponse(
            wrapped_stream_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
        )
        
    except Exception as e:
        # 标记步骤失败
        if 'report_id' in locals():
            end_time = datetime.datetime.now()
            execution_time = (end_time - start_time).total_seconds()
            
            report_service.fail_step(
                report_id, "summary_generation",
                error_message=str(e),
                execution_time=execution_time
            )
        
        logger.error(f"生成报告总结API失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"生成报告总结失败: {str(e)}")


@router.get("/download/pdf/{report_id}")
async def download_final_report_markdown(
    report_id: str
):
    """
    根据报告ID获取详细信息 - 返回PDF格式文档（使用Markdown转换）
    """
    try:
        # 获取报告内容
        report_content = mongo_api_service_manager.get_detail_by_report_final_id(
            report_id=report_id
        )

        if not report_content:
            raise BizError(code=ErrorCode.get_code(ErrorCode.REPORT_NOT_EXIST),
                           message=ErrorCode.get_message(ErrorCode.REPORT_NOT_EXIST))

        report_title = mongo_api_service_manager.get_report_message_by_report_id(report_id)

        results = mongo_api_service_manager.get_results_report_id(report_id)

        serp_list = mongo_api_service_manager.get_serp_by_report_id(report_id)

        # 获取报告引言
        report_introduction = mongo_api_service_manager.get_introduction(report_id)

        report_summary = mongo_api_service_manager.get_report_summary(report_id)

        # 生成 PDF 字节流
        pdf_bytes = get_pdf_bytes(report_content, report_title, results,report_introduction,report_summary)

        # 使用ASCII安全的文件名
        ascii_filename = f"deep_research_report_{report_id}.pdf"
        # 对中文文件名进行URL编码
        utf8_filename = f"{report_title}深度研究报告.pdf"
        encoded_filename = urllib.parse.quote(utf8_filename.encode('utf-8'))
        # 返回 PDF 文件流
        headers = {
            "Content-Disposition": f"attachment; filename={ascii_filename}; filename*=UTF-8''{encoded_filename}"
        }
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers=headers
        )

    except Exception as e:
        logger.error(f"生成PDF报告失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"生成PDF报告失败: {str(e)}")


@router.get("/download/word1/{report_id}")
async def download_final_report_markdown(
    report_id: str
):
    """
    根据报告ID获取详细信息 - 返回PDF格式文档（使用Markdown转换）
    """
    try:
        # 获取报告内容
        report_content = mongo_api_service_manager.get_detail_by_report_final_id(
            report_id=report_id
        )

        if not report_content:
            raise BizError(code=ErrorCode.get_code(ErrorCode.REPORT_NOT_EXIST),
                           message=ErrorCode.get_message(ErrorCode.REPORT_NOT_EXIST))

        report_title = mongo_api_service_manager.get_report_message_by_report_id(report_id)

        results = mongo_api_service_manager.get_results_report_id(report_id)

        serp_list = mongo_api_service_manager.get_serp_by_report_id(report_id)

        # 获取报告引言
        report_introduction = mongo_api_service_manager.get_introduction(report_id)

        report_summary = mongo_api_service_manager.get_report_summary(report_id)

        # 生成 PDF 字节流
        # pdf_bytes = get_pdf_bytes(report_content, report_title, results,report_introduction,report_summary)
        # 准备Markdown内容
        markdown_content = "# 标题\n\n这是内容\n\n- 列表项1\n- 列表项2"
        # 转换为docx格式
        pdf_bytes = convert_markdown_to_format(markdown_content,"docx")

        # 使用ASCII安全的文件名
        ascii_filename = f"deep_research_report_{report_id}.docx"
        # 对中文文件名进行URL编码
        utf8_filename = f"{report_title}深度研究报告.docx"
        encoded_filename = urllib.parse.quote(utf8_filename.encode('utf-8'))
        # 返回 PDF 文件流
        headers = {
            "Content-Disposition": f"attachment; filename={ascii_filename}; filename*=UTF-8''{encoded_filename}"
        }
        return Response(
            content=pdf_bytes,
            media_type="application/docx",
            headers=headers
        )

    except Exception as e:
        logger.error(f"生成docx报告失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"生成docx报告失败: {str(e)}")



def generate_markdown_content1(report_content: str,
                              report_title: str,
                              report_introduction: str = "",
                              report_summary: str = "") -> str:
    """
    生成Markdown格式的报告内容

    Args:
        report_content: 报告主要内容
        report_title: 报告标题
        report_introduction: 报告引言（可选）
        report_summary: 报告总结（可选）

    Returns:
        str: Markdown格式的完整报告内容
    """
    # 初始化Markdown内容
    markdown_parts = []

    # 添加标题
    markdown_parts.append(f"# {report_title}")
    markdown_parts.append("")  # 空行

    # 添加引言（如果存在）
    if report_introduction and report_introduction.strip():
        markdown_parts.append("## 引言")
        markdown_parts.append("")
        # 处理引言内容，保持段落格式
        intro_lines = report_introduction.strip().split('\n')
        for line in intro_lines:
            if line.strip():
                markdown_parts.append(line.strip())
            else:
                markdown_parts.append("")  # 保留空行
        markdown_parts.append("")  # 额外空行分隔

    # 添加主要内容
    if report_content and report_content.strip():
        # 直接添加主要内容，保持原有格式
        markdown_parts.append(report_content.strip())
        markdown_parts.append("")  # 内容后添加空行

    # 添加总结（如果存在）
    if report_summary and report_summary.strip():
        markdown_parts.append("## 总结")
        markdown_parts.append("")
        # 处理总结内容
        summary_lines = report_summary.strip().split('\n')
        for line in summary_lines:
            if line.strip():
                markdown_parts.append(line.strip())
            else:
                markdown_parts.append("")  # 保留空行
        markdown_parts.append("")  # 最后的空行

    # 连接所有部分
    return "\n".join(markdown_parts)


def generate_markdown_content(report_content: str,
                              report_title: str,
                              report_introduction: str = "",
                              report_summary: str = "",
                              results: list = None) -> str:
    """
    生成Markdown格式的报告内容，包含参考文献

    Args:
        report_content: 报告主要内容
        report_title: 报告标题
        report_introduction: 报告引言（可选）
        report_summary: 报告总结（可选）
        results: 参考文献列表（可选）

    Returns:
        str: Markdown格式的完整报告内容
    """
    # 初始化Markdown内容
    markdown_parts = [f"# {report_title}", ""]

    # 添加引言（如果存在）
    if report_introduction and report_introduction.strip():
        markdown_parts.append("## 引言")
        markdown_parts.append("")
        intro_lines = report_introduction.strip().split('\n')
        for line in intro_lines:
            if line.strip():
                markdown_parts.append(line.strip())
            else:
                markdown_parts.append("")
        markdown_parts.append("")

    # 添加主要内容
    if report_content and report_content.strip():
        markdown_parts.append(report_content.strip())
        markdown_parts.append("")

    # 添加总结（如果存在）
    if report_summary and report_summary.strip():
        markdown_parts.append("## 总结")
        markdown_parts.append("")
        summary_lines = report_summary.strip().split('\n')
        for line in summary_lines:
            if line.strip():
                markdown_parts.append(line.strip())
            else:
                markdown_parts.append("")
        markdown_parts.append("")

    # 添加参考文献（如果存在）
    if results and isinstance(results, list) and len(results) > 0:
        markdown_parts.append("## 参考文献")
        markdown_parts.append("")
        for i, ref in enumerate(results, 1):
            title = ref.get("title", "")
            url = ref.get("url", "")
            result_index = ref.get("result_index", "")
            markdown_parts.append(f"{i}. {title} [[{result_index}]({url})]")
        markdown_parts.append("")

    # 连接所有部分
    return "\n".join(markdown_parts)


def convert_report_content_to_padding_rules(report_content) -> dict:
    """
    将report_content数据转换为padding_rules_data格式

    Args:
        report_content: 包含报告内容的数据（可能是字典、JSON字符串或换行符拼接的字符串）

    Returns:
        dict: 转换后的padding_rules_data格式字典
    """
    # 如果是字符串类型，首先尝试解析为JSON
    if isinstance(report_content, str):
        # 尝试解析为JSON对象
        try:
            import json
            parsed_content = json.loads(report_content)
            if isinstance(parsed_content, dict):
                return parsed_content
        except (json.JSONDecodeError, ValueError):
            pass  # 如果JSON解析失败，继续处理字符串

        # 如果不是有效的JSON，按换行符分割处理
        padding_rules_data = {}
        lines = report_content.split('\n')

        for line in lines:
            line = line.strip()
            if line and ':' in line:
                # 尝试按冒号分割键值对
                parts = line.split(':', 1)
                if len(parts) == 2:
                    key = parts[0].strip()
                    value = parts[1].strip()
                    # 去除可能的引号
                    if value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]
                    elif value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    padding_rules_data[key] = value
        return padding_rules_data

    # 如果已经是字典类型，直接返回
    if isinstance(report_content, dict):
        return report_content

    # 其他情况，返回包含原始内容的字典
    return {"content": str(report_content)}


def merge_multiple_dicts_from_string(report_content_str: str) -> dict:
    """
    将一个包含多个字典的字符串（例如 "{'a':1} {'b':2} {'c':3}"）
    解析并合并成一个单一的字典。

    Args:
        report_content_str (str): 包含一个或多个字典的字符串。

    Returns:
        dict: 合并后的字典。如果解析失败，则返回空字典。
    """
    if not report_content_str:
        return {}

    # 步骤 1: 使用正则表达式在每个字典之间插入逗号
    # 正则表达式 r'}\s*{' 匹配一个右花括号，后面跟着任意数量的空白字符，再跟着一个左花括号
    # 我们将其替换为 '}, {'，这样字符串就变成了 "{'a':1}, {'b':2}, {'c':3}"
    list_str = re.sub(r'}\s*{', '}, {', report_content_str)

    # 步骤 2: 在字符串首尾添加方括号，使其成为一个列表字符串
    # 现在字符串变成了 "[{'a':1}, {'b':2}, {'c':3}]"
    list_str = f'[{list_str}]'

    # 步骤 3: 使用 ast.literal_eval 安全地解析这个列表字符串
    try:
        list_of_dicts = ast.literal_eval(list_str)
    except (ValueError, SyntaxError) as e:
        print(f"解析字符串时出错: {e}")
        return {}

    # 步骤 4: 检查解析结果是否是一个字典列表
    if not isinstance(list_of_dicts, list):
        print("解析后的内容不是一个列表。")
        return {}

    # 步骤 5: 遍历列表，合并所有字典
    merged_dict = {}
    for d in list_of_dicts:
        if isinstance(d, dict):
            merged_dict.update(d)
        else:
            print(f"警告：列表中包含非字典元素: {d}，已跳过。")

    return merged_dict


def process_padding_rules_with_urls(padding_rules_data: dict, results: list) -> dict:
    """
    处理padding_rules_data中的引用格式，将[数字]替换为[数字](url)格式
    """
    # 创建result_index到url的映射
    index_to_url = {}
    for result in results:
        result_index = result.get("result_index")
        url = result.get("url")
        result_type = result.get("type")
        if result_type == "knowledge":
            # 拼接url，从config的BASE_URL中获取
            base_url = settings.BASE_URL
            url = f"{base_url}/{url}"
        if result_index is not None and url:
            result_index_str = str(result_index)
            clean_index = result_index_str.strip('[]')
            index_to_url[clean_index] = url

    logger.info(f"Index to URL mapping: {index_to_url}")

    # 处理padding_rules_data中的所有值
    processed_data = {}
    for key, value in padding_rules_data.items():
        if isinstance(value, str):
            import re
            def replace_reference(match):
                index_num = match.group(1)
                if index_num in index_to_url:
                    url = index_to_url[index_num]
                    replacement = f"[[{index_num}]({url})]"
                    logger.info(f"Replacing [{index_num}] with {replacement}")
                    return replacement
                else:
                    logger.info(f"No URL found for reference [{index_num}]")
                    return match.group(0)

            processed_value = re.sub(r'\[(\d+)\]', replace_reference, value)
            # 只有在确实进行了替换时才更新值
            if processed_value != value:
                logger.info(f"Processed value for key {key}: {processed_value[:100]}...")
            processed_data[key] = processed_value
        else:
            processed_data[key] = value

    return processed_data


def remove_references_from_padding_rules(padding_rules_data: dict) -> dict:
    """
    从padding_rules_data数据中去除[1], [2]这样的引用标记

    Args:
        padding_rules_data: 包含报告内容的字典数据

    Returns:
        dict: 去除引用标记后的字典数据
    """
    import re

    processed_data = {}

    for key, value in padding_rules_data.items():
        if isinstance(value, str):
            # 使用正则表达式匹配并移除[数字]格式的引用
            # 匹配模式：\[数字\]，其中数字可以是1位或多位
            cleaned_value = re.sub(r'\[\d+\]', '', value).strip()
            # 清理多余的空格
            # cleaned_value = re.sub(r'\s+', ' ', cleaned_value).strip()
            processed_data[key] = cleaned_value
        else:
            # 如果不是字符串类型，保持原值
            processed_data[key] = value

    return processed_data


def process_report_content_with_urls(report_content: str, results: list) -> str:
    """
    处理report_content中的引用格式，将[数字]替换为[数字](url)格式

    Args:
        report_content: 报告内容字符串
        results: 参考文献列表，包含result_index和url字段

    Returns:
        str: 处理后的报告内容
    """
    if not report_content or not isinstance(report_content, str):
        return report_content

    # 创建result_index到url的映射
    index_to_url = {}
    for result in results:
        result_index = result.get("result_index")
        url = result.get("url")
        if result_index is not None and url:
            # 确保result_index是字符串类型
            result_index_str = str(result_index)
            # 去掉result_index中的方括号（如果有的话）
            clean_index = result_index_str.strip('[]')
            index_to_url[clean_index] = url

    # 使用正则表达式查找并替换[数字]格式的引用
    import re
    def replace_reference(match):
        index_num = match.group(1)
        if index_num in index_to_url:
            url = index_to_url[index_num]
            return f"[[{index_num}]({url})]"
        else:
            # 如果找不到对应的url，保持原样
            return match.group(0)

    # 匹配[数字]格式（数字可以是多位数）
    processed_content = re.sub(r'\[(\d+)\]', replace_reference, report_content)

    return processed_content


def remove_references_from_report_content(report_content: str) -> str:
    """
    从report_content数据中去除[1], [2]这样的引用标记

    Args:
        report_content: 包含报告内容的字符串

    Returns:
        str: 去除引用标记后的报告内容
    """
    import re

    if not report_content or not isinstance(report_content, str):
        return report_content

    # 使用正则表达式匹配并移除[数字]格式的引用
    # 匹配模式：\[数字\]，其中数字可以是1位或多位
    cleaned_content = re.sub(r'\[\d+\]', '', report_content)

    # 清理多余的空格和换行符
    # cleaned_content = re.sub(r'\s+', ' ', cleaned_content)
    cleaned_content = cleaned_content.strip()

    return cleaned_content


@router.get("/download/word/{report_id}")
async def download_final_report_markdown(report_id: str,is_include_references : bool = False):
    """
    根据报告ID获取详细信息 - 返回Word格式文档（使用Markdown转换）包含引用
    """
    pdf_bytes =None
    try:

        # 获取报告内容
        report_content = mongo_api_service_manager.get_detail_by_report_final_id(
            report_id=report_id
        )

        if not report_content:
            raise BizError(code=ErrorCode.get_code(ErrorCode.REPORT_NOT_EXIST),
                           message=ErrorCode.get_message(ErrorCode.REPORT_NOT_EXIST))

        logger.info(f"report_content: {report_content}")

        report_title = mongo_api_service_manager.get_report_message_by_report_id(report_id)

        results = mongo_api_service_manager.get_results_report_id(report_id)

        # 根据报告id获取report的数据
        current_report = report_service.get_report(report_id)
        # 替换模版导出word
        if current_report and current_report.is_replace:
            # 获取模板信息
            template = mongo_api_service_manager.get_plan_template_by_id(current_report.template)

            http_file_url= template["file_url"]
            # 将一个包含多个字典的字符串（例如 "{'a':1} {'b':2} {'c':3}"） 解析并合并成一个单一的字典。
            padding_rules_data = merge_multiple_dicts_from_string(report_content)
            logger.info(f"padding_rules_data: {padding_rules_data}")

            # 是否包含引用
            if is_include_references:
                # 处理padding_rules_data中的引用格式，将[数字]替换为[数字](url)格式
                padding_rules_data = process_padding_rules_with_urls(padding_rules_data, results)
            else:
                # 从padding_rules_data数据中去除[1], [2]这样的引用标记
                padding_rules_data = remove_references_from_padding_rules(padding_rules_data)

            logger.info(f"padding_rules_data: {padding_rules_data}")
            # 转换为docx格式
            pdf_bytes = call_template_padding_api(http_file_url, padding_rules_data)

        # 不替换模板导出
        else:

            if is_include_references:
                # 处理report_content中的引用格式，将[数字]替换为[数字](url)格式
                report_content = process_report_content_with_urls(report_content, results)
            else:
                # 去除引用标记
                report_content = remove_references_from_report_content(report_content)
            logger.info(f"report_content: {report_content}")

            # 获取报告引言
            report_introduction = mongo_api_service_manager.get_introduction(report_id)

            report_summary = mongo_api_service_manager.get_report_summary(report_id)

            # 生成Markdown内容
            markdown_content = generate_markdown_content(
                report_content=report_content,
                report_title=report_title,
                report_introduction=report_introduction,
                report_summary=report_summary,
                results=results
            )

            # 转换为docx格式
            pdf_bytes = convert_markdown_to_format(markdown_content, "docx")

        # 使用ASCII安全的文件名
        ascii_filename = f"deep_research_report_{report_id}.docx"
        # 对中文文件名进行URL编码
        utf8_filename = f"{report_title}深度研究报告.docx"
        encoded_filename = urllib.parse.quote(utf8_filename.encode('utf-8'))
        # 返回文件流
        headers = {
            "Content-Disposition": f"attachment; filename={ascii_filename}; filename*=UTF-8''{encoded_filename}"
        }
        return Response(
            content=pdf_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers=headers
        )

    except Exception as e:
        logger.error(f"生成docx报告失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"生成docx报告失败: {str(e)}")


@router.get("/download/dataToWord/{report_id}")
async def download_final_report_markdown(report_id: str):
    """
    根据报告ID获取详细信息 - 返回Word格式文档（使用Markdown转换）
    """
    try:
        # # 获取报告内容
        # report_content = mongo_api_service_manager.get_detail_by_report_final_id(
        #     report_id=report_id
        # )
        #
        # if not report_content:
        #     raise BizError(code=ErrorCode.get_code(ErrorCode.REPORT_NOT_EXIST),
        #                    message=ErrorCode.get_message(ErrorCode.REPORT_NOT_EXIST))
        #
        # report_title = mongo_api_service_manager.get_report_message_by_report_id(report_id)
        #
        # results = mongo_api_service_manager.get_results_report_id(report_id)
        #
        # # 获取报告引言
        # report_introduction = mongo_api_service_manager.get_introduction(report_id)
        #
        # report_summary = mongo_api_service_manager.get_report_summary(report_id)
        #
        # # 生成Markdown内容
        # markdown_content = generate_markdown_content(
        #     report_content=report_content,
        #     report_title=report_title,
        #     report_introduction=report_introduction,
        #     report_summary=report_summary,
        #     results=results
        # )
        http_file_url = "https://copilot.sino-bridge.com:82/deep-research/template/公司客户画像及风险排查报告20251022-模版.docx"
        padding_rules_data = {
            "key_1_8": "hello world",
            "key_2_1_md": "科目xxxx"
        }

        # 转换为docx格式
        pdf_bytes = call_template_padding_api(http_file_url, padding_rules_data)

        # 使用ASCII安全的文件名
        ascii_filename = f"deep_research_report_{report_id}.docx"
        # 对中文文件名进行URL编码
        utf8_filename = f"深度研究报告.docx"
        encoded_filename = urllib.parse.quote(utf8_filename.encode('utf-8'))
        # 返回文件流
        headers = {
            "Content-Disposition": f"attachment; filename={ascii_filename}; filename*=UTF-8''{encoded_filename}"
        }
        return Response(
            content=pdf_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers=headers
        )

    except Exception as e:
        logger.error(f"生成docx报告失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"生成docx报告失败: {str(e)}")



@router.get("/final/detail/{report_id}", response_model=Result)
async def get_final_detail(
    report_id: str  # 改为字符串类型，支持ObjectId
):
    """
    根据报告ID获取详细信息 - 直接返回LLM的完整数据
    """

    current_report = report_service.get_report(report_id)


    results = mongo_api_service_manager.get_results_report_id(report_id)
    report_title = mongo_api_service_manager.get_report_message_by_report_id(report_id)
    report_content = mongo_api_service_manager.get_detail_by_report_final_id(report_id)
    if current_report and current_report.is_replace:
        report_content = merge_multiple_dicts_from_string(report_content)


    # 获取报告引言
    report_introduction = mongo_api_service_manager.get_introduction(report_id)
    # 获取报告总结
    report_summary = mongo_api_service_manager.get_report_summary(report_id)
    return Result.success( {
        "report_title": report_title,
        "report_content": report_content,
        "results": results,
        "report_introduction": report_introduction,
        "report_summary": report_summary
    })



@router.get("/detail/{report_id}", response_model=Result)
async def get_detail(
    report_id: str  # 改为字符串类型，支持ObjectId
):
    """
    根据报告ID获取详细信息 - 直接返回LLM的完整数据
    """
    return Result.success(mongo_api_service_manager.get_detail_by_report_id(
        report_id=report_id
    ))


@router.get("/history/{report_id}", response_model=Result)
async def get_history(
    report_id: str,  # 改为字符串类型，支持ObjectId
    limit: int = 10
):
    """
    根据报告ID获取历史记录列表
    """
    return Result.success(mongo_api_service_manager.get_history_by_report_id(
        report_id=report_id,
        limit=limit
    ))


@router.get("/introduction/{report_id}", response_model=Result)
async def get_report_introduction(
    report_id: str  # 改为字符串类型，支持ObjectId
):
    """
    获取引言
    根据报告ID获取详细信息 - 直接返回LLM的完整数据
    """

    # 在调用引言接口时将isFinalReportCompleted字段更新为false
    try:
        now = datetime.datetime.now()
        update_data = {
            "isFinalReportCompleted": False,
            "updated_at": now
        }
        
        # 执行更新
        result = mongo_db["reports"].update_one(
            {"_id": ObjectId(report_id)},
            {"$set": update_data}
        )
        
        if result.modified_count > 0:
            logger.info(f"成功将报告 {report_id} 的isFinalReportCompleted字段更新为false")
        else:
            logger.warning(f"更新报告 {report_id} 的isFinalReportCompleted字段失败")
    except Exception as e:
        logger.error(f"更新isFinalReportCompleted字段失败: {str(e)}")

    # 1、先查询库中是否有引言 有就直接返回
    report_introduction = mongo_api_service_manager.get_introduction(report_id)
    if report_introduction:
        logger.info(f"引言已存在，直接返回")
        return Result.success(report_introduction)


    # 2、没有就查询大纲 更具大纲生成引言
    report_plan = mongo_api_service_manager.get_plan_by_report_id(report_id)
    # 判断report_plan是否为空，为空则抛出异常
    if not report_plan:
        raise BizError(
            code=ErrorCode.get_code(ErrorCode.PLAN_NOT_EXIST),
            message=ErrorCode.get_message(ErrorCode.PLAN_NOT_EXIST)
        )

    # 取出report_plan里面的response里面的plan的值
    plan_content = report_plan.get("response", {}).get("plan", "")

    if not plan_content:
        raise BizError(
            code=ErrorCode.get_code(ErrorCode.OUTLINE_NOT_EXIST),
            message=ErrorCode.get_message(ErrorCode.OUTLINE_NOT_EXIST)
        )

    # 构造生成引言的prompt
    introduction_prompt = f"""
        基于以下报告大纲，生成一段200-300字的引言，介绍该报告的主要内容和研究意义：

        报告大纲：
        {plan_content}

        要求：
        1. 字数控制在200-300字之间
        2. 简要介绍报告的主题和核心内容
        3. 阐述报告的研究意义和价值
        4. 语言简洁明了，具有学术性但不失可读性
        5. 不要包含任何标题格式
        6. 直接输出引言内容，不要添加其他说明文字

        注意：尽可能结构化数据，提高可阅读性。如添加标号、列表等。
        """

    # 调用大模型生成引言（非流式输出）
    async def llm_service_call():
        return await llm_service.completion(message=introduction_prompt,model="report_final")

    introduction_result = await llm_service_call()
    if not introduction_result:
        raise BizError(
            code=ErrorCode.get_code(ErrorCode.LARGE_MODEL_RESPONSE_FAILED),
            message=ErrorCode.get_message(ErrorCode.LARGE_MODEL_RESPONSE_FAILED)
        )
    logger.info(f"引言生成成功")
    introduction = introduction_result["choices"][0]["message"].get("content", "")

    # 保存引言到数据库中
    mongo_api_service_manager.update_report_introduction(report_id, introduction)

    return Result.success(introduction)


def get_pdf_bytes(input_text: str, report_title: str, results: list[dict[str, Any]],report_introduction: str,report_summary: str):
    # 创建内存中的PDF文件
    buffer = BytesIO()

    # 创建自定义Canvas类来处理页码
    class PageNumCanvas(canvas.Canvas):
        def __init__(self, *args, **kwargs):
            canvas.Canvas.__init__(self, *args, **kwargs)
            self.pages = []

        def showPage(self):
            self.pages.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            page_count = len(self.pages)
            for page in self.pages:
                self.__dict__.update(page)
                self.draw_page_number(page_count)
                canvas.Canvas.showPage(self)
            canvas.Canvas.save(self)

        def draw_page_number(self, page_count):
            page_num = self.getPageNumber()
            text = f"第 {page_num} 页"
            self.saveState()
            try:
                self.setFont("STSong-Light" if 'STSong-Light' in pdfmetrics.getRegisteredFontNames() else "Helvetica",
                             10)
            except:
                self.setFont("Helvetica", 10)
            self.drawRightString(310, 20, text)
            self.restoreState()

    class PdfWithTOCAndPageNumbers(BaseDocTemplate):
        def __init__(self, filename, **kwargs):
            BaseDocTemplate.__init__(self, filename, **kwargs)
            # 创建页面框架
            frame = Frame(self.leftMargin, self.bottomMargin,
                          self.width, self.height, id='normal')
            self.addPageTemplates([PageTemplate(id='First', frames=[frame], pagesize=A4)])

        def afterFlowable(self, flowable):
            "检测标题并注册到目录"
            if flowable.__class__.__name__ == 'Paragraph':
                style = flowable.style.name
                text = flowable.getPlainText()
                if style == 'ChapterStyle':
                    self.notify('TOCEntry', (0, text, self.page, None))
                elif style == 'CustomHeading':
                    self.notify('TOCEntry', (1, text, self.page, None))
                elif style == 'ReferenceTitle':
                    self.notify('TOCEntry', (0, text, self.page, None))

    # 创建文档
    doc = PdfWithTOCAndPageNumbers(buffer, pagesize=A4,
                                   leftMargin=72, rightMargin=72,
                                   topMargin=72, bottomMargin=72)

    # 获取样式表
    styles = getSampleStyleSheet()

    try:
        # 注册中文字体
        pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
        registerFontFamily('STSong-Light', normal='STSong-Light')

        # 创建支持中文的样式
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontName='STSong-Light',
            fontSize=24,
            spaceAfter=30,
            alignment=TA_CENTER,
        )

        subtitle_style = ParagraphStyle(
            'CustomSubtitle',
            parent=styles['Heading2'],
            fontName='STSong-Light',
            fontSize=14,
            spaceAfter=20,
            alignment=TA_CENTER,
        )

        toc_title_style = ParagraphStyle(
            'TOCTitle',
            parent=styles['Heading1'],
            fontName='STSong-Light',
            fontSize=18,
            spaceAfter=20,
            alignment=TA_CENTER,
        )

        chapter_style = ParagraphStyle(
            'ChapterStyle',
            parent=styles['Heading1'],
            fontName='STSong-Light',
            fontSize=16,
            spaceBefore=20,
            spaceAfter=15,
            textColor='#2E4057'
        )

        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontName='STSong-Light',
            fontSize=14,
            spaceBefore=20,
            spaceAfter=15,
        )

        normal_style = ParagraphStyle(
            'CustomNormal',
            parent=styles['Normal'],
            fontName='STSong-Light',
            fontSize=11,
            spaceBefore=8,
            spaceAfter=8,
            leading=16,
            alignment=TA_JUSTIFY
        )

        image_desc_style = ParagraphStyle(
            'ImageDescStyle',
            parent=normal_style,
            fontSize=10,
            textColor='#666666',
            spaceBefore=6,
            spaceAfter=6,
        )

        info_style = ParagraphStyle(
            'InfoStyle',
            parent=normal_style,
            fontSize=10,
        )

        # 参考文献样式
        reference_title_style = ParagraphStyle(
            'ReferenceTitle',
            parent=styles['Heading1'],
            fontName='STSong-Light',
            fontSize=16,
            spaceAfter=20,
            spaceBefore=20,
            alignment=TA_CENTER,
        )

        reference_style = ParagraphStyle(
            'ReferenceStyle',
            parent=normal_style,
            fontName='STSong-Light',
            fontSize=10,
            leftIndent=20,
            spaceBefore=2,
            spaceAfter=2,
        )

    except Exception as e:
        # 如果中文字体注册失败，使用默认字体
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            spaceAfter=30,
            alignment=TA_CENTER,
        )

        subtitle_style = ParagraphStyle(
            'CustomSubtitle',
            parent=styles['Heading2'],
            fontSize=14,
            spaceAfter=20,
            alignment=TA_CENTER,
        )

        toc_title_style = ParagraphStyle(
            'TOCTitle',
            parent=styles['Heading1'],
            fontSize=18,
            spaceAfter=20,
            alignment=TA_CENTER,
        )

        chapter_style = ParagraphStyle(
            'ChapterStyle',
            parent=styles['Heading1'],
            fontSize=16,
            spaceBefore=20,
            spaceAfter=15,
        )

        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=14,
            spaceBefore=20,
            spaceAfter=15,
        )

        normal_style = ParagraphStyle(
            'CustomNormal',
            parent=styles['Normal'],
            fontSize=11,
            spaceBefore=8,
            spaceAfter=8,
            leading=16,
            alignment=TA_JUSTIFY
        )

        image_desc_style = ParagraphStyle(
            'ImageDescStyle',
            parent=normal_style,
            fontSize=10,
            spaceBefore=6,
            spaceAfter=6,
        )

        info_style = ParagraphStyle(
            'InfoStyle',
            parent=normal_style,
            fontSize=10,
        )

        # 参考文献样式
        reference_title_style = ParagraphStyle(
            'ReferenceTitle',
            parent=styles['Heading1'],
            fontSize=16,
            spaceAfter=20,
            spaceBefore=20,
            alignment=TA_CENTER,
        )

        reference_style = ParagraphStyle(
            'ReferenceStyle',
            parent=normal_style,
            fontSize=10,
            leftIndent=20,
            spaceBefore=2,
            spaceAfter=2,
        )

    # 构建文档内容
    story = []

    # 添加标题
    title = Paragraph(report_title, title_style)
    story.append(title)

    # 添加引言
    # if report_introduction:
    #     story.append(Spacer(1, 0.2 * inch))
    #     intro_paragraph = Paragraph(report_introduction, normal_style)
    #     story.append(intro_paragraph)
    #     story.append(Spacer(1, 0.3 * inch))

    story.append(Spacer(1, 0.3 * inch))

    # 添加目录标题
    # toc_title = Paragraph("目录", toc_title_style)
    # story.append(toc_title)
    # story.append(Spacer(1, 0.2 * inch))

    # 添加目录占位符，支持页码跳转
    # table_of_contents = TableOfContents()
    # table_of_contents.levelStyles = [
    #     ParagraphStyle(
    #         name='TOCLevel0',
    #         fontName='STSong-Light' if 'STSong-Light' in pdfmetrics.getRegisteredFontNames() else 'Helvetica',
    #         fontSize=12,
    #         leftIndent=20,
    #         firstLineIndent=-20,
    #         spaceBefore=5,
    #         leading=16,
    #     ),
    #     ParagraphStyle(
    #         name='TOCLevel1',
    #         fontName='STSong-Light' if 'STSong-Light' in pdfmetrics.getRegisteredFontNames() else 'Helvetica',
    #         fontSize=11,
    #         leftIndent=40,
    #         firstLineIndent=-20,
    #         spaceBefore=3,
    #         leading=14,
    #     ),
    # ]
    # story.append(table_of_contents)
    # story.append(PageBreak())  # 目录后分页

    # 添加引言
    if report_introduction:
        introduction_title = Paragraph("引言", chapter_style)
        # story.append(PageBreak())  # 新页面开始总结
        story.append(introduction_title)
        story.append(Spacer(1, 0.3 * inch))

        # 预处理input_text，移除#号和*号
        processed_introduction = report_introduction.replace('#', '').replace('*', '')
        # 处理总结内容，支持换行
        introduction_lines = processed_introduction.split('\n')
        for line in introduction_lines:
            if line.strip():
                introduction_para = Paragraph(line.strip(), normal_style)
                story.append(introduction_para)
                story.append(Spacer(1, 0.1 * inch))

    # 预处理input_text，移除#号和*号
    processed_text = input_text.replace('#', '').replace('*', '')
    lines = processed_text.split('\n')

    for line in lines:
        line = line.strip()
        if not line:
            story.append(Spacer(1, 0.1 * inch))
            continue

        # 检查是否为一级标题（数字. 标题）
        chapter_match = re.match(r'^(\d+\.\s*.*)', line)
        # 检查是否为二级标题（（数字）标题）
        section_match = re.match(r'^（([1-9][0-9]*)）\s*(.*)', line)

        if chapter_match:
            # 一级标题
            chapter_title = chapter_match.group(1)
            heading = Paragraph(chapter_title, chapter_style)
            story.append(heading)
            story.append(Spacer(1, 0.2 * inch))
        elif section_match:
            # 二级标题
            # 保留完整的标题内容，包括括号内的数字
            section_title = f"（{section_match.group(1)}）{section_match.group(2) if section_match.group(2) else ''}"
            heading = Paragraph(section_title, heading_style)
            story.append(heading)
            story.append(Spacer(1, 0.2 * inch))
        else:
            # 处理普通内容行
            line = re.sub(r'！?\[图像描述\]：([^！\n]+?)\s*[-—]\s*(https?://[^\s\n\\\\`]+)',
                          r'![\1](\2)', line)
            # 处理带括号的图片格式
            line = re.sub(r'！?\[图像描述\]：([^(\n]+?)\s*\(\s*(https?://[^\s\)]+)\s*\)！?',
                          r'![\1](\2)', line)
            # 检查是否包含图片
            image_pattern1 = r'!\[([^\]]+)\]\((https?://[^\s\)]+)\)'
            image_matches = re.findall(image_pattern1, line)
            if image_matches:
                # 处理图片
                for alt_text, image_url in image_matches:
                    try:
                        # 下载图片并嵌入PDF
                        response = httpx.get(image_url, timeout=15.0)
                        if response.status_code == 200 and response.headers.get('content-type', '').startswith('image'):
                            image_data = BytesIO(response.content)
                            img = Image(image_data)
                            img.drawWidth = 400
                            img.drawHeight = 300
                            img.hAlign = 'CENTER'
                            story.append(img)
                            story.append(Spacer(1, 0.2 * inch))
                    except Exception as e:
                        logger.warning(f"图片处理异常 {image_url}: {str(e)}")
                        image_url_para = Paragraph(f"<i>图片URL: {image_url}</i>", image_desc_style)
                        story.append(image_url_para)
                        story.append(Spacer(1, 0.1 * inch))
            else:
                # 普通段落
                line = line.replace('&', '&amp;')
                line = line.replace('<', '&lt;').replace('>', '&gt;')
                para = Paragraph(line, normal_style)
                story.append(para)
                story.append(Spacer(1, 0.1 * inch))
                
    # 添加总结
    if report_summary:
        # 在参考文献之前添加总结章节
        summary_title = Paragraph("总结", chapter_style)
        story.append(PageBreak())  # 新页面开始总结
        story.append(summary_title)
        story.append(Spacer(1, 0.3 * inch))

        # 预处理input_text，移除#号和*号
        processed_summary = report_summary.replace('#', '').replace('*', '')
        # 处理总结内容，支持换行
        summary_lines = processed_summary.split('\n')
        for line in summary_lines:
            if line.strip():
                summary_para = Paragraph(line.strip(), normal_style)
                story.append(summary_para)
                story.append(Spacer(1, 0.1 * inch))

    # 添加参考文献部分
    try:
        if results:
            # 添加参考文献标题（使用ChapterStyle以便在目录中显示为章节）
            reference_title = Paragraph("参考文献", chapter_style)
            story.append(PageBreak())  # 新页面开始参考文献
            story.append(reference_title)
            story.append(Spacer(1, 0.3 * inch))

            # 添加参考文献条目
            for i, ref in enumerate(results, 1):
                title = ref["title"]
                url = ref["url"]
                result_index =ref["result_index"]
                # 创建可点击的链接
                reference_text = f'<link href="{url}">{i}. {title} [{result_index}]</link>'
                reference_para = Paragraph(reference_text, reference_style)
                story.append(reference_para)
                story.append(Spacer(1, 0.1 * inch))
    except Exception as e:
        logger.warning(f"获取参考文献数据失败: {str(e)}")

    # 构建PDF，使用multiBuild支持目录，并使用自定义Canvas处理页码
    doc.multiBuild(story, canvasmaker=PageNumCanvas)

    # 获取PDF内容
    buffer.seek(0)
    pdf_content = buffer.getvalue()
    buffer.close()

    return pdf_content


def summary_prompt(full_content: str) -> str:
    """
    生成报告总结的prompt
    
    Args:
        full_content: 完整的报告内容
        
    Returns:
        str: 总结生成的prompt
    """
    return f"""
请对以下完整的研究报告进行总结，生成一个1000-3000字的综合总结。

<完整报告内容>
{full_content}
</完整报告内容>

总结要求：
1. 字数控制在1000-3000字之间
2. 总结应该涵盖报告的主要观点、关键发现和重要结论
3. 保持逻辑清晰，结构完整
4. 突出报告的核心价值和意义
5. 语言简洁明了，避免冗余
6. 不要包含具体的引用格式或参考文献
7. 总结应该是对原报告的高度概括和提炼
8. 总结不需要标题，只需要正文即可

请直接输出总结内容，不要包含任何其他说明文字。
注意：大段的内容，尽可能结构化数据，提高可阅读性。如添加标号、列表等。
"""

def prompt(title: str, plan: str, learnings: str, sources: str, images: str, requirement: str, current: str, template: str = None, report_content: str = None):

    images_prompt = ""
    if len(images) > 0:
        images_prompt = f"""
以下是之前研究的所有图像：
<图片>
{images}
</图片>
图像规则：
- 根据图像描述，将与段落内容相关的图像放在文章中的适当位置。
- 只放置与文章内容相关的图片。如果发现图像描述与稳定存储无关，则不会使用本文。
- 使用"![图像描述](Image_url)"包含图像在单独的部分。
- 在单独的章节中使用 ![图像描述](Image_url) 的格式插入图片。
- 请勿在文章末尾添加任何图片
- 所有的图片尽可能是引用一次，相同的图片不要重复引用
- **在报告中纳入之前研究中有意义的图像非常有帮助**
- 合理地将图像添加到内容的中间，不要在末尾输出所有图像，或者在末尾输出一两个图像。

"""

    requirement_prompt = ""
    if requirement:
        requirement_prompt = f"""
请根据用户的书写要求书写：
<要求>
{requirement}
</要求>
"""

    template_prompt = ""
    if template:
        template_prompt = f"""
参考以模板对应部分的结构来生成报告的样式，不要影响<计划>的内容：
<模板>
{template}
</模板>
"""

    report_content_prompt = ""
    if report_content:
        report_content_prompt = f"""
这是已生成的报告部分，后续生成的尽量减少重复内容，前后不要有冲突，如果还没有则不需要参考
<已生成的报告部分>
{report_content}
</已生成的报告部分>
"""

    return  f"""
用户需要生成的报告：

这是需要生成的报告名称：
<报告名>
{title}
</报告名>

这是用户确认后的报告计划：
<计划>
{plan}
</计划>

以下是从之前的研究中获得的所有经验：
<学习>
{learnings}
</学习>

以下是之前研究的所有来源（如果有的话）：
<来源>
{sources}
</来源>

{images_prompt}

{requirement_prompt}

{template_prompt}

根据报告计划的 {current} 部分，使用研究中的知识写一篇文章。
尽可能详细，越多越好，包括从研究中获得的所有知识。
不要输出与报告无关的任何内容。
仅回复最终报告内容，前后无其他文本。
{current} 名称不要有调整，也不要用**等符号包起来，也不要丢失#。
章节标题，严格要按照<计划>的章节标题来生成，##千万不要搞错了。

引用规则：
- 请在适当的时候在段落末尾引用研究参考文献。
- 如果引用来自参考文献，请**忽略**。仅包括来源的引用。
- 请使用参考格式[数字]，参考答案相应部分的学习链接。
- 如果一个段落来自多个学习参考链接，请列出所有相关的引用号，例如[1][2]。
- 记住不要在末尾对引文进行分组，而是将其列在答案的相应部分。控制脚注的数量。
- 一个段落中不要有超过3个参考链接，只保留最相关的链接。
- 不要在报告末尾添加参考文献。
- 如果发现有冲突，再后面标注【需人工确认】。

注意：大段的内容，尽可能结构化数据，提高可阅读性。如添加标号、列表等，不要出现大段的内容。

"""
