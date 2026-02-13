import ReactMarkdown, { type Components } from "react-markdown";
import rehypeRaw from "rehype-raw";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import remarkGfm from "remark-gfm";

type MarkdownViewerProps = {
  markdown: string;
};

const allowedTagNames = [
  "a",
  "blockquote",
  "code",
  "details",
  "div",
  "em",
  "h1",
  "h2",
  "h3",
  "h4",
  "h5",
  "h6",
  "hr",
  "img",
  "li",
  "ol",
  "p",
  "pre",
  "span",
  "strong",
  "summary",
  "table",
  "tbody",
  "td",
  "th",
  "thead",
  "tr",
  "ul",
];

const sanitizeSchema = {
  ...defaultSchema,
  tagNames: Array.from(new Set([...(defaultSchema.tagNames ?? []), ...allowedTagNames])),
  attributes: {
    ...(defaultSchema.attributes ?? {}),
    a: ["href", "title", "target", "rel"],
    img: ["src", "alt", "title", "width", "height"],
    table: ["className"],
    th: ["align", "colspan", "rowspan"],
    td: ["align", "colspan", "rowspan"],
    details: ["open"],
    div: ["className"],
    span: ["className"],
    code: ["className"],
    pre: ["className"],
  },
  protocols: {
    ...(defaultSchema.protocols ?? {}),
    href: ["http", "https"],
    src: ["http", "https"],
  },
};

const markdownComponents: Components = {
  a: ({ node: _node, href, children, ...props }) => {
    const safeHref = href && /^https?:\/\//i.test(href) ? href : undefined;
    return (
      <a
        {...props}
        href={safeHref}
        target="_blank"
        rel="noreferrer noopener"
        className="underline decoration-zinc-400 underline-offset-4 hover:decoration-zinc-900"
      >
        {children}
      </a>
    );
  },
  img: ({ node: _node, alt, src, title, width, height, ...props }) => {
    const safeSrc = src && /^https?:\/\//i.test(src) ? src : undefined;
    if (!safeSrc) {
      return null;
    }
    return (
      <img
        {...props}
        src={safeSrc}
        alt={alt ?? ""}
        title={title}
        width={width as number | string | undefined}
        height={height as number | string | undefined}
        loading="lazy"
        className="my-3 max-h-[420px] rounded-lg border border-border/60"
      />
    );
  },
  table: ({ node: _node, children, ...props }) => (
    <div className="my-4 w-full overflow-x-auto rounded-lg border border-border/60">
      <table {...props} className="min-w-full border-collapse text-sm">
        {children}
      </table>
    </div>
  ),
  thead: ({ node: _node, ...props }) => <thead {...props} className="bg-muted/70" />,
  th: ({ node: _node, ...props }) => (
    <th {...props} className="whitespace-nowrap border-b border-border/70 px-3 py-2 text-left font-semibold" />
  ),
  td: ({ node: _node, ...props }) => <td {...props} className="border-b border-border/50 px-3 py-2 align-top" />,
  tr: ({ node: _node, ...props }) => <tr {...props} className="odd:bg-background even:bg-muted/20" />,
  code: ({ node: _node, className, children, ...props }) => {
    const text = String(children ?? "");
    const isInline = !className && !text.includes("\n");
    if (isInline) {
      return (
        <code {...props} className="rounded bg-muted px-1.5 py-0.5 text-[0.88em]">
          {children}
        </code>
      );
    }
    return (
      <code {...props} className={className}>
        {children}
      </code>
    );
  },
  pre: ({ node: _node, ...props }) => (
    <pre
      {...props}
      className="mb-4 overflow-auto rounded-xl border border-border bg-muted p-4 text-xs text-foreground shadow-sm dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
    />
  ),
  details: ({ node: _node, ...props }) => (
    <details {...props} className="my-4 rounded-lg border border-border/70 bg-muted/20 px-3 py-2" />
  ),
  summary: ({ node: _node, ...props }) => <summary {...props} className="cursor-pointer font-medium" />,
};

export function MarkdownViewer({ markdown }: MarkdownViewerProps) {
  if (!markdown.trim()) {
    return <div className="text-sm text-muted-foreground">暂无内容</div>;
  }

  return (
    <article className="max-w-none rounded-xl border border-border/70 bg-card p-5 text-[15px] leading-7 text-foreground/85 [&_blockquote]:my-4 [&_blockquote]:border-l-4 [&_blockquote]:border-border [&_blockquote]:pl-4 [&_blockquote]:text-muted-foreground [&_h1]:mb-3 [&_h1]:mt-6 [&_h1]:text-2xl [&_h1]:font-semibold [&_h2]:mb-2 [&_h2]:mt-5 [&_h2]:text-xl [&_h2]:font-semibold [&_h3]:mb-2 [&_h3]:mt-4 [&_h3]:text-lg [&_h3]:font-semibold [&_li]:my-1 [&_ol]:mb-4 [&_ol]:list-decimal [&_ol]:pl-6 [&_p]:mb-3 [&_ul]:mb-4 [&_ul]:list-disc [&_ul]:pl-6">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeRaw, [rehypeSanitize, sanitizeSchema]]}
        components={markdownComponents}
      >
        {markdown}
      </ReactMarkdown>
    </article>
  );
}
