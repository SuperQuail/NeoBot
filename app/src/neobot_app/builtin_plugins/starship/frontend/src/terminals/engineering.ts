// terminals/engineering.ts —— 工程舱终端：反应堆监控、能量分配、插件模块机架。

import * as THREE from 'three';

import { Poller, type ApiResult } from '../net/api';
import type { TerminalContext, TerminalController, TerminalDefinition } from '../ui/terminal';
import type { UiSurface } from '../ui/surface';
import {
  failMessage,
  formatCost,
  formatDuration,
  formatNumber,
  formatTokens,
  type PluginItem,
  type PluginListPayload,
  type SimpleMessage,
  type SystemPayload,
  type UsagePayload,
} from './shared';

interface TasksPayload {
  scheduled?: Array<Record<string, unknown>>;
  background?: Array<Record<string, unknown>>;
  scheduled_error?: string;
}

interface ServicesPayload {
  items?: Array<{ name?: string; description?: string; available?: boolean }>;
}

// ---------------------------------------------------------------------------
// 反应堆监控：系统资源 / 后台任务 / 宿主服务
// ---------------------------------------------------------------------------

export const systemTerminal: TerminalDefinition = {
  id: 'system',
  title: '反应堆监控',
  subtitle: '系统资源 · REACTOR',
  accent: 0xffb454,
  decorate(group, materials) {
    const core = new THREE.Mesh(
      new THREE.IcosahedronGeometry(0.45, 1),
      new THREE.MeshBasicMaterial({ color: 0xffb454, transparent: true, opacity: 0.85 }),
    );
    core.position.set(0, 2.4, -0.9);
    group.add(core);
    const cage = new THREE.Mesh(
      new THREE.TorusGeometry(0.62, 0.03, 6, 32),
      materials.trim,
    );
    cage.position.set(0, 2.4, -0.9);
    group.add(cage);
  },
  create(ctx: TerminalContext): TerminalController {
    let system: SystemPayload | null = null;
    let tasks: TasksPayload | null = null;
    let services: ServicesPayload | null = null;
    let error: string | null = null;
    const history: number[] = [];

    const pollers = [
      new Poller<SystemPayload>(
        () => ctx.host.consoleApi.get<SystemPayload>('/api/system') as Promise<ApiResult<SystemPayload>>,
        3000,
        (data) => {
          system = data;
          history.push(Number(data.cpu_percent || 0));
          if (history.length > 120) history.shift();
          ctx.redraw();
        },
        (message) => {
          error = message;
          ctx.redraw();
        },
      ),
      new Poller<TasksPayload>(
        () => ctx.host.consoleApi.get<TasksPayload>('/api/tasks') as Promise<ApiResult<TasksPayload>>,
        15000,
        (data) => {
          tasks = data;
          ctx.redraw();
        },
      ),
      new Poller<ServicesPayload>(
        () => ctx.host.consoleApi.get<ServicesPayload>('/api/services') as Promise<ApiResult<ServicesPayload>>,
        30000,
        (data) => {
          services = data;
          ctx.redraw();
        },
      ),
    ];

    return {
      pollers,
      draw(ui: UiSurface) {
        const info = system || {};
        ui.panel({ x: 20, y: 130, w: 640, h: 300 }, { title: '堆芯负载 / CORE LOAD' });
        const cpu = Number(info.cpu_percent || 0);
        const mem = Number(info.mem_percent || 0);
        const disk = Number(info.disk_percent || 0);
        ui.gauge({ x: 130, y: 280 }, 66, cpu / 100, {
          valueText: cpu.toFixed(0) + '%',
          label: 'CPU' + (info.cpu_count ? ' × ' + info.cpu_count : ''),
          color: cpu > 85 ? ui.theme.error : ui.theme.accent,
        });
        ui.gauge({ x: 340, y: 280 }, 66, mem / 100, {
          valueText: mem.toFixed(0) + '%',
          label: '内存',
          color: mem > 90 ? ui.theme.error : ui.theme.ok,
        });
        ui.gauge({ x: 550, y: 280 }, 66, disk / 100, {
          valueText: disk.toFixed(0) + '%',
          label: '存储',
          color: disk > 92 ? ui.theme.error : ui.theme.warn,
        });
        ui.keyValue(40, 380, 300, '进程内存', formatNumber(info.process_memory_mb) + ' MB');
        ui.keyValue(360, 380, 280, '线程数', formatNumber(info.process_threads));
        ui.keyValue(40, 408, 300, '内存明细', formatNumber(info.mem_used_mb) + ' / ' + formatNumber(info.mem_total_mb) + ' MB');
        ui.keyValue(360, 408, 280, '磁盘占用', (info.disk_used_gb ?? 0).toFixed(1) + ' / ' + (info.disk_total_gb ?? 0).toFixed(1) + ' GB');

        ui.panel({ x: 676, y: 130, w: 328, h: 300 }, { title: '运行信息 / HOST' });
        ui.keyValue(696, 180, 288, '主机', String(info.hostname || '—'));
        ui.keyValue(696, 208, 288, '系统', String(info.os || '—'));
        ui.keyValue(696, 236, 288, 'Python', String(info.python_version || '—'));
        ui.keyValue(696, 264, 288, '进程 PID', String(info.pid ?? '—'));
        ui.keyValue(696, 292, 288, 'NeoBot 运行', formatDuration(ctx.shell.status.uptime_seconds));
        ui.keyValue(696, 320, 288, '负载', (info.load_average || []).map((value) => value.toFixed(2)).join(' / ') || '—');
        ui.sparkline({ x: 696, y: 350, w: 288, h: 60 }, history.slice(-80), {
          label: 'CPU 曲线',
          fill: true,
        });

        ui.panel({ x: 20, y: 446, w: 484, h: 108 }, { title: '后台任务 / TASKS' });
        const scheduled = tasks?.scheduled || [];
        const background = tasks?.background || [];
        ui.keyValue(40, 492, 444, '定时任务', String(scheduled.length) + ' 项');
        ui.keyValue(40, 522, 444, '后台作业', String(background.length) + ' 项');
        if (tasks?.scheduled_error) {
          ui.text(40, 546, '⚠ ' + tasks.scheduled_error, { size: 14, color: ui.theme.warn });
        }

        ui.panel({ x: 520, y: 446, w: 484, h: 108 }, { title: '宿主服务 / SERVICES' });
        const items = (services?.items || []).slice(0, 3);
        if (items.length === 0) {
          ui.text(540, 500, '服务注册表不可用', { size: 16, color: ui.theme.textDim });
        }
        items.forEach((item, index) => {
          ui.text(540, 494 + index * 24, (item.available === false ? '○ ' : '● ') + String(item.name || ''), {
            size: 16,
            color: item.available === false ? ui.theme.warn : ui.theme.ok,
          });
        });
        if (error) {
          ui.text(24, 128, '', { size: 12 });
        }
      },
    };
  },
};

