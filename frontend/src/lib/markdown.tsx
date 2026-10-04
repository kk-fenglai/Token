import type { ReactNode } from "react";

// Minimal README renderer for the dev-project page. It builds React elements
// directly — never innerHTML — because the README is repo content and this
// origin can commit and push: a <script> in someone's README must stay text.
// Covers what READMEs actually use: headings, paragraphs, lists, fenced code,
// quotes, rules, tables, and inline code / bold / italic / links. Raw HTML and
// images are dropped, and only http(s) links are clickable.

const SAFE_URL = /^https?:\/\//i;

// Linked images first (`[![CI](badge.svg)](url)` — badge rows), then bare
// images: neither can load from a local README, and badges are noise here.
const IMAGES = /\[!\[[^\]]*\]\([^)]*\)\]\([^)]*\)|!\[[^\]]*\]\([^)]*\)/g;

function inline(raw: string, key = "i"): ReactNode[] {
  const text = raw.replace(IMAGES, "").replace(/ {2,}/g, " ");
  const out: ReactNode[] = [];
  // order matters: code first so its contents are not parsed further
  const re = /(`[^`]+`)|(!\[([^\]]*)\]\([^)]*\))|(\[([^\]]+)\]\(([^)\s]+)[^)]*\))|(\*\*([^*]+)\*\*|__([^_]+)__)|(\*([^*\s][^*]*)\*|_([^_\s][^_]*)_)|(<[^>]+>)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let n = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const k = `${key}-${n++}`;
    if (m[1]) out.push(<code key={k} className="rounded bg-surface px-1 py-0.5 font-mono text-[0.85em]">{m[1].slice(1, -1)}</code>);
    else if (m[2]) { /* image — already stripped above; kept so the groups stay aligned */ }
    else if (m[4]) {
      const url = m[6];
      out.push(SAFE_URL.test(url)
        ? <a key={k} href={url} target="_blank" rel="noreferrer noopener" className="text-primary-container hover:underline">{inline(m[5], k)}</a>
        : <span key={k}>{inline(m[5], k)}</span>);
    }
    else if (m[7]) out.push(<strong key={k}>{inline(m[8] ?? m[9], k)}</strong>);
    else if (m[10]) out.push(<em key={k}>{inline(m[11] ?? m[12], k)}</em>);
    // m[13]: raw HTML tag — dropped
    last = re.lastIndex;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

const H_CLS = ["text-xl font-bold", "text-lg font-semibold", "text-base font-semibold", "text-sm font-semibold", "text-sm font-semibold", "text-sm font-medium"];

function isTableSep(line: string) {
  return /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(line);
}

function cells(line: string) {
  return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
}

export function Markdown({ source }: { source: string }) {
  const lines = source.replace(/\r\n?/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let i = 0;
  let b = 0;
  const key = () => `b${b++}`;

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();

    if (!trimmed) { i++; continue; }

    const fence = trimmed.match(/^(```|~~~)/);
    if (fence) {
      const body: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith(fence[1])) body.push(lines[i++]);
      i++;
      blocks.push(<pre key={key()} className="overflow-x-auto rounded bg-surface px-3 py-2 font-mono text-xs">{body.join("\n")}</pre>);
      continue;
    }

    const h = trimmed.match(/^(#{1,6})\s+(.*?)\s*#*$/);
    if (h) {
      blocks.push(<div key={key()} className={`${H_CLS[h[1].length - 1]} mt-2`}>{inline(h[2])}</div>);
      i++;
      continue;
    }

    if (/^(-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
      blocks.push(<hr key={key()} className="border-border-card" />);
      i++;
      continue;
    }

    if (trimmed.includes("|") && i + 1 < lines.length && isTableSep(lines[i + 1])) {
      const head = cells(line);
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && lines[i].includes("|") && lines[i].trim()) rows.push(cells(lines[i++]));
      blocks.push(
        <div key={key()} className="overflow-x-auto">
          <table className="text-xs">
            <thead><tr>{head.map((c, j) => <th key={j} className="border border-border-card px-2 py-1 text-left font-semibold">{inline(c)}</th>)}</tr></thead>
            <tbody>{rows.map((r, ri) => <tr key={ri}>{r.map((c, j) => <td key={j} className="border border-border-card px-2 py-1 align-top">{inline(c)}</td>)}</tr>)}</tbody>
          </table>
        </div>,
      );
      continue;
    }

    if (trimmed.startsWith(">")) {
      const body: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith(">")) body.push(lines[i++].trim().replace(/^>\s?/, ""));
      blocks.push(<blockquote key={key()} className="border-l-4 border-border-card pl-3 text-on-surface-variant">{inline(body.join(" "))}</blockquote>);
      continue;
    }

    const li = /^\s*([-*+]|\d+[.)])\s+(.*)$/;
    if (li.test(line)) {
      const ordered = /^\s*\d/.test(line);
      const items: { depth: number; text: string }[] = [];
      while (i < lines.length && li.test(lines[i])) {
        const mm = lines[i].match(li)!;
        const depth = Math.min(3, Math.floor((lines[i].match(/^\s*/)![0].length) / 2));
        items.push({ depth, text: mm[2].replace(/^\[( |x|X)\]\s+/, (s) => (s.includes(" ]") ? "☐ " : "☑ ")) });
        i++;
      }
      const Tag = ordered ? "ol" : "ul";
      blocks.push(
        <Tag key={key()} className={`${ordered ? "list-decimal" : "list-disc"} space-y-0.5 pl-5`}>
          {items.map((it, j) => <li key={j} style={{ marginLeft: it.depth * 16 }}>{inline(it.text)}</li>)}
        </Tag>,
      );
      continue;
    }

    // HTML-only lines (centered logos, <br>, <details>) carry nothing once tags are dropped
    if (/^<[^>]+>$/.test(trimmed) || /^<\/?[a-z][^>]*>(\s*<\/?[a-z][^>]*>)*$/i.test(trimmed)) { i++; continue; }

    const para: string[] = [];
    while (i < lines.length && lines[i].trim() && !/^(#{1,6}\s|```|~~~|>)/.test(lines[i].trim()) && !li.test(lines[i])
      && !(lines[i].includes("|") && i + 1 < lines.length && isTableSep(lines[i + 1]))) {
      para.push(lines[i++].trim());
    }
    const body = inline(para.join(" ")).filter((n) => typeof n !== "string" || n.trim());
    if (body.length) blocks.push(<p key={key()} className="leading-relaxed">{body}</p>);
  }

  return <div className="space-y-2 text-sm">{blocks}</div>;
}
