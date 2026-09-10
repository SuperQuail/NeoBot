// circuit.tsx —— 配电回路修复（纯 React + SVG，无 canvas / 无 three.js）
//
// 可解性保证：
//   关卡不是「随便撒一把管道」，而是先在网格上生成一棵以反应堆为根、覆盖全部输出端口的
//   随机生成树（随机化 DFS + 剪掉死枝），把每个节点的开口位掩码记为该格的「已解朝向」；
//   然后再把可旋转的格子打乱，并把每格的打乱量记录在 cell.scramble 里。
//   因此「把所有格子的 rot 归零」永远是本关的一个解，而 resetLevel 能精确回到打乱后的初始态。
//
// 纯逻辑（createLevel / applyMove / isSolved / solutionMoves / poweredNodes）全部导出，
// 不依赖 DOM，可直接单测。

import { useCallback, useEffect, useMemo, useState, type ReactElement } from 'react';
import { sfx } from '../../core/sound';
import { unlock } from '../../core/store';
import './minigames.css';

export interface MiniGameProps {
  /** 一次检修结束时回调，父级负责存档与提示 */
  onFinish: (score: number) => void;
  /** 关闭小游戏并回到自由巡航 */
  onExit: () => void;
  /** 舰体完整度 0..100（父级由真实系统指标换算），不可用时为 null */
  hullIntegrity: number | null;
}

export const meta = {
  key: 'circuit',
  name: '配电回路修复',
  code: 'PWR-FIX',
  brief: '旋转配电节点，把反应堆电力送到全部输出端口，共 3 段回路。',
  scoring: '每段得分 = 240 + 段序号×140 + 剩余秒数×4 + (标准步数 − 实际步数)×8；超时本段无分且检修中止。',
} as const;

/** 分段数（难度递增：5×5 → 6×6 → 7×7） */
export const CIRCUIT_ROUNDS = 3;

/** 方向编号：0=上(北) 1=右(东) 2=下(南) 3=左(西)，顺时针 */
const DIRS: ReadonlyArray<readonly [number, number]> = [
  [0, -1],
  [1, 0],
  [0, 1],
  [-1, 0],
];

const clamp = (value: number, lo: number, hi: number): number => Math.min(hi, Math.max(lo, value));

/** mulberry32 单步：状态进、状态出，保证 createLevel 可复现 */
function randStep(seed: number): [number, number] {
  const next = (seed + 0x6d2b79f5) >>> 0;
  let t = next;
  t = Math.imul(t ^ (t >>> 15), t | 1);
  t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
  return [((t ^ (t >>> 14)) >>> 0) / 4294967296, next];
}

export type CircuitTileKind = 'empty' | 'cap' | 'straight' | 'elbow' | 'tee' | 'cross';

export interface CircuitCell {
  /** 已解状态下四个方向的开口位掩码（bit d = 方向 d 有开口） */
  solution: number;
  /** 当前旋转量，单位 90°，顺时针为正 */
  rot: number;
  /** 反应堆 / 输出端口 / 空槽 / 十字枢纽：不可旋转 */
  fixed: boolean;
  /** 生成时记录的打乱量，「重置」按它精确还原 */
  scramble: number;
}

export interface CircuitLevel {
  seed: number;
  round: number;
  size: number;
  /** 反应堆馈电口所在格索引 */
  source: number;
  /** 输出端口格索引 */
  sinks: number[];
  cells: CircuitCell[];
  moves: number;
  /** 参考解步数（全部逆时针归零的步数），用于计分与 HUD */
  par: number;
}

export interface CircuitMove {
  index: number;
  /** 1 = 顺时针，-1 = 逆时针 */
  dir: 1 | -1;
}

/** 顺时针旋转 90°×rot 后的开口掩码 */
export function rotateMask(mask: number, rot: number): number {
  const r = ((rot % 4) + 4) % 4;
  return ((mask << r) | (mask >>> (4 - r))) & 0b1111;
}

/** 当前实际开口 */
export function openingsOf(cell: CircuitCell): number {
  return rotateMask(cell.solution, cell.rot);
}

