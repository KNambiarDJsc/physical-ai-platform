/**
 * A deliberately small Markdown reader for the agent's answers: headings, paragraphs, bullet and numbered lists, bold,
 * inline code and pipe tables (kept as aligned text). It produces data, never HTML: the page renders it with React
 * elements, so nothing a model writes can inject markup. Anything it does not know stays as plain text.
 */

export type Inline = { kind: "text" | "bold" | "code"; text: string };

export type Block =
  | { kind: "heading"; level: 1 | 2 | 3; inline: Inline[] }
  | { kind: "paragraph"; inline: Inline[] }
  | { kind: "list"; ordered: boolean; items: Inline[][] }
  | { kind: "pre"; text: string };

export function parseInline(s: string): Inline[] {
  const out: Inline[] = [];
  for (const part of s.split(/(\*\*[^\s*](?:[^*\n]*[^\s*])?\*\*|`[^`\n]+`)/)) {
    if (!part) continue;
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) out.push({ kind: "bold", text: part.slice(2, -2) });
    else if (part.startsWith("`") && part.endsWith("`") && part.length > 2) out.push({ kind: "code", text: part.slice(1, -1) });
    else out.push({ kind: "text", text: part });
  }
  return out;
}

const HEADING = /^(#{1,3})\s+(.*\S)\s*$/;
const BULLET = /^\s*[-*]\s+(.*\S)\s*$/;
const NUMBERED = /^\s*\d+[.)]\s+(.*\S)\s*$/;
const RULE = /^\s*(-{3,}|\*{3,}|_{3,})\s*$/;
const TABLE = /^\s*\|.*\|\s*$/;

export function parseMarkdown(text: string): Block[] {
  const blocks: Block[] = [];
  let para: string[] = [];
  let list: { ordered: boolean; items: Inline[][] } | null = null;
  let table: string[] = [];

  const flush = () => {
    if (para.length) blocks.push({ kind: "paragraph", inline: parseInline(para.join("\n")) });
    if (list) blocks.push({ kind: "list", ordered: list.ordered, items: list.items });
    if (table.length) blocks.push({ kind: "pre", text: table.join("\n") });
    para = [];
    list = null;
    table = [];
  };

  for (const raw of text.replace(/\r\n?/g, "\n").split("\n")) {
    const line = raw.trimEnd();
    if (!line.trim()) {
      flush();
      continue;
    }
    if (RULE.test(line)) {
      flush();
      continue;
    }
    const h = HEADING.exec(line);
    if (h) {
      flush();
      blocks.push({ kind: "heading", level: h[1]!.length as 1 | 2 | 3, inline: parseInline(h[2]!) });
      continue;
    }
    if (TABLE.test(line)) {
      if (para.length || list) flush();
      table.push(line);
      continue;
    }
    const b = BULLET.exec(line);
    const n = b ? null : NUMBERED.exec(line);
    if (b || n) {
      const ordered = !b;
      if (para.length || table.length || (list && list.ordered !== ordered)) flush();
      if (!list) list = { ordered, items: [] };
      list.items.push(parseInline((b ?? n)![1]!));
      continue;
    }
    if (list || table.length) flush();
    para.push(line.trim());
  }
  flush();
  return blocks;
}
