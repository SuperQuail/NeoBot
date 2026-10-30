/** 插件页面桥接协议；页面仅能调用当前插件声明的动作。 */
export interface PluginViewContext {
  pluginId: string;
  viewId: string;
  mode: 'live' | 'demo';
  permissions: Array<'read' | 'operate' | 'manage'>;
  available: boolean;
  suspended: boolean;
  theme: Record<string, string>;
  reducedMotion: boolean;
  language: string;
  /** 设置区随内容伸缩；思索舞台保持独立滚动。SDK 自动上报尺寸。 */
  layout?: 'inline' | 'stage';
  colorScheme?: string;
}

export interface PluginGuideStep {
  target: string;
  text: string;
  chapter?: string;
  example?: Record<string, unknown>;
  command?: { text: string; context: string; reply?: string };
  /** 完整配置表单的有限演示阶段；不会保存真实配置。 */
  form?: 'start' | 'edit' | 'validate' | 'save' | 'saved';
  mode: 'live' | 'demo';
}

export interface PluginNotice {
  title: string;
  message?: string;
  tone?: 'ok' | 'warn' | 'err' | 'info';
}

/** 配置与自动表单共用同一文档，敏感字段由宿主接口按原规则屏蔽。 */
export interface PluginConfigSnapshot {
  config: Record<string, unknown>;
  /** 配置文件内容摘要；尚未创建的文件使用空串，保存时原样传回。 */
  revision: string;
  form_supported?: boolean;
  schema?: Array<Record<string, unknown>>;
  message?: string;
  applied?: boolean;
  changes?: Record<string, unknown>;
}

export interface PluginBridgeError extends Error {
  code: string;
  status?: number;
  fields?: Array<{ path?: string; message?: string }>;
}

export interface NeoBotPluginClient {
  ready(): Promise<PluginViewContext>;
  /** 返回业务结果本身；失败时抛出附带 code 的 Error。演示只返回声明的样例。 */
  action<Result = unknown>(id: string, values?: unknown): Promise<Result>;
  getConfig(): Promise<PluginConfigSnapshot>;
  /** 使用读取时的版本保存；409 以 config_conflict 错误返回，作者应保留当前草稿。 */
  saveConfig(values: Record<string, unknown>, revision: string): Promise<PluginConfigSnapshot>;
  notify(notice: PluginNotice): Promise<null>;
  navigate(target: string): Promise<null>;
  registerAnchor(id: string, element: HTMLElement): () => void;
  onContext(listener: (context: PluginViewContext) => void): () => void;
  onGuideStep(listener: (step: PluginGuideStep) => void): () => void;
  /** 页面关闭时自动清理；作者也可在自己的卸载生命周期中调用。 */
  dispose(): void;
}

declare global {
  interface Window {
    NeoBotPlugin: NeoBotPluginClient;
  }
}
