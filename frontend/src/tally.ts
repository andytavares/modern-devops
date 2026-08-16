// Pure, DOM-free tally logic — kept separate from main.ts so it can be unit
// tested directly (see tally.test.ts) without a browser.
//
// The whole point of this module: `priced_by` is a free-form string on the
// wire, not a closed v1/v2 union (see api.ts). Tallying must key on
// whatever string actually came back, so an unexpected value shows up as
// its own bucket instead of being folded into an existing one.

const PALETTE = ["#4f8cff", "#ff9f43", "#2ecc71", "#e84393", "#a29bfe", "#00cec9"];

/**
 * Records one occurrence of `key` in `counts`, in place. `key` is whatever
 * `priced_by` the backend returned — no validation, no fallback bucket.
 */
export function recordPriced(counts: Map<string, number>, key: string): void {
  counts.set(key, (counts.get(key) ?? 0) + 1);
}

/** Total occurrences across all keys. */
export function totalOf(counts: Map<string, number>): number {
  let sum = 0;
  for (const n of counts.values()) sum += n;
  return sum;
}

/** Percentage (0-100, rounded) of `key` within `counts`. 0 if the total is 0. */
export function percentOf(counts: Map<string, number>, key: string): number {
  const total = totalOf(counts);
  if (total === 0) return 0;
  return Math.round(((counts.get(key) ?? 0) / total) * 100);
}

/**
 * Stable colour per key, assigned from a small palette in first-seen order
 * and cached in `assigned` so a key never changes colour across renders,
 * even as new keys appear or the bar re-sorts.
 */
export function colorFor(key: string, assigned: Map<string, string>): string {
  const existing = assigned.get(key);
  if (existing) return existing;
  const color = PALETTE[assigned.size % PALETTE.length] as string;
  assigned.set(key, color);
  return color;
}
