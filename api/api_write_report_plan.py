"""
Deep Research - Report Outline Generation
"""

import logging
import datetime
import asyncio
import uuid
import re
import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from models.models import LLMMessage, UpdatePlan, LLMMessageAskQuestions
from services.llm_service import llm_service
from services.mongo_api_service_manager import mongo_api_service_manager
from services.report_service import report_service
from services.step_record_service import step_record_service
from utils.exception_handler import ErrorCode
from utils.response_models import Result, BizError

logger = logging.getLogger(__name__)

router = APIRouter()


def split_outline_by_chapters1(content: str) -> list:
    """Split outline content by chapters"""
    chapter_pattern = r'##\s*第[一二三四五六七八九十\d]+章\s*(.+?)(?=##\s*第[一二三四五六七八九十\d]+章|$)'
    matches = re.findall(chapter_pattern, content, re.DOTALL)

    chapter_title_pattern = r'##\s*(第[一二三四五六七八九十\d]+章\s*[^\n]+)'
    chapter_titles = re.findall(chapter_title_pattern, content)

    chapters = []
    for index, (chapter_content, chapter_title) in enumerate(zip(matches, chapter_titles), 1):
        if chapter_content.strip():
            full_content = f"## {chapter_title}\n{chapter_content.strip()}"
            chapters.append({
                "index": index,
                "content": full_content,
                "section_title": chapter_title
            })

    if not chapters and content.strip():
        chapters = [{
            "index": 0,
            "content": content.strip(),
            "section_title": "Overall Content"
        }]

    return chapters

def split_outline_by_chapters(content: str) -> list:
    """Split outline content by chapters"""
    array = content.split("\n## ")

    chapters = []
    for index, item in enumerate(array, 1):
        title = item.split("\n")[0]
        title = title.replace("\n## ", "")
        title = title.replace("## ", "")
        chapters.append({
            "index": index,
            "content": item,
            "section_title": title
        })

    return chapters

@router.get("/test", response_model=Result)
async def get_test():
    """
    Test streaming output endpoint
    """

    async def stream_generator():
        async for chunk in llm_service.stream(message="Test", model="plan"):
            yield chunk

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )


@router.post("/split/{report_id}", response_model=Result)
async def split_plan(
    report_id: str
):
    """Split plan content, supporting content generated in completion and stream modes"""
    start_time = datetime.datetime.now()

    try:
        if not report_id:
            raise BizError(code=ErrorCode.get_code(ErrorCode.REPORT_ID_NOT_EXIST),
                           message=ErrorCode.get_message(ErrorCode.REPORT_ID_NOT_EXIST))

        plan_records = step_record_service.get_records_by_report_id(report_id, "plan")
        if not plan_records or "plan" not in plan_records or not plan_records["plan"]:
            raise BizError(code=ErrorCode.get_code(ErrorCode.PLAN_NOT_EXIST),
                           message=ErrorCode.get_message(ErrorCode.PLAN_NOT_EXIST))

        plan_record = plan_records["plan"][0]

        if not plan_record.get("response") or "plan" not in plan_record["response"]:
            raise BizError(code=ErrorCode.get_code(ErrorCode.PLAN_RESPONSE_NOT_EXIST),
                           message=ErrorCode.get_message(ErrorCode.PLAN_RESPONSE_NOT_EXIST))

        plan_content = plan_record["response"]["plan"]
        plan_id = str(plan_record["_id"])
        only_key = plan_record.get("only_key", str(uuid.uuid4()))

        report_service.start_step(report_id, "serp")

        delete_results = step_record_service.delete_records_by_report_id(
            report_id, 
            ['report_plan_split', 'report_serp', 'serp_task']
        )
        logger.info(f"Deleted related records: {delete_results}")

        existing_report = report_service.get_report(report_id)

        chapter_records = []
        if existing_report and existing_report.template:
            logger.info(f"Getting template list template_id: {existing_report.template}")
            template_split = mongo_api_service_manager.get_all__plan_template_split(existing_report.template)
            for template in template_split:
                chapter_split_id = step_record_service.upsert_plan_split_record(
                    report_id=report_id,
                    template_id=template["_id"],
                    plan_id=plan_id,
                    original_content=template["content"],
                    chapters_count=0,
                    response={
                        "content": [template["content"]],
                        "section_titles": [template["section_title"]]
                    },
                    only_key=only_key,
                    chapter_index=template["index"],
                    section_title=template["section_title"]
                )
                chapter_records.append({
                    "split_id": chapter_split_id,
                    "content": template["content"],
                    "sectionTitle": template["section_title"]
                })
        else:
            chapters = split_outline_by_chapters(plan_content)
            logger.info(f"Outline split into {len(chapters)} chapters")

            for chapter in chapters:
                chapter_split_id = step_record_service.upsert_plan_split_record(
                    report_id=report_id,
                    template_id=None,
                    plan_id=plan_id,
                    original_content=chapter["content"],
                    chapters_count=0,
                    response={
                        "content": [chapter["content"]],
                        "section_titles": [chapter["section_title"]]
                    },
                    only_key=only_key,
                    chapter_index=chapter["index"],
                    section_title=chapter["section_title"]
                )

                chapter_records.append({
                    "split_id": chapter_split_id,
                    "content": chapter["content"],
                    "sectionTitle": chapter["section_title"]
                })

        logger.info(f"Chapter content stored to report_plan_split, total {len(chapter_records)} chapters")

        end_time = datetime.datetime.now()
        execution_time = (end_time - start_time).total_seconds()

        report_service.complete_step(
            report_id, "serp",
            result={"chapters": chapter_records},
            execution_time=execution_time
        )

        data= {
            "split_id": chapter_records[0]["split_id"] if chapter_records else None,
            "chapters_count": len(chapter_records),
            "response": chapter_records,
            "execution_time": execution_time
        }
        return Result.success(data)

    except Exception as e:
        logger.error(f"Plan split API failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Plan split failed: {str(e)}")


