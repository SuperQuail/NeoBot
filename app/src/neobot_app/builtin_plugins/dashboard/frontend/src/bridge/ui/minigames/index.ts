// index.ts —— 小游戏桶导出
//
// 对外只暴露三样东西：三个组件、它们的元数据表、以及统一的 props 契约。
// 游戏机（父级）按 key 索引即可挂载，不需要知道具体是哪个文件实现的。

import type { ComponentType } from 'react';
import TurretGame from './turret';
import CircuitGame from './circuit';
import CargoGame from './cargo';
import { meta as turretMeta } from './turret';
import { meta as circuitMeta } from './circuit';
import { meta as cargoMeta } from './cargo';
import type { MiniGameProps } from './turret';

/** 三个小游戏共用的 props 契约（与各文件内的同名接口结构一致） */
export type { MiniGameProps };

export { TurretGame, CircuitGame, CargoGame };

export type MiniGameKey = 'turret' | 'circuit' | 'cargo';

export interface MiniGameMeta {
  key: MiniGameKey;
  name: string;
  code: string;
  brief: string;
  scoring: string;
}

/** 终端 UI 用元数据：name/code 显示在抬头，brief/scoring 显示在开局简报 */
export const META: Record<MiniGameKey, MiniGameMeta> = {
  turret: turretMeta,
  circuit: circuitMeta,
  cargo: cargoMeta,
};

/** 按 key 取组件，供游戏机动态挂载 */
export const MINIGAME_COMPONENTS: Record<MiniGameKey, ComponentType<MiniGameProps>> = {
  turret: TurretGame,
  circuit: CircuitGame,
  cargo: CargoGame,
};
