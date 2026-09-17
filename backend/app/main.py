from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router

app = FastAPI(
    title="Agentic Location Web Intelligence System",
    description="A LocationResearchAgent that investigates public information about a place to answer a question.",
    version="0.1.0",
)

# Local-dev-only CORS: the frontend (Vite dev server) runs on a different
# origin/port than this API. Not a production CORS policy.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
