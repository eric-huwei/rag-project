from __future__ import annotations

from threading import Lock
from typing import Any

from app.core.config import settings


class AIService:
    def __init__(self) -> None:
        self._content_store: dict[str, str] = {}
        self._lock = Lock()

    def save_content(self, *, call_id: str, content: str) -> None:
        with self._lock:
            self._content_store[call_id] = content

    def get_content(self, call_id: str) -> str | None:
        with self._lock:
            return self._content_store.get(call_id)

    def ask(self, *, call_id: str, content: str) -> dict[str, str]:
        clean_call_id = call_id.strip()
        clean_content = content.strip()

        if not clean_call_id:
            raise ValueError("callId is required")
        if not clean_content:
            raise ValueError("content is required")
        if not settings.aliai_api_key:
            raise RuntimeError("ALIAI_API_KEY is not configured")

        self.save_content(call_id=clean_call_id, content=clean_content)

        completion = self._create_completion(clean_content)
        answer = self._extract_answer(completion)

        if not answer:
            raise RuntimeError("AI returned an empty answer")

        return {"callId": clean_call_id, "answer": answer}

    def _create_completion(self, content: str) -> Any:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("openai package is not installed") from exc

        client = OpenAI(
            api_key=settings.aliai_api_key,
            base_url=settings.aliai_base_url,
        )
        return client.chat.completions.create(
            model=settings.aliai_model,
            messages=[{"role": "user", "content": content}],
        )

    def _extract_answer(self, completion: Any) -> str:
        choices = getattr(completion, "choices", None) or []
        if not choices:
            return ""

        message = getattr(choices[0], "message", None)
        content = getattr(message, "content", None)

        if isinstance(content, str):
            return content.strip()

        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                else:
                    text = getattr(item, "text", None)
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
            return "\n".join(parts).strip()

        return ""


ai_service = AIService()

__all__ = ["AIService", "ai_service"]
