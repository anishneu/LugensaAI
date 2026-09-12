from __future__ import annotations

from fastapi import FastAPI

from app.api.routes import router

app = FastAPI(
    title="Agentic Location Web Intelligence System",
    description="A LocationResearchAgent that investigates public information about a place to answer a question.",
    version="0.1.0",
)
app.include_router(router, prefix="/api")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
