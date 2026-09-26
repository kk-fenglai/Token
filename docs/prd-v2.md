# TokenScope — 产品需求文档 v2(从「记账」到「省钱」)

| 字段 | 内容 |
|---|---|
| 文档版本 | v2.1 |
| 日期 | 2026-09-26 |
| 作者 | Davin |
| 状态 | v1.3 已实现(本文档与实现同步写就) |
| 关联文档 | `tokenscope-prd-v1.md`(v1 / v1.1 需求,F1–F16)、`tokenscope/README.md`(用户文档) |
| 对应版本 | tokenscope 1.3.0 |

---

## 0. 修订记录

**v2.1(2026-09-26)** — 新增 F26 开发项目追踪与 GitHub 推送提醒,随 1.3.0 交付。起因:同时开发多个本地仓库时经常 commit 之后忘记 push;TokenScope 已经从会话日志知道「最近在哪些目录工作」,顺手把 git 状态也看一眼。

**v2.0(2026-09-12)** — 新增 F17–F25 九个功能点,全部在本次迭代中实现并随 1.2.0 交付。

v1 交付后的看板能准确回答「花了多少」(F1–F16),但回答不了「为什么花了这么多」和「下次怎么少花」。本次评审归纳了六个改进方向,本文档把它们落成需求,并记录实现时的取舍:

1. 从「花了多少」到「为什么花」:会话级下钻、上下文增长曲线、工具归因(F18、F19)
2. 主动提醒而不是被动看图:异常波动与失控会话提醒(F20)
3. 堵住数据缺口:自动同步、留存提示、定价时效(F24)
4. 效率指标:缓存命中率、每千 output 成本、时段热力图(F21、F22)
5. 分享与对账:周报(F23);与官方用量 API 对账列为未做,见 §8
6. 工程层面:多币种显示、路由级代码拆分、汇率快照标注(F17、F25)

v1 的目标(G1–G4)、非目标与场景(S1–S4)不变;新增场景 S5、S6(§3)。

---

## 1. 背景与问题

v1 的查询层把每条 assistant 消息压成四个 token 计数,所有面板都是这四个数字在时间、模型、项目三个维度上的聚合。这足以算账,但丢掉了日志里最有解释力的三样东西:

- **会话结构。** `session_id` 已入库,却没有任何按会话聚合的视图;一个月 1.2 万条调用明细,找不到「是哪一次对话跑飞了」。
- **上下文规模。** 每一轮的 `input + cache_write + cache_read` 就是那一轮实际发出去的上下文长度。它只增不减,直到 `/clear`。不看它,就不知道长会话里的钱是怎么随轮次膨胀的。
- **工具与子代理。** `tool_use` 块记录了每一轮是在 Read、Bash 还是 Agent;`subagents/*.jsonl` 记录了子代理的独立消耗。v1 的解析器把这些全部丢弃。

此外还有两类「隐性失真」:
- 日志缺口。Claude Code 默认 30 天清理本地日志,若这期间没打开过看板,那个月就永久缺失(作者机器上 5 月、6 月已空)。
- 定价漂移。`pricing.json` 有 `last_verified` 但界面从不提示,Anthropic 调价后所有金额静默失真。

---

## 2. 目标与非目标

### 2.1 目标(在 v1 G1–G4 之上)

- **G5 可解释。** 对任何一天的异常消耗,两次点击内定位到具体会话和具体轮次。
- **G6 可行动。** 看板主动指出「该 /clear 了」「缓存没命中」「日志快被清理了」,而不是等用户自己发现。
- **G7 可分享。** 一周的消耗可以一键变成一段 Markdown 发到群里。

### 2.2 非目标

- 不做实时配额监控(5 小时窗口 / 周上限精确剩余量仍以 Claude Code 自带 `/usage` 为准,同 v1)。
- 不联网拉取汇率或价格;所有换算只用本地快照或用户手填的值(隐私立场同 v1:数据不出本机)。
- 不对账官方用量 API(需要 Admin API key,且个人订阅账号拿不到),列为 v2.1 候选,见 §8。

---

## 3. 用户与场景

