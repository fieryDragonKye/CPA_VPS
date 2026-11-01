import type { Credential, CredentialRow } from '@/services/api/insights';

/** Use the latest selection, so delayed initialization cannot replace a manual choice. */
export function resolveCredentialSelection(
  current: string,
  visible: Credential[],
  allowUnlinked: boolean
): string {
  if ((current === 'unlinked' && allowUnlinked) || visible.some((c) => c.id === current))
    return current;
  return (
    visible.find((c) => c.configured)?.id ?? visible[0]?.id ?? (allowUnlinked ? 'unlinked' : '')
  );
}

export type CredentialSort =
  'requests' | 'total_tokens' | 'success_rate' | 'ttft_p50_ms' | 'estimated_cost';

/** Unknown values stay last in either direction; zero is a measured value. */
export function sortCredentials(
  rows: CredentialRow[],
  field: CredentialSort,
  ascending: boolean
): CredentialRow[] {
  return [...rows].sort((a, b) => {
    const av = a[field],
      bv = b[field];
    if (av == null && bv == null) return a.id.localeCompare(b.id);
    if (av == null) return 1;
    if (bv == null) return -1;
    return (av - bv) * (ascending ? 1 : -1) || a.id.localeCompare(b.id);
  });
}