// ---------------------------------------------------------------------------
// 能量分配：模型用量与开销
// ---------------------------------------------------------------------------

export const usageTerminal: TerminalDefinition = {
  id: 'usage',
  title: '能量分配',
  subtitle: '模型用量 · POWER GRID',
  accent: 0x7ce0ff,
  create(ctx: TerminalContext): TerminalController {
    const usage = hub<UsagePayload>();
    const series = hub<UsagePayload>();
    const pollers = [
      new Poller<UsagePayload>(
        () => ctx.host.consoleApi.get<UsagePayload>('/api/stats/usage?hours=24') as Promise<ApiResult<UsagePayload>>,
        20000,
        (data) => {
          usage.value = data;
          ctx.redraw();
        },
        (message) => {
          usage.error = message;
          ctx.redraw();
        },
      ),
      new Poller<UsagePayload>(
        () => ctx.host.consoleApi.get<UsagePayload>('/api/series/usage?hours=24&bucket=hour') as Promise<ApiResult<UsagePayload>>,
        30000,
        (data) => {
          series.value = data;
          ctx.redraw();
        },
      ),
    ];

    return {
      pollers,
      draw(ui: UiSurface) {
        const totals = usage.value?.totals || {};
        const points = series.value?.points || [];
        ui.panel({ x: 20, y: 130, w: 984, h: 190 }, { title: '总功率 / TOTALS' });
        ui.gauge({ x: 130, y: 230 }, 58, Math.min(1, Number(totals.calls || 0) / 200), {
          valueText: formatNumber(totals.calls),
          label: '调用次数',
        });
        ui.gauge({ x: 330, y: 230 }, 58, Math.min(1, Number(totals.input_tokens || 0) / 500000), {
          valueText: formatTokens(totals.input_tokens),
          label: '输入 Token',
          color: ui.theme.ok,
        });
        ui.gauge({ x: 530, y: 230 }, 58, Math.min(1, Number(totals.output_tokens || 0) / 200000), {
          valueText: formatTokens(totals.output_tokens),
          label: '输出 Token',
          color: ui.theme.warn,
        });
        ui.gauge({ x: 730, y: 230 }, 58, Math.min(1, Number(totals.cost_cny || 0) / 20), {
          valueText: formatCost(totals.cost_cny),
          label: '24h 花费',
          color: '#ff9ad5',
        });
        ui.sparkline({ x: 830, y: 170, w: 154, h: 120 }, points.map((point) => Number(point.cost_cny || 0)), {
          label: '开销曲线',
          fill: true,
          color: '#ff9ad5',
        });

        ui.panel({ x: 20, y: 336, w: 484, h: 218 }, { title: '按模块 / MODULES' });
        const modules = (usage.value?.items || []).slice(0, 7);
        if (modules.length === 0) {
          ui.text(44, 400, usage.value?.available === false ? '用量库不可用' : '24 小时内没有模型调用', {
            size: 17,
            color: ui.theme.textDim,
          });
        }
        modules.forEach((item, index) => {
          const y = 386 + index * 22;
          ui.text(44, y, String(item.module || '未知模块').slice(0, 18), { size: 16 });
          ui.text(300, y, formatNumber(item.calls) + ' 次', { size: 15, color: ui.theme.textDim });
          ui.text(484, y, formatCost(item.cost_cny), { size: 16, align: 'right', color: ui.theme.accent });
        });

        ui.panel({ x: 520, y: 336, w: 484, h: 218 }, { title: '按模型 / MODELS' });
        const models = (series.value?.models || []).slice(0, 7);
        if (models.length === 0) {
          ui.text(544, 400, '暂无模型用量明细', { size: 17, color: ui.theme.textDim });
        }
        models.forEach((item, index) => {
          const y = 386 + index * 22;
          const name = String(item.model_name || item.name || item.model || '未知模型');
          ui.text(544, y, name.slice(0, 22), { size: 16 });
          ui.text(784, y, formatTokens(Number(item.total_tokens || 0)), { size: 15, color: ui.theme.textDim });
          ui.text(984, y, formatCost(Number(item.cost_cny || 0)), { size: 16, align: 'right', color: ui.theme.accent });
        });
      },
    };
  },
};