在 v1 的 S1–S4 之外新增:

- **S5 事后追责。** 「今天怎么花了三倍?」→ 总览页顶部的提醒直接指向那个会话 → 会话详情页看到上下文在第 40 轮之后翻了三倍,且都是同一个文件被反复 Read。
- **S6 周会汇报。** 团队周会要一句话说清本周 AI 支出:打开「洞察与周报」,复制 Markdown,贴进群。

---

## 4. 功能需求

### 4.1 面板总览

| # | 面板 | 优先级 | 状态 |
|---|---|---|---|
| F17 | 多币种显示(USD / GBP / EUR / CNY) | P1 | 已交付 |
| F18 | 会话分析:列表 + 逐轮详情 + 上下文增长曲线 | P0 | 已交付(完成 v1 F10 的会话层) |
| F19 | 工具归因与子代理占比 | P0 | 已交付 |
| F20 | 异常提醒 | P0 | 已交付 |
| F21 | 缓存效率指标 | P1 | 已交付(即 v1 F8) |
| F22 | 时段热力图 | P2 | 已交付(即 v1 F9) |
| F23 | 周报 | P1 | 已交付 |
| F24 | 数据留存保障与定价时效 | P0 | 已交付 |
| F25 | 工程改进:路由级代码拆分、汇率快照标注 | P2 | 已交付 |
| F26 | 开发项目追踪与 GitHub 推送提醒 | P1 | 已交付(1.3.0) |

### 4.2 F17 — 多币种显示

顶栏新增货币下拉框:`$ USD` / `£ GBP` / `€ EUR` / `¥ CNY`。选择非美元货币后出现汇率按钮,可手动修改,回车或失焦生效,可一键恢复默认。

规则:
- **底层永远是美元。** 定价表与套餐月费都以美元计,后端不参与换算;前端在渲染时乘以汇率。自定义月费输入仍按美元填写,提示文案明确写 USD。
- 所有硬编码的 `$` 文案改为占位符,由代码传入已带符号的金额;「单价 $/Mtok」表头随货币变化。
- 选择与汇率存于浏览器 localStorage,不联网。
- 默认汇率是快照(`RATES_AS_OF` 常量,当前 2026-09-12),弹层里注明取样日期(F25)。

验收:切换到人民币后,总览、明细、账单、项目、说明五个页面无残留 `$`;控制台无报错。

### 4.3 F18 — 会话分析

**列表页(/sessions)。** 一行一个会话:项目、开始时间、时长、消息数、模型、工具调用次数、峰值上下文、虚拟成本、子代理占比。支持范围切换(今日 / 7 天 / 30 天 / 本月 / 全部)、按开始时间或成本排序、按项目名或会话 ID 搜索,分页 50 条。按时间排序时插入「日期分隔行」(当天会话数与合计),完成 v1 F10 规划的「日期 → 会话 → 消息」三层结构。峰值上下文 ≥ 150K 的行标红。

**详情页(/sessions/detail)。** 四张指标卡(成本 / 消息数与时长 / 峰值上下文及出现轮次 / 工具调用与 token 总量);**上下文随轮次增长图**:折线 = 每轮发送的上下文,柱 = 该轮成本,红点 = 峰值;本会话的工具分布;逐轮明细表(轮次、时间、模型、上下文、output、工具、本轮成本、累计成本),子代理轮次带标签,峰值行高亮。上限 5000 轮,超过时提示截断。

定义:
- 上下文 = `input + cache_write + cache_read`(该轮实际发送的提示词总量)。
- 子代理消息(`subagents/agent-*.jsonl`,`isSidechain: true`)带父会话的 `sessionId`,自动并入父会话。

验收:作者机器上 7 天内会话列表在 300 ms 内返回;任一会话详情的累计成本与列表中的成本一致(误差 < $0.001,由测试保证)。

### 4.4 F19 — 工具归因与子代理占比

「洞察」页的工具表:每个工具的调用次数、涉及消息数、output token、成本与占比,外加「纯文本回复」一行。

