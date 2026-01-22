"""
LLM service, use LangChain & MCP
"""

import asyncio
import datetime
import json
import httpx
import logging
from typing import Dict, Any, List, AsyncGenerator, Optional
import re

from config import settings
from models.models import LLMRequest
from services.mcp_client_service import mcp_client_service

logger = logging.getLogger(__name__)

# System Prompt
def system_prompt():
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"""
    您是一位专业研究人员。今天是 {now}。在回应时请遵循以下指示：
    - 您可能会被要求研究超出您知识截止日期的主题，当收到新闻信息时，请假设用户提供的内容是正确的。
    - 用户是一位经验丰富的分析师，无需简化内容，应尽可能详细并确保回应准确无误。
    - 内容需高度有条理。
    - 提出我未曾想到的解决方案。
    - 积极主动并预判我的需求。
    - 将我视为所有领域的专家。
    - 错误会削弱我的信任，因此请保证内容准确且全面。
    - 提供详细的解释，我能够接受大量细节信息。
    - 重视有说服力的论证而非权威观点，信息来源无关紧要。
    - 不仅要考虑传统观点，还需纳入新技术和反向思维。
    - 您可以进行高度的推测或预测，但请为此负责。 
    - 请使用简体中文回答问题。
    - /no_think
    """

def response_language_prompt():
    return "**使用与用户语言相同的语言进行响应**"