// ---------------------------------------------------------------------------
// 模块机架：插件装载与启停（依赖体系在面板上同样可见）
// ---------------------------------------------------------------------------

export const pluginsTerminal: TerminalDefinition = {
  id: 'plugins',
  title: '模块机架',
  subtitle: '插件装载 · MODULE RACK',
  accent: 0x8affc8,
  decorate(group, materials) {
    for (let index = 0; index < 4; index += 1) {
      const rack = new THREE.Mesh(
        new THREE.BoxGeometry(0.28, 0.5, 0.36),
        materials.prop,
      );
      rack.position.set(-1.1 + index * 0.72, 2.3, -0.75);
      group.add(rack);
      const led = new THREE.Mesh(
        new THREE.BoxGeometry(0.16, 0.04, 0.02),
        materials.emissive,
      );
      led.position.set(-1.1 + index * 0.72, 2.5, -0.56);
      group.add(led);
    }
  },
  create(ctx: TerminalContext): TerminalController {
    let payload: PluginListPayload | null = null;
    let error: string | null = null;
    let selected = '';
    let busy = false;
    const pollers = [
      new Poller<PluginListPayload>(
        () => ctx.host.consoleApi.get<PluginListPayload>('/api/plugins') as Promise<ApiResult<PluginListPayload>>,
        12000,
        (data) => {
          payload = data;
          if (typeof data.manage_enabled === 'boolean') ctx.shell.setManageEnabled(data.manage_enabled);
          if (!selected && (data.items || []).length > 0) selected = String((data.items || [])[0].id || '');
          ctx.redraw();
        },
        (message) => {
          error = message;
          ctx.redraw();
        },
      ),
    ];

    async function operate(name: string, action: 'toggle' | 'reload'): Promise<void> {
      const item = (payload?.items || []).find((entry) => entry.id === name);
      const enable = item ? !item.enabled : true;
      const confirmed = await ctx.confirm({
        title: action === 'toggle' ? (enable ? '启用模块 ' + name : '停用模块 ' + name) : '重载模块 ' + name,
        body:
          action === 'toggle'
            ? enable
              ? '模块会立即装载并启动。'
              : '模块会立即停止；依赖它的模块会被联动停用（前置插件满足后会自动恢复）。'
            : '模块会重新导入并重启，期间它的功能短暂不可用。',
        confirmLabel: action === 'toggle' ? (enable ? '启用' : '停用') : '重载',
        danger: action === 'toggle' && !enable,
      });
      if (!confirmed) return;
      busy = true;
      ctx.redraw();
      const result = await ctx.host.consoleApi.post<SimpleMessage>(
        '/api/plugins/' + encodeURIComponent(name) + '/' + action,
        {},
      );
      busy = false;
      if (result.ok) ctx.toast(result.data?.message || '操作完成', 'ok');
      else ctx.toast(failMessage(result), 'error');
      void pollers[0].tick();
      ctx.redraw();
    }

    return {
      pollers,
      draw(ui: UiSurface) {
        const items = payload?.items || [];
        ui.panel({ x: 20, y: 130, w: 520, h: 424 }, { title: '模块清单 / MODULES (' + items.length + ')' });
        const listItems = items.map((item) => ({
          label: item.name + (item.official ? ' · 官方' : ''),
          sub:
            'v' + String(item.version || '?') +
            (item.auto_disabled ? ' · 依赖未满足' : '') +
            (item.dependency_issues && item.dependency_issues.length > 0 ? ' · ' + item.dependency_issues[0] : ''),
          badge: item.status === 'running' ? '运行中' : item.enabled === false ? '已停用' : item.status || '',
          tone:
            item.status === 'running'
              ? ui.theme.ok
              : item.auto_disabled
                ? ui.theme.warn
                : item.status === 'error'
                  ? ui.theme.error
                  : ui.theme.textDim,
          active: item.id === selected,
        }));
        const clicked = ui.list('plugins', { x: 36, y: 168, w: 488, h: 372 }, listItems, { rowHeight: 46 });
        if (clicked >= 0 && items[clicked]) selected = String(items[clicked].id || '');

        const current = items.find((item) => item.id === selected) || items[0];
        ui.panel({ x: 556, y: 130, w: 448, h: 424 }, { title: '模块详情 / DETAIL' });
        if (!current) {
          ui.text(580, 200, '没有可显示的模块', { size: 18, color: ui.theme.textDim });
        } else {
          ui.text(580, 186, current.name, { size: 26, weight: 'bold' });
          ui.text(580, 214, current.description || '（无描述）', { size: 15, color: ui.theme.textDim, maxWidth: 400 });
          ui.keyValue(580, 252, 400, '版本', String(current.version || '—'));
          ui.keyValue(580, 276, 400, '状态', String(current.status || '—'));
          ui.keyValue(580, 300, 400, '作者', String(current.author || '—'));
          ui.keyValue(580, 324, 400, '热重载', current.hot_reload === false ? '不支持' : '支持');
          if (current.dependencies && current.dependencies.length > 0) {
            ui.keyValue(580, 348, 400, '前置插件', current.dependencies.join(', '));
          }
          if (current.dependents && current.dependents.length > 0) {
            ui.keyValue(580, 372, 400, '被依赖', current.dependents.join(', '));
          }
          if (current.disabled_reason) {
            ui.text(580, 402, '⚠ ' + current.disabled_reason, { size: 14, color: ui.theme.warn, maxWidth: 400 });
          }
          if (current.dependency_issues && current.dependency_issues.length > 0) {
            ui.text(580, 424, '未满足：' + current.dependency_issues.join('；'), {
              size: 14,
              color: ui.theme.warn,
              maxWidth: 400,
            });
          }
          const readOnly = ctx.shell.availability('plugins').readOnly || busy;
          if (ui.button('toggle', { x: 580, y: 452, w: 190, h: 52 }, current.enabled === false ? '装载模块' : '停用模块', {
            disabled: readOnly,
            tone: current.enabled === false ? ui.theme.ok : ui.theme.warn,
          })) {
            void operate(String(current.id), 'toggle');
          }
          if (ui.button('reload', { x: 786, y: 452, w: 198, h: 52 }, busy ? '执行中…' : '热重载', {
            disabled: readOnly || current.official === true,
            tone: ui.theme.accent,
          })) {
            void operate(String(current.id), 'reload');
          }
          ui.text(580, 528, '依赖未满足的模块会被自动停用，前置插件恢复后自动装载。', {
            size: 14,
            color: ui.theme.textDim,
            maxWidth: 400,
          });
        }
        if (error) {
          ui.text(24, 120, '⚠ ' + error, { size: 15, color: ui.theme.error });
        }
      },
    };
  },
};

interface Hub<T> {
  value: T | null;
  error: string | null;
  updatedAt: number;
}

function hub<T>(): Hub<T> {
  return { value: null, error: null, updatedAt: 0 };
}

export const engineeringTerminals: TerminalDefinition[] = [
  systemTerminal,
  usageTerminal,
  pluginsTerminal,
];
