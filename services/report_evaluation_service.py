"""
报告评估服务模块
提供数据提取、Context Precision计算、G-Eval主题契合度评估、数据回写等功能

评估指标包括：
- Context Precision (基础)
- Weighted Precision@K (位置加权)
- NDCG@K (归一化折扣累积增益)
- End-to-End RAG Precision (端到端评估)
- 区分 RAG 和 Web 来源的评估
"""

import asyncio
import logging
import math
import re
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from bson import ObjectId

from config import settings
from utils.database import mongo_db
from models.models import LLMRequest

logger = logging.getLogger(__name__)

# 评估模型 Temperature（优先使用配置文件的设置）
EVALUATION_MODEL_TEMPERATURE = 0.2  # 服务内部默认值

# ===== Context Precision 评估提示词（改进版 - 多维度评估）=====
EVALUATION_SYSTEM_PROMPT = """您是一个专业的RAG评估专家。请从以下维度评估检索文本与查询的相关性：

1. 主题匹配度 (0-1): 检索内容是否涉及查询的核心主题
2. 信息有用性 (0-1): 是否包含回答查询所需的具体信息、事实或数据
3. 内容质量 (0-1): 来源是否可靠，内容是否准确（不是泛泛而谈）

判断标准：
- Relevant: 综合得分 >= 0.6，且各维度 >= 0.3
- Irrelevant: 综合得分 < 0.6，或任一维度 < 0.2

请只回答：Relevant 或 Irrelevant"""

EVALUATION_USER_PROMPT = """查询：{query}
研究目标：{research_goal}

待评估文本：
{retrieved_text}

请判断该文本是否对回答查询有帮助？（Relevant / Irrelevant）"""

# ===== 端到端 RAG 评估提示词（检查章节是否使用摘要知识）=====
E2E_EVALUATION_SYSTEM_PROMPT = """您是一个专业的RAG系统评估专家。请评估章节内容是否与检索摘要主题相关。

评估标准：
1. 主题相关性: 章节内容是否围绕摘要的主题展开
2. 知识连贯性: 章节内容是否自然地延续了摘要中的信息（即使经过改写）

判断标准：
- Used: 章节内容主题与摘要相关，内容是基于摘要信息展开的
- Not Used: 章节内容主题与摘要完全无关，或由模型凭空生成

请只回答：Used 或 Not Used"""

E2E_EVALUATION_USER_PROMPT = """【查询】{query}
【研究目标】{research_goal}

【检索摘要】
{retrieved_text}

【章节内容】
{final_content}

请判断：章节内容是否基于检索摘要生成/展开？（Used / Not Used）"""


# ===== 辅助评估函数 =====

def calculate_weighted_precision(relevance_results: List[bool], k: int = 10) -> float:
    """
    计算位置加权的 Precision@K
    位置1的权重最高，位置越靠后权重越低（使用倒数衰减）

    Args:
        relevance_results: 相关性判断结果列表 [True, False, True, ...]
        k: 只考虑前 k 个结果

    Returns:
        加权后的 Precision@K 值
    """
    if not relevance_results:
        return 0.0

    results = relevance_results[:k]
    weighted_sum = 0.0
    total_weight = 0.0

    for i, is_relevant in enumerate(results):
        # 倒数衰减：weight = 1 / (i + 1)
        weight = 1.0 / (i + 1)
        total_weight += weight
        if is_relevant:
            weighted_sum += weight

    return weighted_sum / total_weight if total_weight > 0 else 0.0


def calculate_ndcg(relevance_results: List[bool], k: int = 10) -> float:
    """
    计算 NDCG@K (归一化折扣累积增益)
    考虑了位置因素的评估指标，越靠前的相关结果贡献越大

    Args:
        relevance_results: 相关性判断结果列表 [True, False, True, ...]
        k: 只考虑前 k 个结果

    Returns:
        NDCG@K 值，范围 [0, 1]
    """
    if not relevance_results:
        return 0.0

    def dcg_at_k(results: List[bool], k: int) -> float:
        """计算 DCG@K"""
        dcg = 0.0
        for i, is_relevant in enumerate(results[:k]):
            # 位置从1开始，所以是 log2(i+2)
            rel = 1.0 if is_relevant else 0.0
            dcg += rel / math.log2(i + 2)
        return dcg

    results = relevance_results[:k]

    # 计算 DCG@K
    dcg = dcg_at_k(results, k)

    # 计算 IDCG@K（理想情况：所有相关结果排在前面）
    relevant_count = sum(1 for r in results if r)
    ideal_results = [True] * relevant_count + [False] * (k - relevant_count)
    idcg = dcg_at_k(ideal_results, k)

    # NDCG = DCG / IDCG
    return dcg / idcg if idcg > 0 else 0.0


