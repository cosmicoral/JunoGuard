import post01 from "@docs-blog/01-coding-agent-blast-radius.md?raw";
import post02 from "@docs-blog/02-agent-productive-without-blast-radius.md?raw";
import post03 from "@docs-blog/03-what-unguarded-agent-costs.md?raw";
import post04 from "@docs-blog/04-demo-blocking-ossprey-test-package.md?raw";
import post05 from "@docs-blog/05-npx-init-wire-agents.md?raw";
import post06 from "@docs-blog/06-honest-limits.md?raw";
import post07 from "@docs-blog/07-no-llm-on-hot-path.md?raw";
import post08 from "@docs-blog/08-mcp-tools-lock.md?raw";

export type BlogPostMeta = {
  slug: string;
  title: string;
  description: string;
  date: string;
  keyword: string;
  readingMinutes: number;
  body: string;
};

function titleFromMarkdown(md: string): string {
  const match = md.match(/^#\s+(.+)$/m);
  return match?.[1]?.trim() ?? "Untitled";
}

function keywordFromMarkdown(md: string): string {
  const match = md.match(/\*\*Primary keyword:\*\*\s*(.+)$/m);
  return match?.[1]?.trim() ?? "AI coding agent security";
}

function descriptionFromMarkdown(md: string): string {
  const withoutMeta = md
    .replace(/^#\s+.+$/m, "")
    .replace(/\*\*Series:\*\*.+$/m, "")
    .replace(/\*\*Citation style:\*\*.+$/m, "")
    .replace(/\*\*Primary keyword:\*\*.+$/m, "")
    .replace(/^---$/gm, "")
    .replace(/!\[[^\]]*\]\([^)]+\)/g, "")
    .replace(/\*\*Figure[^*]+\*\*/g, "");
  const para = withoutMeta
    .split(/\n\n+/)
    .map((p) => p.replace(/\s+/g, " ").trim())
    .find((p) => p.length > 40 && !p.startsWith("#") && !p.startsWith("```"));
  if (!para) return "JunoGuard field notes on coding-agent blast radius.";
  return para.length > 180 ? `${para.slice(0, 177)}…` : para;
}

function readingMinutes(md: string): number {
  const words = md.trim().split(/\s+/).length;
  return Math.max(4, Math.round(words / 220));
}

function entry(
  slug: string,
  date: string,
  body: string,
): BlogPostMeta {
  return {
    slug,
    title: titleFromMarkdown(body),
    description: descriptionFromMarkdown(body),
    date,
    keyword: keywordFromMarkdown(body),
    readingMinutes: readingMinutes(body),
    body,
  };
}

/** Newest first. */
export const BLOG_POSTS: BlogPostMeta[] = [
  entry("mcp-tools-lock", "2026-08-03", post08),
  entry("no-llm-on-hot-path", "2026-08-03", post07),
  entry("honest-limits", "2026-08-03", post06),
  entry("npx-init-wire-agents", "2026-08-03", post05),
  entry("demo-blocking-ossprey-test-package", "2026-08-03", post04),
  entry("what-unguarded-agent-costs", "2026-08-03", post03),
  entry("agent-productive-without-blast-radius", "2026-08-03", post02),
  entry("coding-agent-blast-radius", "2026-08-03", post01),
];

export function getPost(slug: string): BlogPostMeta | undefined {
  return BLOG_POSTS.find((p) => p.slug === slug);
}
