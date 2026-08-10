"""Project identity — folding session cwds into one project.

Claude Code records the exact directory each session started in, so one project
arrives as several cwds: `<project>`, `<project>/backend`,
`<project>/frontend/src`. Each cwd is folded to the first directory under
whichever configured workspace root contains it, then run through the alias map
— needed for folders that were renamed or moved, whose old and new paths share
no prefix and so cannot be merged by any rule.

Folding happens at query time (like pricing): `events` keeps the raw cwd, so
editing config.json regroups all history retroactively and drill-down to the
original directories stays possible.
"""
from __future__ import annotations

from .config import load_config
from .parser import normalize_cwd, project_name


class Folder:
    """Folds cwds to project keys. Build one per query — it snapshots config."""

    def __init__(self, cfg: dict | None = None) -> None:
        cfg = cfg if cfg is not None else load_config()
        roots = cfg.get("workspace_roots") or []
        # Longest first: `~/OneDrive/Desktop` must win over `~/OneDrive`.
        self.roots = sorted(
            {normalize_cwd(str(r)) for r in roots if isinstance(r, str) and r.strip()},
            key=len, reverse=True,
        )
        raw_aliases = cfg.get("project_aliases") or {}
        self.aliases = (
            {normalize_cwd(k): normalize_cwd(v)
             for k, v in raw_aliases.items() if isinstance(v, str) and v.strip()}
            if isinstance(raw_aliases, dict) else {}
        )

    def fold(self, cwd: str) -> str:
        path = normalize_cwd(cwd)
        # An alias on the raw cwd is the most specific instruction there is.
        if path in self.aliases:
            return self.aliases[path]
        key = path
        low = path.lower()
        for root in self.roots:
            rl = root.lower()
            if low == rl or low.startswith(rl + "/"):
                rest = path[len(root):].strip("/")
                key = f"{root}/{rest.split('/')[0]}" if rest else root
                break
        return self.aliases.get(key, key)

    def name(self, key: str) -> str:
        return project_name(key)
