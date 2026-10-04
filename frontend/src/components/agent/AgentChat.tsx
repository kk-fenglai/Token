import { useCallback, useEffect, useRef, useState } from "react";
import type { AgentAssistantMessage, AgentConversation, AgentMessage, AgentToolCall, AgentUsage } from "../../api/types";
import { useI18n } from "../../i18n";
import { Markdown } from "../../lib/markdown";
import type { PageContext } from "../../lib/pageContext";
import { HttpError, streamSSE } from "../../lib/sse";

interface Props {
  conversationId: string | null;
  onConversationChange: (id: string | null) => void;
  pageContext?: PageContext;
  keyConfigured: boolean;
  onOpenSettings: () => void;
  onActivity?: () => void;
  compact?: boolean;
  suggestions?: string[];
}

const EMPTY_USAGE: AgentUsage = { hit: 0, miss: 0, completion: 0, cost_usd: 0, requests: 0 };

export function formatUsd(v: number): string {
  if (v === 0) return "$0";
  if (v < 0.01) return `$${v.toFixed(4)}`;
  return `$${v.toFixed(2)}`;
}

export default function AgentChat({ conversationId, onConversationChange, pageContext, keyConfigured,
  onOpenSettings, onActivity, compact, suggestions }: Props) {
  const { t } = useI18n();
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [usage, setUsage] = useState<AgentUsage>(EMPTY_USAGE);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<{ code: string; message: string } | null>(null);
  const [loading, setLoading] = useState(false);
  const [input, setInput] = useState("");

  const msgsRef = useRef<AgentMessage[]>([]);
  const frame = useRef<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const runIdRef = useRef<string | null>(null);
  const streamingConv = useRef<string | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  // Parents pass inline callbacks; keep them out of effect deps.
  const onChangeRef = useRef(onConversationChange);
  onChangeRef.current = onConversationChange;

  const flush = useCallback(() => {
    if (frame.current != null) return;
    frame.current = requestAnimationFrame(() => {
      frame.current = null;
      setMessages([...msgsRef.current]);
    });
  }, []);

  const load = useCallback(async (id: string) => {
    setLoading(true);
    try {
      const res = await fetch(`/api/agent/conversations/${id}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const conv = (await res.json()) as AgentConversation;
      msgsRef.current = conv.messages;
      setMessages(conv.messages);
      setUsage(conv.usage);
      setRunning(conv.running);
    } catch {
      msgsRef.current = [];
      setMessages([]);
      onChangeRef.current(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (conversationId && conversationId === streamingConv.current) return; // we just created it
    setError(null);
    if (!conversationId) {
      msgsRef.current = [];
      setMessages([]);
      setUsage(EMPTY_USAGE);
      return;
    }
    void load(conversationId);
  }, [conversationId, load]);

  useEffect(() => () => { abortRef.current?.abort(); }, []);

  useEffect(() => {
    const el = scroller.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [messages]);

  const last = (): AgentAssistantMessage | null => {
    const m = msgsRef.current[msgsRef.current.length - 1];
    return m && m.role === "assistant" ? m : null;
  };
  const patchLast = (fn: (m: AgentAssistantMessage) => AgentAssistantMessage) => {
    const i = msgsRef.current.length - 1;
    const m = msgsRef.current[i];
    if (m && m.role === "assistant") msgsRef.current[i] = fn(m);
  };
  const patchTool = (id: string, fn: (c: AgentToolCall) => AgentToolCall) => {
    msgsRef.current = msgsRef.current.map((m) => m.role === "assistant" && m.tool_calls.some((c) => c.id === id)
      ? { ...m, tool_calls: m.tool_calls.map((c) => (c.id === id ? fn(c) : c)) } : m);
  };

  async function send(text: string) {
    const message = text.trim();
    if (!message || running) return;
    setError(null);
    setInput("");
    stick.current = true;
    const fresh = (): AgentAssistantMessage => ({ role: "assistant", content: "", reasoning: "", tool_calls: [] });
    msgsRef.current = [...msgsRef.current, { role: "user", content: message }, fresh()];
    flush();
    setRunning(true);
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    let convId = conversationId;
    try {
      await streamSSE("/api/agent/chat", { message, conversation_id: conversationId, page_context: pageContext }, {
        signal: ctrl.signal,
        onEvent: (event, data) => {
          switch (event) {
            case "run_start":
              runIdRef.current = data.run_id;
              if (!convId) {
                convId = data.conversation_id;
                streamingConv.current = data.conversation_id;
                onChangeRef.current(data.conversation_id);
              }
              break;
            case "step":
              if (data.n > 1) {
                const l = last();
                if (l && (l.content || l.reasoning || l.tool_calls.length)) msgsRef.current = [...msgsRef.current, fresh()];
              }
              break;
            case "reasoning_delta":
              patchLast((m) => ({ ...m, reasoning: m.reasoning + data.text }));
              break;
            case "text_delta":
              patchLast((m) => ({ ...m, content: m.content + data.text }));
              break;
            case "tool_call":
              patchLast((m) => ({ ...m, tool_calls: [...m.tool_calls, { id: data.id, name: data.name, args: data.args,
                kind: data.kind, status: "running", result: null, chars: null, ms: null }] }));
              break;
            case "confirm_required":
              patchTool(data.id, (c) => ({ ...c, status: "awaiting", runId: data.run_id }));
              break;
            case "tool_result":
              patchTool(data.id, (c) => ({ ...c, status: data.status, result: data.preview, chars: data.chars, ms: data.ms }));
              break;
            case "usage":
              setUsage((u) => ({ hit: u.hit + (data.hit ?? 0), miss: u.miss + (data.miss ?? 0),
                completion: u.completion + (data.completion ?? 0), cost_usd: u.cost_usd + (data.cost_usd ?? 0),
                requests: u.requests + 1 }));
              break;
            case "notice":
              patchLast((m) => ({ ...m, content: `${m.content}\n\n_${data.message}_` }));
              break;
            case "error":
              setError({ code: data.code, message: data.message });
              break;
          }
          flush();
        },
      });
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        const code = e instanceof HttpError ? e.code ?? `http_${e.status}` : "network";
        setError({ code, message: (e as Error).message });
      }
    } finally {
      abortRef.current = null;
      runIdRef.current = null;
      setRunning(false);
      streamingConv.current = null;
      // Drop an assistant bubble that never received anything.
      const l = last();
      if (l && !l.content && !l.reasoning && !l.tool_calls.length) msgsRef.current = msgsRef.current.slice(0, -1);
      flush();
      if (convId) void load(convId); // server copy is the source of truth (statuses, usage)
      onActivity?.();
    }
  }

  async function stop() {
    const rid = runIdRef.current;
    if (rid) await fetch(`/api/agent/runs/${rid}/cancel`, { method: "POST" }).catch(() => null);
    else abortRef.current?.abort();
  }

  async function answer(call: AgentToolCall, approve: boolean) {
    if (!call.runId) return;
    patchTool(call.id, (c) => ({ ...c, status: "running" }));
    flush();
    await fetch(`/api/agent/runs/${call.runId}/confirm`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tool_call_id: call.id, approve }),
    }).catch(() => null);
  }

  const prompts = suggestions ?? [t("agent.suggest.spend"), t("agent.suggest.save"), t("agent.suggest.push"), t("agent.suggest.patrol")];
  const prompt = usage.hit + usage.miss;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div ref={scroller} onScroll={(e) => {
        const el = e.currentTarget;
        stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
      }} className={`min-h-0 flex-1 overflow-y-auto ${compact ? "px-4 py-3" : "px-6 py-5"}`}>
        {!keyConfigured ? (
          <div className="mx-auto mt-10 max-w-md rounded border border-border-card bg-surface p-5 text-center text-sm">
            <span className="material-symbols-outlined text-[36px] text-primary-container">key</span>
            <p className="mt-2 font-semibold">{t("agent.noKeyTitle")}</p>
            <p className="mt-1 text-on-surface-variant">{t("agent.noKeyBody")}</p>
            <button onClick={onOpenSettings}
              className="mt-4 rounded bg-primary-container px-4 py-1.5 font-semibold text-on-primary hover:opacity-90">
              {t("agent.openSettings")}
            </button>
          </div>
        ) : loading && !messages.length ? (
          <div className="flex h-32 items-center justify-center text-sm text-on-surface-variant">{t("common.loading")}</div>
        ) : !messages.length ? (
          <div className={`mx-auto ${compact ? "mt-4" : "mt-10"} max-w-xl text-center`}>
            <span className="material-symbols-outlined text-[40px] text-primary-container">smart_toy</span>
            <p className="mt-2 text-base font-semibold">{t("agent.emptyTitle")}</p>
            <p className="mt-1 text-sm text-on-surface-variant">{t("agent.emptyBody")}</p>
            <div className={`mt-5 grid gap-2 ${compact ? "" : "sm:grid-cols-2"}`}>
              {prompts.map((p) => (
                <button key={p} onClick={() => void send(p)}
                  className="rounded border border-border-card bg-surface-card px-3 py-2 text-left text-sm hover:border-primary-container hover:text-primary-container">
                  {p}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {messages.map((m, i) => m.role === "user"
              ? <UserBubble key={i} text={m.content} />
              : <AssistantBlock key={i} m={m} streaming={running && i === messages.length - 1}
                  continued={i > 0 && messages[i - 1].role === "assistant"} onAnswer={answer} />)}
          </div>
        )}
      </div>

      {error && (
        <div className="mx-4 mb-2 flex items-start gap-2 rounded border border-l-4 border-border-card border-l-error bg-surface px-3 py-2 text-sm">
          <span className="material-symbols-outlined text-[18px] text-error">error</span>
          <div className="min-w-0 flex-1">
            <span className="font-semibold">{t(`agent.errors.${error.code}`) === `agent.errors.${error.code}` ? t("agent.errors.generic") : t(`agent.errors.${error.code}`)}</span>
            <span className="block break-words text-xs text-on-surface-variant">{error.message}</span>
          </div>
          {["auth", "no_key", "bad_model", "http_412"].includes(error.code) && (
            <button onClick={onOpenSettings} className="shrink-0 text-xs text-primary-container hover:underline">{t("agent.openSettings")}</button>
          )}
        </div>
      )}

      <Composer value={input} onChange={setInput} onSend={() => void send(input)} onStop={() => void stop()}
        running={running} disabled={!keyConfigured} compact={compact}
        meta={usage.requests > 0 ? t("agent.usageLine", {
          cost: formatUsd(usage.cost_usd), n: usage.requests,
          hit: prompt ? Math.round((usage.hit / prompt) * 100) : 0,
        }) : null} />
    </div>
  );
}

function UserBubble({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] whitespace-pre-wrap rounded-lg rounded-tr-sm bg-primary-container px-3.5 py-2 text-sm text-on-primary">
        {text}
      </div>
    </div>
  );
}

function AssistantBlock({ m, streaming, continued, onAnswer }: {
  m: AgentAssistantMessage; streaming: boolean; continued: boolean;
  onAnswer: (c: AgentToolCall, approve: boolean) => void;
}) {
  const { t } = useI18n();
  const thinkingNow = streaming && !m.content && !m.tool_calls.length;
  return (
    <div className={`flex gap-2.5 ${continued ? "-mt-2" : ""}`}>
      <div className="w-7 shrink-0">
        {!continued && (
          <span className="flex h-7 w-7 items-center justify-center rounded-full bg-primary-container/10 text-primary-container">
            <span className="material-symbols-outlined text-[18px]">smart_toy</span>
          </span>
        )}
      </div>
      <div className="min-w-0 flex-1 space-y-2">
        {(m.reasoning || thinkingNow) && (
          <details className="group rounded border border-border-card/70 bg-surface/60" open={thinkingNow && !!m.reasoning}>
            <summary className="flex cursor-pointer list-none items-center gap-1.5 px-2.5 py-1 text-xs text-on-surface-variant">
              <span className={`material-symbols-outlined text-[16px] ${thinkingNow ? "animate-pulse" : ""}`}>psychology</span>
              {thinkingNow ? t("agent.thinking") : t("agent.thought")}
              <span className="material-symbols-outlined ml-auto text-[16px] transition-transform group-open:rotate-180">expand_more</span>
            </summary>
            {m.reasoning && (
              <div className="max-h-60 overflow-y-auto whitespace-pre-wrap border-t border-border-card/70 px-2.5 py-2 text-xs leading-relaxed text-on-surface-variant">
                {m.reasoning}
              </div>
            )}
          </details>
        )}
        {m.tool_calls.length > 0 && (
          <div className="flex flex-col gap-1.5">
            {m.tool_calls.map((c) => <ToolCallChip key={c.id} call={c} onAnswer={onAnswer} />)}
          </div>
        )}
        {m.content && (
          <div className="text-sm leading-relaxed">
            <Markdown source={m.content} />
            {streaming && <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-primary-container align-middle" />}
          </div>
        )}
      </div>
    </div>
  );
}

const KIND_STYLE: Record<string, string> = {
  read: "bg-surface text-on-surface-variant",
  write: "bg-secondary-container/25 text-secondary",
  external: "bg-error-container text-on-error-container",
};

function pretty(raw: string | null): string {
  if (!raw) return "";
  try { return JSON.stringify(JSON.parse(raw), null, 2); } catch { return raw; }
}

function ToolCallChip({ call, onAnswer }: { call: AgentToolCall; onAnswer: (c: AgentToolCall, approve: boolean) => void }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const icon = call.status === "running" || call.status === "pending" ? "progress_activity"
    : call.status === "ok" ? "check_circle" : call.status === "awaiting" ? "front_hand"
    : call.status === "denied" ? "block" : call.status === "blocked" ? "gpp_maybe" : "error";
  const color = call.status === "ok" ? "text-success" : call.status === "running" || call.status === "pending"
    ? "text-primary-container" : call.status === "awaiting" ? "text-secondary" : "text-error";
  const args = pretty(call.args);
  return (
    <div className={`rounded border ${call.status === "awaiting" ? "border-secondary-container" : "border-border-card"} bg-surface-card text-xs`}>
      <button onClick={() => setOpen((o) => !o)} className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left">
        <span className={`material-symbols-outlined text-[16px] ${color} ${call.status === "running" ? "animate-spin" : ""}`}>{icon}</span>
        <span className="font-mono font-medium">{call.name}</span>
        {call.kind && (
          <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${KIND_STYLE[call.kind] ?? KIND_STYLE.read}`}>
            {t(`agent.kind.${call.kind}`)}
          </span>
        )}
        {call.status !== "ok" && call.status !== "running" && call.status !== "pending" && (
          <span className={`text-[11px] ${color}`}>{t(`agent.status.${call.status}`)}</span>
        )}
        <span className="ml-auto flex items-center gap-2 text-[11px] text-outline">
          {call.ms != null && <span>{call.ms < 1000 ? `${call.ms} ms` : `${(call.ms / 1000).toFixed(1)} s`}</span>}
          <span className={`material-symbols-outlined text-[16px] transition-transform ${open ? "rotate-180" : ""}`}>expand_more</span>
        </span>
      </button>
      {call.status === "awaiting" && (
        <div className="flex items-center gap-2 border-t border-border-card px-2.5 py-1.5">
          <span className="flex-1 text-on-surface-variant">{t("agent.confirmAsk")}</span>
          <button onClick={() => onAnswer(call, false)} className="rounded border border-border-card px-2 py-0.5 hover:bg-surface">{t("agent.deny")}</button>
          <button onClick={() => onAnswer(call, true)} className="rounded bg-primary-container px-2 py-0.5 font-semibold text-on-primary">{t("agent.approve")}</button>
        </div>
      )}
      {open && (
        <div className="space-y-2 border-t border-border-card px-2.5 py-2">
          {args && args !== "{}" && (
            <div>
              <div className="mb-0.5 text-[10px] font-semibold uppercase tracking-wide text-outline">{t("agent.args")}</div>
              <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-all rounded bg-surface px-2 py-1 font-mono text-[11px]">{args}</pre>
            </div>
          )}
          {call.result != null && (
            <div>
              <div className="mb-0.5 text-[10px] font-semibold uppercase tracking-wide text-outline">
                {t("agent.result")}{call.chars != null && call.chars > 4000 ? ` · ${t("agent.resultChars", { n: call.chars.toLocaleString() })}` : ""}
              </div>
              <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-all rounded bg-surface px-2 py-1 font-mono text-[11px]">{pretty(call.result).slice(0, 8000)}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Composer({ value, onChange, onSend, onStop, running, disabled, compact, meta }: {
  value: string; onChange: (v: string) => void; onSend: () => void; onStop: () => void;
  running: boolean; disabled: boolean; compact?: boolean; meta: string | null;
}) {
  const { t } = useI18n();
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
  }, [value]);
  return (
    <div className={`border-t border-border-card bg-surface-card ${compact ? "px-3 py-2" : "px-6 py-3"}`}>
      <div className="flex items-end gap-2 rounded border border-border-card bg-surface px-3 py-2 focus-within:border-primary-container">
        <textarea ref={ref} value={value} rows={1} disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            // isComposing: Enter that confirms a Chinese IME candidate must not send.
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); if (!running) onSend(); }
          }}
          placeholder={disabled ? t("agent.placeholderNoKey") : t("agent.placeholder")}
          className="max-h-[180px] min-h-[24px] flex-1 resize-none bg-transparent text-sm outline-none disabled:opacity-60" />
        {running ? (
          <button onClick={onStop} title={t("agent.stop")}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded bg-error text-white hover:opacity-90">
            <span className="material-symbols-outlined text-[18px]">stop</span>
          </button>
        ) : (
          <button onClick={onSend} disabled={disabled || !value.trim()} title={t("agent.send")}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded bg-primary-container text-on-primary hover:opacity-90 disabled:opacity-40">
            <span className="material-symbols-outlined text-[18px]">arrow_upward</span>
          </button>
        )}
      </div>
      <div className="mt-1 flex justify-between gap-2 text-[11px] text-outline">
        <span>{t("agent.hint")}</span>
        {meta && <span className="shrink-0">{meta}</span>}
      </div>
    </div>
  );
}
