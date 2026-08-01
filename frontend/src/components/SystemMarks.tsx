/**
 * Marks for the "BUILT FOR" strip.
 *
 * Five are the official brand marks, path data copied from Simple Icons
 * (https://simpleicons.org, CC0-1.0) so the strip is instantly recognisable
 * and there is no runtime dependency or CDN fetch for five paths.
 *
 * Two have no official mark available and are drawn here instead:
 *   Codex   — OpenAI's mark is not in any CC0 set (they asked for its removal),
 *             so this is a neutral terminal prompt rather than a bad trace.
 *   Ossprey — no published brand mark; a raptor, after the name.
 *
 * Brand paths are solid fills on a 24px box; the two drawn glyphs are strokes
 * on the same box, weighted to sit at the same optical density.
 */

type MarkProps = { className?: string };

const FILL = {
  viewBox: "0 0 24 24",
  fill: "currentColor",
  "aria-hidden": true,
} as const;

/* The five brand marks are solid fills. The two drawn ones are too, or they
   read a full step lighter than their neighbours at 21px. */

/* -- official marks, Simple Icons (CC0-1.0) -------------------------------- */

const MCP_PATH =
  "M13.85 0a4.16 4.16 0 0 0-2.95 1.217L1.456 10.66a.835.835 0 0 0 0 1.18.835.835 0 0 0 1.18 0l9.442-9.442a2.49 2.49 0 0 1 3.541 0 2.49 2.49 0 0 1 0 3.541L8.59 12.97l-.1.1a.835.835 0 0 0 0 1.18.835.835 0 0 0 1.18 0l.1-.098 7.03-7.034a2.49 2.49 0 0 1 3.542 0l.049.05a2.49 2.49 0 0 1 0 3.54l-8.54 8.54a1.96 1.96 0 0 0 0 2.755l1.753 1.753a.835.835 0 0 0 1.18 0 .835.835 0 0 0 0-1.18l-1.753-1.753a.266.266 0 0 1 0-.394l8.54-8.54a4.185 4.185 0 0 0 0-5.9l-.05-.05a4.16 4.16 0 0 0-2.95-1.218c-.2 0-.401.02-.6.048a4.17 4.17 0 0 0-1.17-3.552A4.16 4.16 0 0 0 13.85 0m0 3.333a.84.84 0 0 0-.59.245L6.275 10.56a4.186 4.186 0 0 0 0 5.902 4.186 4.186 0 0 0 5.902 0L19.16 9.48a.835.835 0 0 0 0-1.18.835.835 0 0 0-1.18 0l-6.985 6.984a2.49 2.49 0 0 1-3.54 0 2.49 2.49 0 0 1 0-3.54l6.983-6.985a.835.835 0 0 0 0-1.18.84.84 0 0 0-.59-.245";

const CURSOR_PATH =
  "M11.503.131 1.891 5.678a.84.84 0 0 0-.42.726v11.188c0 .3.162.575.42.724l9.609 5.55a1 1 0 0 0 .998 0l9.61-5.55a.84.84 0 0 0 .42-.724V6.404a.84.84 0 0 0-.42-.726L12.497.131a1.01 1.01 0 0 0-.996 0M2.657 6.338h18.55c.263 0 .43.287.297.515L12.23 22.918c-.062.107-.229.064-.229-.06V12.335a.59.59 0 0 0-.295-.51l-9.11-5.257c-.109-.063-.064-.23.061-.23";

const CLAUDE_CODE_PATH =
  "M21 10.5h3v3h-3v3h-1.5v3H18v-3h-1.5v3H15v-3H9v3H7.5v-3H6v3H4.5v-3H3v-3H0v-3h3v-6h18Zm-15 0h1.5v-3H6Zm10.5 0H18v-3h-1.5z";

const SUPABASE_PATH =
  "M11.9 1.036c-.015-.986-1.26-1.41-1.874-.637L.764 12.05C-.33 13.427.65 15.455 2.409 15.455h9.579l.113 7.51c.014.985 1.259 1.408 1.873.636l9.262-11.653c1.093-1.375.113-3.403-1.645-3.403h-9.642z";

const MODAL_PATH =
  "M4.89 5.57 0 14.002l2.521 4.4h5.05l4.396-7.718 4.512 7.709 4.996.037L24 14.057l-4.857-8.452-5.073-.015-2.076 3.598L9.94 5.57Zm.837.729h3.787l1.845 3.252H7.572Zm9.189.021 3.803.012 4.228 7.355-3.736-.027zm-9.82.346L6.94 9.914l-4.209 7.389-1.892-3.3Zm9.187.014 4.297 7.343-1.892 3.282-4.3-7.344zm-6.713 3.6h3.79l-4.212 7.394H3.361Zm11.64 4.109 3.74.027-1.893 3.281-3.74-.027z";

function brandMark(path: string) {
  return function Brand(props: MarkProps) {
    return (
      <svg {...FILL} {...props}>
        <path d={path} />
      </svg>
    );
  };
}

/* -- drawn stand-ins, no official mark available --------------------------- */

/** Codex — a shell prompt. No frame: it keeps the weight near MCP and Modal. */
function MarkCodex(props: MarkProps) {
  return (
    <svg {...FILL} {...props}>
      <path d="M4.42 4.3a1.5 1.5 0 0 0-2.02 2.22l4.9 4.45a1.4 1.4 0 0 1 0 2.06l-4.9 4.45a1.5 1.5 0 0 0 2.02 2.22l6.1-5.54a2.6 2.6 0 0 0 0-3.84L4.42 4.3Z" />
      <rect x="11.6" y="16.8" width="10.4" height="2.9" rx="1.45" />
    </svg>
  );
}

/**
 * Ossprey — a cleared shield. Swap this the moment we have their real SVG.
 *
 * A raptor was the obvious read on the name, but at 21px every version of it
 * came out as a wine glass. The shield says "package cleared" instantly, which
 * is what Ossprey does here, and the wordmark beside it carries the identity.
 */
function MarkOssprey(props: MarkProps) {
  return (
    <svg {...FILL} {...props} fillRule="evenodd" clipRule="evenodd">
      <path d="M12 2.1 3.5 5.05v6.5c0 5.2 3.55 8.98 8.5 10.5 4.95-1.52 8.5-5.3 8.5-10.5v-6.5L12 2.1Zm4.32 7.35a1.2 1.2 0 0 0-1.86-1.52l-3.4 4.16-1.5-1.5a1.2 1.2 0 1 0-1.7 1.7l2.44 2.44a1.2 1.2 0 0 0 1.78-.09l4.24-5.19Z" />
    </svg>
  );
}

export const SYSTEM_MARKS = [
  { label: "MCP", Mark: brandMark(MCP_PATH) },
  { label: "Cursor", Mark: brandMark(CURSOR_PATH) },
  { label: "Claude Code", Mark: brandMark(CLAUDE_CODE_PATH) },
  { label: "Codex", Mark: MarkCodex },
  { label: "Ossprey", Mark: MarkOssprey },
  { label: "Supabase", Mark: brandMark(SUPABASE_PATH) },
  { label: "Modal", Mark: brandMark(MODAL_PATH) },
] as const;
