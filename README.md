# TokenScope

Token usage and cost analytics for Claude Code. TokenScope parses the transcript
files Claude Code already writes to `~/.claude/projects/**/*.jsonl`, stores them
in a local SQLite database, and shows what you used — by day, by month, by exact
model, and by project — together with a **virtual cost** in USD.

Everything runs on your machine. Nothing is uploaded anywhere.

Three ways to use it, installable together or separately:

- **Claude Code plugin** — MCP tools plus a `/tokenscope` command, so you can ask
  "how many tokens did I burn this month?" in the middle of a session.
- **MCP server** — 18 tools Claude can call directly, if you want the data
  without the slash command.
- **Web dashboard** — FastAPI + React on `localhost:8787`, the full visual
  interface with charts, per-model tables and a subscription break-even panel.

---

## Table of contents

- [Why this exists](#why-this-exists)
- [Install](#install)
- [What "virtual cost" means](#what-virtual-cost-means)
- [The dashboard](#the-dashboard)
- [MCP tools](#mcp-tools)
- [The `/tokenscope` skill](#the-tokenscope-skill)
- [Model granularity and pricing](#model-granularity-and-pricing)
- [Subscription savings](#subscription-savings)
- [Project scope mode](#project-scope-mode)
- [How projects are folded](#how-projects-are-folded)
- [Data, config and privacy](#data-config-and-privacy)
- [Accuracy and limits](#accuracy-and-limits)
- [Development](#development)
- [Troubleshooting](#troubleshooting)

---

## Why this exists

If you are on a Claude subscription (Pro or Max), your Claude Code usage is a
black box. The plan bills a flat monthly fee, so the Console shows you no
per-token numbers. You find out you are near a limit when you hit one.

That leaves three questions unanswered:

1. **How much am I actually using?** Per day, per month, in tokens and in
   equivalent dollars.
2. **Where is it going?** Which project, which model, which time period. When a
   day's quota vanishes into one runaway debugging loop, you want to be able to
   see that.
3. **Is the plan worth it?** You are paying a fixed fee. What would the same
   usage have cost at API list price?

TokenScope answers all three from data that is already on your disk.

It is built on the same technical approach as `ccusage`,
`Claude-Code-Usage-Monitor`, `ccflare` and others — parse the local JSONL — and
adds per-model cost breakdown, project folding, and subscription break-even
analysis on top.

---

## Install

**Prerequisite:** [uv](https://docs.astral.sh/uv/), which provides `uvx`.

### Option 1 — Claude Code plugin (recommended)

```bash
claude plugin marketplace add kk-fenglai/Token
claude plugin install tokenscope@tokenscope
```

This installs both the MCP server and the `/tokenscope` skill. After it lands:

```
/tokenscope              # last 30 days report
/tokenscope today        # today only
/tokenscope month        # calendar month to date
/tokenscope projects     # per-project table
/tokenscope this         # what has THIS project cost
/tokenscope savings      # is my subscription worth it
/tokenscope models       # exact per-model breakdown
/tokenscope dashboard    # launch and open the web UI
/tokenscope pricing      # show or edit the rate table
```

Or just ask in plain language — "which project is burning the most money?",
"open the usage dashboard for this project", "is my Max plan paying for itself?"

### Option 2 — MCP server only

```bash
claude mcp add tokenscope -s user -- uvx --from git+https://github.com/kk-fenglai/Token@v1.1.0 tokenscope-mcp
```

`-s user` is the right scope: TokenScope reports **your** usage across every
project, so it belongs at the user level rather than pinned to one repo. Use
`-s project` only if you deliberately want the `.mcp.json` committed to a shared
repo — each collaborator would then see their own account's usage, not the
project's combined usage.

### Option 3 — dashboard only

```bash
uvx --from git+https://github.com/kk-fenglai/Token@v1.1.0 tokenscope-web
# then open http://127.0.0.1:8787
```

### First run

Two things are slow exactly once:

- **uvx cold start** builds a virtual environment on the spot (10–60 s), then
  caches it. If Claude Code reports an MCP startup timeout, run the `uvx`
  command manually once to warm the cache, or raise `MCP_TIMEOUT`.
- **The initial sync** parses your entire transcript history — roughly 10
  seconds per 200 files. Every sync after that is incremental.

The MCP server initialises lazily, on the first tool call rather than at
startup, precisely so that the initial sync cannot trip the host's startup
timeout.

---

## What "virtual cost" means

Every dollar figure in TokenScope is a **virtual cost**: what the tokens would
have cost at API list price, computed from an editable rate file.

If you are on a subscription, this is **not a bill**. You pay a flat monthly
fee; no per-token charge exists. The number is useful for two things only:

- comparing projects and models against each other, and
- judging whether the plan is worth its fee.

If you are on pay-as-you-go API billing, the same number *is* your real bill,
and TokenScope says so instead (`comparable: false` everywhere the distinction
matters).

The UI never mixes the two framings.

---

## The dashboard

`localhost:8787`, four pages.

### Dashboard

- **Four summary cards** — tokens and virtual cost, today and this month, with
  request counts.
- **Subscription savings panel** — see [below](#subscription-savings).
- **Usage trend** — 30 days daily or 12 months monthly. Stacked bars for the
  four token types, virtual cost as a line on the right axis. Click the legend
  to toggle a series.
- **Model split by family** — donut, switchable between token share and cost
  share. The two differ sharply: Opus costs roughly 5× Sonnet.
- **Top 10 projects this month** — horizontal bars, click through to detail.
- **Calls and cost per model** — a table at exact model ID granularity
  (`claude-opus-5` vs `claude-opus-4-8`, not just "Opus") with call count, token
  split, the unit rates applied, average cost per call, total cost and cost
  share. Click a model name to filter Usage Logs to it.

### Usage Logs

One row per assistant message: timestamp, exact model, project, the four token
counts, virtual cost. Filter by date range, model family, exact model, or a
substring of project name / session ID / message ID. Export the filtered set to
CSV.

### Project Costs

A card per project with tokens, virtual cost, a 30-day sparkline, and **today's
figures shown regardless of the selected range** — so a 30-day view still tells
you what is burning right now. The header summarises the range total plus
today's total and how many projects are active today.

### Tokens & Pricing

A built-in explainer covering what a token is, how the four token types arise in
a single Claude Code turn, why prompt caching exists, and how billing works.
Section three uses **your own data** to make the key point: on a typical
machine, cache reads are the overwhelming majority of tokens but a minority of
cost, while output tokens are a rounding error by volume and a large share of
spend. Judging usage by token count alone is badly misleading.

The UI is available in **Chinese, English and French**. It picks your browser
language on first open; the switcher is in the top right and the choice is
remembered in `localStorage`.

---

## MCP tools

18 tools. Read tools marked ⓟ accept a `project=` argument to narrow the answer
to one project (pass a project path or any session directory under it).

| Tool | What it returns |
|---|---|
| `get_summary` ⓟ | Today and month-to-date cards: tokens by type, cost by family, event counts, plus sync status |
| `get_trend` ⓟ | Time series, `day` (1–366 days) or `month` (1–36 months) |
| `get_models_distribution` ⓟ | Breakdown two ways: `items` by family, `models` by exact model ID with rates and per-call average |
| `get_projects_top` | Top N projects by virtual cost |
| `get_projects` | All projects with tokens, cost, sessions, last active, 30-day sparkline, and today's figures |
| `get_project_detail` | One project, all time: month-over-month delta, average cost per event, per-model table |
| `get_project_share` | One project **this month** vs the account and vs the plan fee |
| `query_logs` ⓟ | Paginated per-request log, newest first |
| `sync_now` | Rescan transcripts immediately (incremental) |
| `get_sync_status` | Last sync time, files seen/parsed, event count, parse errors, missing scan roots |
| `get_pricing` | Current rate document |
| `update_pricing` | Replace the rate document (full replace — see the warning below) |
| `get_subscription_savings` | Detected plan, this month's savings, month-by-month cumulative timeline |
| `set_subscription` | Pin the plan and fee, or hand control back to auto-detection |
| `get_project_grouping` | Current folding rules and which cwds merged into each project |
| `set_project_alias` | Merge a renamed or moved folder into its new identity |
| `set_workspace_roots` | Replace the list of directories whose children are projects |
| `launch_dashboard` | Start the web UI and return its URL; optionally scoped to a project |

> **`update_pricing` is a full replace, not a merge.** Always call `get_pricing`
> first and carry the existing `models` section through unchanged unless you
> mean to change it — omitting it silently deletes your per-model rates.

---

## The `/tokenscope` skill

The skill is a set of instructions for Claude, not executable code. It tells
Claude which MCP tools to call for a given request and how to format the answer.
It therefore **cannot be installed on its own** — without the MCP server behind
it, every command fails. This is why the plugin bundles the two together.

Beyond formatting, the skill encodes the accounting rules that keep the output
honest — never calling a per-project cost a "saving", flagging months whose logs
have been pruned, warning before an operation that would delete custom rates.

---

## Model granularity and pricing

Every aggregate groups by **exact model ID**, not just the family. That is what
lets the dashboard tell you whether `claude-opus-5` or `claude-opus-4-8` is
responsible for your Opus spend. The family rollup is still available for the
donut chart.

`pricing.json` prices by family. Models in the same family share a rate unless
you override them individually with an optional `models` section. Overrides are
**partial** — any rate you leave out falls back to the family rate:

```json
{
  "last_verified": "2026-08-09",
  "unit": "usd_per_million_tokens",
  "families": {
    "fable":  { "input": 10.0, "output": 50.0, "cache_write": 12.5, "cache_read": 1.0 },
    "opus":   { "input": 5.0,  "output": 25.0, "cache_write": 6.25, "cache_read": 0.5 },
    "sonnet": { "input": 3.0,  "output": 15.0, "cache_write": 3.75, "cache_read": 0.3 },
    "haiku":  { "input": 1.0,  "output": 5.0,  "cache_write": 1.25, "cache_read": 0.1 },
    "other":  { "input": 3.0,  "output": 15.0, "cache_write": 3.75, "cache_read": 0.3 }
  },
  "models": {
    "claude-opus-4-8": { "input": 2.0, "output": 10.0 }
  }
}
```

Rates are applied **at query time**, not at ingest. Change a price and the whole
history is recomputed immediately — no re-parsing. Rows priced by an override
are tagged in the model table.

Rate lookup order: model override → family → the `other` family.

---

## Subscription savings

### Plan detection

The plan is detected automatically by reading `~/.claude.json` →
`oauthAccount`, specifically `organizationType` and
`organizationRateLimitTier`. That identifies Pro, Max 5x, Max 20x, Team, or
pay-as-you-go API billing.

Only those non-secret profile fields are read. TokenScope **never opens**
`~/.claude/.credentials.json`.

Detection is best-effort. If it is wrong, or your billing is unusual (annual
discount, multiple seats, a plan not listed), set it explicitly in the panel or
via `set_subscription`. A manual setting always wins and is stored in
`config.json` under `subscription`.

When a Max organisation reports a rate-limit tier the tool does not recognise,
it assumes the **cheaper** rung rather than the more expensive one — better to
understate the savings than to overstate them.

### What the panel shows

This month's API-equivalent cost against the fee, the net saving, how many times
over the fee has been earned back, break-even progress, an end-of-month
projection from the current burn rate, and a month-by-month bar chart with a
cumulative net-saving line.

### Two accounting rules worth knowing

These exist because the alternative would inflate the number:

- **Months before your subscription started do not count.** You were not paying
  a fee then, so nothing was saved. Their usage is still drawn on the chart for
  context, but excluded from totals — which keeps
  `total_saved = total_api_cost − total_fees` exactly true.
- **Months whose logs have been pruned are charged their full fee against $0 of
  usage.** Claude Code deletes transcripts after roughly 30 days. A gap in the
  data means "records deleted", not "no usage". Skipping those months would
  overstate savings, so they are counted the unfavourable way. The cumulative
  figure is therefore a **conservative floor**, and the UI reports how many
  months are affected (`months_missing_data`).

On pay-as-you-go API billing there is no fixed fee to beat: `comparable` is
false and no savings figure is shown at all.

---

## Project scope mode

By default the dashboard covers your whole account. Launch it from inside a
project directory with `--project` to pin every panel to that project:

```bash
cd /path/to/project
tokenscope-web --project           # bare flag = current directory
tokenscope-web --project ./sub     # or an explicit path
TOKENSCOPE_PROJECT=/path/... tokenscope-web
```

The path can be the project root or any session directory beneath it — both fold
to the same project. A path with no records shows an empty dashboard and says
so; it **never silently falls back** to account-wide data, which matters if you
are showing the screen to someone else.

The scope selector in the top bar switches at runtime and remembers your choice
in `localStorage`, but **the launch flag wins on first load** — starting from
inside a repo should show that repo regardless of what was picked last time.

When scoped, the subscription savings panel is replaced by a **project share**
card. A monthly fee buys the whole account, so "this project saved you $X" is
not a coherent statement. The coherent question is how much of the fee this
project consumed, and that is what the card shows: month-to-date cost, share of
the account's month, and percentage of the monthly fee (over 100% means this one
project already paid the plan back).

From a Claude Code session you can just say "open the dashboard for this
project" — Claude calls `launch_dashboard(project=<cwd>)`. Note that if a
dashboard is already running on the port, the existing instance is reused and
the scope is **not** applied; the tool reports this in `already_running`.

---

## How projects are folded

Claude Code records the directory each session **started in**, so a single
project shows up under many paths — `myapp`, `myapp/backend`,
`myapp/frontend/src`, and so on. Counting each as its own project makes the
attribution view useless.

TokenScope folds them at query time:

1. If a cwd sits under one of your `workspace_roots`, the project is the
   **first directory beneath that root**. Defaults include `~/Desktop`,
   `~/OneDrive/Desktop`, `~/Documents`, `~/code` and similar.
2. A cwd under **no** root keeps its full path. This is deliberate: otherwise a
   single session started in your home directory would swallow every project
   beneath it.
3. `project_aliases` are then applied, for folders that were renamed or moved.
   Old and new paths share no prefix, so no rule can merge them automatically.

Because folding happens at query time, the database always keeps the raw cwd.
Changing the config **retroactively** regroups all history with no re-parsing,
and each project still lists the original directories it merged in its `cwds`
field.

Edit `config.json` directly, or use the tools:

- `get_project_grouping` — current rules, and what merged into what
- `set_project_alias(source, target)` — merge a renamed project (empty `target`
  removes the alias)
- `set_workspace_roots(roots)` — replace the root list

If your code lives somewhere unusual — `D:\work`, say — adding it to
`workspace_roots` is usually the one piece of setup worth doing.

---

## Data, config and privacy

### What TokenScope reads

| Path | Why |
|---|---|
| `~/.claude/projects/**/*.jsonl` | The usage data itself: assistant messages with a `usage` block |
| `~/.claude.json` → `oauthAccount` | Plan detection only (org type, rate-limit tier, subscription start) |

It does **not** read `~/.claude/.credentials.json`, and it makes no network
requests. There is no telemetry.

Note what the transcript files contain: message IDs, timestamps, token counts,
model IDs, session IDs, and the working directory of each session. Directory
names may reveal client or project names, which matters if you screen-share the
dashboard.

### Where it writes

Runtime data lives in `%LOCALAPPDATA%\TokenScope\` on Windows, or
`~/.local/share/tokenscope/` on macOS and Linux. Override with
`TOKENSCOPE_DATA_DIR`.

This is **deliberately not** a cloud-synced folder — SQLite WAL and cloud sync
corrupt each other.

| File | Contents |
|---|---|
| `tokenscope.db` | The event store. **This is the only complete history** — Claude Code prunes its own logs after ~30 days. Back it up occasionally. |
| `config.json` | `scan_roots`, `port`, `sync_interval_seconds`, `workspace_roots`, `project_aliases`, `subscription` |
| `pricing.json` | Rates per family and optional per-model overrides |

`scan_roots` is a list; missing paths are skipped silently. On WSL2 you can add
`\\wsl$\Ubuntu\home\<user>\.claude\projects` alongside the Windows path.

The deduplication key is `message_id + request_id`, last write wins. Rescanning
the same files, or having two scan roots that overlap, is therefore safe.

---

## Accuracy and limits

- Daily totals cross-validate against
  [ccusage](https://github.com/ryoppippi/ccusage) within 2%.
- For the exact remaining headroom in the 5-hour window or the weekly cap, use
  Claude Code's built-in `/usage`. TokenScope's value is historical trend and
  attribution, not real-time quota.
- Only Claude Code usage is covered. Chats on claude.ai or the mobile apps leave
  no local transcript and cannot be counted.
- History is bounded by what Claude Code kept. Raising `cleanupPeriodDays` in
  your Claude Code settings prevents gaps if you go a while without opening it.
- Rates go stale when Anthropic changes prices. `pricing.json` carries a
  `last_verified` date and is editable; edits apply retroactively.

---

## Development

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m pytest tests -q

.\scripts\start.ps1   # production mode, single process on :8787
.\scripts\dev.ps1     # dev mode: uvicorn --reload + vite dev server
```

Requires Python 3.10+. Runtime dependencies are FastAPI, uvicorn, pydantic and
the MCP SDK. The frontend is React 18 + TypeScript + Vite + Tailwind + Recharts.

### Frontend

The build output is committed to git and ships inside the wheel as package data,
so after changing anything under `frontend/` you must rebuild **and commit the
result**:

```powershell
cd frontend; npm run build   # writes to src/tokenscope/static/
```

Forgetting this ships a wheel whose dashboard 404s.

### Adding UI text

`frontend/src/i18n/zh.ts` is the canonical dictionary. `en.ts` and `fr.ts` are
typed against its shape, so a missing or misspelled key fails the build rather
than silently falling back. At runtime, lookup degrades Chinese → English → the
raw key, so a gap never renders as blank.

Product names are intentionally left untranslated in all three locales — model
families (Opus, Sonnet, Haiku, Fable) and token types (Input, Output, Cache
Write, Cache Read) are API field names, and translating them only makes it
harder to compare the UI against raw logs.

### Releasing

Keep three version strings in sync — `pyproject.toml`,
`src/tokenscope/__init__.py`, `.claude-plugin/plugin.json` — and tag the commit.
Point install URLs at the tag rather than a bare branch, so users are not
exposed to whatever is currently on `main`.

---

## Troubleshooting

**MCP server times out on startup.** The first `uvx` run builds an environment
from scratch. Warm it by running the command manually once, or raise
`MCP_TIMEOUT`.

**The dashboard is empty.** Check `get_sync_status`. If `last_sync_at` is null,
run `sync_now`. If `missing_roots` is non-empty, the configured scan paths do
not exist on this machine.

**A project appears several times.** Its directory is not under any
`workspace_roots` entry, so the fold rule does not apply. Add the parent
directory with `set_workspace_roots`. If the folder was renamed, use
`set_project_alias` instead — renamed paths share no prefix and cannot be merged
by any rule.

**Costs look wrong after an Anthropic price change.** Edit `pricing.json` (or
use `update_pricing`) — the change applies to all history immediately.

**Cumulative savings look lower than expected.** Check
`months_missing_data`. Months whose transcripts Claude Code has already pruned
are counted as $0 of usage against a full monthly fee, which drags the total
down on purpose. The real figure is higher.

**New MCP tools do not appear.** Restart the Claude Code session — tool lists
are read at connection time.

---

MIT licensed.
