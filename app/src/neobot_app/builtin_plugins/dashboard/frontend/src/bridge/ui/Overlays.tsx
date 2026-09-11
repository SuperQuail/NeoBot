// Overlays.tsx —— 舰内浮层：终端总览 / 导航跃迁 / 物资清单 / 操作手册 / 终端机框
//
// 这些是「驾驶舱 HUD 之外」的界面层，用同一套毛玻璃 + 青色描边的舰载视觉，
// 与全息面板（ui/panels）区分：浮层是舰桥玻璃投影，面板是终端全息投影。

import { useEffect, type ReactNode } from 'react';
import { ITEMS, ITEM_IDS, STATIONS, type ItemId, type PanelId } from '../core/types';
import { useShipLog } from '../core/store';
import { sfx } from '../core/sound';
import { vitalStatus, type VitalsState } from '../core/vitals';

export interface OverlayProps {
  onClose: () => void;
}

interface ShellProps extends OverlayProps {
  code: string;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
}

/** 通用浮层外壳：Esc 关闭、点击背景关闭、焦点回到浮层 */
export function OverlayShell({ code, title, children, footer, onClose, wide }: ShellProps) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        onClose();
      }
    };
    // capture 阶段拦截：避免 Esc 同时触发「释放鼠标」与「关闭浮层」两件事
    window.addEventListener('keydown', onKey, true);
    return () => window.removeEventListener('keydown', onKey, true);
  }, [onClose]);

  return (
    <div className="ov-backdrop">
      {/* 背景点击关闭：用真正的 button 而不是给 div 挂 onClick，
          这样键盘用户（Esc 之外的路径）与辅助技术都能触发，也满足 jsx-a11y 规则 */}
      <button type="button" className="ov-backdrop-hit" aria-label="关闭浮层" onClick={onClose} />
      <section
        className={`ov-shell${wide ? ' ov-shell-wide' : ''}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <header className="ov-head">
          <div>
            <span className="ov-code">{code}</span>
            <h2>{title}</h2>
          </div>
          <button type="button" className="ov-close" onClick={onClose} aria-label="关闭">
            ESC
          </button>
        </header>
        <div className="ov-body">{children}</div>
        {footer && <footer className="ov-foot">{footer}</footer>}
      </section>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 终端总览
// ---------------------------------------------------------------------------

export interface TerminalSwitcherProps extends OverlayProps {
  vitals: VitalsState;
  activeId: PanelId | null;
  onSelect: (id: PanelId) => void;
}

export function TerminalSwitcher({ vitals, activeId, onSelect, onClose }: TerminalSwitcherProps) {
  const log = useShipLog();
  return (
    <OverlayShell
      code="SYS-MAP-01"
      title="终端总览"
      wide
      onClose={onClose}
      footer={<span>点击任意终端接入；已接入过的终端会标记为「已校准」。数字键 1–8 可直接快接。</span>}
    >
      <div className="ov-terminal-grid">
        {STATIONS.map((station, index) => {
          const visited = log.visited.includes(station.id);
          return (
            <button
              key={station.id}
              type="button"
              className={`ov-terminal${activeId === station.id ? ' is-active' : ''}${visited ? ' is-visited' : ''}`}
              onClick={() => {
                sfx.beep();
                onSelect(station.id);
              }}
            >
              <span className="ov-terminal-hot">{index + 1}</span>
              <span className="ov-terminal-code">{station.code}</span>
              <span className="ov-terminal-name">{station.label}</span>
              <span className="ov-terminal-title">{station.title}</span>
              <span className="ov-terminal-sys">{station.subsystem}</span>
              <span className={`ov-terminal-flag${visited ? ' is-ok' : ''}`}>{visited ? '已校准' : '未接入'}</span>
            </button>
          );
        })}
      </div>
      <div className="ov-vitals-strip">
        {vitals.vitals.map((vital) => (
          <span key={vital.key} className={`ov-vital ov-vital-${vitalStatus(vital.key, vital.value)}`}>
            {vital.label} {vital.value}
            {vital.unit}
          </span>
        ))}
      </div>
    </OverlayShell>
  );
}

// ---------------------------------------------------------------------------
// 舰内导航
// ---------------------------------------------------------------------------

export interface NavOverlayProps extends OverlayProps {
  currentZone: string;
  onWarp: (id: PanelId) => void;
}

export function NavOverlay({ currentZone, onWarp, onClose }: NavOverlayProps) {
  return (
    <OverlayShell
      code="NAV-INTERNAL"
      title="舰内导航"
      onClose={onClose}
      footer={<span>跃迁会消耗一次姿态修正：抵达后请稍候再操作终端。当前舱室：{currentZone}</span>}
    >
      <div className="ov-nav-list">
        {STATIONS.map((station, index) => (
          <button
            key={station.id}
            type="button"
            className="ov-nav-item"
            onClick={() => {
              sfx.warp();
              onWarp(station.id);
            }}
          >
            <span className="ov-nav-key">{index + 1}</span>
            <span className="ov-nav-main">
              <strong>{station.label}</strong>
              <em>{station.subsystem}</em>
            </span>
            <span className="ov-nav-zone">{station.code}</span>
          </button>
        ))}
      </div>
    </OverlayShell>
  );
}

// ---------------------------------------------------------------------------
// 物资清单
// ---------------------------------------------------------------------------

export interface InventoryProps extends OverlayProps {
  vitals: VitalsState;
  onUse: (id: ItemId) => void;
}

export function InventoryOverlay({ vitals, onUse, onClose }: InventoryProps) {
  const log = useShipLog();
  const capacity = ITEM_IDS.length;
  return (
    <OverlayShell
      code="SUPPLY-MANIFEST"
      title="物资清单"
      onClose={onClose}
      footer={<span>物资用于应急处置：能源下降、主机过热或舰体受损时，用对应物资把读数拉回安全区。</span>}
    >
      <div className="ov-inventory-head">
        <span>货舱容量 {capacity} 类</span>
        <span>舰况同步：{vitals.availability === 'ok' ? '正常' : '受限'}</span>
      </div>
      <ul className="ov-inventory">
        {ITEM_IDS.map((id) => {
          const def = ITEMS[id];
          const owned = log.inventory[id] ?? 0;
          const restores = Object.entries(def.restore);
          return (
            <li key={id} className={owned > 0 ? 'is-owned' : 'is-empty'}>
              <div className="ov-item-main">
                <span className="ov-item-name">{def.name}</span>
                <span className="ov-item-hint">{def.hint}</span>
                {restores.length > 0 && (
                  <span className="ov-item-effect">
                    效果：
                    {restores
                      .map(([key, delta]) => `${key === 'heat' ? '主机温度' : key === 'energy' ? '能源' : key === 'hull' ? '舰体' : '生命保障'}${(delta as number) > 0 ? '+' : ''}${delta}`)
                      .join('、')}
                  </span>
                )}
              </div>
              <div className="ov-item-count">
                <span>×{owned}</span>
                <button type="button" disabled={owned === 0} onClick={() => onUse(id)}>
                  使用
                </button>
              </div>
            </li>
          );
        })}
      </ul>
      <p className="ov-note">物资散布在舰内各处：靠近漂浮的补给箱按 <kbd>F</kbd> 回收。</p>
    </OverlayShell>
  );
}

// ---------------------------------------------------------------------------
// 操作手册
// ---------------------------------------------------------------------------

export interface HelpOverlayProps extends OverlayProps {
  onOpenClassic: () => void;
}

export function HelpOverlay({ onOpenClassic, onClose }: HelpOverlayProps) {
  return (
    <OverlayShell code="FLIGHT-MANUAL" title="操作手册" wide onClose={onClose}>
      <div className="ov-manual">
        <section>
          <h3>移动与视角</h3>
          <ul>
            <li>
              <kbd>W</kbd>
              <kbd>A</kbd>
              <kbd>S</kbd>
              <kbd>D</kbd> 移动，鼠标转视角；点击画面后由浏览器接管指针（按 <kbd>Esc</kbd> 释放）
            </li>
            <li>
              <kbd>Shift</kbd> 推进冲刺，<kbd>Ctrl</kbd> 蹲伏钻行，<kbd>Space</kbd> 喷射跳（空中再按一次可二段喷射）
            </li>
            <li>移动端：左半屏拖动移动，右半屏拖动转视角，长按 0.3 秒等同按 <kbd>F</kbd></li>
          </ul>
        </section>
        <section>
          <h3>接入终端</h3>
          <ul>
            <li>走到终端正前方（约 3 米内），准星变为实心环，屏幕中出现「接入」提示</li>
            <li>
              按 <kbd>F</kbd> 接入；按 <kbd>1</kbd>–<kbd>8</kbd> 可快接对应终端，距离过远会自动跃迁
            </li>
            <li>
              接入后仍可用 <kbd>WASD</kbd> 移动，按住鼠标右键拖动可转视角；<kbd>V</kbd> 切换鼠标操作 / 自由视角，<kbd>F</kbd> 可重新操作已连接的终端。编辑输入框时不会触发移动。
            </li>
            <li>
              <kbd>Esc</kbd> 断开终端，点击「刷新」更新数据；断开局域网连接时面板会明确提示而不是显示旧值
            </li>
          </ul>
        </section>
        <section>
          <h3>舰况与物资</h3>
          <ul>
            <li>四项舰况直接来自服务器的真实遥测：能源 ← 电池/CPU、生命保障 ← 内存、舰体 ← 磁盘、主机温度 ← 负载</li>
            <li>读数进入警戒区时屏幕会出现红色横幅并伴随警报音，用对应物资可回补</li>
            <li>舰体受损（磁盘将满）时会触发「损管」提示，可在火控台查看处置建议</li>
          </ul>
        </section>
        <section>
          <h3>小游戏</h3>
          <ul>
            <li>近防炮演习：在火控台附近启动，击毁来袭目标保护舰体</li>
            <li>配电回路检修：工程舱的断路器面板，修复供电回路</li>
            <li>货舱调度：机库的船坞调配台，按质量与危险等级分派货柜</li>
          </ul>
        </section>
        <section>
          <h3>其他</h3>
          <ul>
            <li>
              <kbd>Q</kbd> 舰内导航、<kbd>E</kbd> 物资清单、<kbd>Tab</kbd> 终端总览、<kbd>H</kbd> 本手册、<kbd>M</kbd> 静音
            </li>
            <li>探索进度、成就与小游戏成绩保存在本机浏览器，不上传服务器</li>
          </ul>
        </section>
      </div>
      <div className="ov-manual-actions">
        <button type="button" className="ov-ghost" onClick={onOpenClassic}>
          改用经典控制台（2D 面板）
        </button>
      </div>
    </OverlayShell>
  );
}

// ---------------------------------------------------------------------------
// 终端机框（全息面板的外壳）
// ---------------------------------------------------------------------------

export interface TerminalFrameProps {
  code: string;
  terminal: string;
  title: string;
  subtitle: string;
  onClose: () => void;
  onRefresh?: () => void;
  children: ReactNode;
}

/**
 * 全息终端外壳：面板实现由 ui/panels 提供，这里只负责舰载机框、状态灯与关闭逻辑，
 * 保证 8 个终端的观感与外层行为完全一致。
 */
export function TerminalFrame({
  code,
  terminal,
  title,
  subtitle,
  onClose,
  onRefresh,
  children,
}: TerminalFrameProps) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        onClose();
      }
    };
    window.addEventListener('keydown', onKey, true);
    return () => window.removeEventListener('keydown', onKey, true);
  }, [onClose]);

  return (
    <div className="hologram" role="region" aria-label={`${title} 全息终端`}>
      <div className="hologram-noise" aria-hidden="true" />
      <header className="hologram-head">
        <div className="hologram-id">
          <span className="hologram-code">{code}</span>
          <span className="hologram-terminal">{terminal}</span>
        </div>
        <div className="hologram-title">
          <h2>{title}</h2>
          <p>{subtitle}</p>
        </div>
        <div className="hologram-actions">
          {onRefresh && (
            <button type="button" onClick={onRefresh} title="刷新数据（R）">
              刷新
            </button>
          )}
          <button type="button" className="hologram-close" onClick={onClose} title="断开终端（Esc）">
            断开
          </button>
        </div>
      </header>
      <div className="hologram-body">{children}</div>
      <footer className="hologram-foot">
        <span className="hologram-live" aria-hidden="true" />
        <span>链路已加密 · 数据实时来自舰载主机</span>
        <span className="hologram-hint">
          <kbd>WASD</kbd> 移动 · 右键拖动转视角 · <kbd>V</kbd> 切换 · <kbd>Esc</kbd> 断开
        </span>
      </footer>
    </div>
  );
}
