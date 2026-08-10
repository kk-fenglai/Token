---
name: tokenscope
description: Show Claude Code token usage & cost reports from the TokenScope MCP server. Use when the user asks about token consumption, usage costs, spend by project or model, cache efficiency, or wants to open the TokenScope dashboard or edit pricing. Args: today | 7d | 30d | month | all | projects | dashboard | pricing (default 30d).
---

# TokenScope usage report

All data comes from the `tokenscope` MCP server tools. Costs are **virtual
costs** in USD (equivalent API price computed from an editable pricing file) —
never present them as a real bill.

1. Parse the argument. Default: `30d`. Range vocabulary: `today | 7d | 30d | month | all`.

2. **Range argument (today/7d/30d/month/all)** — call `get_summary`,
   `get_models_distribution(range)`, and `get_projects_top(range, limit=5)`.
   Render a compact markdown report:
   - Headline: total tokens and virtual cost for the range (from
     models_distribution totals; for `today`/`month` prefer the matching
     get_summary block which also has the input/output/cache split).
   - Token split: input / output / cache write / cache read.
   - Model table: family, tokens, cost, token_share vs cost_share (point out
     when the two differ sharply).
   - Top 5 projects by cost.

3. **`projects`** — call `get_projects(range="30d")`; render a table sorted by
   cost: name, tokens, cost, events, sessions, last_active. Offer
   `get_project_detail(path)` for drill-down.

4. **`dashboard`** — call `launch_dashboard()`; give the user the returned URL
   (note the UI is in Chinese). If `warning` is present, say it may need a few
   more seconds.

5. **`pricing`** — call `get_pricing()` and show the rates table (USD per
   million tokens). If the user wants changes, build the COMPLETE document
   (all 5 families x 4 rates, keep unchanged values) and call
   `update_pricing`; on `{ok: false}` show the errors instead of retrying
   blindly.

Notes:
- If `get_sync_status` / the `sync` block shows `last_sync_at` is null or
  stale (>10 min old), call `sync_now` first.
- Format token counts with thousands separators (1,234,567) and costs as
  `$X.XX` (two decimals; use more only for sub-cent values).
- If `missing_roots` is non-empty, tell the user which scan roots don't exist
  (config lives at the path in `get_summary().sync`, typically
  `%LOCALAPPDATA%\TokenScope\config.json` on Windows,
  `~/.local/share/tokenscope/config.json` elsewhere).
