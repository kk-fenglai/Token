import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import type { PublishPlan, PublishResult } from "../api/types";
import { useI18n } from "../i18n";

interface Props {
  path: string;
  name: string;
  onClose: (changed: boolean) => void;
}

const SHOWN_FILES = 40;

// F27 — confirm-then-run dialog for one-click "upload to GitHub". The server
// re-plans on submit, so this view is only a preview of what will happen.
export default function PublishDialog({ path, name, onClose }: Props) {
  const { t } = useI18n();
  const [plan, setPlan] = useState<PublishPlan | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [commit, setCommit] = useState(true);
  const [message, setMessage] = useState("");
  const [repoName, setRepoName] = useState("");
  const [isPrivate, setIsPrivate] = useState(true);
  const [confirmed, setConfirmed] = useState(false);
  const [showFiles, setShowFiles] = useState(false);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<PublishResult | null>(null);
  const [errorCode, setErrorCode] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    fetch(`/api/dev-projects/publish-plan?path=${encodeURIComponent(path)}`)
      .then(async (res) => {
        const json = await res.json();
        if (!res.ok) throw new Error(json?.detail?.code ?? `HTTP ${res.status}`);
        return json as PublishPlan;
      })
      .then((p) => {
        if (!alive) return;
        setPlan(p);
        setMessage(p.default_message);
        setRepoName(p.default_repo_name);
      })
      .catch((e: Error) => alive && setLoadError(e.message));
    return () => { alive = false; };
  }, [path]);

  const done = result?.ok === true;
  const errText = (code: string) => {
    const key = `devProjects.publish.errors.${code}`;
    const s = t(key);
    return s === key ? `${t("devProjects.publish.errors.failed")} (${code})` : s;
  };
  const close = () => { if (!running) onClose(result !== null); };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const willCommit = commit && (plan?.file_count ?? 0) > 0;
  const hasWork = plan && (willCommit || plan.ahead > 0 || plan.action === "push_upstream" || plan.action === "create_repo");
  const needsConfirm = willCommit && (plan?.sensitive.length ?? 0) > 0;
  const repoNameOk = plan?.action !== "create_repo" || /^(?:[A-Za-z0-9-]{1,39}\/)?[A-Za-z0-9._-]{1,100}$/.test(repoName.trim());
  const canGo = !!plan && plan.action !== "blocked" && plan.action !== "nothing" && !!hasWork
    && (!needsConfirm || confirmed) && repoNameOk && !running && !done
    && (!willCommit || message.trim().length > 0);

  async function go() {
    if (!canGo || !plan) return;
    setRunning(true);
    setErrorCode(null);
    try {
      const res = await fetch("/api/dev-projects/publish", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          path, commit, message,
          ...(plan.action === "create_repo" ? { repo_name: repoName.trim(), private: isPrivate } : {}),
        }),
      });
      const json = await res.json();
      if (!res.ok) {
        setErrorCode(json?.detail?.code ?? "failed");
      } else {
        setResult(json as PublishResult);
        if (!json.ok) setErrorCode(json.error ?? "failed");
      }
    } catch {
      setErrorCode("failed");
    } finally {
      setRunning(false);
    }
  }

  const target = !plan ? "" : plan.action === "create_repo"
    ? t("devProjects.publish.targetCreate")
    : t(plan.action === "push_upstream" ? "devProjects.publish.targetUpstream" : "devProjects.publish.targetPush",
      { branch: plan.branch ?? "HEAD", remote: plan.github_url ?? plan.remote_url ?? plan.remote ?? "origin" });

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onMouseDown={close}>
      <div role="dialog" aria-modal="true" aria-labelledby="publish-title"
        onMouseDown={(e) => e.stopPropagation()}
        className="flex max-h-[90vh] w-full max-w-2xl flex-col rounded border border-border-card bg-surface-card shadow-card">
        <div className="flex items-center justify-between border-b border-border-card px-5 py-3">
          <h3 id="publish-title" className="flex items-center gap-2 text-base font-semibold">
            <span className="material-symbols-outlined text-[20px] text-primary-container">cloud_upload</span>
            {t("devProjects.publish.title", { name })}
          </h3>
          <button onClick={close} disabled={running} className="rounded p-1 text-on-surface-variant hover:bg-surface disabled:opacity-50">
            <span className="material-symbols-outlined text-[20px]">close</span>
          </button>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4 text-sm">
          {loadError ? (
            <p className="text-error">{errText(loadError)}</p>
          ) : !plan ? (
            <p className="text-on-surface-variant">{t("devProjects.publish.loading")}</p>
          ) : plan.action === "blocked" ? (
            <Notice tone="info" icon="info">{t(`devProjects.publish.blocked.${plan.blocked_reason}`)}</Notice>
          ) : plan.action === "nothing" ? (
            <Notice tone="ok" icon="check_circle">{t("devProjects.publish.nothing")}</Notice>
          ) : (
            <>
              <Field label={t("devProjects.publish.target")}>
                <span className="font-mono text-xs">{target}</span>
              </Field>

              {plan.action === "create_repo" && (
                <div className="grid gap-3 md:grid-cols-[1fr_auto]">
                  <label className="block">
                    <span className="block text-xs font-semibold uppercase tracking-wide text-on-surface-variant">{t("devProjects.publish.repoName")}</span>
                    <div className="mt-1 flex items-center rounded border border-border-card bg-surface font-mono text-sm">
                      {plan.gh?.user && !repoName.includes("/") && <span className="pl-3 text-outline">{plan.gh.user}/</span>}
                      <input value={repoName} onChange={(e) => setRepoName(e.target.value)} disabled={running || done}
                        className={`w-full bg-transparent px-2 py-1.5 outline-none ${repoNameOk ? "" : "text-error"}`} />
                    </div>
                    <span className="mt-1 block text-[11px] text-outline">{t("devProjects.publish.repoNameHint")}</span>
                  </label>
                  <div>
                    <span className="block text-xs font-semibold uppercase tracking-wide text-on-surface-variant">{t("devProjects.publish.visibility")}</span>
                    <div className="mt-1 flex overflow-hidden rounded border border-border-card">
                      {[true, false].map((v) => (
                        <button key={String(v)} onClick={() => setIsPrivate(v)} disabled={running || done}
                          className={`flex items-center gap-1 px-3 py-1.5 text-sm ${isPrivate === v ? "bg-primary-container text-on-primary" : "hover:bg-surface"}`}>
                          <span className="material-symbols-outlined text-[16px]">{v ? "lock" : "public"}</span>
                          {t(v ? "devProjects.publish.private" : "devProjects.publish.public")}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {plan.behind > 0 && <Notice tone="warn" icon="warning">{t("devProjects.publish.behindWarn", { n: plan.behind })}</Notice>}

              {plan.file_count > 0 && (
                <div className="space-y-2">
                  <label className="flex items-center gap-2">
                    <input type="checkbox" checked={commit} onChange={(e) => setCommit(e.target.checked)} disabled={running || done} />
                    <span className="font-medium">{t("devProjects.publish.commitAll")}</span>
                  </label>
                  <button onClick={() => setShowFiles((s) => !s)} className="flex items-center gap-1 text-xs text-on-surface-variant hover:text-on-surface">
                    <span className="material-symbols-outlined text-[16px]">{showFiles ? "expand_less" : "expand_more"}</span>
                    {t("devProjects.publish.changes", { n: plan.file_count })}
                  </button>
                  {showFiles && (
                    <ul className="max-h-40 overflow-y-auto rounded bg-surface px-3 py-2 font-mono text-[11px]">
                      {plan.files.slice(0, SHOWN_FILES).map((f) => (
                        <li key={f.path} className={plan.sensitive.includes(f.path) ? "text-error" : ""}>
                          <span className="inline-block w-7 text-outline">{f.status}</span>{f.path}
                        </li>
                      ))}
                      {plan.file_count > SHOWN_FILES && (
                        <li className="text-outline">{t("devProjects.publish.moreFiles", { n: plan.file_count - SHOWN_FILES })}</li>
                      )}
                    </ul>
                  )}
                  {commit && (
                    <label className="block">
                      <span className="block text-xs font-semibold uppercase tracking-wide text-on-surface-variant">{t("devProjects.publish.message")}</span>
                      <textarea value={message} onChange={(e) => setMessage(e.target.value)} rows={2} disabled={running || done}
                        className="mt-1 w-full rounded border border-border-card bg-surface px-3 py-1.5 font-mono text-xs" />
                    </label>
                  )}
                </div>
              )}

              {willCommit && plan.sensitive.length > 0 && (
                <Notice tone="danger" icon="key">
                  <p>{t("devProjects.publish.sensitive")}</p>
                  <ul className="my-1 font-mono text-[11px]">{plan.sensitive.map((p) => <li key={p}>{p}</li>)}</ul>
                  <label className="flex items-center gap-2 font-medium">
                    <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} disabled={running || done} />
                    {t("devProjects.publish.sensitiveConfirm")}
                  </label>
                </Notice>
              )}
              {willCommit && plan.large.length > 0 && (
                <Notice tone="warn" icon="hard_drive">
                  <p>{t("devProjects.publish.large")}</p>
                  <ul className="mt-1 font-mono text-[11px]">{plan.large.map((p) => <li key={p}>{p}</li>)}</ul>
                </Notice>
              )}

              <div>
                <span className="block text-xs font-semibold uppercase tracking-wide text-on-surface-variant">
                  {plan.commits.length ? t("devProjects.publish.commits", { n: plan.commits.length }) : t("devProjects.publish.noCommits")}
                </span>
                {plan.commits.length > 0 && (
                  <ul className="mt-1 max-h-32 overflow-y-auto font-mono text-[11px]">
                    {plan.commits.map((c) => (
                      <li key={c.sha}><span className="text-outline">{c.sha}</span> {c.subject}</li>
                    ))}
                  </ul>
                )}
              </div>
            </>
          )}

          {done && (
            <Notice tone="ok" icon="check_circle">
              <span className="font-semibold">{t("devProjects.publish.done")}</span>
              {result?.github_url && (
                <a href={result.github_url} target="_blank" rel="noreferrer" className="ml-2 text-primary-container underline">
                  {t("devProjects.publish.viewOnGithub")}
                </a>
              )}
            </Notice>
          )}
          {errorCode && (
            <Notice tone="danger" icon="error">
              <span className="font-semibold">{t("devProjects.publish.failed")}</span>
              <p className="mt-0.5">{errText(errorCode)}</p>
            </Notice>
          )}
          {result && result.steps.length > 0 && (
            <details open={!result.ok} className="rounded border border-border-card">
              <summary className="cursor-pointer px-3 py-1.5 text-xs text-on-surface-variant">{t("devProjects.publish.details")}</summary>
              <div className="space-y-2 border-t border-border-card px-3 py-2">
                {result.steps.map((s, i) => (
                  <div key={i}>
                    <div className="flex items-center gap-1 font-mono text-[11px]">
                      <span className={`material-symbols-outlined text-[14px] ${s.ok ? "text-success" : "text-error"}`}>{s.ok ? "check" : "close"}</span>
                      $ {s.cmd}
                    </div>
                    {s.output && <pre className="mt-0.5 max-h-32 overflow-auto whitespace-pre-wrap rounded bg-surface px-2 py-1 text-[11px] text-on-surface-variant">{s.output}</pre>}
                  </div>
                ))}
              </div>
            </details>
          )}
        </div>

        <div className="flex justify-end gap-2 border-t border-border-card px-5 py-3">
          <button onClick={close} disabled={running}
            className="rounded border border-border-card px-4 py-1.5 text-sm hover:bg-surface disabled:opacity-50">
            {done || plan?.action === "blocked" || plan?.action === "nothing" ? t("devProjects.publish.close") : t("devProjects.publish.cancel")}
          </button>
          {plan && plan.action !== "blocked" && plan.action !== "nothing" && !done && (
            <button onClick={go} disabled={!canGo}
              className="flex items-center gap-1 rounded bg-primary-container px-4 py-1.5 text-sm font-semibold text-on-primary hover:opacity-90 disabled:opacity-50">
              <span className={`material-symbols-outlined text-[18px] ${running ? "animate-spin" : ""}`}>{running ? "progress_activity" : "cloud_upload"}</span>
              {running ? t("devProjects.publish.running") : t("devProjects.publish.go")}
            </button>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}

const TONES = {
  ok: "border-l-success",
  info: "border-l-outline-variant",
  warn: "border-l-secondary-container",
  danger: "border-l-error",
} as const;

function Notice({ tone, icon, children }: { tone: keyof typeof TONES; icon: string; children: React.ReactNode }) {
  const color = tone === "ok" ? "text-success" : tone === "danger" ? "text-error" : tone === "warn" ? "text-secondary" : "text-on-surface-variant";
  return (
    <div className={`flex gap-2 rounded border border-l-4 border-border-card bg-surface px-3 py-2 ${TONES[tone]}`}>
      <span className={`material-symbols-outlined text-[18px] ${color}`}>{icon}</span>
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <span className="block text-xs font-semibold uppercase tracking-wide text-on-surface-variant">{label}</span>
      <div className="mt-0.5">{children}</div>
    </div>
  );
}
