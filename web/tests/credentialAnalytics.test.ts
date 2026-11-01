import { afterEach, describe, expect, test } from 'bun:test';
import { readFileSync } from 'node:fs';
import { resolveCredentialSelection, sortCredentials } from '../src/features/credentials/logic';
import { insightsApi, type Credential, type CredentialRow } from '../src/services/api/insights';
import { apiClient } from '../src/services/api/client';

describe('credential comparison', () => {
  test('late default selection preserves a newer manual choice and respects empty groups', () => {
    const visible = [
      { id: 'default', configured: 1 },
      { id: 'manual', configured: 1 },
    ] as Credential[];
    expect(resolveCredentialSelection('manual', visible, true)).toBe('manual');
    expect(resolveCredentialSelection('', visible, true)).toBe('default');
    expect(resolveCredentialSelection('unlinked', visible, true)).toBe('unlinked');
    expect(resolveCredentialSelection('gone', [], false)).toBe('');
  });
  test('keeps unknown values last without turning missing cost or timing into zero', () => {
    const rows = [
      { id: 'unknown', estimated_cost: null, ttft_p50_ms: null },
      { id: 'free', estimated_cost: 0, ttft_p50_ms: 100 },
      { id: 'paid', estimated_cost: 1, ttft_p50_ms: 500 },
    ] as CredentialRow[];
    expect(sortCredentials(rows, 'estimated_cost', true).map((r) => r.id)).toEqual([
      'free',
      'paid',
      'unknown',
    ]);
    expect(sortCredentials(rows, 'estimated_cost', false).map((r) => r.id)).toEqual([
      'paid',
      'free',
      'unknown',
    ]);
    expect(sortCredentials(rows, 'ttft_p50_ms', true).map((r) => r.id)).toEqual([
      'free',
      'paid',
      'unknown',
    ]);
    expect(rows[0].id).toBe('unknown');
  });
});

describe('credential companion calls', () => {
  const originalGet = apiClient.getRaw;
  const originalPost = apiClient.post;
  afterEach(() => {
    apiClient.getRaw = originalGet;
    apiClient.post = originalPost;
  });
  test('passes cancellation and filters to the authenticated companion, never the consuming queue', async () => {
    const calls: { url: string; signal?: AbortSignal; params: unknown }[] = [];
    apiClient.getRaw = (async (url, config) => {
      calls.push({ url, signal: config?.signal as AbortSignal, params: config?.params });
      return { status: 200, data: [] };
    }) as typeof apiClient.getRaw;
    const api = insightsApi('http://127.0.0.1:1');
    const signal = new AbortController().signal;
    const query = {
      range: '24h',
      credential_id: 'fixture-id',
      group_name: 'Fixture',
      model: '',
      provider: '',
      source: '',
      client: '',
      result: '',
      page: 1,
    };
    await api.credentials(signal);
    await api.credentialReport(query, signal);
    expect(calls.map((c) => c.url)).toEqual([
      'http://127.0.0.1:1/v8/management/extensions/insights/credentials',
      'http://127.0.0.1:1/v8/management/extensions/insights/credentials/summary',
    ]);
    expect(calls.every((c) => c.signal === signal)).toBe(true);
    expect(calls[1].params).toEqual(query);
  });
  test('does not interpret failed metadata edits as success', async () => {
    apiClient.post = (async () => ({ saved: false })) as typeof apiClient.post;
    await expect(
      insightsApi('http://127.0.0.1:1').editCredential({
        id: 'fixture',
        alias: 'Demo',
        group_name: '',
        archived: false,
      })
    ).rejects.toThrow();
  });
});

test('credential translations keep the same keys and interpolation variables in every supported locale', () => {
  const load = (locale: string) =>
    JSON.parse(readFileSync(new URL(`../src/i18n/locales/${locale}.json`, import.meta.url), 'utf8'))
      .credentialAnalytics;
  const flatten = (value: Record<string, unknown>, prefix = ''): Record<string, string> =>
    Object.fromEntries(
      Object.entries(value).flatMap(([key, entry]) =>
        typeof entry === 'string'
          ? [[prefix + key, entry]]
          : Object.entries(flatten(entry as Record<string, unknown>, `${prefix}${key}.`))
      )
    );
  const english = flatten(load('en'));
  for (const locale of ['zh-CN', 'zh-TW', 'ko', 'ru', 'vi']) {
    const translated = flatten(load(locale));
    expect(Object.keys(translated).sort()).toEqual(Object.keys(english).sort());
    for (const key of Object.keys(english)) {
      expect(translated[key].length).toBeGreaterThan(0);
      expect(translated[key].match(/\{\{\w+\}\}/g)?.sort() ?? []).toEqual(
        english[key].match(/\{\{\w+\}\}/g)?.sort() ?? []
      );
    }
  }
});
