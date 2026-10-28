/** Missing, invalid and upstream zero-sentinel timings are not measured zeroes. */
export function formatTtft(value: number | null | undefined): string {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) return '—';
  return value < 1000
    ? `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })}ms`
    : `${(value / 1000).toLocaleString(undefined, { maximumFractionDigits: 2 })}s`;
}