class LLMService:
    """LLM service - use LangChain + MCP"""
    
    def __init__(self):
        self.base_url = settings.LLM_BASE_URL
        self.api_key = settings.LLM_API_KEY
        self.default_model = settings.LLM_MODEL
        # 缓存不同模型的LangChain实例和智能体
        self._langchain_cache = {}
        self._react_agent_cache = {}
        self._mcp_initialized = False

    async def _get_langchain_llm(self, model: str = None):
        """获取指定模型的LangChain LLM实例"""
        model = model or self.default_model
        
        if model not in self._langchain_cache:
            from langchain_openai import ChatOpenAI

            llm_entity = settings.LLM_ENTITY[model]

            # 创建新的LangChain LLM实例
            self._langchain_cache[model] = ChatOpenAI(
                openai_api_key=llm_entity["api_key"],
                openai_api_base=f"{llm_entity['url']}/v1",
                temperature=0.1
            )
            logger.info(f"创建模型 {model} 的LangChain实例")
        
        return self._langchain_cache[model]

    async def _get_react_agent(self, model: str = None):
        """获取指定模型的ReAct智能体"""
        model = model or self.default_model
        
        if model not in self._react_agent_cache:
            # 确保MCP客户端服务已初始化
            if not self._mcp_initialized:
                await mcp_client_service.initialize()
                self._mcp_initialized = True
            
            # 获取LangChain LLM实例
            langchain_llm = await self._get_langchain_llm(model)
            
            # 创建ReAct智能体
            react_agent = await mcp_client_service.create_react_agent(langchain_llm)
            
            if not react_agent:
                raise Exception(f"无法为模型 {model} 创建ReAct智能体，MCP功能不可用")
            
            self._react_agent_cache[model] = react_agent
            logger.info(f"创建模型 {model} 的ReAct智能体")
        
        return self._react_agent_cache[model]

    async def completion(self, message: str, use_mcp: bool = False, model: str = None):
        """非流式聊天完成"""
        request = LLMRequest(
            use_mcp=use_mcp,
            model=model or self.default_model,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt()
                },
                {
                    "role": "user",
                    "content": message
                },
                {
                    "role": "user",
                    "content": response_language_prompt()
                }
            ]
        )
        result = await self.chat_completion(request)
        return result
    # 根据参数，让大模型判断是否符合规则，
    async def check_rule(self, message: str, model: str = None):
        """根据参数，让大模型判断是否符合规则"""
        # llm_entity = settings.LLM_ENTITY[model]
        # model = model or settings.LLM_CHECK_ROLE_MODEL
        # model = model or self.default_model
        # model=llm_entity["name"] or self.default_model
        request = LLMRequest(
            use_mcp=False,
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt()
                },
                {
                    "role": "user",
                    "content": message
                }
            ]
        )
        result = await self.chat_completion(request)

        # {'id': 'chatcmpl-20250917204858788787805isey5Euk', 'model': 'gemini-2.5-pro', 'object': 'chat.completion', 'created': 1758113353, 'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': '否'}, 'finish_reason': 'stop'}], 'usage': {'prompt_tokens': 2817, 'completion_tokens': 1250, 'total_tokens': 4067, 'prompt_tokens_details': {'cached_tokens': 0, 'text_tokens': 2817, 'audio_tokens': 0, 'image_tokens': 0}, 'completion_tokens_details': {'text_tokens': 0, 'audio_tokens': 0, 'reasoning_tokens': 1249}, 'input_tokens': 0, 'output_tokens': 0, 'input_tokens_details': None}}
        return result["choices"][0]["message"]["content"]

    async def stream(self, message: str, use_mcp: bool = False, model: str = None):

        # llm_entity = settings.LLM_ENTITY[model]
        # logger.info(f"调用LLM服务，使用模型: {llm_entity['name']}")

        """流式聊天 - 返回异步生成器"""
        request = LLMRequest(
            use_mcp=use_mcp,
            model=model or self.default_model,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt()
                },
                {
                    "role": "user",
                    "content": message
                },
                {
                    "role": "user",
                    "content": response_language_prompt()
                }
            ]
        )
        # 直接返回异步生成器，而不是StreamingResponse
        async for chunk in self.chat_stream(request):
            yield chunk
    
    async def chat_completion(self, request: LLMRequest) -> Dict[str, Any]:
        """聊天完成接口"""
        model = request.model or self.default_model
        logger.info(f"聊天完成请求: use_mcp={request.use_mcp}, model={model}")
        
        if request.use_mcp:
            # 如果启用MCP，必须使用LangChain方式，失败则报错
            logger.info("使用LangChain + MCP路径")
            return await self._chat_with_langchain(request)
        else:
            # 不使用MCP的普通聊天
            logger.info("使用普通聊天路径")
            return await self._chat_without_mcp(request)

    async def _chat_with_langchain(self, request: LLMRequest) -> Dict[str, Any]:
        """使用LangChain ReAct智能体的聊天完成"""
        try:
            model = request.model or self.default_model
            
            # 获取指定模型的ReAct智能体
            react_agent = await self._get_react_agent(model)
            
            # 提取用户消息
            user_message = ""
            for msg in request.messages:
                if msg.get("role") == "user":
                    user_message = msg.get("content", "")
                    break
            
            if not user_message:
                raise ValueError("未找到用户消息")
            
            # 使用ReAct智能体处理
            from langchain.schema import HumanMessage
            
            result = await react_agent.ainvoke({
                "messages": [HumanMessage(content=user_message)]
            })
            
            # 提取响应和工具调用信息
            final_message = result["messages"][-1]
            tool_calls = []
            
            # 提取工具调用信息
            for msg in result["messages"]:
                if hasattr(msg, 'tool_calls') and msg.tool_calls:
                    for call in msg.tool_calls:
                        tool_calls.append({
                            "tool_name": call.get('name', 'unknown'),
                            "parameters": call.get('args', {}),
                            "result": "completed"
                        })
            
            # 构造兼容的响应格式
            response = {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": final_message.content if hasattr(final_message, 'content') else str(final_message),
                        "mcp_tool_calls": tool_calls
                    },
                    "finish_reason": "stop"
                }],
                "usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0
                },
                "model": model
            }
            
            logger.info(f"LangChain处理完成，调用了 {len(tool_calls)} 个工具")
            return response
            
        except Exception as e:
            logger.error(f"LangChain处理失败: {e}")
            raise

    async def _chat_without_mcp(self, request: LLMRequest) -> Dict[str, Any]:
        """不使用MCP的基础聊天"""
        # 添加系统提示词
        if not any(msg.get("role") == "system" for msg in request.messages):
            request.messages.insert(0, {
                "role": "system",
                "content": system_prompt()
            })

        llm_entity = settings.LLM_ENTITY[request.model]
        payload = {
            "model": llm_entity["name"],
            "messages": request.messages,
            "temperature": request.temperature,
            # "max_tokens": request.max_tokens,
            "stream": False
        }
        
        # 调试日志
        # logger.info(f"LLM API 请求详情:")
        # logger.info(f"  URL: {self.base_url}/v1/chat/completions")
        # logger.info(f"  模型: {payload['model']}")
        # logger.info(f"  default_model: {self.default_model}")
        # logger.info(f"  request.model: {request.model}")
        # logger.info(f"  消息数量: {len(payload['messages'])}")
        
        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(
                f"{llm_entity['url']}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {llm_entity['api_key']}",
                    "Content-Type": "application/json"
                },
                json=payload
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"LLM API调用失败详情:")
                logger.error(f"  状态码: {response.status_code}")
                logger.error(f"  响应: {response.text}")
                logger.error(f"  请求payload: {payload}")
                raise Exception(f"LLM API调用失败: {response.status_code} - {response.text}")

    async def chat_stream(self, request: LLMRequest) -> AsyncGenerator[str, None]:
        """流式聊天接口"""
        if request.use_mcp:
            # 如果启用MCP，必须使用LangChain方式，失败则报错
            async for chunk in self._stream_with_langchain(request):
                yield chunk
        else:
            # 不使用MCP的普通流式聊天
            async for chunk in self._stream_without_mcp(request):
                        yield chunk
    
    async def _stream_with_langchain(self, request: LLMRequest) -> AsyncGenerator[str, None]:
        """使用LangChain的流式响应"""
        # 先获取完整结果，然后模拟流式输出
        result = await self._chat_with_langchain(request)
        
        if result and "choices" in result:
            content = result["choices"][0]["message"]["content"]
            
            # 模拟流式输出
            words = content.split()
            for i, word in enumerate(words):
                chunk_data = {
                    "choices": [{
                        "delta": {
                            "content": word if i == 0 else f" {word}"
                        }
                    }]
                }
                yield f"data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.05)
            
            # 发送结束标记
            yield "data: [DONE]\n\n"

    async def _stream_without_mcp(self, request: LLMRequest) -> AsyncGenerator[str, None]:
        """不使用MCP的流式聊天"""
        # 添加系统提示词
        if not any(msg.get("role") == "system" for msg in request.messages):
            request.messages.insert(0, {
                "role": "system",
                "content": system_prompt()
            })

        llm_entity = settings.LLM_ENTITY[request.model]
        
        payload = {
            "model": llm_entity["name"],
            "messages": request.messages,
            "temperature": request.temperature,
            # "max_tokens": request.max_tokens,
            "stream": True
        }
        
        async with httpx.AsyncClient(timeout=180.0) as client:
            print(f"xxxxxx__{llm_entity['url']}/v1/chat/completions")
            async with client.stream(
                "POST",
                f"{llm_entity['url']}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {llm_entity['api_key']}",
                    "Content-Type": "application/json"
                },
                json=payload
            ) as response:
                if response.status_code == 200:
                    async for line in response.aiter_lines():
                        if line.strip():
                            yield f"{line}\n"
                else:
                    error_msg = await response.aread()
                    yield f"data: {json.dumps({'error': f'HTTP {response.status_code}: {error_msg.decode()}'}, ensure_ascii=False)}\n\n"



llm_service = LLMService()

