import { afterEach, expect, spyOn, test } from 'bun:test';
import { AxiosHeaders } from 'axios';
import { apiClient } from '../src/services/api/client';
import { configFileApi } from '../src/services/api/configFile';
import { applyConfigPatch } from '../src/services/api/configPatch';
import { ConfigVersionUnavailableError, readConfigETag } from '../src/services/api/configVersion';

const cleanups: (() => void)[] = [];
afterEach(() => {
  cleanups
    .splice(0)
    .reverse()
    .forEach((cleanup) => cleanup());
  apiClient.setConfig({ apiBase: '', managementKey: '' });
});

function server(options: { conflictAfterFirst?: boolean; omitWriteETag?: boolean } = {}) {
  let version = 1;
  let content = 'server:\n  port: 8317\n';
  const writes: { method: string; etag: string | null; body: string }[] = [];
  const app = Bun.serve({
    hostname: '127.0.0.1',
    port: 0,
    async fetch(request) {
      if (request.method === 'GET')
        return new Response(content, { headers: { ETag: `"${version}"` } });
      const body = await request.text();
      writes.push({ method: request.method, etag: request.headers.get('if-match'), body });
      if (request.headers.get('if-match') !== `"${version}"`) {
        return Response.json({ error: 'precondition_failed' }, { status: 412 });
      }
      content = body;
      version++;
      const etag = `"${version}"`;
      if (options.conflictAfterFirst && writes.length === 1) version++;
      return Response.json(
        { status: 'ok' },
        { headers: options.omitWriteETag ? {} : { ETag: etag } }
      );
    },
  });
  cleanups.push(() => app.stop(true));
  apiClient.setConfig({ apiBase: `http://127.0.0.1:${app.port}`, managementKey: 'fixture-only' });
  return {
    writes,
    change: () => {
      version++;
      content = 'concurrent: keep\n';
    },
    content: () => content,
  };
}

test('accepts case-insensitive strong ETags and AxiosHeaders; rejects weak/invalid values', () => {
  expect(readConfigETag({ ETag: '"one"' })).toBe('"one"');
  expect(readConfigETag(new AxiosHeaders({ etag: '"two"' }))).toBe('"two"');
  for (const value of ['W/"weak"', 'missing-quotes', '"bad\nheader"'])
    expect(readConfigETag({ etag: value })).toBeUndefined();
});

test('source save blocks a concurrent writer and preserves its content', async () => {
  const app = server();
  const snapshot = await configFileApi.fetchConfigSnapshot();
  app.change();
  await expect(configFileApi.saveConfigYaml('local: draft\n', snapshot.etag)).rejects.toMatchObject(
    { status: 412 }
  );
  expect(app.content()).toBe('concurrent: keep\n');
  expect(app.writes).toHaveLength(1);
});

test('another read never replaces the version attached to an earlier draft', async () => {
  const app = server();
  const first = await configFileApi.fetchConfigSnapshot();
  app.change();
  const second = await configFileApi.fetchConfigSnapshot();
  expect(first.etag).not.toBe(second.etag);
  await expect(configFileApi.saveConfigYaml(first.content, first.etag)).rejects.toMatchObject({
    status: 412,
  });
});

test('visual PATCH, empty-map PUT and DELETE chain response versions', async () => {
  const app = server();
  const snapshot = await configFileApi.fetchConfigSnapshot();
  await applyConfigPatch(
    { patch: { server: { port: 9000 } }, emptyMaps: [['example']], deletions: [['old']] },
    apiClient.getConnectionRevision(),
    snapshot.etag
  );
  expect(app.writes.map((w) => [w.method, w.etag])).toEqual([
    ['PATCH', '"1"'],
    ['PUT', '"2"'],
    ['DELETE', '"3"'],
  ]);
});

test('a concurrent edit between visual steps stops without retrying or rolling back', async () => {
  const app = server({ conflictAfterFirst: true });
  const snapshot = await configFileApi.fetchConfigSnapshot();
  await expect(
    applyConfigPatch(
      { patch: { a: 1 }, emptyMaps: [['empty']], deletions: [['old']] },
      apiClient.getConnectionRevision(),
      snapshot.etag
    )
  ).rejects.toMatchObject({ status: 412 });
  expect(app.writes.map((w) => w.method)).toEqual(['PATCH', 'PUT']);
});

test('missing version after a successful write cannot downgrade later steps', async () => {
  const app = server({ omitWriteETag: true });
  const snapshot = await configFileApi.fetchConfigSnapshot();
  await expect(
    applyConfigPatch(
      { patch: { a: 1 }, deletions: [['old']] },
      apiClient.getConnectionRevision(),
      snapshot.etag
    )
  ).rejects.toBeInstanceOf(ConfigVersionUnavailableError);
  expect(app.writes).toHaveLength(1);
});

test('connection change during conditional write prevents all remaining operations', async () => {
  apiClient.setConfig({ apiBase: 'http://first.invalid', managementKey: 'fixture-only' });
  const revision = apiClient.getConnectionRevision();
  const raw = spyOn(apiClient, 'requestRaw').mockImplementation(async () => {
    apiClient.setConfig({ apiBase: 'http://second.invalid', managementKey: 'fixture-only' });
    return { headers: { etag: '"2"' } } as never;
  });
  cleanups.push(() => raw.mockRestore());
  await expect(
    applyConfigPatch({ patch: { a: 1 }, deletions: [['old']] }, revision, '"1"')
  ).rejects.toThrow('Connection changed');
  expect(raw).toHaveBeenCalledTimes(1);
});
