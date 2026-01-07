"""
简化的MCP客户端服务 - 仅支持URL配置
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class MCPClientService:
    """简化的MCP客户端服务 - 仅支持LangChain集成和URL配置"""
    
    def __init__(self):
        self._langchain_client = None
        self._tools_cache = None
        self._initialized = False
        
    async def initialize(self):
        """初始化MCP客户端"""
        if self._initialized:
            return
            
        try:
            # 尝试导入LangChain MCP适配器
            from langchain_mcp_adapters.client import MultiServerMCPClient
            
            # 固定配置 - 只支持URL方式
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
            logger.info("MCP客户端初始化成功")
            
        except ImportError:
            logger.warning("langchain-mcp-adapters未安装，MCP功能不可用")
        except Exception as e:
            logger.error(f"MCP客户端初始化失败: {e}")
    
    async def get_tools(self):
        """获取可用工具列表"""
        if not self._initialized:
            await self.initialize()
            
        if not self._langchain_client:
            return []
            
        try:
            if self._tools_cache is None:
                self._tools_cache = await self._langchain_client.get_tools()
                logger.info(f"获取到 {len(self._tools_cache)} 个MCP工具")
            return self._tools_cache
        except Exception as e:
            logger.error(f"获取MCP工具失败: {e}")
            return []
    
    async def create_react_agent(self, llm):
        """创建ReAct智能体"""
        try:
            from langgraph.prebuilt import create_react_agent
            
            tools = await self.get_tools()
            if not tools:
                logger.warning("没有可用的工具，无法创建ReAct智能体")
                return None
                
            agent = create_react_agent(llm, tools)
            logger.info("ReAct智能体创建成功")
            return agent
            
        except ImportError:
            logger.error("langgraph未安装，无法创建ReAct智能体")
            return None
        except Exception as e:
            logger.error(f"创建ReAct智能体失败: {e}")
            return None
    
    async def close(self):
        """清理资源"""
        if self._langchain_client:
            try:
                await self._langchain_client.close()
            except:
                pass
        self._langchain_client = None
        self._tools_cache = None
        self._initialized = False

# 全局MCP客户端服务实例
mcp_client_service = MCPClientService()