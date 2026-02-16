#!/usr/bin/env python3
"""
深度研究 搜索总结API路由模块
"""

import logging
import datetime
import asyncio
from fastapi import APIRouter, HTTPException  # type: ignore
from models.models import LLMMessage, LLMRequest, LLMMessage1, LLMMessageSearchSummary
from services.llm_service import llm_service
from services.mongo_api_service_manager import mongo_api_service_manager
from services.report_service import report_service
from services.task_service import get_task_info
from utils.database import mongo_db
from services.step_record_service import step_record_service
import traceback
from utils.exception_handler import ErrorCode
from utils.response_models import Result, BizError


logger = logging.getLogger(__name__)

router = APIRouter()


def _get_search_data_and_build_context(task_id: str):
    try:
        collection = mongo_db.search_results
        
        # 查询数据
        results = collection.find({"task_id": task_id})
        results_list = list(results)  # 转换为列表
        if not results_list:
            logger.warning(f"未找到task_id为 {task_id} 的数据")
            return [], [], ""

        # 定义空数组
        images = []
        sources = []

        # 遍历 results_list，合并 images 和 sources 数组
        for doc in results_list:
            # 合并 images 数组（现在直接从每条记录的images字段获取）
            if "images" in doc and isinstance(doc["images"], list):
                images.extend(doc["images"])

            # 合并 sources 数组
            source = {
                "title": doc.get("title", ""),
                "url": doc.get("url", ""),
                "content": doc.get("content", ""),  # 保持与原接口一致
                "raw_content": doc.get("raw_content", ""),  # 保持与原接口一致
                "published_date": doc.get("published_date"),
                "score": doc.get("score"),
                "result_index": doc.get("result_index")
            }
            sources.append(source)
        
        # 生成context，模拟JavaScript代码的逻辑
        context_parts = []
        for idx, source in enumerate(sources):
            logger.info(f"source: {source}")
            # 为每个source添加num字段（从1开始）
            source_with_num = dict(source)
            raw_content = source_with_num.get("raw_content", "")
            # 添加 None 检查，确保 raw_content 不为 None
            if raw_content is None:
                raw_content = ""
            # 如果raw_content的len大于100，则为有效数据
            if len(raw_content) > 100:
                # 如果raw_content的len大于10000字，则截取1w字
                if len(raw_content) > 10000:
                    raw_content = raw_content[:10000]
                context_part = f'<content index="{source_with_num.get("result_index", "")}" url="{source_with_num.get("url", "")}" title="{source_with_num.get("title", "")}">\n{raw_content}\n</content>'
                context_parts.append(context_part)

        context = "\n".join(context_parts)
        
        logger.info(f"成功构建context，包含 {len(sources)} 个源")
        return images, sources, context
        
    except Exception as e:
        logger.error(f"查询搜索数据失败: {str(e)}")
        raise ValueError(f"查询搜索数据失败: {str(e)}")


