// panels.test.tsx —— 舰载全息面板回归测试
//
// 覆盖：出口契约（8 个面板 + PANEL_COMPONENTS/PANEL_META 一致）、
// 总览渲染真实载荷、日志级别过滤与跟随开关、模块启停调用、火控保存与校验错误、
// 以及「每个面板在 Esc 时都会 onClose」。
// 说明：终端外框（engine 侧）持有全局 Esc；面板只处理落在自己子树内的按键，
// 因此这里把 Esc 派发到面板根节点上（等价于焦点在终端内部时按下 Esc）。

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { api } from '../../../api/endpoints';
import { clearQueries } from '../../../data/queryCore';
import { STATION_BY_ID } from '../../core/types';
import type { PanelId, Vital } from '../../core/types';
import {
  CommsPanel,
  DrydockPanel,
  FireControlPanel,
  FlightPanel,
  MainframePanel,
  NavPanel,
  OverviewPanel,
  PANEL_COMPONENTS,
  PANEL_META,
  PowerPanel,
  type PanelProps,
} from './index';

vi.mock('../../../api/endpoints.js', () => ({
  api: {
    overview: vi.fn(),
    bots: vi.fn(),
    botDetail: vi.fn(),
    system: vi.fn(),
    services: vi.fn(),
    tasks: vi.fn(),
    logs: vi.fn(),
    logsSince: vi.fn(),
    seriesMessages: vi.fn(),
    seriesLatency: vi.fn(),
    statsApiCalls: vi.fn(),
    statsActiveUsers: vi.fn(),
    statsUsage: vi.fn(),
    seriesUsage: vi.fn(),
    plugins: vi.fn(),
    pluginToggle: vi.fn(),
    pluginReload: vi.fn(),
    pluginUpdate: vi.fn(),
    pluginUninstall: vi.fn(),
    pluginInstall: vi.fn(),
    pluginsCheckUpdates: vi.fn(),
    pluginsProxySave: vi.fn(),
    pluginConfig: vi.fn(),
    pluginConfigSave: vi.fn(),
    config: vi.fn(),
    configSave: vi.fn(),
    configValidate: vi.fn(),
    configReload: vi.fn(),
    configModels: vi.fn(),
    modelsLibrarySave: vi.fn(),
    modelsAssignmentsSave: vi.fn(),
    modelsTest: vi.fn(),
    modelsProviderModels: vi.fn(),
    env: vi.fn(),
    envSave: vi.fn(),
    envAddPlatform: vi.fn(),
    restart: vi.fn(),
  },
}));

const VITALS: Vital[] = [
  { key: 'energy', label: '能源储备', value: 72, unit: '%', source: 'CPU 占用' },
  { key: 'atmosphere', label: '生命保障', value: 64, unit: '%', source: '内存占用' },
  { key: 'hull', label: '舰体结构', value: 88, unit: '%', source: '磁盘占用' },
  { key: 'heat', label: '热负荷', value: 31, unit: '%', source: '系统负载' },
];

const OVERVIEW = {
  online: true,
  app_name: 'NapCat',
  app_version: '4.0.0',
  uptime_seconds: 3660,
  today_messages: 12345,
  total_messages: 99999,
  plugins_loaded: 6,
  plugins_total: 8,
  bot_nickname: 'NeoBot',
  bot_user_id: 10001,
};

const SYSTEM = {
  hostname: 'neobot-host',
  os: 'Linux',
  python_version: '3.12.4',
  pid: 4321,
  cpu_percent: 12.5,
  cpu_count: 4,
  mem_percent: 33.3,
  mem_used_mb: 1024,
  mem_total_mb: 4096,
  disk_percent: 44.4,
  disk_used_gb: 10.5,
  disk_total_gb: 100,
  load_average: [0.5, 0.4, 0.3],
  process_memory_mb: 256,
  process_threads: 12,
};

const LOGS = {
  total: 3,
  last_id: 3,
  items: [
    { id: 1, time: '10:00:00', level: 'INFO', module: 'core', message: '舰桥已上线' },
    { id: 2, time: '10:00:01', level: 'ERROR', module: 'net', message: '连接超时' },
    { id: 3, time: '10:00:02', level: 'SUCCESS', module: 'core', message: '插件加载完成' },
  ],
};

