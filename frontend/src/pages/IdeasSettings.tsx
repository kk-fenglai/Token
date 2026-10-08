import { useEffect, useState } from "react";
import { useApi } from "../api/useApi";
import { api, dateTime, errorText, type SyncConfig, type SyncStatus } from "../lib/ideas";

const NUM_FIELDS: { key: keyof SyncConfig; label: string; hint: string }[] = [
  { key: "min_mrr", label: "MRR 下限($)", hint: "列表同步只拉这个区间的产品" },
  { key: "max_mrr", label: "MRR 上限($)", hint: "$1k–$20k 是个人做得动的区间" },
  { key: "sync_hours", label: "同步间隔(小时)", hint: "TrustMRR 每小时更新,每天一次足够" },
  { key: "max_requests", label: "每次最多请求数", hint: "标准 Key 10 次/分钟,120 次约 12 分钟" },
  { key: "max_details", label: "每次最多拉详情", hint: "感兴趣和已归簇的产品优先" },
  { key: "rate_per_minute", label: "每分钟请求上限", hint: "标准 Key 10,高级 Key 60" },
];

export default function IdeasSettings() {
  const status = useApi<SyncStatus>("/api/ideas/sync");
  const [form, setForm] = useState<SyncConfig | null>(null);
  const [key, setKey] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const s = status.data;

  useEffect(() => { if (s && !form) setForm(s.config); }, [s, form]);

  // Poll while a run is going so progress and the result show up.
  useEffect(() => {
    if (!s?.running) return;
    const t = setTimeout(status.retry, 3000);
    return () => clearTimeout(t);
  }, [s, status.retry]);

  const flash = (m: string) => { setMsg(m); setTimeout(() => setMsg(null), 2000); };
  const run = async (fn: () => Promise<unknown>, ok: string) => {
    setError(null);
    try { await fn(); flash(ok); status.retry(); } catch (e) { setError(errorText(e)); }
  };

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-base font-semibold">数据源</h3>
        <p className="mt-0.5 max-w-3xl text-xs text-on-surface-variant">
          只用 TrustMRR 官方接口,不抓网页。没有 API Key 时每天拉一次公开发现接口(最近新增 25 个 + 30 天增长最快 25 个);
          配置个人 Key 后按 MRR 区间翻页同步,断点续传。数据只存在本机 TokenScope 数据库里,不对外展示。
        </p>
      </div>
      {msg && <div className="rounded bg-success-container px-3 py-2 text-sm text-on-success-container">{msg}</div>}
      {error && <div className="rounded bg-error-container px-3 py-2 text-sm text-on-error-container">{error}</div>}

      <section className="rounded border border-border-card bg-surface-card p-4 shadow-card">
        <h4 className="mb-2 text-sm font-semibold">TrustMRR API Key</h4>
        <div className="text-sm text-on-surface-variant">
          {s ? (s.key.configured ? `已配置 ${s.key.masked}(${s.key.source === "env" ? "来自环境变量 TRUSTMRR_API_KEY" : "本机加密保存"})` : "未配置") : "…"}
        </div>
        <div className="mt-2 flex flex-wrap gap-2">
          <input type="password" value={key} onChange={(e) => setKey(e.target.value)} placeholder="tmrr_…"
            className="w-80 rounded border border-border-card bg-surface px-3 py-1.5 font-mono text-sm" />
          <button onClick={() => run(async () => { await api("/key", "PUT", { key }); setKey(""); }, "已保存")}
            className="rounded bg-primary-container px-3 py-1.5 text-sm font-semibold text-on-primary">保存</button>
          {s?.key.source === "stored" && (
            <button onClick={() => run(() => api("/key", "DELETE"), "已删除")} className="rounded border border-border-card px-3 py-1.5 text-sm">删除</button>
          )}
          <a href="https://trustmrr.com/docs/api" target="_blank" rel="noreferrer noopener" className="self-center text-xs text-primary hover:underline">去 TrustMRR 申请 Key</a>
        </div>
        <p className="mt-2 text-xs text-outline">在 Windows 上用 DPAPI 加密,只有当前用户能解开;Key 归个人所有,不要共享。</p>
      </section>

      {form && (
        <section className="rounded border border-border-card bg-surface-card p-4 shadow-card">
          <h4 className="mb-3 text-sm font-semibold">同步设置</h4>
          <div className="grid gap-4 md:grid-cols-3">
            {NUM_FIELDS.map((f) => (
              <label key={f.key} className="text-sm">
                <span className="block text-xs font-semibold text-on-surface-variant">{f.label}</span>
                <input type="number" min={0} value={form[f.key] as number}
                  onChange={(e) => setForm({ ...form, [f.key]: Math.max(0, parseInt(e.target.value || "0", 10)) })}
                  className="mt-1 w-full rounded border border-border-card bg-surface px-3 py-1.5 font-mono text-sm" />
                <span className="text-xs text-outline">{f.hint}</span>
              </label>
            ))}
          </div>
          <div className="mt-4 flex items-center justify-between">
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={form.auto_sync} onChange={(e) => setForm({ ...form, auto_sync: e.target.checked })} />
              TokenScope 运行时自动同步
            </label>
            <button onClick={() => run(() => api("/settings", "PUT", form), "已保存")}
              className="rounded bg-primary-container px-3 py-1.5 text-sm font-semibold text-on-primary">保存设置</button>
          </div>
        </section>
      )}

      <section className="rounded border border-border-card bg-surface-card p-4 shadow-card">
        <div className="mb-3 flex items-center justify-between">
          <h4 className="text-sm font-semibold">同步记录</h4>
          <button onClick={() => run(() => api("/sync", "POST"), "已开始同步")} disabled={s?.running}
            className="flex items-center gap-1 rounded bg-primary-container px-3 py-1.5 text-sm font-semibold text-on-primary disabled:opacity-60">
            <span className={`material-symbols-outlined text-[18px] ${s?.running ? "animate-spin" : ""}`}>sync</span>
            {s?.running ? "同步中…" : "立即同步"}
          </button>
        </div>
        {s?.running && (
          <div className="mb-3 text-sm text-primary">
            正在{s.phase === "discovery" ? "拉公开发现接口" : s.phase === "list" ? `翻列表第 ${s.page} 页${s.total ? `(共 ${s.total} 个产品)` : ""}` : s.phase === "detail" ? `拉详情:${s.slug}` : "准备"}
          </div>
        )}
        <div className="mb-2 text-xs text-on-surface-variant">
          列表游标:第 {s?.cursor_page ?? "…"} 页 · 上次完整扫完:{s?.last_full_sweep ? dateTime(s.last_full_sweep) : "还没有"}
        </div>
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-on-surface-variant">
            <tr><th className="py-1">开始</th><th>方式</th><th className="text-right">请求</th><th className="text-right">产品</th><th className="text-right">详情</th><th className="pl-4">结果</th></tr>
          </thead>
          <tbody>
            {s?.runs.length === 0 && <tr><td colSpan={6} className="py-3 text-center text-on-surface-variant">还没同步过。</td></tr>}
            {s?.runs.map((r) => (
              <tr key={r.id} className="border-t border-border-card">
                <td className="py-1.5">{dateTime(r.started_at)}</td>
                <td>{r.mode === "api" ? "认证 API" : "公开发现接口"}</td>
                <td className="text-right font-mono">{r.requests}</td>
                <td className="text-right font-mono">{r.products}</td>
                <td className="text-right font-mono">{r.details}</td>
                <td className={`pl-4 ${r.status === "ok" ? "text-success" : r.status === "error" ? "text-error" : "text-primary"}`}>
                  {r.status === "ok" ? "成功" : r.status === "error" ? `失败:${r.error}` : "进行中"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="rounded border border-border-card bg-surface p-4 text-xs leading-5 text-on-surface-variant">
        <div className="mb-1 font-semibold">使用边界(TrustMRR 服务条款第 9 节,私人研究)</div>
        可以:用认证 API 拉数据到本机研究;在本机筛选、标注、归簇、写卡片;对外讲自己的结论并附原页面链接。<br />
        不能:抓取网页;把这个工具部署到公网或给别人用;对外发指标截图、批量导出或转载数据;共享 Key。<br />
        AI 功能未接入:把 TrustMRR 数据送进大模型是否允许还没确认,确认前不做。
      </section>
    </div>
  );
}