**成本口径(必须在界面上写明):** 一个工具的成本 = 调用它的那轮 assistant 消息的成本;一轮并行调多个工具时平均分摊。这是「决定用它并写出参数」的成本,不含工具结果被读入后续轮次的开销 —— 后者已经体现在下一轮的 input / cache_write 里,无法无歧义地归到某个工具头上,所以不做。

子代理:按 `attributionAgent`(Explore、general-purpose 等)拆分事件数与成本,给出子代理占总成本的比例。

验收:工具成本之和 + 纯文本成本 = 范围内总成本(测试保证)。

### 4.5 F20 — 异常提醒

`/api/alerts` 返回按紧急度排序的提醒列表,每条含 `kind`、`level`(danger / warn / info)与 `params`。前端负责文案(三语)与金额换算(F17)。总览页顶部只显示 warn 与 danger,没有时**不显示任何东西**(常驻「一切正常」是噪音);「洞察」页显示全部。

| kind | 触发条件 | 级别 |
|---|---|---|
| daily_spike | 今日成本 ≥ 近 30 天有用量日的中位数 × 2(× 4 升级为 danger),且今日 ≥ $1、历史 ≥ 5 天 | warn / danger |
| week_pace | 近 7 天成本较前 7 天变化 ≥ 30% | 上升 warn,下降 info |
| runaway_session | 今日成本 ≥ $5,且单个会话占 ≥ 40%(今日不止一个会话) | warn,带会话链接 |
| context_bloat | 近 24 小时内有会话峰值上下文 ≥ 150K tokens | warn,带会话链接 |
| cache_efficiency | 本月缓存命中率 < 70%(提示词 ≥ 100 万 token 才评估) | warn |
| subagent_share | 本月子代理成本占比 ≥ 30% | info |
| pricing_stale | 定价表 `last_verified` 距今 > 90 天或缺失 | warn |
| retention | 有订阅月日志缺失(warn),或 `cleanupPeriodDays` ≤ 30(info) | warn / info |

阈值是「值得看一眼」的粗标尺,不是监控系统;写死在 `insights.py` 顶部常量里,不做配置项(避免用户先要调阈值再能用)。

### 4.6 F21 — 缓存效率(v1 F8)

三个数:
- 缓存命中率 = `cache_read ÷ (input + cache_write + cache_read)`
- 缓存省下 = Σ 各模型 `cache_read × (input 单价 − cache_read 单价) ÷ 10⁶`(按模型各自的单价,含 pricing.json 的按模型覆盖)
- 每千 output token 成本 = 成本 ÷ (output ÷ 1000)

出现位置:总览页「本月 Token 总量」卡片备注;「洞察」页本月效率卡;项目成本页每张项目卡;项目详情页独立区块;周报。命中率 < 70% 以橙色标示。

按 v1 Q3 的结论,这里的「省下」与 F13 的「订阅节省」是两个不同的「省」,全部文案使用「缓存省下」措辞,不进入 F13 面板。

### 4.7 F22 — 时段热力图(v1 F9)

7 × 24 矩阵(本地时间,周一起行),颜色深浅 = 该时段近 30 天虚拟成本;悬停显示成本、token、调用数;下方标出高峰时段。纯 DOM 网格实现,不用图表库(168 个格子用 SVG 散点既慢又糊)。

### 4.8 F23 — 周报

周一到周日一周的摘要,与上周对比:成本 / 会话 / 调用 / token 及各自的环比;逐日成本;最忙的一天与高峰时段;项目 Top 5;模型 Top 5;最贵的 5 个会话(可点进详情);工具 Top 5;子代理占比;缓存效率;月初至今的订阅节省(仅账户级且可对比时)。

交付形式:
- 「洞察」页周报卡:本周 / 上周 / 2 周前 / 3 周前切换,左侧指标,右侧 Markdown 预览,「复制 Markdown」与「下载 .md」。
- `GET /api/report/weekly`(JSON + markdown 字段)与 `GET /api/report/weekly.md`(直接下载)。
- MCP 工具 `get_weekly_report(weeks_ago, project, lang)`。
- Markdown 有中、英两套模板;法语界面使用英文模板(法语 Markdown 的翻译成本高于其价值,见 §8)。

