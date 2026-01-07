"""
Global exception handler
"""
import logging
from typing import Union
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from .response_models import Result, BizError

logger = logging.getLogger(__name__)


async def biz_error_handler(request: Request, exc: BizError) -> JSONResponse:
    """
    Handle custom exceptions
    """
    logger.warning(f"Exception: {exc}")
    result = Result.error(code=exc.code, message=exc.message)
    return JSONResponse(
        status_code=200,
        content=result.model_dump()
    )


async def http_exception_handler(request: Request, exc: Union[HTTPException, StarletteHTTPException]) -> JSONResponse:
    """
    Handle HTTP exceptions
    """
    logger.error(f"HTTP exception: {exc}")
    result = Result.error(
        code=exc.status_code,
        message=exc.detail if hasattr(exc, 'detail') else str(exc)
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=result.model_dump()
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """
    Handle request parameter validation exceptions
    """
    logger.error(f"Validation exception: {exc}")
    # Extract detailed validation error information
    error_details = []
    for error in exc.errors():
        field = " -> ".join(str(x) for x in error["loc"])
        message = error["msg"]
        error_details.append(f"{field}: {message}")
    
    result = Result.error(
        code=400,
        message=f"Validation failed: {'; '.join(error_details)}"
    )
    return JSONResponse(
        status_code=400,
        content=result.model_dump()
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Handle other uncaught exceptions
    """
    logger.error(f"Uncaught exception: {type(exc).__name__}: {exc}", exc_info=True)
    result = Result.error(
        code=500,
        message="Internal server error"
    )
    return JSONResponse(
        status_code=500,
        content=result.model_dump()
    )


def setup_exception_handlers(app):
    """
    Set up global exception handlers
    """
    # Custom business exceptions
    app.add_exception_handler(BizError, biz_error_handler)
    
    # HTTP exceptions
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    
    # Request parameter validation exceptions
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    
    # General exception handling
    app.add_exception_handler(Exception, general_exception_handler)
    
    logger.info("Global exception handlers have been set up")


class ErrorCode:
    SUCCESS = (0, "Operation successful")

    USER_NOT_LOGGED_IN = (400, "User not logged in")
    TOKEN_NOT_EMPTY = (401, "Token cannot be empty")
    TENANT_ID_NOT_EMPTY = (402, "Tenant ID cannot be empty")

    DATA_FORMAT_ERROR = (500, "Data format error")

    REPORT_NOT_EXIST = (1001, "Report not exist")
    REPORT_DELETE_FAILED = (1002, "Report delete failed")
    REPORT_INVALID_STEPS = (1003, "Invalid step name")
    REPORT_ID_NOT_EXIST = (1004, "report_id not exist")
    REPORT_TITLE_NOT_EXIST = (1005, "Report title not exist")
    REPORT_UPDATE_FAILED = (1006, "Report update failed")

    PLAN_NOT_EXIST = (2001, "Plan not exist")
    PLAN_RESPONSE_NOT_EXIST = (2002, "Plan response not exist or format error")
    PLAN_ID_NOT_EMPTY = (2003, "plan_id cannot be empty")
    OUTLINE_NOT_EXIST = (2004, "Report outline not exist")

    SERP_NEED_EFFECTIVE = (3001, "SERP query needs valid split_id and plan_id")
    SERP_CHAPTER_NOT_EXIST = (3002, "Specified chapter ID not exist")
    SERP_LACK_REPORT_ID = (3003, "Chapter record lacks report_id")

    TASK_ID_NOT_EMPTY = (4001, "task_id cannot be empty")
    TASK_NOT_EXIST = (4002, "task not exist")
    SPLIT_ID_NOT_EMPTY = (4003, "split_id cannot be empty")
    TASK_DELETE_FAIL = (4004, "task delete failed")

    SEARCH_ID_NOT_EMPTY = (5001, "search_id cannot be empty")
    SEARCH_QUERY_NOT_EMPTY = (5002, "Search query parameter cannot be empty")

    FINAL_NEED_EFFECTIVE = (6001, "Search summary needs valid report_id and split_id")

    # Template related error codes
    TEMPLATE_NOT_EXIST = (7001, "Template not exist")
    TEMPLATE_CREATE_FAILED = (7002, "Template create failed")
    TEMPLATE_UPDATE_FAILED = (7003, "Template update failed")
    TEMPLATE_DELETE_FAILED = (7004, "Template delete failed")
    TEMPLATE_ID_INVALID = (7005, "Template ID invalid")
    TEMPLATE_NAME_REQUIRED = (7006, "Template name cannot be empty")
    TEMPLATE_CONTENT_REQUIRED = (7007, "Template content cannot be empty")

    LARGE_MODEL_RESPONSE_FAILED = (9001, "Large model response failed")

    @classmethod
    def get_code(cls, error):
        return error[0]

    @classmethod
    def get_message(cls, error):
        return error[1]
