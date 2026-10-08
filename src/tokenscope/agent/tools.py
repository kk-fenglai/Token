"""Tool registry: which Python functions the model may call, their JSON
schemas, and how results are shrunk before they go back into the context.

The whitelist below IS the safety boundary under "fully automatic" mode:
there is no shell, no file editing, and every function either reads
TokenScope data or performs one narrow, validated write. Each tool has a
`kind`:
  read      no side effects (sync_now counts: it only re-reads transcripts)
  write     changes local TokenScope state (pricing, aliases, project notes)
  external  leaves the machine (git push / GitHub API)

Schemas are built from the function signature with pydantic, which also
validates the model's arguments, then simplified — `X | None` becomes an
optional `X` — because OpenAI-compatible backends vary in `anyOf` support.
"""
from __future__ import annotations

import inspect
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, ValidationError, create_model

from .. import mcp_server
from . import tools_extra

Kind = Literal["read", "write", "external"]

MCP_TOOLS: dict[str, Kind] = {
    "get_summary": "read", "get_trend": "read", "get_models_distribution": "read",
    "get_projects_top": "read", "get_projects": "read", "get_project_detail": "read",
    "query_logs": "read", "sync_now": "read", "get_sync_status": "read", "get_pricing": "read",
    "get_subscription_savings": "read", "get_project_share": "read", "get_project_grouping": "read",
    "get_sessions": "read", "get_session_detail": "read", "get_tools_breakdown": "read",
    "get_heatmap": "read", "get_alerts": "read", "get_dev_projects": "read",
    "get_weekly_report": "read", "get_retention_status": "read", "get_project_todos": "read",
    "update_pricing": "write", "set_subscription": "write", "set_project_alias": "write",
    "set_workspace_roots": "write", "add_project_todo": "write",
}
# Deliberately NOT exposed: launch_dashboard (we are the dashboard),
# platform_push / platform_status / set_session_requirement (AIPM platform
# integration — pushes data to another server).
EXCLUDED = {"launch_dashboard", "platform_push", "platform_status", "set_session_requirement"}

EXTRA_TOOLS: dict[str, Kind] = {
    "get_efficiency_snapshot": "read", "get_dev_project_detail": "read", "get_publish_plan": "read",
    "get_repo_changes": "read", "get_agent_usage": "read",
    "save_project_meta": "write",
    "publish_project": "external", "push_github_description": "external",
}

DEFAULT_MAX_CHARS = 16_000
LOG_MAX_CHARS = 200_000


@dataclass
class ToolSpec:
    name: str
    fn: Callable[..., Any]
    description: str
    parameters: dict
    model: type[BaseModel]
    kind: Kind
    timeout: float = 60.0
    max_chars: int = DEFAULT_MAX_CHARS


@dataclass
class ToolResult:
    ok: bool
    content: str            # what the model sees (shrunk)
    full: str               # what the audit log keeps
    truncated: bool
    ms: int
    status: str = "ok"      # ok | error | blocked | denied
    data: Any = field(default=None, repr=False)


# ---------------------------------------------------------------- schemas ----

def _simplify(schema: dict, defs: dict | None = None) -> dict:
    defs = defs if defs is not None else schema.get("$defs", {})
    if isinstance(schema, dict):
        if "$ref" in schema:
            ref = schema["$ref"].rsplit("/", 1)[-1]
            return _simplify(dict(defs.get(ref, {})), defs)
        if "anyOf" in schema:
            opts = [o for o in schema["anyOf"] if o.get("type") != "null"]
            if len(opts) == 1:
                merged = {**{k: v for k, v in schema.items() if k != "anyOf"}, **opts[0]}
                return _simplify(merged, defs)
        out = {}
        for k, v in schema.items():
            if k in ("title", "$defs"):
                continue
            if k == "default" and v is None:
                continue
            if isinstance(v, dict):
                out[k] = {pk: _simplify(pv, defs) for pk, pv in v.items()} if k == "properties" else _simplify(v, defs)
            elif isinstance(v, list):
                out[k] = [_simplify(x, defs) if isinstance(x, dict) else x for x in v]
            else:
                out[k] = v
        return out
    return schema


def _model_for(name: str, fn: Callable) -> type[BaseModel]:
    fields: dict = {}
    hints = inspect.get_annotations(fn, eval_str=True)
    for pname, p in inspect.signature(fn).parameters.items():
        ann = hints.get(pname, Any)
        default = ... if p.default is inspect.Parameter.empty else p.default
        fields[pname] = (ann, default)
    return create_model(f"{name}_args", __config__=ConfigDict(extra="forbid"), **fields)


