// SDK 声明式功能、资源与教程；页面不推断权限或执行插件脚本。
export type PluginPermission = 'read' | 'operate' | 'manage';

export type JsonSchema =
  | boolean
  | {
      type?: string | string[];
      title?: string;
      description?: string;
      default?: unknown;
      enum?: unknown[];
      properties?: Record<string, JsonSchema>;
      required?: string[];
      items?: JsonSchema | JsonSchema[];
      minimum?: number;
      maximum?: number;
      $ref?: string;
      $defs?: Record<string, JsonSchema>;
      [key: string]: unknown;
    };

export interface PluginAction {
  id: string;
  title: string;
  description?: string;
  permission: PluginPermission;
  input_schema: JsonSchema | null;
  output_schema: JsonSchema | null;
}

export interface PluginResource {
  id: string;
  title: string;
  list_action: string;
  columns: Array<{ key: string; title: string }>;
  create_action?: string | null;
  delete_action?: string | null;
}

export interface PluginGuide {
  id: string;
  title: string;
  steps: PluginGuideStep[];
  completion_action?: string | null;
  demo?: PluginGuideDemo;
}

export interface PluginGuideStep {
  target: string;
  text: string;
  chapter?: string;
  example?: Record<string, unknown>;
  command?: { text: string; context: string; reply?: string };
  /** 每步 example 是独立合成配置快照；保存阶段仅演示，不调用真实接口。 */
  form?: 'start' | 'edit' | 'validate' | 'save' | 'saved';
}

export interface PluginGuideDemo {
  actions?: Record<string, unknown>;
  config?: Record<string, unknown>;
}

export interface PluginView {
  id: string;
  title: string;
  entry: string;
  anchors: string[];
  url?: string;
}

export interface PluginSurfaceContract {
  schema_version: 1;
  plugin: { name: string; version?: string; description?: string };
  config: JsonSchema | null;
  actions: PluginAction[];
  resources: PluginResource[];
  guides: PluginGuide[];
  views?: PluginView[];
}

export interface PluginSurfacePayload {
  ok?: boolean;
  contract: PluginSurfaceContract | null;
  available: boolean;
  state: string;
  permissions: PluginPermission[];
  source: 'runtime' | 'package' | 'none';
}

export interface PluginActionPayload {
  ok: boolean;
  result?: unknown;
  error?: string;
  code?: string;
  fields?: Array<{ path: Array<string | number>; type: string }>;
}
