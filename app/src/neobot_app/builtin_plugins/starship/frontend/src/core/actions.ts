// core/actions.ts —— 游戏对终端暴露的能力集合（终端不直接依赖 Game，避免循环依赖）。

export type BoostKind = 'sprint' | 'jump';

export interface GameActions {
  /** 触发跃迁；返回是否成功点火 */
  triggerWarp(manual: boolean): boolean;
  warping(): boolean;
  warpPhase(): string;
  systemName(): string;
  /** 合成音效 */
  playChime(kind: string): void;
  playMusic(scale: number[]): void;
  stopMusic(): void;
  setMusicActive(active: boolean): void;
  /** 增益 */
  boost(kind: BoostKind, seconds: number): void;
  boostRemaining(kind: BoostKind): number;
  /** 成就（写入插件数据库） */
  unlockAchievement(key: string, detail?: string): void;
  /** 面向 */
  setSeated(seated: boolean): void;
  isSeated(): boolean;
  lookAtTarget(name: string): void;
  zoomView(factor: number): void;
  /** 小游戏（stationId 用于定位同一玩法的多个站点） */
  openMinigame(id: string, stationId?: string): void;
  toast(message: string, tone?: 'info' | 'ok' | 'warn' | 'error'): void;
}
