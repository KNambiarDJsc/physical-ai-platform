import { Fragment } from "react";
import { parseMarkdown, type Inline } from "@/lib/markdown";

function Inlines({ parts }: { parts: Inline[] }) {
  return (
    <>
      {parts.map((p, i) =>
        p.kind === "bold" ? (
          <strong key={i} className="font-semibold">
            {p.text}
          </strong>
        ) : p.kind === "code" ? (
          <code key={i} className="num rounded-sm bg-sunken px-1 text-[12px]">
            {p.text}
          </code>
        ) : (
          <Fragment key={i}>{p.text}</Fragment>
        ),
      )}
    </>
  );
}

/** An agent's answer, formatted. React elements only (see lib/markdown.ts): a model cannot inject markup. */
export function Markdown({ text }: { text: string }) {
  return (
    <div className="space-y-2.5">
      {parseMarkdown(text).map((b, i) => {
        if (b.kind === "heading")
          return (
            <h4 key={i} className="pt-1 text-[13px] font-semibold first:pt-0">
              <Inlines parts={b.inline} />
            </h4>
          );
        if (b.kind === "list") {
          const Tag = b.ordered ? "ol" : "ul";
          return (
            <Tag key={i} className={b.ordered ? "list-decimal space-y-1 pl-5" : "list-disc space-y-1 pl-5"}>
              {b.items.map((item, j) => (
                <li key={j}>
                  <Inlines parts={item} />
                </li>
              ))}
            </Tag>
          );
        }
        if (b.kind === "pre")
          return (
            <pre key={i} className="num overflow-x-auto whitespace-pre text-[12px] text-muted">
              {b.text}
            </pre>
          );
        return (
          <p key={i} className="whitespace-pre-line">
            <Inlines parts={b.inline} />
          </p>
        );
      })}
    </div>
  );
}
