---
name: tokenscope
description: Show Claude Code token usage & cost reports from the TokenScope MCP server. Use when the user asks about token consumption, usage costs, spend by project or model, whether their subscription is worth it, how much this project has cost, cache efficiency, or wants to open the TokenScope dashboard or edit pricing. Args: today | 7d | 30d | month | all | projects | this | savings | models | dashboard | pricing (default 30d).
---

# TokenScope usage report

All data comes from the `tokenscope` MCP server tools. Costs are **virtual
costs** in USD (equivalent API price computed from an editable pricing file) —
never present them as a real bill unless the user is on pay-as-you-go API
billing.

1. Parse the argument. Default: `30d`. Range vocabulary:
   `today | 7d | 30d | month | all`. Other verbs: `projects`, `this`,
   `savings`, `models`, `dashboard`, `pricing`.

2. **Range argument (today/7d/30d/month/all)** — call `get_summary`,
   `get_models_distribution(range)`, and `get_projects_top(range, limit=5)`.
   Render a compact markdown report:
   - Headline: total tokens and virtual cost for the range (from
     models_distribution totals; for `today`/`month` prefer the matching
     get_summary block which also has the input/output/cache split).
   - Token split: input / output / cache write / cache read.
   - Model table from `models` (exact model ids such as claude-opus-5 vs
     claude-opus-4-8), with calls, tokens, cost and cost_share. Use `items`
     (family rollup) only when the user explicitly wants families, or when
     there are so many models the table gets unwieldy. Point out when
     token_share and cost_share differ sharply.
   - Top 5 projects by cost.
   - If `get_summary().savings.comparable` is true, close with one line:
     saved `savings.saved` this month against the `savings.plan_label` fee.

3. **`projects`** — call `get_projects(range="30d")`; render a table sorted by
   cost: name, tokens, cost, events, sessions, last_active. Offer
   `get_project_detail(path)` for drill-down. Each project folds together every
   directory sessions were started in (its `cwds`); if the user says two
   projects are really one (usually a renamed folder), use
   `get_project_grouping` to find the exact paths and `set_project_alias` to
   merge them.

4. **`this`** (or "how much has this project cost") — call
   `get_project_share(project=<current working directory>)`. Report: this
   month's cost and tokens for the project, its share of the whole account's
   month, the per-model split, and `pct_of_fee` — the share of the monthly
   subscription fee this project alone consumed at API-equivalent price. Over
   100% means this project by itself already paid the plan back.
   **Never call this a per-project "saving"**: one fee covers the entire
   account, so savings only exist account-wide. If `comparable` is false the
   user is on pay-as-you-go API billing — there the cost IS this project's real
   bill, so say that instead.
   If `scope.known` is false, the directory has no records: say so and check
   whether the path is right rather than reporting zeros as fact.

5. **`savings`** (or "is my plan worth it") — call
   `get_subscription_savings()`. Report:
   - The plan and fee, and whether it was auto-detected from `~/.claude.json`
     or pinned manually (`subscription.source`).
   - This month: API-equivalent cost vs fee, net saving, and `multiple`
     ("earned the fee back N times over").
   - `timeline.total_saved` across `timeline.paid_months` subscribed months.
   - If `timeline.months_missing_data > 0`, state plainly that those months
     have no transcripts left (Claude Code prunes after ~30 days) and are
     counted as $0 of usage against a full fee, so the cumulative figure is a
     **conservative floor**, not an estimate of the true total.
   - If `comparable` is false, there is no fixed fee to compare against — do
     not invent a saving. Offer `set_subscription` if the plan looks wrong.

6. **`models`** — call `get_models_distribution(range="30d")` and render the
   `models` array: model id, calls, tokens, the unit rates applied, average
   cost per call, cost, cost_share. Note any model whose `priced_by` is
   `"model"` — it has its own rate rather than the family rate.

7. **`dashboard`** — call `launch_dashboard()`. If the user is asking about the
   current project ("open the dashboard for this project"), pass
   `project=<current working directory>` so every panel opens scoped to it.
   Give the user the returned URL. The UI is available in Chinese, English and
   French — it picks the browser language on first open and there is a switcher
   in the top right. If `already_running` is true, the existing dashboard was
   reused and any `project` you passed was **not** applied — say so rather than
   claiming it opened scoped. If `warning` is present, say it may need a few
   more seconds.

8. **`pricing`** — call `get_pricing()` and show the rates table (USD per
   million tokens). To change rates: `update_pricing` is a **full replace**, so
   build the COMPLETE document — all 5 families x 4 rates with unchanged values
   preserved, **and carry over the existing `models` section verbatim** unless
   the user asked to change it. Dropping `models` silently deletes their
   per-model rates. On `{ok: false}` show the errors instead of retrying
   blindly.

Notes:
- If `get_sync_status` / the `sync` block shows `last_sync_at` is null or
  stale (>10 min old), call `sync_now` first.
- Most read tools (`get_summary`, `get_trend`, `get_models_distribution`,
  `query_logs`) accept `project=` to narrow the answer to one project — pass a
  project path or any session directory under it. Note that `get_summary`'s
  `savings` block stays account-wide even when scoped.
- Format token counts with thousands separators (1,234,567) and costs as
  `$X.XX` (two decimals; use more only for sub-cent values).
- If `missing_roots` is non-empty, tell the user which scan roots don't exist
  (config lives at the path in `get_summary().sync`, typically
  `%LOCALAPPDATA%\TokenScope\config.json` on Windows,
  `~/.local/share/tokenscope/config.json` elsewhere).
