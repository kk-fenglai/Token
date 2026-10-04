"""F29 tool registry: schemas, kinds, argument validation, result shrinking,
and the guard rails on the dev-project tools (real git repos)."""
import json
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from tokenscope import db, dev_projects
from tokenscope.agent import tools, tools_extra
from tokenscope.parser import normalize_cwd

HAS_GIT = shutil.which("git") is not None
needs_git = pytest.mark.skipif(not HAS_GIT, reason="git not installed")


def _walk(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def test_every_tool_has_a_kind_and_a_clean_schema():
    reg = tools.build_registry()
    assert set(reg) == set(tools.MCP_TOOLS) | set(tools.EXTRA_TOOLS)
    assert not (set(reg) & tools.EXCLUDED)
    for name, spec in reg.items():
        assert spec.kind in ("read", "write", "external"), name
        assert spec.description and len(spec.description) <= 1800, name
        p = spec.parameters
        assert p["type"] == "object" and p["additionalProperties"] is False, name
        for node in _walk(p):
            assert "anyOf" not in node and "title" not in node and "$ref" not in node, name
            assert node.get("type") != "null", name


def test_mcp_module_tools_are_all_classified():
    """A new @mcp.tool() must be consciously added to MCP_TOOLS or EXCLUDED."""
    from tokenscope import mcp_server
    import inspect
    src = inspect.getsource(mcp_server)
    decorated = set()
    lines = src.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == "@mcp.tool()":
            decorated.add(lines[i + 1].split("def ", 1)[1].split("(", 1)[0])
    assert decorated == set(tools.MCP_TOOLS) | tools.EXCLUDED


def test_side_effect_kinds():
    reg = tools.build_registry()
    external = {n for n, s in reg.items() if s.kind == "external"}
    write = {n for n, s in reg.items() if s.kind == "write"}
    assert external == {"publish_project", "push_github_description"}
    assert write == {"update_pricing", "set_subscription", "set_project_alias", "set_workspace_roots",
                     "save_project_meta"}
    assert "private" not in reg["publish_project"].parameters["properties"]  # always private


def test_toolset_filters_by_kind():
    ro = tools.ToolSet({"read"})
    names = {s["function"]["name"] for s in ro.schemas()}
    assert "get_summary" in names and "publish_project" not in names and "update_pricing" not in names
    assert ro.call("publish_project", {"path": "x", "commit_message": "y"}).status == "error"


def test_call_validates_arguments():
    ts = tools.ToolSet({"read"})
    r = ts.call("get_projects_top", '{"limit": "many"}')
    assert r.status == "error" and "invalid_arguments" in r.content
    r = ts.call("get_projects_top", '{"bogus": 1}')
    assert r.status == "error" and "invalid_arguments" in r.content
    r = ts.call("get_projects_top", "not json")
    assert r.status == "error" and "invalid_json" in r.content
    r = ts.call("get_projects_top", "[1, 2]")
    assert r.status == "error" and "invalid_json" in r.content


def test_shrink_truncates_the_longest_list_and_marks_it():
    obj = {"items": [{"n": i, "pad": "x" * 50} for i in range(500)], "meta": {"k": "v"}}
    text, truncated = tools.shrink(obj, 4000)
    assert truncated and len(text) <= 4000
    data = json.loads(text)
    assert data["meta"] == {"k": "v"} and data["_truncated"]["items"] == 500 and len(data["items"]) < 500
    small, t2 = tools.shrink({"a": 1}, 4000)
    assert small == '{"a":1}' and not t2
    blob, t3 = tools.shrink("y" * 10000, 100)
    assert t3 and blob.endswith("…[truncated]")


def test_tool_exceptions_become_results(monkeypatch):
    def boom() -> dict:
        """x"""
        raise RuntimeError("kaput")
    spec = tools._spec("boom", boom, "read")
    ts = tools.ToolSet({"read"})
    ts.specs = {"boom": spec}
    r = ts.call("boom", "{}")
    assert not r.ok and r.status == "error" and "kaput" in r.content


# --------------------------------------------------------------- git repos ----

def _git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("TOKENSCOPE_DATA_DIR", str(tmp_path / "data"))
    db.reset_conn()
    work, bare = tmp_path / "work", tmp_path / "remote.git"
    work.mkdir()
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True, capture_output=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(work)], check=True, capture_output=True)
    for k, v in (("user.email", "t@example.com"), ("user.name", "t"), ("commit.gpgsign", "false")):
        _git(work, "config", k, v)
    (work / "a.py").write_text("print(1)\n", encoding="utf-8")
    _git(work, "add", ".")
    _git(work, "commit", "-qm", "init")
    _git(work, "remote", "add", "origin", str(bare))
    _git(work, "push", "-qu", "origin", "main")
    key = normalize_cwd(str(work))
    monkeypatch.setattr(dev_projects, "snapshot", lambda *a, **k: {"items": [{
        "path": key, "name": "work", "sources": ["manual"], "pinned": False, "last_active": None}]})
    yield SimpleNamespace(dir=work, key=key, bare=bare)
    db.reset_conn()


