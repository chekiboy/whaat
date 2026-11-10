import type { ReactNode } from "react";

/* The markdown subset a curation report uses, and nothing beyond it: paragraphs (lines joined),
   nested `-`/`*` lists with continuation lines, `>` quotes, fenced code (a diff block colours + and - lines), tables
   (cells split on " | "), `<details>` blocks with their summary, ### and #### headings, and inline `code`, **bold**
   and http(s) links. */

type Block = ReactNode;

export function Markdown({ text }: { text: string }) {
  return <div className="cur-md">{blocks(text.split("\n"))}</div>;
}

function blocks(lines: string[]): Block[] {
  const out: Block[] = [];
  let i = 0;
  let key = 0;
  while (i < lines.length) {
    const line = lines[i] ?? "";
    const trimmed = line.trim();
    if (!trimmed) {
      i++;
      continue;
    }
    if (trimmed.startsWith("```")) {
      const lang = trimmed.slice(3).trim();
      const body: string[] = [];
      i++;
      while (i < lines.length && !(lines[i] ?? "").trim().startsWith("```")) body.push(lines[i++] ?? "");
      i++;
      out.push(
        <pre key={key++}>
          {body.map((codeLine, n) => {
            const cls =
              lang === "diff" && codeLine.startsWith("+") && !codeLine.startsWith("+++")
                ? "d-add"
                : lang === "diff" && codeLine.startsWith("-") && !codeLine.startsWith("---")
                  ? "d-del"
                  : undefined;
            return (
              // biome-ignore lint/suspicious/noArrayIndexKey: lines of one fixed block
              <span key={n} className={cls}>
                {codeLine}
                {"\n"}
              </span>
            );
          })}
        </pre>,
      );
      continue;
    }
    if (trimmed.startsWith("<details")) {
      const inner: string[] = [];
      let summary = "Details";
      const first = trimmed.match(/<summary>(.*?)<\/summary>/);
      if (first?.[1]) summary = first[1];
      i++;
      let depth = 1;
      while (i < lines.length) {
        const current = lines[i] ?? "";
        if (current.includes("<details")) depth++;
        if (current.includes("</details>")) {
          depth--;
          if (depth === 0) break;
        }
        const s = current.match(/^\s*<summary>(.*?)<\/summary>\s*$/);
        if (s?.[1] && inner.length === 0 && summary === "Details") summary = s[1];
        else inner.push(current);
        i++;
      }
      i++;
      out.push(
        <details key={key++} className="cur-md-details">
          <summary>{inline(summary)}</summary>
          {blocks(inner)}
        </details>,
      );
      continue;
    }
    const heading = trimmed.match(/^(#{3,4})\s+(.*)$/);
    if (heading) {
      const content = inline(heading[2] ?? "");
      out.push(heading[1] === "###" ? <h3 key={key++}>{content}</h3> : <h4 key={key++}>{content}</h4>);
      i++;
      continue;
    }
    if (trimmed.startsWith("|")) {
      const rows: string[][] = [];
      while (i < lines.length && (lines[i] ?? "").trim().startsWith("|")) {
        rows.push(cells(lines[i] ?? ""));
        i++;
      }
      const [header, , ...body] = rows;
      out.push(
        <table key={key++} className="cur-md-table">
          <thead>
            <tr>
              {(header ?? []).map((cell, n) => (
                // biome-ignore lint/suspicious/noArrayIndexKey: cells of one fixed row
                <th key={n}>{inline(cell)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {body.map((row, r) => (
              // biome-ignore lint/suspicious/noArrayIndexKey: rows of one fixed table
              <tr key={r}>
                {row.map((cell, n) => (
                  // biome-ignore lint/suspicious/noArrayIndexKey: cells of one fixed row
                  <td key={n}>{inline(cell)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>,
      );
      continue;
    }
    if (trimmed.startsWith(">")) {
      const quote: string[] = [];
      while (i < lines.length && (lines[i] ?? "").trim().startsWith(">")) {
        quote.push((lines[i] ?? "").trim().replace(/^>\s?/, ""));
        i++;
      }
      out.push(<blockquote key={key++}>{inline(quote.join(" "))}</blockquote>);
      continue;
    }
    if (/^\s*[-*]\s+/.test(line)) {
      const items: { depth: number; text: string }[] = [];
      while (i < lines.length) {
        const current = lines[i] ?? "";
        const bullet = current.match(/^(\s*)[-*]\s+(.*)$/);
        if (bullet) {
          items.push({ depth: Math.floor((bullet[1] ?? "").length / 2), text: bullet[2] ?? "" });
        } else if (current.trim() && items.length && !current.trim().startsWith("|")) {
          const last = items[items.length - 1];
          if (last) last.text += ` ${current.trim()}`;
        } else break;
        i++;
      }
      out.push(<List key={key++} items={items} />);
      continue;
    }
    const paragraph: string[] = [];
    while (
      i < lines.length &&
      (lines[i] ?? "").trim() &&
      !/^\s*([-*]\s|\||>|```|<details|#{3,4}\s)/.test(lines[i] ?? "")
    ) {
      paragraph.push((lines[i] ?? "").trim());
      i++;
    }
    if (paragraph.length === 0) {
      paragraph.push(trimmed);
      i++;
    }
    out.push(<p key={key++}>{inline(paragraph.join(" "))}</p>);
  }
  return out;
}

function List({ items }: { items: { depth: number; text: string }[] }) {
  const build = (start: number, depth: number): [ReactNode[], number] => {
    const nodes: ReactNode[] = [];
    let i = start;
    while (i < items.length) {
      const item = items[i];
      if (!item || item.depth < depth) break;
      if (item.depth > depth) {
        const [children, next] = build(i, item.depth);
        nodes.push(<ul key={`u${i}`}>{children}</ul>);
        i = next;
        continue;
      }
      const next = items[i + 1];
      if (next && next.depth > depth) {
        const [children, after] = build(i + 1, next.depth);
        nodes.push(
          <li key={i}>
            {inline(item.text)}
            <ul>{children}</ul>
          </li>,
        );
        i = after;
      } else {
        nodes.push(<li key={i}>{inline(item.text)}</li>);
        i++;
      }
    }
    return [nodes, i];
  };
  return <ul>{build(0, items[0]?.depth ?? 0)[0]}</ul>;
}

function cells(line: string): string[] {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split(" | ")
    .map((cell) => cell.trim());
}

export function inline(text: string): ReactNode {
  return text.split(/(`[^`]+`)/).map((part, index) => {
    if (part.length > 1 && part.startsWith("`") && part.endsWith("`"))
      // biome-ignore lint/suspicious/noArrayIndexKey: the parts of one fixed string
      return <code key={index}>{part.slice(1, -1)}</code>;
    return (
      // biome-ignore lint/suspicious/noArrayIndexKey: the parts of one fixed string
      <span key={index}>
        {part.split(/(\*\*.+?\*\*|\[[^\]]+\]\(https?:\/\/[^)]+\))/).map((bit, j) => {
          if (bit.length > 4 && bit.startsWith("**") && bit.endsWith("**"))
            // biome-ignore lint/suspicious/noArrayIndexKey: the parts of one fixed string
            return <strong key={j}>{bit.slice(2, -2)}</strong>;
          const link = bit.match(/^\[([^\]]+)\]\((https?:\/\/[^)]+)\)$/);
          if (link)
            return (
              // biome-ignore lint/suspicious/noArrayIndexKey: the parts of one fixed string
              <a key={j} href={link[2]} target="_blank" rel="noreferrer">
                {link[1]}
              </a>
            );
          return bit;
        })}
      </span>
    );
  });
}
