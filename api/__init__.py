"""
Initialization for the APIs
"""

from fastapi import FastAPI
from api.api_base import router as base_router
from api.api_report import router as report_router
from api.api_write_report_serp import router as write_report_serp_router
from api.api_write_report_ask_questions import router as write_report_ask_questions_router
from api.api_write_report_plan import router as write_report_plan_router


def setup_routers(app: FastAPI):
    app.include_router(base_router, prefix="")
    app.include_router(report_router, prefix="/report")
    app.include_router(write_report_serp_router, prefix="/serp")
    app.include_router(write_report_ask_questions_router, prefix="/ask_questions")
    app.include_router(write_report_plan_router, prefix="/plan")


__all__ = ["setup_routers"]
