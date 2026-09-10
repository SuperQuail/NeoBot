// cargo.tsx —— 货舱调度（装载规则判定 + 波次压力）
//
// 规则（legend 与判定共用同一份纯函数，避免「说明与实现」走偏）：
//   1) 危险品（hazard）        → 3 号隔离舱
//   2) 冷链货物（cold）        → 2 号冷藏舱
//   3) 活体 / 精密仪器         → 1 号恒温货舱
//   4) 其余：单件 ≥ 40 吨      → 4 号重载舱
//              单件 < 40 吨     → 1 号恒温货舱
// 规则自上而下按优先级判定：一件 55 吨的冷链箱仍然进 2 号舱，因为冷链优先于重量。
//
// 所有判定/计分逻辑都在导出的纯函数里（expectedBay / judgeAssignment / assignCargo / stepCargo），
// 组件只负责把它们接到 DOM 与音效上，因此不需要浏览器环境也能单测。

import { useCallback, useEffect, useRef, useState } from 'react';
import { sfx } from '../../core/sound';
import { unlock } from '../../core/store';
import './minigames.css';

export interface MiniGameProps {
  /** 一次调度结束时回调，父级负责存档与提示 */
  onFinish: (score: number) => void;
  /** 关闭小游戏并回到自由巡航 */
  onExit: () => void;
  /** 舰体完整度 0..100（父级由真实系统指标换算），不可用时为 null */
  hullIntegrity: number | null;
}

export const meta = {
  key: 'cargo',
  name: '货舱调度',
  code: 'DCK-SORT',
  brief: '按装载规则把进货箱分派到正确的货舱，货损归零即终止调度。',
  scoring: '正确入舱 = 20 + 剩余决策秒数×3 + 连击×4（上限 40）；错误或超时扣 12 点货损并清空连击。',
} as const;

/** 拿到该分数点亮「装载长」成就（与 core/types.ts 的 ACHIEVEMENTS 对齐） */
export const CARGO_MASTER_SCORE = 300;
/** 单件超重阈值（吨）：达到该质量必须走重载舱 */
export const CARGO_MASS_LIMIT = 40;
/** 错误投放 / 超时的货损 */
export const CARGO_MISLOAD_PENALTY = 12;
export const CARGO_TIMEOUT_PENALTY = 12;
/** 每波货箱数量 */
export const ITEMS_PER_WAVE = 8;

const clamp = (value: number, lo: number, hi: number): number => Math.min(hi, Math.max(lo, value));

/** mulberry32 单步：状态进、状态出，保证货箱序列可复现 */
function randStep(seed: number): [number, number] {
  const next = (seed + 0x6d2b79f5) >>> 0;
  let t = next;
  t = Math.imul(t ^ (t >>> 15), t | 1);
  t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
  return [((t ^ (t >>> 14)) >>> 0) / 4294967296, next];
}

export type CargoKind = 'standard' | 'cold' | 'live' | 'fragile';

export interface CargoItem {
  id: number;
  name: string;
  kind: CargoKind;
  /** 单件质量（吨） */
  mass: number;
  hazard: boolean;
}

export interface CargoBay {
  id: number;
  code: string;
  name: string;
  /** 该舱接收的货物，直接显示在 legend 里 */
  accepts: string;
}

export const CARGO_BAYS: CargoBay[] = [
  { id: 1, code: 'BAY-1', name: '恒温货舱', accepts: '活体货物 / 精密仪器 / 普通轻件' },
  { id: 2, code: 'BAY-2', name: '冷藏舱', accepts: '冷链货物' },
  { id: 3, code: 'BAY-3', name: '隔离舱', accepts: '危险品（最高优先级）' },
  { id: 4, code: 'BAY-4', name: '重载舱', accepts: '普通货中单件 ≥ 40 吨' },
];

const KIND_META: Record<CargoKind, { label: string; names: string[]; mass: readonly [number, number] }> = {
  standard: { label: '普通干货', names: ['标准集装箱', '舰用备件箱', '压缩口粮箱'], mass: [8, 60] },
  cold: { label: '冷链货物', names: ['冷链疫苗箱', '冷冻生鲜柜', '低温样本罐'], mass: [4, 26] },
  live: { label: '活体货物', names: ['活体样本舱', '实验动物箱', '移植器官箱'], mass: [3, 20] },
  fragile: { label: '精密仪器', names: ['陀螺仪组件', '光纤阵列箱', '导航反射镜组'], mass: [2, 16] },
};

