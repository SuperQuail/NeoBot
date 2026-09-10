// client.js —— 统一鉴权 fetch 客户端
// 登录用面板密码；会话 token 存 localStorage，请求头带 X-Token；写操作带 X-CSRF-Token；401 跳登录页。

const TOKEN_KEY = 'neobot-dashboard-token';
const CSRF_KEY = 'neobot-dashboard-csrf';

// 接口前缀跟随 Vite base（'./' 时为相对路径，天然支持 base_path 前缀）。
const API_BASE = import.meta.env.BASE_URL.replace(/\/+$/, '');
const withBase = (path) => (API_BASE === '.' ? path : API_BASE + path);

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || '';
}
export function setToken(t, csrf = '') {
  if (t) localStorage.setItem(TOKEN_KEY, t);
  if (csrf) localStorage.setItem(CSRF_KEY, csrf);
}
export function getCsrf() {
  return localStorage.getItem(CSRF_KEY) || '';
}
export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(CSRF_KEY);
}

function gotoLogin(reason) {
  clearToken();
  if (!location.hash.startsWith('#/login')) {
    location.hash = '#/login' + (reason ? '?reason=' + reason : '');
  }
}

// 面板鉴权状态（公开接口，用于判断是否需要设置密码）
export async function authStatus() {
  try {
    const r = await fetch(withBase('/api/auth/status'), { cache: 'no-store' });
    return await r.json();
  } catch {
    return null;
  }
}

// 登录（不触发 401 跳转，失败返回错误供页面展示）
export async function apiLogin(password) {
  try {
    const r = await fetch(withBase('/api/auth/login'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok || !data.token) {
      return { ok: false, error: data.error || '登录失败 (HTTP ' + r.status + ')' };
    }
    return { ok: true, token: data.token, csrf: data.csrf_token || '' };
  } catch (e) {
    return { ok: false, error: '网络错误: ' + e.message };
  }
}

// 本机首次设置密码（仅未配置密码且来源为本机时可用）
export async function apiSetup(password, confirm) {
  try {
    const r = await fetch(withBase('/api/auth/setup'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password, confirm }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok || !data.token) {
      return { ok: false, error: data.error || '设置密码失败 (HTTP ' + r.status + ')' };
    }
    return { ok: true, token: data.token, csrf: data.csrf_token || '' };
  } catch (e) {
    return { ok: false, error: '网络错误: ' + e.message };
  }
}

export async function checkAuth(token) {
  if (!token) return false;
  try {
    const r = await fetch(withBase('/api/auth/me'), { headers: { 'X-Token': token } });
    return r.ok;
  } catch {
    return false;
  }
}

export async function authFetch(path, init = {}) {
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
    gotoLogin(tk ? 'expired' : 'required');
    throw new Error('unauthorized');
  }
  return r;
}

// 拉 JSON，失败返回 null（不抛出以免打断渲染）
export async function getJSON(path) {
  try {
    const r = await authFetch(path);
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return await r.json();
  } catch (e) {
    if (e.message !== 'unauthorized') console.warn('[api] fetch failed:', path, e);
    return null;
  }
}

// 编辑器需要 HTTP 错误（含 revision 冲突），不能静默返回 null
export async function getResult(path) {
  try {
    const response = await authFetch(path);
    const data = await response.json().catch(() => null);
    return {
      ok: response.ok,
      data,
      error: response.ok ? null : data?.error || 'HTTP ' + response.status,
      status: response.status,
    };
  } catch (error) {
    return { ok: false, data: null, error: error.message, status: 0 };
  }
}

export async function postJSON(path, body) {
  try {
    const r = await authFetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await r.json().catch(() => null);
    return {
      ok: r.ok,
      data,
      error: r.ok ? null : data?.error || 'HTTP ' + r.status,
      status: r.status,
    };
  } catch (e) {
    return { ok: false, data: null, error: e.message, status: 0 };
  }
}
