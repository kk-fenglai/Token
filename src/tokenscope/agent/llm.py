"""DeepSeek via the OpenAI SDK: client construction, one streamed completion
folded into events, and error mapping.

DeepSeek extends the OpenAI deltas with `reasoning_content` (thinking mode)
and the usage block with `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens`.
The SDK keeps unknown fields as attributes (pydantic extra), so they are read
with getattr and never assumed present.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import AsyncIterator

import openai
from openai import AsyncOpenAI


def make_client(api_key: str, cfg: dict) -> AsyncOpenAI:
    return AsyncOpenAI(api_key=api_key, base_url=cfg["base_url"], max_retries=2, timeout=120.0)


@dataclass
class Completion:
    content: str = ""
    reasoning: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    finish_reason: str | None = None
    usage: dict = field(default_factory=dict)


def _usage(u) -> dict:
    if u is None:
        return {}
    prompt = getattr(u, "prompt_tokens", 0) or 0
    hit = getattr(u, "prompt_cache_hit_tokens", None)
    miss = getattr(u, "prompt_cache_miss_tokens", None)
    if hit is None and miss is None:
        details = getattr(u, "prompt_tokens_details", None)
        hit = getattr(details, "cached_tokens", 0) or 0 if details is not None else 0
        miss = prompt - hit
    details = getattr(u, "completion_tokens_details", None)
    return {"prompt": prompt, "hit": hit or 0, "miss": miss or 0,
            "completion": getattr(u, "completion_tokens", 0) or 0,
            "reasoning": (getattr(details, "reasoning_tokens", 0) or 0) if details is not None else 0}


async def stream_completion(client: AsyncOpenAI, *, model: str, messages: list[dict],
                            tools: list[dict] | None, thinking: bool) -> AsyncIterator[tuple[str, object]]:
    """Yields ("reasoning", str) and ("text", str) deltas while streaming,
    then exactly one ("done", Completion)."""
    kwargs: dict = {
        "model": model, "messages": messages, "stream": True,
        "stream_options": {"include_usage": True},
        "extra_body": {"thinking": {"type": "enabled" if thinking else "disabled"}},
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    stream = await client.chat.completions.create(**kwargs)
    comp = Completion()
    calls: dict[int, dict] = {}
    async for chunk in stream:
        if getattr(chunk, "usage", None):
            comp.usage = _usage(chunk.usage)
        for choice in getattr(chunk, "choices", None) or []:
            delta = choice.delta
            r = getattr(delta, "reasoning_content", None)
            if r:
                comp.reasoning += r
                yield "reasoning", r
            if delta.content:
                comp.content += delta.content
                yield "text", delta.content
            for tc in getattr(delta, "tool_calls", None) or []:
                slot = calls.setdefault(tc.index, {"id": "", "type": "function",
                                                   "function": {"name": "", "arguments": ""}})
                if tc.id:
                    slot["id"] = tc.id
                fn = getattr(tc, "function", None)
                if fn is not None:
                    if fn.name:
                        slot["function"]["name"] += fn.name
                    if fn.arguments:
                        slot["function"]["arguments"] += fn.arguments
            if choice.finish_reason:
                comp.finish_reason = choice.finish_reason
    comp.tool_calls = [calls[i] for i in sorted(calls)]
    yield "done", comp


def map_error(exc: BaseException) -> tuple[str, str]:
    """(code, message) for the UI. Most specific first."""
    if isinstance(exc, openai.AuthenticationError):
        return "auth", "API Key 无效或已被撤销"
    if isinstance(exc, openai.RateLimitError):
        return "rate_limit", "请求太频繁,稍后再试"
    if isinstance(exc, openai.APITimeoutError):
        return "network", "请求超时"
    if isinstance(exc, openai.APIConnectionError):
        return "network", "无法连接到 DeepSeek"
    if isinstance(exc, openai.BadRequestError):
        return "bad_request", str(getattr(exc, "message", exc))[:500]
    if isinstance(exc, openai.NotFoundError):
        return "bad_model", str(getattr(exc, "message", exc))[:300]
    if isinstance(exc, openai.APIStatusError):
        if exc.status_code == 402:
            return "balance", "DeepSeek 账户余额不足"
        if exc.status_code >= 500:
            return "server_busy", f"DeepSeek 服务繁忙({exc.status_code})"
        return "api_error", f"HTTP {exc.status_code}: {str(getattr(exc, 'message', exc))[:300]}"
    return "internal", f"{type(exc).__name__}: {exc}"[:500]
