// store.ts —— 舰内进度存档（本地持久化 + 订阅）
//
// 只存「探索类」数据（访问记录、物资、成就、小游戏最好成绩），
// 舰况与业务数据永远实时向 /api 请求，不做本地缓存，避免面板显示过期数据。

import { useSyncExternalStore } from 'react';
import type { AchievementDef, ItemId, MiniGameRecord, PanelId, ShipLog } from './types';
import { ACHIEVEMENTS } from './types';

const STORAGE_KEY = 'neobot-bridge-log';
const LOG_VERSION = 1;

function emptyLog(): ShipLog {
  return {
    version: LOG_VERSION,
    visited: [],
    inventory: {},
    achievements: [],
    miniGames: {},
    distance: 0,
    lastPos: null,
  };
}

/** localStorage 可能被禁用（隐私模式），全部访问都要能降级为纯内存 */
function readStorage(): ShipLog {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return emptyLog();
    const parsed = JSON.parse(raw) as Partial<ShipLog>;
    if (!parsed || parsed.version !== LOG_VERSION) return emptyLog();
    return {
      ...emptyLog(),
      ...parsed,
      visited: Array.isArray(parsed.visited) ? parsed.visited : [],
      achievements: Array.isArray(parsed.achievements) ? parsed.achievements : [],
      inventory: parsed.inventory ?? {},
      miniGames: parsed.miniGames ?? {},
    };
  } catch {
    return emptyLog();
  }
}

let current: ShipLog = readStorage();
const listeners = new Set<() => void>();

function emit(): void {
  for (const listener of listeners) listener();
}

function persist(): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(current));
  } catch {
    // 存不下就只在内存里保留，不影响游戏进行
  }
}

/** 以不可变方式更新存档，通知所有订阅者 */
export function updateLog(patch: (log: ShipLog) => ShipLog): ShipLog {
  const next = patch(current);
  if (next === current) return current;
  current = next;
  persist();
  emit();
  return current;
}

export function getLog(): ShipLog {
  return current;
}

export function subscribeLog(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** React 侧读取存档 */
export function useShipLog(): ShipLog {
  return useSyncExternalStore(subscribeLog, getLog, getLog);
}

/** 舰内通知（成就、解锁、拾取）由这里广播，HUD 负责显示 */
export interface BridgeNotice {
  id: number;
  text: string;
  tone: 'info' | 'good' | 'warn';
}

const noticeListeners = new Set<(notice: BridgeNotice) => void>();
let noticeSeq = 0;

export function onNotice(listener: (notice: BridgeNotice) => void): () => void {
  noticeListeners.add(listener);
  return () => noticeListeners.delete(listener);
}

export function notify(text: string, tone: BridgeNotice['tone'] = 'info'): void {
  noticeSeq += 1;
  const notice: BridgeNotice = { id: noticeSeq, text, tone };
  for (const listener of noticeListeners) listener(notice);
}

function grantAchievement(id: string): void {
  const def: AchievementDef | undefined = ACHIEVEMENTS.find((item) => item.id === id);
  if (!def) return;
  if (getLog().achievements.includes(id)) return;
  updateLog((log) => ({ ...log, achievements: [...log.achievements, id] }));
  notify(`成就解锁 · ${def.name}`, 'good');
}

/** 访客记录：首次踏入某终端范围时给一次提示并累计「全系统在线」 */
export function markVisited(id: PanelId): void {
  const log = getLog();
  if (log.visited.includes(id)) return;
  updateLog((prev) => ({ ...prev, visited: [...prev.visited, id] }));
  notify(`终端已接入 · ${id.toUpperCase()}`, 'info');
  if (getLog().visited.length >= 8) grantAchievement('all-terminals');
}

export function collectItem(id: ItemId, count = 1): void {
  updateLog((log) => ({
    ...log,
    inventory: { ...log.inventory, [id]: (log.inventory[id] ?? 0) + count },
  }));
  const total = Object.values(getLog().inventory).reduce((sum, n) => sum + (n ?? 0), 0);
  if (total >= 10) grantAchievement('collector');
}

export function consumeItem(id: ItemId, count = 1): boolean {
  const owned = getLog().inventory[id] ?? 0;
  if (owned < count) return false;
  updateLog((log) => ({
    ...log,
    inventory: { ...log.inventory, [id]: owned - count },
  }));
  return true;
}

export function recordMiniGame(key: string, score: number): MiniGameRecord {
  const previous = getLog().miniGames[key];
  const record: MiniGameRecord = {
    best: Math.max(score, previous?.best ?? 0),
    plays: (previous?.plays ?? 0) + 1,
    lastAt: Date.now(),
  };
  updateLog((log) => ({ ...log, miniGames: { ...log.miniGames, [key]: record } }));
  return record;
}

export function addDistance(meters: number): void {
  if (meters <= 0) return;
  updateLog((log) => ({ ...log, distance: log.distance + meters }));
}

export function rememberPosition(x: number, y: number, z: number): void {
  updateLog((log) => ({ ...log, lastPos: [x, y, z] }));
}

export function unlock(id: string): void {
  grantAchievement(id);
}

export function resetLog(): void {
  current = emptyLog();
  persist();
  emit();
}

/** 供测试与非持久化场景使用：绕过 localStorage 直接注入状态 */
export function __setLogForTest(log: ShipLog): void {
  current = log;
  emit();
}
