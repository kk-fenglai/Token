// POST + Server-Sent Events. EventSource only does GET, so read the fetch
// body stream and split on blank lines ourselves.

export interface SSEHandlers {
  onEvent: (event: string, data: any) => void;
  signal?: AbortSignal;
}

export class HttpError extends Error {
  constructor(public status: number, public code: string | null, message: string) {
    super(message);
  }
}

export async function streamSSE(url: string, body: unknown, { onEvent, signal }: SSEHandlers): Promise<void> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) {
    let code: string | null = null;
    let msg = `HTTP ${res.status}`;
    try {
      const json = await res.json();
      code = json?.detail?.code ?? null;
      msg = json?.detail?.detail ?? msg;
    } catch { /* not JSON */ }
    throw new HttpError(res.status, code, typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const block = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      let event = "message";
      const data: string[] = [];
      for (const line of block.split("\n")) {
        if (line.startsWith(":")) continue; // keep-alive comment
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
      }
      if (!data.length) continue;
      try {
        onEvent(event, JSON.parse(data.join("\n")));
      } catch { /* malformed frame: skip */ }
    }
  }
}
