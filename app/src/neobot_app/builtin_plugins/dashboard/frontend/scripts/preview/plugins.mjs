import { clone, longUrl } from './scenario.mjs';
import { field, toml, parseDemoToml, describeFields, changes } from './config-schema.mjs';
import { json } from './http.mjs';

export function createPluginPreview(scene) {
  const { empty, canManage, label } = scene;
  let plugins = [
    {
      name: 'speaking_schedule',
      version: '1.0.0',
      official: true,
      status: 'disabled',
      enabled: false,
      manageable: true,
      hot_reload: true,
      config_hot_reload: true,
      description: '虚构的 Bot 发言时段配置，仅保存到演示内存',
    },
    {
      name: 'dashboard',
      version: '1.0.0',
      official: true,
      status: 'loaded',
      enabled: true,
      manageable: false,
      hot_reload: false,
      config_hot_reload: true,
      description: 'NeoBot 网页面板',
      author: '演示开发者',
    },
    {
      name: 'chat',
      version: '1.2.0',
      official: true,
      status: 'loaded',
      enabled: true,
      manageable: true,
      hot_reload: true,
      config_hot_reload: true,
      description: '对话回复与上下文管理',
      author: '演示开发者',
    },
    {
      name: 'memory',
      version: '1.1.0',
      official: true,
      status: 'loaded',
      enabled: true,
      manageable: true,
      hot_reload: true,
      config_hot_reload: true,
      description: '长期记忆、档案与对话总结',
      dependents: ['daily_notes'],
    },
    {
      name: 'daily_notes',
      version: '0.4.2',
      official: false,
      status: 'loaded',
      enabled: true,
      manageable: true,
      hot_reload: true,
      config_hot_reload: false,
      description: '把群聊中的待办与灵感整理为每日笔记',
      repo: 'https://example.invalid/plugins/daily-notes',
      dependencies: ['memory>=1.0.0'],
    },
    {
      name: 'weather',
      version: '0.3.0',
      official: false,
      status: 'disabled',
      enabled: false,
      manageable: true,
      hot_reload: true,
      config_hot_reload: true,
      description: '演示天气查询与城市订阅',
    },
    {
      name: 'starship',
      version: '1.0.0',
      official: true,
      status: 'disabled',
      enabled: false,
      manageable: true,
      hot_reload: true,
      config_hot_reload: true,
      description: 'NeoBot 星舰，默认关闭；开关只改变演示内存与侧栏入口。',
      author: '演示开发者',
    },
    {
      name: 'sample_error',
      version: '0.1.0',
      official: false,
      status: 'error',
      enabled: true,
      manageable: true,
      hot_reload: true,
      config_hot_reload: true,
      description: '用于检查失败状态展示的虚构插件',
      error: '演示：供应商未配置，补全配置后重载插件。',
    },
  ];
  let proxy = { mode: 'system', description: '跟随系统代理（演示，不建立网络连接）' };
  const pluginConfigs = new Map();
  function pluginDoc(name) {
    if (!pluginConfigs.has(name))
      pluginConfigs.set(name, {
        revision: 1,
        config:
          name === 'speaking_schedule'
            ? { timezone: 'Asia/Shanghai', windows: [], overrides: [] }
            : { enabled: true, greeting: '你好，欢迎使用演示面板。', max_items: 20, notify_admin: false },
      });
    const doc = pluginConfigs.get(name);
    return {
      section: name,
      path: `演示数据/plugins/${name}.toml`,
      ...clone(doc),
      source: toml(doc.config),
      form_supported: true,
      source_available: true,
      schema: describeFields(
        name === 'speaking_schedule'
          ? [
              field('timezone', ['timezone'], 'str', '时区', 'Asia/Shanghai'),
              { name: 'windows', path: ['windows'], kind: 'list', type: 'dict', value: [], default: [] },
              { name: 'overrides', path: ['overrides'], kind: 'list', type: 'dict', value: [], default: [] },
            ]
          : [
              field('enabled', ['enabled'], 'bool', '启用功能', true),
              field('greeting', ['greeting'], 'str', '欢迎语', ''),
              field('max_items', ['max_items'], 'int', '最多条目', 20, { min: 1, max: 200 }),
              field('notify_admin', ['notify_admin'], 'bool', '通知管理员', false),
            ],
        doc.config,
      ),
    };
  }

  return {
    get items() {
      return plugins;
    },
    handle({ path, method, body, res }) {
      if (path === '/api/extensions') {
        if (method !== 'GET') return json(res, { error: '演示扩展列表仅接受 GET' }, 405);
        const starship = plugins.find((item) => item.name === 'starship');
        return json(res, {
          items:
            !empty() && starship?.enabled && starship.status === 'loaded'
              ? [
                  {
                    name: 'starship',
                    prefixes: ['/api/preview/starship/'],
                    auth_prefixes: ['/api/preview/starship/'],
                    panel: {
                      title: 'NeoBot 星舰',
                      path: '/api/preview/starship/',
                      icon: 'game',
                      description: '仅用于验证开关与侧栏入口的虚构演示',
                    },
                  },
                ]
              : [],
        });
      }
      if (path === '/api/preview/starship/') {
        const starship = plugins.find((item) => item.name === 'starship');
        if (method !== 'GET') return json(res, { error: '演示扩展页面仅接受 GET' }, 405);
        if (empty() || !starship?.enabled || starship.status !== 'loaded')
          return json(res, { error: '星舰演示未启用' }, 404);
        res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
        return res.end(
          '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>星舰演示</title><body style="margin:0;background:#f7f8fa;color:#292d34;font:16px/1.8 system-ui"><main style="max-width:640px;margin:12vh auto;padding:32px"><h1>NeoBot 星舰</h1><p>星舰演示已启用。此页面只用于检查扩展开关与入口，不加载游戏资源，不连接真实服务。</p><a href="/#/system" style="color:#bd4e2d">返回系统状态</a></main></body></html>',
        );
      }
      if (path === '/api/plugins')
        return json(res, {
          items: empty()
            ? []
            : plugins.map((item) => ({
                ...item,
                id: item.name,
                source: item.official ? 'official' : 'third_party',
                description: label(item.description),
                repo: scene.name === 'long' && !item.official ? longUrl : item.repo,
              })),
          console_plugin: 'dashboard',
          manage_enabled: canManage(),
          hot_reload: true,
          installer: true,
          proxy,
        });
      if (path === '/api/plugins/proxy') {
        proxy = { ...body };
        return json(res, { proxy, message: '演示代理设置已保存；不会建立连接' });
      }
      if (path === '/api/plugins/check-updates')
        return json(res, { ok: true, message: '已模拟检查：插件均为演示版本，无需更新' });
      if (path === '/api/plugins/probe')
        return json(res, { conflict: false, official: false, message: '演示安装路径可用' });
      if (path === '/api/plugins/install') {
        if (!body.dry_run)
          plugins.push({
            name: 'installed_demo',
            version: '1.0.0',
            status: 'loaded',
            enabled: true,
            manageable: true,
            official: false,
            hot_reload: true,
            description: '刚安装的虚构插件',
          });
        return json(res, {
          ok: true,
          dry_run: !!body.dry_run,
          message: body.dry_run ? '演示探测通过，未访问仓库' : '演示插件已加入内存列表',
          version: '1.0.0',
        });
      }
      const pluginMatch = /^\/api\/plugins\/([^/]+)\/(config|toggle|reload|update|uninstall)$/.exec(path);
      if (pluginMatch) {
        const name = decodeURIComponent(pluginMatch[1]);
        const action = pluginMatch[2];
        const item = plugins.find((entry) => entry.name === name);
        if (action === 'config') {
          if (method === 'GET') return json(res, pluginDoc(name));
          const doc = pluginDoc(name);
          if (body.revision !== doc.revision) return json(res, { error: '演示插件配置版本已变化' }, 409);
          pluginConfigs.set(name, {
            revision: doc.revision + 1,
            config: body.mode === 'toml' ? parseDemoToml(body.source) : clone(body.config || {}),
          });
          return json(res, { ...pluginDoc(name), message: '插件配置已保存到演示内存', changes });
        }
        if (!item) return json(res, { error: '演示插件不存在' }, 404);
        if (action === 'toggle') {
          if (!body || typeof body !== 'object' || Array.isArray(body))
            return json(res, { ok: false, error: '演示开关参数必须为对象' }, 400);
          for (const key of ['enabled', 'expected_enabled'])
            if (Object.hasOwn(body, key) && typeof body[key] !== 'boolean')
              return json(res, { ok: false, error: `${key} 必须是布尔值` }, 400);
          const current = !!item.enabled;
          if (Object.hasOwn(body, 'expected_enabled') && body.expected_enabled !== current)
            return json(
              res,
              { ok: false, error: '插件启停状态已被其他操作修改，请刷新后重试', name, enabled: current },
              409,
            );
          item.enabled = body.enabled ?? !current;
          item.status = item.enabled ? 'loaded' : 'disabled';
          return json(res, {
            ok: true,
            name,
            state: item.enabled ? 'running' : 'unloaded',
            message: `演示插件已${item.enabled ? '启用' : '停用'}`,
          });
        }
        if (action === 'uninstall') plugins = plugins.filter((entry) => entry.name !== name);
        if (action === 'reload') {
          item.status = 'loaded';
          item.error = undefined;
        }
        return json(res, { ok: true, message: '演示插件操作已完成' });
      }
    },
  };
}
