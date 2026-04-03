"""
搜索增强服务模块 V2
提供 Query Expansion、Re-ranking、RRF 融合等功能来提高搜索相关性

优化项：
1. 优化的 Re-ranking Prompt - 更严格的评分标准和推理过程
2. 查询意图识别 - 根据查询类型针对性搜索
3. 相关性阈值过滤 - 过滤低相关结果
"""

import asyncio
import logging
import re
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass, field

from config import settings

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """搜索结果数据结构"""
    title: str
    url: str
    content: str
    raw_content: str = ""
    score: float = 0.0
    source: str = "online"  # online 或 knowledge
    relevance_score: float = 0.0  # LLM 评估的相关性分数


@dataclass
class ExpandedQuery:
    """扩展后的查询"""
    original_query: str
    expanded_queries: List[str]
    reasoning: str = ""


@dataclass
class QueryIntent:
    """查询意图分类"""
    query: str
    intent_type: str  # factual / conceptual / procedural / comparative / exploratory
    keywords: List[str] = field(default_factory=list)
    reasoning: str = ""


class SearchEnhancementService:
    """搜索增强服务 V2"""

    def __init__(self):
        self._llm_initialized = False
        # Query Expansion 的查询数量
        self.expansion_count = 3
        # 相关性阈值（低于此值的过滤掉）
        self.relevance_threshold = 0.3

    async def _get_llm_response(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3
    ) -> str:
        """调用 LLM 获取响应"""
        try:
            import httpx

            _eval_entity = {
                "name": settings.LLM_MODEL,
                "url": "https://dashscope.aliyuncs.com/compatible-mode",
                "api_key": settings.LLM_API_KEY
            }
            llm_entity = settings.LLM_ENTITY.get("search_summary", _eval_entity)

            payload = {
                "model": llm_entity["name"],
                "messages": messages,
                "temperature": temperature,
                "stream": False
            }

            async with httpx.AsyncClient(timeout=90.0) as client:
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

    # ============ 1. 查询意图识别 ============

    async def classify_intent(self, query: str, research_goal: str = "") -> QueryIntent:
        """
        查询意图识别 - 分类查询类型并生成针对性关键词

        意图类型：
        - factual: 事实性问题（谁、什么、什么时候、哪里）
        - conceptual: 概念性问题（是什么、为什么、原理）
        - procedural: 程序性问题（怎么做、如何）
        - comparative: 对比问题（A vs B、比较、区别）
        - exploratory: 探索性问题（趋势、最新、发展）

        Args:
            query: 原始查询
            research_goal: 研究目标

        Returns:
            QueryIntent: 查询意图对象
        """
        try:
            logger.info(f"开始查询意图识别: {query[:50]}...")

            context = f"研究目标：{research_goal}" if research_goal else ""

            intent_prompt = f"""分析以下查询的意图类型，并提取关键搜索词。

{context}

查询：{query}

任务：
1. 判断意图类型（factual/conceptual/procedural/comparative/exploratory）
2. 提取 3-5 个关键搜索词，用于提高搜索精确度

意图定义：
- factual: 事实性问题（谁、什么、什么时候、哪里、数字）
- conceptual: 概念性问题（是什么、为什么、原理、定义）
- procedural: 程序性问题（怎么做、如何、步骤、方法）
- comparative: 对比问题（A vs B、比较、区别、优缺点）
- exploratory: 探索性问题（趋势、最新、发展、未来）

请按以下格式输出：
意图类型：[类型]
关键搜索词：[词1], [词2], [词3]

只输出这两行，不要其他内容。"""

            messages = [
                {"role": "system", "content": "你是一个专业的查询意图分析专家。"},
                {"role": "user", "content": intent_prompt}
            ]

            response = await self._get_llm_response(messages, temperature=0.2)

            # 解析响应
            intent_type = "exploratory"  # 默认
            keywords = []

            for line in response.strip().split('\n'):
                line = line.strip()
                if line.startswith('意图类型：') or line.startswith('意图类型:'):
                    intent_type = line.split('：')[-1].split(':')[-1].strip().lower()
                elif line.startswith('关键搜索词：') or line.startswith('关键搜索词:'):
                    kw_str = line.split('：')[-1].split(':')[-1].strip()
                    keywords = [k.strip() for k in kw_str.split(',') if k.strip()]

            # 验证意图类型
            valid_intents = ["factual", "conceptual", "procedural", "comparative", "exploratory"]
            if intent_type not in valid_intents:
                intent_type = "exploratory"

            logger.info(f"意图识别完成: {intent_type}, 关键词: {keywords}")

            return QueryIntent(
                query=query,
                intent_type=intent_type,
                keywords=keywords,
                reasoning=response
            )

        except Exception as e:
            logger.error(f"意图识别失败: {str(e)}")
            return QueryIntent(query=query, intent_type="exploratory", keywords=[])

    # ============ 2. Query Expansion（增强版）============

    async def expand_query(
        self,
        original_query: str,
        research_goal: str = "",
        intent: Optional[QueryIntent] = None
    ) -> ExpandedQuery:
        """
        Query Expansion - 将单一查询扩展为多个子查询（增强版）

        根据意图类型调整扩展策略：
        - factual: 扩展为多个具体事实查询
        - conceptual: 扩展为原理和定义查询
        - procedural: 扩展为步骤和方法查询
        - comparative: 扩展为对比和多角度查询
        - exploratory: 扩展为广泛探索查询

        Args:
            original_query: 原始查询
            research_goal: 研究目标
            intent: 查询意图（可选）

        Returns:
            ExpandedQuery: 包含原始查询和扩展查询的对象
        """
        try:
            logger.info(f"开始 Query Expansion: {original_query[:50]}...")

            context = f"研究目标：{research_goal}" if research_goal else ""

            # 根据意图类型调整 prompt
            intent_str = f"查询意图：{intent.intent_type}" if intent else ""
            keywords_str = f"关键词：{', '.join(intent.keywords)}" if intent and intent.keywords else ""

            expansion_prompt = f"""你是一个专业的搜索查询优化专家。请将以下查询扩展为 {self.expansion_count} 个不同的子查询。

{context}
{intent_str}
{keywords_str}

原始查询：{original_query}

扩展策略要求：
1. 根据意图类型调整扩展方向
2. 每个子查询应该从不同角度探索原始查询的主题
3. 子查询可以是：具体问题、背景查询、对比查询、深入研究等
4. 保持子查询简洁（15-30字）
5. 避免子查询之间重复

请按以下格式输出：
1. [第一个子查询]
2. [第二个子查询]
3. [第三个子查询]

只输出子查询，不要其他解释。"""

            messages = [
                {"role": "system", "content": "你是一个专业的搜索查询优化专家。"},
                {"role": "user", "content": expansion_prompt}
            ]

            response = await self._get_llm_response(messages, temperature=0.3)

            # 解析响应，提取子查询
            expanded_queries = []
            lines = response.strip().split('\n')
            for line in lines:
                line = line.strip()
                if line and line[0].isdigit():
                    query = line.split('.', 1)[-1].strip()
                    if query:
                        expanded_queries.append(query)

            # 如果解析失败，使用默认策略
            if len(expanded_queries) < 2:
                expanded_queries = [
                    original_query,
                    f"{original_query} 原理",
                    f"{original_query} 应用"
                ][:self.expansion_count]

            logger.info(f"Query Expansion 完成，生成 {len(expanded_queries)} 个子查询")

            return ExpandedQuery(
                original_query=original_query,
                expanded_queries=expanded_queries,
                reasoning=response
            )

        except Exception as e:
            logger.error(f"Query Expansion 失败: {str(e)}")
            return ExpandedQuery(
                original_query=original_query,
                expanded_queries=[original_query],
                reasoning=""
            )

    # ============ 3. Re-ranking（优化版）============

    async def rerank_results(
        self,
        query: str,
        results: List[SearchResult],
        top_k: int = 10,
        intent: Optional[QueryIntent] = None
    ) -> List[SearchResult]:
        """
        Re-ranking - 使用 LLM 对搜索结果重排序（优化版）

        改进：
        1. 更严格的评分标准（0-10 分）
        2. 要求输出推理过程
        3. 同时输出相关性和排序
        4. 根据意图类型调整评估重点

        Args:
            query: 查询词
            results: 搜索结果列表
            top_k: 返回前 k 个结果
            intent: 查询意图

        Returns:
            重排序后的搜索结果
        """
        try:
            if not results:
                return []

            logger.info(f"开始 Re-ranking: 查询={query[:30]}..., 结果数={len(results)}")

            # 根据意图类型调整评估重点
            intent_focus = {
                "factual": "重点评估：数据准确性、来源权威性、时效性",
                "conceptual": "重点评估：概念清晰度、解释完整性、逻辑严谨性",
                "procedural": "重点评估：步骤完整性、可操作性、实用性",
                "comparative": "重点评估：对比全面性、观点平衡性、论据充分性",
                "exploratory": "重点评估：覆盖面广度、洞察深度、启发性"
            }
            focus_text = intent_focus.get(intent.intent_type if intent else "exploratory", "") if intent else ""

            # 构建评估 prompt（优化版）
            results_text = "\n".join([
                f"[{i}] 标题: {r.title}\nURL: {r.url}\n摘要: {r.content[:150]}..."
                for i, r in enumerate(results[:15])  # 最多评估15个
            ])

            rerank_prompt = f"""你是一个专业的搜索引擎排序专家。请对以下搜索结果进行严格评估。

查询：{query}
{focus_text}

搜索结果：
{results_text}

评估要求：
1. 对每个结果给出 0-10 的相关性分数（0=完全不相关，10=完美匹配）
2. 考虑：主题匹配度、内容质量、来源权威性、时效性
3. 特别关注：内容是否直接回答查询、是否有深度

请按以下格式输出（每行一个结果）：
[序号]: [相关性分数] - [简短理由]

只输出评估结果，不要其他内容。"""

            messages = [
                {"role": "system", "content": "你是一个专业的搜索引擎排序专家。"},
                {"role": "user", "content": rerank_prompt}
            ]

            response = await self._get_llm_response(messages, temperature=0.2)

            # 解析响应，提取分数和排序
            scores = {}
            rankings = []

            for line in response.strip().split('\n'):
                line = line.strip()
                if not line:
                    continue

                # 匹配 "[0]: 8 - 理由" 格式
                match = re.match(r'\[(\d+)\]:\s*(\d+(?:\.\d+)?)', line)
                if match:
                    idx = int(match.group(1))
                    score = float(match.group(2))
                    scores[idx] = score
                    rankings.append((idx, score))

            # 按分数降序排序
            rankings.sort(key=lambda x: x[1], reverse=True)

            # 如果解析失败，使用原始顺序
            if len(rankings) < len(results) // 2:
                logger.warning(f"Re-ranking 解析失败，使用原始顺序")
                reranked = results[:top_k]
            else:
                # 根据排序重新排列结果
                reranked = []
                for idx, score in rankings:
                    if idx < len(results):
                        results[idx].relevance_score = score / 10.0  # 归一化到 0-1
                        results[idx].score = score / 10.0
                        reranked.append(results[idx])

                # 处理未评分的项目（放在最后）
                scored_indices = set(idx for idx, _ in rankings)
                for i, r in enumerate(results):
                    if i not in scored_indices:
                        r.relevance_score = 0.0
                        r.score = 0.0
                        reranked.append(r)

            logger.info(f"Re-ranking 完成，返回 {min(top_k, len(reranked))} 个结果")

            return reranked[:top_k]

        except Exception as e:
            logger.error(f"Re-ranking 失败: {str(e)}")
            return results[:top_k]

    # ============ 4. 相关性阈值过滤 ============

    def filter_by_threshold(
        self,
        results: List[SearchResult],
        threshold: float = 0.3
    ) -> List[SearchResult]:
        """
        根据相关性阈值过滤结果

        Args:
            results: 搜索结果列表
            threshold: 最低相关性阈值

        Returns:
            过滤后的结果
        """
        original_count = len(results)
        filtered = [r for r in results if r.relevance_score >= threshold]

        logger.info(f"阈值过滤: {original_count} -> {len(filtered)} (阈值={threshold})")

        return filtered

    # ============ 5. RRF 融合 ============

    def rrf_fusion(
        self,
        result_lists: List[List[SearchResult]],
        top_k: int = 10,
        rrf_k: int = 60
    ) -> List[SearchResult]:
        """
        RRF (Reciprocal Rank Fusion) - 倒数排名融合

        Args:
            result_lists: 多个搜索结果列表
            top_k: 返回前 k 个结果
            rrf_k: RRF 参数（通常 60）

        Returns:
            融合后的搜索结果
        """
        if not result_lists:
            return []

        rrf_scores = {}
        source_count = {}

        for result_list in result_lists:
            for rank, result in enumerate(result_list):
                key = result.url

                if key not in rrf_scores:
                    rrf_scores[key] = 0.0
                    source_count[key] = 0
                    rrf_scores[f"{key}_data"] = result

                rrf_scores[key] += 1.0 / (rrf_k + rank + 1)
                source_count[key] += 1

        sorted_keys = sorted(
            [k for k in rrf_scores.keys() if not k.endswith('_data')],
            key=lambda x: rrf_scores[x],
            reverse=True
        )

        fused_results = []
        for rank, key in enumerate(sorted_keys[:top_k]):
            result = rrf_scores[f"{key}_data"]
            result.score = rrf_scores[key]
            result.source = f"fused_{source_count[key]}"
            fused_results.append(result)

        logger.info(f"RRF 融合完成，输入 {len(result_lists)} 个列表，输出 {len(fused_results)} 个结果")

        return fused_results


