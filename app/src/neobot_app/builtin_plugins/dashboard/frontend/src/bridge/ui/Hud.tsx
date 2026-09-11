// Hud.tsx —— 舰内抬头显示器（HUD）
//
// 全部用 DOM 叠加在 3D 画布之上：矢量文字清晰、可被辅助技术读取、样式复用现有主题。
// 布局刻意做成舰桥玻璃座舱的观感：顶部任务条 + 四周角标 + 中央准星 + 底部状态条。

import { useEffect, useMemo, useRef, useState } from 'react';
import type { HudSnapshot, InteractionTarget } from '../core/engine';
import type { BridgeNotice } from '../core/store';
import { hasCritical, vitalStatus, type VitalsState } from '../core/vitals';
import type { PanelId, Vital } from '../core/types';

export interface HudProps {
  snapshot: HudSnapshot;
  vitals: VitalsState;
  notices: BridgeNotice[];
  target: InteractionTarget | null;
  /** 已连接的终端不再显示重复接入提示；不影响引擎的 F 交互。 */
  connectedPanel?: PanelId | null;
  /** 是否处于指针锁定（未锁定时显示「点击继续」遮罩） */
  locked: boolean;
  /** 面板/小游戏打开时隐藏准星与提示 */
  dimmed: boolean;
  /** 已收集物资数量 / 总数，用于探索进度 */
  pickupProgress: { collected: number; total: number };
  onInteract: () => void;
}

/**
 * 罗盘方位：把 yaw 弧度换成「舰艏 / 右舷 / 舰艉 / 左舷」八档。
 *
 * 与 player.ts 的约定一致：yaw=0 朝 +z（舰艏），yaw=+π/2 朝 +x（右舷）。
 * 因此角度 = yaw（度），右转为正——这里不能取反，否则罗盘会左右颠倒。
 */
function compassLabel(yaw: number): string {
  const degrees = ((yaw * 180) / Math.PI) % 360;
  const angle = (degrees + 360) % 360;
  const names = ['舰艏', '右舷前', '右舷', '右舷后', '舰艉', '左舷后', '左舷', '左舷前'];
  return names[Math.round(angle / 45) % 8];
}

/** 姿态读数：蹲伏有过渡状态，按比例显示更贴近实际视角高度 */
function poseLabel(snapshot: HudSnapshot): string {
  if (snapshot.crouching) {
    const percent = Math.round(snapshot.crouchBlend * 100);
    return percent >= 90 ? '蹲伏检修' : `下蹲中 ${percent}%`;
  }
  if (!snapshot.grounded) return '悬浮';
  return snapshot.sprinting ? '推进冲刺' : '站立';
}

/** 读数条：颜色随警戒等级变化 */
function VitalGauge({ vital }: { vital: Vital }) {
  const status = vitalStatus(vital.key, vital.value);
  return (
    <div className={`hud-vital hud-vital-${status}`} title={`${vital.label}：${vital.value}${vital.unit}（${vital.source}）`}>
      <div className="hud-vital-head">
        <span className="hud-vital-label">{vital.label}</span>
        <span className="hud-vital-value">
          {vital.value}
          {vital.unit}
        </span>
      </div>
      <div className="hud-vital-bar">
        <span style={{ width: `${Math.max(2, Math.min(100, vital.value))}%` }} />
      </div>
    </div>
  );
}