@router.post("/completion", response_model=Result)
async def chat_completion(
    dto: LLMMessageSearchSummary
):
    """
    搜索总结 - completion模式，需要有效的report_id
    """
    start_time = datetime.datetime.now()
    
    try:
 
        if not dto.task_id:
            raise HTTPException(status_code=400, detail="task_id不能为空")
        
        # 获取任务信息
        task_info = await get_task_info(dto.task_id)
        logger.info(f"task_info: {task_info}")
        query = task_info["query"]
        research_goal = task_info["research_goal"]
        report_id = task_info["report_id"]
        split_id = task_info["split_id"]
        
        # 3. 从数据库查询数据并构建context
        if not dto.task_id:
            raise BizError(code=ErrorCode.get_code(ErrorCode.TASK_ID_NOT_EMPTY),
                           message=ErrorCode.get_message(ErrorCode.TASK_ID_NOT_EMPTY))

        images, sources, context = _get_search_data_and_build_context(dto.task_id)
        # 4. 开始步骤
        report_service.start_step(report_id, "search_summary")

        prompt_used = prompt(query, research_goal, context)
        logger.info(f"prompt_used: {prompt_used}")

        async def llm_service_call():
            return await llm_service.completion(message=prompt_used,model="search_summary")
        
        # 5. 使用统一的MongoDB API服务管理器
        result = await mongo_api_service_manager.execute_completion_api(
            query=query,
            query_type="search_summary",
            title_prefix="搜索总结",
            service_call=llm_service_call,
            additional_data={
                "prompt_used": prompt_used,
                "task_id": dto.task_id,
                "images": images,
                "sources": sources
            },
            report_id=report_id
        )
        
        # 4. 完成步骤
        end_time = datetime.datetime.now()
        execution_time = (end_time - start_time).total_seconds()
        
        report_service.complete_step(
            report_id, "search_summary",
            result=result["llm_response"],
            execution_time=execution_time
        )

        # 5. 插入 report_search_summary数据 插入前先删除旧数据
        mongo_api_service_manager.delete_search_summary_by_task_id(dto.task_id)
        step_record_service.create_search_summary_record(report_id,query,dto.task_id,split_id,result["llm_response"])

        # 6. 更新serp_task状态为completed
        # mongo_api_service_manager.update_serp_task_search_state(dto.task_id, "completed")
        if "llm_response" in result and isinstance(result["llm_response"], dict):
            # 检查是否有错误信息
            if "id" in result["llm_response"] and "error" in str(result["llm_response"]["id"]).lower():
                mongo_api_service_manager.update_serp_task_search_state(dto.task_id, "failed")
            else:
                mongo_api_service_manager.update_serp_task_search_state(dto.task_id, "completed")

        logger.info("---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------")
        logger.info(f"result: {result}")
        return Result.success(result["llm_response"])
        
    except Exception as e:
        # 5. 标记步骤失败
        if 'report_id' in locals():
            end_time = datetime.datetime.now()
            execution_time = (end_time - start_time).total_seconds()
            
            report_service.fail_step(
                report_id, "search_summary",
                error_message=str(e),
                execution_time=execution_time
            )
        # 更新serp_task状态为failed
        mongo_api_service_manager.update_serp_task_search_state(dto.task_id, "failed")
        
        logger.error(f"搜索总结API失败: {str(e)}")
        traceback.print_exc()
        raise ValueError(f"搜索总结失败: {str(e)}")


