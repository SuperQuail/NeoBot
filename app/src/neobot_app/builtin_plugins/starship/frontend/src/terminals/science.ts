// terminals/science.ts —— 科学舱/档案舱/指挥室终端：航行日志、神经矩阵、舰载系统配置。

import * as THREE from 'three';

import { Poller, type ApiResult } from '../net/api';
import type { TerminalContext, TerminalController, TerminalDefinition } from '../ui/terminal';
import type { UiSurface } from '../ui/surface';
import {
  failMessage,
  formatClock,
  type ConfigDocument,
  type FieldDescriptor,
  type LogItem,
  type LogPayload,
  type PromptAnalysisItem,
  type PromptAnalysisPayload,
  type SimpleMessage,
} from './shared';

interface EnvPayload {
  revision?: number;
  items?: Array<{ key?: string; value?: string; masked?: boolean; configured?: boolean; description?: string }>;
  entries?: Array<{ key?: string; value?: string; masked?: boolean; configured?: boolean }>;
  keys?: string[];
  [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// 航行日志
// ---------------------------------------------------------------------------

export const logsTerminal: TerminalDefinition = {
  id: 'logs',
  title: '航行日志',
  subtitle: '实时日志 · SHIP LOG',
  accent: 0x9fd4ff,
  create(ctx: TerminalContext): TerminalController {
    let items: LogItem[] = [];
    let error: string | null = null;
    let levelFilter = 'ALL';
    const levels = ['ALL', 'INFO', 'WARNING', 'ERROR', 'DEBUG'];
    let follow = true;
    const pollers = [
      new Poller<LogPayload>(
        () => ctx.host.consoleApi.get<LogPayload>('/api/logs?limit=120') as Promise<ApiResult<LogPayload>>,
        4000,
        (data) => {
          items = data.items || [];
          ctx.redraw();
        },
        (message) => {
          error = message;
          ctx.redraw();
        },
      ),
    ];
    return {
      pollers,
      draw(ui: UiSurface) {
        ui.panel({ x: 20, y: 130, w: 984, h: 424 }, { title: '日志流 / STREAM' });
        levels.forEach((level, index) => {
          if (ui.button('lv-' + level, { x: 40 + index * 96, y: 164, w: 88, h: 32 }, level, {
            tone: levelFilter === level ? ui.theme.accent : ui.theme.textDim,
            size: 15,
          })) {
            levelFilter = level;
            ui.scrollReset('logs');
          }
        });
        if (ui.button('follow', { x: 856, y: 164, w: 128, h: 32 }, follow ? '自动滚动：开' : '自动滚动：关', {
          tone: follow ? ui.theme.ok : ui.theme.textDim,
          size: 15,
        })) {
          follow = !follow;
        }
        const filtered = items.filter((item) => {
          if (levelFilter === 'ALL') return true;
          return String(item.level || '').toUpperCase().startsWith(levelFilter.slice(0, 4));
        });
        const listItems = filtered
          .slice()
          .reverse()
          .map((item) => ({
            label: '[' + formatClock(item.time || item.datetime) + '] ' + String(item.message || '').slice(0, 68),
            sub: String(item.module || '') + ' · ' + String(item.level || '').toLowerCase(),
            tone:
              String(item.level || '').toUpperCase().startsWith('ERR')
                ? ui.theme.error
                : String(item.level || '').toUpperCase().startsWith('WARN')
                  ? ui.theme.warn
                  : undefined,
          }));
        const clicked = ui.list('logs', { x: 36, y: 206, w: 952, h: 330 }, listItems, { rowHeight: 40 });
        if (clicked >= 0) {
          const entry = filtered.slice().reverse()[clicked];
          if (entry) ctx.toast(String(entry.module || '') + ': ' + String(entry.message || ''), 'info');
        }
        ui.text(24, 574, '共 ' + String(filtered.length) + ' 条 · 点击条目可在舰桥广播完整内容', {
          size: 14,
          color: ui.theme.textDim,
        });
        if (error) ui.text(700, 574, '⚠ ' + error, { size: 14, color: ui.theme.error });
      },
    };
  },
};

// ---------------------------------------------------------------------------
// 神经矩阵：提示词与 Agent 分析
// ---------------------------------------------------------------------------

export const analysisTerminal: TerminalDefinition = {
  id: 'analysis',
  title: '神经矩阵',
  subtitle: '提示词分析 · NEURAL MATRIX',
  accent: 0xff8ad8,
  decorate(group) {
    for (let index = 0; index < 3; index += 1) {
      const ring = new THREE.Mesh(
        new THREE.TorusGeometry(0.5 + index * 0.18, 0.02, 6, 40),
        new THREE.MeshBasicMaterial({
          color: 0xff8ad8,
          transparent: true,
          opacity: 0.5 - index * 0.1,
        }),
      );
      ring.position.set(0, 2.5, -0.9);
      ring.rotation.x = Math.PI / 2 + index * 0.4;
      group.add(ring);
    }
  },
  create(ctx: TerminalContext): TerminalController {
    let report: PromptAnalysisPayload | null = null;
    let error: string | null = null;
    let selected = 0;
    const pollers = [
      new Poller<PromptAnalysisPayload>(
        () => ctx.host.consoleApi.get<PromptAnalysisPayload>('/api/analysis/prompts') as Promise<ApiResult<PromptAnalysisPayload>>,
        30000,
        (data) => {
          report = data;
          ctx.redraw();
        },
        (message) => {
          error = message;
          ctx.redraw();
        },
      ),
    ];
    return {
      pollers,
      draw(ui: UiSurface) {
        const sources = collectSources(report);
        ui.panel({ x: 20, y: 130, w: 430, h: 424 }, { title: '分析对象 / SOURCES (' + sources.length + ')' });
        const listItems = sources.map((item) => ({
          label: String(item.name || item.label || item.key || item.agent || '未命名'),
          sub: '约 ' + String(Math.round(Number(item.tokens ?? item.estimated_tokens ?? 0))) + ' tokens · ' + String(item.chars ?? 0) + ' 字符',
          active: sources[selected] === item,
        }));
        const clicked = ui.list('analysis', { x: 36, y: 168, w: 398, h: 370 }, listItems, { rowHeight: 44 });
        if (clicked >= 0) selected = clicked;

        ui.panel({ x: 466, y: 130, w: 538, h: 424 }, { title: '矩阵详情 / DETAIL' });
        const current = sources[selected];
        if (!current) {
          ui.text(490, 200, error ? '⚠ ' + error : '等待分析数据…', {
            size: 18,
            color: error ? ui.theme.error : ui.theme.textDim,
          });
        } else {
          ui.text(490, 190, String(current.name || current.label || current.key || '未命名'), {
            size: 26,
            weight: 'bold',
          });
          const tokens = Number(current.tokens ?? current.estimated_tokens ?? 0);
          ui.gauge({ x: 590, y: 300 }, 62, Math.min(1, tokens / 8000), {
            valueText: Math.round(tokens) + '',
            label: '估算 tokens',
          });
          ui.keyValue(700, 250, 284, '字符数', String(current.chars ?? 0));
          ui.keyValue(700, 278, 284, '估算 tokens', String(Math.round(tokens)));
          ui.keyValue(700, 306, 284, '来源', String(current.agent || current.key || '—'));
          const sections = (current.sections || []).slice(0, 6);
          if (sections.length === 0) {
            ui.text(490, 400, '没有分段信息（该来源不提供分段统计）', { size: 15, color: ui.theme.textDim });
          }
          sections.forEach((section, index) => {
            const y = 396 + index * 24;
            ui.text(490, y, String(section.name || '段落'), { size: 15, color: ui.theme.textDim });
            ui.text(960, y, String(Math.round(Number(section.tokens ?? 0))) + ' tok', { size: 15, align: 'right' });
          });
          ui.text(490, 540, '提示词分析不调用模型，仅统计装配后的字符与估算 token。', {
            size: 14,
            color: ui.theme.textDim,
            maxWidth: 480,
          });
        }
      },
    };
  },
};

function collectSources(report: PromptAnalysisPayload | null): PromptAnalysisItem[] {
  if (!report) return [];
  if (Array.isArray(report.items)) return report.items;
  if (Array.isArray(report.sources)) return report.sources;
  const collected: PromptAnalysisItem[] = [];
  for (const [key, value] of Object.entries(report)) {
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      const entry = value as Record<string, unknown>;
      if (typeof entry.chars === 'number' || typeof entry.tokens === 'number' || Array.isArray(entry.sections)) {
        collected.push({ key, name: String(entry.name || key), ...(entry as object) } as PromptAnalysisItem);
      }
    }
  }
  return collected;
}

// ---------------------------------------------------------------------------
// 舰载系统配置
// ---------------------------------------------------------------------------

export const configTerminal: TerminalDefinition = {
  id: 'config',
  title: '舰载系统配置',
  subtitle: '本体配置 · SHIP CONFIG',
  accent: 0x8fb8ff,
  create(ctx: TerminalContext): TerminalController {
    let document: ConfigDocument | null = null;
    let env: EnvPayload | null = null;
    let error: string | null = null;
    let openSection = '';
    let busy = false;
    let editing: { path: string; value: string } | null = null;

    const pollers = [
      new Poller<ConfigDocument>(
        () => ctx.host.consoleApi.get<ConfigDocument>('/api/config') as Promise<ApiResult<ConfigDocument>>,
        20000,
        (data) => {
          document = data;
          ctx.redraw();
        },
        (message) => {
          error = message;
          ctx.redraw();
        },
      ),
      new Poller<EnvPayload>(
        () => ctx.host.consoleApi.get<EnvPayload>('/api/config/env') as Promise<ApiResult<EnvPayload>>,
        30000,
        (data) => {
          env = data;
          ctx.redraw();
        },
      ),
    ];

    const sections = (): FieldDescriptor[] => (document?.schema || []).filter((field) => field.kind === 'group');

    async function saveValue(path: string[], value: unknown): Promise<void> {
      if (!document) return;
      const draft = JSON.parse(JSON.stringify(document.config || {})) as Record<string, unknown>;
      let cursor: Record<string, unknown> = draft;
      for (let index = 0; index < path.length - 1; index += 1) {
        const key = path[index];
        const next = cursor[key];
        if (!next || typeof next !== 'object') cursor[key] = {};
        cursor = cursor[key] as Record<string, unknown>;
      }
      cursor[path[path.length - 1]] = value;
      busy = true;
      ctx.redraw();
      const result = await ctx.host.consoleApi.post<ConfigDocument>('/api/config', {
        revision: document.revision,
        config: draft,
      });
      busy = false;
      if (result.ok) {
        document = result.data || document;
        ctx.toast(result.data?.message || '配置已写入 config.toml', 'ok');
        void pollers[0].tick();
      } else {
        ctx.toast(failMessage(result), 'error');
      }
      ctx.redraw();
    }

    function parseValue(raw: string, type?: string): unknown {
      if (type === 'bool' || type === 'boolean') return raw === 'true' || raw === '是' || raw === '1';
      if (type === 'int' || type === 'integer') return Number.parseInt(raw, 10);
      if (type === 'float' || type === 'number') return Number.parseFloat(raw);
      const trimmed = raw.trim();
      if (trimmed.startsWith('[') || trimmed.startsWith('{')) {
        try {
          return JSON.parse(trimmed);
        } catch {
          return raw;
        }
      }
      return raw;
    }

    return {
      pollers,
      draw(ui: UiSurface) {
        const groups = sections();
        ui.panel({ x: 20, y: 130, w: 320, h: 424 }, { title: '分区 / SECTIONS (' + groups.length + ')' });
        const listItems = groups.map((group) => ({
          label: String(group.name || (group.path || []).join('.')),
          sub: String(group.description || '').slice(0, 22) || 'config.toml',
          active: openSection === String(group.name),
        }));
        const clicked = ui.list('config-sections', { x: 36, y: 168, w: 288, h: 370 }, listItems, { rowHeight: 46 });
        if (clicked >= 0 && groups[clicked]) openSection = String(groups[clicked].name || '');

        const readOnly = ctx.shell.availability('config').readOnly;
        ui.panel({ x: 356, y: 130, w: 648, h: 424 }, { title: '参数 / PARAMETERS' });
        void env;
        const group = groups.find((item) => String(item.name) === openSection) || groups[0];
        if (!group) {
          ui.text(380, 200, error ? '⚠ ' + error : '正在读取 config.toml…', {
            size: 18,
            color: error ? ui.theme.error : ui.theme.textDim,
          });
        } else {
          openSection = String(group.name || '');
          const fields = (group.fields || []).filter((field) => !field.hidden).slice(0, 9);
          ui.text(380, 176, String(group.name || '') + '  ·  ' + String(group.description || ''), {
            size: 17,
            color: ui.theme.textDim,
            maxWidth: 600,
          });
          fields.forEach((field, index) => {
            const y = 216 + index * 40;
            const hovered = ui.isHovered('field-' + index);
            void hovered;
            const label = String(field.name || '');
            const value = field.value;
            const text =
              value === undefined || value === null
                ? '（未设置）'
                : typeof value === 'object'
                  ? JSON.stringify(value).slice(0, 26)
                  : String(value);
            const rect = { x: 380, y: y - 20, w: 600, h: 34 };
            const fieldState = ui.textField('field-' + index, rect, label + '  =  ' + text, {
              placeholder: label,
              focused: editing !== null && editing.path === (field.path || []).join('.'),
            });
            if (fieldState.clicked && !readOnly && field.kind === 'scalar') {
              const path = field.path || [String(field.name)];
              editing = { path: path.join('.'), value: value === undefined || value === null ? '' : String(value) };
              ctx.host.textCapture.open({
                initial: editing.value,
                onType: (text) => {
                  if (editing) editing.value = text;
                  ctx.redraw();
                },
                onCommit: (text) => {
                  editing = null;
                  void saveValue(path, parseValue(text, String(field.type || '')));
                },
                onCancel: () => {
                  editing = null;
                  ctx.redraw();
                },
              });
            }
          });
          // 危险/全局操作：与面板一致，保留写操作但都走二次确认
          if (ui.button('config-reload', { x: 380, y: 496, w: 170, h: 44 }, busy ? '执行中…' : '重载配置', {
            disabled: busy,
            tone: ui.theme.accent,
            size: 16,
          })) {
            void (async () => {
              const ok = await ctx.confirm({
                title: '重载运行配置',
                body: '按磁盘上的 config.toml 重新装配运行期组件（等价于面板的「重载运行配置」）。',
                confirmLabel: '重载',
              });
              if (!ok) return;
              busy = true;
              ctx.redraw();
              const result = await ctx.host.consoleApi.post<{ message?: string }>('/api/config/reload', {});
              busy = false;
              ctx.toast(result.ok ? result.data?.message || '配置已重载' : failMessage(result), result.ok ? 'ok' : 'error');
              void pollers[0].tick();
              ctx.redraw();
            })();
          }
          if (ui.button('env-open', { x: 560, y: 496, w: 200, h: 44 }, '环境变量密钥', { size: 16 })) {
            const keys = collectEnvKeys(env);
            ctx.toast(
              keys.length > 0
                ? '已配置 ' + keys.length + ' 个密钥：' + keys.slice(0, 6).join('、') + '（Key 只写不读，需在面板编辑）'
                : '尚未配置任何 API 密钥',
              'info',
            );
          }
          if (readOnly) {
            ui.text(380, 476, '当前为只读模式：无法保存配置', { size: 15, color: ui.theme.warn });
          } else {
            ui.text(380, 552, '点击任意参数行即可修改；保存会写入 config.toml 并做一次校验。', {
              size: 14,
              color: ui.theme.textDim,
              maxWidth: 600,
            });
          }
        }
      },
    };
  },
};

function collectEnvKeys(payload: EnvPayload | null): string[] {
  if (!payload) return [];
  const items = payload.items || payload.entries || [];
  const keys = items
    .map((item) => String(item.key || ''))
    .filter((key) => key.length > 0);
  if (keys.length > 0) return keys;
  if (Array.isArray(payload.keys)) return payload.keys.map((key) => String(key));
  return [];
}

export const scienceTerminals: TerminalDefinition[] = [logsTerminal, analysisTerminal, configTerminal];
