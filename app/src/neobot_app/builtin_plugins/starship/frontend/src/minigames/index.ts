// minigames/index.ts —— 注册全部小游戏（新增玩法时在这里 import 一次即可）。

import { minigameRegistry } from './api';
import './turret';
import './repair';

export { minigameRegistry };
export type { MinigameContext, MinigameModule } from './api';