### 4.9 F24 — 数据留存保障与定价时效

**自动同步。** 新增 `tokenscope-sync` 命令行入口(一次增量同步后退出,失败返回码 1)。三条路径让它在看板没打开时也跑:
1. 插件 `hooks/hooks.json`:SessionStart(startup | resume)时后台执行 `tokenscope-sync --quiet`,超时 120 s。
2. `scripts/install-autosync.ps1`:注册 Windows 计划任务(每日 09:00 + 登录时);`-Remove` 卸载。
3. `scripts/install-autosync.sh`:macOS / Linux 的 cron 条目。

**留存信息。** `GET /api/retention` 读取 `~/.claude/settings.json` 的 `cleanupPeriodDays`(默认 30,标注是否自定义)、上次同步时间、建议值 365,以及定价时效。「洞察」页有专门的「数据留存」卡片,说明两步防丢做法。

**定价时效。** `GET /api/pricing/status` 返回 `last_verified` 距今天数与 `stale`(> 90 天)。「Token 与计费说明」页第 ④ 节顶部显示核对日期,过期时红底提示;同时进入 F20 提醒。

**解析器版本。** `PARSER_VERSION` 常量随抽取规则变化递增;同步时若与 `meta.parser_version` 不一致,忽略文件缓存、全部重解析一次,让还留在磁盘上的历史补上新字段。已被清理的日志无法补齐,新字段留空。

### 4.10 F25 — 工程改进

- **路由级代码拆分。** 每个页面 `React.lazy`,`recharts` 与 `react` 各成独立 chunk;首屏只加载框架与当前页。构建产物从单个 708 kB 拆为 react / recharts / 各页面若干个文件。
- **汇率快照标注。** 见 F17。
- **版本。** 1.2.0;`.mcp.json` 与 `hooks.json` 指向 `@v1.2.0` 标签,**发布时必须打该标签**,否则插件安装失败。

### 4.11 F26 — 开发项目追踪与 GitHub 推送提醒

**问题。** 本机同时有六七个仓库在开发,commit 之后忘记 push 是常态;要等到换机器或者丢盘才发现代码只在本地。

**做什么。** 侧栏新增「开发项目」页,列出正在开发的本地 git 仓库和「还有什么没到 GitHub」;warn / danger 级别同时进入 F20 的提醒体系(总览页 AlertStrip、`get_alerts`),并在 Windows 上弹桌面通知。

**哪些仓库算「正在开发」。** 三者取并集,减去 `ignored`:
1. 近 `active_days`(默认 14)天有 Claude Code 会话的项目目录,按 F13 的折叠规则归并后,再向下找到最近的 `.git`(`Token消耗量/tokenscope/frontend` 里的会话追踪 `tokenscope` 仓库);
2. `workspace_roots` 直接子目录中含 `.git` 的目录;
3. 手动 `extra`。`pinned` 置顶。

**检查什么。** 每个仓库一次 `git status --porcelain=v2 --branch -z --untracked-files=normal`,加 `remote get-url`、`log -1 --format=%ct`、仅在领先时 `log --format=%ct @{upstream}..HEAD`(最后一行 = 最早未推送提交)。并行 8 路,60 秒缓存。**全部离线**:不 fetch、不写仓库(`GIT_OPTIONAL_LOCKS=0`)、不弹凭据提示(`GIT_TERMINAL_PROMPT=0`)。

**分级。**

| 情形 | 级别 | reason |
|---|---|---|
| 领先上游 N 个提交 | warn | `unpushed` |
| …且最早未推送提交超过 `unpushed_danger_hours`(24) | danger | `unpushed_stale` |
| 有未提交改动,最新改动文件 mtime 超过 `dirty_warn_hours`(24) | warn | `dirty_stale` |
| 有未提交改动但仍在编辑 | ok(显示不提醒) | `dirty_fresh` |
| 无远程 / 远程非 GitHub / 分支无上游 / 分离 HEAD | info | `no_remote` / `not_github` / `no_upstream` / `detached` |