const PLUGIN_LIST = {
  console_plugin: 'dashboard',
  manage_enabled: true,
  hot_reload: true,
  proxy: { mode: 'system', description: '跟随系统' },
  items: [
    {
      id: 'memo',
      name: 'memo',
      version: '0.2.0',
      official: false,
      source: 'third_party',
      status: 'loaded',
      enabled: true,
      manageable: true,
      hot_reload: true,
      config_hot_reload: true,
      description: '记忆插件',
    },
    {
      id: 'dashboard',
      name: 'dashboard',
      version: '1.0.0',
      official: true,
      source: 'official',
      status: 'loaded',
      enabled: true,
      manageable: false,
      hot_reload: false,
      description: '网页面板',
    },
  ],
};

const PLUGIN_CONFIG = {
  section: 'memo',
  path: 'plugin.toml',
  revision: 2,
  form_supported: true,
  source_available: true,
  source: '[config]\nlimit = 5\n',
  config: { limit: 5 },
  schema: [{ name: 'limit', path: ['limit'], kind: 'scalar' as const, type: 'int', value: 5 }],
};

const BODY_CONFIG = {
  path: 'config.toml',
  revision: 3,
  form_supported: false,
  source_available: true,
  source: '[bot]\nnickname = "NeoBot"\n',
  config: { bot: { nickname: 'NeoBot' } },
  schema: [],
};

/** 写操作未在测试里显式提供时的兜底：返回一个失败的 Result，避免面板读到 undefined */
const NO_RESULT = { ok: false, data: null, error: '测试未提供该接口', status: 0 };

function renderPanel(id: PanelId, overrides: Partial<PanelProps> = {}) {
  const Component = PANEL_COMPONENTS[id];
  const onClose = overrides.onClose ?? vi.fn();
  const onLaunchMiniGame = overrides.onLaunchMiniGame ?? vi.fn();
  const utils = render(
    <Component
      station={STATION_BY_ID[id]}
      vitals={VITALS}
      onClose={onClose}
      onLaunchMiniGame={onLaunchMiniGame}
      refreshToken={overrides.refreshToken ?? 0}
    />,
  );
  return { ...utils, onClose, onLaunchMiniGame };
}

beforeEach(() => {
  vi.clearAllMocks();
  // useQuery 的缓存是模块级的：每个用例都从空缓存开始，避免上一个用例的数据串味
  clearQueries();

  vi.mocked(api.overview).mockResolvedValue(OVERVIEW);
  vi.mocked(api.system).mockResolvedValue(SYSTEM);
  vi.mocked(api.logs).mockResolvedValue(LOGS);
  vi.mocked(api.logsSince).mockResolvedValue({ items: [], last_id: 0, total: 3 });
  vi.mocked(api.seriesMessages).mockResolvedValue({ series: [{ at: '2024-05-01T10:00', count: 3 }], total: 3 });
  vi.mocked(api.seriesLatency).mockResolvedValue({ series: [{ at: '2024-05-01T10:00', ms: 42 }], current_ms: 42, avg_ms: 40, success_rate: 99 });
  vi.mocked(api.statsApiCalls).mockResolvedValue({ items: [{ action: 'send_msg', count: 7 }], total_calls: 7, unique_actions: 1 });
  vi.mocked(api.statsActiveUsers).mockResolvedValue({ items: [{ user_id: 10001, nickname: '舰长', count: 5, last_seen: 0 }], tracked_users: 1 });
  vi.mocked(api.tasks).mockResolvedValue({ scheduled: [], background: [] });
  vi.mocked(api.services).mockResolvedValue({ items: [] });
  vi.mocked(api.botDetail).mockResolvedValue({ nickname: 'NeoBot', user_id: 10001, online: true, latency_ms: 42, uptime_seconds: 3600 });

  vi.mocked(api.plugins).mockResolvedValue(PLUGIN_LIST);
  vi.mocked(api.pluginConfig).mockResolvedValue({ ok: true, data: PLUGIN_CONFIG, error: null, status: 200 });
  vi.mocked(api.pluginToggle).mockResolvedValue({ ok: true, data: { message: '已停用' }, error: null, status: 200 });
  vi.mocked(api.pluginReload).mockResolvedValue({ ok: true, data: { message: '已重载' }, error: null, status: 200 });
  vi.mocked(api.pluginUpdate).mockResolvedValue({ ok: true, data: { message: '已更新' }, error: null, status: 200 });
  vi.mocked(api.pluginUninstall).mockResolvedValue({ ok: true, data: { message: '已卸载' }, error: null, status: 200 });
  vi.mocked(api.pluginInstall).mockResolvedValue({ ok: true, data: { message: '安装完成' }, error: null, status: 200 });
  vi.mocked(api.pluginConfigSave).mockResolvedValue({ ok: true, data: PLUGIN_CONFIG, error: null, status: 200 });
  vi.mocked(api.pluginsCheckUpdates).mockResolvedValue({ ok: true, data: { message: '检查完成' }, error: null, status: 200 });
  vi.mocked(api.pluginsProxySave).mockResolvedValue({ ok: true, data: { proxy: { mode: 'system' } }, error: null, status: 200 });

  vi.mocked(api.config).mockResolvedValue({ ok: true, data: BODY_CONFIG, error: null, status: 200 });
  vi.mocked(api.configSave).mockResolvedValue({ ok: true, data: BODY_CONFIG, error: null, status: 200 });
  vi.mocked(api.configValidate).mockResolvedValue({ ok: true, data: {}, error: null, status: 200 });
  vi.mocked(api.configReload).mockResolvedValue({ ok: true, data: { message: '已重载' }, error: null, status: 200 });
  vi.mocked(api.restart).mockResolvedValue({ ok: true, data: { message: '已请求重启' }, error: null, status: 200 });

  vi.mocked(api.seriesUsage).mockResolvedValue(NO_RESULT);
  vi.mocked(api.configModels).mockResolvedValue(NO_RESULT);
  vi.mocked(api.modelsLibrarySave).mockResolvedValue(NO_RESULT);
  vi.mocked(api.modelsAssignmentsSave).mockResolvedValue(NO_RESULT);
  vi.mocked(api.modelsTest).mockResolvedValue(NO_RESULT);
  vi.mocked(api.modelsProviderModels).mockResolvedValue(NO_RESULT);
  vi.mocked(api.env).mockResolvedValue(NO_RESULT);
  vi.mocked(api.envSave).mockResolvedValue(NO_RESULT);
  vi.mocked(api.envAddPlatform).mockResolvedValue(NO_RESULT);
});