def calculate_average_precision(relevance_results: List[bool]) -> float:
    """
    计算 Average Precision (AP)
    用于后续计算 MAP (Mean Average Precision)

    Args:
        relevance_results: 相关性判断结果列表

    Returns:
        Average Precision 值
    """
    if not relevance_results:
        return 0.0

    precisions = []
    relevant_so_far = 0

    for i, is_relevant in enumerate(relevance_results):
        if is_relevant:
            relevant_so_far += 1
            precision_at_i = relevant_so_far / (i + 1)
            precisions.append(precision_at_i)

    return sum(precisions) / len(precisions) if precisions else 0.0

# ===== G-Eval 内容质量评估提示词 =====
GEVAL_SYSTEM_PROMPT = """您是一个专业的报告评估专家。请评估报告内容与原始大纲的契合程度。"""

GEVAL_USER_PROMPT = """请评估以下报告内容与原始大纲的契合程度。

【原始大纲】
{outline}

【待评估报告内容】
{report_text}

评估标准：
1. 内容是否紧扣大纲主题
2. 章节结构是否与大纲一致
3. 论述深度是否充分
4. 信息准确性

请按以下格式输出：

**评估推理过程：**
[详细说明你的评估思路和分析过程]

**最终评分：**
[1-5]  # 只输出一个数字，1=差，5=优秀"""


