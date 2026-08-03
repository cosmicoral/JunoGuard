import type { ReactNode } from "react";
import { createElement, Fragment } from "react";

/** Rewrite local figure paths so Vite serves them from /blog/assets. */
function assetUrl(src: string): string {
  if (src.startsWith("./assets/")) return `/blog/assets/${src.slice("./assets/".length)}`;
  if (src.startsWith("assets/")) return `/blog/assets/${src.slice("assets/".length)}`;
  return src;
}

function inline(text: string, keyBase: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const re =
    /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|\[[^\]]+\]\([^)]+\)|\[\^[^\]]+\])/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) nodes.push(text.slice(last, m.index));
    const token = m[0];
    if (token.startsWith("**")) {
      nodes.push(createElement("strong", { key: `${keyBase}-b-${i++}` }, token.slice(2, -2)));
    } else if (token.startsWith("*")) {
      nodes.push(createElement("em", { key: `${keyBase}-i-${i++}` }, token.slice(1, -1)));
    } else if (token.startsWith("`")) {
      nodes.push(createElement("code", { key: `${keyBase}-c-${i++}` }, token.slice(1, -1)));
    } else if (token.startsWith("[^")) {
      const id = token.slice(2, -1);
      nodes.push(
        createElement(
          "a",
          {
            key: `${keyBase}-fn-${i++}`,
            href: `#fn-${id}`,
            className: "blog-footnote-ref",
            id: `fnref-${id}`,
          },
          createElement("sup", null, id),
        ),
      );
    } else {
      const link = token.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
      if (link) {
        const href = link[2];
        const external = /^https?:\/\//.test(href);
        nodes.push(
          createElement(
            "a",
            {
              key: `${keyBase}-a-${i++}`,
              href,
              ...(external ? { target: "_blank", rel: "noreferrer" } : {}),
            },
            link[1],
          ),
        );
      }
    }
    last = m.index + token.length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

/**
 * Minimal Markdown renderer for JunoGuard field notes:
 * headings, paragraphs, lists, fenced code, images, hr, footnotes section.
 */
export function renderMarkdown(md: string): ReactNode[] {
  const lines = md.replace(/\r\n/g, "\n").split("\n");
  const out: ReactNode[] = [];
  let i = 0;
  let block = 0;

  const pushPara = (buf: string[]) => {
    const text = buf.join(" ").trim();
    if (!text) return;
    if (/^\*\*Figure\s+\d+\./i.test(text)) {
      out.push(
        createElement("p", { key: `cap-${block++}`, className: "blog-figure-caption" }, inline(text, `cap-${block}`)),
      );
      return;
    }
    out.push(createElement("p", { key: `p-${block++}` }, inline(text, `p-${block}`)));
  };

  while (i < lines.length) {
    const line = lines[i];

    if (line.trim() === "---") {
      out.push(createElement("hr", { key: `hr-${block++}` }));
      i++;
      continue;
    }

    if (line.startsWith("```")) {
      const lang = line.slice(3).trim();
      const code: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) {
        code.push(lines[i]);
        i++;
      }
      i++; // closing fence
      out.push(
        createElement(
          "pre",
          { key: `pre-${block++}`, className: "blog-pre" },
          createElement("code", { "data-lang": lang || undefined }, code.join("\n")),
        ),
      );
      continue;
    }

    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      const level = heading[1].length as 1 | 2 | 3;
      const tag = (`h${level}` as const);
      const id =
        level > 1
          ? heading[2]
              .toLowerCase()
              .replace(/[^a-z0-9]+/g, "-")
              .replace(/^-|-$/g, "")
          : undefined;
      out.push(
        createElement(tag, { key: `h-${block++}`, id }, inline(heading[2], `h-${block}`)),
      );
      i++;
      continue;
    }

    const img = line.match(/^!\[([^\]]*)\]\(([^)]+)\)$/);
    if (img) {
      out.push(
        createElement(
          "figure",
          { key: `fig-${block++}`, className: "blog-figure" },
          createElement("img", {
            src: assetUrl(img[2]),
            alt: img[1],
            loading: "lazy",
          }),
        ),
      );
      i++;
      continue;
    }

    if (/^[-*]\s+/.test(line)) {
      const items: ReactNode[] = [];
      while (i < lines.length && /^[-*]\s+/.test(lines[i])) {
        const item = lines[i].replace(/^[-*]\s+/, "");
        items.push(createElement("li", { key: `li-${block}-${items.length}` }, inline(item, `li-${block}-${items.length}`)));
        i++;
      }
      out.push(createElement("ul", { key: `ul-${block++}` }, items));
      continue;
    }

    if (/^\[\^[^\]]+\]:/.test(line)) {
      // Footnotes: collect until blank line or next note
      const notes: { id: string; text: string }[] = [];
      while (i < lines.length && /^\[\^[^\]]+\]:/.test(lines[i])) {
        const m = lines[i].match(/^\[\^([^\]]+)\]:\s*(.*)$/);
        if (!m) break;
        let text = m[2];
        i++;
        while (i < lines.length && lines[i].trim() !== "" && !/^\[\^[^\]]+\]:/.test(lines[i]) && !/^##\s/.test(lines[i])) {
          text += ` ${lines[i].trim()}`;
          i++;
        }
        if (lines[i]?.trim() === "") i++;
        notes.push({ id: m[1], text });
      }
      out.push(
        createElement(
          "ol",
          { key: `fns-${block++}`, className: "blog-footnotes" },
          notes.map((n) =>
            createElement(
              "li",
              { key: n.id, id: `fn-${n.id}` },
              inline(n.text, `fn-${n.id}`),
              " ",
              createElement("a", { href: `#fnref-${n.id}`, className: "blog-footnote-back" }, "↩"),
            ),
          ),
        ),
      );
      continue;
    }

    if (line.trim() === "") {
      i++;
      continue;
    }

    // Skip meta lines already shown in the page chrome
    if (/^\*\*(Series|Citation style|Primary keyword):\*\*/.test(line)) {
      i++;
      continue;
    }

    const buf: string[] = [line];
    i++;
    while (i < lines.length && lines[i].trim() !== "" && !/^(#{1,3}\s|```|---|!\[|[-*]\s|\[\^)/.test(lines[i])) {
      buf.push(lines[i]);
      i++;
    }
    pushPara(buf);
  }

  return out.length ? out : [createElement(Fragment, { key: "empty" })];
}
