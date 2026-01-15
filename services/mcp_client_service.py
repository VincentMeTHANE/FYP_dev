"""
MCP client service
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class MCPClientService:
    """LangChain MCP client service"""
    
    def __init__(self):
        self._langchain_client = None
        self._tools_cache = None
        self._initialized = False
        
    async def initialize(self):
        """Initialize the MCP client"""
        if self._initialized:
            return
            
        try:
            # try to import the LangChain MCP adapter
            from langchain_mcp_adapters.client import MultiServerMCPClient
            
            # fixed configuration - only support URL
            langchain_config = {
                "mcp_server_chart": {
                    "url": "http://localhost:1122/mcp",
                    "transport": "streamable_http"
                }
                # "mcp_server_google_search": {
                #     "url": "http://localhost:1123/mcp",
                #     "transport": "streamable_http"
                # }
            }
            
            self._langchain_client = MultiServerMCPClient(langchain_config)
            self._initialized = True
            logger.info("MCP client initialized successfully")
            
        except ImportError:
            logger.warning("langchain-mcp-adapters is not installed, MCP functionality is not available")
        except Exception as e:
            logger.error(f"MCP client initialization failed: {e}")
    
    async def get_tools(self):
        """Get the available tool list"""
        if not self._initialized:
            await self.initialize()
            
        if not self._langchain_client:
            return []
            
        try:
            if self._tools_cache is None:
                self._tools_cache = await self._langchain_client.get_tools()
                logger.info(f"Got {len(self._tools_cache)} MCP tools")
            return self._tools_cache
        except Exception as e:
            logger.error(f"Failed to get MCP tools: {e}")
            return []
    
    async def create_react_agent(self, llm):
        """Create a ReAct agent"""
        try:
            from langgraph.prebuilt import create_react_agent
            
            tools = await self.get_tools()
            if not tools:
                logger.warning("No available tools, cannot create a ReAct agent")
                return None
                
            agent = create_react_agent(llm, tools)
            logger.info("ReAct agent created successfully")
            return agent
            
        except ImportError:
            logger.error("langgraph is not installed, cannot create a ReAct agent")
            return None
        except Exception as e:
            logger.error(f"Failed to create a ReAct agent: {e}")
            return None
    
    async def close(self):
        """Clean up the resources"""
        if self._langchain_client:
            try:
                await self._langchain_client.close()
            except:
                pass
        self._langchain_client = None
        self._tools_cache = None
        self._initialized = False

# Global MCP client service instance
mcp_client_service = MCPClientService()