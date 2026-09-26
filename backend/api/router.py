from fastapi import APIRouter
from .endpoints import analytics, targets, geo, cache, preferences, system, evidencias

api_router = APIRouter()

api_router.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
api_router.include_router(targets.router, prefix="/targets", tags=["Targets"])
api_router.include_router(geo.router, prefix="/geo", tags=["Geo"])
api_router.include_router(cache.router, prefix="/cache", tags=["Cache"])
api_router.include_router(preferences.router, prefix="/preferences", tags=["Preferences"])
api_router.include_router(evidencias.router, prefix="/evidencias", tags=["Evidencias"])
api_router.include_router(system.router, prefix="/system", tags=["System"])