export default function Hud({
  snapshot,
  vitals,
  notices,
  target,
  connectedPanel = null,
  locked,
  dimmed,
  pickupProgress,
  onInteract,
}: HudProps) {
  const [clock, setClock] = useState(() => new Date());
  const criticalRef = useRef<string | null>(null);

  // 舰钟：每秒走一次，成本可忽略
  useEffect(() => {
    const timer = window.setInterval(() => setClock(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const critical = useMemo(() => hasCritical(vitals.vitals), [vitals.vitals]);
  const criticalKey = critical ? `${critical.key}:${critical.value}` : null;
  // 只在警戒状态变化时提示，避免每帧刷屏
  useEffect(() => {
    criticalRef.current = criticalKey;
  }, [criticalKey]);

  const unavailable = vitals.availability === 'unavailable';
  const connectedTarget = target?.kind === 'station' && target.station?.id === connectedPanel;
  const showTarget = target !== null && !connectedTarget;

  return (
    <div className={`hud${dimmed ? ' hud-dimmed' : ''}${critical ? ' hud-alert' : ''}`}>
      {/* 座舱玻璃反光与扫描线，纯装饰 */}
      <div className="hud-glass" aria-hidden="true" />
      <div className="hud-scanlines" aria-hidden="true" />

      {/* 顶部任务条 */}
      <header className="hud-top">
        <div className="hud-badge">
          <span className="hud-badge-code">NEOBOT</span>
          <span className="hud-badge-name">号 · 舰载控制台</span>
        </div>
        <div className="hud-zone">
          <span className="hud-zone-code">{snapshot.zoneCode}</span>
          <span className="hud-zone-label">{snapshot.zone}</span>
        </div>
        <div className="hud-meta">
          <span title="舰内标准时">{clock.toLocaleTimeString('zh-CN', { hour12: false })}</span>
          <span title="渲染帧率">FPS {snapshot.fps}</span>
          <span title="罗盘方位">{compassLabel(snapshot.yaw)}</span>
        </div>
      </header>

      {/* 舰况读数 */}
      <aside className="hud-vitals" aria-label="舰况">
        {vitals.vitals.map((vital) => (
          <VitalGauge key={vital.key} vital={vital} />
        ))}
        <div className="hud-vitals-note">
          {unavailable
            ? '主机遥测不可用：请检查网页面板后端连接'
            : vitals.availability === 'partial'
              ? '部分遥测缺失，读数按可用项估算'
              : `遥测已同步 · ${vitals.lastUpdated ? new Date(vitals.lastUpdated).toLocaleTimeString('zh-CN', { hour12: false }) : '—'}`}
        </div>
      </aside>

      {/* 探索进度 */}
      <aside className="hud-explore" aria-label="探索进度">
        <div className="hud-explore-row">
          <span className="hud-explore-key">物资回收</span>
          <span className="hud-explore-value">
            {pickupProgress.collected}/{pickupProgress.total}
          </span>
        </div>
        <div className="hud-explore-bar">
          <span
            style={{
              width: `${pickupProgress.total === 0 ? 0 : (pickupProgress.collected / pickupProgress.total) * 100}%`,
            }}
          />
        </div>
        <div className="hud-explore-row hud-explore-sub">
          <span>坐标</span>
          <span>
            {snapshot.x.toFixed(1)} / {snapshot.z.toFixed(1)}
          </span>
        </div>
        <div className="hud-explore-row hud-explore-sub">
          <span>姿态</span>
          <span>{poseLabel(snapshot)}</span>
        </div>
      </aside>

      {/* 准星与交互提示 */}
      <div className="hud-center">
        {!dimmed && (
          <>
            <div className={`hud-crosshair${showTarget ? ' hud-crosshair-active' : ''}`} aria-hidden="true">
              <span className="hud-crosshair-dot" />
              <span className="hud-crosshair-ring" />
            </div>
            {showTarget && target && (
              <button type="button" className="hud-prompt" onClick={onInteract}>
                <kbd>F</kbd>
                <span className="hud-prompt-label">{target.hint}</span>
                <span className="hud-prompt-distance">{target.distance.toFixed(1)}m</span>
              </button>
            )}
            {!target && snapshot.nearestStation && snapshot.nearestStation.id !== connectedPanel && snapshot.nearestStation.distance < 14 && (
              <div className="hud-nearby">
                最近终端 · {snapshot.nearestStation.label}（{snapshot.nearestStation.distance.toFixed(0)}m）
              </div>
            )}
          </>
        )}
      </div>

      {/* 通知 */}
      <div className="hud-notices" role="status" aria-live="polite">
        {notices.map((notice) => (
          <div key={notice.id} className={`hud-notice hud-notice-${notice.tone}`}>
            {notice.text}
          </div>
        ))}
      </div>

      {/* 底部键位提示 */}
      <footer className="hud-keys">
        <span>
          <kbd>WASD</kbd> 移动
        </span>
        <span>
          <kbd>Space</kbd> 喷射跳
        </span>
        <span>
          <kbd>Shift</kbd> 冲刺
        </span>
        <span>
          <kbd>Ctrl</kbd> 蹲伏
        </span>
        <span>
          <kbd>F</kbd> 交互
        </span>
        <span>
          <kbd>1</kbd>-<kbd>8</kbd> 快接终端
        </span>
        <span>
          <kbd>Q</kbd> 导航
        </span>
        <span>
          <kbd>E</kbd> 物资
        </span>
        <span>
          <kbd>Tab</kbd> 终端总览
        </span>
        <span>
          <kbd>H</kbd> 手册
        </span>
      </footer>

      {/* 未锁定指针：提示点击继续（触屏设备不显示） */}
      {!locked && !dimmed && (
        <div className="hud-lock-hint" aria-hidden="true">
          <span>点击画面以接管视角</span>
        </div>
      )}

      {/* 舰况警戒横幅 */}
      {critical && (
        <div className="hud-critical" role="alert">
          <strong>舰况警戒</strong>
          <span>
            {critical.label} {critical.value}
            {critical.unit} — 建议前往对应终端处置
          </span>
        </div>
      )}
    </div>
  );
}
