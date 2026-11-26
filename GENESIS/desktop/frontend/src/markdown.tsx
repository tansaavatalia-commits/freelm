// Small, safe Markdown renderer for chat answers: builds React elements (never innerHTML), so text from a
// model can never inject markup. Supports headings, paragraphs, lists, code blocks, `code`, **bold**, _italic_
// (a single `*` is left alone: it is usually a multiplication).
import { Fragment, type ReactNode } from "react";

function inline(text: string, key: string): ReactNode[] {
  const out: ReactNode[] = [];
  const re = /(`[^`\n]+`|\*\*[^*\n]+\*\*|(?<![\w])_[^_\n]+_(?![\w]))/g;
  let last = 0;
  let i = 0;
  for (const m of text.matchAll(re)) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const token = m[0];
    const k = `${key}-${i++}`;
    if (token.startsWith("`")) out.push(<code key={k}>{token.slice(1, -1)}</code>);
    else if (token.startsWith("**")) out.push(<strong key={k}>{token.slice(2, -2)}</strong>);
    else out.push(<em key={k}>{token.slice(1, -1)}</em>);
    last = m.index + token.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export function Markdown({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  const parts = text.split(/```/);
  parts.forEach((part, pi) => {
    if (pi % 2 === 1) { // code block (first line may name the language)
      const body = part.replace(/^[\w+-]*\n/, "");
      blocks.push(<pre key={`c${pi}`} className="md-code"><code>{body.replace(/\n$/, "")}</code></pre>);
      return;
    }
    let list: { ordered: boolean; items: string[] } | null = null;
    let para: string[] = [];
    const flushPara = (k: string) => {
      if (para.length) blocks.push(<p key={k}>{inline(para.join(" "), k)}</p>);
      para = [];
    };
    const flushList = (k: string) => {
      if (!list) return;
      const items = list.items.map((it, j) => <li key={j}>{inline(it, `${k}-${j}`)}</li>);
      blocks.push(list.ordered ? <ol key={k}>{items}</ol> : <ul key={k}>{items}</ul>);
      list = null;
    };
    part.split("\n").forEach((line, li) => {
      const k = `b${pi}-${li}`;
      const heading = /^(#{1,4})\s+(.*)$/.exec(line);
      const bullet = /^\s*[-*•]\s+(.*)$/.exec(line);
      const numbered = /^\s*\d+[.)]\s+(.*)$/.exec(line);
      if (heading) {
        flushPara(`${k}p`); flushList(`${k}l`);
        blocks.push(<h4 key={k} className="md-h">{inline(heading[2], k)}</h4>);
      } else if (bullet || numbered) {
        flushPara(`${k}p`);
        const ordered = Boolean(numbered);
        if (list && list.ordered !== ordered) flushList(`${k}l`);
        if (!list) list = { ordered, items: [] };
        list.items.push((bullet ?? numbered)![1]);
      } else if (!line.trim()) {
        flushPara(`${k}p`); flushList(`${k}l`);
      } else {
        flushList(`${k}l`);
        para.push(line.trim());
      }
    });
    flushPara(`e${pi}p`); flushList(`e${pi}l`);
  });
  return <Fragment>{blocks}</Fragment>;
}
