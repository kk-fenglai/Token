import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import type { AgentSettings } from "../../api/types";
import { useI18n } from "../../i18n";
import { openAgentSettings, refreshAgentSettings, setAgentSettings, useAgentSettings } from "./agentStore";

type Form = Pick<AgentSettings, "base_url" | "model" | "models" | "thinking" | "confirm_side_effects" | "max_iterations"
  | "max_external_calls" | "patrol" | "pricing">;

async function jsonOrThrow(res: Response) {
  const json = await res.json().catch(() => null);
  if (!res.ok) {
    const d = json?.detail?.detail;
    throw new Error(Array.isArray(d) ? d.join("; ") : typeof d === "string" ? d : `HTTP ${res.status}`);
  }
  return json;
}

export default function AgentSettingsDialog() {
  const { t } = useI18n();
  const s = useAgentSettings();
  const [form, setForm] = useState<Form | null>(null);
  const [modelsText, setModelsText] = useState("");
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [test, setTest] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => { void refreshAgentSettings(); }, []);
  useEffect(() => {
    if (s && !form) {
      setForm({ base_url: s.base_url, model: s.model, models: s.models, thinking: s.thinking,
        confirm_side_effects: s.confirm_side_effects, max_iterations: s.max_iterations,
        max_external_calls: s.max_external_calls, patrol: s.patrol, pricing: s.pricing });
      setModelsText(s.models.join(", "));
    }
  }, [s, form]);

  const close = () => { if (!busy) openAgentSettings(false); };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  async function saveKey() {
    if (!key.trim()) return;
    setBusy(true); setMsg(null);
    try {
      await jsonOrThrow(await fetch("/api/agent/key", { method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ api_key: key.trim() }) }));
      setKey("");
      await refreshAgentSettings();
      setMsg({ ok: true, text: t("agent.settings.keySaved") });
    } catch (e) { setMsg({ ok: false, text: (e as Error).message }); } finally { setBusy(false); }
  }

  async function removeKey() {
    setBusy(true);
    try { await fetch("/api/agent/key", { method: "DELETE" }); await refreshAgentSettings(); } finally { setBusy(false); }
  }

  async function runTest() {
    setTest(null); setBusy(true);
    try {
      const r = await (await fetch("/api/agent/test", { method: "POST" })).json();
      setTest(r.ok
        ? { ok: r.configured_available, text: r.configured_available ? t("agent.settings.testOk", { n: r.models.length })
          : t("agent.settings.testMissing", { model: r.configured, models: r.models.join(", ") }) }
        : { ok: false, text: r.message ?? r.code });
    } catch (e) { setTest({ ok: false, text: (e as Error).message }); } finally { setBusy(false); }
  }

  async function save() {
    if (!form) return;
    setBusy(true); setMsg(null);
    const models = modelsText.split(/[,\s，]+/).map((m) => m.trim()).filter(Boolean);
    try {
      const next = await jsonOrThrow(await fetch("/api/agent/settings", { method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...form, models: models.includes(form.model) ? models : [form.model, ...models] }) }));
      setAgentSettings(next);
      setMsg({ ok: true, text: t("agent.settings.saved") });
    } catch (e) { setMsg({ ok: false, text: (e as Error).message }); } finally { setBusy(false); }
  }

  const pc = form?.patrol;
  const setPatrol = (patch: Partial<Form["patrol"]>) => form && setForm({ ...form, patrol: { ...form.patrol, ...patch } });

  return createPortal(
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-4" onMouseDown={close}>
      <div role="dialog" aria-modal="true" aria-labelledby="agent-settings-title" onMouseDown={(e) => e.stopPropagation()}
        className="flex max-h-[90vh] w-full max-w-2xl flex-col rounded border border-border-card bg-surface-card shadow-card">
        <div className="flex items-center justify-between border-b border-border-card px-5 py-3">
          <h3 id="agent-settings-title" className="flex items-center gap-2 text-base font-semibold">
            <span className="material-symbols-outlined text-[20px] text-primary-container">tune</span>{t("agent.settings.title")}
          </h3>
          <button onClick={close} className="rounded p-1 text-on-surface-variant hover:bg-surface">
            <span className="material-symbols-outlined text-[20px]">close</span>
          </button>
        </div>

        {!s || !form ? (
          <div className="p-8 text-center text-sm text-on-surface-variant">{t("common.loading")}</div>
        ) : (
          <div className="flex-1 space-y-5 overflow-y-auto px-5 py-4 text-sm">
            {/* key */}
            <section>
              <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-on-surface-variant">{t("agent.settings.key")}</h4>
              <div className="flex flex-wrap items-center gap-2 text-xs">
                {s.key.configured ? (
                  <span className="flex items-center gap-1 rounded-full bg-success-container px-2 py-0.5 text-on-success-container">
                    <span className="material-symbols-outlined text-[14px]">check_circle</span>
                    {t("agent.settings.keyConfigured", { masked: s.key.masked ?? "" })} · {t(`agent.settings.source.${s.key.source}`)}
                  </span>
                ) : (
                  <span className="rounded-full bg-surface px-2 py-0.5 text-on-surface-variant">{t("agent.settings.keyMissing")}</span>
                )}
                {s.key.source === "stored" && (
                  <button onClick={removeKey} disabled={busy} className="text-error hover:underline">{t("agent.settings.removeKey")}</button>
                )}
              </div>
              <form className="mt-2 flex gap-2" onSubmit={(e) => { e.preventDefault(); void saveKey(); }}>
                <input type="text" name="username" autoComplete="username" value="deepseek" readOnly hidden />
                <input type="password" value={key} onChange={(e) => setKey(e.target.value)} autoComplete="new-password"
                  placeholder={s.key.configured ? t("agent.settings.keyReplace") : "sk-…"}
                  className="flex-1 rounded border border-border-card bg-surface px-3 py-1.5 font-mono text-sm" />
                <button type="submit" disabled={busy || !key.trim()}
                  className="rounded bg-primary-container px-3 py-1.5 font-semibold text-on-primary disabled:opacity-50">{t("agent.settings.saveKey")}</button>
                <button type="button" onClick={runTest} disabled={busy || !s.key.configured}
                  className="rounded border border-border-card px-3 py-1.5 hover:bg-surface disabled:opacity-50">{t("agent.settings.test")}</button>
              </form>
              <p className="mt-1 text-[11px] text-outline">{t("agent.settings.keyHint")}</p>
              {test && <p className={`mt-1 text-xs ${test.ok ? "text-success" : "text-error"}`}>{test.text}</p>}
            </section>

            {/* model */}
            <section className="grid gap-3 md:grid-cols-2">
              <Field label={t("agent.settings.model")}>
                <select value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })}
                  className="w-full rounded border border-border-card bg-surface px-3 py-1.5">
                  {Array.from(new Set([form.model, ...modelsText.split(/[,\s，]+/).filter(Boolean)])).map((m) =>
                    <option key={m} value={m}>{m}</option>)}
                </select>
              </Field>
              <Field label={t("agent.settings.models")} hint={t("agent.settings.modelsHint")}>
                <input value={modelsText} onChange={(e) => setModelsText(e.target.value)}
                  className="w-full rounded border border-border-card bg-surface px-3 py-1.5 font-mono text-xs" />
              </Field>
              <Field label={t("agent.settings.baseUrl")}>
                <input value={form.base_url} onChange={(e) => setForm({ ...form, base_url: e.target.value })}
                  className="w-full rounded border border-border-card bg-surface px-3 py-1.5 font-mono text-xs" />
              </Field>
              <Field label={t("agent.settings.maxIterations")}>
                <input type="number" min={1} max={40} value={form.max_iterations}
                  onChange={(e) => setForm({ ...form, max_iterations: Math.max(1, Math.min(40, parseInt(e.target.value || "1", 10))) })}
                  className="w-full rounded border border-border-card bg-surface px-3 py-1.5 font-mono" />
              </Field>
            </section>

            {/* behaviour */}
            <section className="space-y-2">
              <Toggle checked={form.thinking} onChange={(v) => setForm({ ...form, thinking: v })}
                label={t("agent.settings.thinking")} hint={t("agent.settings.thinkingHint")} />
              <Toggle checked={form.confirm_side_effects} onChange={(v) => setForm({ ...form, confirm_side_effects: v })}
                label={t("agent.settings.confirm")} hint={t("agent.settings.confirmHint")} />
              <div className="flex items-center gap-2 pl-6 text-xs text-on-surface-variant">
                {t("agent.settings.externalLimit")}
                <input type="number" min={0} max={10} value={form.max_external_calls}
                  onChange={(e) => setForm({ ...form, max_external_calls: Math.max(0, Math.min(10, parseInt(e.target.value || "0", 10))) })}
                  className="w-16 rounded border border-border-card bg-surface px-2 py-0.5 font-mono" />
              </div>
            </section>

            {/* patrol */}
            {pc && (
              <section className="rounded border border-border-card p-3">
                <Toggle checked={pc.enabled} onChange={(v) => setPatrol({ enabled: v })}
                  label={t("agent.settings.patrol")} hint={t("agent.settings.patrolHint")} />
                <div className={`mt-2 flex flex-wrap items-center gap-2 pl-6 text-xs ${pc.enabled ? "" : "opacity-50"}`}>
                  <select value={pc.schedule} onChange={(e) => setPatrol({ schedule: e.target.value as "daily" | "weekly" })}
                    className="rounded border border-border-card bg-surface px-2 py-1">
                    <option value="daily">{t("agent.settings.daily")}</option>
                    <option value="weekly">{t("agent.settings.weekly")}</option>
                  </select>
                  {pc.schedule === "weekly" && (
                    <select value={pc.weekday} onChange={(e) => setPatrol({ weekday: parseInt(e.target.value, 10) })}
                      className="rounded border border-border-card bg-surface px-2 py-1">
                      {[1, 2, 3, 4, 5, 6, 7].map((d) => <option key={d} value={d}>{t(`agent.settings.weekdays.${d}`)}</option>)}
                    </select>
                  )}
                  <input type="time" value={pc.time} onChange={(e) => setPatrol({ time: e.target.value })}
                    className="rounded border border-border-card bg-surface px-2 py-1 font-mono" />
                  <label className="flex items-center gap-1"><input type="checkbox" checked={pc.notify}
                    onChange={(e) => setPatrol({ notify: e.target.checked })} />{t("agent.settings.patrolNotify")}</label>
                  <label className="flex items-center gap-1"><input type="checkbox" checked={pc.use_llm}
                    onChange={(e) => setPatrol({ use_llm: e.target.checked })} />{t("agent.settings.patrolLlm")}</label>
                </div>
              </section>
            )}

            {/* pricing */}
            <section>
              <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-on-surface-variant">{t("agent.settings.pricing")}</h4>
              <table className="w-full text-xs">
                <thead><tr className="text-left text-outline">
                  <th className="py-1 font-medium">{t("agent.settings.model")}</th>
                  <th className="py-1 font-medium">{t("agent.settings.priceMiss")}</th>
                  <th className="py-1 font-medium">{t("agent.settings.priceHit")}</th>
                  <th className="py-1 font-medium">{t("agent.settings.priceOut")}</th>
                </tr></thead>
                <tbody>
                  {Object.entries(form.pricing).map(([m, p]) => (
                    <tr key={m}>
                      <td className="py-0.5 font-mono">{m}</td>
                      {(["input_miss", "input_hit", "output"] as const).map((r) => (
                        <td key={r} className="py-0.5 pr-2">
                          <input type="number" step="0.001" min={0} value={p[r]}
                            onChange={(e) => setForm({ ...form, pricing: { ...form.pricing, [m]: { ...p, [r]: Math.max(0, parseFloat(e.target.value || "0")) } } })}
                            className="w-24 rounded border border-border-card bg-surface px-2 py-0.5 font-mono" />
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="mt-1 text-[11px] text-outline">{t("agent.settings.pricingHint")}</p>
            </section>

            <div className="flex gap-2 rounded border border-l-4 border-border-card border-l-secondary-container bg-surface px-3 py-2 text-xs text-on-surface-variant">
              <span className="material-symbols-outlined text-[18px] text-secondary">privacy_tip</span>
              <span>{t("agent.settings.privacy")}</span>
            </div>
          </div>
        )}

        <div className="flex items-center justify-end gap-2 border-t border-border-card px-5 py-3">
          {msg && <span className={`mr-auto text-xs ${msg.ok ? "text-success" : "text-error"}`}>{msg.text}</span>}
          <button onClick={close} className="rounded border border-border-card px-4 py-1.5 text-sm hover:bg-surface">{t("devProjects.publish.close")}</button>
          <button onClick={save} disabled={busy || !form}
            className="rounded bg-primary-container px-4 py-1.5 text-sm font-semibold text-on-primary hover:opacity-90 disabled:opacity-50">
            {t("devProjects.save")}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="block text-xs font-semibold uppercase tracking-wide text-on-surface-variant">{label}</span>
      <div className="mt-1">{children}</div>
      {hint && <span className="mt-0.5 block text-[11px] text-outline">{hint}</span>}
    </label>
  );
}

function Toggle({ checked, onChange, label, hint }: { checked: boolean; onChange: (v: boolean) => void; label: string; hint?: string }) {
  return (
    <label className="flex items-start gap-2">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="mt-1" />
      <span>
        <span className="font-medium">{label}</span>
        {hint && <span className="block text-xs text-on-surface-variant">{hint}</span>}
      </span>
    </label>
  );
}
