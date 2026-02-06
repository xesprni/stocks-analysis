import { Fragment } from "react";

type MarkdownViewerProps = {
  markdown: string;
};

type MarkdownBlock =
  | { type: "heading"; level: number; text: string }
  | { type: "paragraph"; text: string }
  | { type: "code"; language: string; code: string }
  | { type: "blockquote"; lines: string[] }
  | { type: "ul"; items: string[] }
  | { type: "ol"; items: string[] };

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function inlineMarkdownToHtml(text: string): string {
  let html = escapeHtml(text);
  html = html.replace(
    /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
    '<a href="$2" target="_blank" rel="noreferrer" class="underline decoration-zinc-400 underline-offset-4 hover:decoration-zinc-900">$1</a>'
  );
  html = html.replace(/`([^`]+)`/g, '<code class="rounded bg-zinc-100 px-1.5 py-0.5 text-[0.88em] text-zinc-900">$1</code>');
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\*([^*]+)\*/g, "<em>$1</em>");
  return html;
}

function parseMarkdown(markdown: string): MarkdownBlock[] {
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  const blocks: MarkdownBlock[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    const trimmed = line.trim();

    if (!trimmed) {
      index += 1;
      continue;
    }

    if (trimmed.startsWith("```")) {
      const language = trimmed.slice(3).trim();
      const codeLines: string[] = [];
      index += 1;
      while (index < lines.length && !lines[index].trim().startsWith("```")) {
        codeLines.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) {
        index += 1;
      }
      blocks.push({
        type: "code",
        language,
        code: codeLines.join("\n"),
      });
      continue;
    }

    const headingMatch = trimmed.match(/^(#{1,6})\s+(.*)$/);
    if (headingMatch) {
      blocks.push({
        type: "heading",
        level: headingMatch[1].length,
        text: headingMatch[2],
      });
      index += 1;
      continue;
    }

    if (trimmed.startsWith(">")) {
      const quoteLines: string[] = [];
      while (index < lines.length && lines[index].trim().startsWith(">")) {
        quoteLines.push(lines[index].trim().replace(/^>\s?/, ""));
        index += 1;
      }
      blocks.push({ type: "blockquote", lines: quoteLines });
      continue;
    }

    if (/^[-*]\s+/.test(trimmed)) {
      const items: string[] = [];
      while (index < lines.length && /^[-*]\s+/.test(lines[index].trim())) {
        items.push(lines[index].trim().replace(/^[-*]\s+/, ""));
        index += 1;
      }
      blocks.push({ type: "ul", items });
      continue;
    }

    if (/^\d+\.\s+/.test(trimmed)) {
      const items: string[] = [];
      while (index < lines.length && /^\d+\.\s+/.test(lines[index].trim())) {
        items.push(lines[index].trim().replace(/^\d+\.\s+/, ""));
        index += 1;
      }
      blocks.push({ type: "ol", items });
      continue;
    }

    const paragraphLines: string[] = [];
    while (index < lines.length) {
      const current = lines[index].trim();
      if (!current) {
        break;
      }
      if (
        current.startsWith("```") ||
        /^#{1,6}\s+/.test(current) ||
        current.startsWith(">") ||
        /^[-*]\s+/.test(current) ||
        /^\d+\.\s+/.test(current)
      ) {
        break;
      }
      paragraphLines.push(lines[index].trim());
      index += 1;
    }
    if (paragraphLines.length) {
      blocks.push({ type: "paragraph", text: paragraphLines.join(" ") });
      continue;
    }

    index += 1;
  }

  return blocks;
}

export function MarkdownViewer({ markdown }: MarkdownViewerProps) {
  const blocks = parseMarkdown(markdown);

  if (!blocks.length) {
    return <div className="text-sm text-muted-foreground">暂无内容</div>;
  }

  return (
    <article className="prose prose-zinc max-w-none rounded-xl border border-border/70 bg-white p-5">
      {blocks.map((block, blockIndex) => {
        switch (block.type) {
          case "heading": {
            const classNameByLevel: Record<number, string> = {
              1: "mb-3 mt-6 text-2xl font-semibold tracking-tight",
              2: "mb-2 mt-5 text-xl font-semibold tracking-tight",
              3: "mb-2 mt-4 text-lg font-semibold",
              4: "mb-2 mt-4 text-base font-semibold",
              5: "mb-1 mt-3 text-sm font-semibold uppercase tracking-wide",
              6: "mb-1 mt-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground",
            };
            const cls = classNameByLevel[block.level] ?? classNameByLevel[3];
            const Tag = `h${Math.min(6, Math.max(1, block.level))}` as keyof JSX.IntrinsicElements;
            return (
              <Tag
                key={`heading-${blockIndex}`}
                className={cls}
                dangerouslySetInnerHTML={{ __html: inlineMarkdownToHtml(block.text) }}
              />
            );
          }
          case "paragraph":
            return (
              <p
                key={`paragraph-${blockIndex}`}
                className="mb-3 text-[15px] leading-7 text-zinc-800"
                dangerouslySetInnerHTML={{ __html: inlineMarkdownToHtml(block.text) }}
              />
            );
          case "blockquote":
            return (
              <blockquote key={`quote-${blockIndex}`} className="my-4 border-l-4 border-zinc-300 pl-4 text-zinc-700">
                {block.lines.map((line, lineIndex) => (
                  <p
                    key={`quote-line-${blockIndex}-${lineIndex}`}
                    className="mb-1"
                    dangerouslySetInnerHTML={{ __html: inlineMarkdownToHtml(line) }}
                  />
                ))}
              </blockquote>
            );
          case "ul":
            return (
              <ul key={`ul-${blockIndex}`} className="mb-4 list-disc space-y-1 pl-6 text-zinc-800">
                {block.items.map((item, itemIndex) => (
                  <li
                    key={`ul-item-${blockIndex}-${itemIndex}`}
                    dangerouslySetInnerHTML={{ __html: inlineMarkdownToHtml(item) }}
                  />
                ))}
              </ul>
            );
          case "ol":
            return (
              <ol key={`ol-${blockIndex}`} className="mb-4 list-decimal space-y-1 pl-6 text-zinc-800">
                {block.items.map((item, itemIndex) => (
                  <li
                    key={`ol-item-${blockIndex}-${itemIndex}`}
                    dangerouslySetInnerHTML={{ __html: inlineMarkdownToHtml(item) }}
                  />
                ))}
              </ol>
            );
          case "code":
            return (
              <Fragment key={`code-${blockIndex}`}>
                {block.language ? (
                  <div className="mb-1 mt-4 text-xs uppercase tracking-wide text-muted-foreground">{block.language}</div>
                ) : null}
                <pre className="mb-4 overflow-auto rounded-xl border border-zinc-800 bg-zinc-950 p-4 text-xs text-zinc-100 shadow-sm">
                  <code>{block.code}</code>
                </pre>
              </Fragment>
            );
          default:
            return null;
        }
      })}
    </article>
  );
}
