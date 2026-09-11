// net/api.ts —— 控制台接口与游戏接口的统一客户端。
// 复用面板的会话：同样的 localStorage token / CSRF，同样的 Cookie。

import { consoleApiBase, gameApiBase } from '../config';

const TOKEN_KEY = 'neobot-dashboard-token';
const CSRF_KEY = 'neobot-dashboard-csrf';

export interface ApiResult<T> {
  ok: boolean;
  data: T | null;
  error: string | null;
  status: number;
}

export class UnauthorizedError extends Error {
  constructor() {
    super('需要登录网页面板');
  }
}

function readToken(): string {
  try {
    return localStorage.getItem(TOKEN_KEY) || '';
  } catch {
    return '';
  }
}

function readCsrf(): string {
  try {
    return localStorage.getItem(CSRF_KEY) || '';
  } catch {
    return '';
  }
}

async function request<T>(
  base: string,
  path: string,
  init: RequestInit = {},
): Promise<ApiResult<T>> {
  const headers = new Headers(init.headers || {});
  const token = readToken();
  if (token) headers.set('X-Token', token);
  const method = (init.method || 'GET').toUpperCase();
  if (method !== 'GET' && method !== 'HEAD') {
    const csrf = readCsrf();
    if (csrf) headers.set('X-CSRF-Token', csrf);
    headers.set('Content-Type', 'application/json');
  }
  try {
    const response = await fetch(base + path, {
      ...init,
      headers,
      cache: 'no-store',
    });
    const payload = (await response.json().catch(() => null)) as
      | (T & { error?: string })
      | null;
    if (response.status === 401) {
      return { ok: false, data: null, error: '需要登录网页面板', status: 401 };
    }
    if (!response.ok) {
      return {
        ok: false,
        data: payload,
        error: (payload && payload.error) || 'HTTP ' + response.status,
        status: response.status,
      };
    }
    return { ok: true, data: payload as T, error: null, status: response.status };
  } catch (error) {
    return {
      ok: false,
      data: null,
      error: (error as Error).message || '网络错误',
      status: 0,
    };
  }
}

/** 控制台接口（面板 /api/*），游戏终端的主要数据来源 */
export const consoleApi = {
  base: consoleApiBase,
  get<T>(path: string): Promise<ApiResult<T>> {
    return request<T>(consoleApiBase(), path);
  },
  post<T>(path: string, body?: unknown): Promise<ApiResult<T>> {
    return request<T>(consoleApiBase(), path, {
      method: 'POST',
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  },
};

/** 游戏自有接口（starship 插件的 /game/api/*） */
export const gameApi = {
  base: gameApiBase,
  get<T>(path: string): Promise<ApiResult<T>> {
    return request<T>(gameApiBase(), path);
  },
  post<T>(path: string, body?: unknown): Promise<ApiResult<T>> {
    return request<T>(gameApiBase(), path, {
      method: 'POST',
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  },
};

/** 任何轮询器的结构类型（终端只负责 start/stop，不关心数据类型） */
export interface Pollable {
  start(immediate?: boolean): void;
  stop(): void;
  tick(): Promise<void>;
  readonly running: boolean;
}

/** 轮询器：只在页面可见、且被显式启用时才拉数据 */
export class Poller<T> {
  private timer: number | null = null;
  private busy = false;
  private stopped = true;

  constructor(
    private readonly loader: () => Promise<ApiResult<T>>,
    private readonly intervalMs: number,
    private readonly onData: (data: T) => void,
    private readonly onError?: (message: string) => void,
  ) {}

  start(immediate = true): void {
    if (!this.stopped) return;
    this.stopped = false;
    if (immediate) void this.tick();
    this.timer = window.setInterval(() => void this.tick(), this.intervalMs);
  }

  stop(): void {
    this.stopped = true;
    if (this.timer !== null) {
      window.clearInterval(this.timer);
      this.timer = null;
    }
  }

  get running(): boolean {
    return !this.stopped;
  }

  async tick(): Promise<void> {
    if (this.stopped || this.busy) return;
    this.busy = true;
    try {
      const result = await this.loader();
      if (!this.stopped && result.ok && result.data) {
        this.onData(result.data);
      } else if (!result.ok && this.onError && result.status !== 401) {
        this.onError(result.error || '请求失败');
      }
    } finally {
      this.busy = false;
    }
  }
}