export function hasOpening(mask: number, dir: number): boolean {
  return (mask & (1 << dir)) !== 0;
}

function bitCount(mask: number): number {
  let count = 0;
  for (let dir = 0; dir < 4; dir += 1) if (hasOpening(mask, dir)) count += 1;
  return count;
}

function firstDir(mask: number): number {
  for (let dir = 0; dir < 4; dir += 1) if (hasOpening(mask, dir)) return dir;
  return 0;
}

/** 由开口形状推断管道类型（渲染与读屏文案共用） */
export function cellKind(mask: number): CircuitTileKind {
  const count = bitCount(mask);
  if (count === 0) return 'empty';
  if (count === 1) return 'cap';
  if (count === 4) return 'cross';
  if (count === 3) return 'tee';
  return mask === 0b0101 || mask === 0b1010 ? 'straight' : 'elbow';
}

/** 每段的限时：90 / 80 / 70 秒 */
export function roundSeconds(round: number): number {
  return Math.max(45, 100 - round * 10);
}

/** 反应堆已通电的格子集合：从馈电口出发，只走「双方都有对接开口」的边 */
export function poweredNodes(level: CircuitLevel): Set<number> {
  const powered = new Set<number>([level.source]);
  const stack: number[] = [level.source];
  while (stack.length > 0) {
    const index = stack.pop();
    if (index === undefined) break;
    const x = index % level.size;
    const y = Math.floor(index / level.size);
    const mask = openingsOf(level.cells[index]);
    for (let dir = 0; dir < 4; dir += 1) {
      if (!hasOpening(mask, dir)) continue;
      const nx = x + DIRS[dir][0];
      const ny = y + DIRS[dir][1];
      if (nx < 0 || ny < 0 || nx >= level.size || ny >= level.size) continue;
      const neighbour = ny * level.size + nx;
      if (powered.has(neighbour)) continue;
      if (!hasOpening(openingsOf(level.cells[neighbour]), (dir + 2) % 4)) continue;
      powered.add(neighbour);
      stack.push(neighbour);
    }
  }
  return powered;
}

/** 通关判定：全部输出端口通电 */
export function isSolved(level: CircuitLevel): boolean {
  const powered = poweredNodes(level);
  return level.sinks.every((sink) => powered.has(sink));
}

/** 把每格逆时针转回 0 度的参考解（一定能让 isSolved 为真） */
export function solutionMoves(level: CircuitLevel): CircuitMove[] {
  const moves: CircuitMove[] = [];
  level.cells.forEach((cell, index) => {
    if (cell.fixed || cell.rot === 0) return;
    for (let step = 0; step < cell.rot; step += 1) moves.push({ index, dir: -1 });
  });
  return moves;
}

/** 执行一次旋转；不可旋转的格子原样返回（父级据此放「操作无效」音） */
export function applyMove(level: CircuitLevel, move: CircuitMove): CircuitLevel {
  const cell = level.cells[move.index];
  if (!cell || cell.fixed) return level;
  const cells = level.cells.slice();
  cells[move.index] = { ...cell, rot: (((cell.rot + move.dir) % 4) + 4) % 4 };
  return { ...level, cells, moves: level.moves + 1 };
}

/** 重置：按记录的打乱量精确还原初始盘面（步数归零） */
export function resetLevel(level: CircuitLevel): CircuitLevel {
  return {
    ...level,
    cells: level.cells.map((cell) => ({ ...cell, rot: cell.scramble })),
    moves: 0,
  };
}

/**
 * 生成第 round 段回路。同一 seed+round 必定得到同一盘面（可复现、可单测）。
 */
