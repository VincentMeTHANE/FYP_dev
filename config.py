"""
The configuration file for the backend framework. 
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional, Dict
import os


class Settings(BaseSettings):
    # Redis Configuration
    REDIS_HOST: str = ""
    REDIS_PORT: int = 
    REDIS_PASSWORD: str = ""
    REDIS_DB: int = 

    # MySQL Configuration
    MYSQL_HOST: str = ""
    MYSQL_PORT: int = 
    MYSQL_USER: str = ""
    MYSQL_PASSWORD: str = ""
    MYSQL_DATABASE: str = ""

    # MongoDB Configuration
    MONGO_HOST: str = ""
    MONGO_PORT: int = 
    MONGO_DATABASE: str = ""
    MONGO_USERNAME: str = ""
    MONGO_PASSWORD: str = ""
    MONGO_AUTH_DB: str = ""

    LLM_BASE_URL: str = ""
    LLM_API_KEY: str = ""
    LLM_MODEL: str = ""    
    LLM_CHECK_ROLE_MODEL: str = ""
    
    # Tavily(Current Search Engine Configuration)
    TAVILY_BASE_URL: str = ""
    TAVILY_API_KEY: str = ""

    #SEARCH_BASE_URL: str = ""
    SEARCH_BASE_URL: str = ""
    # BASE_URL: str = ""
    BASE_URL: str = ""

    LLM_ENTITY: Dict[str, Dict[str, str]] = {
        "ask_questions": {
            # "name": "",
            # "url": "",
            # "api_key": ""
            "name": "",
            "url": "",
            "api_key": ""
        },
        "plan": {
            "name": "",
            "url": "",
            "api_key": ""
        },
        "serp": {
            # "name": "",
            # "url": "",
            # "api_key": ""
            "name": "",
            "url": "",
            "api_key": ""

        },
        "search": {
            # "name": "",
            # "url": "",
            # "api_key": ""
            "name": "",
            "url": "",
            "api_key": ""
        },
        "search_summary": {
            "name": "",
            "url": "",
            "api_key": ""
        },
        "search_check": {
            # "name": "",
            # "url": "",
            # "api_key": ""
            "name": "",
            "url": "",
            "api_key": ""
        },
        "report_final": {
            "name": "",
            "url": "",
            "api_key": ""
        },
        "value_extract": {
            "name": "",
            "url": "",
            "api_key": ""
        }
    }


    class Config:
        env_file = ".env"


settings = Settings()