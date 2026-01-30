"""
深度研究 写大纲
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
    """按章拆分大纲内容"""
    # 匹配 ## 开头的章节标题
    chapter_pattern = r'##\s*第[一二三四五六七八九十\d]+章\s*(.+?)(?=##\s*第[一二三四五六七八九十\d]+章|$)'
    matches = re.findall(chapter_pattern, content, re.DOTALL)

    # 同时匹配章节标题
    chapter_title_pattern = r'##\s*(第[一二三四五六七八九十\d]+章\s*[^\n]+)'
    chapter_titles = re.findall(chapter_title_pattern, content)

    chapters = []
    for index, (chapter_content, chapter_title) in enumerate(zip(matches, chapter_titles), 1):
        if chapter_content.strip():
            # 在内容前加上章节标题
            full_content = f"## {chapter_title}\n{chapter_content.strip()}"
            chapters.append({
                "index": index,
                "content": full_content,
                "section_title": chapter_title
            })

    # 如果没有匹配到章节，index的内容为0，content为整个内容
    if not chapters and content.strip():
        chapters = [{
            "index": 0,
            "content": content.strip(),
            "section_title": "整体内容"
        }]

    return chapters

def split_outline_by_chapters(content: str) -> list:
    """按章拆分大纲内容"""
    # 匹配 ## 开头的章节标题
    array = content.split("\n## ")

    chapters = []
    for index, item in enumerate(array, 1):
        title = item.split("\n")[0]
        # title 去掉前面的 ##
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
    测试流式输出接口
    """

    async def stream_generator():
        async for chunk in llm_service.stream(message="测试", model="plan"):
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
    """对计划内容进行拆分，支持completion和stream两种模式生成的内容"""
    start_time = datetime.datetime.now()

    try:
        # 1. 验证参数
        if not report_id:
            raise BizError(code=ErrorCode.get_code(ErrorCode.REPORT_ID_NOT_EXIST),
                           message=ErrorCode.get_message(ErrorCode.REPORT_ID_NOT_EXIST))

        # 2. 获取计划内容 - 根据report_id查询plan数据库
        plan_records = step_record_service.get_records_by_report_id(report_id, "plan")
        if not plan_records or "plan" not in plan_records or not plan_records["plan"]:
            raise BizError(code=ErrorCode.get_code(ErrorCode.PLAN_NOT_EXIST),
                           message=ErrorCode.get_message(ErrorCode.PLAN_NOT_EXIST))

        # 获取最新的计划记录
        plan_record = plan_records["plan"][0]  # 按创建时间倒序，取最新的

        if not plan_record.get("response") or "plan" not in plan_record["response"]:
            raise BizError(code=ErrorCode.get_code(ErrorCode.PLAN_RESPONSE_NOT_EXIST),
                           message=ErrorCode.get_message(ErrorCode.PLAN_RESPONSE_NOT_EXIST))

        plan_content = plan_record["response"]["plan"]
        plan_id = str(plan_record["_id"])
        only_key = plan_record.get("only_key", str(uuid.uuid4()))

        report_service.start_step(report_id, "serp")

        # 删除report_plan_split、report_serp、serp_task集合中的相关记录，但不删除report_plan
        delete_results = step_record_service.delete_records_by_report_id(
            report_id, 
            ['report_plan_split', 'report_serp', 'serp_task']
        )
        logger.info(f"删除相关记录完成: {delete_results}")

        existing_report = report_service.get_report(report_id)

        # 3. 拆分内容
        chapter_records = []
        if existing_report and existing_report.template:
            # 获取所有模板列表
            logger.info(f"获取模板列表template_id : {existing_report.template}")
            template_split = mongo_api_service_manager.get_all__plan_template_split(existing_report.template)
            for template in template_split:
                # 为每个章节创建独立的split记录
                chapter_split_id = step_record_service.upsert_plan_split_record(
                    report_id=report_id,
                    template_id=template["_id"],
                    plan_id=plan_id,
                    original_content=template["content"],  # 存储章节内容而不是原始内容
                    chapters_count=0,  # 这个参数不再使用，但保持兼容性
                    response={
                        "content": [template["content"]],
                        "section_titles": [template["section_title"]]
                    },
                    only_key=only_key,
                    chapter_index=template["index"],  # 添加章节索引
                    section_title=template["section_title"]  # 添加章节标题
                )
                chapter_records.append({
                    "split_id": chapter_split_id,
                    "content": template["content"],
                    "sectionTitle": template["section_title"]
                })
        else:
            chapters = split_outline_by_chapters(plan_content)
            logger.info(f"大纲内容已拆分为 {len(chapters)} 章")

            # 4. 直接存储拆分后的内容到report_plan_split库，不再使用split_chapters库
            for chapter in chapters:
                # 为每个章节创建独立的split记录
                chapter_split_id = step_record_service.upsert_plan_split_record(
                    report_id=report_id,
                    template_id=None,
                    plan_id=plan_id,
                    original_content=chapter["content"],  # 存储章节内容而不是原始内容
                    chapters_count=0,  # 这个参数不再使用，但保持兼容性
                    response={
                        "content": [chapter["content"]],
                        "section_titles": [chapter["section_title"]]
                    },
                    only_key=only_key,
                    chapter_index=chapter["index"],  # 添加章节索引
                    section_title=chapter["section_title"]  # 添加章节标题
                )

                chapter_records.append({
                    "split_id": chapter_split_id,
                    "content": chapter["content"],
                    "sectionTitle": chapter["section_title"]
                })

        logger.info(f"章节内容已直接存储到report_plan_split库，共 {len(chapter_records)} 章")

        # 5. 计算执行时间
        end_time = datetime.datetime.now()
        execution_time = (end_time - start_time).total_seconds()

        # 6. 完成步骤，增加completed_steps
        report_service.complete_step(
            report_id, "serp",
            result={"chapters": chapter_records},
            execution_time=execution_time
        )

        data= {
            "split_id": chapter_records[0]["split_id"] if chapter_records else None,  # 返回第一个章节的split_id作为主要ID
            "chapters_count": len(chapter_records),
            "response": chapter_records,
            "execution_time": execution_time
        }
        return Result.success(data)

    except Exception as e:
        logger.error(f"计划拆分API失败: {str(e)}")
        ## 如果拆分失败 没有第四部的数据 暂时不做标记步骤失败
        raise HTTPException(status_code=500, detail=f"计划拆分失败: {str(e)}")


