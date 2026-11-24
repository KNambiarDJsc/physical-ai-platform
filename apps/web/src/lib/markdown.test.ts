import { describe, expect, it } from "vitest";
import { parseInline, parseMarkdown } from "./markdown";

describe("markdown for agent answers", () => {
  it("reads bold and inline code and leaves anything else as text", () => {
    expect(parseInline("a **b** and `c` d")).toEqual([
      { kind: "text", text: "a " },
      { kind: "bold", text: "b" },
      { kind: "text", text: " and " },
      { kind: "code", text: "c" },
      { kind: "text", text: " d" },
    ]);
    expect(parseInline("2 ** 3 and a lone ** mark")).toEqual([{ kind: "text", text: "2 ** 3 and a lone ** mark" }]);
  });

  it("reads headings, paragraphs and lists in order", () => {
    const blocks = parseMarkdown("## Summary\n\nThe pump **reported** success.\nThe balance disagrees.\n\n- first\n- second\n\n1. one\n2. two");
    expect(blocks.map((b) => b.kind)).toEqual(["heading", "paragraph", "list", "list"]);
    expect(blocks[0]).toMatchObject({ kind: "heading", level: 2 });
    expect(blocks[1]).toMatchObject({ kind: "paragraph" });
    expect((blocks[1] as { inline: { text: string }[] }).inline.map((i) => i.text).join("")).toBe("The pump reported success.\nThe balance disagrees.");
    expect(blocks[2]).toMatchObject({ kind: "list", ordered: false });
    expect((blocks[2] as { items: unknown[] }).items).toHaveLength(2);
    expect(blocks[3]).toMatchObject({ kind: "list", ordered: true });
  });

  it("keeps a pipe table as aligned text and drops horizontal rules", () => {
    const blocks = parseMarkdown("| id | what |\n|---|---|\n| F1 | bad |\n\n---\n\nafter");
    expect(blocks.map((b) => b.kind)).toEqual(["pre", "paragraph"]);
    expect((blocks[0] as { text: string }).text.split("\n")).toHaveLength(3);
  });

  it("never produces markup: HTML in a model's text stays plain text", () => {
    const blocks = parseMarkdown("<script>alert(1)</script> and <b>x</b>");
    expect(blocks).toEqual([{ kind: "paragraph", inline: [{ kind: "text", text: "<script>alert(1)</script> and <b>x</b>" }] }]);
  });

  it("returns nothing for an empty answer", () => {
    expect(parseMarkdown("")).toEqual([]);
    expect(parseMarkdown("\n\n  \n")).toEqual([]);
  });
});