export type CargoEvent = 'correct' | 'wrong' | 'wave' | 'over';

export interface CargoState {
  status: 'running' | 'over';
  wave: number;
  /** 货损完整度 0..100，归零则调度中止 */
  integrity: number;
  score: number;
  combo: number;
  bestCombo: number;
  correct: number;
  wrong: number;
  /** 已处理件数 */
  served: number;
  /** 当前货箱的剩余决策时间（秒） */
  timeLeft: number;
  elapsed: number;
  item: CargoItem | null;
  /** 最近几条判定结果，HUD 里滚动显示 */
  log: string[];
  rng: number;
  seq: number;
}

export interface CargoVerdict {
  correct: boolean;
  points: number;
  integrity: number;
  reason: string;
}

export interface CargoResult {
  state: CargoState;
  events: CargoEvent[];
  verdict?: CargoVerdict;
}

/** 每件货箱的决策时间随波次收紧 */
export function itemTime(wave: number): number {
  return Math.max(3, 8 - wave * 0.7);
}

export function waveOf(served: number): number {
  return 1 + Math.floor(served / ITEMS_PER_WAVE);
}

/** 装载规则判定：返回该货箱「应该」去的舱位编号 */
export function expectedBay(item: CargoItem): number {
  if (item.hazard) return 3;
  if (item.kind === 'cold') return 2;
  if (item.kind === 'live' || item.kind === 'fragile') return 1;
  return item.mass >= CARGO_MASS_LIMIT ? 4 : 1;
}

/** 判定一次投放：正确给分（含速度分与连击加成），错误只给货损 */
export function judgeAssignment(
  item: CargoItem,
  bay: number,
  secondsLeft: number,
  combo: number,
): CargoVerdict {
  const want = expectedBay(item);
  if (bay === want) {
    const speed = Math.max(5, Math.round(Math.max(0, secondsLeft) * 3));
    const comboBonus = Math.min(40, Math.max(0, combo) * 4);
    const points = 20 + speed + comboBonus;
    return {
      correct: true,
      points,
      integrity: 0,
      reason: `${item.name} → ${want} 号舱 · 合规 +${points}`,
    };
  }
  return {
    correct: false,
    points: 0,
    integrity: CARGO_MISLOAD_PENALTY,
    reason: `${item.name} 应入 ${want} 号舱，误投 ${bay} 号舱 · 货损 −${CARGO_MISLOAD_PENALTY}`,
  };
}

/** 结算成就：拿到 300 分点亮「装载长」 */
export function cargoAchievements(state: CargoState): string[] {
  return state.score >= CARGO_MASTER_SCORE ? ['cargo-master'] : [];
}

function pushLog(log: string[], line: string): string[] {
  return [...log, line].slice(-4);
}

/** 抽取下一个货箱 */
function drawItem(seed: number, wave: number, seq: number): { item: CargoItem; rng: number } {
  let rng = seed;
  const [rollKind, s1] = randStep(rng);
  const [rollName, s2] = randStep(s1);
  const [rollMass, s3] = randStep(s2);
  const [rollHazard, s4] = randStep(s3);
  rng = s4;

  const kinds: CargoKind[] = ['standard', 'standard', 'cold', 'live', 'fragile'];
  const kind = kinds[Math.min(kinds.length - 1, Math.floor(rollKind * kinds.length))];
  const kindMeta = KIND_META[kind];
  const name =
    kindMeta.names[Math.min(kindMeta.names.length - 1, Math.floor(rollName * kindMeta.names.length))];
  const mass = Math.round(kindMeta.mass[0] + rollMass * (kindMeta.mass[1] - kindMeta.mass[0]));
  const hazard = rollHazard < Math.min(0.45, 0.18 + wave * 0.03);
  return { item: { id: seq, name, kind, mass, hazard }, rng };
}

