/**
 * Brand marks for the landing page's integration strip.
 *
 * Split into two groups because they are two different claims. The first is
 * what `juno init` wires today. The second is what JunoGuard is built on.
 *
 * Path data is inlined rather than imported. It is a dozen paths that never
 * change, the packages are tens of megabytes, and the page must not fetch
 * anything at runtime.
 *   AI brand marks  — @lobehub/icons-static-svg (MIT)
 *   Supabase        — Simple Icons (CC0-1.0)
 * The logos remain trademarks of their owners, used here to identify the
 * products JunoGuard interoperates with.
 */

type MarkProps = { className?: string };

const CURSOR = [
  "M22.106 5.68L12.5.135a.998.998 0 00-.998 0L1.893 5.68a.84.84 0 00-.419.726v11.186c0 .3.16.577.42.727l9.607 5.547a.999.999 0 00.998 0l9.608-5.547a.84.84 0 00.42-.727V6.407a.84.84 0 00-.42-.726zm-.603 1.176L12.228 22.92c-.063.108-.228.064-.228-.061V12.34a.59.59 0 00-.295-.51l-9.11-5.26c-.107-.062-.063-.228.062-.228h18.55c.264 0 .428.286.296.514z",
];

const CLAUDE_CODE = [
  "M20.998 10.949H24v3.102h-3v3.028h-1.487V20H18v-2.921h-1.487V20H15v-2.921H9V20H7.488v-2.921H6V20H4.487v-2.921H3V14.05H0V10.95h3V5h17.998v5.949zM6 10.949h1.488V8.102H6v2.847zm10.51 0H18V8.102h-1.49v2.847z",
];

const WINDSURF = [
  "M23.78 5.004h-.228a2.187 2.187 0 00-2.18 2.196v4.912c0 .98-.804 1.775-1.76 1.775a1.818 1.818 0 01-1.472-.773L13.168 5.95a2.197 2.197 0 00-1.81-.95c-1.134 0-2.154.972-2.154 2.173v4.94c0 .98-.797 1.775-1.76 1.775-.57 0-1.136-.289-1.472-.773L.408 5.098C.282 4.918 0 5.007 0 5.228v4.284c0 .216.066.426.188.604l5.475 7.889c.324.466.8.812 1.351.938 1.377.316 2.645-.754 2.645-2.117V11.89c0-.98.787-1.775 1.76-1.775h.002c.586 0 1.135.288 1.472.773l4.972 7.163a2.15 2.15 0 001.81.95c1.158 0 2.151-.973 2.151-2.173v-4.939c0-.98.787-1.775 1.76-1.775h.194c.122 0 .22-.1.22-.222V5.225a.221.221 0 00-.22-.222z",
];

const MCP = [
  "M15.688 2.343a2.588 2.588 0 00-3.61 0l-9.626 9.44a.863.863 0 01-1.203 0 .823.823 0 010-1.18l9.626-9.44a4.313 4.313 0 016.016 0 4.116 4.116 0 011.204 3.54 4.3 4.3 0 013.609 1.18l.05.05a4.115 4.115 0 010 5.9l-8.706 8.537a.274.274 0 000 .393l1.788 1.754a.823.823 0 010 1.18.863.863 0 01-1.203 0l-1.788-1.753a1.92 1.92 0 010-2.754l8.706-8.538a2.47 2.47 0 000-3.54l-.05-.049a2.588 2.588 0 00-3.607-.003l-7.172 7.034-.002.002-.098.097a.863.863 0 01-1.204 0 .823.823 0 010-1.18l7.273-7.133a2.47 2.47 0 00-.003-3.537z",
  "M14.485 4.703a.823.823 0 000-1.18.863.863 0 00-1.204 0l-7.119 6.982a4.115 4.115 0 000 5.9 4.314 4.314 0 006.016 0l7.12-6.982a.823.823 0 000-1.18.863.863 0 00-1.204 0l-7.119 6.982a2.588 2.588 0 01-3.61 0 2.47 2.47 0 010-3.54l7.12-6.982z",
];

const SUPABASE = [
  "M11.9 1.036c-.015-.986-1.26-1.41-1.874-.637L.764 12.05C-.33 13.427.65 15.455 2.409 15.455h9.579l.113 7.51c.014.985 1.259 1.408 1.873.636l9.262-11.653c1.093-1.375.113-3.403-1.645-3.403h-9.642z",
];

/** Ossprey has no published mark. A cleared shield until we have their SVG. */
const OSSPREY = [
  "M12 2.1 3.5 5.05v6.5c0 5.2 3.55 8.98 8.5 10.5 4.95-1.52 8.5-5.3 8.5-10.5v-6.5L12 2.1Zm4.32 7.35a1.2 1.2 0 0 0-1.86-1.52l-3.4 4.16-1.5-1.5a1.2 1.2 0 1 0-1.7 1.7l2.44 2.44a1.2 1.2 0 0 0 1.78-.09l4.24-5.19Z",
];

/** Modal wordmark-free monogram used for the cold-path sandbox host. */
const MODAL = [
  "M4 19V5l4.5 8.5L13 5v14h-2.2V10.2L8.5 15.4 6.2 10.2V19H4zm12.2 0V5h2.1l3.4 9.1L25 5h2.1v14h-2.15v-9.1L21.7 19h-1.9l-3.25-9.1V19h-2.15z",
];

function mark(paths: readonly string[], viewBox = "0 0 24 24") {
  return function Brand({ className }: MarkProps) {
    return (
      <svg
        viewBox={viewBox}
        fill="currentColor"
        fillRule="evenodd"
        clipRule="evenodd"
        className={className}
        aria-hidden
      >
        {paths.map((d) => (
          <path key={d.slice(0, 24)} d={d} />
        ))}
      </svg>
    );
  };
}

/**
 * What `juno init` wires today. Other MCP clients can still call the tools,
 * but this strip only claims the agents with a first-class init path.
 */
export const AGENT_MARKS = [
  { label: "Cursor", Mark: mark(CURSOR) },
  { label: "Claude Code", Mark: mark(CLAUDE_CODE) },
  { label: "Windsurf", Mark: mark(WINDSURF) },
] as const;

/** What Juno is built on. */
export const STACK_MARKS = [
  { label: "MCP", Mark: mark(MCP) },
  { label: "Ossprey", Mark: mark(OSSPREY) },
  { label: "Supabase", Mark: mark(SUPABASE) },
  { label: "Modal", Mark: mark(MODAL, "0 0 28 24") },
] as const;
