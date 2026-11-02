"""Optional OpenAI-compatible structured extraction, never called by the allocator."""

import json
import os
from urllib.parse import urlparse
import httpx
from backend.app.schemas import LLMExtraction
from .prompts import SYSTEM_PROMPT, PROMPT_VERSION


def provider_status():
    # Explicit offline mode wins even when credentials remain in the environment.
    # With LLM_PROVIDER unset, preserve the original credentials-based selection.
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    configured = provider != "rules" and bool(
        os.getenv("LLM_API_KEY")
        and os.getenv("LLM_MODEL")
        and os.getenv("LLM_BASE_URL")
    )
    return {
        "mode": "openai" if configured else "rules",
        "configured": configured,
        "model": os.getenv("LLM_MODEL") or None,
        "prompt_version": PROMPT_VERSION,
        "reference_date": "2026-04-01",
        "live_provider_verified": False,
    }


def parse_with_provider(message, context=None):
    if not provider_status()["configured"]:
        return None, None
    base = os.environ["LLM_BASE_URL"].rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme != "https" and parsed.hostname not in ("localhost", "127.0.0.1"):
        return None, "模型地址需使用 HTTPS；已切换规则解析。"
    payload = {
        "model": os.environ["LLM_MODEL"],
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {"message": message, "pending_context": context}, ensure_ascii=False
                ),
            },
        ],
        "response_format": {"type": "json_object"},
    }
    # One bounded request. A failure never exposes credentials or upstream response text.
    try:
        with httpx.Client(timeout=httpx.Timeout(20, connect=5)) as client:
            response = client.post(
                base + "/chat/completions",
                json=payload,
                headers={"Authorization": "Bearer " + os.environ["LLM_API_KEY"]},
            )
            response.raise_for_status()
            value = response.json()["choices"][0]["message"]["content"]
            result = LLMExtraction.model_validate_json(value)
        return result, None
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
        return None, "模型请求失败或输出校验未通过；本次使用受限规则解析。"