class ReportEvaluationService:
    """报告评估服务"""

    def __init__(self):
        self._llm_initialized = False

    async def _get_llm_response(self, messages: List[Dict[str, str]], model: str = None) -> str:
        """调用 LLM 获取响应"""
        try:
            import httpx

            model = model or settings.LLM_MODEL
            _eval_entity = {
                "name": settings.LLM_MODEL,
                "url": "https://dashscope.aliyuncs.com/compatible-mode",
                "api_key": settings.LLM_API_KEY
            }
            llm_entity = settings.LLM_ENTITY.get("evaluation") or settings.LLM_ENTITY.get("search_summary", _eval_entity)

            payload = {
                "model": llm_entity["name"],
                "messages": messages,
                "temperature": EVALUATION_MODEL_TEMPERATURE,
                "stream": False
            }

            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{llm_entity['url']}/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {llm_entity['api_key']}",
                        "Content-Type": "application/json"
                    },
                    json=payload
                )

                if response.status_code == 200:
                    result = response.json()
                    return result["choices"][0]["message"]["content"]
                else:
                    logger.error(f"LLM API 调用失败: {response.status_code} - {response.text}")
                    raise Exception(f"LLM API 调用失败: {response.status_code}")

        except Exception as e:
            logger.error(f"获取 LLM 响应失败: {str(e)}")
            raise

    async def fetch_eval_data(self, report_id: str) -> Dict[str, Any]:
        """
        从 MongoDB 多个集合提取评估所需数据

        Args:
            report_id: 报告ID

        Returns:
            评估数据结构
        """
        try:
            logger.info(f"开始提取报告 {report_id} 的评估数据")

            # 1. 从 report_plan 集合获取大纲
            report_plan = mongo_db["report_plan"].find_one({"report_id": report_id})
            outline = ""
            if report_plan and "response" in report_plan and "plan" in report_plan["response"]:
                outline = report_plan["response"]["plan"]

            # 2. 从 serp_task 集合获取查询词和研究目标，同时获取 task_id 用于后续查询 search_results
            serp_tasks = list(mongo_db["serp_task"].find({"report_id": report_id}))
            logger.info(f"从 serp_task 集合获取到 {len(serp_tasks)} 条记录")
            
            # 如果 serp_task 为空，尝试其他可能的查询方式
            if not serp_tasks:
                # 尝试使用 report_id 作为字符串查询
                serp_tasks_by_str = list(mongo_db["serp_task"].find({"report_id": {"$regex": report_id}}))
                logger.info(f"使用正则查询 serp_task 找到 {len(serp_tasks_by_str)} 条")
                
                # 尝试查找是否有其他报告ID格式
                all_reports_sample = list(mongo_db["serp_task"].find({}).limit(5))
                if all_reports_sample:
                    sample_report_ids = [t.get("report_id", "") for t in all_reports_sample[:3]]
                    logger.info(f"serp_task 中的样本 report_id: {sample_report_ids}")
                    logger.info(f"当前查询的 report_id: {report_id}")
            
            serp_data_map = {}
            serp_task_ids = {}  # chapter_index -> task_id 映射
            for idx, task in enumerate(serp_tasks):
                task_id = str(task.get("_id", ""))
                chapter_idx = task.get("chapter_index", idx)  # 如果没有 chapter_index，使用循环索引
                serp_task_ids[chapter_idx] = task_id
                serp_data_map[chapter_idx] = {
                    "query": task.get("query", ""),
                    "research_goal": task.get("research_goal", ""),
                    "task_id": task_id
                }
                logger.debug(f"serp_task {idx}: _id={task_id}, chapter_index={chapter_idx}, query={task.get('query', '')[:50]}")

            logger.info(f"serp_task_ids 映射: {serp_task_ids}")

            # 3. 从 search_results 集合获取 Top-K 检索文本（按 task_id 查询）
            # 4. 从 report_search_summary 集合获取章节摘要（用于评估）
            search_data_map = {}  # chapter_idx -> [content, ...]
            search_data_by_type = {}  # chapter_idx -> {"online": [...], "knowledge": [...]}
            summary_data_map = {}  # chapter_idx -> summary_content
            
            for chapter_idx, task_id in serp_task_ids.items():
                # 先检查 search_results 集合的实际数据格式
                # 方法1: 按 task_id 查询
                search_results_by_task = list(mongo_db["search_results"].find({"task_id": task_id}))
                # 方法2: 按 _id ObjectId 查询
                try:
                    from bson import ObjectId
                    search_results_by_object_id = list(mongo_db["search_results"].find({"task_id": ObjectId(task_id)}))
                except:
                    search_results_by_object_id = []
                
                logger.info(f"章节 {chapter_idx}: task_id={task_id}, 按task_id查到{len(search_results_by_task)}条, 按ObjectId查到{len(search_results_by_object_id)}条")
                
                # 尝试找到有数据的查询方式
                search_results = search_results_by_task if search_results_by_task else search_results_by_object_id
                
                # 如果还是没有数据，尝试其他查询方式
                if not search_results:
                    split_id = task.get("split_id", "")
                    if split_id:
                        search_results_by_split = list(mongo_db["search_results"].find({"split_id": split_id}))
                        logger.info(f"章节 {chapter_idx}: 按split_id={split_id}查到{len(search_results_by_split)}条")
                        if search_results_by_split:
                            search_results = search_results_by_split
                    
                    if not search_results:
                        search_results_by_report = list(mongo_db["search_results"].find({"report_id": report_id}))
                        logger.info(f"章节 {chapter_idx}: 按report_id查到{len(search_results_by_report)}条")
                        if search_results_by_report:
                            search_results = search_results_by_report
                
                logger.info(f"章节 {chapter_idx} 最终从 search_results 集合获取到 {len(search_results)} 条记录")
                
                # ===== 区分 RAG 和 Web 搜索结果 =====
                chapter_knowledge = []  # 所有结果
                online_results = []  # 网络搜索结果 (type="online")
                rag_results = []  # RAG 知识库结果 (type="knowledge")
                
                for result in search_results:
                    # 提取 content 字段作为检索文本
                    content = result.get("content", "") or result.get("raw_content", "")
                    if content:
                        chapter_knowledge.append(content)
                        
                        # 按类型分类
                        result_type = result.get("type", "online")
                        if result_type == "knowledge":
                            rag_results.append(content)
                        else:
                            online_results.append(content)
                
                search_data_map[chapter_idx] = chapter_knowledge
                search_data_by_type[chapter_idx] = {
                    "online": online_results,
                    "knowledge": rag_results
                }
                
                logger.info(f"章节 {chapter_idx} 提取到 {len(chapter_knowledge)} 条知识数据 (Web: {len(online_results)}, RAG: {len(rag_results)})")
                
                # ===== 从 report_search_summary 集合获取章节摘要 =====
                # 注意：report_search_summary 存储时用的是 task_id
                if task_id:
                    summary_docs = list(mongo_db["report_search_summary"].find({
                        "task_id": task_id
                    }))
                    
                    logger.info(f"章节 {chapter_idx} summary 查询: task_id={task_id}, 找到 {len(summary_docs)} 条记录")
                    
                    if summary_docs:
                        # 合并所有 summary 内容
                        summary_parts = []
                        for doc in summary_docs:
                            response_data = doc.get("response", {})
                            choices = response_data.get("choices", []) if isinstance(response_data, dict) else []
                            if choices and len(choices) > 0:
                                message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
                                content = message.get("content", "") if isinstance(message, dict) else ""
                                if content:
                                    summary_parts.append(content)
                                    logger.debug(f"章节 {chapter_idx} summary 内容长度: {len(content)}")
                        
                        if summary_parts:
                            summary_data_map[chapter_idx] = "\n\n".join(summary_parts)
                            logger.info(f"章节 {chapter_idx} 从 summary 获取到 {len(summary_parts)} 条摘要，总长度={len(summary_data_map[chapter_idx])}")
                        else:
                            logger.warning(f"章节 {chapter_idx} summary_docs 有 {len(summary_docs)} 条但无有效内容")
                    else:
                        logger.warning(f"章节 {chapter_idx} 未从 summary 获取到数据（task_id={task_id}）")

            # 4. 从 report_final 集合获取最终报告内容
            final_report_docs = list(mongo_db["report_final"].find({"report_id": report_id}).sort("chapter_index", 1))
            logger.info(f"从 report_final 集合获取到 {len(final_report_docs)} 条记录")
            
            content_map = {}
            for doc in final_report_docs:
                chapter_idx = doc.get("chapter_index", 0)
                # report_final 集合中的内容存储在 current 字段中
                current_content = doc.get("current", "")
                if current_content:
                    content_map[chapter_idx] = current_content
                    logger.debug(f"章节 {chapter_idx} 提取到内容长度: {len(current_content)}")
                else:
                    logger.warning(f"章节 {chapter_idx} 未找到 current 字段内容")
            
            logger.info(f"共提取到 {len(content_map)} 个章节的内容，outline 长度: {len(outline)}")

            # 5. 构建章节数据
            chapters = []
            all_chapter_indices = set()
            all_chapter_indices.update(serp_data_map.keys())
            all_chapter_indices.update(search_data_map.keys())
            all_chapter_indices.update(content_map.keys())

            for chapter_idx in sorted(all_chapter_indices):
                serp_data = serp_data_map.get(chapter_idx, {})
                top_k_results = search_data_map.get(chapter_idx, [])
                type_data = search_data_by_type.get(chapter_idx, {"online": [], "knowledge": []})
                final_content = content_map.get(chapter_idx, "")
                chapter_summary = summary_data_map.get(chapter_idx, "")

                chapters.append({
                    "chapter_index": chapter_idx,
                    "section_title": serp_data.get("section_title", f"章节 {chapter_idx}"),
                    "queries": [{
                        "query": serp_data.get("query", ""),
                        "research_goal": serp_data.get("research_goal", "")
                    }],
                    "top_k_results": top_k_results[:10] if top_k_results else [],
                    "top_k_online": type_data["online"][:10] if type_data["online"] else [],
                    "top_k_knowledge": type_data["knowledge"][:10] if type_data["knowledge"] else [],
                    "final_content": final_content,
                    "chapter_summary": chapter_summary if chapter_summary else "\n\n".join(top_k_results[:5])  # 后备：使用前5条搜索结果
                })

            result = {
                "report_id": report_id,
                "outline": outline,
                "chapters": chapters
            }

            logger.info(f"成功提取报告 {report_id} 的评估数据，共 {len(chapters)} 个章节")
            return result

        except Exception as e:
            logger.error(f"提取评估数据失败: {str(e)}")
            raise

    async def _evaluate_single_result(
        self,
        query: str,
        research_goal: str,
        retrieved_text: str,
        chapter_idx: int = 0,
        result_idx: int = 0
    ) -> bool:
        """
        评估单条检索结果是否相关

        Args:
            query: 查询词
            research_goal: 研究目标
            retrieved_text: 待评估的检索文本
            chapter_idx: 章节索引（用于日志）
            result_idx: 结果索引（用于日志）

        Returns:
            True 表示 Relevant，False 表示 Irrelevant
        """
        try:
            # 添加调试日志
            text_preview = retrieved_text[:200] + "..." if len(retrieved_text) > 200 else retrieved_text
            logger.info(f"评估检索结果 - 章节:{chapter_idx}, 结果:{result_idx}, 查询:{query[:50]}..., 文本:{text_preview}")
            
            messages = [
                {"role": "system", "content": EVALUATION_SYSTEM_PROMPT},
                {"role": "user", "content": EVALUATION_USER_PROMPT.format(
                    query=query,
                    research_goal=research_goal,
                    retrieved_text=retrieved_text
                )}
            ]

            response = await self._get_llm_response(messages)
            response_clean = response.strip()
            response_lower = response_clean.lower()

            # 详细日志记录 LLM 响应
            logger.info(f"LLM 响应 - 章节:{chapter_idx}, 结果:{result_idx}, 响应:{response_clean[:150]}")

            # 更健壮的解析逻辑：检查响应是否以 Relevant/Irrelevant 开头
            # 或者在响应开头部分（200字符内）查找关键词
            response_head = response_lower[:200] if len(response_lower) > 200 else response_lower
            
            # 优先检查是否包含 "relevant" 关键词
            if "relevant" in response_head:
                # 如果同时包含 "irrelevant"，需要更仔细判断
                # 常见情况："not relevant" 或 "irrelevant" 应该判定为 Irrelevant
                if "irrelevant" in response_head:
                    # 检查 "relevant" 是否在 "irrelevant" 之前（说明先提到相关再否定）
                    relevant_pos = response_head.find("relevant")
                    irrelevant_pos = response_head.find("irrelevant")
                    if irrelevant_pos < relevant_pos:
                        # "irrelevant" 出现在 "relevant" 之前，判定为 Irrelevant
                        logger.info(f"判定为 Irrelevant (优先) - 章节:{chapter_idx}, 结果:{result_idx}")
                        return False
                    # 否则可能有 "not relevant" 等情况，检查是否有否定词
                    elif "not relevant" in response_head or "is not relevant" in response_head:
                        logger.info(f"判定为 Irrelevant (否定) - 章节:{chapter_idx}, 结果:{result_idx}")
                        return False
                
                # 没有 "irrelevant"，判定为 Relevant
                logger.info(f"判定为 Relevant - 章节:{chapter_idx}, 结果:{result_idx}")
                return True
            elif "irrelevant" in response_head:
                logger.info(f"判定为 Irrelevant - 章节:{chapter_idx}, 结果:{result_idx}")
                return False
            else:
                # 无法解析，尝试其他常见格式
                if response_lower.startswith("yes") or "yes," in response_head[:50]:
                    logger.info(f"判定为 Relevant (yes) - 章节:{chapter_idx}, 结果:{result_idx}")
                    return True
                elif response_lower.startswith("no") or "no," in response_head[:50]:
                    logger.info(f"判定为 Irrelevant (no) - 章节:{chapter_idx}, 结果:{result_idx}")
                    return False
                
                logger.warning(f"无法解析评估结果: {response_clean[:100]}，默认返回 False")
                return False

        except Exception as e:
            logger.error(f"评估单条结果失败: 章节:{chapter_idx}, 结果:{result_idx}, 错误:{str(e)}")
            # 返回 None 而不是 False，这样在统计时不会被计算
            return None

    async def calculate_context_precision(self, evaluation_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        计算 Context Precision（上下文精准度）- 增强版

        计算以下指标：
        1. Basic Precision@k - 基础精准度
        2. Weighted Precision@K - 位置加权的精准度
        3. NDCG@K - 归一化折扣累积增益
        4. 分别统计 RAG 和 Web 来源的指标

        Args:
            evaluation_data: 评估数据（来自 fetch_eval_data）

        Returns:
            包含所有评估指标的完整结果
        """
        try:
            logger.info(f"开始计算增强版 Context Precision")

            chapters = evaluation_data.get("chapters", [])
            logger.info(f"总共 {len(chapters)} 个章节需要评估")

            # 累积统计
            all_chapter_details = []
            total_basic_precision = 0.0
            total_weighted_precision = 0.0
            total_ndcg = 0.0
            total_online_precision = 0.0
            total_rag_precision = 0.0
            online_chapters = 0
            rag_chapters = 0
            chapter_count = 0

            for chapter in chapters:
                chapter_idx = chapter.get("chapter_index", 0)
                top_k_results = chapter.get("top_k_results", [])
                top_k_online = chapter.get("top_k_online", [])
                top_k_knowledge = chapter.get("top_k_knowledge", [])
                queries = chapter.get("queries", [{}])
                query_info = queries[0] if queries else {}
                query = query_info.get("query", "")
                research_goal = query_info.get("research_goal", "")

                if not top_k_results:
                    logger.warning(f"章节 {chapter_idx} 跳过评估：没有 top_k_results")
                    all_chapter_details.append({
                        "chapter_index": chapter_idx,
                        "precision@k": 0.0,
                        "weighted_precision@k": 0.0,
                        "ndcg@k": 0.0,
                        "online_precision@k": None,
                        "rag_precision@k": None,
                        "skip_reason": "no_top_k_results"
                    })
                    continue

                if not query:
                    logger.warning(f"章节 {chapter_idx} 跳过评估：query 为空")
                    all_chapter_details.append({
                        "chapter_index": chapter_idx,
                        "precision@k": 0.0,
                        "weighted_precision@k": 0.0,
                        "ndcg@k": 0.0,
                        "online_precision@k": None,
                        "rag_precision@k": None,
                        "skip_reason": "empty_query"
                    })
                    continue

                logger.info(f"评估章节 {chapter_idx}，共 {len(top_k_results)} 条检索结果")

                # 1. 评估所有检索结果
                tasks = [
                    self._evaluate_single_result(query, research_goal, text, chapter_idx, idx)
                    for idx, text in enumerate(top_k_results)
                ]
                relevance_results = await asyncio.gather(*tasks, return_exceptions=True)

                # 处理异常
                valid_results = [r for r in relevance_results if isinstance(r, bool)]
                
                # 2. 计算基础 Precision@k
                relevant_count = sum(1 for r in valid_results if r)
                basic_precision = relevant_count / len(valid_results) if valid_results else 0.0

                # 3. 计算 Weighted Precision@K (位置加权)
                weighted_precision = calculate_weighted_precision(valid_results)

                # 4. 计算 NDCG@K
                ndcg = calculate_ndcg(valid_results)

                # 5. 分别评估 RAG 和 Web 结果
                online_precision = None
                rag_precision = None
                
                if top_k_online:
                    online_tasks = [
                        self._evaluate_single_result(query, research_goal, text, chapter_idx, f"online_{idx}")
                        for idx, text in enumerate(top_k_online)
                    ]
                    online_results = await asyncio.gather(*online_tasks, return_exceptions=True)
                    online_valid = [r for r in online_results if isinstance(r, bool)]
                    online_relevant = sum(1 for r in online_valid if r)
                    online_precision = online_relevant / len(online_valid) if online_valid else 0.0
                    total_online_precision += online_precision
                    online_chapters += 1
                    logger.info(f"章节 {chapter_idx} Web 评估: {online_relevant}/{len(online_valid)}, precision={online_precision:.4f}")
                
                if top_k_knowledge:
                    rag_tasks = [
                        self._evaluate_single_result(query, research_goal, text, chapter_idx, f"rag_{idx}")
                        for idx, text in enumerate(top_k_knowledge)
                    ]
                    rag_results = await asyncio.gather(*rag_tasks, return_exceptions=True)
                    rag_valid = [r for r in rag_results if isinstance(r, bool)]
                    rag_relevant = sum(1 for r in rag_valid if r)
                    rag_precision = rag_relevant / len(rag_valid) if rag_valid else 0.0
                    total_rag_precision += rag_precision
                    rag_chapters += 1
                    logger.info(f"章节 {chapter_idx} RAG 评估: {rag_relevant}/{len(rag_valid)}, precision={rag_precision:.4f}")

                logger.info(f"章节 {chapter_idx} 评估完成: basic={basic_precision:.4f}, weighted={weighted_precision:.4f}, ndcg={ndcg:.4f}")

                all_chapter_details.append({
                    "chapter_index": chapter_idx,
                    "precision@k": round(basic_precision, 4),
                    "weighted_precision@k": round(weighted_precision, 4),
                    "ndcg@k": round(ndcg, 4),
                    "online_precision@k": round(online_precision, 4) if online_precision is not None else None,
                    "rag_precision@k": round(rag_precision, 4) if rag_precision is not None else None,
                    "relevant_count": relevant_count,
                    "total_count": len(top_k_results)
                })

                total_basic_precision += basic_precision
                total_weighted_precision += weighted_precision
                total_ndcg += ndcg
                chapter_count += 1

            # 计算平均指标
            avg_basic = total_basic_precision / chapter_count if chapter_count > 0 else 0.0
            avg_weighted = total_weighted_precision / chapter_count if chapter_count > 0 else 0.0
            avg_ndcg = total_ndcg / chapter_count if chapter_count > 0 else 0.0
            avg_online = total_online_precision / online_chapters if online_chapters > 0 else None
            avg_rag = total_rag_precision / rag_chapters if rag_chapters > 0 else None

            result = {
                "context_precision": round(avg_basic, 4),
                "weighted_precision@k": round(avg_weighted, 4),
                "ndcg@k": round(avg_ndcg, 4),
                "online_precision@k": round(avg_online, 4) if avg_online is not None else None,
                "rag_precision@k": round(avg_rag, 4) if avg_rag is not None else None,
                "chapter_details": all_chapter_details,
                "stats": {
                    "total_chapters": chapter_count,
                    "online_chapters": online_chapters,
                    "rag_chapters": rag_chapters
                }
            }

            logger.info(f"Context Precision 计算完成: basic={result['context_precision']}, weighted={result['weighted_precision@k']}, ndcg={result['ndcg@k']}")
            if avg_online is not None:
                logger.info(f"Web 精确度: {result['online_precision@k']}, RAG 精确度: {result['rag_precision@k']}")

            return result

        except Exception as e:
            logger.error(f"计算增强版 Context Precision 失败: {str(e)}")
            raise

    async def _evaluate_content_usage(
        self,
        query: str,
        research_goal: str,
        retrieved_text: str,
        final_content: str,
        chapter_idx: int = 0
    ) -> bool:
        """
        评估章节内容是否使用了检索结果（端到端 RAG 评估）

        Args:
            query: 查询词
            research_goal: 研究目标
            retrieved_text: 检索文本
            final_content: 章节最终内容
            chapter_idx: 章节索引

        Returns:
            True 表示使用了，False 表示未使用
        """
        try:
            messages = [
                {"role": "system", "content": E2E_EVALUATION_SYSTEM_PROMPT},
                {"role": "user", "content": E2E_EVALUATION_USER_PROMPT.format(
                    query=query,
                    research_goal=research_goal,
                    retrieved_text=retrieved_text[:2000],  # 限制长度
                    final_content=final_content[:3000]  # 限制长度
                )}
            ]

            response = await self._get_llm_response(messages)
            response_clean = response.strip().lower()
            response_head = response_clean[:100]

            logger.info(f"端到端评估 - 章节:{chapter_idx}, 响应:{response_clean[:50]}")

            if "used" in response_head and "not used" not in response_head:
                return True
            elif "not used" in response_head:
                return False
            else:
                logger.warning(f"无法解析端到端评估结果: {response_clean[:100]}")
                return False

        except Exception as e:
            logger.error(f"端到端评估失败: 章节:{chapter_idx}, 错误:{str(e)}")
            return False

    async def calculate_e2e_rag_precision(self, evaluation_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        计算端到端 RAG 精确度
        评估章节内容是否真正使用了检索到的知识（通过摘要评估）

        评估逻辑：
        - 检查 chapter_summary（章节摘要）是否有内容
        - 评估 final_content（章节内容）是否使用了 chapter_summary 中的信息

        Args:
            evaluation_data: 评估数据

        Returns:
            端到端 RAG 评估结果
        """
        try:
            logger.info("开始计算端到端 RAG 精确度（基于摘要）")

            chapters = evaluation_data.get("chapters", [])
            chapter_details = []
            total_used = 0
            total_results = 0
            chapter_count = 0

            for chapter in chapters:
                chapter_idx = chapter.get("chapter_index", 0)
                chapter_summary = chapter.get("chapter_summary", "")
                final_content = chapter.get("final_content", "")
                queries = chapter.get("queries", [{}])
                query_info = queries[0] if queries else {}
                query = query_info.get("query", "")
                research_goal = query_info.get("research_goal", "")

                # 优先使用 summary 进行评估
                if not chapter_summary:
                    logger.warning(f"章节 {chapter_idx} 跳过端到端评估：无章节摘要")
                    chapter_details.append({
                        "chapter_index": chapter_idx,
                        "e2e_rag_precision": 0.0,
                        "used": None,
                        "skip_reason": "no_summary"
                    })
                    continue
                
                if not final_content:
                    logger.warning(f"章节 {chapter_idx} 跳过端到端评估：无章节内容")
                    chapter_details.append({
                        "chapter_index": chapter_idx,
                        "e2e_rag_precision": 0.0,
                        "used": None,
                        "skip_reason": "no_content"
                    })
                    continue

                logger.info(f"端到端评估章节 {chapter_idx}，摘要长度={len(chapter_summary)}，内容长度={len(final_content)}")

                # 使用摘要评估章节是否使用了知识
                is_used = await self._evaluate_content_usage(
                    query, research_goal, chapter_summary, final_content, chapter_idx
                )

                used_count = 1 if is_used else 0
                total_used += used_count
                total_results += 1

                chapter_details.append({
                    "chapter_index": chapter_idx,
                    "e2e_rag_precision": round(used_count / 1, 4),
                    "used": is_used,
                    "summary_length": len(chapter_summary)
                })

                chapter_count += 1

            e2e_precision = total_used / total_results if total_results > 0 else 0.0

            result = {
                "e2e_rag_precision": round(e2e_precision, 4),
                "used_count": total_used,
                "total_chapters": chapter_count,
                "chapter_details": chapter_details,
                "debug_info": {
                    "chapters_with_summary": sum(1 for c in chapters if c.get("chapter_summary")),
                    "chapters_with_content": sum(1 for c in chapters if c.get("final_content"))
                }
            }

            logger.info(f"端到端 RAG 精确度计算完成: {result['e2e_rag_precision']}, 使用了={total_used}/{chapter_count}")
            logger.info(f"调试信息: 有摘要的章节={result['debug_info']['chapters_with_summary']}, 有内容的章节={result['debug_info']['chapters_with_content']}")
            return result

        except Exception as e:
            logger.error(f"计算端到端 RAG 精确度失败: {str(e)}")
            raise

    async def evaluate_content_quality(
        self,
        report_text: str,
        outline: str
    ) -> Dict[str, Any]:
        """
        评估报告内容质量与主题契合度（G-Eval）

        Args:
            report_text: 报告正文
            outline: 原始大纲

        Returns:
            包含评分和推理过程的评估结果
        """
        try:
            logger.info("开始 G-Eval 内容质量评估")

            # 构建 G-Eval 提示词
            messages = [
                {"role": "system", "content": GEVAL_SYSTEM_PROMPT},
                {"role": "user", "content": GEVAL_USER_PROMPT.format(
                    outline=outline,
                    report_text=report_text
                )}
            ]

            # 调用 LLM
            response = await self._get_llm_response(messages)

            # 提取推理过程
            reasoning_pattern = r'\*\*评估推理过程：\*\*(.*?)\*\*最终评分：\*\*'
            reasoning_match = re.search(reasoning_pattern, response, re.DOTALL)

            if reasoning_match:
                reasoning_process = reasoning_match.group(1).strip()
            else:
                reasoning_process = "无法提取推理过程"
                logger.warning(f"无法解析 G-Eval 响应: {response}")

            # 提取评分 [1-5]
            score_pattern = r'\[([1-5])\]'
            score_match = re.search(score_pattern, response)

            if score_match:
                content_quality_score = int(score_match.group(1))
            else:
                # 尝试其他格式
                fallback_pattern = r'\*\*最终评分：\*\*\s*([1-5])'
                fallback_match = re.search(fallback_pattern, response)
                if fallback_match:
                    content_quality_score = int(fallback_match.group(1))
                else:
                    content_quality_score = 3  # 默认中等评分
                    logger.warning(f"无法解析评分，使用默认值 3，响应: {response}")

            result = {
                "content_quality_score": content_quality_score,
                "reasoning_process": reasoning_process
            }

            logger.info(f"G-Eval 评估完成，评分: {content_quality_score}")
            return result

        except Exception as e:
            logger.error(f"G-Eval 评估失败: {str(e)}")
            raise

    async def persist_evaluation_results(
        self,
        report_id: str,
        eval_results: Dict[str, Any]
    ) -> bool:
        """
        将评估结果写回 reports 集合

        Args:
            report_id: 报告ID
            eval_results: 评估结果

        Returns:
            是否成功
        """
        try:
            logger.info(f"开始将评估结果写入报告 {report_id}")

            # 构建评估文档（包含所有新指标）
            evaluation_doc = {
                "evaluated_at": eval_results.get("evaluated_at", datetime.now().isoformat()),
                
                # 检索精准度指标
                "context_precision": eval_results.get("context_precision", 0.0),
                "weighted_precision@k": eval_results.get("weighted_precision@k", 0.0),
                "ndcg@k": eval_results.get("ndcg@k", 0.0),
                "online_precision@k": eval_results.get("online_precision@k"),
                "rag_precision@k": eval_results.get("rag_precision@k"),
                
                # 端到端 RAG 指标
                "e2e_rag_precision": eval_results.get("e2e_rag_precision", 0.0),
                
                # 内容质量指标
                "content_quality_score": eval_results.get("content_quality_score", 0),
                "reasoning_process": eval_results.get("reasoning_process", ""),
                
                # 章节详情
                "chapter_details": eval_results.get("chapter_details", []),
                "e2e_chapter_details": eval_results.get("e2e_chapter_details", []),
                
                # 统计信息
                "stats": eval_results.get("stats", {}),
                "total_chapters": eval_results.get("total_chapters", 0)
            }

            # 使用 $set 更新 reports 集合
            result = mongo_db["reports"].update_one(
                {"_id": ObjectId(report_id)},
                {
                    "$set": {
                        "evaluations": evaluation_doc,
                        "updated_at": datetime.now()
                    }
                }
            )

            if result.modified_count > 0:
                logger.info(f"评估结果成功写入报告 {report_id}")
                return True
            else:
                logger.warning(f"未更新报告 {report_id}，可能报告不存在")
                return False

        except Exception as e:
            logger.error(f"写入评估结果失败: {str(e)}")
            raise

    async def run_evaluation(self, report_id: str) -> Dict[str, Any]:
        """
        执行完整评估流程

        计算以下指标：
        1. Context Precision (基础精准度)
        2. Weighted Precision@K (位置加权精准度)
        3. NDCG@K (归一化折扣累积增益)
        4. Online Precision (Web 搜索精准度)
        5. RAG Precision (知识库精准度)
        6. E2E RAG Precision (端到端 RAG 精确度)
        7. Content Quality Score (内容质量评分)

        Args:
            report_id: 报告ID

        Returns:
            完整评估报告
        """
        try:
            logger.info(f"开始对报告 {report_id} 执行完整评估")

            start_time = datetime.now()

            # 1. 提取评估数据
            eval_data = await self.fetch_eval_data(report_id)

            # 2. 计算增强版 Context Precision（包含所有精准度指标）
            precision_result = await self.calculate_context_precision(eval_data)

            # 3. 计算端到端 RAG 精确度
            e2e_result = await self.calculate_e2e_rag_precision(eval_data)

            # 4. 评估内容质量（G-Eval）
            all_chapter_content = "\n\n".join([
                chapter.get("final_content", "")
                for chapter in eval_data.get("chapters", [])
            ])
            
            logger.info(f"评估数据提取完成: outline长度={len(eval_data.get('outline', ''))}, 内容总长度={len(all_chapter_content)}, 章节数={len(eval_data.get('chapters', []))}")
            
            # 检查是否有内容可供评估
            if not all_chapter_content.strip():
                logger.error(f"报告内容为空，outline长度={len(eval_data.get('outline', ''))}")
                for i, chapter in enumerate(eval_data.get("chapters", [])):
                    logger.error(f"章节 {i}: final_content长度={len(chapter.get('final_content', ''))}")

            quality_result = await self.evaluate_content_quality(
                report_text=all_chapter_content,
                outline=eval_data.get("outline", "")
            )

            # 5. 构建完整评估结果（包含所有新指标）
            eval_results = {
                "report_id": report_id,
                "evaluated_at": datetime.now().isoformat(),
                "total_chapters": len(eval_data.get("chapters", [])),
                
                # 检索精准度指标
                "context_precision": precision_result.get("context_precision", 0.0),
                "weighted_precision@k": precision_result.get("weighted_precision@k", 0.0),
                "ndcg@k": precision_result.get("ndcg@k", 0.0),
                "online_precision@k": precision_result.get("online_precision@k"),
                "rag_precision@k": precision_result.get("rag_precision@k"),
                
                # 端到端 RAG 指标
                "e2e_rag_precision": e2e_result.get("e2e_rag_precision", 0.0),
                
                # 内容质量指标
                "content_quality_score": quality_result.get("content_quality_score", 0),
                "reasoning_process": quality_result.get("reasoning_process", ""),
                
                # 章节详情
                "chapter_details": precision_result.get("chapter_details", []),
                "e2e_chapter_details": e2e_result.get("chapter_details", []),
                
                # 统计信息
                "stats": precision_result.get("stats", {})
            }

            # 6. 回写评估结果
            await self.persist_evaluation_results(report_id, eval_results)

            end_time = datetime.now()
            execution_time = (end_time - start_time).total_seconds()

            eval_results["execution_time_seconds"] = execution_time

            logger.info(f"报告 {report_id} 评估完成，耗时 {execution_time:.2f} 秒")
            logger.info(f"指标汇总: context_precision={eval_results['context_precision']}, "
                       f"weighted={eval_results['weighted_precision@k']}, "
                       f"ndcg={eval_results['ndcg@k']}, "
                       f"e2e_rag={eval_results['e2e_rag_precision']}")
            
            return eval_results

        except Exception as e:
            logger.error(f"执行评估失败: {str(e)}")
            raise


# 全局实例
report_evaluation_service = ReportEvaluationService()
