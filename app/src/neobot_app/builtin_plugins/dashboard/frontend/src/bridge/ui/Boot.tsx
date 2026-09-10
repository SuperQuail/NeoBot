// Boot.tsx —— 登舰引导（进入舰内前的检查清单）
//
// 进入 3D 场景前先做两件事：确认后端遥测可用（真实数据，不假装），
// 以及把操作方式讲清楚（Minecraft 式操作在浏览器里不直观，必须显式引导）。
// 「登舰」按钮同时承担了音频上下文初始化的用户手势。

import { useEffect, useState } from 'react';
import type { SystemInfo } from '../../api/types';
import type { VitalsState } from '../core/vitals';

export interface BootProps {
  vitals: VitalsState;
  system: SystemInfo | null;
  /** 上次离开时的位置（存档），用于「继续上次位置」 */
  lastPos: [number, number, number] | null;
  visitedCount: number;
  distance: number;
  onBoard: (options: { resume: boolean }) => void;
  onOpenClassic: () => void;
}

interface CheckItem {
  label: string;
  value: string;
  ok: boolean | null;
}

/** 逐行打印的启动自检：视觉上是「舰载主机自检」，实际检查的是真实接口连通性 */
export default function Boot({
  vitals,
  system,
  lastPos,
  visitedCount,
  distance,
  onBoard,
  onOpenClassic,
}: BootProps) {
  const availability = vitals.availability;
  const checks: CheckItem[] = [
    {
      label: '舰载主机遥测',
      value: availability === 'ok' ? '全部通道在线' : availability === 'partial' ? '部分通道在线' : '未接通',
      ok: availability === 'ok' ? true : availability === 'partial' ? null : false,
    },
    {
      label: '处理核心',
      value: system ? `${system.cpu_count ?? '?'} 核 · 负载 ${system.cpu_percent ?? '—'}%` : '等待遥测',
      ok: system ? true : null,
    },
    {
      label: '生命保障',
      value: system ? `内存 ${system.mem_percent ?? '—'}% · ${system.process_memory_mb ?? '—'}MB 进程` : '等待遥测',
      ok: system ? true : null,
    },
    {
      label: '舰体外壳',
      value: system ? `磁盘 ${system.disk_percent ?? '—'}%` : '等待遥测',
      ok: system ? true : null,
    },
    {
      label: '指挥链',
      value: system?.hostname ? `${system.hostname} · PID ${system.pid ?? '—'}` : '未识别',
      ok: system?.hostname ? true : null,
    },
  ];

  // 逐行显现，营造自检打印的节奏（约 1.2 秒走完）
  const [visible, setVisible] = useState(0);
  useEffect(() => {
    if (visible >= checks.length) return;
    const timer = window.setTimeout(() => setVisible((n) => n + 1), 190);
    return () => window.clearTimeout(timer);
  }, [visible, checks.length]);

  const allChecked = visible >= checks.length;

  return (
    <div className="boot">
      <div className="boot-grid" aria-hidden="true" />
      <div className="boot-panel">
        <div className="boot-head">
          <span className="boot-code">NEOBOT // BRIDGE OS 4.2</span>
          <h1>登舰引导</h1>
          <p>
            这里是 <strong>NeoBot 号</strong>的舰内控制台。全舰 8 座控制终端分别对应网页面板的真实功能：
            舰况、日志、星图、能源、模块、舰载单位、补给与本体配置。走到终端前按 <kbd>F</kbd> 接入。
          </p>
        </div>

        <ul className="boot-checks">
          {checks.slice(0, visible).map((check) => (
            <li key={check.label} className={check.ok === false ? 'is-bad' : check.ok === null ? 'is-warn' : 'is-ok'}>
              <span className="boot-check-dot" aria-hidden="true" />
              <span className="boot-check-label">{check.label}</span>
              <span className="boot-check-value">{check.value}</span>
            </li>
          ))}
          {!allChecked && <li className="boot-check-pending">自检进行中…</li>}
        </ul>

        <div className="boot-controls">
          <h2>操作方式</h2>
          <dl>
            <div>
              <dt>
                <kbd>W</kbd>
                <kbd>A</kbd>
                <kbd>S</kbd>
                <kbd>D</kbd>
              </dt>
              <dd>移动（鼠标转视角，左键点击画面后接管）</dd>
            </div>
            <div>
              <dt>
                <kbd>Space</kbd>
              </dt>
              <dd>喷射跳；空中再按一次触发二段喷射，可跨过管线与货箱</dd>
            </div>
            <div>
              <dt>
                <kbd>Shift</kbd> / <kbd>Ctrl</kbd>
              </dt>
              <dd>推进冲刺 / 蹲伏钻行（钻入低矮检修口）</dd>
            </div>
            <div>
              <dt>
                <kbd>F</kbd>
              </dt>
              <dd>接入终端、拾取物资、启动小游戏</dd>
            </div>
            <div>
              <dt>
                <kbd>1</kbd>–<kbd>8</kbd>
              </dt>
              <dd>快接终端；距离过远会自动跃迁</dd>
            </div>
            <div>
              <dt>
                <kbd>Q</kbd> / <kbd>E</kbd> / <kbd>Tab</kbd> / <kbd>H</kbd>
              </dt>
              <dd>舰内导航 / 物资清单 / 终端总览 / 操作手册</dd>
            </div>
            <div>
              <dt>
                <kbd>Esc</kbd>
              </dt>
              <dd>断开终端；再按一次释放鼠标</dd>
            </div>
          </dl>
        </div>

        <div className="boot-save">
          <span>航行记录：访问终端 {visitedCount}/8</span>
          <span>累计航程 {Math.round(distance)} m</span>
          {lastPos && <span>上次位置 {lastPos.map((n) => n.toFixed(1)).join(' / ')}</span>}
        </div>

        <div className="boot-actions">
          <button type="button" className="boot-primary" onClick={() => onBoard({ resume: false })} disabled={!allChecked}>
            登舰（从舰桥出发）
          </button>
          <button
            type="button"
            className="boot-secondary"
            onClick={() => onBoard({ resume: true })}
            disabled={!allChecked || !lastPos}
            title={lastPos ? '回到上次离开的位置' : '还没有存档位置'}
          >
            继续上次位置
          </button>
          <button type="button" className="boot-ghost" onClick={onOpenClassic}>
            改用经典控制台
          </button>
        </div>

        <p className="boot-foot">
          音频需要一次点击才能启动：登舰后即有引擎底噪与终端提示音，可用 <kbd>M</kbd> 静音。
          移动端支持左半屏拖动移动、右半屏拖动转视角、长按交互。
        </p>
      </div>
    </div>
  );
}
