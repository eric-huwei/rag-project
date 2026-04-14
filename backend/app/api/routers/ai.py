from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.ai_service import ai_service

router = APIRouter()


class AIChatRequest(BaseModel):
    callId: str = Field(..., description="流水号")
    content: str = Field(..., description="发送给 AI 的对话内容")


class AIChatResponse(BaseModel):
    callId: str
    answer: str


@router.post("/chat", response_model=AIChatResponse)
def chat_with_ai(payload: AIChatRequest) -> dict[str, str]:
    try:
        return ai_service.ask(call_id=payload.callId, content=payload.content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI request failed: {exc}") from exc
