// terminals/index.ts —— 终端注册表：菜单 id -> 终端定义。

import type { TerminalDefinition } from '../ui/terminal';
import { bridgeTerminals } from './bridge';
import { engineeringTerminals } from './engineering';
import { scienceTerminals } from './science';
import { propTerminals } from './props';
import { minigameStations } from './minigames';

const definitions = [
  ...bridgeTerminals,
  ...engineeringTerminals,
  ...scienceTerminals,
  ...propTerminals,
  ...minigameStations,
];

export const TERMINALS: Record<string, TerminalDefinition> = Object.fromEntries(
  definitions.map((definition) => [definition.id, definition]),
);

/** 菜单类终端（与面板的 8 个页面一一对应） */
export const MENU_TERMINALS = ['dashboard', 'plugins', 'config', 'system', 'usage', 'analysis', 'bots', 'logs'];

export function terminalDefinition(id: string): TerminalDefinition | undefined {
  return TERMINALS[id];
}

export function terminalDefinitions(): TerminalDefinition[] {
  return definitions;
}