def _spec(name: str, fn: Callable, kind: Kind) -> ToolSpec:
    model = _model_for(name, fn)
    schema = _simplify(model.model_json_schema())
    schema.setdefault("properties", {})
    schema["additionalProperties"] = False
    doc = inspect.getdoc(fn) or name
    timeout = 180.0 if kind == "external" else 90.0 if name in ("sync_now", "get_dev_projects") else 60.0
    return ToolSpec(name=name, fn=fn, description=doc[:1800], parameters=schema, model=model,
                    kind=kind, timeout=timeout)


def build_registry() -> dict[str, ToolSpec]:
    reg: dict[str, ToolSpec] = {}
    for name, kind in MCP_TOOLS.items():
        reg[name] = _spec(name, getattr(mcp_server, name), kind)
    for name, kind in EXTRA_TOOLS.items():
        reg[name] = _spec(name, getattr(tools_extra, name), kind)
    return reg


_REGISTRY: dict[str, ToolSpec] | None = None


def registry() -> dict[str, ToolSpec]:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = build_registry()
    return _REGISTRY


# ----------------------------------------------------------------- shrink ----

def _dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str, separators=(",", ":"))


def shrink(obj: Any, max_chars: int = DEFAULT_MAX_CHARS) -> tuple[str, bool]:
    """Compact JSON under `max_chars`: repeatedly halve the longest list
    (recording the original length under `_truncated`), then hard-cut."""
    text = _dump(obj)
    if len(text) <= max_chars:
        return text, False
    if isinstance(obj, (dict, list)):
        obj = json.loads(text)  # private copy
        marks: dict[str, int] = {}
        for _ in range(40):
            longest: tuple[int, list | None, str] = (0, None, "")

            def walk(node, path):
                nonlocal longest
                if isinstance(node, list):
                    if len(node) > longest[0]:
                        longest = (len(node), node, path)
                    for i, x in enumerate(node[:50]):
                        walk(x, f"{path}[{i}]")
                elif isinstance(node, dict):
                    for k, v in node.items():
                        walk(v, f"{path}.{k}" if path else k)
            walk(obj, "")
            n, lst, path = longest
            if lst is None or n <= 3:
                break
            marks.setdefault(path or "$", n)
            del lst[max(3, n // 2):]
            if isinstance(obj, dict):
                obj["_truncated"] = marks
            text = _dump(obj if not isinstance(obj, list) else {"items": obj, "_truncated": marks})
            if len(text) <= max_chars:
                return text, True
    return text[:max_chars] + "…[truncated]", True


# ----------------------------------------------------------------- toolset ----

class ToolSet:
    def __init__(self, kinds: set[str]):
        self.specs = {n: s for n, s in registry().items() if s.kind in kinds}

    def schemas(self) -> list[dict]:
        return [{"type": "function", "function": {"name": s.name, "description": s.description,
                                                  "parameters": s.parameters}}
                for s in self.specs.values()]

    def kind(self, name: str) -> str | None:
        s = self.specs.get(name)
        return s.kind if s else None

    def call(self, name: str, raw_args: str | dict | None) -> ToolResult:
        """Synchronous; the loop runs it in a thread with a timeout."""
        t0 = time.monotonic()

        def done(ok: bool, payload: Any, status: str = "ok") -> ToolResult:
            spec = self.specs.get(name)
            content, truncated = shrink(payload, spec.max_chars if spec else DEFAULT_MAX_CHARS)
            full = _dump(payload)
            return ToolResult(ok=ok, content=content, full=full[:LOG_MAX_CHARS], truncated=truncated,
                              ms=int((time.monotonic() - t0) * 1000), status=status, data=payload)

        spec = self.specs.get(name)
        if spec is None:
            return done(False, {"error": "unknown_tool", "detail": f"no tool named {name!r} in this mode"}, "error")
        try:
            args = raw_args if isinstance(raw_args, dict) else json.loads(raw_args or "{}")
            if not isinstance(args, dict):
                raise ValueError("arguments must be a JSON object")
        except ValueError as e:
            return done(False, {"error": "invalid_json", "detail": str(e)[:200]}, "error")
        try:
            parsed = spec.model.model_validate(args)
        except ValidationError as e:
            return done(False, {"error": "invalid_arguments",
                                "detail": [{"loc": list(x["loc"]), "msg": x["msg"]} for x in e.errors()][:10]},
                        "error")
        try:
            result = spec.fn(**parsed.model_dump(exclude_unset=True))
        except Exception as e:  # noqa: BLE001 — a tool failure goes back to the model, not up the stack
            return done(False, {"error": "tool_failed", "detail": f"{type(e).__name__}: {e}"[:500]}, "error")
        blocked = isinstance(result, dict) and result.get("blocked") is True
        failed = isinstance(result, dict) and result.get("ok") is False
        return done(not (blocked or failed), result, "blocked" if blocked else "error" if failed else "ok")
