// api/client.ts 回归测试 —— 鉴权头、CSRF、401 跳登录、base_path 前缀
import { describe, expect, it, beforeEach, vi } from 'vitest';
import { getJSON, postJSON, getResult, setToken, getToken, getCsrf, clearToken } from '../api/client';

/** 构造一个足够像 Response 的对象，供 fetch mock 返回 */
function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  };
}

/** 取出 fetch mock 的第 n 次调用参数，避免 tsc 对 vi.fn() 的元组推断报错 */
function callArgs(fetchMock: ReturnType<typeof vi.fn>, index = 0): { url: string; headers: Headers } {
  const [url, init] = fetchMock.mock.calls[index] as [string, RequestInit | undefined];
  return { url, headers: new Headers(init?.headers) };
}

describe('api/client 鉴权与错误处理', () => {
  beforeEach(() => {
    clearToken();
    vi.unstubAllGlobals();
  });

  it('有 token 时自动带 X-Token 头', async () => {
    setToken('tk-1', 'csrf-1');
    const fetchMock = vi.fn(async () => jsonResponse({ ok: true }));
    vi.stubGlobal('fetch', fetchMock);

    await getJSON('/api/system');

    const { url, headers } = callArgs(fetchMock);
    expect(url).toBe('/api/system');
    expect(headers.get('X-Token')).toBe('tk-1');
  });

  it('写操作带 CSRF 令牌，读操作不带', async () => {
    setToken('tk-1', 'csrf-1');
    const fetchMock = vi.fn(async () => jsonResponse({ ok: true }));
    vi.stubGlobal('fetch', fetchMock);

    await postJSON('/api/config', { a: 1 });
    await getJSON('/api/config');

    expect(callArgs(fetchMock, 0).headers.get('X-CSRF-Token')).toBe('csrf-1');
    expect(callArgs(fetchMock, 1).headers.get('X-CSRF-Token')).toBeNull();
  });

  it('401 时清空 token 并跳转登录页', async () => {
    setToken('tk-expired', 'csrf-1');
    const fetchMock = vi.fn(async () => jsonResponse({ error: 'unauthorized' }, 401));
    vi.stubGlobal('fetch', fetchMock);

    const result = await getResult('/api/plugins/foo/config');

    expect(result.ok).toBe(false);
    expect(result.status).toBe(401);
    expect(getToken()).toBe('');
    expect(getCsrf()).toBe('');
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('网络异常时 getJSON 返回 null 而不是抛出', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('network down'); }));
    await expect(getJSON('/api/overview')).resolves.toBeNull();
  });

  it('base_path 前缀由 BASE_URL 提供（本面板为相对路径 ./）', async () => {
    const fetchMock = vi.fn(async () => jsonResponse({}));
    vi.stubGlobal('fetch', fetchMock);

    await getJSON('/api/auth/status');

    // 当前构建 base 为 './'，请求应保持根相对路径，不出现 './' 前缀
    expect(callArgs(fetchMock).url).toBe('/api/auth/status');
  });
});