@router.post("/template/synopsis", response_model=Result)
async def split_plan(llm_message: LLMMessageAskQuestions):
    """Generate outline after selecting template"""
    start_time = datetime.datetime.now()

    try:
        if not llm_message.report_id:
            raise HTTPException(status_code=400, detail="Valid report_id required for outline generation")

        report_id = llm_message.report_id
        existing_report = report_service.get_report(report_id)
        if not existing_report:
            raise HTTPException(status_code=404, detail="Report ID does not exist")

        report_service.update_report_title(report_id, llm_message.message)

        delete_results = step_record_service.delete_records_by_report_id(report_id)
        logger.info(f"Deleted related records: {delete_results}")

        final_delete_result = step_record_service.final_collection.delete_many({"report_id": report_id})
        logger.info(f"Deleted report_final records: {final_delete_result.deleted_count} records")

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
            raise HTTPException(status_code=500, detail="Template does not exist")

        report_service.start_step(report_id, "plan")
        stream_step_record_id = step_record_service.upsert_plan_record(report_id,llm_message.message)

        end_time = datetime.datetime.now()
        execution_time = (end_time - start_time).total_seconds()

        step_record_service.update_plan_record(
            stream_step_record_id, "completed",
            response={"plan": template.get("content", "")},
            execution_time=execution_time
        )

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
                    "content": template.get("content", "")
                },
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }
        }

        report_service.complete_step(
            report_id, "plan",
            result=llm_response,
            execution_time=execution_time
        )

        return Result.success({"plan": template.get("content", "")})
    except Exception as e:
        if 'report_id' in locals():
            end_time = datetime.datetime.now()
            execution_time = (end_time - start_time).total_seconds()

            report_service.fail_step(
                report_id, "plan",
                error_message=str(e),
                execution_time=execution_time
            )

        logger.error(f"Template outline generation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Template outline generation failed: {str(e)}")