**提醒。** 提醒种类 `git_unpushed`(warn/danger)、`git_dirty`(warn)、`git_no_remote`(info),params 带 `name / path / ahead / changes / hours`,AlertRow 对 `path` 渲染「查看项目」链接。桌面通知由 web 进程的同步循环触发(`tokenscope-sync` CLI 不触发),把当天尚未提醒过的 warn/danger 项目合并为**一条** toast,成功后在 `meta` 表记 `notify:dev:<path>` = 日期;每项目每天最多一次,失败不消耗当天名额。实现:Windows PowerShell 5.1 的 WinRT `ToastNotificationManager`,文案走环境变量、脚本走 `-EncodedCommand`,不做任何 shell 拼接;失败回退 `NotifyIcon` 气泡;非 Windows 静默返回。

**配置。** `config.json` → `dev_projects: {extra, ignored, pinned, active_days, unpushed_danger_hours, dirty_warn_hours, desktop_notify}`,页面内可改。

**非目标。** 不自动 push、不 fetch、不管理 GitHub 认证。

### 4.12 横切要求(在 v1 §4.5 基础上)

- **提醒文案的换算。** 提醒的 `params` 是裸数字;前端按键名决定格式:`today / median / this / prev / cost` 走货币换算,`ctx_max` 走 token 缩写,`delta_pct` 带符号。新增提醒种类时同步维护这张映射。
- **三语。** 新增 alerts / sessions / sessionDetail / insights 四个字典区块,中文为准,英法由类型系统校验(缺键即构建失败,同 v1)。
- **范围边界。** 跨越范围边界的会话只统计范围内的部分,列表页脚注写明。

---

## 5. 技术方案

### 5.1 数据层

`events` 表新增四列(`db.MIGRATIONS`,启动时 `ALTER TABLE` 补齐,幂等):

| 列 | 含义 |
|---|---|
| `tool_names TEXT` | 该消息 `tool_use` 块的工具名 JSON 列表,如 `["Read","Bash"]`;无则 NULL |
| `tool_count INTEGER` | 上述列表长度 |
| `is_sidechain INTEGER` | `isSidechain: true` 或文件路径含 `/subagents/` |
| `agent_name TEXT` | `attributionAgent`(Explore、general-purpose…) |

解析器 `PARSER_VERSION = 2`。元组末尾追加四个字段,前 13 位不变,v1 测试不受影响。

### 5.2 查询层

新模块 `insights.py`(`queries.py` 回答「多少」,它回答「在哪、为什么」):

- `sessions()` / `session_detail()`:按 `(session_id, model, family, is_sidechain)` 分组一次查询,Python 侧合并;详情按 `ts, id` 取前 5000 条。
- `tools_breakdown()`:按事件行拉取,Python 侧解析 `tool_names` 并分摊成本。
- `heatmap()`:`strftime('%w' / '%H', ts, 'localtime')` 分组。
- `alerts()`:组合上述查询与 `queries.savings_report()`。
- `weekly_report()` + `render_weekly_markdown()`。
- `pricing_status()` / `retention_info()`。

`queries.py` 增加 `efficiency_of()`,挂在 `_block`(总览 / 分享 / 周报)与 `_merge_projects`(项目列表 / 详情)的返回值上。

### 5.3 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/alerts?project=` | F20 |
| GET | `/api/sessions?range=&from=&to=&project=&q=&sort=&page=&page_size=` | F18 列表 |
| GET | `/api/sessions/detail?id=` | F18 详情 |
| GET | `/api/tools?range=&project=` | F19 |
| GET | `/api/heatmap?range=&project=` | F22 |
| GET | `/api/report/weekly?week=&lang=&project=` | F23(JSON + markdown) |
| GET | `/api/report/weekly.md?week=&lang=&project=` | F23(下载) |
| GET | `/api/retention` | F24 |
| GET | `/api/pricing/status` | F24 |
| GET | `/api/dev-projects` | F26 快照(60 s 缓存) |
| POST | `/api/dev-projects/refresh` | F26 强制重查 |
| GET / PUT | `/api/dev-projects/config` | F26 配置(PUT 为部分更新,422 校验) |
| POST | `/api/dev-projects/notify-test` | F26 发一条测试 toast |
| POST | `/api/dev-projects/notify-now` | F26 立即跑一遍提醒(遵守每日去重) |
| POST | `/api/dev-projects/open` | F26 在资源管理器打开(仅限快照内的路径) |

