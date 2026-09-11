// bridge.tsx —— 3D 舰载控制台主组件
//
// 装配关系：
//   BridgeEngine（three.js：场景 / 角色 / 碰撞 / 交互目标）
//        ↕ 引擎回调 + 节流快照
//   HUD / 浮层 / 全息面板 / 小游戏（React：全部界面）
// 两侧单向通信：React 卸载重建不影响渲染循环，反之亦然。

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type { PerspectiveCamera } from 'three';
import type { PanelPlane } from './three/projector';
import { clearToken } from '../api/client';
import { BridgeEngine, type HudSnapshot, type InteractionTarget } from './core/engine';
import { initSound, isMuted, sfx, toggleMuted } from './core/sound';
import {
  consumeItem,
  notify,
  onNotice,
  recordMiniGame,
  rememberPosition,
  unlock,
  useShipLog,
  type BridgeNotice,
} from './core/store';
import { ITEMS, STATIONS, STATION_BY_ID, type ItemId, type PanelId, type Station } from './core/types';
import { hasCritical, useVitals } from './core/vitals';
import { PanelCompositor } from './three/composite';
import Boot from './ui/Boot';
import Hud from './ui/Hud';
import PanelAnchor from './ui/PanelAnchor';
import { HelpOverlay, InventoryOverlay, NavOverlay, TerminalFrame, TerminalSwitcher } from './ui/Overlays';
import { PANEL_META, PANEL_COMPONENTS, type PanelProps } from './ui/panels';
import { META as MINIGAME_META, MINIGAME_COMPONENTS, type MiniGameKey } from './ui/minigames';
import './bridge.css';

type Phase = 'boot' | 'play';
type OverlayKind = 'terminal' | 'nav' | 'inventory' | 'help' | null;

const EMPTY_SNAPSHOT: HudSnapshot = {
  x: 0,
  y: 0,
  z: 0,
  yaw: 0,
  zone: '舰桥',
  zoneCode: 'BRIDGE',
  grounded: true,
  sprinting: false,
  crouching: false,
  crouchBlend: 0,
  fps: 0,
  target: null,
  collected: 0,
  nearestStation: null,
};

/** 舰内可回收物资总数（与 ship.ts 的投放数量一致，HUD 用来显示探索进度） */
const TOTAL_PICKUPS = 12;

