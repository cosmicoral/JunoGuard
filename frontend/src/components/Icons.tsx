/** Small line icons — no emoji. 16×16 viewBox, currentColor stroke. */

import type { ReactNode } from "react";

type IconProps = {
  size?: number;
  className?: string;
  title?: string;
};

function Icon({
  size = 16,
  className,
  title,
  children,
}: IconProps & { children: ReactNode }) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden={title ? undefined : true}
      role={title ? "img" : undefined}
    >
      {title ? <title>{title}</title> : null}
      {children}
    </svg>
  );
}

const stroke = {
  stroke: "currentColor",
  strokeWidth: 1.5,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

export function IconArrowRight(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M3 8h10M9 4l4 4-4 4" {...stroke} />
    </Icon>
  );
}

export function IconExternal(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M6.5 3.5H12.5V9.5" {...stroke} />
      <path d="M12.5 3.5L6 10" {...stroke} />
      <path d="M4 5.5V12.5H11" {...stroke} />
    </Icon>
  );
}

export function IconOverview(props: IconProps) {
  return (
    <Icon {...props}>
      <rect x="2.5" y="2.5" width="4.5" height="4.5" rx="0.75" {...stroke} />
      <rect x="9" y="2.5" width="4.5" height="4.5" rx="0.75" {...stroke} />
      <rect x="2.5" y="9" width="4.5" height="4.5" rx="0.75" {...stroke} />
      <rect x="9" y="9" width="4.5" height="4.5" rx="0.75" {...stroke} />
    </Icon>
  );
}

export function IconFeed(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M3 4.5h10M3 8h10M3 11.5h7" {...stroke} />
    </Icon>
  );
}

export function IconIncidents(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M8 2.75 13.25 12.5H2.75L8 2.75Z" {...stroke} />
      <path d="M8 6.5v2.75" {...stroke} />
      <circle cx="8" cy="11" r="0.65" fill="currentColor" />
    </Icon>
  );
}

export function IconControls(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M3 5h10M3 8h10M3 11h10" {...stroke} />
      <circle cx="6" cy="5" r="1.25" fill="currentColor" />
      <circle cx="10" cy="8" r="1.25" fill="currentColor" />
      <circle cx="7.5" cy="11" r="1.25" fill="currentColor" />
    </Icon>
  );
}

export function IconAllow(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M3.5 8.25 6.5 11.25 12.5 4.75" {...stroke} />
    </Icon>
  );
}

export function IconBlock(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M4.5 4.5l7 7M11.5 4.5l-7 7" {...stroke} />
    </Icon>
  );
}

export function IconFlag(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M4 13.5V3.5" {...stroke} />
      <path d="M4 3.5h7l-1.5 2.5L11 8.5H4" {...stroke} />
    </Icon>
  );
}

export function IconShield(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M8 2.5 13 5v3.5c0 3.2-2.1 5.4-5 6.5-2.9-1.1-5-3.3-5-6.5V5L8 2.5Z" {...stroke} />
    </Icon>
  );
}

export function IconClock(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="8" cy="8" r="5.25" {...stroke} />
      <path d="M8 5.5V8l2 1.5" {...stroke} />
    </Icon>
  );
}

export function IconSpend(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="8" cy="8" r="5.25" {...stroke} />
      <path d="M8 4.75v6.5M6.25 6.5c.4-.7 1-.95 1.75-.95 1.1 0 1.9.55 1.9 1.45S9.1 8.5 8 8.5 6.1 9 6.1 9.95c0 .9.85 1.5 1.9 1.5.8 0 1.4-.3 1.75-.9" {...stroke} />
    </Icon>
  );
}