export function createLevel(seed: number, round = 1): CircuitLevel {
  const size = clamp(4 + round, 5, 8);
  const sinkCount = clamp(1 + round, 2, 4);
  const source = Math.floor(size / 2) * size; // 左壁中点
  const sinkRows: number[] = [];
  for (let index = 0; index < sinkCount; index += 1) {
    const row = sinkCount === 1 ? Math.floor(size / 2) : Math.round((index * (size - 1)) / (sinkCount - 1));
    if (!sinkRows.includes(row)) sinkRows.push(row);
  }
  const sinks = sinkRows.map((row) => row * size + (size - 1));

  // 1) 随机化 DFS 生成覆盖全网格的生成树，open[i] 记录每个格子的开口
  let rng = (seed ^ (round * 0x9e3779b9)) >>> 0;
  const open = new Array<number>(size * size).fill(0);
  const visited = new Array<boolean>(size * size).fill(false);
  const stack: number[] = [source];
  visited[source] = true;
  while (stack.length > 0) {
    const index = stack[stack.length - 1];
    const x = index % size;
    const y = Math.floor(index / size);
    const candidates: Array<[number, number]> = [];
    for (let dir = 0; dir < 4; dir += 1) {
      const nx = x + DIRS[dir][0];
      const ny = y + DIRS[dir][1];
      if (nx < 0 || ny < 0 || nx >= size || ny >= size) continue;
      const neighbour = ny * size + nx;
      if (visited[neighbour]) continue;
      candidates.push([neighbour, dir]);
    }
    if (candidates.length === 0) {
      stack.pop();
      continue;
    }
    const [roll, nextSeed] = randStep(rng);
    rng = nextSeed;
    const [neighbour, dir] =
      candidates[Math.min(candidates.length - 1, Math.floor(roll * candidates.length))];
    visited[neighbour] = true;
    open[index] |= 1 << dir;
    open[neighbour] |= 1 << ((dir + 2) % 4);
    stack.push(neighbour);
  }

  // 2) 剪掉死枝：只保留反应堆到输出端口之间的回路，让每一格的朝向都有意义
  const sinkSet = new Set(sinks);
  let pruned = true;
  while (pruned) {
    pruned = false;
    for (let index = 0; index < size * size; index += 1) {
      if (index === source || sinkSet.has(index)) continue;
      if (open[index] === 0 || bitCount(open[index]) !== 1) continue;
      const dir = firstDir(open[index]);
      const nx = (index % size) + DIRS[dir][0];
      const ny = Math.floor(index / size) + DIRS[dir][1];
      if (nx >= 0 && ny >= 0 && nx < size && ny < size) {
        open[ny * size + nx] &= ~(1 << ((dir + 2) % 4));
      }
      open[index] = 0;
      pruned = true;
    }
  }

  // 3) 打乱：只旋转「转了确实会变样」的格子，并记录打乱量
  const cells: CircuitCell[] = [];
  for (let index = 0; index < size * size; index += 1) {
    const solution = open[index];
    const isPort = index === source || sinkSet.has(index);
    const options: number[] = [];
    if (!isPort && solution !== 0) {
      for (let rot = 1; rot < 4; rot += 1) if (rotateMask(solution, rot) !== solution) options.push(rot);
    }
    let scramble = 0;
    if (options.length > 0) {
      const [roll, nextSeed] = randStep(rng);
      rng = nextSeed;
      scramble = options[Math.min(options.length - 1, Math.floor(roll * options.length))];
    }
    cells.push({ solution, rot: scramble, fixed: isPort || options.length === 0, scramble });
  }

  const level: CircuitLevel = { seed, round, size, source, sinks, cells, moves: 0, par: 0 };
  level.par = solutionMoves(level).length;

  // 4) 极小概率打乱后恰好已通电：再转一格，保证开局一定需要动手（可解性不受影响）
  if (isSolved(level)) {
    const index = cells.findIndex((cell) => !cell.fixed);
    if (index >= 0) {
      cells[index] = {
        ...cells[index],
        rot: (cells[index].rot + 1) % 4,
        scramble: (cells[index].scramble + 1) % 4,
      };
      level.par = solutionMoves(level).length;
    }
  }
  return level;
}

/** 单段得分：基础分 + 剩余时间 + 省下的步数 */
export function repairScore(round: number, timeLeft: number, moves: number, par: number): number {
  const base = 240 + round * 140;
  const timeBonus = Math.round(Math.max(0, timeLeft) * 4);
  const moveBonus = Math.max(0, par - moves) * 8;
  return base + timeBonus + moveBonus;
}