@router.post("/stream")
async def chat_stream(
    dto: LLMMessageSearchSummary
):
    """
    流式搜索总结 - 需要有效的report_id
    """
    
    start_time = datetime.datetime.now()
    
    try:
        # 1. 验证report_id
        # if not dto.report_id:
        #     raise HTTPException(status_code=400, detail="搜索总结需要有效的report_id")
        
        report_id = dto.report_id
        # if not report_service.get_report(report_id):
        #     raise HTTPException(status_code=404, detail="指定的报告ID不存在")
        
        # 2. 验证task_id并获取任务信息
        if not dto.task_id:
            raise BizError(code=ErrorCode.get_code(ErrorCode.TASK_ID_NOT_EMPTY),
                           message=ErrorCode.get_message(ErrorCode.TASK_ID_NOT_EMPTY))

        # 获取任务信息
        task_info = await get_task_info(dto.task_id)
        query = task_info["query"]
        research_goal = task_info["research_goal"]
        # 获取split_id
        split_id = task_info["split_id"]
        
        # 3. 从数据库查询数据并构建context
        if not dto.search_id:
            raise BizError(code=ErrorCode.get_code(ErrorCode.SEARCH_ID_NOT_EMPTY),
                           message=ErrorCode.get_message(ErrorCode.SEARCH_ID_NOT_EMPTY))

        images, sources, context = _get_search_data_and_build_context(dto.search_id)
        
        # 4. 开始步骤
        report_service.start_step(report_id, "search_summary")
        
        # 异步更新完成状态的任务
        async def update_completion_status():
            await asyncio.sleep(3)  # 给流式处理一些时间
            try:
                end_time = datetime.datetime.now()
                execution_time = (end_time - start_time).total_seconds()
                
                # 检查步骤是否还在处理中，如果是则标记为完成
                current_report = report_service.get_report(report_id)
                if current_report and current_report.steps.search_summary.status == "processing":
                    report_service.complete_step(
                        report_id, "search_summary",
                        execution_time=execution_time
                    )
            except Exception as e:
                logger.error(f"更新流式处理状态失败: {str(e)}")
                # 如果更新失败，标记为失败状态
                end_time = datetime.datetime.now()
                execution_time = (end_time - start_time).total_seconds()
                report_service.fail_step(
                    report_id, "search_summary",
                    error_message=str(e),
                    execution_time=execution_time
                )
        
        # 启动后台任务
        asyncio.create_task(update_completion_status())
        
        return await mongo_api_service_manager.execute_stream_api(
            query=query,
            query_type="search_summary",
            title_prefix="搜索总结",
            prompt_builder=prompt(query, research_goal, context),
            report_id=report_id,
            model="search_summary"
        )
        
    except Exception as e:
        # 标记步骤失败
        if 'report_id' in locals():
            end_time = datetime.datetime.now()
            execution_time = (end_time - start_time).total_seconds()
            
            report_service.fail_step(
                report_id, "search_summary",
                error_message=str(e),
                execution_time=execution_time
            )
        
        logger.error(f"流式搜索总结API失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"流式搜索总结失败: {str(e)}")


@router.get("/detail/{report_id}", response_model=Result)
async def get_detail(
    report_id: str  # 改为字符串类型，支持ObjectId
):
    """
    根据报告ID获取详细信息 - 直接返回LLM的完整数据
    """
    return Result.success(mongo_api_service_manager.get_detail_by_report_id(report_id))


@router.get("/history/{report_id}", response_model=Result)
async def get_history(
    report_id: str,  # 改为字符串类型，支持ObjectId
    limit: int = 10
):
    """
    根据报告ID获取历史记录列表
    """
    return Result.success(mongo_api_service_manager.get_history_by_report_id(report_id,limit))


def prompt(query: str, researchGoal: str, context: str):
    return f"""
我从网络上抓取了一些信息，现在需要你帮我整理内容，请按照以下要求组织搜索到的信息：
<查询>
{query}
<查询>

您需要按照以下要求组织搜索到的信息：
<研究目标>
{researchGoal}
</研究目标>

SERP搜索中的以下上下文：
数据分为两种，由type区分，online和knowledge
online数据为网络搜索到的数据，knowledge数据为知识库搜索到的数据
如果数据在多个上下文出现，则优先使用knowledge数据，如果数据有冲突，标注[需人工确认]
<上下文>
{context}
</上下文>

你需要像人类研究人员一样思考。
从上下文中生成一个学习列表。
分析查询的核心要点
根据<查询>总结重要信息，并给出你的分析和总结。

请确保：
- 确保每项学习都是独一无二的，彼此之间没有相似之处。
- 学习应该切中要害，尽可能详细和信息密集，且有价值
- 确保在学习中包括任何实体，如人、地点、公司、产品、事物等，以及任何特定的实体、指标、数字和日期（如果可用），所学知识将用于进一步研究该主题。
- 内容结构清晰，便于理解
- 当任务中指定了时间范围要求时，请在搜索查询中严格遵守这些约束，并验证提供的所有信息是否都在指定的时间段内。
- 信息全面、最新，来源可靠
- 现有信息中不存在重大差距、歧义或矛盾
- 信息涵盖了事实数据和必要的背景
- 信息准确，没有错误或误导性的陈述
- 信息有条理，易于理解
- 信息有深度，能够提供有价值的见解
- 数据点有可靠的证据或来源支持
- 始终核实所收集信息的相关性和可信度
- 尽可能通过至少两个独立来源验证信息
- 不要提后续研究建议，只输出总结内容

强制：
- 如果数据有冲突，请使用距离当前时间最近的信息
- 如果查询的企业信息有冲突，以天眼查的数据为准
- 如果没有权威机构，已距离现在最近的时间为准
- 避免过度输出推理的内容，输出内容要简洁明了

引用规则：
- 请在适当的时候在句末引用上下文。
- 请使用引用号[编号]的格式在您的答案的相应部分引用上下文，标号使用<content index="编号">的编号
- 如果一个句子来自多个上下文，请列出所有相关的引用号，例如[1][2]。记住不要在末尾对引文进行分组，而是将其列在答案的相应部分。

注意事项：
- 所有的内容应该都来自于<上下文>，不要输出任何<上下文>之外的内容，只允许适当的修饰语句，不允许凭空输出。
- 如果<上下文>中没有内容，直接输出“没有找到相关内容”。
"""