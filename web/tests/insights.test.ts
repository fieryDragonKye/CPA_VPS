import { describe, expect, test } from 'bun:test';
import { insightsBase } from '../src/services/api/insights';

describe('usage companion endpoint isolation', () => {
  test('keeps SSH gateway origin and clears connection suffixes', () => {
    expect(insightsBase('http://127.0.0.1:18317/v8/management?x=1#test')).toBe(
      'http://127.0.0.1:18317/v8/management/extensions/insights/'
    );
    expect(insightsBase('http://localhost:8317')).toBe(
      'http://localhost:8317/v8/management/extensions/insights/'
    );
  });

  test('keeps remote HTTPS and port for future same-origin deployment', () => {
    expect(insightsBase('https://proxy.example.com:8443')).toBe(
      'https://proxy.example.com:8443/v8/management/extensions/insights/'
    );
  });
});