/** 音效守卫：AudioContext 从未创建时 sfx 内部会直接 return，这里再兜一层 */
function play(effect: () => void): void {
  try {
    effect();
  } catch {
    // 音频不可用：静默降级
  }
}

const TILE_LABELS: Record<CircuitTileKind, string> = {
  empty: '空槽',
  cap: '单端接线',
  straight: '直通管道',
  elbow: '弯头管道',
  tee: '三通管道',
  cross: '十字枢纽',
};

/** 读屏/长按提示用的格子描述 */
export function cellLabel(level: CircuitLevel, index: number, powered: boolean): string {
  const cell = level.cells[index];
  const row = Math.floor(index / level.size) + 1;
  const col = (index % level.size) + 1;
  const kind = cellKind(openingsOf(cell));
  const port =
    index === level.source ? '反应堆馈电口' : level.sinks.includes(index) ? '输出端口' : TILE_LABELS[kind];
  if (cell.fixed) return `第 ${row} 行第 ${col} 列 · ${port} · 固定不可旋转`;
  return `第 ${row} 行第 ${col} 列 · ${port} · ${powered ? '已通电' : '未通电'} · 回车顺时针旋转，方向键可双向旋转`;
}

/** 单元格图形：中心枢纽 + 各方向支管 */
function TileArt({ mask }: { mask: number }) {
  const stubs: ReactElement[] = [];
  for (let dir = 0; dir < 4; dir += 1) {
    if (!hasOpening(mask, dir)) continue;
    stubs.push(
      <line
        key={dir}
        className="mg-circuit-pipe"
        x1={50}
        y1={50}
        x2={50 + DIRS[dir][0] * 50}
        y2={50 + DIRS[dir][1] * 50}
      />,
    );
  }
  return (
    <svg className="mg-circuit-art" viewBox="0 0 100 100" aria-hidden="true">
      {stubs}
      <circle className="mg-circuit-hub" cx={50} cy={50} r={mask === 0 ? 5 : 11} />
    </svg>
  );
}

type CircuitPhase = 'brief' | 'running' | 'clear' | 'over';

