// minigames/api.ts —— 小游戏框架：注册表 + 运行上下文（便于后续扩充玩法）。
//
// 扩展方式（见 README「增加小游戏」）：
//   1. 服务端 minigames.py 里注册元数据（或由其它插件调用 starship 的
//      minigame.register 能力）；
//   2. 客户端新建 minigames/xxx.ts，实现 MinigameModule 并 registerMinigame()。
//
// 两种呈现模式：
//   * 'screen'：占用某块全息屏，用 UiSurface 画 2D 交互（解谜、卡牌、节奏…）；
//   * 'world' ：接管相机与指针锁，在 3D 场景里玩（射击、飞行、驾驶…）。

import type * as THREE from 'three';
import type { GameActions } from '../core/actions';
import type { AudioKit } from '../core/audio';
import type { Hud } from '../core/hud';
import type { Input } from '../core/input';
import type { QualityPreset } from '../config';
import type { ApiResult } from '../net/api';
import type { ShellState } from '../state';
import type { UiSurface } from '../ui/surface';

export interface MinigameScoreResult {
  ok: boolean;
  best?: number;
  rank?: number;
  error?: string;
}

export interface MinigameContext {
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  input: Input;
  hud: Hud;
  audio: AudioKit;
  shell: ShellState;
  quality: QualityPreset;
  actions: GameActions;
  playerPosition: THREE.Vector3;
  submitScore(game: string, score: number, durationMs: number, detail: string): Promise<MinigameScoreResult>;
  leaderboard(game: string, limit: number): Promise<ApiResult<{ items?: Array<{ player?: string; score?: number }> }>>;
  toast(message: string, tone?: 'info' | 'ok' | 'warn' | 'error'): void;
  /** 结束小游戏并回到舰内 */
  exit(reason?: string): void;
  /** 结算界面（显示得分与名次，可重来或退出） */
  finish(summary: { title: string; lines: string[]; score: number; canRetry: boolean }): void;
  setHud(info: { title: string; score: string; extra?: string; hint?: string } | null): void;
  rng(): number;
}

export interface MinigameModule {
  id: string;
  name: string;
  description: string;
  icon: string;
  mode: 'screen' | 'world';
  /** 进入位置（world 模式）：相机绝对坐标与朝向 */
  viewpoint?(ctx: MinigameContext): { position: THREE.Vector3; yaw: number; pitch: number };
  start?(ctx: MinigameContext): void;
  update?(dt: number, ctx: MinigameContext): void;
  /** screen 模式：绘制到全息屏 */
  draw?(ui: UiSurface, ctx: MinigameContext): void;
  onPointerMove?(dx: number, dy: number, ctx: MinigameContext): void;
  onPointerDown?(ctx: MinigameContext): void;
  /** screen 模式：在全息屏上点击（ui.cursor 已是屏幕坐标） */
  onScreenClick?(ui: UiSurface, ctx: MinigameContext): void;
  onKey?(key: string, ctx: MinigameContext): void;
  dispose?(ctx: MinigameContext): void;
}

class MinigameRegistry {
  private readonly modules = new Map<string, MinigameModule>();

  register(module: MinigameModule): void {
    this.modules.set(module.id, module);
  }

  get(id: string): MinigameModule | undefined {
    return this.modules.get(id);
  }

  list(): MinigameModule[] {
    return [...this.modules.values()];
  }
}

export const minigameRegistry = new MinigameRegistry();

export function registerMinigame(module: MinigameModule): void {
  minigameRegistry.register(module);
}
