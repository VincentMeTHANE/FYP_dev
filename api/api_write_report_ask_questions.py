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

llm_service = LLMService()

@router.post("/stream")
async def chat_stream(
    llm_message: LLMMessageAskQuestions
):
    """
    Stream questions - creates new report if no report_id provided
    """
    start_time = datetime.datetime.now()
    logger.info(f"llm_message: {llm_message}")
    
    try:
        if llm_message.report_id:
            report_id = llm_message.report_id
            existing_report = report_service.get_report(report_id)
            logger.info(f"existing_report: {existing_report}")
            if not existing_report:
                raise BizError(code=ErrorCode.get_code(ErrorCode.REPORT_NOT_EXIST),
                               message=ErrorCode.get_message(ErrorCode.REPORT_NOT_EXIST))

            if llm_message.message:
                report_message = llm_message.message
                report_service.update_report_title(report_id, llm_message.message)
            else:
                raise BizError(code=ErrorCode.get_code(ErrorCode.REPORT_TITLE_NOT_EXIST),
                               message=ErrorCode.get_message(ErrorCode.REPORT_TITLE_NOT_EXIST))

        else:
            raise BizError(code=ErrorCode.get_code(ErrorCode.REPORT_NOT_EXIST),
                           message=ErrorCode.get_message(ErrorCode.REPORT_NOT_EXIST))

        template = None
        if llm_message.template_id:
            template = mongo_api_service_manager.get_plan_template_by_id(llm_message.template_id)
            if template:
                from bson import ObjectId
                from utils.database import mongo_db
                mongo_db.reports.update_one(
                    {"_id": ObjectId(report_id)}, 
                    {"$set": {"template": llm_message.template_id, "is_replace": template.get("is_replace")}}
                )
                logger.info(f"Updated report template, report_id: {report_id}, template_id: {llm_message.template_id}")
            else:
                logger.warning(f"Template not found, template_id: {llm_message.template_id}")
        else:
            from bson import ObjectId
            from utils.database import mongo_db
            mongo_db.reports.update_one(
                {"_id": ObjectId(report_id)}, 
                {"$set": {"template": "", "is_replace": False}}
            )
            logger.info(f"Cleared report template, report_id: {report_id}")

        report_service.start_step(report_id, "ask_questions")
        stream_step_record_id = step_record_service.create_ask_questions_record(report_id, report_message)

        async def update_completion_status():
            await asyncio.sleep(3)
            try:
                end_time = datetime.datetime.now()
                execution_time = (end_time - start_time).total_seconds()
                
                current_report = report_service.get_report(report_id)
                if current_report and current_report.steps.ask_questions.status == "processing":
                    report_service.complete_step(
                        report_id, "ask_questions",
                        execution_time=execution_time
                    )
                    step_record_service.update_ask_questions_record(
                        stream_step_record_id, "completed",
                        execution_time=execution_time
                    )
            except Exception as e:
                logger.error(f"Failed to update streaming status: {str(e)}")
                end_time = datetime.datetime.now()
                execution_time = (end_time - start_time).total_seconds()
                report_service.fail_step(
                    report_id, "ask_questions",
                    error_message=str(e),
                    execution_time=execution_time
                )
                step_record_service.update_ask_questions_record(
                    stream_step_record_id, "failed",
                    error_message=str(e),
                    execution_time=execution_time
                )
        
        asyncio.create_task(update_completion_status())

        if template and template.get("is_replace"):
            step_record_service.update_ask_questions_message(report_id, template.get("content"))

            async def empty_stream_generator():
                yield "data: [DONE]\n\n"
            return StreamingResponse(
                empty_stream_generator(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
            )
        else:
            chunks = []

            async def wrapped_stream_generator():
                nonlocal chunks
                try:
                    original_response = await mongo_api_service_manager.execute_stream_api(
                        query=report_message,
                        query_type="ask_questions",
                        title_prefix="询问",
                        prompt_builder=prompt,
                        report_id=report_id,
                        model="plan"
                    )

                    async for chunk in original_response.body_iterator:
                        parsed_chunk = mongo_api_service_manager.stream_service._parse_sse_chunk(chunk)
                        if parsed_chunk:
                            chunks.append(parsed_chunk)
                            yield f"data: {json.dumps(parsed_chunk)}\n\n"
                        else:
                            yield chunk
                    yield "data: [DONE]\n\n"

                    full_content = mongo_api_service_manager.stream_service._collect_content_from_chunks(chunks)

                    step_record_service.update_ask_questions_message(report_id, str(full_content))
                except Exception as stream_e:

                    report_service.fail_step(
                        report_id, "final_report",
                        error_message=str(stream_e),
                        execution_time=(datetime.datetime.now() - start_time).total_seconds()
                    )

                    logger.error(f"Error during streaming: {str(stream_e)}")
                    raise

        return StreamingResponse(
            wrapped_stream_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
        )
        
    except Exception as e:
        if 'report_id' in locals():
            end_time = datetime.datetime.now()
            execution_time = (end_time - start_time).total_seconds()
            
            report_service.fail_step(
                report_id, "ask_questions",
                error_message=str(e),
                execution_time=execution_time
            )
            
            if 'stream_step_record_id' in locals():
                step_record_service.update_ask_questions_record(
                    stream_step_record_id, "failed",
                    error_message=str(e),
                    execution_time=execution_time
                )
        
        logger.error(f"Stream questions API failed: {str(e)}")
        raise ValueError(f"Stream questions failed: {str(e)}")


@router.get("/detail/{report_id}", response_model=Result)
async def get_detail(
    report_id: str
):
    """
    Get details by report_id
    """
    return Result.success(mongo_api_service_manager.get_ask_detail(report_id))

@router.put("/update", response_model=Result)
async def update(
    dto: UpdateQuestion
):
    """
    Update questions
    """
    return Result.success(step_record_service.update_ask_questions_message(dto.report_id, dto.message))


def prompt(query: str):
    return f"""
根据用户查询，提供5个相关的后续研究问题。每个问题后面给出简短建议。
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
