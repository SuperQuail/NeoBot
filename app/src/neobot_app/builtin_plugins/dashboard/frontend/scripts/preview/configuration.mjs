import { randomBytes } from 'node:crypto';
import { clone, longText, longUrl, created } from './scenario.mjs';
import {
  group,
  configSchema,
  modelEntrySchema,
  toml,
  parseDemoToml,
  describeFields,
  foldDemoModelParams,
  reasoningEffortLabel,
  changes,
} from './config-schema.mjs';
import { json } from './http.mjs';

export function createConfigurationPreview(scene) {
  const { empty, label } = scene;
  let configRevision = randomBytes(16).toString('hex');
  let envRevision = randomBytes(16).toString('hex');
  let config = {
    bot: {
      account: '1000000001',
      nick_name: '演示小乔',
      alias_name: ['小乔', 'Neo'],
      bot_data: '你是一位友善的虚构群聊助手，回复简洁自然。',
    },
    chat: {
      admin_accounts: ['1000000002'],
      group_chat_chance: 0.3,
      enable_private_chat: true,
      max_history_messages: 40,
    },
    adapter: { host: '127.0.0.1', port: 9980, access_token: 'preview-onebot-token' },
    agent: { enabled: true, max_iterations: 8, memory: { enabled: true, max_total_chars: 5000 } },
    logging: { level: 'INFO', keep_days: 14 },
  };
  function configDoc() {
    const view = clone(config);
    if (scene.name === 'long' && view.models?.registry?.length) {
      while (view.models.registry.length < 8) {
        const index = view.models.registry.length;
        view.models.registry.push({
          ...clone(view.models.registry[index % 3]),
          model_ref: `long_context_${index + 1}`,
          display_name: `长名称模型 ${index + 1} · ${longText.slice(0, 96)}`,
        });
      }
    }
    const schema = [
      ...configSchema,
      group('models', '模型注册表与生成参数', [
        {
          name: 'registry',
          path: ['models', 'registry'],
          kind: 'model_list',
          description: '每个模型独立配置供应商、基础参数与可选参数。所有内容均为虚构演示。',
          item_fields: modelEntrySchema,
          hot_reload: true,
        },
      ]),
    ];
    return {
      section: 'root',
      path: '演示数据/config.toml',
      revision: configRevision,
      form_supported: true,
      source_available: true,
      source: toml(view),
      config: view,
      schema: describeFields(schema, view),
    };
  }
  let env = [
    {
      key: 'DeepSeek_APIKey',
      description: '演示供应商密钥，只显示设置状态',
      sensitive: true,
      has_value: true,
      builtin: true,
      in_file: true,
    },
    {
      key: 'DeepSeek_URL',
      description: '供应商 API 地址',
      value: 'https://api.example.invalid/v1',
      sensitive: false,
      has_value: true,
      builtin: true,
      in_file: true,
    },
    {
      key: 'DEMO_SEARCH_KEY',
      description: '搜索服务密钥',
      sensitive: true,
      has_value: false,
      builtin: false,
      in_file: true,
    },
  ];
  let platforms = [{ name: 'DeepSeek', url: 'https://api.example.invalid/v1', has_key: true, builtin: true }];
  const envDoc = () => ({
    revision: envRevision,
    path: '演示数据/.env',
    items: clone(env).map((item) => ({
      ...item,
      value: item.sensitive
        ? undefined
        : scene.name === 'long' && item.key.endsWith('_URL')
          ? longUrl
          : item.value,
    })),
    platforms: clone(platforms),
  });
  let library = [
    {
      model_ref: 'main_chat',
      display_name: '日常对话',
      provider: 'DeepSeek',
      model_name: 'demo-chat',
      model_type: 'chat',
      reasoning_effort: 'high',
      settings: { temperature: 0.7, max_tokens: 4096, enabled_params: ['top_p'], top_p: 0.9, extra_body: {} },
    },
    {
      model_ref: 'deep_reason',
      display_name: '复杂问题推理',
      provider: '演示云',
      model_name: 'demo-reasoner',
      model_type: 'chat',
      reasoning_effort: 'claude:max',
      settings: {
        temperature: 0.3,
        max_tokens: 8192,
        enabled_params: ['top_p'],
        top_p: 0.95,
        extra_body: { demo_mode: true },
      },
      billing_script: 'demo_pricing',
    },
    {
      model_ref: 'vision',
      display_name: '看图识别',
      provider: '演示云',
      model_name: 'demo-vision',
      model_type: 'vision',
      settings: { temperature: 0.4, max_tokens: 2048, enabled_params: [], extra_body: {} },
    },
  ];
  config.models = { registry: clone(library) };
  let assignments = {
    roles: { chat: 'main_chat', agent: 'deep_reason', vision: 'vision', memory: 'main_chat' },
    creator_image_models: [],
  };
  const rolesMeta = [
    ['chat', '主对话'],
    ['agent', 'Agent 推理'],
    ['vision', '图像理解'],
    ['memory', '记忆总结'],
  ].map(([role, text]) => ({
    role,
    label: text,
    required: role === 'chat',
    model_type: role === 'vision' ? 'vision' : 'chat',
    model_type_label: role === 'vision' ? '视觉' : '对话',
  }));
  function modelDoc() {
    return {
      revision: configRevision,
      library: empty()
        ? []
        : library.map((entry) => ({
            ...entry,
            display_name: label(entry.display_name),
            entry: clone(entry),
            reasoning_effort_label: reasoningEffortLabel(entry.reasoning_effort),
            api_key_configured: true,
            url_configured: true,
            registered: true,
            assigned: Object.values(assignments.roles).includes(entry.model_ref),
            type_label: entry.model_type === 'vision' ? '视觉' : '对话',
          })),
      assignments: clone(assignments),
      roles_meta: rolesMeta,
      roles: rolesMeta.map((meta) => ({
        ...meta,
        model_ref: assignments.roles[meta.role],
        status: 'ready',
        registered: true,
      })),
      entry_schema: clone(modelEntrySchema),
      provider_options: platforms.map((item) => item.name),
      providers: platforms.map((item) => item.name),
      model_name_options: ['demo-chat', 'demo-reasoner', 'demo-vision'],
      model_type_labels: { chat: '对话', vision: '视觉', image: '生图', tts: '语音' },
      role_model_types: { chat: 'chat', agent: 'chat', vision: 'vision', memory: 'chat' },
      platforms: clone(platforms),
    };
  }
  const billing = {
    available: true,
    enabled: true,
    timeout_ms: 100,
    reload_on_change: true,
    record_detail: true,
    directory: '演示数据/billing',
    scripts: ['demo_pricing'],
    templates: ['basic'],
    policies: {
      demo_pricing: {
        name: 'demo_pricing',
        ok: true,
        elapsed_ms: 0.2,
        eval_count: 128,
        fallback_count: 0,
        loaded_at: created,
      },
    },
    bindings: [
      {
        model_key: 'deep_reason',
        billing_script: 'demo_pricing',
        available: true,
        source: 'script:demo_pricing',
        last_eval_ms: 0.2,
        eval_count: 128,
      },
    ],
    errors: {},
  };

  return {
    get config() {
      return config;
    },
    handle({ path, method, body, res }) {
      if (path === '/api/config') {
        if (method === 'GET') return json(res, configDoc());
        if (body.revision !== configRevision)
          return json(res, { error: '配置已被其他演示会话修改，请重新读取' }, 409);
        config = foldDemoModelParams(
          body.mode === 'toml' ? parseDemoToml(body.source) : clone(body.config || config),
        );
        configRevision = randomBytes(16).toString('hex');
        return json(res, { ...configDoc(), message: '已保存到演示内存', applied: !!body.reload, changes });
      }
      if (path === '/api/config/validate') {
        if (body.mode === 'toml') parseDemoToml(body.source);
        return json(res, { errors: [], message: '演示基础校验通过' });
      }
      if (path === '/api/config/reload')
        return json(res, { message: '演示运行时配置已重载', applied: true, changes });
      if (path === '/api/config/env') {
        if (method === 'GET') return json(res, envDoc());
        if (body.revision !== envRevision) return json(res, { error: '环境变量已变化，请重新读取' }, 409);
        env = env.filter((item) => !(body.deletes || []).includes(item.key));
        for (const [key, value] of Object.entries(body.updates || {})) {
          let item = env.find((entry) => entry.key === key);
          if (!item) {
            item = { key, in_file: true, sensitive: /key|token|secret|password/i.test(key) };
            env.push(item);
          }
          if (value)
            Object.assign(item, { has_value: true, value: item.sensitive ? undefined : String(value) });
        }
        envRevision = randomBytes(16).toString('hex');
        return json(res, {
          ...envDoc(),
          applied: !!body.reload,
          needs_restart: false,
          message: '已保存到演示内存',
        });
      }
      if (path === '/api/config/env/platform') {
        const name = String(body.name || '演示供应商');
        platforms.push({
          name,
          url: body.url || 'https://example.invalid/v1',
          has_key: !!body.api_key,
          builtin: false,
        });
        env.push(
          { key: name + '_APIKey', sensitive: true, has_value: !!body.api_key, in_file: true },
          { key: name + '_URL', sensitive: false, value: body.url, in_file: true },
        );
        envRevision = randomBytes(16).toString('hex');
        return json(res, { ...envDoc(), message: '演示供应商已添加' });
      }
      if (path === '/api/config/models') return json(res, modelDoc());
      if (path === '/api/config/models/library') {
        if (body.action === 'delete') library = library.filter((item) => item.model_ref !== body.model_ref);
        else {
          const entry = clone(body.entry || {});
          entry.model_ref ||= 'preview_model_' + (library.length + 1);
          const index = library.findIndex((item) => item.model_ref === entry.model_ref);
          if (index < 0) library.push(entry);
          else library[index] = entry;
        }
        configRevision = randomBytes(16).toString('hex');
        return json(res, {
          ...modelDoc(),
          models: modelDoc(),
          saved_model_ref: body.entry?.model_ref,
          message: '模型已保存到演示内存',
          needs_restart_parts: [],
          changes,
        });
      }
      if (path === '/api/config/models/assignments') {
        const draft = body.assignments || {};
        assignments = {
          roles: Object.fromEntries(Object.entries(draft).filter(([key]) => key !== 'creator_image_models')),
          creator_image_models: draft.creator_image_models || [],
        };
        configRevision = randomBytes(16).toString('hex');
        return json(res, { ...modelDoc(), models: modelDoc(), message: '演示模型分配已保存' });
      }
      if (path === '/api/config/models/test')
        return json(res, {
          ok: true,
          reachable: true,
          authorized: true,
          model_found: true,
          provider: body.provider || 'DeepSeek',
          model_name: body.model_name || 'demo-chat',
          latency_ms: 128,
          status: 200,
          detail: '仅模拟成功，不访问供应商',
          message: '演示连通性测试通过',
        });
      if (path === '/api/config/models/provider-models')
        return json(res, {
          ok: true,
          provider: body.provider,
          models: ['demo-chat', 'demo-reasoner', 'demo-vision'],
          message: '返回演示模型目录，未访问外部服务',
        });
      if (path === '/api/config/billing' || path === '/api/config/billing/reload')
        return json(res, { ...billing, reloaded: method === 'GET' ? [] : ['demo_pricing'] });
      if (path === '/api/config/billing/preview')
        return json(res, {
          ok: true,
          cost_cny: 0.026,
          builtin_cost_cny: 0.03,
          source: 'script:demo_pricing',
          components: { input: 0.02, output: 0.006 },
          note: '虚构试算，不执行脚本',
          elapsed_ms: 0.2,
        });
      if (path === '/api/deploy/status')
        return json(res, {
          revision: configRevision,
          env_revision: envRevision,
          ready: true,
          values: {
            bot_account: config.bot.account,
            bot_nick_name: config.bot.nick_name,
            alias_name: config.bot.alias_name,
            bot_data: config.bot.bot_data,
            admin_accounts: config.chat.admin_accounts,
            group_chat_chance: config.chat.group_chat_chance,
          },
          defaults: { bot_account: '请填写 QQ', bot_nick_name: 'NeoBot', bot_data: '请填写人设' },
          steps: [
            ['bot_identity', '机器人身份', true],
            ['persona', '机器人设定', true],
            ['platform_key', '模型供应商', true],
            ['admin', '超级管理员', false],
            ['onebot', 'OneBot 连接', true],
          ].map(([key, text, required]) => ({
            key,
            label: text,
            required,
            done: true,
            hint: '演示配置已完成',
          })),
          onebot: {
            host: '127.0.0.1',
            port: 9980,
            token: 'preview-onebot-token',
            token_enabled: true,
            url_local: 'ws://127.0.0.1:9980/onebot',
            url_lan: 'ws://192.0.2.10:9980/onebot',
            path_hint: '/onebot',
            warning: '以上地址为虚构连接信息，不会建立连接。',
          },
        });
      if (path === '/api/deploy/onebot-token')
        return json(res, {
          token: 'preview-onebot-token',
          applied: true,
          message: '演示 token 已生成，仅保存在内存',
        });
    },
  };
}
