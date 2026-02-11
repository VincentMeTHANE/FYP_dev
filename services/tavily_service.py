import httpx
import json
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from models.models import TavilySearchRequest, TavilySearchResponse
from utils.api_key_manager import api_key_manager
from config import settings
import logging
import time

logger = logging.getLogger(__name__)


class TavilyService:
    """Tavily搜索服务"""
    
    def __init__(self):
        self.base_url = settings.TAVILY_BASE_URL
        self.timeout = 30.0
    
    async def search(self, request: TavilySearchRequest, db: Optional[Session] = None) -> TavilySearchResponse:
        """
        执行Tavily搜索
        
        Args:
            request: 搜索请求
            db: 数据库会话（可选，如果为None则从配置获取API Key）
            
        Returns:
            TavilySearchResponse: 搜索结果
        """
        start_time = time.time()
        
        try:
            # 获取可用的API Key
            key_info = api_key_manager.get_available_key()
            if not key_info:
                # 如果没有可用的数据库API Key，尝试从配置中获取（临时方案）
                api_key = getattr(settings, 'TAVILY_API_KEY', None)
                if not api_key:
                    raise ValueError("没有可用的Tavily API Key")
                logger.warning("使用配置文件中的API Key，建议在数据库中添加API Key")
            else:
                api_key = key_info.api_key
            
            # 准备搜索请求
            search_data = {
                "api_key": api_key,
                "query": request.query,
                "search_depth": request.search_depth,
                "include_answer": request.include_answer,
                "include_raw_content": request.include_raw_content,
                "max_results": request.max_results,
                "include_images": request.include_images,
                "include_image_descriptions": request.include_image_descriptions
            }
            
            # 添加可选参数
            if request.include_domains:
                search_data["include_domains"] = request.include_domains
            if request.exclude_domains:
                search_data["exclude_domains"] = request.exclude_domains
            
            logger.info(f"使用API Key {api_key[:10] if api_key else 'None'}... 执行Tavily搜索: {request.query}")
            
            # 发送搜索请求
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/search",
                    headers={"Content-Type": "application/json"},
                    json=search_data
                )
                
                response_time = time.time() - start_time
                
                if response.status_code != 200:
                    error_msg = f"Tavily API调用失败: {response.status_code} - {response.text}"
                    logger.error(error_msg)
                    # 这里可以考虑回滚key的使用计数，但为了简化，暂时不实现
                    raise ValueError(error_msg)
                
                result = response.json()
                
                # 构造响应
                tavily_response = TavilySearchResponse(
                    answer=result.get("answer"),
                    query=request.query,
                    response_time=response_time,
                    images=result.get("images", []),
                    results=result.get("results", []),
                    follow_up_questions=result.get("follow_up_questions", [])
                )
                
                logger.info(f"Tavily搜索完成，耗时: {response_time:.2f}秒，结果数: {len(tavily_response.results)}")
                
                return tavily_response
                
        except httpx.TimeoutException:
            error_msg = f"Tavily API调用超时（>{self.timeout}秒）"
            logger.error(error_msg)
            raise ValueError(error_msg)
        except Exception as e:
            error_msg = f"Tavily搜索失败: {str(e)}"
            logger.error(error_msg)
            raise ValueError(error_msg)
    
    async def batch_search(self, requests: list[TavilySearchRequest], db: Session) -> list[TavilySearchResponse]:
        """
        批量搜索
        
        Args:
            requests: 搜索请求列表
            db: 数据库会话
            
        Returns:
            list[TavilySearchResponse]: 搜索结果列表
        """
        results = []
        
        for request in requests:
            try:
                result = await self.search(request, db)
                results.append(result)
            except Exception as e:
                logger.error(f"批量搜索中的单个请求失败: {e}")
                # 创建错误响应
                error_response = TavilySearchResponse(
                    answer=None,
                    query=request.query,
                    response_time=0.0,
                    images=[],
                    results=[{"error": str(e)}],
                    follow_up_questions=[]
                )
                results.append(error_response)
        
        return results
    
    def validate_search_request(self, request: TavilySearchRequest) -> Optional[str]:
        """
        验证搜索请求参数
        
        Args:
            request: 搜索请求
            
        Returns:
            Optional[str]: 验证错误信息，如果验证通过返回None
        """
        if not request.query or not request.query.strip():
            return "搜索查询不能为空"
        
        if request.max_results and (request.max_results < 1 or request.max_results > 20):
            return "max_results必须在1-20之间"
        
        if request.search_depth and request.search_depth not in ["basic", "advanced"]:
            return "search_depth必须是'basic'或'advanced'"
        
        return None


# 全局实例
tavily_service = TavilyService()