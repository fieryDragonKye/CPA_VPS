import { expect, test } from 'bun:test';
import { formatEstimatedCost } from '../src/features/insights/metrics';

test('unknown costs are distinct from explicitly zero priced usage', () => {
  for (const value of [null, undefined, NaN, Infinity, -1])
    expect(formatEstimatedCost(value)).toBe('—');
  expect(formatEstimatedCost(0)).toBe('$0.0000');
});

test('tiny positive usage is never rendered as a free request', () => {
  expect(formatEstimatedCost(0.0000001)).toBe('<$0.000001');
  expect(formatEstimatedCost(0.000001)).toBe('$0.000001');
  expect(formatEstimatedCost(0.0148)).toBe('$0.0148');
});
