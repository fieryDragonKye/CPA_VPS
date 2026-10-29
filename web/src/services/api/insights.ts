import { apiClient } from './client';

export type UsageQuery = {
  range: string;
  model: string;
  provider: string;
  source: string;
  client: string;
  result: string;
  page: number;
};

export interface KeeperStatus {
  state: string;
  last_collected: string | null;
  last_error: string | null;
  retention_days: number;
  record_limit: number;
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
  async function read<T>(path: string, params?: UsageQuery): Promise<T> {
    // Companion authentication can fail independently (for example after key rotation).
    // Handle its HTTP status here so it cannot emit the main CPA client's logout event.
    const response = await apiClient.getRaw(`${base}${path}`, {
      params,
      validateStatus: acceptedByCompanion,
    });
    if (response.status < 200 || response.status >= 300) {
      throw new Error('Usage companion request failed');
    }
    return response.data as T;
  }
  return {
    status: () => read<KeeperStatus>('status'),
    summary: (params: UsageQuery) => read<UsageSummary>('summary', params),
    events: (params: UsageQuery) =>
      read<{ rows: UsageEvent[]; total: number; page_size: number }>('events', params),
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
