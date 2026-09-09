// endpoints.js —— 后端 /api/* 端点集中封装
import { getJSON, getResult, postJSON } from './client.js';

export const api = {
  // 鉴权
  login: (password) => postJSON('/api/auth/login', { password }),
  setup: (password, confirm) => postJSON('/api/auth/setup', { password, confirm }),
  logout: () => postJSON('/api/auth/logout'),
  me: () => getResult('/api/auth/me'),

  // 概览 / 统计
  overview: () => getJSON('/api/overview'),
  bots: () => getJSON('/api/bots'),
  system: () => getJSON('/api/system'),
  services: () => getJSON('/api/services'),
  tasks: () => getJSON('/api/tasks'),
  botDetail: () => getJSON('/api/bot/detail'),
  logs: (limit = 80) => getJSON('/api/logs?limit=' + limit),
  logsSince: (since, limit = 500) => getJSON('/api/logs?since=' + since + '&limit=' + limit),
  seriesMessages: (days = 30) => getJSON('/api/series/messages?days=' + days),
  seriesLatency: () => getJSON('/api/series/latency'),
  statsApiCalls: (limit = 10) => getJSON('/api/stats/api-calls?limit=' + limit),
  statsActiveUsers: (limit = 10) => getJSON('/api/stats/active-users?limit=' + limit),
  statsUsage: (hours = 24) => getJSON('/api/stats/usage?hours=' + hours),
  seriesUsage: (hours = 24, bucket = 'hour') =>
    getResult('/api/series/usage?hours=' + hours + '&bucket=' + bucket),

  // 插件
  plugins: () => getJSON('/api/plugins'),
  pluginToggle: (name) => postJSON('/api/plugins/' + encodeURIComponent(name) + '/toggle'),
  pluginReload: (name) => postJSON('/api/plugins/' + encodeURIComponent(name) + '/reload'),
  pluginUpdate: (name) => postJSON('/api/plugins/' + encodeURIComponent(name) + '/update'),
  pluginUninstall: (name) => postJSON('/api/plugins/' + encodeURIComponent(name) + '/uninstall'),
  pluginInstall: (repo, branch = 'main', replace = false) =>
    postJSON('/api/plugins/install', { repo, branch, replace }),
  pluginsCheckUpdates: () => getResult('/api/plugins/check-updates'),
  pluginsProxySave: (body) => postJSON('/api/plugins/proxy', body),
  pluginConfig: (name) => getResult('/api/plugins/' + encodeURIComponent(name) + '/config'),
  pluginConfigSave: (name, body) =>
    postJSON('/api/plugins/' + encodeURIComponent(name) + '/config', body),

  // 本体配置 / 环境变量 / 模型
  config: () => getResult('/api/config'),
  configSave: (body) => postJSON('/api/config', body),
  configValidate: (body) => postJSON('/api/config/validate', body),
  configReload: () => postJSON('/api/config/reload'),
  configModels: () => getResult('/api/config/models'),
  modelsLibrarySave: (body) => postJSON('/api/config/models/library', body),
  modelsAssignmentsSave: (body) => postJSON('/api/config/models/assignments', body),
  env: () => getResult('/api/config/env'),
  envSave: (body) => postJSON('/api/config/env', body),
  envAddPlatform: (body) => postJSON('/api/config/env/platform', body),

  // 管理
  restart: () => postJSON('/api/admin/restart'),
};
