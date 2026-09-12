// client.ts —— 统一鉴权 fetch 客户端
// 登录用面板密码；会话 token 存 localStorage，请求头带 X-Token；写操作带 X-CSRF-Token；401 跳登录页。
import type { Result } from './types';

const TOKEN_KEY = 'neobot-dashboard-token';
const CSRF_KEY = 'neobot-dashboard-csrf';

// 接口前缀跟随 Vite base（'./' 时为相对路径，天然支持 base_path 前缀）。
const API_BASE = import.meta.env.BASE_URL.replace(/\/+$/, '');
const withBase = (path: string): string => (API_BASE === '.' ? path : API_BASE + path);

export interface AuthStatus {
  ok?: boolean;
  authenticated?: boolean;
  configured?: boolean;
  setup_required?: boolean;
  setup_allowed?: boolean;
  loopback?: boolean;
  can_manage?: boolean;
  base_path?: string;
  version?: string;
}

export interface LoginResult {
  ok: boolean;
  token?: string;
  csrf?: string;
  error?: string;
}

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) || '';
}

export function setToken(token: string, csrf = ''): void {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  if (csrf) localStorage.setItem(CSRF_KEY, csrf);
}

export function getCsrf(): string {
  return localStorage.getItem(CSRF_KEY) || '';
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(CSRF_KEY);
}

function gotoLogin(reason?: string): void {
  clearToken();
  if (!location.hash.startsWith('#/login')) {
    location.hash = '#/login' + (reason ? '?reason=' + reason : '');
  }
}

// 面板鉴权状态（公开接口，用于判断是否需要设置密码）
export async function authStatus(): Promise<AuthStatus | null> {
  try {
    const r = await fetch(withBase('/api/auth/status'), { cache: 'no-store' });
    return (await r.json()) as AuthStatus;
  } catch {
    return null;
  }
}

// 登录（不触发 401 跳转，失败返回错误供页面展示）
export async function apiLogin(password: string): Promise<LoginResult> {
  try {
    const r = await fetch(withBase('/api/auth/login'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password }),
    });
    const data = (await r.json().catch(() => ({}))) as { token?: string; csrf_token?: string; error?: string };
    if (!r.ok || !data.token) {
      return { ok: false, error: data.error || '登录失败 (HTTP ' + r.status + ')' };
    }
    return { ok: true, token: data.token, csrf: data.csrf_token || '' };
  } catch (e) {
    return { ok: false, error: '网络错误: ' + (e as Error).message };
  }
}

// 本机首次设置密码（仅未配置密码且来源为本机时可用）
export async function apiSetup(password: string, confirm: string): Promise<LoginResult> {
  try {
    const r = await fetch(withBase('/api/auth/setup'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password, confirm }),
    });
    const data = (await r.json().catch(() => ({}))) as { token?: string; csrf_token?: string; error?: string };
    if (!r.ok || !data.token) {
      return { ok: false, error: data.error || '设置密码失败 (HTTP ' + r.status + ')' };
    }
    return { ok: true, token: data.token, csrf: data.csrf_token || '' };
  } catch (e) {
    return { ok: false, error: '网络错误: ' + (e as Error).message };
  }
}

export async function checkAuth(token: string): Promise<boolean> {
  if (!token) return false;
  try {
    const r = await fetch(withBase('/api/auth/me'), { headers: { 'X-Token': token } });
    return r.ok;
  } catch {
    return false;
  }
}

export async function authFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const tk = getToken();
  const headers = new Headers(init.headers || {});
  if (tk) headers.set('X-Token', tk);
  const method = (init.method || 'GET').toUpperCase();
  if (method !== 'GET' && method !== 'HEAD') {
    const csrf = getCsrf();
    if (csrf) headers.set('X-CSRF-Token', csrf);
  }
  const r = await fetch(withBase(path), { ...init, headers, cache: 'no-store' });
  if (r.status === 401) {
    // 只清会话并跳登录，不抛异常：调用方需要拿到真实状态码，
    // 网络错误与未授权必须能区分。
    gotoLogin(tk ? 'expired' : 'required');
  }
  return r;
}

/** 401 后会话已被清空并跳转登录页，调用方据此静默处理 */
export const isUnauthorized = (response: Response): boolean => response.status === 401;

// 拉 JSON，失败返回 null（不抛出以免打断渲染）
export async function getJSON<T>(path: string): Promise<T | null> {
  try {
    const r = await authFetch(path);
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return (await r.json()) as T;
  } catch (e) {
    console.warn('[api] fetch failed:', path, e);
    return null;
  }
}

// 编辑器需要 HTTP 错误（含 revision 冲突），不能静默返回 null
export async function getResult<T>(path: string): Promise<Result<T>> {
  try {
    const response = await authFetch(path);
    const data = (await response.json().catch(() => null)) as (T & { error?: string }) | null;
    return {
      ok: response.ok,
      data: data as T | null,
      error: response.ok ? null : data?.error || 'HTTP ' + response.status,
      status: response.status,
    };
  } catch (error) {
    return { ok: false, data: null, error: (error as Error).message, status: 0 };
  }
}

/** 写操作的公共实现：POST / PUT / DELETE 只差 method，错误与状态码语义完全一致 */
async function sendJSON<T>(method: string, path: string, body?: unknown): Promise<Result<T>> {
  try {
    const r = await authFetch(path, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = (await r.json().catch(() => null)) as (T & { error?: string }) | null;
    return {
      ok: r.ok,
      data: data as T | null,
      error: r.ok ? null : data?.error || 'HTTP ' + r.status,
      status: r.status,
    };
  } catch (e) {
    return { ok: false, data: null, error: (e as Error).message, status: 0 };
  }
}

export function postJSON<T>(path: string, body?: unknown): Promise<Result<T>> {
  return sendJSON<T>('POST', path, body);
}

/** PUT：档案编辑等写操作需要区分 409 乐观锁冲突，因此必须带 HTTP 状态码 */
export function putJSON<T>(path: string, body?: unknown): Promise<Result<T>> {
  return sendJSON<T>('PUT', path, body);
}

/** DELETE：档案删除等写操作（body 里带 version 做乐观锁） */
export function deleteJSON<T>(path: string, body?: unknown): Promise<Result<T>> {
  return sendJSON<T>('DELETE', path, body);
}
