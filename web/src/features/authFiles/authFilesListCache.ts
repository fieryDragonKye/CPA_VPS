import type { AuthFileItem } from '@/types';

const CACHE_TTL_MS = 240_000;
const scalarFields = [
  'type',
  'provider',
  'email',
  'projectId',
  'size',
  'authIndex',
  'supportsQuota',
  'quotaProvider',
  'quotaPluginId',
  'runtimeOnly',
  'disabled',
  'unavailable',
  'status',
  'statusMessage',
  'lastRefresh',
  'modified',
  'priority',
  'weight',
  'note',
  'successCount',
  'failureCount',
  'plan_type',
  'planType',
  'prefix',
  'last_refresh',
] as const;

// Deliberately omit raw account, metadata, attributes, id_token and other credentials.
// Fresh responses remain unchanged in component state; this snapshot is display metadata only.
const snapshot = (files: AuthFileItem[]): AuthFileItem[] =>
  files.map((file) => {
    const item: AuthFileItem = { name: file.name };
    for (const field of scalarFields) {
      const value = file[field];
      if (
        typeof value === 'string' ||
        typeof value === 'boolean' ||
        (typeof value === 'number' && Number.isFinite(value))
      )
        Object.assign(item, { [field]: value });
    }
    const recent = file.recentRequests ?? file.recent_requests;
    if (Array.isArray(recent)) {
      item.recentRequests = recent.map(({ time, success, failed }) => ({ time, success, failed }));
    }
    if (file.cooldownSnapshot) {
      const { receivedAtMs, observedAt, records } = file.cooldownSnapshot;
      item.cooldownSnapshot = {
        receivedAtMs,
        observedAt,
        records:
          records?.map(
            ({ scope, modelKey, reason, retryAt, remainingSeconds, backoffLevel, httpStatus }) => ({
              scope,
              modelKey,
              reason,
              retryAt,
              remainingSeconds,
              backoffLevel,
              httpStatus,
            })
          ) ?? null,
      };
    }
    return item;
  });

export class AuthFilesListCache {
  private revision = -1;
  private generation = 0;
  private entry: { savedAt: number; files: AuthFileItem[] } | null = null;

  begin(revision: number) {
    if (revision !== this.revision) {
      this.invalidate();
      this.revision = revision;
    }
    return { revision, generation: this.generation };
  }

  read(revision: number, now = Date.now()): AuthFileItem[] | null {
    if (revision !== this.revision || !this.entry) return null;
    if (now - this.entry.savedAt >= CACHE_TTL_MS) {
      this.entry = null;
      return null;
    }
    return snapshot(this.entry.files);
  }

  write(ticket: { revision: number; generation: number }, files: AuthFileItem[], now = Date.now()) {
    if (ticket.revision !== this.revision || ticket.generation !== this.generation) return false;
    this.entry = { savedAt: now, files: snapshot(files) };
    return true;
  }

  invalidate() {
    this.generation += 1;
    this.entry = null;
  }
}

// One bounded in-memory snapshot. Never localStorage, sessionStorage or IndexedDB.
export const authFilesListCache = new AuthFilesListCache();
