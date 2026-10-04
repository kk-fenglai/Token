"""Scripted stand-in for the OpenAI SDK client, shaped like DeepSeek's
streamed Chat Completions (reasoning_content deltas, cache usage fields)."""
from __future__ import annotations

import copy
from types import SimpleNamespace as NS


def text(s: str, reasoning: str = "", finish: str = "stop", usage: dict | None = None) -> list:
    chunks = []
    if reasoning:
        chunks.append(_delta(reasoning_content=reasoning))
    for part in [s[i:i + 5] for i in range(0, len(s), 5)] or [""]:
        chunks.append(_delta(content=part))
    chunks.append(_finish(finish))
    chunks.append(_usage(**(usage or {})))
    return chunks


def tool_calls(calls: list[tuple[str, str, str]], reasoning: str = "", content: str = "",
               usage: dict | None = None) -> list:
    """calls: [(id, name, arguments_json)] — arguments split across chunks."""
    chunks = []
    if reasoning:
        chunks.append(_delta(reasoning_content=reasoning))
    if content:
        chunks.append(_delta(content=content))
    for i, (cid, name, args) in enumerate(calls):
        chunks.append(_delta(tool_calls=[NS(index=i, id=cid, function=NS(name=name, arguments=""))]))
        half = len(args) // 2
        for piece in (args[:half], args[half:]):
            chunks.append(_delta(tool_calls=[NS(index=i, id=None, function=NS(name=None, arguments=piece))]))
    chunks.append(_finish("tool_calls"))
    chunks.append(_usage(**(usage or {})))
    return chunks


def _delta(content=None, reasoning_content=None, tool_calls=None):
    d = NS(content=content, tool_calls=tool_calls)
    if reasoning_content is not None:
        d.reasoning_content = reasoning_content
    return NS(choices=[NS(delta=d, finish_reason=None)], usage=None)


def _finish(reason):
    return NS(choices=[NS(delta=NS(content=None, tool_calls=None), finish_reason=reason)], usage=None)


def _usage(prompt=1000, hit=800, miss=200, completion=50):
    return NS(choices=[], usage=NS(prompt_tokens=prompt, prompt_cache_hit_tokens=hit,
                                   prompt_cache_miss_tokens=miss, completion_tokens=completion,
                                   completion_tokens_details=None))


class _Stream:
    def __init__(self, chunks):
        self._it = iter(chunks)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration from None


class FakeClient:
    """`script` is a list of responses; each is a chunk list or an exception."""

    def __init__(self, script: list):
        self.script = list(script)
        self.requests: list[dict] = []
        self.chat = NS(completions=NS(create=self._create))
        self.models = NS(list=self._models)

    async def _create(self, **kw):
        self.requests.append(copy.deepcopy(kw))
        if not self.script:
            raise AssertionError("FakeClient ran out of scripted responses")
        nxt = self.script.pop(0)
        if isinstance(nxt, BaseException):
            raise nxt
        return _Stream(nxt)

    async def _models(self):
        return NS(data=[NS(id="deepseek-flash"), NS(id="deepseek-v4-pro")])
