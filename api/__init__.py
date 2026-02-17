"""
Initialization for the APIs
"""

from fastapi import FastAPI
from api.api_base import router as base_router
from api.api_report import router as report
from api.api_write_report_serp import router as write_report_serp
from api.api_write_report_ask_questions import router as write_report_ask_questions
from api.api_write_report_plan import router as write_report_plan
from api.api_write_report_search import router as write_report_search
from api.api_write_report_search_summary import router as write_report_search_summary
from api.api_write_report_final import router as write_report_final


def setup_routers(app: FastAPI):
    app.include_router(base_router, prefix="")
    app.include_router(report, prefix="/report")
    app.include_router(write_report_serp, prefix="/serp")
    app.include_router(write_report_search_summary, prefix="/summary")
    app.include_router(write_report_ask_questions, prefix="/ask_questions")
    app.include_router(write_report_plan, prefix="/plan")
    app.include_router(write_report_search, prefix="/search")
    app.include_router(write_report_final, prefix="/final")


__all__ = ["setup_routers"]
