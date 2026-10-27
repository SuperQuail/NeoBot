// 插件列表、安装冲突、依赖、扩展入口与代理。

/** 插件 /api/plugins */
export type PluginStatus = 'loaded' | 'disabled' | 'error' | 'unloaded' | 'stopped';

export interface Plugin {
  id?: string;
  path?: string;
  name: string;
  version?: string;
  official?: boolean;
  source?: string;
  status: PluginStatus | string;
  enabled?: boolean;
  manageable?: boolean;
  hot_reload?: boolean;
  config_hot_reload?: boolean;
  description?: string;
  author?: string;
  error?: string;
  /** 配置校验告警：非空表示已存值非法、运行时已回落默认值 */
  config_error?: string | null;
  repo?: string;
  homepage?: string;
  tags?: string[];
  /** 依赖声明（可能带版本约束，如 dashboard>=1.0.0） */
  dependencies?: string[];
  /** 当前未满足的依赖说明（缺失 / 未就绪 / 版本不符） */
  dependency_issues?: string[];
  /** 依赖本插件的其他插件（停用 / 卸载时会联动处理） */
  dependents?: string[];
  /** 因前置插件未满足而自动禁用的原因 */
  disabled_reason?: string | null;
  /** 是否属于依赖自动禁用（区别于用户手动停用） */
  auto_disabled?: boolean;
  /** 命令因重名被自动改名：原 /x -> 实际 /plugin__x（spec(4) R26） */
  command_renames?: PluginCommandRename[];
}

/** 命令重名导致的自动改名（后端 snapshot.command_renames） */
export interface PluginCommandRename {
  requested: string;
  actual: string;
  message: string;
}

/** 插件 ID 冲突的一侧（请求方 / 已存在方） */
export interface PluginConflictSide {
  name?: string;
  version?: string;
  repo?: string;
  branch?: string;
  path?: string;
  official?: boolean;
}

/** 插件安装冲突（spec(4) R27/D24）：两侧来源与版本 + 只能二选一 */
export interface PluginConflict {
  kind?: 'existing_plugin' | 'official' | string;
  requested?: PluginConflictSide;
  existing?: PluginConflictSide;
  message?: string;
  reserved?: boolean;
}

/** 面板 HTTP 扩展 /api/extensions：依赖面板的插件挂在同一端口上的页面 */
export interface ExtensionEntry {
  name?: string;
  prefixes?: string[];
  auth_prefixes?: string[];
  panel?: {
    title?: string;
    path?: string;
    icon?: string;
    description?: string;
  } | null;
}

export interface ProxyInfo {
  mode?: string;
  host?: string;
  port?: number;
  description?: string;
}

export interface PluginListPayload {
  items?: Plugin[];
  console_plugin?: string;
  manage_enabled?: boolean;
  hot_reload?: boolean;
  proxy?: ProxyInfo;
  /** 插件安装器是否可用 */
  installer?: boolean;
}
