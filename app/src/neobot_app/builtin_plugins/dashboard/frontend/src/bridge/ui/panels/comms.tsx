// comms.tsx —— 航行日志（对应 2D 面板 pages/Logs.tsx）
//
// 增量流式读取：首次 /api/logs 拉全量，之后按 last_id 走 /api/logs?since=… 只取新增，
// 因此长时间开着终端也不会重复拉取历史。过滤（级别/模块/文本）只在本地做，不影响抓取。
// 轮询节奏可由用户在状态条切换；暂停跟随后新日志只累加待看计数，不打断阅读位置。

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent, ReactNode } from 'react';
import { api } from '../../../api/endpoints';
import type { LogItem, LogPayload } from '../../../api/types';
import { mapTag } from '../../../utils/format';
import Icon from '../../../components/Icon';
import { sfx } from '../../core/sound';
import type { PanelProps } from './index';

const MAX_ROWS = 2000;
const NEAR_BOTTOM = 12;

const LEVELS: Array<{ key: string; label: string }> = [
  { key: 'info', label: 'INFO' },
  { key: 'ok', label: 'SUCCESS' },
  { key: 'warn', label: 'WARNING' },
  { key: 'err', label: 'ERROR' },
];

/** 抓取节奏（0 = 暂停自动抓取，仍可手动刷新） */
const REFRESH_CHOICES: Array<[number, string]> = [
  [0, '暂停抓取'],
  [1500, '1.5 秒'],
  [3000, '3 秒'],
  [10000, '10 秒'],
];

function clockOf(ms: number): string {
  if (!ms) return '—';
  return new Date(ms).toLocaleTimeString('zh-CN', { hour12: false });
}

function play(effect: keyof typeof sfx): void {
  try {
    sfx[effect]();
  } catch {
    // 音频不可用不影响面板功能
  }
}

/**
 * 面板内键盘：Esc 断开终端、R 刷新。
 * 终端外框（engine）已在 window 捕获阶段接管这两个键，因此这里不注册全局监听，
 * 只处理落在面板子树内的按键（输入框里的 Esc 同样有效）。
 */
function usePanelKeys(onClose: () => void, onRefresh: () => void) {
  const handlers = useRef({ onClose, onRefresh });
  handlers.current = { onClose, onRefresh };
  return useCallback((event: ReactKeyboardEvent<HTMLElement>) => {
    if (event.key === 'Escape') {
      if (document.querySelector('[role="dialog"][aria-modal="true"]')) return;
      handlers.current.onClose();
      return;
    }
    if (event.key !== 'r' && event.key !== 'R') return;
    if (event.ctrlKey || event.metaKey || event.altKey) return;
    const target = event.target;
    if (target instanceof HTMLElement && target.closest('input, textarea, select, [contenteditable="true"]'))
      return;
    handlers.current.onRefresh();
  }, []);
}

