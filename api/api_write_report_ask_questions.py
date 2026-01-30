"""
The API to ask questions to the user, in order to enrich the plan of the whole report. 
"""

import logging
import datetime, json
import asyncio
from fastapi import APIRouter, HTTPException
from models.models import LLMMessageAskQuestions, UpdateQuestion
from services.llm_service import LLMService
from services.mongo_api_service_manager import mongo_api_service_manager
from services.report_service import report_service
from services.step_record_service import step_record_service
from utils.exception_handler import ErrorCode
from utils.response_models import Result, BizError
from starlette.responses import StreamingResponse

logger = logging.getLogger(__name__)

router = APIRouter()

# 初始化LLM服务
llm_service = LLMService()

@router.post("/stream")
async def chat_stream(
    llm_message: LLMMessageAskQuestions
):
    """
    流式询问问题 - 如果没有report_id则创建新报告
    """
    start_time = datetime.datetime.now()
    logger.info(f"llm_message: {llm_message}")
    
    try:
        # 1. 获取或创建报告
        if llm_message.report_id:
            report_id = llm_message.report_id
            # 从数据库获取报告详情
            existing_report = report_service.get_report(report_id)
            logger.info(f"existing_report: {existing_report}")
            if not existing_report:
                raise BizError(code=ErrorCode.get_code(ErrorCode.REPORT_NOT_EXIST),
                               message=ErrorCode.get_message(ErrorCode.REPORT_NOT_EXIST))

            # 1. 获取或创建报告
            if llm_message.message:
                # 使用数据库中的报告内容
                report_message = llm_message.message
                # 更新报告title
                report_service.update_report_title(report_id, llm_message.message)
            else:
                raise BizError(code=ErrorCode.get_code(ErrorCode.REPORT_TITLE_NOT_EXIST),
                               message=ErrorCode.get_message(ErrorCode.REPORT_TITLE_NOT_EXIST))

        else:
            raise BizError(code=ErrorCode.get_code(ErrorCode.REPORT_NOT_EXIST),
                           message=ErrorCode.get_message(ErrorCode.REPORT_NOT_EXIST))
        # 2. 处理模板相关逻辑
        template = None
        if llm_message.template_id:
            # 验证模板是否存在
            template = mongo_api_service_manager.get_plan_template_by_id(llm_message.template_id)
            if template:
                # 将template_id存储到reports库的template字段中
                from bson import ObjectId
                from utils.database import mongo_db
                mongo_db.reports.update_one(
                    {"_id": ObjectId(report_id)}, 
                    {"$set": {"template": llm_message.template_id, "is_replace": template.get("is_replace")}}
                )
                logger.info(f"更新报告模板ID，报告ID: {report_id}, 模板ID: {llm_message.template_id}")
            else:
                logger.warning(f"指定的模板不存在，模板ID: {llm_message.template_id}")
        else:
            # 如果template_id为空，清空template字段
            from bson import ObjectId
            from utils.database import mongo_db
            mongo_db.reports.update_one(
                {"_id": ObjectId(report_id)}, 
                {"$set": {"template": "", "is_replace": False}}
            )
            logger.info(f"清空报告模板ID，报告ID: {report_id}")

        # 3. 开始步骤并创建记录
        report_service.start_step(report_id, "ask_questions")
        stream_step_record_id = step_record_service.create_ask_questions_record(report_id, report_message)

        # 异步更新完成状态的任务
        async def update_completion_status():
            await asyncio.sleep(3)  # 给流式处理一些时间
            try:
                end_time = datetime.datetime.now()
                execution_time = (end_time - start_time).total_seconds()
                
                # 检查步骤是否还在处理中，如果是则标记为完成
                current_report = report_service.get_report(report_id)
                if current_report and current_report.steps.ask_questions.status == "processing":
                    report_service.complete_step(
                        report_id, "ask_questions",
                        execution_time=execution_time
                    )
                    # 更新步骤记录
                    step_record_service.update_ask_questions_record(
                        stream_step_record_id, "completed",
                        execution_time=execution_time
                    )
            except Exception as e:
                logger.error(f"更新流式处理状态失败: {str(e)}")
                # 如果更新失败，标记为失败状态
                end_time = datetime.datetime.now()
                execution_time = (end_time - start_time).total_seconds()
                report_service.fail_step(
                    report_id, "ask_questions",
                    error_message=str(e),
                    execution_time=execution_time
                )
                # 更新步骤记录
                step_record_service.update_ask_questions_record(
                    stream_step_record_id, "failed",
                    error_message=str(e),
                    execution_time=execution_time
                )
        
        # 启动后台任务
        asyncio.create_task(update_completion_status())

        # 如果模板不为空， 并且is_replace 为true 则返回空的流式响应

        if template and template.get("is_replace"):
            # 保存调用参数记录到report_ask_questions表
            step_record_service.update_ask_questions_message(report_id, template.get("content"))

            # 返回空的流式响应
            async def empty_stream_generator():
                yield "data: [DONE]\n\n"
            return StreamingResponse(
                empty_stream_generator(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
            )
        else:
            # 定义一个收集完整响应的变量
            chunks = []

            # 创建一个包装的流式响应生成器
            async def wrapped_stream_generator():
                nonlocal chunks
                try:
                    # 获取原始流式响应
                    original_response = await mongo_api_service_manager.execute_stream_api(
                        query=report_message,
                        query_type="ask_questions",
                        title_prefix="询问",
                        prompt_builder=prompt,
                        report_id=report_id,
                        model="plan"
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

                    # 保存调用参数记录到report_ask_questions表
                    step_record_service.update_ask_questions_message(report_id, str(full_content))
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
        #     query=report_message,
        #     query_type="ask_questions",
        #     title_prefix="询问",
        #     prompt_builder=prompt,
        #     report_id=report_id
        # )
        
    except Exception as e:
        # 标记步骤失败
        if 'report_id' in locals():
            end_time = datetime.datetime.now()
            execution_time = (end_time - start_time).total_seconds()
            
            report_service.fail_step(
                report_id, "ask_questions",
                error_message=str(e),
                execution_time=execution_time
            )
            
            # 更新步骤记录
            if 'stream_step_record_id' in locals():
                step_record_service.update_ask_questions_record(
                    stream_step_record_id, "failed",
                    error_message=str(e),
                    execution_time=execution_time
                )
        
        logger.error(f"流式询问问题API失败: {str(e)}")
        raise ValueError(f"流式询问问题失败: {str(e)}")


@router.get("/detail/{report_id}", response_model=Result)
async def get_detail(
    report_id: str  # 改为字符串类型，支持ObjectId
):
    """
    根据报告ID获取详细信息
    """
    return Result.success(mongo_api_service_manager.get_ask_detail(report_id))

@router.put("/update", response_model=Result)
async def update(
    dto: UpdateQuestion
):
    """
    更新问题
    """
    return Result.success(step_record_service.update_ask_questions_message(dto.report_id, dto.message))

# 注意：详情和历史查询接口已迁移到 /api/report/ 路由中


def prompt(query: str):
    return f"""
根据用户查询，提供10个以上相关的后续研究问题。每个问题后面给出简短建议。
提出的问题尽可能的全面，不要遗漏，覆盖所有需要研究的内容。
给出的建议要具有可行性，不要过于理想化。
问题和建议要分开，不要混在一起。
不要输出【样例】之外的任何内容

用户查询：{query}

样例：
1. 问题1
   建议内容
2. 问题2
   建议内容
3. 问题3
   建议内容
"""
