// config.ts —— 游戏运行期配置、画质档位与接口地址推导。
// 设计约束：不进入游戏就不产生任何开销，因此这里只做纯计算，不发起请求。

/** 服务端 /game/api/bootstrap 返回的启动配置 */
export interface GameBootstrap {
  title: string;
  prefix: string;
  panel_base: string;
  quality: QualityLevel;
  allow_minigames: boolean;
  enable_audio: boolean;
  jump_interval_minutes: number;
  leaderboard_size: number;
  minigames: MinigameSpecPayload[];
  version: string;
  server_time: string;
}

export interface MinigameSpecPayload {
  id: string;
  name: string;
  description: string;
  icon: string;
  score_label: string;
  max_score: number;
  higher_is_better: boolean;
  tags: string[];
  order: number;
}

export type QualityLevel = 'low' | 'medium' | 'high';

export interface QualityPreset {
  label: string;
  pixelRatio: number;
  antialias: boolean;
  asteroidCount: number;
  trafficCount: number;
  starCount: number;
  particles: number;
  viewDistance: number;
  fogDensity: number;
  refreshIdleTerminals: boolean;
}

export const QUALITY_PRESETS: Record<QualityLevel, QualityPreset> = {
  low: {
    label: '节能',
    pixelRatio: 0.85,
    antialias: false,
    asteroidCount: 90,
    trafficCount: 2,
    starCount: 2200,
    particles: 220,
    viewDistance: 1400,
    fogDensity: 0.0016,
    refreshIdleTerminals: false,
  },
  medium: {
    label: '标准',
    pixelRatio: 1,
    antialias: true,
    asteroidCount: 200,
    trafficCount: 4,
    starCount: 4200,
    particles: 420,
    viewDistance: 2200,
    fogDensity: 0.0011,
    refreshIdleTerminals: false,
  },
  high: {
    label: '高画质',
    pixelRatio: 1.5,
    antialias: true,
    asteroidCount: 340,
    trafficCount: 7,
    starCount: 7200,
    particles: 720,
    viewDistance: 3200,
    fogDensity: 0.0008,
    refreshIdleTerminals: true,
  },
};

export const QUALITY_ORDER: QualityLevel[] = ['low', 'medium', 'high'];

const QUALITY_KEY = 'neobot-starship-quality';
const PLAYER_KEY = 'neobot-starship-player';
const SEEN_KEY = 'neobot-starship-seen';
const SHIP_NAME_KEY = 'neobot-starship-ship-name';
const SHIP_NAME_CUSTOM_KEY = 'neobot-starship-ship-name-custom';
export const DEFAULT_SHIP_NAME = '亚顿之矛';
// A denied/quota-limited store must not prevent boarding or lose edits this session.
const memoryStorage = new Map<string, string>();

function readPreference(key: string): string | null {
  if (memoryStorage.has(key)) return memoryStorage.get(key)!;
  try { return localStorage.getItem(key); } catch { return null; }
}

function writePreference(key: string, value: string): void {
  memoryStorage.set(key, value);
  try { localStorage.setItem(key, value); } catch { /* Session fallback above. */ }
}

/** Unicode code points, not UTF-16 units; surrounding whitespace is not part of a name. */
export function normalizeShipName(value: string): string {
  const name = value.trim();
  const length = Array.from(name).length;
  if (length < 1 || length > 24) throw new RangeError('舰名须为 1–24 个字符（不含首尾空格）。');
  return name;
}

/** Independent of player/captain identity. Invalid persisted data falls back safely. */
export function loadShipName(): string {
  try {
    const name = normalizeShipName(readPreference(SHIP_NAME_KEY) ?? DEFAULT_SHIP_NAME);
    // Only migrate the legacy default, never another saved name. New explicit
    // choices (even the old default itself) carry a marker and remain untouched.
    if (name === '曙光之矛' && readPreference(SHIP_NAME_CUSTOM_KEY) !== '1') {
      writePreference(SHIP_NAME_KEY, DEFAULT_SHIP_NAME);
      return DEFAULT_SHIP_NAME;
    }
    return name;
  }
  catch { return DEFAULT_SHIP_NAME; }
}

/** Returns trimmed name; throws RangeError on invalid input, never on storage failure. */
export function saveShipName(value: string): string {
  const name = normalizeShipName(value);
  writePreference(SHIP_NAME_KEY, name);
  writePreference(SHIP_NAME_CUSTOM_KEY, '1');
  return name;
}

export function loadQuality(fallback: QualityLevel): QualityLevel {
  const stored = readPreference(QUALITY_KEY);
  if (stored === 'low' || stored === 'medium' || stored === 'high') return stored;
  return fallback;
}

export function saveQuality(level: QualityLevel): void {
  writePreference(QUALITY_KEY, level);
}

export function loadPlayerName(): string {
  return readPreference(PLAYER_KEY) || '舰长';
}

export function savePlayerName(name: string): void {
  writePreference(PLAYER_KEY, Array.from(name.trim()).slice(0, 32).join('') || '舰长');
}

export function hasSeenIntro(): boolean {
  return readPreference(SEEN_KEY) === '1';
}

export function markIntroSeen(): void {
  writePreference(SEEN_KEY, '1');
}

/**
 * 面板根路径（base_path），例如 "" 或 "/nb"。
 *
 * 游戏页面在 {base}{route}/ 下，面板接口在 {base}/api/...，
 * 因此所有请求都是 面板根路径 + 以 / 开头的接口路径。
 */
export function panelBase(): string {
  const url = new URL('../', window.location.href);
  return url.pathname.replace(/\/+$/, '');
}

/** 控制台接口前缀（与面板页面同源，路径与面板前端一致） */
export function consoleApiBase(): string {
  return panelBase();
}

/** 游戏自有接口前缀：当前页面路径去掉结尾斜杠（{base}{route}） */
export function gameApiBase(): string {
  return window.location.pathname.replace(/\/+$/, '');
}

/** 控制台首页地址（HUD 里的「返回控制台」链接用） */
export function consoleHomeUrl(): string {
  return panelBase() + '/';
}
