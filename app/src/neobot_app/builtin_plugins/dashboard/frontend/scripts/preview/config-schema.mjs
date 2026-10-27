import { clone } from './scenario.mjs';

export const field = (name, path, type, description, defaultValue, extra = {}) => ({
  name,
  path,
  kind: 'scalar',
  type,
  description,
  default: defaultValue,
  hot_reload: true,
  ...extra,
});
export const group = (name, description, fields) => ({
  name,
  path: [name],
  kind: 'group',
  description,
  fields,
});
export const configSchema = [
  group('bot', '机器人身份与人设', [
    field('account', ['bot', 'account'], 'str', '机器人 QQ 号', ''),
    field('nick_name', ['bot', 'nick_name'], 'str', '机器人昵称', 'NeoBot'),
    {
      name: 'alias_name',
      path: ['bot', 'alias_name'],
      kind: 'list',
      type: 'str',
      description: '别名',
      default: [],
      hot_reload: true,
    },
    field('bot_data', ['bot', 'bot_data'], 'str', '人设说明', '', { multiline: true }),
  ]),
  group('chat', '聊天与回复策略', [
    {
      name: 'admin_accounts',
      path: ['chat', 'admin_accounts'],
      kind: 'list',
      type: 'str',
      description: '超级管理员 QQ',
      default: [],
      hot_reload: true,
    },
    field('group_chat_chance', ['chat', 'group_chat_chance'], 'float', '群聊回复意愿', 0.3, {
      min: 0,
      max: 1,
    }),
    field('enable_private_chat', ['chat', 'enable_private_chat'], 'bool', '启用私聊回复', true),
    field('max_history_messages', ['chat', 'max_history_messages'], 'int', '上下文消息上限', 40, {
      min: 1,
      max: 200,
    }),
  ]),
  group('adapter', 'OneBot 反向 WebSocket 连接', [
    field('host', ['adapter', 'host'], 'str', '监听地址', '127.0.0.1', {
      hot_reload: false,
      restart_reason: '监听地址在进程启动时绑定',
    }),
    field('port', ['adapter', 'port'], 'int', '监听端口', 9980, { min: 1, max: 65535, hot_reload: false }),
    field('access_token', ['adapter', 'access_token'], 'str', '连接令牌（仅演示值）', '', {
      sensitive: true,
    }),
  ]),
  group('agent', 'Agent 运行与记忆', [
    field('enabled', ['agent', 'enabled'], 'bool', '启用 Agent', true),
    field('max_iterations', ['agent', 'max_iterations'], 'int', '最大迭代次数', 8, { min: 1, max: 30 }),
    {
      name: 'memory',
      path: ['agent', 'memory'],
      kind: 'group',
      description: '长期记忆',
      fields: [
        field('enabled', ['agent', 'memory', 'enabled'], 'bool', '启用长期记忆', true),
        field('max_total_chars', ['agent', 'memory', 'max_total_chars'], 'int', '单条档案字符上限', 5000),
      ],
    },
  ]),
  group('logging', '日志输出', [
    field('level', ['logging', 'level'], 'str', '日志级别', 'INFO', {
      options: ['DEBUG', 'INFO', 'WARNING', 'ERROR'],
      options_strict: true,
    }),
    field('keep_days', ['logging', 'keep_days'], 'int', '保留天数', 14, { min: 1, max: 90 }),
  ]),
];
export function toml(data, prefix = '') {
  const lines = [];
  for (const [key, value] of Object.entries(data)) {
    if (value && typeof value === 'object' && !Array.isArray(value)) continue;
    if (Array.isArray(value) && value.some((item) => item && typeof item === 'object')) continue;
    lines.push(`${key} = ${JSON.stringify(value)}`);
  }
  for (const [key, value] of Object.entries(data)) {
    const path = prefix ? prefix + '.' + key : key;
    if (Array.isArray(value)) {
      if (value.some((item) => item && typeof item === 'object'))
        for (const item of value) lines.push('', `[[${path}]]`, toml(item, path));
      continue;
    }
    if (!value || typeof value !== 'object') continue;
    lines.push('', `[${path}]`, toml(value, path));
  }
  const source = lines.join('\n');
  return prefix ? source : source.replace(/^\n+/, '');
}
export function parseDemoToml(source) {
  const result = {};
  let target = result;
  for (const raw of String(source).split('\n')) {
    const line = raw.trim();
    if (!line || line.startsWith('#')) continue;
    const table = /^(\[\[?)([\w.]+)(\]\]?)$/.exec(line);
    if (table && table[1].length === table[3].length) {
      target = result;
      const keys = table[2].split('.');
      for (const [index, key] of keys.entries()) {
        if (table[1] === '[[' && index === keys.length - 1) {
          const list = (target[key] ||= []);
          if (!Array.isArray(list)) throw new Error('演示数组表与已有值冲突');
          const item = {};
          list.push(item);
          target = item;
        } else {
          const value = (target[key] ||= {});
          target = Array.isArray(value) ? value.at(-1) : value;
          if (!target || typeof target !== 'object') throw new Error('演示表路径与已有值冲突');
        }
      }
      continue;
    }
    const match = /^([\w-]+)\s*=\s*(.+)$/.exec(line);
    if (!match) throw new Error('演示夹具仅支持本页生成的基础 TOML 语法');
    try {
      target[match[1]] = JSON.parse(match[2]);
    } catch {
      throw new Error('演示夹具仅支持字符串、数字、布尔与基础数组');
    }
  }
  return result;
}
export function describeFields(fields, values = {}, prefix = []) {
  return fields.map((descriptor) => {
    const path = [...prefix, descriptor.name];
    const value = values?.[descriptor.name] ?? descriptor.default;
    if (descriptor.kind === 'group')
      return {
        ...clone(descriptor),
        path,
        value: value || {},
        fields: describeFields(descriptor.fields || [], value || {}, path),
      };
    if (descriptor.kind === 'model_list') {
      const entries = Array.isArray(value) ? value : [];
      return {
        ...clone(descriptor),
        path,
        value: entries,
        item_fields: describeFields(descriptor.item_fields || [], {}, [...path, '0']),
        items: entries.map((item, index) => ({
          index,
          fields: describeFields(descriptor.item_fields || [], item, [...path, String(index)]),
        })),
      };
    }
    if (descriptor.kind === 'model_params')
      return {
        ...clone(descriptor),
        path,
        value: {
          enabled_params: values.enabled_params || [],
          extra_body: values.extra_body || {},
          values: Object.fromEntries(
            (descriptor.catalog || [])
              .filter((entry) => values[entry.name] !== undefined)
              .map((entry) => [entry.name, values[entry.name]]),
          ),
        },
      };
    return { ...clone(descriptor), path, value };
  });
}
export function foldDemoModelParams(data) {
  for (const entry of data.models?.registry || []) {
    const params = entry.settings?.params;
    if (!params || typeof params !== 'object') continue;
    Object.assign(entry.settings, params.values || {}, {
      enabled_params: params.enabled_params || [],
      extra_body: params.extra_body || {},
    });
    delete entry.settings.params;
  }
  return data;
}
export const changes = {
  hot_reload: [{ path: 'bot.nick_name', reason: '演示：运行时配置已重载' }],
  hot_reload_count: 1,
  needs_restart: [],
  needs_restart_count: 0,
};
export const modelEntrySchema = [
  field('model_ref', ['model_ref'], 'str', '本机引用名', ''),
  field('display_name', ['display_name'], 'str', '显示名称', ''),
  field('provider', ['provider'], 'str', '供应商', 'DeepSeek', {
    options: ['DeepSeek', '演示云'],
    options_strict: false,
  }),
  field('model_name', ['model_name'], 'str', '供应商模型名', 'demo-chat'),
  field('model_type', ['model_type'], 'str', '模型类型', 'chat', {
    options: ['chat', 'vision', 'image', 'tts'],
    options_strict: true,
  }),
  field('use_system_proxy', ['use_system_proxy'], 'bool', '使用系统代理', false),
  {
    name: 'settings',
    path: ['settings'],
    kind: 'group',
    description: '生成参数',
    fields: [
      field('temperature', ['settings', 'temperature'], 'float', '温度', 0.7, { min: 0, max: 2 }),
      field('max_tokens', ['settings', 'max_tokens'], 'int', '最大输出 Token', 4096),
      {
        name: 'params',
        path: ['settings', 'params'],
        kind: 'model_params',
        label: '模型参数',
        description: '选择需要发送给模型的可选参数；未添加的参数保留数值但不下发。',
        base_param_names: ['temperature', 'max_tokens'],
        catalog: [
          { name: 'top_p', group: 'sampling', label: '采样范围', type: 'float', default: 1 },
          { name: 'frequency_penalty', group: 'sampling', label: '重复惩罚', type: 'float', default: 0 },
          { name: 'presence_penalty', group: 'sampling', label: '话题重复惩罚', type: 'float', default: 0 },
          { name: 'seed', group: 'sampling', label: '随机种子', type: 'int', default: 42 },
          {
            name: 'reasoning_effort',
            group: 'reasoning',
            label: '推理强度',
            type: 'str',
            default: 'medium',
            options: ['low', 'medium', 'high'],
          },
        ],
        hot_reload: true,
      },
    ],
  },
  field('billing_script', ['billing_script'], 'str', '计费脚本', ''),
];
