import { describe, expect, test } from 'bun:test';
import { AuthFilesListCache } from '../src/features/authFiles/authFilesListCache';

describe('auth-files display snapshot', () => {
  test('reuses successful empty lists, but expires after the polling window', () => {
    const cache = new AuthFilesListCache();
    cache.write(cache.begin(1), [], 1000);
    expect(cache.read(1, 1001)).toEqual([]);
    expect(cache.read(1, 241000)).toBeNull();
  });

  test('isolates identities and rejects responses from a previous connection', () => {
    const cache = new AuthFilesListCache();
    const old = cache.begin(1);
    cache.write(old, [{ name: 'first.json' }]);
    expect(cache.read(2)).toBeNull();
    const next = cache.begin(2);
    expect(cache.write(old, [{ name: 'stale.json' }])).toBe(false);
    cache.write(next, [{ name: 'second.json' }]);
    expect(cache.read(2)?.[0].name).toBe('second.json');
    expect(cache.read(1)).toBeNull();
  });

  test('mutation or logout invalidation cannot be undone by an older GET', () => {
    const cache = new AuthFilesListCache();
    const pending = cache.begin(1);
    cache.invalidate();
    expect(cache.write(pending, [{ name: 'deleted.json' }])).toBe(false);
    expect(cache.read(1)).toBeNull();
    expect(cache.write(cache.begin(1), [{ name: 'fresh.json' }])).toBe(true);
  });

  test('retains only display metadata, never raw account keys or nested tokens', () => {
    const cache = new AuthFilesListCache();
    cache.write(cache.begin(1), [
      {
        name: 'example.json',
        email: 'example@example.invalid',
        disabled: false,
        account: 'secret-example',
        access_token: 'secret-example',
        id_token: 'secret-example',
        metadata: { refresh_token: 'secret-example' },
        attributes: { api_key: 'secret-example' },
      },
    ]);
    expect(cache.read(1)).toEqual([
      {
        name: 'example.json',
        email: 'example@example.invalid',
        disabled: false,
      },
    ]);
  });

  test('copies nested display data so callers cannot mutate the cached snapshot', () => {
    const cache = new AuthFilesListCache();
    const files = [
      { name: 'example.json', recentRequests: [{ time: 'now', success: 2, failed: 0 }] },
    ];
    cache.write(cache.begin(1), files);
    files[0].recentRequests[0].success = 100;
    const copy = cache.read(1)!;
    copy[0].recentRequests![0].success = 200;
    expect(cache.read(1)![0].recentRequests![0].success).toBe(2);
  });
});
