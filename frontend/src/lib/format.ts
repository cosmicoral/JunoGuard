/** Fixed-width helpers. Everything in the feed is tabular, so nothing jitters. */

export function clockTime(iso: string): string {
  const d = new Date(iso);
  return [d.getHours(), d.getMinutes(), d.getSeconds()]
    .map((n) => String(n).padStart(2, "0"))
    .join(":");
}

export function usd(n: number): string {
  return `$${n.toFixed(2)}`;
}

/** Per-request cost needs more places than the daily rollup. */
export function usdFine(n: number): string {
  return `$${n.toFixed(4)}`;
}

export function tokens(n: number): string {
  if (n < 1000) return `${Math.round(n)} tok`;
  return `${(n / 1000).toFixed(1)}k tok`;
}

export function integer(n: number): string {
  return String(Math.round(n));
}

export function count(n: number): string {
  return Math.round(n).toLocaleString("en-US");
}
