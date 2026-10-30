// 配置 schema、文档、变更结果、环境变量与快捷部署。

/** 快捷部署 /api/deploy/status */
export interface DeployStep {
  key?: string;
  label?: string;
  /** 必填项才参与「可以工作了」的判定；选填项配不配都不拦 */
  required?: boolean;
  done?: boolean;
  hint?: string;
  action?: string;
}

/** OneBot 反向 WS 的生效监听信息（NapCat 侧要填的就是地址与 token） */
export interface OneBotConnection {
  host?: string;
  port?: number;
  token?: string;
  token_enabled?: boolean;
  bind_all?: boolean;
  /** 同机连接用（NapCat 与 NeoBot 同机） */
  url_local?: string;
  /** 局域网连接用（NapCat 在另一台机器） */
  url_lan?: string;
  /** 路径由框架侧自己配，服务端不限制 */
  path_hint?: string;
  /** 未配 token 却对外监听时的安全告警 */
  warning?: string | null;
  from_config?: boolean;
  /** 预留：装了 NapCat Desktop 后可自动创建连接（当前 available=false + 原因） */
  auto_connect?: { available?: boolean; reason?: string };
}

export interface DeployStatus {
  steps?: DeployStep[];
  onebot?: OneBotConnection;
  values?: {
    bot_account?: string;
    bot_nick_name?: string;
    bot_data?: string;
    alias_name?: string[];
    admin_accounts?: string[];
    group_chat_chance?: number;
  };
  /** 出厂默认值：account / 昵称 / 人设仍是出厂占位时，向导据此判「未配置」 */
  defaults?: { bot_account?: string; bot_nick_name?: string; bot_data?: string };
  revision?: string;
  env_revision?: string;
  ready?: boolean;
}

/** schema 字段描述（由后端 config_manager.describe_dataclass 生成） */
export type FieldKind = 'scalar' | 'group' | 'list' | 'dict' | 'model_list' | 'model_params' | 'json';

export interface FieldDescriptor {
  name: string;
  /** 开发者声明的显示名称；缺省时使用存储字段名。 */
  label?: string;
  path: Array<string | number>;
  kind: FieldKind;
  /** 读取时的当前值（后端快照，编辑草稿以 values 为准） */
  value?: unknown;
  type?: string;
  default?: unknown;
  description?: string;
  options?: string[];
  option_values?: Record<string, string | number | boolean | null>;
  options_strict?: boolean;
  /** strict 下拉的中文选项名（值 → 文案）；缺省时直接显示原始值 */
  option_labels?: Record<string, string>;
  /** strict 下拉的选项分组；未列入任何分组的值（如「不设置」）排在分组之前 */
  option_groups?: Array<{ label: string; options: string[] }>;
  readonly?: boolean;
  multi?: boolean;
  min?: number;
  max?: number;
  hot_reload?: boolean;
  partial_hot_reload?: boolean;
  restart_reason?: string;
  /** 后端标记为不在表单里展示 */
  hidden?: boolean;
  fields?: FieldDescriptor[];
  items?: Array<{ index: number; fields: FieldDescriptor[] }>;
  item_fields?: FieldDescriptor[];
  [key: string]: unknown;
}

/** 保存/重载后返回的「已生效 / 需重启」明细 */
export interface ConfigChangeItem {
  path: string;
  reason?: string;
  before?: unknown;
  after?: unknown;
}

export interface ConfigChanges {
  hot_reload?: ConfigChangeItem[];
  needs_restart?: ConfigChangeItem[];
  hot_reload_count?: number;
  needs_restart_count?: number;
  [key: string]: unknown;
}

/** 配置文档（本体 config.toml / 插件配置共用） */
export interface ConfigDocument {
  section?: string;
  path?: string;
  /** 配置文件内容摘要；文件尚未创建时为空串，保存时不作数值转换。 */
  revision?: string;
  form_supported?: boolean;
  source_available?: boolean;
  source_disabled_reason?: string;
  source?: string;
  config?: Record<string, unknown>;
  schema?: FieldDescriptor[];
  message?: string;
  applied?: boolean;
  /** 校验失败时后端返回的字段级错误 */
  errors?: Array<{ path?: string; message?: string }>;
  /** 重载后返回的生效明细 */
  changes?: ConfigChanges;
  [key: string]: unknown;
}

/** 环境变量 /api/config/env */
export interface EnvItem {
  key: string;
  description?: string;
  value?: string;
  has_value?: boolean;
  builtin?: boolean;
  required?: boolean;
  removed?: boolean;
  /** 是否实际写入文件；内置占位项不提供删除入口。 */
  in_file?: boolean;
  /** 密钥类变量：只写不读 */
  sensitive?: boolean;
  [key: string]: unknown;
}

export interface EnvPayload {
  items?: EnvItem[];
  path?: string;
  platforms?: Array<{
    name?: string;
    url?: string;
    has_key?: boolean;
    builtin?: boolean;
    [k: string]: unknown;
  }>;
  revision?: string;
  message?: string;
  /** 保存并重载的结果：仍有部分模块需重启进程才生效（启动期读取环境变量的那些，如 TTS / 生图） */
  needs_restart?: boolean;
  /** 重载是否成功 */
  applied?: boolean;
  [key: string]: unknown;
}