@needs_git
def test_repo_changes_skip_secret_bodies(repo):
    (repo.dir / "a.py").write_text("print(2)\n", encoding="utf-8")
    (repo.dir / ".env").write_text("TOKEN=supersecret\n", encoding="utf-8")
    (repo.dir / "new.txt").write_text("hello", encoding="utf-8")
    _git(repo.dir, "add", "-f", ".env")  # a tracked secret is the dangerous case
    r = tools_extra.get_repo_changes(repo.key.replace("/", "\\"))  # Windows-style path is normalized
    assert "print(2)" in r["diff"] and "supersecret" not in r["diff"]
    assert r["sensitive_skipped"] == [".env"] and r["untracked"] == ["new.txt"]


@needs_git
def test_publish_project_blocks_secrets_and_pushes_otherwise(repo):
    (repo.dir / ".env").write_text("TOKEN=1", encoding="utf-8")
    r = tools_extra.publish_project(repo.key, "feat: add env")
    assert r["blocked"] and r["error"] == "unsafe_files" and r["sensitive"] == [".env"]
    assert tools_extra.publish_project(repo.key, "  ")["error"] == "bad_message"

    (repo.dir / ".env").unlink()
    (repo.dir / "b.py").write_text("x = 1\n", encoding="utf-8")
    r = tools_extra.publish_project(repo.key, "feat: add b")
    assert r["ok"] and r["action"] == "push"
    log = subprocess.run(["git", "-C", str(repo.bare), "log", "-1", "--format=%s", "main"],
                         capture_output=True, check=True).stdout.decode().strip()
    assert log == "feat: add b"
    assert tools_extra.publish_project(repo.key, "again")["error"] == "nothing_to_push"


@needs_git
def test_untracked_paths_are_refused(repo, tmp_path):
    with pytest.raises(Exception):
        tools_extra.get_repo_changes(str(tmp_path / "elsewhere"))
    r = tools_extra.publish_project(str(tmp_path / "elsewhere"), "x")
    assert r == {"ok": False, "error": "not_tracked"}


@needs_git
def test_save_project_meta_is_partial(repo):
    assert tools_extra.save_project_meta(repo.key)["error"] == "nothing_to_update"
    r = tools_extra.save_project_meta(repo.key, alias="Work", tags=["cli"])
    assert r["ok"] and r["meta"]["alias"] == "Work"
    r = tools_extra.save_project_meta(repo.key, stage="paused")
    assert r["meta"]["alias"] == "Work" and r["meta"]["tags"] == ["cli"] and r["meta"]["stage"] == "paused"
    assert tools_extra.save_project_meta(repo.key, stage="done")["error"] == "invalid"
    assert tools_extra.push_github_description(repo.key)["error"] == "empty_description"
