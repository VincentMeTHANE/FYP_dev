"""
Basic API module
"""

from fastapi import APIRouter
from services.mcp_client_service import mcp_client_service

router = APIRouter()

@router.get("/")
async def root():
    """Root path"""
    return {
        "message": "Deep Research Python - LangChain + MCP Version",
        "version": "2.0.0",
        "features": [
            "LangChain ReAct Agent",
            "Auto Tool Selection",
            "URL-configured MCP Server",
            "Streaming Response Support"
        ]
    }

@router.get("/health")
async def health_check():
    """health check"""
    try:
        await mcp_client_service.initialize()
        tools = await mcp_client_service.get_tools()
        tools_count = len(tools) if tools else 0
    except Exception:
        tools_count = 0
        
    return {
        "status": "healthy",
        "service": "deep-research-python",
        "version": "2.0.0",
        "database": "connected",
        "mcp_tools_count": tools_count
    }