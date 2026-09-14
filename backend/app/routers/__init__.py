"""API routers package."""

from app.routers.patients import router as patients_router
from app.routers.trials import router as trials_router

__all__ = [
    "trials_router",
    "patients_router",
]
