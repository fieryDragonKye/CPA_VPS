import { apiClient } from './client';

/** Tokens belong to a particular read/save, never a global latest-response cache. */
export function readConfigETag(headers: unknown): string | undefined {
  if (!headers || typeof headers !== 'object') return undefined;
  const record = headers as Record<string, unknown> & { get?: (name: string) => unknown };
  const value =
    typeof record.get === 'function'
      ? record.get('etag')
      : Object.entries(record).find(([name]) => name.toLowerCase() === 'etag')?.[1];
  return typeof value === 'string' && /^"[^"\r\n]+"$/.test(value) ? value : undefined;
}

export class ConfigVersionUnavailableError extends Error {
  constructor() {
    super('Configuration version missing after a conditional write');
    this.name = 'ConfigVersionUnavailableError';
  }
}

export async function writeConfigChange(
  method: 'patch' | 'put' | 'delete',
  url: string,
  data: unknown,
  etag: string | undefined,
  headers?: Record<string, string>
): Promise<string | undefined> {
  // Older backends without ETag retain their existing compatibility path.
  if (etag === undefined) {
    if (method === 'delete') await apiClient.delete(url);
    else if (method === 'patch') await apiClient.patch(url, data);
    else await apiClient.put(url, data, headers ? { headers } : undefined);
    return undefined;
  }
  const response = await apiClient.requestRaw({
    method,
    url,
    data,
    headers: { ...headers, 'If-Match': etag },
  });
  const next = readConfigETag(response.headers);
  // Never silently downgrade the remainder of a multi-step save to unconditional writes.
  if (!next) throw new ConfigVersionUnavailableError();
  return next;
}