@router.post("/template/synopsis", response_model=Result)
async def split_plan(llm_message: LLMMessageAskQuestions):
    """选择模版后生成大纲"""
    start_time = datetime.datetime.now()

    try:
        # 1. 验证report_id并获取报告详情
        if not llm_message.report_id:
            raise HTTPException(status_code=400, detail="生成报告大纲需要有效的report_id")

        report_id = llm_message.report_id
        existing_report = report_service.get_report(report_id)
        if not existing_report:
            raise HTTPException(status_code=404, detail="指定的报告ID不存在")

        # 更新报告title
        report_service.update_report_title(report_id, llm_message.message)

        # 删除相关记录
        delete_results = step_record_service.delete_records_by_report_id(report_id)
        logger.info(f"删除相关记录完成: {delete_results}")

        # 删除report_final集合内对应report_id的记录
        final_delete_result = step_record_service.final_collection.delete_many({"report_id": report_id})
        logger.info(f"删除report_final集合记录完成，删除了 {final_delete_result.deleted_count} 条记录")

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
            raise HTTPException(status_code=500, detail="模版不存在")

        # 3. 开始步骤并创建步骤记录
        report_service.start_step(report_id, "plan")
        stream_step_record_id = step_record_service.upsert_plan_record(report_id,llm_message.message)

        # 计算执行时间
        end_time = datetime.datetime.now()
        execution_time = (end_time - start_time).total_seconds()

        # 更新步骤记录，存储完整的大纲内容
        step_record_service.update_plan_record(
            stream_step_record_id, "completed",
            response={"plan": template.get("content", "")},
            execution_time=execution_time
        )

        # 5. 完成步骤
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
        # 标记步骤失败
        if 'report_id' in locals():
            end_time = datetime.datetime.now()
            execution_time = (end_time - start_time).total_seconds()

            report_service.fail_step(
                report_id, "plan",
                error_message=str(e),
                execution_time=execution_time
            )

        logger.error(f"模板报告大纲生成失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"模板报告大纲生成失败: {str(e)}")

@router.post("/stream")
async def chat_stream(
    llm_message: LLMMessage
):
    """生成报告大纲 - stream模式，需要有效的report_id"""
    start_time = datetime.datetime.now()
    
    try:
        # 1. 验证report_id并获取报告详情
        if not llm_message.report_id:
            raise HTTPException(status_code=400, detail="生成报告大纲需要有效的report_id")
        
        report_id = llm_message.report_id
        existing_report = report_service.get_report(report_id)
        if not existing_report:
            raise HTTPException(status_code=404, detail="指定的报告ID不存在")

        # 删除相关记录
        delete_results = step_record_service.delete_records_by_report_id(report_id)
        logger.info(f"删除相关记录完成: {delete_results}")
        
        # 删除report_final集合内对应report_id的记录
        final_delete_result = step_record_service.final_collection.delete_many({"report_id": report_id})
        logger.info(f"删除report_final集合记录完成，删除了 {final_delete_result.deleted_count} 条记录")

        # 保存调用参数记录到report_ask_questions表
        # step_record_service.update_ask_questions_message(report_id, llm_message.message)

        # 使用数据库中的报告内容
        report_message = existing_report.message
        logger.info(f"使用现有报告内容生成流式大纲，ID: {report_id}, Message: {report_message[:100]}...")
        
        # 处理模板相关逻辑 - 从reports库中获取template字段（存储的是template_id）
        template_content = None
        existing_report = report_service.get_report(report_id)
        # if existing_report and hasattr(existing_report, 'template') and existing_report.template:
        #     # template字段存储的是template_id，需要查询report_plan_template集合获取实际内容
        #     template_id = existing_report.template
        #     template = mongo_api_service_manager.get_plan_template_by_id(template_id)
        #     if template:
        #         template_content = template.get("content", "")
        #         logger.info(f"使用报告中的模板内容生成流式大纲，报告ID: {report_id}, 模板ID: {template_id}")
        #     else:
        #         logger.warning(f"模板不存在，模板ID: {template_id}")
        # else:
        #     logger.info(f"报告中没有模板ID，使用默认方式生成流式大纲，报告ID: {report_id}")
        
        # 3. 开始步骤并创建步骤记录
        report_service.start_step(report_id, "plan")
        stream_step_record_id = step_record_service.upsert_plan_record(report_id, report_message)
        
        # 3. 创建流式响应生成器，包含内容收集和存储逻辑
        async def stream_with_content_collection():
            chunks = []
            full_content = ""

            try:
                # 获取流式响应
                async for chunk in mongo_api_service_manager.stream_service.llm_service.stream(
                    message=write_report_plan_prompt(report_message, template_content),model="plan"
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

                # 4. 在后台异步处理内容存储
                async def process_content_and_store():
                    try:
                        if full_content:
                            # 计算执行时间
                            end_time = datetime.datetime.now()
                            execution_time = (end_time - start_time).total_seconds()

                            # 更新步骤记录，存储完整的大纲内容
                            step_record_service.update_plan_record(
                                stream_step_record_id, "completed",
                                response={"plan": full_content},
                                execution_time=execution_time
                            )

                        # 5. 完成步骤
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
                        logger.error(f"后台处理流式内容失败: {str(e)}")
                        # 标记步骤失败
                        end_time = datetime.datetime.now()
                        execution_time = (end_time - start_time).total_seconds()

                        report_service.fail_step(
                            report_id, "plan",
                            error_message=str(e),
                            execution_time=execution_time
                        )

                        # 更新步骤记录状态
                        step_record_service.update_plan_record(
                            stream_step_record_id, "failed",
                            error_message=str(e),
                            execution_time=execution_time
                        )

                # 启动后台任务处理内容存储
                asyncio.create_task(process_content_and_store())

            except Exception as e:
                logger.error(f"流式处理失败: {str(e)}")
                # 标记步骤失败
                end_time = datetime.datetime.now()
                execution_time = (end_time - start_time).total_seconds()

                report_service.fail_step(
                    report_id, "plan",
                    error_message=str(e),
                    execution_time=execution_time
                )

                # 更新步骤记录状态
                step_record_service.update_plan_record(
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
                report_id, "plan",
                error_message=str(e),
                execution_time=execution_time
            )
        
        logger.error(f"流式报告大纲API失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"流式生成报告大纲失败: {str(e)}")

"""
    根据report_id查询详情
"""
@router.get("/detail/{report_id}", response_model=Result)
async def get_detail(
    report_id: str  # 改为字符串类型，支持ObjectId
):
    """
    根据报告ID获取详细信息（如有多条记录返回最新的）
    """
    return Result.success(mongo_api_service_manager.get_plan_by_report_id(report_id))

@router.put("/update", response_model=Result)
async def update(
    dto: UpdatePlan
):
    """
    更新大纲
    """

    plan = mongo_api_service_manager.get_plan_by_report_id(dto.report_id)
    if not plan:
        raise BizError(code=ErrorCode.get_code(ErrorCode.PLAN_NOT_EXIST),
                       message=ErrorCode.get_message(ErrorCode.PLAN_NOT_EXIST))

    mongo_api_service_manager.update_report_plan(plan["_id"], dto.plan)
    return Result.success(True)


# 提示词
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
- 每个章节分为5-10个子标题，尽可能展示所有的信息
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