describe('面板出口', () => {
  it('导出全部 8 个面板组件', () => {
    const exported = [OverviewPanel, CommsPanel, NavPanel, PowerPanel, MainframePanel, FlightPanel, DrydockPanel, FireControlPanel];
    expect(exported).toHaveLength(8);
    for (const Component of exported) expect(typeof Component).toBe('function');
  });

  it('PANEL_COMPONENTS 的键与 PANEL_META 完全一致', () => {
    expect(Object.keys(PANEL_COMPONENTS).sort()).toEqual(Object.keys(PANEL_META).sort());
    expect(Object.keys(PANEL_COMPONENTS).sort()).toEqual([
      'comms',
      'drydock',
      'firecontrol',
      'flight',
      'mainframe',
      'nav',
      'overview',
      'power',
    ]);
    // 抬头文案来自 STATIONS，唯一数据源
    expect(PANEL_META.overview.terminal).toBe(STATION_BY_ID.overview.terminal);
    expect(PANEL_META.overview.title).toBe(STATION_BY_ID.overview.title);
  });
});

describe('overview 指挥台', () => {
  it('渲染总览与系统真实载荷，并给出链路状态读数', async () => {
    renderPanel('overview');

    expect(await screen.findByText('12,345')).toBeInTheDocument(); // today_messages
    expect(screen.getByText('累计 99,999')).toBeInTheDocument(); // total_messages
    expect(screen.getByText(/neobot-host/)).toBeInTheDocument(); // /api/system hostname
    expect(screen.getByText('NeoBot')).toBeInTheDocument(); // bot_nickname
    // 标题/编号由外框（TerminalFrame）负责渲染，面板自己只保留状态条——
    // 这里守住状态条确实在，避免「去掉重复抬头」时把链路读数一起删掉。
    expect(screen.getByText(/末次刷新/)).toBeInTheDocument();
  });

  it('提供火控演习与断路器检修两个小游戏入口', async () => {
    const user = userEvent.setup();
    const { onLaunchMiniGame } = renderPanel('overview');

    await user.click(screen.getByRole('button', { name: '启动火控演习' }));
    expect(onLaunchMiniGame).toHaveBeenCalledWith('turret');

    await user.click(screen.getByRole('button', { name: '启动断路器检修' }));
    expect(onLaunchMiniGame).toHaveBeenCalledWith('circuit');
  });
});