### 5.4 MCP 工具(v2.0 新增 7 个;v2.1 新增 `get_dev_projects`,共 26 个)

`get_sessions`、`get_session_detail`(超过 300 轮时等距采样并标注 `sampled_every`)、`get_tools_breakdown`、`get_heatmap`、`get_alerts`、`get_weekly_report`、`get_retention_status`。工具描述里写明成本口径与「不要把子代理/工具成本说成节省」等表述规则,与 v1 skill 的诚实性约束一致。

### 5.5 前端

新页面:`Sessions`、`SessionDetail`、`Insights`,v2.1 新增 `DevProjects`;新组件:`AlertStrip`(含可复用的 `AlertRow`)、`ToolsTable`、`Heatmap`、`ContextChart`;`format.formatDuration`。侧栏新增「会话分析」「洞察与周报」。

---

## 6. 里程碑与状态

| 项 | 状态 |
|---|---|
| F17 多币种 | 已交付(2026-09-12) |
| F18–F25 | 已交付(2026-09-12),后端 46 个测试通过,前端类型检查与构建通过 |
| 打标签 v1.2.0 并推送 | **待做**(插件 / hook 依赖该标签) |
| README、SKILL.md 更新 | 已更新(与代码一起待提交) |
| F26 开发项目追踪 | 已交付(2026-09-26),后端 78 个测试通过,前端构建通过 |
| 打标签 v1.3.0 并推送,`.mcp.json` / `hooks.json` 改为 `@v1.3.0` | **待做** |

---

## 7. 成功指标(在 v1 M1–M6 之上)

- **M7** 从总览页的任一 warn 级提醒到对应会话详情页 ≤ 2 次点击。
- **M8** 启用自动同步后,连续 90 天无「日志缺失」月份。
- **M9** 周报 Markdown 粘贴到任意 Markdown 渲染器(GitHub / 飞书 / Slack)表格不乱。

---

## 8. 风险与未决问题

**R7 工具成本口径可能被误读。** 「Read 花了 $X」容易被理解为读文件本身贵。缓解:表格副标题与 MCP 工具描述都写明是「决定用它那一轮的成本」;不提供「含下游」口径,因为无法无歧义分摊。

**R8 阈值写死。** 重度用户可能天天触发 daily_spike。先观察一个版本再决定是否开放配置。

**R9 SessionStart 钩子的首次延迟。** `uvx` 首次解析 git 依赖可能超过 10 s;之后有缓存。超时设为 120 s,且钩子失败不影响 Claude Code 使用。

**R10 OneDrive 中的仓库。** 按需文件可能让 `git status` 先下载再比较,15 s 超时兜底并显示为 `git_error`;用户可忽略该仓库。`GIT_OPTIONAL_LOCKS=0` 避免每 5 分钟重写 `.git/index` 触发同步。

**R11 桌面通知依赖 Windows PowerShell 5.1。** pwsh 7 没有 WinRT 投影;专注助手可能静默压制。站内提醒是最终依据。

**Q5 是否联网拉汇率?** 倾向不做:与「数据不出本机」的承诺冲突,且手填一次即可。已在弹层标注快照日期。

**Q6 与官方用量 API 对账(v2.1 候选)。** Admin API 仅对组织账号开放,个人 Pro / Max 无法调用;若做,只能作为可选配置项。在此之前,「虚拟成本」的可信度背书仍是与 ccusage 的 2% 交叉验证。

**Q7 周报要不要法语模板?** 暂不做;法语界面用英文 Markdown。若有法语用户反馈再补。

**Q8 5 小时窗口 / 周上限(v1 F5–F7)。** 本次仍未做。F20 的 week_pace 用「环比」替代「对上限的进度」,因为各档位的周上限没有公开的 token 数值,估出来的数字可信度不够放进提醒。