@router.post("/stream")
async def chat_stream(
    llm_message: LLMMessage
):
    """Generate report outline - stream mode, requires valid report_id"""
    start_time = datetime.datetime.now()
    
    try:
        if not llm_message.report_id:
            raise HTTPException(status_code=400, detail="Valid report_id required for outline generation")
        
        report_id = llm_message.report_id
        existing_report = report_service.get_report(report_id)
        if not existing_report:
            raise HTTPException(status_code=404, detail="Report ID does not exist")

        delete_results = step_record_service.delete_records_by_report_id(report_id)
        logger.info(f"Deleted related records: {delete_results}")
        
        final_delete_result = step_record_service.final_collection.delete_many({"report_id": report_id})
        logger.info(f"Deleted report_final records: {final_delete_result.deleted_count} records")

        report_message = existing_report.message
        logger.info(f"Using existing report content for streaming outline, ID: {report_id}, Message: {report_message[:100]}...")
        
        template_content = None
        existing_report = report_service.get_report(report_id)
        
        report_service.start_step(report_id, "plan")
        stream_step_record_id = step_record_service.upsert_plan_record(report_id, report_message)
        
        async def stream_with_content_collection():
            chunks = []
            full_content = ""

            try:
                async for chunk in mongo_api_service_manager.stream_service.llm_service.stream(
                    message=write_report_plan_prompt(report_message, template_content),model="plan"
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
                        if full_content:
                            end_time = datetime.datetime.now()
                            execution_time = (end_time - start_time).total_seconds()

                            step_record_service.update_plan_record(
                                stream_step_record_id, "completed",
                                response={"plan": full_content},
                                execution_time=execution_time
                            )

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
                                "prompt_tokens": len(write_report_plan_prompt(report_message).split()),
                                "completion_tokens": len(full_content.split()),
                                "total_tokens": len(write_report_plan_prompt(report_message).split()) + len(full_content.split())
                            }
                        }

                        report_service.complete_step(
                            report_id, "plan",
                            result=llm_response,
                            execution_time=execution_time
                        )
                    except Exception as e:
                        logger.error(f"Background processing failed: {str(e)}")
                        end_time = datetime.datetime.now()
                        execution_time = (end_time - start_time).total_seconds()

                        report_service.fail_step(
                            report_id, "plan",
                            error_message=str(e),
                            execution_time=execution_time
                        )

                        step_record_service.update_plan_record(
                            stream_step_record_id, "failed",
                            error_message=str(e),
                            execution_time=execution_time
                        )

                asyncio.create_task(process_content_and_store())

            except Exception as e:
                logger.error(f"Streaming failed: {str(e)}")
                end_time = datetime.datetime.now()
                execution_time = (end_time - start_time).total_seconds()

                report_service.fail_step(
                    report_id, "plan",
                    error_message=str(e),
                    execution_time=execution_time
                )

                step_record_service.update_plan_record(
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
                report_id, "plan",
                error_message=str(e),
                execution_time=execution_time
            )
        
        logger.error(f"Stream outline API failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Stream outline generation failed: {str(e)}")


@router.get("/detail/{report_id}", response_model=Result)
async def get_detail(
    report_id: str
):
    """
    Get details by report_id (returns latest if multiple records)
    """
    return Result.success(mongo_api_service_manager.get_plan_by_report_id(report_id))

@router.put("/update", response_model=Result)
async def update(
    dto: UpdatePlan
):
    """
    Update outline
    """

    plan = mongo_api_service_manager.get_plan_by_report_id(dto.report_id)
    if not plan:
        raise BizError(code=ErrorCode.get_code(ErrorCode.PLAN_NOT_EXIST),
                       message=ErrorCode.get_message(ErrorCode.PLAN_NOT_EXIST))

    mongo_api_service_manager.update_report_plan(plan["_id"], dto.plan)
    return Result.success(True)


def write_report_plan_prompt(message: str, template_content: str = None):
    template_prompt = ""
    if template_content:
        template_prompt = f"""
请参考以下模板的内容来生成大纲：
<模板>
{template_content}
</模板>
请根据用户查询内容，结合上述模板结构，生成符合要求的大纲，根据实际查询内容对大纲进行调整。
"""

    return f"""
给定用户的以下查询：
<查询>
{message}
</查询>

- 只输出大纲内容，不要输出其他内容
- 根据主题和反馈为报告生成章节列表。
- 章节列表应从浅到深。
- 你的计划应该紧凑而集中，没有重叠的部分或不必要的填充物。 
- 章节数量不设限制，尽可能的展示所有信息。
- 章节数量不超过3个，每个章节分为3个子标题，尽可能展示所有的信息
- 每节都需要一个句子来总结其副标题。
- 确保每个部分都有不同的目的，没有内容重叠。
- 将相关概念结合起来，而不是将它们分开。
- 关键：每个部分都必须与主题直接相关。
- 避免不直接涉及核心主题的切线或松散相关的部分。
- 在提交之前，请检查您的结构，以确保它没有多余的部分，并遵循逻辑流程。
- 严格按照示例的格式输出。
- 标题总结内容不要输出具体内容，尽可能多的描述这个章节所需要分析的内容，后续我要用这个通过网络检索信息。
- 所有的章节内容，应该只涉及用户需要查询的内容，不要输出不相关的内容
- 不要输出细节，只输出章节标题和子标题。用最少的字描述完整章节内容。

{template_prompt}

<例子>
## 第一章 Title
需要检索的内容
#### 第一节 sub title
需要检索的内容
#### 第二节 sub title
需要检索的内容

---

## 1. Title
需要检索的内容
#### 第一节 sub title
需要检索的内容

---

## xxx. Title
需要检索的内容
#### 第一节 sub title
需要检索的内容
#### 第二节 sub title
需要检索的内容
#### 第三节 sub title
需要检索的内容
</例子>
"""