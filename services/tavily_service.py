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
    """Tavily search service"""

    def __init__(self):
        self.base_url = settings.TAVILY_BASE_URL
        self.timeout = 30.0

    async def search(self, request: TavilySearchRequest, db: Optional[Session] = None) -> TavilySearchResponse:
        """
        Execute Tavily search

        Args:
            request: Search request
            db: Database session (optional)

        Returns:
            TavilySearchResponse: Search results
        """
        start_time = time.time()

        try:
            api_key = getattr(settings, 'TAVILY_API_KEY', None)
            if not api_key:
                raise ValueError("Tavily API Key not configured, please check config.py")

            if api_key == "tvly-YOUR_API_KEY_HERE":
                logger.warning("Default Tavily API Key placeholder detected, please update TAVILY_API_KEY in config.py")

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

            if request.include_domains:
                search_data["include_domains"] = request.include_domains
            if request.exclude_domains:
                search_data["exclude_domains"] = request.exclude_domains

            logger.info(f"Executing Tavily search with API Key {api_key[:10] if api_key else 'None'}...: {request.query}")

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/search",
                    headers={"Content-Type": "application/json"},
                    json=search_data
                )

                response_time = time.time() - start_time

                if response.status_code != 200:
                    error_msg = f"Tavily API call failed: {response.status_code} - {response.text}"
                    logger.error(error_msg)
                    raise ValueError(error_msg)

                result = response.json()

                tavily_response = TavilySearchResponse(
                    answer=result.get("answer"),
                    query=request.query,
                    response_time=response_time,
                    images=result.get("images", []),
                    results=result.get("results", []),
                    follow_up_questions=result.get("follow_up_questions", [])
                )

                logger.info(f"Tavily search completed, time: {response_time:.2f}s, results: {len(tavily_response.results)}")

                return tavily_response

        except httpx.TimeoutException:
            error_msg = f"Tavily API call timeout (>{self.timeout}s)"
            logger.error(error_msg)
            raise ValueError(error_msg)
        except Exception as e:
            error_msg = f"Tavily search failed: {str(e)}"
            logger.error(error_msg)
            raise ValueError(error_msg)

    async def batch_search(self, requests: list[TavilySearchRequest], db: Session) -> list[TavilySearchResponse]:
        """
        Batch search

        Args:
            requests: List of search requests
            db: Database session

        Returns:
            list[TavilySearchResponse]: List of search results
        """
        results = []

        for request in requests:
            try:
                result = await self.search(request, db)
                results.append(result)
            except Exception as e:
                logger.error(f"Single request failed in batch search: {e}")
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
        Validate search request parameters

        Args:
            request: Search request

        Returns:
            Optional[str]: Validation error message, or None if valid
        """
        if not request.query or not request.query.strip():
            return "Search query cannot be empty"

        if request.max_results and (request.max_results < 1 or request.max_results > 20):
            return "max_results must be between 1 and 20"

        if request.search_depth and request.search_depth not in ["basic", "advanced"]:
            return "search_depth must be 'basic' or 'advanced'"

        return None


tavily_service = TavilyService()