/** 关键词高亮：先转义正则元字符，再按大小写不敏感切分 */
function highlight(text: string | undefined, keyword: string): ReactNode {
  const source = String(text ?? '');
  if (!keyword) return source;
  const re = new RegExp(keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
  const out: ReactNode[] = [];
  let last = 0;
  let index = 0;
  let match = re.exec(source);
  while (match !== null) {
    if (match.index > last) out.push(source.slice(last, match.index));
    out.push(
      <span className="bp-log-mark" key={index}>
        {match[0]}
      </span>,
    );
    index += 1;
    last = match.index + match[0].length;
    if (match.index === re.lastIndex) re.lastIndex += 1;
    match = re.exec(source);
  }
  if (last < source.length) out.push(source.slice(last));
  return out;
}

export default function CommsPanel({ station, onClose, refreshToken }: PanelProps) {
  const [rows, setRows] = useState<LogItem[]>([]);
  const [levelOn, setLevelOn] = useState<Record<string, boolean>>({
    info: true,
    ok: true,
    warn: true,
    err: true,
  });
  const [moduleFilter, setModuleFilter] = useState('');
  const [textFilter, setTextFilter] = useState('');
  const [following, setFollowing] = useState(true);
  const [pendingNew, setPendingNew] = useState(0);
  const [refreshMs, setRefreshMs] = useState(1500);
  const [busy, setBusy] = useState(false);
  const [link, setLink] = useState<'ok' | 'busy' | 'err'>('busy');
  const [updatedAt, setUpdatedAt] = useState(0);

  const lastIdRef = useRef(0);
  const aliveRef = useRef(true);
  const followingRef = useRef(true);
  const viewportRef = useRef<HTMLDivElement | null>(null);
  followingRef.current = following;

  useEffect(
    () => () => {
      aliveRef.current = false;
    },
    [],
  );

  /** 已知模块（用于下拉过滤）：只反映当前缓冲区里出现过的模块 */
  const modules = useMemo(() => {
    const names = new Set<string>();
    for (const row of rows) if (row.module) names.add(row.module);
    return Array.from(names).sort();
  }, [rows]);

  const passes = useCallback(
    (row: LogItem) => {
      if (!levelOn[mapTag(row.level)]) return false;
      if (moduleFilter && row.module !== moduleFilter) return false;
      if (textFilter) {
        const haystack = `${row.message || ''} ${row.module || ''}`.toLowerCase();
        if (!haystack.includes(textFilter)) return false;
      }
      return true;
    },
    [levelOn, moduleFilter, textFilter],
  );

  const visible = useMemo(() => {
    const filtered = rows.filter(passes);
    return filtered.length > MAX_ROWS ? filtered.slice(-MAX_ROWS) : filtered;
  }, [rows, passes]);

  const levelCounts = useMemo(() => {
    const counts: Record<string, number> = { info: 0, ok: 0, warn: 0, err: 0 };
    for (const row of rows) {
      const key = mapTag(row.level);
      counts[key] = (counts[key] || 0) + 1;
    }
    return counts;
  }, [rows]);

  /** 合并一次接口结果；replace=true 表示这是全量快照（首读或手动重读） */
  const applyPayload = useCallback((payload: LogPayload, replace: boolean) => {
    const items = payload.items || [];
    if (payload.last_id) lastIdRef.current = payload.last_id;
    else if (items.length) lastIdRef.current = items[items.length - 1].id ?? lastIdRef.current;
    if (items.length === 0 && !replace) return;
    setRows((previous) => {
      const merged = replace ? items : [...previous, ...items];
      return merged.length > MAX_ROWS * 2 ? merged.slice(-MAX_ROWS) : merged;
    });
    // 暂停跟随期间只累计提示数量，不打断用户正在看的位置
    if (!replace && items.length > 0 && !followingRef.current) setPendingNew((count) => count + items.length);
  }, []);

  /** 抓取一次：没有游标（或显式要求）时拉全量，否则只取新增 */
  const pull = useCallback(
    async (forceFull = false) => {
      setBusy(true);
      const full = forceFull || lastIdRef.current === 0;
      const payload = full ? await api.logs(500) : await api.logsSince(lastIdRef.current, 500);
      if (!aliveRef.current) return;
      setBusy(false);
      if (!payload) {
        // 客户端在 401 时会清 token 并跳登录页；这里只标记链路中断，不再渲染新数据
        setLink('err');
        return;
      }
      setLink('ok');
      setUpdatedAt(Date.now());
      applyPayload(payload, full);
    },
    [applyPayload],
  );

  useEffect(() => {
    void pull(true);
  }, [pull]);

  // 增量轮询：节奏跟随状态条选择；0 表示只手动刷新
  useEffect(() => {
    if (refreshMs === 0) return undefined;
    const timer = setInterval(() => void pull(false), refreshMs);
    return () => clearInterval(timer);
  }, [pull, refreshMs]);

  const refreshNow = useCallback(() => {
    play('beep');
    void pull(false);
  }, [pull]);

  // 外框的「刷新」按钮只递增 refreshToken：按变化补抓一次增量即可
  const tokenRef = useRef(refreshToken);
  useEffect(() => {
    if (tokenRef.current === refreshToken) return;
    tokenRef.current = refreshToken;
    void pull(false);
  }, [refreshToken, pull]);

  const onPanelKeyDown = usePanelKeys(onClose, refreshNow);

  useLayoutEffect(() => {
    const element = viewportRef.current;
    if (element && following) element.scrollTop = element.scrollHeight;
  }, [visible, following]);

  const onScroll = () => {
    const element = viewportRef.current;
    if (!element) return;
    const atBottom = element.scrollTop + element.clientHeight >= element.scrollHeight - NEAR_BOTTOM;
    if (atBottom && !followingRef.current) {
      setFollowing(true);
      setPendingNew(0);
    } else if (!atBottom && followingRef.current) {
      setFollowing(false);
    }
  };

  const resume = () => {
    play('beep');
    setFollowing(true);
    setPendingNew(0);
  };

  const toggleFollow = () => {
    play('beep');
    setFollowing((previous) => !previous);
    setPendingNew(0);
  };

  const clearBuffer = () => {
    play('beep');
    setRows([]);
    setPendingNew(0);
  };

  const download = () => {
    play('beep');
    const lines = rows
      .filter(passes)
      .map(
        (row) =>
          `[${row.datetime || row.time}] [${(row.level || '').toUpperCase()}] [${row.module || '-'}] ${row.message}`,
      );
    try {
      const blob = new Blob([lines.join('\n')], { type: 'text/plain;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `neobot-${new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)}.log`;
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      URL.revokeObjectURL(url);
    } catch {
      // 浏览器不支持 Blob 下载时静默（面板其余功能不受影响）
    }
  };

  const linkText = link === 'err' ? '日志链路中断' : busy ? '正在抓取…' : '接收中';

  return (
    // 面板根节点只在「焦点位于终端内部」时兜底处理 Esc/R：外框（TerminalFrame）已在 window 捕获阶段
    // 接管 Esc 并阻止冒泡，因此这里不会重复触发；面板被直接挂载（测试/单独打开）时它才是唯一入口。
    // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions
    <section
      className="bp-panel"
      aria-label={`${station.terminal} ${station.title}`}
      onKeyDown={onPanelKeyDown}
    >
      {/* 抬头（编号 / 终端名 / 中文标题）由外框 TerminalFrame 渲染，面板内只保留动作按钮 */}
      <div className="bp-head-actions">
        <span className={`bp-pill ${following ? 'ok' : 'warn'}`}>{following ? '实时跟随' : '已暂停'}</span>
        <button className="btn-sm" onClick={download} aria-label="下载当前过滤结果">
          <Icon name="download" size={14} /> 下载
        </button>
        <button className="btn-sm" onClick={clearBuffer} aria-label="清空缓冲区">
          <Icon name="trash" size={14} /> 清屏
        </button>
        <button className="btn-sm" onClick={onClose} aria-label="断开终端">
          断开终端
        </button>
      </div>

      <div className="bp-status" role="status" aria-live="polite">
        <span className={`bp-link ${link === 'err' ? 'err' : busy ? 'busy' : 'ok'}`}>
          <i className="bp-dot" />
          {linkText}
        </span>
        <span className="bp-status-item">末次抓取 {clockOf(updatedAt)}</span>
        <span className="bp-status-item">游标 last_id {lastIdRef.current || '—'}</span>
        <button className="btn-sm" onClick={refreshNow} disabled={busy} aria-label="刷新数据">
          <Icon name="refresh" size={14} /> 刷新
        </button>
        <label className="bp-status-item">
          抓取间隔
          <select
            className="input bp-select"
            aria-label="自动刷新间隔"
            value={refreshMs}
            onChange={(event) => setRefreshMs(Number(event.target.value))}
          >
            {REFRESH_CHOICES.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="bp-body">
        <div className="bp-toolbar">
          <div className="bp-toolbar-group" role="group" aria-label="日志级别过滤">
            {LEVELS.map((level) => (
              <button
                key={level.key}
                type="button"
                className={`level-pill ${level.key}${levelOn[level.key] ? ' active' : ''}`}
                aria-pressed={levelOn[level.key]}
                aria-label={level.label}
                onClick={() => {
                  play('beep');
                  setLevelOn((previous) => ({ ...previous, [level.key]: !previous[level.key] }));
                }}
              >
                {level.label}
                <span aria-hidden="true"> {levelCounts[level.key] || 0}</span>
              </button>
            ))}
          </div>
          <label className="bp-field" style={{ minWidth: 150 }}>
            <span>模块</span>
            <select
              className="input"
              aria-label="模块过滤"
              value={moduleFilter}
              onChange={(event) => setModuleFilter(event.target.value)}
            >
              <option value="">全部模块</option>
              {modules.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <label className="bp-field" style={{ minWidth: 200 }}>
            <span>文本搜索</span>
            <input
              className="input"
              aria-label="搜索日志"
              placeholder="搜索日志内容…"
              value={textFilter}
              onChange={(event) => setTextFilter(event.target.value.trim().toLowerCase())}
            />
          </label>
          <span className="bp-spacer" />
          <button className="btn-sm" aria-pressed={!following} onClick={toggleFollow}>
            <Icon name={following ? 'pause' : 'play'} size={14} />
            {following ? '暂停跟随' : '恢复跟随'}
          </button>
          {!following && pendingNew > 0 && (
            <button className="btn-sm primary" onClick={resume}>
              ↓ {pendingNew} 条新日志
            </button>
          )}
        </div>

        {link === 'err' && rows.length === 0 && (
          <div className="bp-alert err" role="alert">
            无法读取日志（/api/logs 返回空）：可能未登录或后端未就绪。
            <button className="btn-sm" onClick={refreshNow}>
              重试
            </button>
          </div>
        )}

        <div className="bp-log-viewport" ref={viewportRef} onScroll={onScroll} role="log" aria-label="日志流">
          {visible.length === 0 && <div className="bp-empty">暂无日志</div>}
          {visible.map((row, index) => (
            <div
              className="bp-log-row"
              key={row.id ?? `${row.time}-${index}`}
              title={row.datetime || row.time}
            >
              <span className="bp-log-time">{row.time}</span>
              <span className={`bp-log-level ${mapTag(row.level)}`}>{row.level}</span>
              <span className="bp-log-msg">
                <span className="bp-log-module">[{row.module || '—'}]</span>{' '}
                {highlight(row.message, textFilter)}
              </span>
            </div>
          ))}
        </div>

        <div className="bp-toolbar" style={{ marginTop: 10, marginBottom: 0 }}>
          <span className="bp-metric-src">
            显示 {visible.length} / 缓冲 {rows.length} 条（上限 {MAX_ROWS}）
          </span>
          <span className="bp-spacer" />
          {following ? (
            <span className="bp-pill ok">实时跟随</span>
          ) : (
            <span className="bp-pill warn">已暂停{pendingNew > 0 ? ` · 新增 ${pendingNew}` : ''}</span>
          )}
        </div>
      </div>
    </section>
  );
}
