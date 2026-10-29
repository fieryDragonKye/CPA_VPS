/** Missing, invalid and upstream zero-sentinel timings are not measured zeroes. */
export function formatTtft(value: number | null | undefined): string {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) return '—';
  return value < 1000
    ? `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })}ms`
    : `${(value / 1000).toLocaleString(undefined, { maximumFractionDigits: 2 })}s`;
}

/** Keep unknown prices and tiny positive costs distinct from an explicitly free rate. */
export function formatEstimatedCost(value: number | null | undefined): string {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) return '—';
  if (value > 0 && value < 0.000001) return '<$0.000001';
  return `$${value.toLocaleString('en-US', { minimumFractionDigits: 4, maximumFractionDigits: 6 })}`;
}
