import http from 'node:http';
import { URL } from 'node:url';
import { createScenario, SCENARIOS } from './scenario.mjs';
import { bodyOf, json, PREVIEW_HOST, requiresPost } from './http.mjs';
import { createAuthPreview } from './auth.mjs';
import { createAssetPreview } from './assets.mjs';
import { createConfigurationPreview } from './configuration.mjs';
import { createPluginPreview } from './plugins.mjs';
import { createConversationPreview } from './conversations.mjs';
import { createArchivePreview } from './archives.mjs';
import { createRuntimePreview } from './runtime.mjs';

/** Each server owns an isolated memory world; the CLI decides where to listen. */
export function createPreviewServer({ scenario = 'default' } = {}) {
  const scene = createScenario(scenario);
  const auth = createAuthPreview(scene);
  const assets = createAssetPreview();
  const configuration = createConfigurationPreview(scene);
  const plugins = createPluginPreview(scene);
  const routes = [
    assets,
    createRuntimePreview(scene, configuration, plugins),
    configuration,
    plugins,
    createConversationPreview(scene, configuration),
    createArchivePreview(scene),
  ];
  return http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url, 'http://' + PREVIEW_HOST);
      const path = url.pathname;
      const method = req.method || 'GET';
      const context = { path, method, q: url.searchParams, req, res };
      await assets.loginPage(context);
      if (res.writableEnded) return;
      if (requiresPost(path) && method !== 'POST')
        return json(res, { error: '演示操作接口仅接受 POST' }, 405);
      if (path === '/__preview')
        return json(res, {
          fixture: '本地演示夹具',
          fictional: true,
          memory_only: true,
          scenario: scene.name,
          scenarios: [...SCENARIOS],
        });
      await assets.image(context);
      if (res.writableEnded) return;
      if (path === '/api/auth/status') return auth.status(res);
      context.body = method === 'GET' || method === 'HEAD' ? {} : await bodyOf(req);
      if (path === '/api/auth/login') return auth.login(context.body, res);
      if (!auth.requireSession(req, res)) return;
      if (path === '/api/auth/me') return auth.me(res);
      if (path === '/api/auth/logout') return auth.logout(res);
      if (method !== 'GET' && method !== 'HEAD') {
        if (!auth.requireCsrf(req, res)) return;
        if (path === '/__preview/scenario') {
          if (!scene.set(context.body.scenario)) return json(res, { error: '未知演示场景' }, 400);
          return json(res, { ok: true, scenario: scene.name, message: '演示场景已切换，请刷新页面' });
        }
        if (!scene.canManage()) return json(res, { error: '当前为只读演示场景' }, 403);
      }
      if (path === '/api/auth/password') return auth.changePassword(context.body, res);
      for (const route of routes) {
        await route.handle(context);
        if (res.writableEnded) return;
      }
      return json(res, { error: '未实现的演示接口：' + path }, 404);
    } catch (error) {
      json(res, { error: error instanceof Error ? error.message : '演示请求失败' }, 400);
    }
  });
}
