// pages/plugins/pluginProps.ts —— 插件工作区各视图共享的 props 契约
// 由 PluginsPage 持有状态与副作用，展示组件只消费数据 + 回传意图（不直接发请求）。
import type { Dispatch, RefObject, SetStateAction } from 'react';
import type { ConfigDocument, Plugin, ProxyInfo, Result } from '../../api/types';

/** act() 的返回值：所有插件操作统一走它 */
export type ActResult = Result<any> | undefined;

export interface PluginActionHandlers {
  /** 执行一次受管操作：内部维护 operation/busyRef 并 toast 结果 */
  act: (key: string, fn: () => Promise<Result<any>>, success: string) => Promise<ActResult>;
  load: () => Promise<void>;
  read: (id: string) => Promise<void>;
  save: (reload: boolean) => Promise<void>;
  applyDocument: (data: ConfigDocument, preferredMode?: string) => void;
}

export interface PluginPermissions {
  manage_enabled: boolean;
  hot_reload: boolean;
}

/** 列表侧栏 */
export interface PluginListPanelProps {
  items: Plugin[];
  visible: Plugin[];
  statusLabels: Record<string, string>;
  statusGroups: Array<[string, string]>;
  pluginId: (plugin: Plugin) => string;
  selectedId: string;
  collapsed: Record<string, boolean>;
  setCollapsed: Dispatch<SetStateAction<Record<string, boolean>>>;
  filter: string;
  setFilter: (value: string) => void;
  sourceFilter: string;
  setSourceFilter: (value: string) => void;
  sourceFilters: Array<[string, string]>;
  searchRef: RefObject<HTMLInputElement>;
  listLoading: boolean;
  listError: string;
  operation: string;
  permissions: PluginPermissions;
  proxy: ProxyInfo;
  onSelect: (plugin: Plugin) => void;
  onOpenInstall: () => void;
  onOpenProxy: () => void;
  onReload: () => void;
}

/** 右侧编辑器（工具条 + 详情 + 配置体 + 页脚） */
export interface PluginEditorPanelProps extends PluginActionHandlers {
  selected?: Plugin;
  selectedId: string;
  itemsCount: number;
  statusLabels: Record<string, string>;
  permissions: PluginPermissions;
  configDocument: ConfigDocument | null;
  proxy: ProxyInfo;
  mode: 'form' | 'toml';
  source: string;
  draft: Record<string, any>;
  errors: Array<{ path?: string; message?: string }>;
  configError: string;
  notice: { text?: string; warning?: boolean } | null;
  loading: boolean;
  operation: string;
  dirty: boolean;
  isConsole: boolean;
  canEdit: boolean;
  canSave: boolean;
  canReload: boolean;
  canManage: boolean;
  editorVersion: number;
  actionsRef: RefObject<HTMLDetailsElement>;
  onBack: () => void;
  onModeChange: (mode: 'form' | 'toml') => void;
  onSourceChange: (value: string) => void;
  onChangeField: (path: string[], value: unknown) => void;
  onRetryRead: () => void;
}
