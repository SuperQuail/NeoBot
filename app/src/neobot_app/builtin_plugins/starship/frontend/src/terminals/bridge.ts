// terminals/bridge.ts —— 舰桥终端：主控台、通讯台，以及货舱的战绩墙。

import * as THREE from 'three';
import { Poller, type ApiResult } from '../net/api';
import type { TerminalContext, TerminalController, TerminalDefinition } from '../ui/terminal';
import type { UiSurface } from '../ui/surface';
import {
  formatClock,
  formatCost,
  formatDuration,
  formatNumber,
  formatTokens,
  failMessage,
  type AchievementItem,
  type LatencyPayload,
  type MessageSeriesPayload,
  type OverviewPayload,
  type PluginListPayload,
  type PowerPayload,
  type RankPayload,
  type ScorePayload,
  type SimpleMessage,
  type UsagePayload,
} from './shared';

interface DataHub<T> {
  value: T | null;
  error: string | null;
  updatedAt: number;
}

function hub<T>(): DataHub<T> {
  return { value: null, error: null, updatedAt: 0 };
}

// ---------------------------------------------------------------------------
// 主控台：舰船总览 + 运行状态控制
// ---------------------------------------------------------------------------

export const dashboardTerminal: TerminalDefinition = {
  id: 'dashboard',
  title: '主控台',
  subtitle: '舰船总览 · MASTER CONSOLE',
  accent: 0x38d8ff,
  create(ctx: TerminalContext): TerminalController {
    const overview = hub<OverviewPayload>();
    const latency = hub<LatencyPayload>();
    const messages = hub<MessageSeriesPayload>();
    const usage = hub<UsagePayload>();
    const plugins = hub<PluginListPayload>();
    const power = hub<PowerPayload>();
    let busy = false;

    const pollers = [
      new Poller<OverviewPayload>(
        () => ctx.host.consoleApi.get<OverviewPayload>('/api/overview') as Promise<ApiResult<OverviewPayload>>,
        5000,
        (data) => {
          overview.value = data;
          overview.updatedAt = performance.now();
          ctx.redraw();
        },
        (message) => {
          overview.error = message;
          ctx.redraw();
        },
      ),
      new Poller<LatencyPayload>(
        () => ctx.host.consoleApi.get<LatencyPayload>('/api/series/latency') as Promise<ApiResult<LatencyPayload>>,
        8000,
        (data) => {
          latency.value = data;
          ctx.redraw();
        },
      ),
      new Poller<MessageSeriesPayload>(
        () => ctx.host.consoleApi.get<MessageSeriesPayload>('/api/series/messages?days=14') as Promise<ApiResult<MessageSeriesPayload>>,
        30000,
        (data) => {
          messages.value = data;
          ctx.redraw();
        },
      ),
      new Poller<UsagePayload>(
        () => ctx.host.consoleApi.get<UsagePayload>('/api/stats/usage?hours=24') as Promise<ApiResult<UsagePayload>>,
        30000,
        (data) => {
          usage.value = data;
          ctx.redraw();
        },
      ),
      new Poller<PluginListPayload>(
        () => ctx.host.consoleApi.get<PluginListPayload>('/api/plugins') as Promise<ApiResult<PluginListPayload>>,
        20000,
        (data) => {
          plugins.value = data;
          if (typeof data.manage_enabled === 'boolean') {
            ctx.shell.setManageEnabled(data.manage_enabled);
          }
          ctx.redraw();
        },
      ),
      new Poller<PowerPayload>(
        () => ctx.host.consoleApi.get<PowerPayload>('/api/admin/power') as Promise<ApiResult<PowerPayload>>,
        5000,
        (data) => {
          power.value = data;
          ctx.redraw();
        },
      ),
    ];

    async function post(path: string, body: unknown, okText: string): Promise<void> {
      busy = true;
      ctx.redraw();
      const result = await ctx.host.consoleApi.post<SimpleMessage>(path, body);
      busy = false;
      if (result.ok) {
        ctx.toast(okText, 'ok');
        for (const poller of pollers) void poller.tick();
      } else {
        ctx.toast(failMessage(result), 'error');
      }
      ctx.redraw();
    }

    return {
      pollers,
      onFocus() {
        ctx.redraw();
      },
      draw(ui: UiSurface, focused: boolean) {
        const status = ctx.shell.status;
        const info = overview.value || {};
        const powerInfo = power.value || {};
        const standby = Boolean(powerInfo.standby ?? status.standby);

        // 左：舰体状态
        ui.panel({ x: 20, y: 130, w: 330, h: 250 }, { title: '舰体状态 / HULL' });
        const hull = standby
          ? 0.32
          : clamp01(1 - (status.plugins.error || 0) * 0.08);
        ui.gauge({ x: 110, y: 300 }, 62, hull, {
          valueText: (hull * 100).toFixed(0) + '%',
          label: standby ? '低功耗' : '运转正常',
          color: standby ? ui.theme.warn : ui.theme.ok,
        });
        ui.keyValue(190, 220, 150, '运行时长', formatDuration(info.uptime_seconds ?? status.uptime_seconds));
        ui.keyValue(190, 248, 150, '在位插件', String(status.plugins.running) + '/' + String(status.plugins.total));
        ui.keyValue(190, 276, 150, '待机时长', standby ? formatDuration(status.standby_seconds) : '—');
        ui.keyValue(190, 304, 150, 'OneBot', status.online ? '已连接' : '未连接', status.online ? ui.theme.ok : ui.theme.error);
        ui.keyValue(190, 332, 150, '版本', String(info.app_version || '—'));

        // 中：实时指标
        ui.panel({ x: 368, y: 130, w: 636, h: 250 }, { title: '实时指标 / TELEMETRY' });
        const latencySeries = (latency.value?.series || []).map((point) => Number(point.ms || 0));
        ui.sparkline({ x: 388, y: 190, w: 300, h: 84 }, latencySeries.slice(-60), {
          label: 'API 往返延迟',
          valueText: String(Math.round(latency.value?.current_ms ?? 0)) + ' ms',
          fill: true,
        });
        const messageSeries = (messages.value?.series || []).map((point) => Number(point.count || 0));
        ui.sparkline({ x: 706, y: 190, w: 278, h: 84 }, messageSeries.slice(-40), {
          label: '近 14 天消息量',
          valueText: formatNumber(info.today_messages) + ' / 今日',
          fill: true,
          color: ui.theme.ok,
        });
        ui.keyValue(388, 300, 280, '今日消息', formatNumber(info.today_messages));
        ui.keyValue(388, 326, 280, '累计消息', formatNumber(info.total_messages));
        ui.keyValue(388, 352, 280, '模型调用（24h）', formatNumber(usage.value?.totals?.calls));
        ui.keyValue(706, 300, 278, '24h 消耗', formatCost(usage.value?.totals?.cost_cny));
        ui.keyValue(706, 326, 278, '输入 / 输出', formatTokens(usage.value?.totals?.input_tokens) + ' / ' + formatTokens(usage.value?.totals?.output_tokens));
        ui.keyValue(706, 352, 278, '在线机器人', String(info.bot_nickname || '—'));

        // 下：舰船指令（写操作，全部保留 + 危险操作二次确认）
        ui.panel({ x: 20, y: 396, w: 984, h: 158 }, { title: '舰船指令 / COMMAND', tone: ui.theme.warn });
        ui.text(40, 448, standby ? '舰船当前处于低功耗待机：仅主控台、配置、日志与插件终端在线。' : '所有系统在线。危险指令会有二次确认。', {
          size: 17,
          color: standby ? ui.theme.warn : ui.theme.textDim,
        });
        const canResume = !busy && standby;
        if (ui.button('power-resume', { x: 40, y: 468, w: 190, h: 58 }, busy ? '执行中…' : '恢复运行', { disabled: !canResume, tone: ui.theme.ok })) {
          void (async () => {
            const ok = await ctx.confirm({
              title: '恢复舰船运行',
              body: '将重建 bot 运行时（回复、记忆、Agent 全部恢复）。期间消息处理会短暂中断。',
              confirmLabel: '恢复运行',
            });
            if (ok) await post('/api/admin/resume', { reason: '星舰主控台恢复' }, '已开始恢复运行');
          })();
        }
        if (ui.button('power-standby', { x: 246, y: 468, w: 190, h: 58 }, '进入待机', { disabled: busy || standby, tone: ui.theme.warn })) {
          void (async () => {
            const ok = await ctx.confirm({
              title: '进入待机（低功耗）',
              body: '将停止回复与记忆管线，只保留面板与核心服务。舰内多数终端会随之离线。',
              confirmLabel: '进入待机',
              danger: true,
            });
            if (ok) await post('/api/admin/standby', { reason: '星舰主控台待机' }, '已进入待机');
          })();
        }
        if (ui.button('power-reboot', { x: 452, y: 468, w: 190, h: 58 }, '软重启运行', { disabled: busy, tone: ui.theme.warn })) {
          void (async () => {
            const ok = await ctx.confirm({
              title: '软重启运行',
              body: '重建运行时并按当前配置重新装配（不重启进程）。',
              confirmLabel: '软重启',
              danger: true,
            });
            if (ok) await post('/api/admin/reboot', { reason: '星舰主控台软重启' }, '已开始软重启');
          })();
        }
        if (ui.button('admin-restart', { x: 658, y: 468, w: 190, h: 58 }, '重启 NeoBot', { disabled: busy, tone: ui.theme.error })) {
          void (async () => {
            const ok = await ctx.confirm({
              title: '重启 NeoBot 进程',
              body: '整个进程会退出并重新启动，网页面板会短暂断开（本页面随后需要刷新）。',
              confirmLabel: '确认重启',
              danger: true,
            });
            if (ok) await post('/api/admin/restart', {}, '重启指令已下发');
          })();
        }
        if (ui.button('open-console', { x: 854, y: 562, w: 130, h: 30 }, '在面板中打开', { size: 15, tone: ui.theme.textDim })) {
          window.open(new URL('../', window.location.href).toString(), '_blank');
        }
        if (!focused) {
          ui.text(40, 545, '靠近并按 E 可操作终端', { size: 15, color: ui.theme.textDim });
        }
      },
    };
  },
};

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