export function createCargoState(seed = 1): CargoState {
  const drawn = drawItem(seed >>> 0, 1, 1);
  return {
    status: 'running',
    wave: 1,
    integrity: 100,
    score: 0,
    combo: 0,
    bestCombo: 0,
    correct: 0,
    wrong: 0,
    served: 0,
    timeLeft: itemTime(1),
    elapsed: 0,
    item: drawn.item,
    log: ['装卸区已清空，等待第 1 波货箱'],
    rng: drawn.rng,
    seq: 2,
  };
}

/** 处理完一件后推进：计件、换波、抽取下一件、判定是否结束 */
function advance(state: CargoState, events: CargoEvent[]): CargoState {
  const next: CargoState = { ...state, served: state.served + 1 };
  const wave = waveOf(next.served);
  if (wave !== next.wave) {
    next.wave = wave;
    next.log = pushLog(next.log, `第 ${wave} 波进场 · 单件决策时间收紧到 ${itemTime(wave).toFixed(1)}s`);
    events.push('wave');
  }
  const drawn = drawItem(next.rng, next.wave, next.seq);
  next.item = drawn.item;
  next.rng = drawn.rng;
  next.seq += 1;
  next.timeLeft = itemTime(next.wave);
  if (next.integrity <= 0) {
    next.status = 'over';
    events.push('over');
  }
  return next;
}

/** 时间流逝：当前货箱超时视为一次错误投放 */
export function stepCargo(state: CargoState, dt: number): CargoResult {
  if (state.status === 'over' || !state.item) return { state, events: [] };
  // 步长由调用方决定（组件固定 0.1s）；这里只挡掉负数与非有限值，
  // 不做上限截断 —— 否则「一次推进超过剩余时间」就不再触发超时，纯函数语义会被破坏。
  const step = Number.isFinite(dt) ? Math.max(0, dt) : 0;
  const next: CargoState = { ...state, elapsed: state.elapsed + step, timeLeft: state.timeLeft - step };
  const events: CargoEvent[] = [];
  if (next.timeLeft > 0) return { state: next, events };

  next.integrity = Math.max(0, next.integrity - CARGO_TIMEOUT_PENALTY);
  next.combo = 0;
  next.wrong += 1;
  next.log = pushLog(next.log, `超时 · ${state.item.name} 滞留装卸区 · 货损 −${CARGO_TIMEOUT_PENALTY}`);
  events.push('wrong');
  return { state: advance(next, events), events };
}

/** 把当前货箱投放到指定舱位 */
export function assignCargo(state: CargoState, bay: number): CargoResult {
  if (state.status === 'over' || !state.item) return { state, events: [] };
  const verdict = judgeAssignment(state.item, bay, state.timeLeft, state.combo);
  const events: CargoEvent[] = [];
  const next: CargoState = { ...state, log: pushLog(state.log, verdict.reason) };
  if (verdict.correct) {
    next.score = state.score + verdict.points;
    next.combo = state.combo + 1;
    next.bestCombo = Math.max(state.bestCombo, next.combo);
    next.correct = state.correct + 1;
    events.push('correct');
  } else {
    next.integrity = Math.max(0, state.integrity - verdict.integrity);
    next.combo = 0;
    next.wrong = state.wrong + 1;
    events.push('wrong');
  }
  return { state: advance(next, events), events, verdict };
}

/** 音效守卫：AudioContext 从未创建时 sfx 内部会直接 return，这里再兜一层 */
function play(effect: () => void): void {
  try {
    effect();
  } catch {
    // 音频不可用：静默降级
  }
}

type CargoPhase = 'brief' | 'running' | 'over';

