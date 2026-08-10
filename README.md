# TokenScope

Claude Code Token 消耗分析工具 —— 解析本机 `~/.claude/projects/**/*.jsonl` 入库 SQLite,
按日/月/模型/项目展示用量与**虚拟成本**(等效 API 价——套餐实际为固定月费,该数字仅用于衡量性价比)。

Token usage & cost analytics for Claude Code: an MCP server (ask Claude about
your usage in natural language), a `/tokenscope` skill, and a local web dashboard.
All data stays on your machine.

两种使用方式,可同时安装:

- **Claude Code 插件**(MCP 工具 + `/tokenscope` 命令)——直接在会话里问「我这个月用了多少 token / 哪个项目最烧钱」
- **Web 看板**(FastAPI + React,`localhost:8787`)——完整可视化界面

## 安装(其他用户)

前置:已安装 [uv](https://docs.astral.sh/uv/)(提供 `uvx`)。

### 方式一:Claude Code 插件(推荐)

```bash
claude plugin marketplace add SM3712_sunmi/tokenscope
claude plugin install tokenscope@tokenscope
```

装完在 Claude Code 里即可:

- `/tokenscope`、`/tokenscope today`、`/tokenscope projects` —— 用量报告
- `/tokenscope dashboard` —— 启动并打开 Web 看板
- 或直接用自然语言问 token 消耗问题

### 方式二:只加 MCP 服务器

```bash
claude mcp add tokenscope -- uvx --from git+https://github.com/SM3712_sunmi/tokenscope tokenscope-mcp
```

### 方式三:只跑 Web 看板

```bash
uvx --from git+https://github.com/SM3712_sunmi/tokenscope tokenscope-web
# 然后打开 http://127.0.0.1:8787
```

> 首次通过 uvx 启动会现场构建虚拟环境(10–60 秒),之后有缓存。若 Claude Code
> 报 MCP 启动超时,可先手动跑一次上面的 `uvx` 命令预热,或调大 `MCP_TIMEOUT`。
> 首次同步会全量扫描历史日志(约 10 秒/200 文件),之后为增量同步。

## MCP 工具一览

`get_summary` · `get_trend` · `get_models_distribution` · `get_projects_top` ·
`get_projects` · `get_project_detail` · `query_logs` · `sync_now` ·
`get_sync_status` · `get_pricing` · `update_pricing` ·
`get_project_grouping` · `set_project_alias` · `set_workspace_roots` ·
`launch_dashboard`

## 数据与配置

运行时数据存放在 `%LOCALAPPDATA%\TokenScope\`(Windows)或
`~/.local/share/tokenscope/`(macOS/Linux),可用环境变量 `TOKENSCOPE_DATA_DIR` 覆盖。
**故意不放云同步目录**——SQLite WAL 与云同步会冲突。

| 文件 | 说明 |
|---|---|
| `tokenscope.db` | 事件库。**这是唯一完整历史**(Claude Code 默认约 30 天清理日志),建议偶尔备份 |
| `config.json` | `scan_roots`:要扫描的日志根目录列表(默认 `~/.claude/projects`);`port`:看板默认端口;`workspace_roots` / `project_aliases`:项目归并规则,见下节。WSL2 侧可给 `scan_roots` 加 `\\\\wsl$\\Ubuntu\\home\\<user>\\.claude\\projects`,不存在会自动跳过 |
| `pricing.json` | 各模型族单价($/Mtok),可直接编辑或用 `update_pricing` 工具修改,立即追溯生效 |

去重键为 `message_id + request_id`(最后写入覆盖),因此重复扫描、双根路径重叠都是安全的。

## 项目归并

Claude Code 记录的是每次会话**启动时所在的目录**,所以同一个项目会以多个 cwd 出现
(`myapp`、`myapp/backend`、`myapp/frontend/src`……)。TokenScope 在查询时把每个 cwd
折叠成一个项目:

1. 若 cwd 落在某个 `workspace_roots` 目录之下,取该根下的**第一层目录**作为项目
   (默认根包含 `~/Desktop`、`~/OneDrive/Desktop`、`~/Documents`、`~/code` 等);
   不在任何根之下的 cwd 保留完整路径,因此在家目录跑的会话不会吞掉所有项目。
2. 再套用 `project_aliases` 重写 —— 用于**文件夹改名或移动**的情况,新旧路径没有共同
   前缀,任何规则都自动合不了。

归并发生在查询时(和定价一样),库里始终保存原始 cwd,所以改配置会**追溯**重新分组,
无需重新解析,项目详情里的 `cwds` 字段仍可看到被合并的原始目录。

直接编辑 `config.json`,或者让 Claude 调 MCP 工具:

- `get_project_grouping` —— 看当前规则,以及每个项目合并了哪些 cwd
- `set_project_alias(source, target)` —— 合并改名前后的项目(`target` 传空串则删除别名)
- `set_workspace_roots(roots)` —— 替换 workspace 根列表

## 与官方数据的关系

- 日汇总与 [ccusage](https://github.com/ryoppippi/ccusage) 交叉验证误差 ≤2%
- 5 小时窗口/周上限的精确余量请用 Claude Code 内置 `/usage` 命令;本工具的价值在历史趋势与项目归因

## 开发

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m pytest tests -q

.\scripts\start.ps1   # 生产模式(单进程 :8787)
.\scripts\dev.ps1     # 开发模式(uvicorn --reload + vite dev)
```

前端改动后需重新构建并提交产物(它作为包数据随 wheel 分发):

```powershell
cd frontend; npm run build   # 输出到 src/tokenscope/static/
```

发版时保持三处版本一致:`pyproject.toml`、`src/tokenscope/__init__.py`、
`.claude-plugin/plugin.json`,并打对应 git tag。

## 提示

- 建议把 Claude Code 的 `cleanupPeriodDays` 调大,避免长期不开机时日志被清理而漏采
- 看板 UI 目前为中文