// ---------------------------------------------------------------------------
// 通讯台：机器人 / 延迟 / 活跃用户
// ---------------------------------------------------------------------------

export const botsTerminal: TerminalDefinition = {
  id: 'bots',
  title: '通讯台',
  subtitle: '机器人 · 会话 · COMMS',
  accent: 0x62e0c8,
  create(ctx: TerminalContext): TerminalController {
    const bots = hub<Array<Record<string, unknown>>>();
    const latency = hub<LatencyPayload>();
    const activeUsers = hub<RankPayload>();
    const apiCalls = hub<RankPayload>();
    const pollers = [
      new Poller<Array<Record<string, unknown>>>(
        () => ctx.host.consoleApi.get<Array<Record<string, unknown>>>('/api/bots') as Promise<ApiResult<Array<Record<string, unknown>>>>,
        10000,
        (data) => {
          bots.value = data;
          ctx.redraw();
        },
        (message) => {
          bots.error = message;
          ctx.redraw();
        },
      ),
      new Poller<LatencyPayload>(
        () => ctx.host.consoleApi.get<LatencyPayload>('/api/series/latency') as Promise<ApiResult<LatencyPayload>>,
        10000,
        (data) => {
          latency.value = data;
          ctx.redraw();
        },
      ),
      new Poller<RankPayload>(
        () => ctx.host.consoleApi.get<RankPayload>('/api/stats/active-users?limit=8') as Promise<ApiResult<RankPayload>>,
        30000,
        (data) => {
          activeUsers.value = data;
          ctx.redraw();
        },
      ),
      new Poller<RankPayload>(
        () => ctx.host.consoleApi.get<RankPayload>('/api/stats/api-calls?limit=8') as Promise<ApiResult<RankPayload>>,
        15000,
        (data) => {
          apiCalls.value = data;
          ctx.redraw();
        },
      ),
    ];

    return {
      pollers,
      draw(ui: UiSurface) {
        const bot = (bots.value || [])[0] || {};
        const online = Boolean(bot.online);
        ui.panel({ x: 20, y: 130, w: 470, h: 420 }, { title: '链路状态 / LINK' });
        ui.text(44, 190, online ? '● 通讯链路正常' : '○ 未检测到 OneBot 连接', {
          size: 24,
          color: online ? ui.theme.ok : ui.theme.error,
        });
        ui.keyValue(44, 240, 420, '昵称', String(bot.nickname || bot.name || '—'));
        ui.keyValue(44, 272, 420, '账号', String(bot.user_id || '—'));
        ui.keyValue(44, 304, 420, '平台', String(bot.platform || bot.app_name || '—'));
        ui.keyValue(44, 336, 420, '延迟', String(Math.round(Number(latency.value?.current_ms ?? bot.latency_ms ?? 0))) + ' ms');
        ui.keyValue(44, 368, 420, '成功率', String(Math.round(Number(latency.value?.success_rate ?? 100))) + '%');
        ui.keyValue(44, 400, 420, '今日消息', formatNumber(Number(bot.today_messages ?? 0)));
        ui.keyValue(44, 432, 420, '累计消息', formatNumber(Number(bot.total_messages ?? 0)));
        ui.keyValue(44, 464, 420, '在线时长', formatDuration(Number(bot.uptime_seconds ?? 0)));
        ui.sparkline({ x: 44, y: 486, w: 420, h: 44 }, (latency.value?.series || []).map((point) => Number(point.ms || 0)).slice(-60), {
          color: ui.theme.ok,
          fill: true,
        });

        ui.panel({ x: 508, y: 130, w: 496, h: 200 }, { title: '活跃会话 / ACTIVE' });
        const users = (activeUsers.value?.items || []).slice(0, 5);
        if (users.length === 0) {
          ui.text(532, 196, '暂无活跃用户数据', { size: 17, color: ui.theme.textDim });
        }
        users.forEach((item, index) => {
          ui.keyValue(532, 186 + index * 28, 448, String(index + 1) + '. ' + String(item.nickname || item.name || item.user_id || '未知'), formatNumber(Number(item.count ?? item.value ?? 0)));
        });

        ui.panel({ x: 508, y: 348, w: 496, h: 202 }, { title: '接口调用排行 / API' });
        const calls = (apiCalls.value?.items || []).slice(0, 5);
        if (calls.length === 0) {
          ui.text(532, 412, '暂无接口调用记录', { size: 17, color: ui.theme.textDim });
        }
        calls.forEach((item, index) => {
          ui.keyValue(532, 404 + index * 28, 448, String(index + 1) + '. ' + String(item.name || item.label || '—'), formatNumber(Number(item.count ?? item.value ?? 0)));
        });
      },
    };
  },
};

