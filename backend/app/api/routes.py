from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agents.factory import build_default_agent
from app.models.response import ResearchResponse
from app.tools.base import LocationNotFoundError

router = APIRouter()


class ResearchRequest(BaseModel):
    location: str
    question: str


@router.post("/research", response_model=ResearchResponse)
def research(request: ResearchRequest) -> ResearchResponse:
    agent = build_default_agent()
    try:
        return agent.run(request.location, request.question)
    except LocationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