export default function CargoGame({ onFinish, onExit, hullIntegrity }: MiniGameProps) {
  const [phase, setPhase] = useState<CargoPhase>('brief');
  const [view, setView] = useState<CargoState>(() => createCargoState(1));

  // 权威状态放在 ref 里：定时器与键盘事件都读它，避免闭包读到过期的 React 状态
  const stateRef = useRef<CargoState>(view);
  const phaseRef = useRef<CargoPhase>('brief');
  const finishedRef = useRef(false);
  const onFinishRef = useRef(onFinish);

  useEffect(() => {
    phaseRef.current = phase;
  }, [phase]);

  useEffect(() => {
    onFinishRef.current = onFinish;
  }, [onFinish]);

  const applyEvents = useCallback((events: readonly CargoEvent[]) => {
    for (const event of events) {
      switch (event) {
        case 'correct':
          play(sfx.pickup);
          break;
        case 'wrong':
          play(sfx.deny);
          break;
        case 'wave':
          play(sfx.pulse);
          break;
        case 'over':
          play(sfx.alarm);
          break;
        default:
          break;
      }
    }
  }, []);

  const finishRun = useCallback((final: CargoState) => {
    if (finishedRef.current) return;
    finishedRef.current = true;
    const badges = cargoAchievements(final);
    if (badges.length > 0) play(sfx.achievement);
    for (const badge of badges) unlock(badge);
    setView(final);
    setPhase('over');
    onFinishRef.current(final.score);
  }, []);

  const commit = useCallback(
    (result: CargoResult) => {
      if (result.events.length === 0) return;
      stateRef.current = result.state;
      applyEvents(result.events);
      setView(result.state);
      if (result.state.status === 'over') finishRun(result.state);
    },
    [applyEvents, finishRun],
  );

  const assign = useCallback(
    (bay: number) => {
      if (phaseRef.current !== 'running') return;
      play(sfx.beep);
      commit(assignCargo(stateRef.current, bay));
    },
    [commit],
  );

  const startRun = useCallback(() => {
    const seed = (Date.now() ^ 0x2f9c1) >>> 0;
    const fresh = createCargoState(seed);
    stateRef.current = fresh;
    finishedRef.current = false;
    setView(fresh);
    setPhase('running');
    play(sfx.open);
  }, []);

  const handleExit = useCallback(() => {
    play(sfx.close);
    onExit();
  }, [onExit]);

  // 决策倒计时：100ms 一跳，超时由 stepCargo 判定
  useEffect(() => {
    if (phase !== 'running') return undefined;
    const timer = window.setInterval(() => {
      commit(stepCargo(stateRef.current, 0.1));
    }, 100);
    return () => window.clearInterval(timer);
  }, [commit, phase]);

  // 数字键 1..4 直接投放
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (phaseRef.current !== 'running') return;
      const index = Number.parseInt(event.key, 10);
      if (!Number.isFinite(index) || index < 1 || index > CARGO_BAYS.length) return;
      event.preventDefault();
      assign(CARGO_BAYS[index - 1].id);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [assign]);

  const item = view.item;
  const kindMeta = item ? KIND_META[item.kind] : null;
  const timeRatio = item ? Math.round((Math.max(0, view.timeLeft) / itemTime(view.wave)) * 100) : 0;
  const integrity = hullIntegrity === null ? null : Math.round(clamp(hullIntegrity, 0, 100));

  return (
    <section className="mg-root mg-cargo" aria-label={`${meta.name} · ${meta.code}`}>
      <header className="mg-head">
        <div className="mg-head-main">
          <span className="mg-code">{meta.code}</span>
          <h2 className="mg-title">{meta.name}</h2>
        </div>
        <div className="mg-head-side">
          <span className="mg-chip">第 {view.wave} 波</span>
          {integrity === null ? null : <span className="mg-chip">舰体实况 {integrity}%</span>}
          <button type="button" className="mg-btn is-ghost" onClick={handleExit}>
            返回
          </button>
        </div>
      </header>

      <div className="mg-cargo-stage">
        <div className="mg-cargo-board">
          <div className="mg-cargo-card">
            {item && kindMeta ? (
              <>
                <div className="mg-cargo-card-head">
                  <span className="mg-cargo-name">{item.name}</span>
                  {item.hazard ? <span className="mg-badge is-hazard">危险品</span> : null}
                </div>
                <dl className="mg-telemetry">
                  <div>
                    <dt>类别</dt>
                    <dd>{kindMeta.label}</dd>
                  </div>
                  <div>
                    <dt>质量</dt>
                    <dd>{item.mass} 吨</dd>
                  </div>
                  <div>
                    <dt>决策余时</dt>
                    <dd>{Math.max(0, view.timeLeft).toFixed(1)}s</dd>
                  </div>
                </dl>
                <div
                  className="mg-bar"
                  role="progressbar"
                  aria-label="当前货箱剩余决策时间"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={timeRatio}
                >
                  <div
                    className={`mg-bar-fill ${view.timeLeft <= 2 ? 'is-err' : 'is-warn'}`}
                    style={{ width: `${timeRatio}%` }}
                  />
                </div>
              </>
            ) : (
              <span className="mg-cargo-name">装卸区空闲</span>
            )}
          </div>

          <div className="mg-cargo-bays" role="group" aria-label="货舱分派">
            {CARGO_BAYS.map((bay) => (
              <button
                key={bay.id}
                type="button"
                className="mg-cargo-bay"
                aria-label={`${bay.id} 号舱 ${bay.name}，接收 ${bay.accepts}`}
                onClick={() => assign(bay.id)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') event.preventDefault();
                }}
                disabled={phase !== 'running'}
              >
                <span className="mg-cargo-bay-no">{bay.id}</span>
                <span className="mg-cargo-bay-name">{bay.name}</span>
                <span className="mg-cargo-bay-hint">{bay.accepts}</span>
              </button>
            ))}
          </div>
        </div>

        {phase === 'brief' ? (
          <div className="mg-overlay">
            <h3 className="mg-overlay-title">调度简报</h3>
            <p className="mg-brief">{meta.brief}</p>
            <p className="mg-scoring">{meta.scoring}</p>
            <button type="button" className="mg-btn is-primary" onClick={startRun}>
              开始调度
            </button>
          </div>
        ) : null}

        {phase === 'over' ? (
          <div className="mg-overlay">
            <h3 className="mg-overlay-title">货损临界 · 调度中止</h3>
            <p className="mg-brief">
              得分 {view.score} · 正确 {view.correct} 件 · 错误 {view.wrong} 件 · 最高连击 {view.bestCombo}
            </p>
            {view.score >= CARGO_MASTER_SCORE ? (
              <p className="mg-note">已达成「装载长」：调度得分突破 {CARGO_MASTER_SCORE}。</p>
            ) : null}
            <div className="mg-overlay-actions">
              <button type="button" className="mg-btn is-primary" onClick={startRun}>
                重新调度
              </button>
              <button type="button" className="mg-btn" onClick={handleExit}>
                返回
              </button>
            </div>
          </div>
        ) : null}
      </div>

      <div className="mg-cargo-panel">
        <div className="mg-bar-row">
          <span className="mg-bar-label">货损完整度</span>
          <div
            className="mg-bar"
            role="progressbar"
            aria-label="货损完整度"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(view.integrity)}
          >
            <div
              className={`mg-bar-fill ${view.integrity <= 35 ? 'is-err' : 'is-ok'}`}
              style={{ width: `${view.integrity}%` }}
            />
          </div>
          <span className="mg-bar-value">{Math.round(view.integrity)}%</span>
        </div>

        <dl className="mg-telemetry">
          <div>
            <dt>调度得分</dt>
            <dd>{view.score}</dd>
          </div>
          <div>
            <dt>连击</dt>
            <dd>{view.combo}</dd>
          </div>
          <div>
            <dt>已调度</dt>
            <dd className="mg-cargo-served">{view.served} 件</dd>
          </div>
          <div>
            <dt>正确率</dt>
            <dd>
              {view.correct + view.wrong > 0
                ? Math.round((view.correct / (view.correct + view.wrong)) * 100)
                : 100}
              %
            </dd>
          </div>
        </dl>

        <ul className="mg-cargo-log" aria-live="polite">
          {view.log.map((line, index) => (
            <li key={`${index}-${line}`}>{line}</li>
          ))}
        </ul>
      </div>

      <section className="mg-help" aria-label="装载规则与操作说明">
        <h3 className="mg-help-title">装载规则（自上而下按优先级判定）</h3>
        <ol className="mg-help-list">
          <li>危险品 → 3 号隔离舱；危险品优先于其他一切规则。</li>
          <li>冷链货物 → 2 号冷藏舱（冷链优先于重量）。</li>
          <li>活体货物 / 精密仪器 → 1 号恒温货舱。</li>
          <li>其余普通货：单件 ≥ 40 吨 → 4 号重载舱，否则 → 1 号恒温货舱。</li>
          <li>操作：点击舱位按钮，或直接按数字键 1 / 2 / 3 / 4；每件货箱都有决策倒计时。</li>
        </ol>
      </section>
    </section>
  );
}