describe('comms 航行日志', () => {
  it('按级别过滤：关闭 INFO 后只保留其他级别', async () => {
    const user = userEvent.setup();
    renderPanel('comms');

    expect(await screen.findByText(/舰桥已上线/)).toBeInTheDocument();
    expect(screen.getByText(/连接超时/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'INFO' }));

    expect(screen.queryByText(/舰桥已上线/)).not.toBeInTheDocument();
    expect(screen.getByText(/连接超时/)).toBeInTheDocument();
    expect(screen.getByText(/插件加载完成/)).toBeInTheDocument();
  });

  it('跟随开关：点击后进入暂停，再点恢复跟随', async () => {
    const user = userEvent.setup();
    renderPanel('comms');

    await screen.findByText(/舰桥已上线/);
    const toggle = screen.getByRole('button', { name: /暂停跟随/ });

    await user.click(toggle);
    expect(screen.getByRole('button', { name: /恢复跟随/ })).toBeInTheDocument();
    expect(screen.getAllByText(/已暂停/).length).toBeGreaterThan(0);

    await user.click(screen.getByRole('button', { name: /恢复跟随/ }));
    expect(screen.getByRole('button', { name: /暂停跟随/ })).toBeInTheDocument();
  });

  it('按 since 游标增量抓取新日志（假定时器）', async () => {
    vi.useFakeTimers();
    try {
      vi.mocked(api.logs).mockResolvedValue({ items: [LOGS.items[0]], last_id: 1, total: 1 });
      vi.mocked(api.logsSince).mockResolvedValue({ items: [LOGS.items[1]], last_id: 2, total: 2 });
      renderPanel('comms');

      // 首读全量
      await act(async () => {
        await Promise.resolve();
      });
      expect(screen.getByText(/舰桥已上线/)).toBeInTheDocument();

      // 推进一个抓取周期（默认 1.5 秒）
      await act(async () => {
        vi.advanceTimersByTime(1600);
        await Promise.resolve();
      });

      expect(api.logsSince).toHaveBeenCalledWith(1, 500);
      expect(screen.getByText(/连接超时/)).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('mainframe 模块管理', () => {
  it('点击启停控件时调用 api.pluginToggle 并带上正确的模块名', async () => {
    const user = userEvent.setup();
    renderPanel('mainframe');

    const toggle = await screen.findByRole('button', { name: '停用模块 memo' });
    await user.click(toggle);

    expect(api.pluginToggle).toHaveBeenCalledTimes(1);
    expect(api.pluginToggle).toHaveBeenCalledWith('memo');
  });

  it('默认选中第一个运行中的模块并读取其配置', async () => {
    renderPanel('mainframe');

    expect(await screen.findByRole('heading', { name: '模块配置' })).toBeInTheDocument();
    expect(api.pluginConfig).toHaveBeenCalledWith('memo');
  });
});

describe('firecontrol 火控台', () => {
  it('TOML 模式下保存会调用 api.configSave，并展示后端返回的校验错误', async () => {
    const user = userEvent.setup();
    vi.mocked(api.configSave).mockResolvedValue({
      ok: false,
      data: { errors: [{ path: 'bot.nickname', message: '昵称必须为 2-20 个字符' }] },
      error: '配置校验未通过',
      status: 400,
    });

    renderPanel('firecontrol');

    const editor = await screen.findByLabelText('config.toml');
    fireEvent.change(editor, { target: { value: '[bot]\nnickname = "N"\n' } });
    await user.click(screen.getByRole('button', { name: /保存并重载/ }));

    expect(api.configSave).toHaveBeenCalledTimes(1);
    expect(api.configSave).toHaveBeenCalledWith(
      expect.objectContaining({ revision: 3, mode: 'toml', reload: true, source: '[bot]\nnickname = "N"\n' }),
    );
    expect(await screen.findByText(/昵称必须为 2-20 个字符/)).toBeInTheDocument();
    expect(screen.getByText(/bot\.nickname/)).toBeInTheDocument();
  });

  it('损管读数由真实指标推导（/api/system）', async () => {
    renderPanel('firecontrol');

    expect(await screen.findByText('cpu_percent')).toBeInTheDocument();
    expect(screen.getByText('mem_percent')).toBeInTheDocument();
    expect(screen.getByText('disk_percent')).toBeInTheDocument();
  });
});

describe('键盘：Esc 断开终端', () => {
  const ids: PanelId[] = ['overview', 'comms', 'nav', 'power', 'mainframe', 'flight', 'drydock', 'firecontrol'];

  it.each(ids)('%s 面板在终端内按下 Esc 时调用 onClose', async (id) => {
    const onClose = vi.fn();
    const { container } = renderPanel(id, { onClose });
    // 让首屏请求落地（含链式请求），避免未包裹 act 的更新警告
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    const root = container.firstElementChild as HTMLElement;

    fireEvent.keyDown(root, { key: 'Escape' });

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('输入框聚焦时按 Esc 同样关闭终端（不会被表单吞掉）', async () => {
    const onClose = vi.fn();
    renderPanel('mainframe', { onClose });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    const search = screen.getByLabelText('搜索模块');

    fireEvent.keyDown(search, { key: 'Escape' });

    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
