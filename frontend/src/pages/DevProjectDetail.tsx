import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import type { DevProjectDetail as Detail, DevProjectMeta } from "../api/types";
import { useApi } from "../api/useApi";
import PublishDialog from "../components/PublishDialog";
import StatCard from "../components/StatCard";
import { useI18n } from "../i18n";
import { useMoney } from "../lib/currency";
import { LEVEL_BADGE, canPublish, postJson, putConfig, reasonText } from "../lib/devProjects";
import { formatLocalTime, formatRelative, formatTokens } from "../lib/format";
import { Markdown } from "../lib/markdown";

// Categorical slots 1–5 of the validated reference palette (light mode); the
// remainder folds into a neutral "Other". Colors are low-contrast against the
// card, so the legend always carries the name and share as text.
const LANG_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"];
const OTHER_COLOR = "#a3a29a";
const TOP_LANGS = LANG_COLORS.length;

type Form = Pick<DevProjectMeta, "alias" | "description" | "tags" | "stage" | "notes">;

export default function DevProjectDetail() {
  const { t, tag } = useI18n();
  const { money } = useMoney();
  const navigate = useNavigate();
  const [sp] = useSearchParams();
  const path = sp.get("path") ?? "";
  const detail = useApi<Detail>(path ? `/api/dev-projects/detail?path=${encodeURIComponent(path)}` : null);
  const d = detail.data;

  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<Form | null>(null);
  const [tagInput, setTagInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [publishing, setPublishing] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);
  const [ghState, setGhState] = useState<"idle" | "busy" | "ok" | "failed">("idle");
  const [readmeOpen, setReadmeOpen] = useState(false);
  const [hoverLang, setHoverLang] = useState<string | null>(null);

  const rel = (iso: string | null | undefined) =>
    formatRelative(iso, tag, { never: t("common.never"), justNow: t("common.justNow") });

  useEffect(() => {
    if (d && !editing) {
      const m = d.meta;
      setForm({ alias: m.alias, description: m.description, tags: m.tags, stage: m.stage, notes: m.notes });
    }
  }, [d, editing]);

  function note(msg: string) {
    setFlash(msg);
    setTimeout(() => setFlash(null), 2500);
  }

  async function save() {
    if (!form || !d) return;
    setSaving(true);
    setSaveError(null);
    try {
      const pending = tagInput.trim();
      const tags = pending && !form.tags.includes(pending) ? [...form.tags, pending] : form.tags;
      const res = await fetch("/api/dev-projects/meta", {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: d.item.path, ...form, tags }),
      });
      if (!res.ok) {
        const json = await res.json().catch(() => null);
        const detailMsg = json?.detail?.detail;
        throw new Error(Array.isArray(detailMsg) ? detailMsg.join("; ") : `HTTP ${res.status}`);
      }
      setTagInput("");
      setEditing(false);
      detail.retry();
      note(t("devDetail.saved"));
    } catch (e) {
      setSaveError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  function addTag() {
    const v = tagInput.trim().replace(/^#/, "");
    if (!form || !v) return;
    if (!form.tags.some((x) => x.toLowerCase() === v.toLowerCase())) setForm({ ...form, tags: [...form.tags, v] });
    setTagInput("");
  }

  async function action(url: string, okMsg?: string) {
    if (!d) return;
    const res = await postJson(url, { path: d.item.path }).catch(() => null);
    if (res?.ok) { if (okMsg) note(okMsg); } else note(t("devDetail.actionFailed"));
  }

  async function togglePin() {
    if (!d) return;
    const cfg = await fetch("/api/dev-projects/config").then((r) => r.json());
    const pinned: string[] = cfg.pinned ?? [];
    await putConfig({ pinned: d.item.pinned ? pinned.filter((x) => x !== d.item.path) : [...pinned, d.item.path] });
    detail.retry();
  }

  async function ignore() {
    if (!d) return;
    const cfg = await fetch("/api/dev-projects/config").then((r) => r.json());
    await putConfig({ ignored: [...(cfg.ignored ?? []), d.item.path] });
    navigate("/dev-projects");
  }

  async function syncGithub() {
    if (!d) return;
    setGhState("busy");
    const res = await postJson("/api/dev-projects/github-description", { path: d.item.path, description: d.meta.description }).catch(() => null);
    const json = res?.ok ? await res.json() : null;
    setGhState(json?.ok ? "ok" : "failed");
    setTimeout(() => setGhState("idle"), 3000);
  }

  if (!path) return <Empty text={t("devDetail.noPath")} />;

  const crumb = (
    <nav className="flex items-center gap-2 text-sm text-on-surface-variant">
      <Link to="/dev-projects" className="hover:text-primary-container hover:underline">{t("devProjects.title")}</Link>
      <span className="material-symbols-outlined text-base">chevron_right</span>
      <span className="text-on-surface">{d ? d.meta.alias || d.item.name : "…"}</span>
    </nav>
  );

  if (detail.error) {
    return (
      <div className="space-y-6">
        {crumb}
        <div className="flex h-48 flex-col items-center justify-center gap-3 rounded border border-border-card bg-surface-card text-sm text-on-surface-variant">
          <span>{detail.error.includes("404") ? t("devDetail.notTracked") : t("common.loadFailed", { error: detail.error })}</span>
          <button onClick={detail.retry} className="rounded border border-primary-container px-3 py-1.5 text-primary-container">{t("common.retry")}</button>
        </div>
      </div>
    );
  }
  if (!d || !form) return <div className="space-y-6">{crumb}<Empty text={t("common.loading")} /></div>;

  const p = d.item;
  const m = d.meta;
  const b = LEVEL_BADGE[p.level];
  const autoSummary = d.readme?.summary || d.manifest?.description || null;
  const langs = d.languages.slice(0, TOP_LANGS);
  const otherPct = Math.round(d.languages.slice(TOP_LANGS).reduce((s, l) => s + l.pct, 0) * 10) / 10;
  const bars = [...langs.map((l, i) => ({ ...l, color: LANG_COLORS[i] })),
    ...(otherPct > 0 ? [{ name: t("devDetail.otherLang"), pct: otherPct, bytes: 0, color: OTHER_COLOR }] : [])];

  return (
    <div className="space-y-6">
      {crumb}

      {/* ---------------------------------------------------------- header */}
      <section className="rounded border border-border-card bg-surface-card p-5 shadow-card">
        <div className="flex flex-wrap items-start justify-between gap-4 lg:flex-nowrap">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              {p.pinned && <span className="material-symbols-outlined text-[22px] text-primary-container">push_pin</span>}
              <h3 className="text-2xl font-bold">{m.alias || p.name}</h3>
              {m.alias && <span className="text-sm text-outline">{p.name}</span>}
              <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${b.cls}`}>
                <span className="material-symbols-outlined text-[14px]">{b.icon}</span>{t(`devProjects.status.${p.level}`)}
              </span>
              {m.stage && (
                <span className="rounded-full border border-border-card px-2 py-0.5 text-[11px] text-on-surface-variant">{t(`devDetail.stages.${m.stage}`)}</span>
              )}
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-on-surface-variant">
              <span className="flex min-w-0 items-center gap-1 break-all font-mono"><span className="material-symbols-outlined text-base">folder</span>{p.path}</span>
              {p.branch && <span className="flex items-center gap-1 font-mono"><span className="material-symbols-outlined text-base">call_split</span>{p.branch}</span>}
              {p.github_url && (
                <a href={p.github_url} target="_blank" rel="noreferrer" className="flex items-center gap-1 font-mono text-primary-container hover:underline">
                  <span className="material-symbols-outlined text-base">link</span>{p.github_url.replace("https://", "")}
                </a>
              )}
            </div>
            {(m.tags.length > 0 || p.reasons.length > 0) && (
              <div className="mt-2 flex flex-wrap gap-1">
                {m.tags.map((tg) => <span key={tg} className="rounded bg-primary-container/10 px-2 py-0.5 text-xs text-primary-container">#{tg}</span>)}
                {p.reasons.map((r) => <span key={r} className="rounded bg-surface px-2 py-0.5 text-xs text-on-surface-variant">{reasonText(t, p, r)}</span>)}
              </div>
            )}
          </div>

          <div className="flex shrink-0 flex-wrap items-center gap-2">
            {canPublish(p) && (
              <button onClick={() => setPublishing(true)}
                className="flex items-center gap-1 rounded bg-primary-container px-3 py-1.5 text-sm font-semibold text-on-primary hover:opacity-90">
                <span className="material-symbols-outlined text-[18px]">cloud_upload</span>{t("devProjects.publish.button")}
              </button>
            )}
            <button onClick={() => setEditing((e) => !e)}
              className={`flex items-center gap-1 rounded border px-3 py-1.5 text-sm ${editing ? "border-primary-container text-primary-container" : "border-border-card hover:bg-surface"}`}>
              <span className="material-symbols-outlined text-[18px]">edit</span>{t("devDetail.edit")}
            </button>
            {d.editor && (
              <IconBtn icon="code" label={t("devDetail.openEditor")} onClick={() => action("/api/dev-projects/open-editor", t("devDetail.opened"))} />
            )}
            <IconBtn icon="folder_open" label={t("devProjects.openFolder")} onClick={() => action("/api/dev-projects/open")} />
            <IconBtn icon={p.pinned ? "keep_off" : "push_pin"} label={p.pinned ? t("devProjects.unpin") : t("devProjects.pin")} onClick={togglePin} active={p.pinned} />
            <IconBtn icon="visibility_off" label={t("devProjects.ignore")} onClick={ignore} danger />
          </div>
        </div>
        {flash && <div className="mt-3 text-xs text-success">{flash}</div>}
      </section>

      {/* ------------------------------------------------------------ editor */}
      {editing && (
        <section className="rounded border border-primary-container/40 bg-surface-card p-5 shadow-card">
          <h4 className="mb-3 text-sm font-semibold">{t("devDetail.editTitle")}</h4>
          <div className="grid gap-4 md:grid-cols-2">
            <Labeled label={t("devDetail.alias")} hint={t("devDetail.aliasHint", { name: p.name })}>
              <input value={form.alias} maxLength={80} onChange={(e) => setForm({ ...form, alias: e.target.value })}
                placeholder={p.name} className="w-full rounded border border-border-card bg-surface px-3 py-1.5 text-sm" />
            </Labeled>
            <Labeled label={t("devDetail.stage")}>
              <select value={form.stage} onChange={(e) => setForm({ ...form, stage: e.target.value as Form["stage"] })}
                className="w-full rounded border border-border-card bg-surface px-3 py-1.5 text-sm">
                <option value="">{t("devDetail.stageNone")}</option>
                {d.stages.map((s) => <option key={s} value={s}>{t(`devDetail.stages.${s}`)}</option>)}
              </select>
            </Labeled>
            <div className="md:col-span-2">
              <Labeled label={t("devDetail.description")} hint={autoSummary ? t("devDetail.descriptionHint") : undefined}>
                <textarea value={form.description} maxLength={2000} rows={3} onChange={(e) => setForm({ ...form, description: e.target.value })}
                  placeholder={autoSummary ?? t("devDetail.descriptionPlaceholder")}
                  className="w-full rounded border border-border-card bg-surface px-3 py-1.5 text-sm" />
              </Labeled>
              {autoSummary && !form.description && (
                <button onClick={() => setForm({ ...form, description: autoSummary })} className="mt-1 text-xs text-primary-container hover:underline">
                  {t("devDetail.useReadme")}
                </button>
              )}
            </div>
            <div className="md:col-span-2">
              <Labeled label={t("devDetail.tags")} hint={t("devDetail.tagsHint")}>
                <div className="flex flex-wrap items-center gap-1 rounded border border-border-card bg-surface px-2 py-1">
                  {form.tags.map((tg) => (
                    <span key={tg} className="flex items-center gap-0.5 rounded bg-primary-container/10 px-2 py-0.5 text-xs text-primary-container">
                      #{tg}
                      <button onClick={() => setForm({ ...form, tags: form.tags.filter((x) => x !== tg) })} aria-label={t("devDetail.removeTag", { tag: tg })}
                        className="material-symbols-outlined text-[14px] hover:text-error">close</button>
                    </span>
                  ))}
                  <input value={tagInput} onChange={(e) => setTagInput(e.target.value)} maxLength={32}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === "," || e.key === "，") { e.preventDefault(); addTag(); }
                      else if (e.key === "Backspace" && !tagInput && form.tags.length) setForm({ ...form, tags: form.tags.slice(0, -1) });
                    }}
                    onBlur={addTag}
                    placeholder={form.tags.length >= 12 ? "" : t("devDetail.tagPlaceholder")} disabled={form.tags.length >= 12}
                    className="min-w-[120px] flex-1 bg-transparent px-1 py-0.5 text-sm outline-none" />
                </div>
              </Labeled>
              {d.stack.length > 0 && (
                <div className="mt-1 flex flex-wrap items-center gap-1 text-xs text-outline">
                  {t("devDetail.suggest")}
                  {d.stack.filter((s) => !form.tags.includes(s)).slice(0, 6).map((s) => (
                    <button key={s} onClick={() => setForm({ ...form, tags: [...form.tags, s].slice(0, 12) })}
                      className="rounded border border-border-card px-1.5 py-0.5 hover:border-primary-container hover:text-primary-container">+ {s}</button>
                  ))}
                </div>
              )}
            </div>
            <div className="md:col-span-2">
              <Labeled label={t("devDetail.notes")} hint={t("devDetail.notesHint")}>
                <textarea value={form.notes} rows={6} onChange={(e) => setForm({ ...form, notes: e.target.value })}
                  placeholder={t("devDetail.notesPlaceholder")}
                  className="w-full rounded border border-border-card bg-surface px-3 py-1.5 font-mono text-xs" />
              </Labeled>
            </div>
          </div>
          <div className="mt-4 flex items-center justify-end gap-2">
            {saveError && <span className="mr-auto text-xs text-error">{t("devDetail.saveFailed", { error: saveError })}</span>}
            <button onClick={() => { setEditing(false); setSaveError(null); setTagInput(""); }}
              className="rounded border border-border-card px-4 py-1.5 text-sm hover:bg-surface">{t("devProjects.publish.cancel")}</button>
            <button onClick={save} disabled={saving}
              className="rounded bg-primary-container px-4 py-1.5 text-sm font-semibold text-on-primary hover:opacity-90 disabled:opacity-60">
              {saving ? t("devDetail.saving") : t("devProjects.save")}
            </button>
          </div>
        </section>
      )}

      {/* ------------------------------------------------------------ stats */}
      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <StatCard label={t("devDetail.commits")} icon="commit" value={d.git.commit_count != null ? String(d.git.commit_count) : "—"}
          note={d.git.first_commit_at ? t("devDetail.since", { date: formatLocalTime(d.git.first_commit_at).slice(0, 10) }) : undefined} />
        <StatCard label={t("devDetail.files")} icon="description" value={String(d.git.file_count)}
          note={p.changes > 0 ? t("devDetail.uncommitted", { n: p.changes }) : t("devDetail.clean")} />
        <StatCard label={t("devDetail.sync")} icon="cloud_sync"
          value={!p.remote_url ? t("devDetail.noRemote") : !p.has_upstream ? t("devProjects.noUpstream") : `↑${p.ahead} ↓${p.behind}`}
          accent={p.ahead > 0 ? "text-error" : undefined}
          note={t("devDetail.lastCommit", { time: rel(p.last_commit_at) })} />
        <StatCard label={t("devDetail.tokenCost")} icon="payments" value={d.tokens ? money(d.tokens.cost) : "—"}
          note={d.tokens ? t("devDetail.tokenNote", { tokens: formatTokens(d.tokens.tokens), n: d.tokens.sessions }) : t("devDetail.noTokens")} />
      </div>

      <div className="grid gap-6 xl:grid-cols-3">
        {/* ------------------------------------------------------ main column */}
        <div className="space-y-6 xl:col-span-2">
          <Card title={t("devDetail.about")} icon="info"
            extra={p.is_github && m.description ? (
              <button onClick={syncGithub} disabled={ghState === "busy"} title={t("devDetail.syncGithubHint")}
                className="flex items-center gap-1 rounded border border-border-card px-2 py-1 text-xs hover:bg-surface disabled:opacity-60">
                <span className={`material-symbols-outlined text-[16px] ${ghState === "busy" ? "animate-spin" : ""}`}>{ghState === "busy" ? "progress_activity" : "sync"}</span>
                {ghState === "ok" ? t("devDetail.syncedGithub") : ghState === "failed" ? t("devDetail.syncGithubFailed") : t("devDetail.syncGithub")}
              </button>
            ) : undefined}>
            {m.description ? (
              <p className="whitespace-pre-wrap text-sm leading-relaxed">{m.description}</p>
            ) : autoSummary ? (
              <div>
                <p className="text-sm leading-relaxed">{autoSummary}</p>
                <p className="mt-2 text-xs text-outline">
                  {t("devDetail.autoFrom", { src: d.readme?.summary ? d.readme.file : d.manifest?.kind ?? "" })}
                  {" · "}
                  <button onClick={() => setEditing(true)} className="text-primary-container hover:underline">{t("devDetail.writeOwn")}</button>
                </p>
              </div>
            ) : (
              <p className="text-sm text-on-surface-variant">
                {t("devDetail.noDescription")}{" "}
                <button onClick={() => setEditing(true)} className="text-primary-container hover:underline">{t("devDetail.writeOwn")}</button>
              </p>
            )}
            {(d.stack.length > 0 || d.manifest?.version) && (
              <div className="mt-4 flex flex-wrap items-center gap-1.5">
                <span className="text-xs font-semibold uppercase tracking-wide text-on-surface-variant">{t("devDetail.stack")}</span>
                {d.stack.map((s) => <span key={s} className="rounded-full border border-border-card px-2 py-0.5 text-xs">{s}</span>)}
                {d.manifest?.version && <span className="rounded-full bg-surface px-2 py-0.5 font-mono text-xs text-on-surface-variant">v{d.manifest.version}</span>}
              </div>
            )}
          </Card>

          {m.notes && (
            <Card title={t("devDetail.notes")} icon="sticky_note_2">
              <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed">{m.notes}</pre>
            </Card>
          )}

          <Card title={d.readme ? d.readme.file : "README"} icon="menu_book"
            extra={d.readme && d.readme.content.length > 1500 ? (
              <button onClick={() => setReadmeOpen((o) => !o)} className="text-xs text-primary-container hover:underline">
                {readmeOpen ? t("devDetail.collapse") : t("devDetail.expand")}
              </button>
            ) : undefined}>
            {!d.readme ? (
              <p className="text-sm text-on-surface-variant">{t("devDetail.noReadme")}</p>
            ) : (
              <div className={`relative ${readmeOpen || d.readme.content.length <= 1500 ? "" : "max-h-[420px] overflow-hidden"}`}>
                {d.readme.markdown ? <Markdown source={d.readme.content} /> : <pre className="whitespace-pre-wrap text-xs">{d.readme.content}</pre>}
                {!readmeOpen && d.readme.content.length > 1500 && (
                  <div className="absolute inset-x-0 bottom-0 flex h-24 items-end justify-center bg-gradient-to-t from-surface-card to-transparent">
                    <button onClick={() => setReadmeOpen(true)} className="mb-1 rounded border border-border-card bg-surface-card px-3 py-1 text-xs hover:bg-surface">{t("devDetail.expand")}</button>
                  </div>
                )}
                {d.readme.truncated && readmeOpen && <p className="mt-2 text-xs text-outline">{t("devDetail.truncated")}</p>}
              </div>
            )}
          </Card>

          <Card title={t("devDetail.recentCommits")} icon="history">
            {d.git.recent_commits.length === 0 ? (
              <p className="text-sm text-on-surface-variant">{t("devDetail.noCommits")}</p>
            ) : (
              <ul className="divide-y divide-border-card/60">
                {d.git.recent_commits.map((c) => (
                  <li key={c.sha} className="flex items-baseline gap-3 py-1.5 text-sm">
                    {p.github_url
                      ? <a href={`${p.github_url}/commit/${c.sha}`} target="_blank" rel="noreferrer" className="font-mono text-xs text-primary-container hover:underline">{c.sha}</a>
                      : <span className="font-mono text-xs text-outline">{c.sha}</span>}
                    <span className="min-w-0 flex-1 truncate" title={c.subject}>{c.subject}</span>
                    <span className="shrink-0 text-xs text-on-surface-variant">{c.author}</span>
                    <span className="w-20 shrink-0 text-right text-xs text-outline">{rel(c.at)}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>

        {/* ------------------------------------------------------ side column */}
        <div className="space-y-6">
          <Card title={t("devDetail.languages")} icon="code_blocks">
            {bars.length === 0 ? (
              <p className="text-sm text-on-surface-variant">{t("devDetail.noLanguages")}</p>
            ) : (
              <>
                <div className="flex h-2.5 w-full gap-[2px] overflow-hidden rounded-full" role="img"
                  aria-label={bars.map((l) => `${l.name} ${l.pct}%`).join(", ")}>
                  {bars.map((l) => (
                    <div key={l.name} style={{ width: `${l.pct}%`, background: l.color, opacity: hoverLang && hoverLang !== l.name ? 0.35 : 1 }}
                      className="h-full min-w-[3px] transition-opacity" title={`${l.name} ${l.pct}%`}
                      onMouseEnter={() => setHoverLang(l.name)} onMouseLeave={() => setHoverLang(null)} />
                  ))}
                </div>
                <ul className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                  {bars.map((l) => (
                    <li key={l.name} className={`flex items-center gap-1.5 rounded px-1 ${hoverLang === l.name ? "bg-surface" : ""}`}
                      onMouseEnter={() => setHoverLang(l.name)} onMouseLeave={() => setHoverLang(null)}>
                      <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: l.color }} />
                      <span className="truncate">{l.name}</span>
                      <span className="ml-auto font-mono text-on-surface-variant">{l.pct}%</span>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </Card>

          <Card title={t("devDetail.tokenUsage")} icon="data_usage">
            {!d.tokens ? (
              <p className="text-sm text-on-surface-variant">{t("devDetail.noTokens")}</p>
            ) : (
              <div className="space-y-2 text-sm">
                <Row k={t("devDetail.totalTokens")} v={formatTokens(d.tokens.tokens)} />
                <Row k={t("devDetail.monthTokens")} v={formatTokens(d.tokens.month_tokens)} />
                <Row k={t("devDetail.totalCost")} v={money(d.tokens.cost)} />
                <Row k={t("devDetail.sessions")} v={String(d.tokens.sessions)} />
                <Row k={t("devProjects.colLastActive")} v={rel(d.tokens.last_active)} />
                {!d.tokens.same_path && <p className="text-xs text-outline">{t("devDetail.foldedInto", { name: d.tokens.name })}</p>}
                <Link to={`/projects/detail?path=${encodeURIComponent(d.tokens.key)}`}
                  className="inline-flex items-center gap-1 text-xs text-primary-container hover:underline">
                  {t("devDetail.viewCosts")}<span className="material-symbols-outlined text-[14px]">arrow_forward</span>
                </Link>
              </div>
            )}
          </Card>

          <Card title={t("devDetail.branches", { n: d.git.branches.length })} icon="call_split">
            {d.git.branches.length === 0 ? (
              <p className="text-sm text-on-surface-variant">—</p>
            ) : (
              <ul className="space-y-1">
                {d.git.branches.map((br) => (
                  <li key={br.name} className="flex items-center gap-2 text-xs">
                    <span className={`font-mono ${br.current ? "font-semibold text-primary-container" : ""}`}>{br.current ? "● " : ""}{br.name}</span>
                    <span className="ml-auto font-mono text-on-surface-variant">
                      {br.gone ? t("devDetail.upstreamGone") : !br.upstream ? t("devProjects.noUpstream")
                        : <><span className={br.ahead ? "text-error" : ""}>↑{br.ahead}</span> ↓{br.behind}</>}
                    </span>
                    <span className="w-16 text-right text-outline">{rel(br.last_commit_at)}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          {d.git.contributors.length > 0 && (
            <Card title={t("devDetail.contributors")} icon="group">
              <ul className="space-y-1 text-xs">
                {d.git.contributors.map((c) => (
                  <li key={c.name} className="flex justify-between"><span>{c.name}</span><span className="font-mono text-on-surface-variant">{c.commits}</span></li>
                ))}
              </ul>
            </Card>
          )}

          {m.updated_at && <p className="text-right text-xs text-outline">{t("devDetail.updatedAt", { time: rel(m.updated_at) })}</p>}
        </div>
      </div>

      {publishing && (
        <PublishDialog path={p.path} name={m.alias || p.name}
          onClose={(changed) => { setPublishing(false); if (changed) detail.retry(); }} />
      )}
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return <div className="flex h-48 items-center justify-center rounded border border-border-card bg-surface-card text-sm text-on-surface-variant">{text}</div>;
}

function Card({ title, icon, extra, children }: { title: string; icon: string; extra?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="rounded border border-border-card bg-surface-card p-4 shadow-card">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h4 className="flex items-center gap-1.5 text-sm font-semibold">
          <span className="material-symbols-outlined text-[18px] text-outline">{icon}</span>{title}
        </h4>
        {extra}
      </div>
      {children}
    </section>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-3">
      <span className="text-on-surface-variant">{k}</span>
      <span className="font-mono">{v}</span>
    </div>
  );
}

function Labeled({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="block text-xs font-semibold uppercase tracking-wide text-on-surface-variant">{label}</span>
      <div className="mt-1">{children}</div>
      {hint && <span className="mt-1 block text-[11px] text-outline">{hint}</span>}
    </label>
  );
}

function IconBtn({ icon, label, onClick, active, danger }: { icon: string; label: string; onClick: () => void; active?: boolean; danger?: boolean }) {
  return (
    <button onClick={onClick} title={label} aria-label={label}
      className={`rounded border border-border-card p-1.5 hover:bg-surface ${active ? "text-primary-container" : "text-on-surface-variant"} ${danger ? "hover:text-error" : ""}`}>
      <span className="material-symbols-outlined text-[18px]">{icon}</span>
    </button>
  );
}
