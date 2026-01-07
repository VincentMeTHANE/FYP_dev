"""
The main file for the backend framework. 
"""

import asyncio
import logging
import uvicorn
from fastapi import FastAPI
from contextlib import asynccontextmanager

from config import settings
from api import setup_routers
from services.mcp_client_service import mcp_client_service
from utils.logger import init_logging, get_logger
from utils.exception_handler import setup_exception_handlers

# initialize the logging service
init_logging(
    log_dir=settings.LOG_DIR,
    max_file_size=settings.LOG_MAX_FILE_SIZE,
    backup_count=settings.LOG_BACKUP_COUNT,
    console_level=settings.LOG_CONSOLE_LEVEL,
    file_level=settings.LOG_FILE_LEVEL
)

logger = get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Life span for MCP service and the logging service"""
    logger.info("Initialzing the MCP and logging service")
    
    # initialize the MCP client
    await _initialize_mcp_client()
    
    yield
    
    # clean the resources
    await mcp_client_service.close()
    logger.info("Shutting down the services")

async def _initialize_mcp_client():
    """initialize the MCP client"""
    try:
        await mcp_client_service.initialize()
        tools = await mcp_client_service.get_tools()
        tool_names = [tool.name for tool in tools] if tools else []
        logger.info(f"MCP Tool List: {tool_names}")
        
    except Exception as e:
        logger.warning(f"Failed to initialize the MCP client: {e}")

# Initialize the FastAPI app
app = FastAPI(
    title="Final Year Project by Yuxuan Shi - QAM1",
    description="",
    version="2.0.0",
    lifespan=lifespan
)

# set up the global exception handler
setup_exception_handlers(app)

# set up the API routers
setup_routers(app)

if __name__ == "__main__":
    # Run the app
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
