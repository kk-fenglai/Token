import { useEffect, useState } from "react";
import type { AgentSettings } from "../../api/types";

// Tiny shared store so the page, the drawer and the sidebar footer agree on
// settings (mainly: is a key configured) without a context provider.
let settings: AgentSettings | null = null;
let inflight: Promise<void> | null = null;
const listeners = new Set<() => void>();
let settingsOpen = false;
const openListeners = new Set<() => void>();

function emit() { listeners.forEach((l) => l()); }

export async function refreshAgentSettings(): Promise<void> {
  if (inflight) return inflight;
  inflight = fetch("/api/agent/settings")
    .then((r) => (r.ok ? r.json() : null))
    .then((s) => { if (s) { settings = s; emit(); } })
    .catch(() => undefined)
    .finally(() => { inflight = null; });
  return inflight;
}

export function setAgentSettings(s: AgentSettings) {
  settings = s;
  emit();
}

export function useAgentSettings(): AgentSettings | null {
  const [, force] = useState(0);
  useEffect(() => {
    const l = () => force((n) => n + 1);
    listeners.add(l);
    if (!settings) void refreshAgentSettings();
    return () => { listeners.delete(l); };
  }, []);
  return settings;
}

export function openAgentSettings(open = true) {
  settingsOpen = open;
  openListeners.forEach((l) => l());
}

export function useAgentSettingsOpen(): boolean {
  const [, force] = useState(0);
  useEffect(() => {
    const l = () => force((n) => n + 1);
    openListeners.add(l);
    return () => { openListeners.delete(l); };
  }, []);
  return settingsOpen;
}
