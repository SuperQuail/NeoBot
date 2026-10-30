import { afterEach, expect, it, vi } from 'vitest';
import { api } from '../api/endpoints';
import { setToken } from '../api/client';

afterEach(() => vi.unstubAllGlobals());

it('插件功能和动作复用统一会话、CSRF，并编码路径段', async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValue(new Response(JSON.stringify({ ok: true, result: null }), { status: 200 }));
  vi.stubGlobal('fetch', fetcher);
  setToken('synthetic-session', 'synthetic-csrf');
  await api.pluginSurface('demo name');
  expect(fetcher.mock.calls[0][0]).toBe('/api/plugins/demo%20name/surface');
  const readHeaders = new Headers(fetcher.mock.calls[0][1].headers);
  expect(readHeaders.get('X-Token')).toBe('synthetic-session');
  expect(readHeaders.has('X-CSRF-Token')).toBe(false);

  fetcher.mockResolvedValue(new Response(JSON.stringify({ ok: true, result: [1] }), { status: 200 }));
  await api.pluginAction('demo name', 'items/check', { count: 2, enabled: true });
  const [path, options] = fetcher.mock.calls[1];
  expect(path).toBe('/api/plugins/demo%20name/actions/items%2Fcheck');
  expect(options.method).toBe('POST');
  const headers = new Headers(options.headers);
  expect(headers.get('X-Token')).toBe('synthetic-session');
  expect(headers.get('X-CSRF-Token')).toBe('synthetic-csrf');
  expect(JSON.parse(options.body)).toEqual({ values: { count: 2, enabled: true } });
});

it('动作错误保留 HTTP 状态、业务代码和字段路径', async () => {
  const data = {
    ok: false,
    error: '参数错误',
    code: 'invalid_input',
    fields: [{ path: ['rules', 0, 'count'], type: 'int_type' }],
  };
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(data), { status: 400 })));
  const result = await api.pluginAction('demo', 'rules.set', {});
  expect(result).toEqual({ ok: false, status: 400, error: '参数错误', data });
});
