"""
Initialization for the APIs
"""

from fastapi import FastAPI
from api.api_base import router as base_router


def setup_routers(app: FastAPI):
    app.include_router(base_router, prefix="/")


__all__ = ["setup_routers"]
