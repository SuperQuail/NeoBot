// index.ts —— 舰载全息面板出口
//
// 对外契约（其它模块正在按这个契约开发，字段名/类型不要改）：
//   PanelProps        —— 每个面板组件收到的 props
//   PanelMeta         —— 终端切换器使用的元数据
//   PANEL_META        —— PanelId -> 元数据
//   PANEL_COMPONENTS  —— PanelId -> 面板组件
//
// 说明：terminal/title 直接取自 core/types.ts 的 STATIONS（唯一数据源），
// 面板抬头渲染的是父级传入的 station 对象，二者始终一致，不会各写一套文案。

import type { ComponentType } from 'react';
import type { PanelId, Station, Vital } from '../../core/types';
import { STATION_BY_ID } from '../../core/types';
import OverviewPanel from './overview';
import CommsPanel from './comms';
import NavPanel from './nav';
import PowerPanel from './power';
import MainframePanel from './mainframe';
import FlightPanel from './flight';
import DrydockPanel from './drydock';
import FireControlPanel from './firecontrol';
// 面板样式随出口一起加载：使用方只需 import 本模块，样式必定就位
import './panels.css';

export interface PanelProps {
  /** The station this panel is mounted on (from STATION_BY_ID). */
  station: Station;
  /** Ship vitals (0..100) derived by the parent from real /api/system data. */
  vitals: Vital[];
  /** Close the holographic terminal and return to free-roam. */
  onClose: () => void;
  /** Open one of the three minigames by key: 'turret' | 'circuit' | 'cargo'. Parent handles the overlay. */
  onLaunchMiniGame: (key: 'turret' | 'circuit' | 'cargo') => void;
  /**
   * Increments whenever the user presses 刷新 in the terminal frame; refetch on change.
   * 终端外框（engine 侧）持有刷新按钮与 Esc（捕获阶段），面板只对 refreshToken 变化做出反应。
   */
  refreshToken: number;
}

export interface PanelMeta {
  id: PanelId;
  /** Holographic header line 1, e.g. 'COMMAND CONSOLE'. */
  terminal: string;
  /** Holographic header line 2, Chinese title. */
  title: string;
  /** Keyboard shortcut hint, e.g. '3'. */
  hotkey?: string;
  /** One-line description shown in the terminal switcher. */
  brief: string;
}

/** 终端一句话说明（切换器里显示；抬头文案来自 STATIONS，不在这里重复） */
const BRIEFS: Record<PanelId, string> = {
  overview: '舰况总览 / 消息趋势 / 调用排行 / 后台任务',
  comms: '增量日志流 / 级别过滤 / 跟随与搜索',
  nav: '消息与延迟航迹 / 用量、Token 与花费',
  power: 'CPU·内存·磁盘·负载实测值与反应堆配能',
  mainframe: '插件启停 / 热重载 / 安装卸载 / 在线配置',
  flight: '机器人状态 / 延迟 / 消息计数 / 活跃排行',
  drydock: '环境变量 / 模型库 / 角色分配与连通性测试',
  firecontrol: 'config.toml 表单与原始编辑 / 损管读数',
};

function meta(id: PanelId, hotkey: string): PanelMeta {
  const station = STATION_BY_ID[id];
  return {
    id,
    terminal: station.terminal,
    title: station.title,
    hotkey,
    brief: BRIEFS[id],
  };
}

/** 数字键顺序与 core/types.ts 的 STATIONS 顺序一致（input.ts 的 HOTKEY_ORDER 同源） */
export const PANEL_META: Record<PanelId, PanelMeta> = {
  overview: meta('overview', '1'),
  comms: meta('comms', '2'),
  nav: meta('nav', '3'),
  power: meta('power', '4'),
  mainframe: meta('mainframe', '5'),
  flight: meta('flight', '6'),
  drydock: meta('drydock', '7'),
  firecontrol: meta('firecontrol', '8'),
};

export const PANEL_COMPONENTS: Record<PanelId, ComponentType<PanelProps>> = {
  overview: OverviewPanel,
  comms: CommsPanel,
  nav: NavPanel,
  power: PowerPanel,
  mainframe: MainframePanel,
  flight: FlightPanel,
  drydock: DrydockPanel,
  firecontrol: FireControlPanel,
};

export {
  OverviewPanel,
  CommsPanel,
  NavPanel,
  PowerPanel,
  MainframePanel,
  FlightPanel,
  DrydockPanel,
  FireControlPanel,
};