export default function CircuitGame({ onFinish, onExit, hullIntegrity }: MiniGameProps) {
  const [seed, setSeed] = useState(() => (Date.now() ^ 0x5f3a) >>> 0);
  const [round, setRound] = useState(1);
  const [level, setLevel] = useState<CircuitLevel>(() => createLevel(1, 1));
  const [phase, setPhase] = useState<CircuitPhase>('brief');
  const [timeLeft, setTimeLeft] = useState(() => roundSeconds(1));
  const [total, setTotal] = useState(0);
  const [lastGain, setLastGain] = useState(0);
  const [message, setMessage] = useState('等待接入配电网络');

  const powered = useMemo(() => poweredNodes(level), [level]);
  const poweredSinks = level.sinks.filter((sink) => powered.has(sink)).length;
  const integrity = hullIntegrity === null ? null : Math.round(clamp(hullIntegrity, 0, 100));

  /** 开始（或重开）一整轮检修 */
  const startRun = useCallback(() => {
    const nextSeed = (Date.now() ^ 0x5f3a) >>> 0;
    setSeed(nextSeed);
    setRound(1);
    setLevel(createLevel(nextSeed, 1));
    setTotal(0);
    setLastGain(0);
    setTimeLeft(roundSeconds(1));
    setMessage('第 1 段回路已接入，等待修复');
    setPhase('running');
    play(sfx.open);
  }, []);

  /** 完成当前段 */
  const completeRound = useCallback(
    (solved: CircuitLevel) => {
      const gain = repairScore(round, timeLeft, solved.moves, solved.par);
      const sum = total + gain;
      setLevel(solved);
      setLastGain(gain);
      setTotal(sum);
      setMessage(`第 ${round} 段回路修复完成，本段 +${gain} 分`);
      play(sfx.achievement);
      unlock('first-repair');
      if (round >= CIRCUIT_ROUNDS) {
        setPhase('over');
        onFinish(sum);
      } else {
        setPhase('clear');
      }
    },
    [onFinish, round, timeLeft, total],
  );

  const rotate = useCallback(
    (index: number, dir: 1 | -1) => {
      if (phase !== 'running') return;
      const next = applyMove(level, { index, dir });
      if (next === level) {
        setMessage('该节点固定在舱壁上，无法旋转');
        play(sfx.deny);
        return;
      }
      play(sfx.beep);
      if (isSolved(next)) completeRound(next);
      else setLevel(next);
    },
    [completeRound, level, phase],
  );

  const continueRound = useCallback(() => {
    const nextRound = round + 1;
    setRound(nextRound);
    setLevel(createLevel(seed, nextRound));
    setTimeLeft(roundSeconds(nextRound));
    setMessage(`第 ${nextRound} 段回路已接入，等待修复`);
    setPhase('running');
    play(sfx.pulse);
  }, [round, seed]);

  const abortRun = useCallback(() => {
    setPhase('over');
    setMessage('检修中止：回路超时，配电网络仍处于降级状态');
    play(sfx.alarm);
    onFinish(total);
  }, [onFinish, total]);

  // 限时：只在检修进行中走秒
  useEffect(() => {
    if (phase !== 'running') return undefined;
    const timer = window.setInterval(() => setTimeLeft((left) => Math.max(0, left - 1)), 1000);
    return () => window.clearInterval(timer);
  }, [phase]);

  useEffect(() => {
    if (phase === 'running' && timeLeft <= 0) abortRun();
  }, [abortRun, phase, timeLeft]);

  const handleExit = useCallback(() => {
    play(sfx.close);
    onExit();
  }, [onExit]);

  const handleReset = useCallback(() => {
    setLevel((current) => resetLevel(current));
    setMessage('盘面已按记录的打乱方案还原');
    play(sfx.beep);
  }, []);

  const timeRatio = Math.round((timeLeft / roundSeconds(round)) * 100);

  return (
    <section className="mg-root mg-circuit" aria-label={`${meta.name} · ${meta.code}`}>
      <header className="mg-head">
        <div className="mg-head-main">
          <span className="mg-code">{meta.code}</span>
          <h2 className="mg-title">{meta.name}</h2>
        </div>
        <div className="mg-head-side">
          <span className="mg-chip">
            第 {round}/{CIRCUIT_ROUNDS} 段
          </span>
          {integrity === null ? null : <span className="mg-chip">舰体实况 {integrity}%</span>}
          <button type="button" className="mg-btn is-ghost" onClick={handleExit}>
            返回
          </button>
        </div>
      </header>

      <div className="mg-circuit-stage">
        <div
          className="mg-circuit-grid"
          role="group"
          aria-label="配电网络拓扑"
          style={{ gridTemplateColumns: `repeat(${level.size}, minmax(0, 1fr))` }}
        >
          {level.cells.map((cell, index) => {
            const mask = openingsOf(cell);
            const isSource = index === level.source;
            const isSink = level.sinks.includes(index);
            const live = powered.has(index);
            const classes = [
              'mg-circuit-cell',
              `is-${cellKind(mask)}`,
              isSource ? 'is-source' : '',
              isSink ? 'is-sink' : '',
              isSink && live ? 'is-powered' : '',
              live && !isSink ? 'is-live' : '',
              cell.fixed ? 'is-fixed' : '',
            ]
              .filter(Boolean)
              .join(' ');
            return (
              <button
                key={index}
                type="button"
                className={classes}
                aria-label={cellLabel(level, index, live)}
                disabled={phase !== 'running'}
                onClick={() => rotate(index, 1)}
                onContextMenu={(event) => {
                  event.preventDefault();
                  rotate(index, -1);
                }}
                onKeyDown={(event) => {
                  if (event.key === 'ArrowRight' || event.key === 'ArrowUp') {
                    event.preventDefault();
                    rotate(index, 1);
                  } else if (event.key === 'ArrowLeft' || event.key === 'ArrowDown') {
                    event.preventDefault();
                    rotate(index, -1);
                  }
                }}
              >
                <TileArt mask={mask} />
                {isSource ? <span className="mg-circuit-tag">堆</span> : null}
                {isSink ? <span className="mg-circuit-tag">{live ? '通电' : '输出'}</span> : null}
              </button>
            );
          })}
        </div>

        {phase === 'brief' ? (
          <div className="mg-overlay">
            <h3 className="mg-overlay-title">检修简报</h3>
            <p className="mg-brief">{meta.brief}</p>
            <p className="mg-scoring">{meta.scoring}</p>
            <button type="button" className="mg-btn is-primary" onClick={startRun}>
              开始检修
            </button>
          </div>
        ) : null}

        {phase === 'clear' ? (
          <div className="mg-overlay">
            <h3 className="mg-overlay-title">第 {round} 段修复完成</h3>
            <p className="mg-brief">
              本段 +{lastGain} 分 · 累计 {total} 分 · 用 {level.moves} 步（标准 {level.par} 步）
            </p>
            <button type="button" className="mg-btn is-primary" onClick={continueRound}>
              接入第 {round + 1} 段
            </button>
          </div>
        ) : null}

        {phase === 'over' ? (
          <div className="mg-overlay">
            <h3 className="mg-overlay-title">
              {poweredSinks === level.sinks.length ? '全部回路贯通' : '检修中止'}
            </h3>
            <p className="mg-brief">
              总得分 {total} 分 · 已完成 {round >= CIRCUIT_ROUNDS ? CIRCUIT_ROUNDS : round - 1} 段修复
            </p>
            <div className="mg-overlay-actions">
              <button type="button" className="mg-btn is-primary" onClick={startRun}>
                重新检修
              </button>
              <button type="button" className="mg-btn" onClick={handleExit}>
                返回
              </button>
            </div>
          </div>
        ) : null}
      </div>

      <div className="mg-circuit-panel">
        <div className="mg-bar-row">
          <span className="mg-bar-label">剩余时间</span>
          <div
            className="mg-bar"
            role="progressbar"
            aria-label="本段剩余时间"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={timeRatio}
          >
            <div
              className={`mg-bar-fill ${timeLeft <= 15 ? 'is-err' : 'is-ok'}`}
              style={{ width: `${timeRatio}%` }}
            />
          </div>
          <span className="mg-bar-value">{timeLeft}s</span>
        </div>

        <dl className="mg-telemetry">
          <div>
            <dt>输出端口</dt>
            <dd>
              {poweredSinks}/{level.sinks.length}
            </dd>
          </div>
          <div>
            <dt>旋转步数</dt>
            <dd>
              {level.moves} / 标准 {level.par}
            </dd>
          </div>
          <div>
            <dt>累计得分</dt>
            <dd>{total}</dd>
          </div>
          <div>
            <dt>反应堆馈电</dt>
            <dd>{powered.size} 节点</dd>
          </div>
        </dl>

        <p className="mg-circuit-status" aria-live="polite">
          {message}
        </p>

        {phase === 'running' ? (
          <div className="mg-circuit-actions">
            <button type="button" className="mg-btn" onClick={handleReset}>
              重置
            </button>
          </div>
        ) : null}
      </div>

      <section className="mg-help" aria-label="操作说明">
        <h3 className="mg-help-title">操作说明</h3>
        <ul className="mg-help-list">
          <li>点击节点顺时针旋转 90°，右键逆时针；把反应堆「堆」口的电力送到每个「输出」端口。</li>
          <li>键盘：Tab 切换节点，回车顺时针旋转，← ↓ 逆时针、→ ↑ 顺时针（读屏会播报行列与通断状态）。</li>
          <li>只有两端管道都对着彼此时才算接通，通电的回路会亮起青色。</li>
          <li>「重置」按开局记录的打乱方案精确还原，不会重新洗牌。</li>
          <li>每段限时逐段收紧，超时则本段不得分并终止检修。</li>
        </ul>
      </section>
    </section>
  );
}
