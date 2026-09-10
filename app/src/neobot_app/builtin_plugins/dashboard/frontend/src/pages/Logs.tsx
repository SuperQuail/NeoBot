// Logs.jsx —— 完整日志查看器(移植自旧 logsPage.js)
// 级别过滤 + 模块过滤 + 文本搜索(高亮)+ 实时增量拉取 + tail 跟随 + 下载 + 清屏
import { useState, useEffect, useRef, useMemo, useCallback, useLayoutEffect } from 'react';
import type { ReactNode } from 'react';
import { api } from '../api/endpoints';
import type { LogItem } from '../api/types';
import { mapTag } from '../utils/format';

const MAX_ROWS = 2000;
const POLL_MS = 1500;
const NEAR_BOTTOM = 12;

const LEVELS = [
  { key: 'info', label: 'INFO' },
  { key: 'ok', label: 'SUCCESS' },
  { key: 'warn', label: 'WARNING' },
  { key: 'err', label: 'ERROR' },
];

// 文本高亮 → 返回 JSX 数组
function highlight(text?: string, kw?: string): ReactNode {
  text = String(text ?? '');
  if (!kw) return text;
  const re = new RegExp(kw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
  const out: ReactNode[] = [];
  let last = 0,
    m: RegExpExecArray | null,
    i = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(text.slice(last, m.index));
    out.push(
      <span className="lv-mark" key={i++}>
        {m[0]}
      </span>
    );
    last = m.index + m[0].length;
    if (m.index === re.lastIndex) re.lastIndex++;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export default function Logs() {
  const [logs, setLogs] = useState<LogItem[]>([]);
  const [levelOn, setLevelOn] = useState<Record<string, boolean>>({ info: true, ok: true, warn: true, err: true });
  const [moduleFilter, setModuleFilter] = useState('');
  const [textFilter, setTextFilter] = useState('');
  const [tail, setTail] = useState(true);
  const [pendingNew, setPendingNew] = useState(0);

  const lastIdRef = useRef(0);
  const tailRef = useRef(true);
  const vpRef = useRef<HTMLDivElement | null>(null);
  tailRef.current = tail;

  // 已知模块(用于下拉)
  const modules = useMemo(() => {
    const s = new Set<string>();
    logs.forEach((it) => it.module && s.add(it.module));
    return Array.from(s).sort();
  }, [logs]);

  const passes = useCallback(
    (it: LogItem) => {
      if (!levelOn[mapTag(it.level)]) return false;
      if (moduleFilter && it.module !== moduleFilter) return false;
      if (textFilter) {
        const t = ((it.message || '') + ' ' + (it.module || '')).toLowerCase();
        if (!t.includes(textFilter)) return false;
      }
      return true;
    },
    [levelOn, moduleFilter, textFilter]
  );

  const visible = useMemo(() => {
    const v = logs.filter(passes);
    return v.length > MAX_ROWS ? v.slice(-MAX_ROWS) : v;
  }, [logs, passes]);

  // 初次拉取 + 增量轮询
  useEffect(() => {
    let alive = true;
    (async () => {
      const data = await api.logs(500);
      if (!alive || !data) return;
      const items = data.items || [];
      setLogs(items);
      lastIdRef.current = data.last_id || (items.length ? items[items.length - 1].id || 0 : 0);
    })();

    const id = setInterval(async () => {
      const data = await api.logsSince(lastIdRef.current, 500);
      if (!data) return;
      const items = data.items || [];
      if (data.last_id) lastIdRef.current = data.last_id;
      else if (items.length) lastIdRef.current = items[items.length - 1].id || lastIdRef.current;
      if (items.length) {
        setLogs((prev) => {
          const merged = [...prev, ...items];
          return merged.length > MAX_ROWS * 2 ? merged.slice(-MAX_ROWS) : merged;
        });
        if (!tailRef.current) setPendingNew((n) => n + items.length);
      }
    }, POLL_MS);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  // tail:渲染后滚到底
  useLayoutEffect(() => {
    if (tail && vpRef.current) vpRef.current.scrollTop = vpRef.current.scrollHeight;
  }, [visible, tail]);

  const onScroll = () => {
    const el = vpRef.current;
    if (!el) return;
    const atBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - NEAR_BOTTOM;
    if (atBottom) {
      if (!tailRef.current) setTail(true);
      setPendingNew(0);
    } else if (tailRef.current) {
      setTail(false);
    }
  };

  const resume = () => {
    setTail(true);
    setPendingNew(0);
  };

  const download = () => {
    const lines = logs
      .filter(passes)
      .map((it) => `[${it.datetime || it.time}] [${(it.level || '').toUpperCase()}] [${it.module || '-'}] ${it.message}`);
    const blob = new Blob([lines.join('\n')], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `neobot-${new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)}.log`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const clear = () => {
    setLogs([]);
    setPendingNew(0);
  };

  return (
    <div className="page">
      <section className="card log-card">
        <div className="log-toolbar">
          <div className="log-levels">
            {LEVELS.map((l) => (
              <button
                key={l.key}
                className={'level-pill ' + l.key + (levelOn[l.key] ? ' active' : '')}
                onClick={() => setLevelOn((s) => ({ ...s, [l.key]: !s[l.key] }))}
              >
                {l.label}
              </button>
            ))}
          </div>
          <select className="input" value={moduleFilter} onChange={(e) => setModuleFilter(e.target.value)}>
            <option value="">全部模块</option>
            {modules.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
          <input
            className="input"
            placeholder="搜索日志…"
            value={textFilter}
            onChange={(e) => setTextFilter(e.target.value.trim().toLowerCase())}
          />
          <div className="spacer" />
          <button className="btn" onClick={download}>
            下载
          </button>
          <button className="btn" onClick={clear}>
            清屏
          </button>
        </div>

        <div className="log-viewport" ref={vpRef} onScroll={onScroll}>
          {visible.length === 0 && <div className="empty muted">暂无日志</div>}
          {visible.map((it) => (
            <div className="lv-row" key={it.id} title={it.datetime || it.time}>
              <span className="lv-time">{it.time}</span>
              <span className={'lv-level ' + mapTag(it.level)}>{it.level}</span>
              <span className="lv-msg">
                <span className="lv-module">[{it.module || '—'}]</span> {highlight(it.message, textFilter)}
              </span>
            </div>
          ))}
        </div>

        <div className="log-statusbar">
          <span className="muted small">
            显示 {visible.length} / 缓冲 {logs.length} 条
          </span>
          <div className="spacer" />
          {!tail && pendingNew > 0 && (
            <button className="btn-sm primary" onClick={resume}>
              ↓ {pendingNew} 条新日志,回到底部
            </button>
          )}
          {tail ? <span className="tag ok">实时跟随</span> : <span className="tag warn">已暂停</span>}
        </div>
      </section>
    </div>
  );
}
