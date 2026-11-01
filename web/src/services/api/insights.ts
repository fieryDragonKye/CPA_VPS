import { apiClient } from './client';

export type UsageQuery = {
  range: string;
  model: string;
  provider: string;
  source: string;
  client: string;
  result: string;
  page: number;
  credential_id?: string;
  group_name?: string;
  search?: string;
};

export interface KeeperStatus {
  state: string;
  last_collected: string | null;
  last_error: string | null;
  retention_days: number;
  record_limit: number;
  last_poll?: string | null;
  metadata_error?: string | null;
  pending_count?: number;
}

export interface UsageEvent {
  timestamp: string;
  model: string;
  alias: string;
  provider: string;
  source: string;
  client: string;
  failed: number;
  latency_ms: number;
  ttft_ms?: number | null;
  input_tokens: number;
  output_tokens: number;
  reasoning_tokens: number;
  cached_tokens: number;
  total_tokens: number;
  endpoint: string;
  estimated_cost: number | null;
  pricing_basis?: string | null;
  long_context_applied?: number;
  credential_id?: string | null;
  association_state?: string;
  event_schema?: number;
  token_quality?: string;
  cache_write_tokens?: number | null;
}

export interface UsageSummary {
  requests: number;
  failures: number;
  input_tokens: number;
  output_tokens: number;
  reasoning_tokens: number;
  cached_tokens: number;
  total_tokens: number;
  latency_ms: number | null;
  success_rate: number | null;
  estimated_cost: number | null;
  priced_requests: number;
  stored_records: number;
  database_bytes: number;
  first_record: string | null;
  trend: Array<{ timestamp: string; requests: number; failures: number; total_tokens: number }>;
  models: Array<{ model: string; requests: number; failures: number; total_tokens: number }>;
  options: Record<'model' | 'provider' | 'source' | 'client', string[]>;
}

export interface ModelPrice {
  model: string;
  input: number;
  output: number;
  cache: number;
  basis?: string;
  source_url?: string;
  verified_at?: string;
}

export interface PricingPreset {
  id: string;
  currency: string;
  speed: string;
  verified_at: string;
  long_context_threshold: number;
  models: ModelPrice[];
}

export interface Credential {
  id: string;
  provider: string;
  auth_type: string;
  alias: string;
  group_name: string;
  archived: number;
  configured: number;
  first_seen: string;
  last_seen: string;
}

export interface CredentialStats {
  requests: number;
  failures: number;
  total_tokens: number;
  estimated_cost: number | null;
  priced_requests: number;
  accounted_requests: number;
  ambiguous_requests: number;
  legacy_requests: number;
  execution_identified_requests: number;
  indexed_requests: number;
  stream_known_requests: number;
  success_rate: number | null;
  last_used: string | null;
  ttft_samples: number;
  ttft_p50_ms: number | null;
  ttft_p95_ms: number | null;
  latency_samples: number;
  latency_p50_ms: number | null;
  latency_p95_ms: number | null;
}

export type CredentialRow = Credential & CredentialStats;
export interface CredentialReport {
  credentials: CredentialRow[];
  unlinked: CredentialStats;
  count_basis: string;
  ttft_basis: string;
  price_basis: string;
}

// Keep bearer handling and connection isolation in the existing API client.
// Linux private gateway keeps statistics on the authenticated same-origin path.
export function insightsBase(apiBase: string): string {
  const url = new URL(apiBase);
  url.pathname = '/v8/management/extensions/insights/';
  url.search = '';
  url.hash = '';
  return url.toString();
}

export function insightsApi(apiBase: string) {
  const base = insightsBase(apiBase);
  const acceptedByCompanion = () => true;
  async function read<T>(
    path: string,
    params?: Partial<UsageQuery>,
    signal?: AbortSignal
  ): Promise<T> {
    // Companion authentication can fail independently (for example after key rotation).
    // Handle its HTTP status here so it cannot emit the main CPA client's logout event.
    const response = await apiClient.getRaw(`${base}${path}`, {
      params,
      signal,
      validateStatus: acceptedByCompanion,
    });
    if (response.status < 200 || response.status >= 300) {
      throw new Error('Usage companion request failed');
    }
    return response.data as T;
  }
  return {
    status: (signal?: AbortSignal) => read<KeeperStatus>('status', undefined, signal),
    summary: (params: UsageQuery, signal?: AbortSignal) =>
      read<UsageSummary>('summary', params, signal),
    events: (params: UsageQuery, signal?: AbortSignal) =>
      read<{ rows: UsageEvent[]; total: number; page_size: number }>('events', params, signal),
    credentials: (signal?: AbortSignal) => read<Credential[]>('credentials', undefined, signal),
    credentialReport: (params: UsageQuery, signal?: AbortSignal) =>
      read<CredentialReport>('credentials/summary', params, signal),
    editCredential: async (data: {
      id: string;
      alias: string;
      group_name: string;
      archived: boolean;
    }) => {
      const response = await apiClient.post<{ saved?: boolean }>(`${base}credentials/edit`, data, {
        validateStatus: acceptedByCompanion,
      });
      if (response.saved !== true) throw new Error('Credential edit failed');
    },
    prices: () => read<ModelPrice[]>('prices'),
    pricingPreset: () => read<PricingPreset>('pricing-preset'),
    importPricePreset: async (preset: string) => {
      const result = await apiClient.post<{ saved?: boolean; imported: number }>(
        `${base}prices/import`,
        { preset },
        { validateStatus: acceptedByCompanion }
      );
      if (result.saved !== true) throw new Error('Usage companion request failed');
      return result;
    },
    savePrice: async (data: ModelPrice) => {
      const result = await apiClient.post<{ saved?: boolean }>(`${base}prices`, data, {
        validateStatus: acceptedByCompanion,
      });
      if (result.saved !== true) throw new Error('Usage companion request failed');
      return result;
    },
    export: async (params: UsageQuery) => {
      const response = await apiClient.getRaw(`${base}export`, {
        params,
        responseType: 'blob',
        validateStatus: acceptedByCompanion,
      });
      if (response.status !== 200) throw new Error('Usage companion request failed');
      return response;
    },
  };
}
