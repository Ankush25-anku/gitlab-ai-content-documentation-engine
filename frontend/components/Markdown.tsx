"use client";

import { Fragment, ReactNode } from "react";

/**
 * Small, safe Markdown renderer for drafts (no raw HTML is ever injected).
 * Renders [S#] citations as clickable markers and [NEEDS SOURCE: ...] as a highlighted gap.
 */
interface Props {
  markdown: string;
  validIds?: Set<string>;
  activeId?: string | null;
  onCite?: (id: string) => void;
  flagged?: string[]; // claim texts to highlight as unsupported
}

function inline(text: string, p: Props, key: string): ReactNode[] {
  const out: ReactNode[] = [];
  const re = /(`[^`]+`|\[S\d+\]|\[NEEDS SOURCE:[^\]]*\]|\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\))/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const tok = m[0];
    const k = `${key}-${i++}`;
    if (tok.startsWith("`")) out.push(<code key={k}>{tok.slice(1, -1)}</code>);
    else if (/^\[S\d+\]$/.test(tok)) {
      const id = tok.slice(1, -1);
      out.push(
        <button key={k} type="button" className="cite" data-active={p.activeId === id}
          data-invalid={p.validIds ? !p.validIds.has(id) : false}
          onClick={() => p.onCite?.(id)} aria-label={`Show source ${id}`}>{id}</button>);
    } else if (tok.startsWith("[NEEDS SOURCE")) out.push(<span key={k} className="needs">{tok.slice(1, -1)}</span>);
    else if (tok.startsWith("**")) out.push(<strong key={k}>{tok.slice(2, -2)}</strong>);
    else {
      const lm = /\[([^\]]+)\]\(([^)]+)\)/.exec(tok)!;
      const href = /^https?:\/\//.test(lm[2]) ? lm[2] : "#";
      out.push(<a key={k} href={href} className="text-accent underline" target="_blank" rel="noreferrer">{lm[1]}</a>);
    }
    last = m.index + tok.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

function sentenceAware(text: string, p: Props, key: string): ReactNode {
  if (!p.flagged?.length) return inline(text, p, key);
  const plain = (s: string) => s.replace(/\s?\[S\d+\]/g, "").replace(/\s+([.,;:!?])/g, "$1").trim();
  const parts = text.split(/(?<=[.!?])\s+/);
  return parts.map((s, i) => {
    const hit = p.flagged!.some((f) => plain(s) === f.trim());
    const node = inline(s, p, `${key}-${i}`);
    return <Fragment key={i}>{hit ? <mark className="flagged">{node}</mark> : node}{i < parts.length - 1 ? " " : ""}</Fragment>;
  });
}

export default function Markdown(props: Props) {
  const lines = props.markdown.split("\n");
  const blocks: ReactNode[] = [];
  let i = 0;
  let n = 0;
  while (i < lines.length) {
    const line = lines[i];
    const key = `b${n++}`;
    if (line.startsWith("```")) {
      const code: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) code.push(lines[i++]);
      i++;
      blocks.push(<pre key={key}><code>{code.join("\n")}</code></pre>);
      continue;
    }
    if (/^#{1,3}\s/.test(line)) {
      const level = line.match(/^#+/)![0].length;
      const text = line.replace(/^#+\s/, "");
      blocks.push(level === 1 ? <h1 key={key}>{inline(text, props, key)}</h1> :
        level === 2 ? <h2 key={key}>{inline(text, props, key)}</h2> : <h3 key={key}>{inline(text, props, key)}</h3>);
      i++;
      continue;
    }
    if (line.startsWith("|")) {
      const rows: string[][] = [];
      while (i < lines.length && lines[i].startsWith("|")) {
        if (!/^\|[\s:|-]+\|$/.test(lines[i])) rows.push(lines[i].split("|").slice(1, -1).map((c) => c.trim()));
        i++;
      }
      const [head, ...body] = rows;
      blocks.push(
        <table key={key}><thead><tr>{head.map((c, j) => <th key={j}>{inline(c, props, `${key}h${j}`)}</th>)}</tr></thead>
          <tbody>{body.map((r, ri) => <tr key={ri}>{r.map((c, j) => <td key={j}>{sentenceAware(c, props, `${key}${ri}${j}`)}</td>)}</tr>)}</tbody>
        </table>);
      continue;
    }
    if (/^(\d+\.|[-*])\s/.test(line)) {
      const ordered = /^\d+\./.test(line);
      const items: string[] = [];
      while (i < lines.length && /^(\d+\.|[-*])\s/.test(lines[i])) items.push(lines[i++].replace(/^(\d+\.|[-*])\s/, ""));
      const li = items.map((t, j) => <li key={j}>{sentenceAware(t, props, `${key}${j}`)}</li>);
      blocks.push(ordered ? <ol key={key}>{li}</ol> : <ul key={key}>{li}</ul>);
      continue;
    }
    if (!line.trim()) { i++; continue; }
    const para: string[] = [];
    while (i < lines.length && lines[i].trim() && !/^(#{1,3}\s|```|\||\d+\.\s|[-*]\s)/.test(lines[i])) para.push(lines[i++]);
    blocks.push(<p key={key}>{sentenceAware(para.join(" "), props, key)}</p>);
  }
  return <div className="doc">{blocks}</div>;
}
