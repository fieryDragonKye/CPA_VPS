import { describe, expect, test } from 'bun:test';
import { readFileSync } from 'node:fs';
import { formatTtft } from '../src/features/insights/metrics';

describe('request first-token timing', () => {
  test('never invents timing for missing, legacy or invalid data', () => {
    for (const value of [undefined, null, 0, -1, NaN, Infinity])
      expect(formatTtft(value)).toBe('—');
  });
  test('preserves subsecond detail and explicitly labels units', () => {
    expect(formatTtft(250)).toBe('250ms');
    expect(formatTtft(1250)).toBe('1.25s');
  });
  test('keeps the request table and expanded details aligned', () => {
    const source = readFileSync(
      new URL('../src/features/insights/InsightsPage.tsx', import.meta.url),
      'utf8'
    );
    expect(source).toMatch(/'duration',\s*'ttft'/);
    expect(source).toContain('colSpan={8}');
  });
});
