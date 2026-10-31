import { useState, type ReactNode } from 'react';
import MermaidDiagram from './MermaidDiagram';

// Minimal, dependency-free Markdown renderer for chat + docs.
// Builds React elements only (never injects HTML), so agent output is safe to render. The one exception is a
// ```mermaid block, drawn by MermaidDiagram in mermaid's strict mode.
// Supports: headings, paragraphs, bold/italic/strike, inline code, links,
// bullet/numbered/task lists, blockquotes, tables, rules, and fenced code callouts.

const FENCE = /^\s*(```|~~~)\s*([\w+#.-]*)\s*$/;
const HEADING = /^(#{1,6})\s+(.*?)\s*#*\s*$/;
const RULE = /^\s*([-*_])(\s*\1){2,}\s*$/;
const UL = /^(\s*)[-*+]\s+(.*)$/;
const OL = /^(\s*)(\d+)[.)]\s+(.*)$/;
const QUOTE = /^\s*>\s?(.*)$/;
const TABLE_SEP = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;

function CodeCallout({ code, lang }: { code: string; lang: string }) {
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(false);
  const copy = () => {
    setCopyError(false);
    if (!navigator.clipboard) { setCopyError(true); return; }
    void navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }).catch(() => setCopyError(true));
  };
  return (
    <div className="codeblock">
      <div className="codeblock-head">
        <span>{lang || 'code'}</span>
        <button className="ghost copy-btn" onClick={copy}>
          {copied ? 'Copied' : copyError ? 'Select to copy' : 'Copy'}
        </button>
      </div>
      <pre>
        <code>{code}</code>
      </pre>
    </div>
  );
}

// ---------------------------------------------------------------- inline
const INLINE =
  /(`+)([\s\S]*?[^`])\1(?!`)|\*\*([\s\S]+?)\*\*|__([\s\S]+?)__|~~([\s\S]+?)~~|\*([^*\s][^*]*?)\*|(?<![\w])_([^_\s][^_]*?)_(?![\w])|\[([^\]]+)\]\(([^)\s]+)\)|(https?:\/\/[^\s<>()]+[^\s<>().,;:!?'"])/g;

function safeHref(url: string): string | undefined {
  return /^(https?:|mailto:|#|\/)/i.test(url) ? url : undefined;
}

function inline(text: string, keyBase = 'i'): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  let k = 0;
  for (const m of text.matchAll(INLINE)) {
    const idx = m.index ?? 0;
    if (idx > last) out.push(text.slice(last, idx));
    const key = `${keyBase}-${k++}`;
    if (m[2] !== undefined) out.push(<code key={key} className="inline-code">{m[2].trim()}</code>);
    else if (m[3] !== undefined || m[4] !== undefined)
      out.push(<strong key={key}>{inline(m[3] ?? m[4] ?? '', key)}</strong>);
    else if (m[5] !== undefined) out.push(<del key={key}>{inline(m[5], key)}</del>);
    else if (m[6] !== undefined || m[7] !== undefined)
      out.push(<em key={key}>{inline(m[6] ?? m[7] ?? '', key)}</em>);
    else if (m[8] !== undefined)
      out.push(
        <a key={key} href={safeHref(m[9] ?? '')} target="_blank" rel="noreferrer">
          {inline(m[8], key)}
        </a>,
      );
    else if (m[10] !== undefined)
      out.push(
        <a key={key} href={m[10]} target="_blank" rel="noreferrer">
          {m[10]}
        </a>,
      );
    last = idx + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

function withBreaks(lines: string[], keyBase: string): ReactNode[] {
  return lines.flatMap((l, i) =>
    i === 0 ? inline(l, `${keyBase}-${i}`) : [<br key={`${keyBase}-br${i}`} />, ...inline(l, `${keyBase}-${i}`)],
  );
}

// ---------------------------------------------------------------- blocks
function splitRow(line: string): string[] {
  return line
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map((c) => c.trim());
}

interface ListItem {
  depth: number;
  text: string[];
}

function renderList(items: ListItem[], ordered: boolean, start: number, key: string): ReactNode {
  // Group items by depth into a nested tree (one level of nesting per indent step).
  const base = Math.min(...items.map((i) => i.depth));
  const top: { item: ListItem; children: ListItem[] }[] = [];
  for (const it of items) {
    const parent = top[top.length - 1];
    if (it.depth > base && parent) parent.children.push(it);
    else top.push({ item: it, children: [] });
  }
  const Tag = ordered ? 'ol' : 'ul';
  return (
    <Tag key={key} start={ordered && start !== 1 ? start : undefined}>
      {top.map(({ item, children }, i) => {
        const first = item.text[0] ?? '';
        const task = first.match(/^\[([ xX])\]\s+(.*)$/);
        const lines = task ? [task[2] ?? '', ...item.text.slice(1)] : item.text;
        return (
          <li key={i} className={task ? 'task' : undefined}>
            {task && <span className="task-box">{task[1] === ' ' ? '☐' : '☑'}</span>}
            {withBreaks(lines, `${key}-${i}`)}
            {children.length > 0 && renderList(children, ordered, 1, `${key}-${i}-c`)}
          </li>
        );
      })}
    </Tag>
  );
}

function blocks(src: string): ReactNode[] {
  const lines = src.replace(/\r\n?/g, '\n').split('\n');
  const out: ReactNode[] = [];
  let i = 0;
  const key = () => `b${out.length}`;

  while (i < lines.length) {
    const line = lines[i] ?? '';

    if (!line.trim()) {
      i++;
      continue;
    }

    const fence = line.match(FENCE);
    if (fence) {
      const body: string[] = [];
      i++;
      // An unterminated fence (e.g. mid-stream) runs to the end of the text.
      while (i < lines.length && !(lines[i] ?? '').trim().startsWith(fence[1] ?? '```')) body.push(lines[i++] ?? '');
      i++;
      const code = body.join('\n');
      const callout = <CodeCallout code={code} lang={fence[2] ?? ''} />;
      out.push(fence[2] === 'mermaid' ? <MermaidDiagram key={key()} code={code} fallback={callout} /> : <CodeCallout key={key()} code={code} lang={fence[2] ?? ''} />);
      continue;
    }

    const h = line.match(HEADING);
    if (h) {
      const level = Math.min((h[1] ?? '#').length + 1, 6); // h1 → h2 so docs don't shout
      const Tag = `h${level}` as 'h2';
      out.push(<Tag key={key()}>{inline(h[2] ?? '')}</Tag>);
      i++;
      continue;
    }

    if (RULE.test(line)) {
      out.push(<hr key={key()} />);
      i++;
      continue;
    }

    if (line.includes('|') && TABLE_SEP.test(lines[i + 1] ?? '')) {
      const head = splitRow(line);
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && (lines[i] ?? '').includes('|') && (lines[i] ?? '').trim()) rows.push(splitRow(lines[i++] ?? ''));
      const k = key();
      out.push(
        <div key={k} className="table-wrap">
          <table>
            <thead>
              <tr>{head.map((c, j) => <th key={j}>{inline(c, `${k}h${j}`)}</th>)}</tr>
            </thead>
            <tbody>
              {rows.map((r, ri) => (
                <tr key={ri}>{head.map((_, j) => <td key={j}>{inline(r[j] ?? '', `${k}r${ri}c${j}`)}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }

    if (QUOTE.test(line)) {
      const body: string[] = [];
      while (i < lines.length && QUOTE.test(lines[i] ?? '')) body.push((lines[i++] ?? '').match(QUOTE)?.[1] ?? '');
      out.push(<blockquote key={key()}>{blocks(body.join('\n'))}</blockquote>);
      continue;
    }

    const ul = line.match(UL);
    const ol = line.match(OL);
    if (ul || ol) {
      const ordered = !!ol && !ul;
      const start = ordered ? Number(ol?.[2] ?? 1) : 1;
      const items: ListItem[] = [];
      while (i < lines.length) {
        const l = lines[i] ?? '';
        const m = ordered ? l.match(OL) : l.match(UL);
        if (m) {
          items.push({ depth: (m[1] ?? '').length, text: [(ordered ? m[3] : m[2]) ?? ''] });
          i++;
        } else if (l.trim() && /^\s{2,}/.test(l) && items.length && !FENCE.test(l)) {
          items[items.length - 1]?.text.push(l.trim()); // indented continuation line
          i++;
        } else break;
      }
      out.push(renderList(items, ordered, start, key()));
      continue;
    }

    const para: string[] = [];
    while (i < lines.length) {
      const l = lines[i] ?? '';
      if (!l.trim() || FENCE.test(l) || HEADING.test(l) || RULE.test(l) || QUOTE.test(l) || UL.test(l) || OL.test(l)) break;
      if (l.includes('|') && TABLE_SEP.test(lines[i + 1] ?? '')) break;
      para.push(l);
      i++;
    }
    const k = key();
    out.push(<p key={k}>{withBreaks(para, k)}</p>);
  }
  return out;
}

export default function Markdown({ text, className }: { text: string; className?: string }) {
  return <div className={`markdown ${className ?? ''}`}>{blocks(text)}</div>;
}