class EnhancedSearchService:
    """
    增强搜索服务 V2 - 整合意图识别 + Query Expansion + Re-ranking + RRF + 阈值过滤
    """

    def __init__(self):
        self.enhancement = SearchEnhancementService()
        self._tavily_service = None

    @property
    def tavily_service(self):
        if self._tavily_service is None:
            from services.tavily_service import tavily_service
            self._tavily_service = tavily_service
        return self._tavily_service

    async def enhanced_search(
        self,
        query: str,
        research_goal: str = "",
        use_expansion: bool = True,
        use_rerank: bool = True,
        use_intent: bool = True,
        max_results: int = 10,
        include_images: bool = True,
        relevance_threshold: float = 0.3
    ) -> Tuple[List[SearchResult], List[Dict]]:
        """
        增强搜索 V2 - 整合所有优化

        工作流：
        1. 查询意图识别（可选）
        2. Query Expansion（可选）- 扩展查询
        3. 并行搜索 - 对每个子查询执行搜索
        4. RRF 融合 - 合并搜索结果
        5. Re-ranking（可选）- LLM 重排序
        6. 相关性阈值过滤

        Args:
            query: 原始查询
            research_goal: 研究目标
            use_expansion: 是否使用 Query Expansion
            use_rerank: 是否使用 Re-ranking
            use_intent: 是否使用意图识别
            max_results: 返回结果数量
            include_images: 是否包含图片
            relevance_threshold: 相关性阈值

        Returns:
            Tuple[List[SearchResult], List[Dict]]: (增强后的搜索结果, 图片列表)
        """
        try:
            all_results = []
            all_images = []
            intent = None

            # 0. 查询意图识别（可选）
            if use_intent:
                intent = await self.enhancement.classify_intent(query, research_goal)
                logger.info(f"查询意图: {intent.intent_type}, 关键词: {intent.keywords}")

            # 1. Query Expansion（可选）
            if use_expansion:
                expanded = await self.enhancement.expand_query(query, research_goal, intent)
                queries_to_search = expanded.expanded_queries
                logger.info(f"使用 Query Expansion，搜索 {len(queries_to_search)} 个查询")
            else:
                queries_to_search = [query]

            # 2. 并行搜索
            search_tasks = []
            for q in queries_to_search:
                search_tasks.append(self._search_single_query(q, include_images))

            search_results_list = await asyncio.gather(*search_tasks, return_exceptions=True)

            # 收集所有结果和图片
            for result in search_results_list:
                if isinstance(result, tuple) and len(result) == 2:
                    results, images = result
                    all_results.extend(results)
                    all_images.extend(images)

            # 去重（基于 URL）
            seen_urls = set()
            unique_results = []
            for r in all_results:
                if r.url not in seen_urls:
                    seen_urls.add(r.url)
                    unique_results.append(r)

            # 图片去重（基于 URL）
            seen_img_urls = set()
            unique_images = []
            for img in all_images:
                img_url = img.get("url", "")
                if img_url and img_url not in seen_img_urls:
                    seen_img_urls.add(img_url)
                    unique_images.append(img)

            logger.info(f"搜索完成，去重后 {len(unique_results)} 个结果, {len(unique_images)} 张图片")

            # 3. RRF 融合（如果有多个查询）
            if len(queries_to_search) > 1:
                grouped_results = []
                offset = 0
                for i, q in enumerate(queries_to_search):
                    if i < len(search_results_list) and isinstance(search_results_list[i], tuple):
                        count = len(search_results_list[i][0])
                    else:
                        count = 0
                    grouped_results.append(unique_results[offset:offset + count])
                    offset += count

                fused = self.enhancement.rrf_fusion(grouped_results, top_k=max_results * 3)
                unique_results = fused

            # 4. Re-ranking（可选）
            if use_rerank and len(unique_results) > 5:
                reranked = await self.enhancement.rerank_results(
                    query, unique_results, top_k=max_results * 2, intent=intent
                )

                # 5. 相关性阈值过滤
                if relevance_threshold > 0:
                    filtered = self.enhancement.filter_by_threshold(
                        reranked, threshold=relevance_threshold
                    )
                    return filtered, unique_images

                return reranked, unique_images

            # 如果不使用 rerank，直接返回（带阈值过滤）
            if relevance_threshold > 0:
                unique_results = self.enhancement.filter_by_threshold(
                    unique_results, threshold=relevance_threshold
                )

            return unique_results[:max_results], unique_images

        except Exception as e:
            logger.error(f"增强搜索失败: {str(e)}")
            raise

    async def _search_single_query(self, query: str, include_images: bool = True) -> Tuple[List[SearchResult], List]:
        """执行单个查询的搜索"""
        try:
            from models.models import TavilySearchRequest

            request = TavilySearchRequest(
                query=query,
                search_depth="advanced",
                include_answer=True,
                include_raw_content=include_images,
                max_results=10,
                include_images=include_images,
                include_image_descriptions=True
            )

            response = await self.tavily_service.search(request)

            results = []
            for r in response.results:
                results.append(SearchResult(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    content=r.get("content", ""),
                    raw_content=r.get("raw_content", ""),
                    score=r.get("score", 0.0),
                    source="online"
                ))

            images = []
            if include_images and response.images:
                for img in response.images:
                    # TavilyImageResult 是对象而非字典
                    img_url = getattr(img, 'url', '') or getattr(img, 'src', '') or ''
                    img_desc = getattr(img, 'description', '') or getattr(img, 'alt', '') or ''
                    if img_url:
                        images.append({
                            "url": img_url,
                            "description": img_desc
                        })

            return results, images

        except Exception as e:
            logger.error(f"单个查询搜索失败: {query[:30]}... - {str(e)}")
            return [], []


# 全局实例
search_enhancement_service = SearchEnhancementService()
enhanced_search_service = EnhancedSearchService()