// ---------------------------------------------------------------------------
// 战绩墙：小游戏排行榜与成就（数据来自 starship 插件自己的数据库）
// ---------------------------------------------------------------------------

export const scoresTerminal: TerminalDefinition = {
  id: 'scores',
  title: '战绩墙',
  subtitle: '排行榜 · 成就 · RECORDS',
  accent: 0xc8a2ff,
  create(ctx: TerminalContext): TerminalController {
    const scores = hub<ScorePayload>();
    const achievements = hub<{ items?: AchievementItem[] }>();
    let selectedGame = '';
    const pollers = [
      new Poller<ScorePayload>(
        () =>
          ctx.host.gameApi.get<ScorePayload>(
            '/api/scores?limit=12' + (selectedGame ? '&game=' + encodeURIComponent(selectedGame) : ''),
          ) as Promise<ApiResult<ScorePayload>>,
        15000,
        (data) => {
          scores.value = data;
          ctx.redraw();
        },
        (message) => {
          scores.error = message;
          ctx.redraw();
        },
      ),
      new Poller<{ items?: AchievementItem[] }>(
        () => ctx.host.gameApi.get<{ items?: AchievementItem[] }>('/api/achievements') as Promise<ApiResult<{ items?: AchievementItem[] }>>,
        30000,
        (data) => {
          achievements.value = data;
          ctx.redraw();
        },
      ),
    ];

    return {
      pollers,
      draw(ui: UiSurface) {
        ui.panel({ x: 20, y: 130, w: 560, h: 424 }, { title: '排行榜 / LEADERBOARD' });
        const tabs: Array<[string, string]> = [
          ['', '全部'],
          ['turret', '舱外炮塔'],
          ['repair', '损管抢修'],
        ];
        tabs.forEach((entry, index) => {
          if (ui.button('tab-' + index, { x: 40 + index * 118, y: 168, w: 110, h: 36 }, entry[1], {
            tone: selectedGame === entry[0] ? ui.theme.accent : ui.theme.textDim,
            size: 16,
          })) {
            selectedGame = entry[0];
            void pollers[0].tick();
          }
        });
        const items = scores.value?.items || [];
        if (items.length === 0) {
          ui.text(44, 260, '还没有成绩记录：去机库玩一局吧。', { size: 19, color: ui.theme.textDim });
        }
        items.slice(0, 9).forEach((item, index) => {
          const y = 228 + index * 36;
          ui.text(44, y, pad(index + 1), { size: 18, color: index < 3 ? ui.theme.warn : ui.theme.textDim });
          ui.text(92, y, String(item.player || '舰长'), { size: 18 });
          ui.text(300, y, String(item.game === 'repair' ? '损管抢修' : '舱外炮塔'), { size: 16, color: ui.theme.textDim });
          ui.text(544, y, formatNumber(item.score), { size: 19, align: 'right', color: ui.theme.accent });
        });

        ui.panel({ x: 600, y: 130, w: 404, h: 424 }, { title: '成就 / ACHIEVEMENTS' });
        const list = achievements.value?.items || [];
        if (list.length === 0) {
          ui.text(624, 200, '尚未解锁任何成就。', { size: 17, color: ui.theme.textDim });
          ui.text(624, 230, '试试：首次跃迁、击毁小行星、完成抢修。', { size: 15, color: ui.theme.textDim });
        }
        list.slice(0, 10).forEach((item, index) => {
          const y = 186 + index * 36;
          ui.text(624, y, '◈ ' + String(item.key || ''), { size: 17, color: ui.theme.accent });
          ui.text(984, y, '×' + String(item.count ?? 1), { size: 16, align: 'right', color: ui.theme.textDim });
        });
      },
    };
  },
};

function pad(value: number): string {
  return String(value).padStart(2, '0');
}

export const bridgeTerminals: TerminalDefinition[] = [dashboardTerminal, botsTerminal, scoresTerminal];
