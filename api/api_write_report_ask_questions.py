"""
The API to ask questions to the user, in order to enrich the plan of the whole report. 
"""

import logging
import datetime, json
import asyncio
from fastapi import APIRouter, HTTPException
from models.models import LLMMessageAskQuestions, UpdateQuestion
from services.llm_service import LLMService
from services.mongo_api_service_manager import mongo_api_service_manager
from services.report_service import report_service
from services.step_record_service import step_record_service
from utils.exception_handler import ErrorCode
from utils.response_models import Result, BizError
from starlette.responses import StreamingResponse
