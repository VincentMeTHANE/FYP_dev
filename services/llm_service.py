"""
LLM service using LangChain and MCP
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


def system_prompt():
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"""
    You are a professional researcher. Today is {now}. Please follow these guidelines when responding:
    - You may be asked to research topics beyond your knowledge cutoff date; when receiving news information, assume the user's content is correct.
    - The user is an experienced analyst; do not simplify content, be as detailed as possible and ensure accuracy.
    - Content must be highly organized.
    - Propose solutions I have not considered.
    - Be proactive and anticipate my needs.
    - Treat me as an expert in all fields.
    - Errors weaken my trust, so ensure content is accurate and comprehensive.
    - Provide detailed explanations; I can accept a large amount of detail.
    - Value persuasive arguments over authority; the source of information is irrelevant.
    - Consider not only traditional views but also new technologies and reverse thinking.
    - You may engage in high levels of speculation or prediction, but take responsibility for them.
    - Please respond in Simplified Chinese.
    - /no_think
    """


def response_language_prompt():
    return "**Respond in the same language as the user**"


class LLMService:
    """LLM service using LangChain and MCP"""

    def __init__(self):
        self.base_url = settings.LLM_BASE_URL
        self.api_key = settings.LLM_API_KEY
        self.default_model = settings.LLM_MODEL
        self._langchain_cache = {}
        self._react_agent_cache = {}
        self._mcp_initialized = False

    async def _get_langchain_llm(self, model: str = None):
        """Get LangChain LLM instance for specified model"""
        model = model or self.default_model

        if model not in self._langchain_cache:
            from langchain_openai import ChatOpenAI

            llm_entity = settings.LLM_ENTITY[model]

            self._langchain_cache[model] = ChatOpenAI(
                openai_api_key=llm_entity["api_key"],
                openai_api_base=f"{llm_entity['url']}/v1",
                temperature=0.1
            )
            logger.info(f"Created LangChain instance for model {model}")

        return self._langchain_cache[model]

    async def _get_react_agent(self, model: str = None):
        """Get ReAct agent for specified model"""
        model = model or self.default_model

        if model not in self._react_agent_cache:
            if not self._mcp_initialized:
                await mcp_client_service.initialize()
                self._mcp_initialized = True

            langchain_llm = await self._get_langchain_llm(model)

            react_agent = await mcp_client_service.create_react_agent(langchain_llm)

            if not react_agent:
                raise Exception(f"Failed to create ReAct agent for model {model}, MCP functionality unavailable")

            self._react_agent_cache[model] = react_agent
            logger.info(f"Created ReAct agent for model {model}")

        return self._react_agent_cache[model]

    async def completion(self, message: str, use_mcp: bool = False, model: str = None):
        """Non-streaming chat completion"""
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

    async def check_rule(self, message: str, model: str = None):
        """Check if content conforms to rules using LLM"""
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
        return result["choices"][0]["message"]["content"]

    async def stream(self, message: str, use_mcp: bool = False, model: str = None):
        """Streaming chat - returns async generator"""
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
        async for chunk in self.chat_stream(request):
            yield chunk
    
    async def chat_completion(self, request: LLMRequest) -> Dict[str, Any]:
        """Chat completion interface"""
        model = request.model or self.default_model
        logger.info(f"Chat completion request: use_mcp={request.use_mcp}, model={model}")

        if request.use_mcp:
            logger.info("Using LangChain + MCP path")
            return await self._chat_with_langchain(request)
        else:
            logger.info("Using regular chat path")
            return await self._chat_without_mcp(request)

    async def _chat_with_langchain(self, request: LLMRequest) -> Dict[str, Any]:
        """Chat completion using LangChain ReAct agent"""
        try:
            model = request.model or self.default_model

            react_agent = await self._get_react_agent(model)

            user_message = ""
            for msg in request.messages:
                if msg.get("role") == "user":
                    user_message = msg.get("content", "")
                    break

            if not user_message:
                raise ValueError("User message not found")

            from langchain.schema import HumanMessage

            result = await react_agent.ainvoke({
                "messages": [HumanMessage(content=user_message)]
            })

            final_message = result["messages"][-1]
            tool_calls = []

            for msg in result["messages"]:
                if hasattr(msg, 'tool_calls') and msg.tool_calls:
                    for call in msg.tool_calls:
                        tool_calls.append({
                            "tool_name": call.get('name', 'unknown'),
                            "parameters": call.get('args', {}),
                            "result": "completed"
                        })

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

            logger.info(f"LangChain processing completed, called {len(tool_calls)} tools")
            return response

        except Exception as e:
            logger.error(f"LangChain processing failed: {e}")
            raise

    async def _chat_without_mcp(self, request: LLMRequest) -> Dict[str, Any]:
        """Basic chat without MCP"""
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
            "stream": False
        }

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
                logger.error(f"LLM API call failed - Status: {response.status_code}, Response: {response.text}")
                logger.error(f"Request payload: {payload}")
                raise Exception(f"LLM API call failed: {response.status_code} - {response.text}")

    async def chat_stream(self, request: LLMRequest) -> AsyncGenerator[str, None]:
        """Streaming chat interface"""
        if request.use_mcp:
            async for chunk in self._stream_with_langchain(request):
                yield chunk
        else:
            async for chunk in self._stream_without_mcp(request):
                yield chunk

    async def _stream_with_langchain(self, request: LLMRequest) -> AsyncGenerator[str, None]:
        """Streaming response using LangChain"""
        result = await self._chat_with_langchain(request)

        if result and "choices" in result:
            content = result["choices"][0]["message"]["content"]

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

            yield "data: [DONE]\n\n"

    async def _stream_without_mcp(self, request: LLMRequest) -> AsyncGenerator[str, None]:
        """Streaming chat without MCP"""
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