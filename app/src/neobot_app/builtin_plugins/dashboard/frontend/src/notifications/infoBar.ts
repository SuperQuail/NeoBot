import type { ReactNode } from 'react';

export type InfoBarTone = 'info' | 'ok' | 'warn' | 'err';

export interface InfoBarOptions {
  title: string;
  tone?: InfoBarTone;
  message?: string;
  details?: ReactNode;
  duration?: number;
}

export interface InfoBarItem {
  id: number;
  title: string;
  fullTitle: string;
  tone: InfoBarTone;
  message?: string;
  details?: ReactNode;
  duration: number;
}

interface Host {
  push: (options: InfoBarOptions) => void;
  closeDetails: () => void;
}

const DEFAULT_TITLES: Record<InfoBarTone, string> = {
  info: '提示',
  ok: '操作完成',
  warn: '需要注意',
  err: '操作失败',
};
let nextId = 0;
let host: Host | null = null;

/** 注册唯一展示宿主；旧宿主的卸载不能清掉新宿主。 */
export function connectInfoBarHost(active: Host): () => void {
  host = active;
  return () => {
    if (host === active) host = null;
  };
}

export function infoBar(options: InfoBarOptions): void {
  host?.push(options);
}

export function closeInfoBarDetails(): void {
  host?.closeDetails();
}

/** 简单结果的简写；长内容保留完整详情，摘要仍受统一限长规则约束。 */
export function notify(text: string, tone: InfoBarTone = 'info', duration?: number): void {
  const longText = Array.from(text).length > 28 || text.includes('\n');
  infoBar({
    title: longText ? DEFAULT_TITLES[tone] : text,
    message: longText ? text : undefined,
    tone,
    duration,
  });
}

export function createInfoBarItem(options: InfoBarOptions): InfoBarItem {
  const tone = options.tone ?? 'info';
  const fullTitle = options.title.trim() || DEFAULT_TITLES[tone];
  const characters = Array.from(fullTitle);
  const title =
    characters.length > 32 || fullTitle.includes('\n')
      ? characters.slice(0, 31).join('').replace(/\s+/g, ' ') + '…'
      : fullTitle;
  const fallbackDuration = tone === 'warn' || tone === 'err' ? 0 : 4000;
  const duration =
    typeof options.duration === 'number' && Number.isFinite(options.duration)
      ? Math.max(0, options.duration)
      : fallbackDuration;
  return {
    id: ++nextId,
    title,
    fullTitle,
    tone,
    message: options.message,
    details: options.details,
    duration,
  };
}
