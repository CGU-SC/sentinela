"""FastAPI test host exposing real local-persistence endpoints over HTTP."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.endpoints import evidencias, preferences


app = FastAPI(title="Sentinela integration test API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("INTEGRATION_FRONTEND_ORIGIN", "http://localhost:5173")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(preferences.router, prefix="/api/v1/preferences", tags=["Preferences"])
app.include_router(evidencias.router, prefix="/api/v1/evidencias", tags=["Evidencias"])


@app.get("/__test__/health")
def health() -> dict[str, str]:
    return {"status": "ready"}