export default function Bridge() {
  const navigate = useNavigate();
  const log = useShipLog();
  const vitals = useVitals();

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const overlayCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const engineRef = useRef<BridgeEngine | null>(null);
  const compositorRef = useRef<PanelCompositor | null>(null);
  const [compositor, setCompositor] = useState<PanelCompositor | null>(null);
  const [phase, setPhase] = useState<Phase>('boot');
  const [snapshot, setSnapshot] = useState<HudSnapshot>(EMPTY_SNAPSHOT);
  const [target, setTarget] = useState<InteractionTarget | null>(null);
  const [locked, setLocked] = useState(false);
  const [panel, setPanel] = useState<PanelId | null>(null);
  const [panelClosing, setPanelClosing] = useState(false);
  const [overlay, setOverlay] = useState<OverlayKind>(null);
  const [miniGame, setMiniGame] = useState<MiniGameKey | null>(null);
  const [notices, setNotices] = useState<BridgeNotice[]>([]);
  const [fatal, setFatal] = useState<string | null>(null);
  const [muted, setMutedState] = useState(() => isMuted());

  // ------------------------------------------------------------------
  // 引擎生命周期
  // ------------------------------------------------------------------
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || engineRef.current) return;
    // 合成器要先生成：引擎构造时需要用它的 render target 画深度
    let panelCompositor: PanelCompositor | null = null;
    if (overlayCanvasRef.current) {
      panelCompositor = new PanelCompositor(overlayCanvasRef.current);
      compositorRef.current = panelCompositor;
      setCompositor(panelCompositor);
      (window as unknown as Record<string, unknown>).__bridgeDebug = {
        getEngine: () => engineRef.current,
        stations: STATIONS,
      };
    }
    let engine: BridgeEngine;
    try {
      engine = new BridgeEngine({
        canvas,
        compositor: panelCompositor ?? undefined,
        callbacks: {
          onTargetChange: setTarget,
          onOpenPanel: (id) => {
            // Reentry must release the cursor even when React sees the same panel id.
            engineRef.current?.input.exitLock();
            setPanelClosing(false);
            setPanel(id);
          },
          onLaunchMiniGame: (key) => {
            if (key === 'turret' || key === 'circuit' || key === 'cargo') setMiniGame(key);
          },
          onWarp: (station) => engine.warpTo(station),
        },
      });
    } catch (error) {
      // WebGL 不可用（远程桌面 / 旧显卡 / 策略禁用）时给出可操作的中文提示，而不是白屏
      setFatal(
        `无法初始化 WebGL 渲染：${(error as Error).message}。可改用经典控制台，或更换支持 WebGL2 的浏览器。`,
      );
      panelCompositor?.dispose();
      compositorRef.current = null;
      return;
    }
    engineRef.current = engine;

    const syncLock = () => setLocked(document.pointerLockElement === canvas);
    document.addEventListener('pointerlockchange', syncLock);
    return () => {
      document.removeEventListener('pointerlockchange', syncLock);
      engine.dispose();
      engineRef.current = null;
      compositorRef.current?.dispose();
      compositorRef.current = null;
      setCompositor(null);
    };
  }, []);

  // 收起动画播完 → 真正卸载面板
  useEffect(() => {
    if (!panelClosing) return;
    const timer = window.setTimeout(() => {
      setPanel(null);
      setPanelClosing(false);
      // Never reacquire pointer lock from a timer after Escape.
    }, 320);
    return () => window.clearTimeout(timer);
  }, [panelClosing]);

  const getCamera = useCallback((): PerspectiveCamera | null => engineRef.current?.camera ?? null, []);
  const getViewport = useCallback(
    () => engineRef.current?.viewport ?? { width: 0, height: 0 },
    [],
  );
  const getVisibility = useCallback(
    (plane: PanelPlane) => engineRef.current?.panelVisibility(plane) ?? 1,
    [],
  );

  // 世界空间终端不冻结移动；只有模态浮层和小游戏接管输入。
  useEffect(() => {
    const engine = engineRef.current;
    if (!engine) return;
    const busy = overlay !== null || miniGame !== null || phase !== 'play';
    engine.input.setEnabled(!busy);
    if (busy || panel !== null) engine.input.exitLock();
  }, [panel, overlay, miniGame, phase]);

  // Browsers can consume Escape before keydown while pointer-locked.
  // Input distinguishes that unlock from our own V/F/overlay releases.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !panel || overlay || miniGame) return;
    const closeOnUnlock = () => setPanelClosing(true);
    canvas.addEventListener('bridge-pointer-unlock', closeOnUnlock);
    return () => canvas.removeEventListener('bridge-pointer-unlock', closeOnUnlock);
  }, [panel, overlay, miniGame]);

  // 离开舰桥时记录位置，供下次「继续上次位置」
  useEffect(
    () => () => {
      const engine = engineRef.current;
      if (engine) {
        const { x, y, z } = engine.player.position;
        rememberPosition(x, y, z);
      }
    },
    [],
  );

  // ------------------------------------------------------------------
  // 快照轮询：HUD 以 10Hz 更新，渲染循环保持 60Hz
  // ------------------------------------------------------------------
  useEffect(() => {
    if (phase !== 'play') return;
    const timer = window.setInterval(() => {
      const engine = engineRef.current;
      if (!engine) return;
      setSnapshot(engine.snapshot());
      engine.reportVitals(vitals.vitals);
    }, 100);
    return () => window.clearInterval(timer);
  }, [phase, vitals.vitals]);

  // ------------------------------------------------------------------
  // 通知总线
  // ------------------------------------------------------------------
  useEffect(() => {
    const timers = new Set<number>();
    const off = onNotice((notice) => {
      setNotices((current) => [...current.slice(-3), notice]);
      if (notice.tone === 'good') sfx.achievement();
      const timer = window.setTimeout(() => {
        timers.delete(timer);
        setNotices((current) => current.filter((item) => item.id !== notice.id));
      }, 4200);
      timers.add(timer);
    });
    return () => {
      off();
      for (const timer of timers) window.clearTimeout(timer);
    };
  }, []);

  // 舰况警戒音：只在状态跳变时响一次，避免持续刷屏
  const criticalKey = useMemo(() => hasCritical(vitals.vitals)?.key ?? null, [vitals.vitals]);
  const lastCritical = useRef<string | null>(null);
  useEffect(() => {
    if (criticalKey && criticalKey !== lastCritical.current) {
      const critical = hasCritical(vitals.vitals);
      sfx.alarm();
      if (critical) notify(`舰况警戒：${critical.label} ${critical.value}${critical.unit}`, 'warn');
    }
    lastCritical.current = criticalKey;
  }, [criticalKey, vitals.vitals]);

  // 成就：四项舰况同时处于良好区间
  useEffect(() => {
    if (vitals.availability !== 'ok') return;
    const allGood = vitals.vitals.every((vital) =>
      vital.key === 'heat' ? vital.value < 60 : vital.value >= 80,
    );
    if (allGood) unlock('systems-nominal');
  }, [vitals.availability, vitals.vitals]);

  // ------------------------------------------------------------------
  // 浮层快捷键（引擎只管移动与交互，界面层按键在这里统一处理）
  // ------------------------------------------------------------------
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const node = event.target as HTMLElement | null;
      const typing =
        node instanceof HTMLInputElement ||
        node instanceof HTMLTextAreaElement ||
        node instanceof HTMLSelectElement ||
        node?.isContentEditable === true;

      if (event.code === 'KeyM' && !typing) {
        setMutedState(toggleMuted());
        return;
      }
      if (typing) return;
      if (event.code === 'KeyV' && panel && !overlay && !miniGame && !event.repeat) {
        const input = engineRef.current?.input;
        if (input?.isLocked()) input.exitLock();
        else input?.requestLock();
        return;
      }
      const toggle = (kind: Exclude<OverlayKind, null>) => {
        event.preventDefault();
        setOverlay((current) => (current === kind ? null : kind));
      };
      if (event.code === 'KeyQ') toggle('nav');
      else if (event.code === 'KeyE') toggle('inventory');
      else if (event.code === 'Tab') toggle('terminal');
      else if (event.code === 'KeyH') toggle('help');
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [panel, overlay, miniGame]);

  // ------------------------------------------------------------------
  // 交互回调
  // ------------------------------------------------------------------
  const handleBoard = useCallback(
    (options: { resume: boolean }) => {
      // 音频上下文必须在用户手势的调用栈里创建
      initSound();
      const engine = engineRef.current;
      if (!engine) return;
      if (options.resume && log.lastPos) engine.player.teleport(log.lastPos, 0);
      engine.start();
      setPhase('play');
      notify('已登舰 · NeoBot 号全系统就绪', 'good');
      unlock('boarded');
      engine.input.requestLock();
    },
    [log.lastPos],
  );

  const handleClosePanel = useCallback(() => {
    // 先释放指针并播收起动画，动画结束后卸载；不再自动抢回鼠标。
    engineRef.current?.input.exitLock();
    setPanelClosing(true);
  }, []);

  /**
   * 从舰桥浮层（终端总览 / 舰内导航）打开某座终端。
   *
   * 关键：**必须先跃迁过去**。面板挂在该终端自己的屏幕上，如果玩家还站在
   * 舰桥另一端，面板会出现在二十米外——加上距离淡出，看起来就是「点了没反应」。
   * 早期这里只 setPanel 不跃迁，实测就是这个现象。
   */
  const openStationFromOverlay = useCallback((id: PanelId) => {
    const engine = engineRef.current;
    const station = STATION_BY_ID[id];
    if (engine) {
      engine.input.exitLock();
      engine.warpTo(station);
      // 落地后再开面板，避免跃迁的瞬移与面板展开动画叠在一起看不清
      engine.triggerShake(0.35);
    }
    setOverlay(null);
    setPanelClosing(false);
    setPanel(id);
    sfx.open();
  }, []);

  const handleUseItem = useCallback((id: ItemId) => {
    if (!consumeItem(id)) {
      sfx.deny();
      notify('物资不足', 'warn');
      return;
    }
    sfx.pulse();
    notify(`已使用 ${ITEMS[id].name} · ${ITEMS[id].hint}`, 'good');
    // 物资影响舰内表现（镜头脉冲）；真实指标始终以服务器遥测为准
    engineRef.current?.triggerShake(0.35);
  }, []);

  const handleMiniGameFinish = useCallback(
    (score: number) => {
      if (!miniGame) return;
      const record = recordMiniGame(miniGame, score);
      const name = MINIGAME_META[miniGame].name;
      notify(`${name}结束 · 本次 ${score} 分，最好成绩 ${record.best} 分`, 'good');
      // 注意：这里**不卸载**小游戏组件——结算界面由游戏自己渲染，
      // 玩家可以在结算页选择「再来一次」或返回舰内（返回时才走 onExit）。
      // 父级只负责记录成绩、解锁成就与提示。
      if (miniGame === 'turret' && score >= 15) unlock('turret-ace');
      if (miniGame === 'cargo' && score >= 300) unlock('cargo-master');
      if (miniGame === 'circuit' && score > 0) unlock('first-repair');
    },
    [miniGame],
  );

  const handleInteract = useCallback(() => {
    engineRef.current?.performInteract();
  }, []);

  const handleExitToClassic = useCallback(() => {
    navigate('/dashboard');
  }, [navigate]);

  const handleCanvasClick = useCallback(() => {
    if (phase !== 'play' || overlay || miniGame) return;
    engineRef.current?.input.requestLock();
  }, [phase, overlay, miniGame]);

  const activeStation: Station | null = panel ? STATION_BY_ID[panel] : null;
  const miniGameMeta = miniGame ? MINIGAME_META[miniGame] : null;
  const MiniGameComponent = miniGame ? MINIGAME_COMPONENTS[miniGame] : null;
  const hullVital = vitals.vitals.find((vital) => vital.key === 'hull');
  const collectedCount = Object.values(log.inventory).reduce((sum, count) => sum + (count ?? 0), 0);

  return (
    <div className={`bridge${miniGame ? ' bridge-minigame' : ''}`}>
      <canvas ref={canvasRef} className="bridge-canvas" onClick={handleCanvasClick} aria-label="舰内第一人称视图" />
      {/* 合成层：夹在主画面与 DOM 面板之间。
          它负责「深度遮挡」——被舱壁挡住的像素 alpha 归零，于是 DOM 面板从那里
          透出来的是场景本身，面板边缘会被门框、货箱正确地切开。
          这一层必须始终存在（哪怕面板没开），否则面板永远浮在最上面。 */}
      <canvas ref={overlayCanvasRef} className="bridge-overlay" aria-hidden="true" />
      {/* 面板打开时压暗场景：注意力集中到终端上，同时掩盖面板穿透导致的观感问题 */}
      <div className={`bridge-dimmer${panel && !locked ? ' is-on' : ''}`} aria-hidden="true" />

      {fatal && (
        <div className="bridge-fatal" role="alert">
          <h2>渲染初始化失败</h2>
          <p>{fatal}</p>
          <div className="bridge-fatal-actions">
            <button type="button" onClick={handleExitToClassic}>
              打开经典控制台
            </button>
            <button
              type="button"
              onClick={() => {
                clearToken();
                navigate('/login', { replace: true });
              }}
            >
              重新登录
            </button>
          </div>
        </div>
      )}

      {!fatal && phase === 'boot' && (
        <Boot
          vitals={vitals}
          system={vitals.system}
          lastPos={log.lastPos}
          visitedCount={log.visited.length}
          distance={log.distance}
          onBoard={handleBoard}
          onOpenClassic={handleExitToClassic}
        />
      )}

      {!fatal && phase === 'play' && (
        <Hud
          snapshot={snapshot}
          vitals={vitals}
          notices={notices}
          target={target}
          connectedPanel={panel}
          locked={locked}
          dimmed={(panel !== null && !locked) || overlay !== null || miniGame !== null}
          pickupProgress={{ collected: collectedCount, total: TOTAL_PICKUPS }}
          onInteract={handleInteract}
        />
      )}

      {/* 舰桥工具条：浮层与静音的鼠标入口（触屏设备主要靠它） */}
      {!fatal && phase === 'play' && (
        <nav className="bridge-dock" aria-label="舰桥工具">
          <button type="button" onClick={() => setOverlay('terminal')} title="终端总览（Tab）">
            <span className="dock-key">Tab</span>终端
          </button>
          <button type="button" onClick={() => setOverlay('nav')} title="舰内导航（Q）">
            <span className="dock-key">Q</span>导航
          </button>
          <button type="button" onClick={() => setOverlay('inventory')} title="物资清单（E）">
            <span className="dock-key">E</span>物资
          </button>
          <button type="button" onClick={() => setOverlay('help')} title="操作手册（H）">
            <span className="dock-key">H</span>手册
          </button>
          <button type="button" onClick={() => setMutedState(toggleMuted())} title="静音（M）" aria-pressed={muted}>
            <span className="dock-key">M</span>
            {muted ? '已静音' : '音效'}
          </button>
          {panel && !overlay && !miniGame && (
            <button type="button" onClick={() => {
              const input = engineRef.current?.input;
              if (input?.isLocked()) input.exitLock();
              else input?.requestLock();
            }} title="保持连接，切换鼠标与视角控制（V）；WASD 移动">
              <span className="dock-key">V</span>{locked ? '操作终端' : '自由视角'}
            </button>
          )}
          <button type="button" onClick={handleExitToClassic} title="切换到 2D 面板">
            经典面板
          </button>
        </nav>
      )}

      {overlay === 'terminal' && (
        <TerminalSwitcher
          vitals={vitals}
          activeId={panel}
          onSelect={openStationFromOverlay}
          onClose={() => setOverlay(null)}
        />
      )}
      {overlay === 'nav' && (
        <NavOverlay currentZone={snapshot.zone} onWarp={openStationFromOverlay} onClose={() => setOverlay(null)} />
      )}
      {overlay === 'inventory' && (
        <InventoryOverlay vitals={vitals} onUse={handleUseItem} onClose={() => setOverlay(null)} />
      )}
      {overlay === 'help' && <HelpOverlay onOpenClassic={handleExitToClassic} onClose={() => setOverlay(null)} />}

      {activeStation && !miniGame && (
        <PanelAnchor
          station={activeStation}
          getCamera={getCamera}
          getViewport={getViewport}
          getVisibility={getVisibility}
          compositor={compositor}
          closing={panelClosing}
        >
          <PanelHost
            station={activeStation}
            vitals={vitals}
            onClose={handleClosePanel}
            onLaunchMiniGame={setMiniGame}
          />
        </PanelAnchor>
      )}

      {miniGame && miniGameMeta && MiniGameComponent && (
        <div className="bridge-minigame-host" role="dialog" aria-modal="true" aria-label={miniGameMeta.name}>
          <MiniGameComponent
            onFinish={handleMiniGameFinish}
            onExit={() => {
              setMiniGame(null);
              engineRef.current?.input.requestLock();
            }}
            hullIntegrity={hullVital?.value ?? null}
          />
        </div>
      )}
    </div>
  );
}

/** 终端宿主：把 ui/panels 的组件套进统一的舰载机框，并下发刷新令牌 */
function PanelHost({
  station,
  vitals,
  onClose,
  onLaunchMiniGame,
}: {
  station: Station;
  vitals: ReturnType<typeof useVitals>;
  onClose: () => void;
  onLaunchMiniGame: (key: MiniGameKey) => void;
}) {
  const [refreshToken, setRefreshToken] = useState(0);
  const meta = PANEL_META[station.id];
  const PanelComponent = PANEL_COMPONENTS[station.id];
  const panelProps: PanelProps = {
    station,
    vitals: vitals.vitals,
    onClose,
    onLaunchMiniGame,
    refreshToken,
  };
  return (
    <div className="bridge-panel-host">
      <TerminalFrame
        code={station.code}
        terminal={station.terminal}
        title={meta.title}
        subtitle={`${station.label} · ${station.subsystem}`}
        onClose={onClose}
        onRefresh={() => setRefreshToken((value) => value + 1)}
      >
        <PanelComponent {...panelProps} />
      </TerminalFrame>
    </div>
  );
}
