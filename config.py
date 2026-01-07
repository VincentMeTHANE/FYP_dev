"""
The configuration file for the backend framework. 
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional, Dict
import os


class Settings(BaseSettings):
    # Redis Configuration
    REDIS_HOST: str = "192.168.113.94"
    REDIS_PORT: int = 16389
    REDIS_PASSWORD: str = "i5X#G!6!Xd52%E"
    REDIS_DB: int = 14

    # MySQL Configuration
    MYSQL_HOST: str = "192.168.111.90"
    MYSQL_PORT: int = 3307
    MYSQL_USER: str = "deepsearch"
    MYSQL_PASSWORD: str = "B7MnLPTn57DsbSLf"
    MYSQL_DATABASE: str = "deep-research"

    # MongoDB Configuration
    MONGO_HOST: str = "192.168.113.94"
    MONGO_PORT: int = 27017
    MONGO_DATABASE: str = "deep-research"
    MONGO_USERNAME: str = "root"
    MONGO_PASSWORD: str = "YTKJ9fyb^H%8Gy"
    MONGO_AUTH_DB: str = "admin"



    # LLM API configuration
    # LLM_BASE_URL: str = "http://copilot.sino-bridge.com:17000"
    # LLM_API_KEY: str = "xxxx"
    # LLM_MODEL: str = "qwen3-32b"
    # LLM_BASE_URL: str = "https://api.siliconflow.cn"
    # LLM_API_KEY: str = "sk-mwaysgirbjonsbfroswgoafxjmbekdmguqfecfcjxlxjnhdr"
    # LLM_MODEL: str = "Qwen/Qwen3-235B-A22B-Instruct-2507"    # Qwen/Qwen3-32B  Qwen/Qwen3-30B-A3B-Instruct-2507  deepseek-ai/DeepSeek-V3.1  Qwen/Qwen3-235B-A22B-Instruct-2507
    LLM_BASE_URL: str = "https://api.deepseek.com"
    LLM_API_KEY: str = "sk-76def72c425f40e59ce890c2fa5e873e"
    LLM_MODEL: str = "deepseek-chat"    
    LLM_CHECK_ROLE_MODEL: str = "deepseek-chat"
    
    # Tavily(Current Search Engine Configuration)
    TAVILY_BASE_URL: str = "https://api.tavily.com"
    TAVILY_API_KEY: str = "tvly-YOUR_API_KEY_HERE"  # 请设置你的Tavily API Key

    #SEARCH_BASE_URL: str = "http://192.168.113.18:8001"
    SEARCH_BASE_URL: str = "https://copilot.sino-bridge.com/chromePa"
    # BASE_URL: str = "https://copilot.sino-bridge.com/"   # http://192.168.113.18:6012
    BASE_URL: str = "http://192.168.113.18:6012"   #

    LLM_ENTITY: Dict[str, Dict[str, str]] = {
        "ask_questions": {
            # "name": "gemini-2.5-pro",
            # "url": "https://api.cursorai.art",
            # "api_key": "sk-rwvMCvsmBFX9RF6uJNv4mqSbZY2tgmWysz3IK0rIw6av28Wi"
            "name": "deepseek-chat",
            "url": "https://api.deepseek.com",
            "api_key": "sk-76def72c425f40e59ce890c2fa5e873e"
        },
        "plan": {
            "name": "deepseek-chat",
            "url": "https://api.deepseek.com",
            "api_key": "sk-76def72c425f40e59ce890c2fa5e873e"
        },
        "serp": {
            # "name": "qwen3-32b",
            # "url": "http://copilot.sino-bridge.com:17000",
            # "api_key": "default_token"
            "name": "deepseek-chat",
            "url": "https://api.deepseek.com",
            "api_key": "sk-76def72c425f40e59ce890c2fa5e873e"

        },
        "search": {
            # "name": "deepseek-ai/DeepSeek-V3.1",
            # "url": "https://api.deepseek.com",
            # "api_key": "sk-mwaysgirbjonsbfroswgoafxjmbekdmguqfecfcjxlxjnhdr"
            "name": "deepseek-chat",
            "url": "https://api.deepseek.com",
            "api_key": "sk-76def72c425f40e59ce890c2fa5e873e"
        },
        "search_summary": {
            "name": "deepseek-chat",
            "url": "https://api.deepseek.com",
            "api_key": "sk-76def72c425f40e59ce890c2fa5e873e"
        },
        "search_check": {
            # "name": "gemini-2.5-pro",
            # "url": "https://api.cursorai.art",
            # "api_key": "sk-rwvMCvsmBFX9RF6uJNv4mqSbZY2tgmWysz3IK0rIw6av28Wi"
            "name": "deepseek-chat",
            "url": "https://api.deepseek.com",
            "api_key": "sk-76def72c425f40e59ce890c2fa5e873e"
        },
        "report_final": {
            "name": "deepseek-chat",
            "url": "https://api.deepseek.com",
            "api_key": "sk-76def72c425f40e59ce890c2fa5e873e"
        },
        "value_extract": {
            "name": "deepseek-chat",
            "url": "https://api.deepseek.com",
            "api_key": "sk-76def72c425f40e59ce890c2fa5e873e"
        }
    }


    class Config:
        env_file = ".env"


settings = Settings()