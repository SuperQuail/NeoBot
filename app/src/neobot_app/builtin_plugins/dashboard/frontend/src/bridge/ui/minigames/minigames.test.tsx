// minigames.test.tsx —— 三个舰载小游戏的回归测试
//
// 只 import 本目录（./turret ./circuit ./cargo ./index）与 react/testing-library，
// 不依赖其它并行开发的 bridge 模块，因此可以独立运行。
// jsdom 没有 WebGL：炮塔用例显式把 HTMLCanvasElement.prototype.getContext 打桩为 null，
// 用来验证「没有 3D 加速时降级为 HUD 平面模式」这条路径，而不是去测渲染结果。

import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import TurretGame, {
  TURRET_ACE_KILLS,
  TURRET_RUN_SECONDS,
  comboMultiplier,
  createTurretState,
  meta as turretMeta,
  stepTurret,
  turretAchievements,
  type TurretState,
  type TurretTarget,
} from './turret';
import CircuitGame, {
  CIRCUIT_ROUNDS,
  applyMove,
  createLevel,
  isSolved,
  meta as circuitMeta,
  poweredNodes,
  repairScore,
  resetLevel,
  roundSeconds,
  solutionMoves,
  type CircuitLevel,
} from './circuit';
import CargoGame, {
  CARGO_BAYS,
  CARGO_MASTER_SCORE,
  assignCargo,
  cargoAchievements,
  createCargoState,
  expectedBay,
  itemTime,
  judgeAssignment,
  meta as cargoMeta,
  stepCargo,
  type CargoItem,
  type CargoKind,
  type CargoState,
} from './cargo';
import {
  CargoGame as CargoFromIndex,
  CircuitGame as CircuitFromIndex,
  META,
  MINIGAME_COMPONENTS,
  TurretGame as TurretFromIndex,
} from './index';

// ---- WebGL 打桩：jsdom 的 getContext 恒为 null，这里显式化以消除 jsdom 的未实现告警 ----
const realGetContext = HTMLCanvasElement.prototype.getContext;

function stubNoWebGL(): void {
  HTMLCanvasElement.prototype.getContext = (() => null) as typeof HTMLCanvasElement.prototype.getContext;
}

afterEach(() => {
  HTMLCanvasElement.prototype.getContext = realGetContext;
});

function props(): {
  onFinish: ReturnType<typeof vi.fn>;
  onExit: ReturnType<typeof vi.fn>;
  hullIntegrity: number | null;
} {
  return { onFinish: vi.fn(), onExit: vi.fn(), hullIntegrity: 72 };
}

function cargoItem(kind: CargoKind, mass: number, hazard = false): CargoItem {
  return { id: 1, name: '测试货箱', kind, mass, hazard };
}

describe('小游戏公共契约', () => {
  it('桶导出：元数据表与组件表按 key 对齐', () => {
    expect(Object.keys(META).sort()).toEqual(['cargo', 'circuit', 'turret']);
    expect(META.turret.key).toBe('turret');
    expect(META.turret.name).toBe(turretMeta.name);
    expect(META.circuit.code).toBe(circuitMeta.code);
    expect(META.cargo.brief).toBe(cargoMeta.brief);
    for (const key of ['turret', 'circuit', 'cargo'] as const) {
      expect(META[key].name.length).toBeGreaterThan(0);
      expect(META[key].brief.length).toBeGreaterThan(0);
      expect(META[key].scoring.length).toBeGreaterThan(0);
      expect(MINIGAME_COMPONENTS[key]).toBeTruthy();
    }
    expect(TurretFromIndex).toBe(TurretGame);
    expect(CircuitFromIndex).toBe(CircuitGame);
    expect(CargoFromIndex).toBe(CargoGame);
    expect(MINIGAME_COMPONENTS.turret).toBe(TurretGame);
  });

  it('舰炮演习：渲染简报与开始控件，点「返回」触发 onExit 且不结算', () => {
    stubNoWebGL();
    const p = props();
    render(<TurretGame {...p} />);
    expect(screen.getByText(turretMeta.brief)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '开始演习' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '返回' }));
    expect(p.onExit).toHaveBeenCalledTimes(1);
    expect(p.onFinish).not.toHaveBeenCalled();
  });

  it('配电回路：渲染简报与开始控件，点「返回」触发 onExit 且不结算', () => {
    const p = props();
    render(<CircuitGame {...p} />);
    expect(screen.getByText(circuitMeta.brief)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '开始检修' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '返回' }));
    expect(p.onExit).toHaveBeenCalledTimes(1);
    expect(p.onFinish).not.toHaveBeenCalled();
  });

  it('货舱调度：渲染简报与开始控件，点「返回」触发 onExit 且不结算', () => {
    const p = props();
    render(<CargoGame {...p} />);
    expect(screen.getByText(cargoMeta.brief)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '开始调度' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '返回' }));
    expect(p.onExit).toHaveBeenCalledTimes(1);
    expect(p.onFinish).not.toHaveBeenCalled();
  });
});

describe('舰炮演习（HUD 降级路径，无需 WebGL）', () => {
  it('拿不到 WebGL 时不创建 canvas，并提示已切换为平面瞄准模式', () => {
    stubNoWebGL();
    const { container } = render(<TurretGame {...props()} hullIntegrity={64} />);
    expect(container.querySelector('canvas')).toBeNull();
    expect(screen.getByText(/平面瞄准模式/)).toBeInTheDocument();
    expect(screen.getByText('HUD 平面模式')).toBeInTheDocument();
  });

  it('HUD 模式仍可开局，遥测引用传入的真实舰况', () => {
    stubNoWebGL();
    const { container } = render(<TurretGame {...props()} hullIntegrity={64} />);
    fireEvent.click(screen.getByRole('button', { name: '开始演习' }));
    expect(container.querySelector('canvas')).toBeNull();
    expect(screen.getByText('舰体实况')).toBeInTheDocument();
    // 真实舰况 64% 同时出现在「舰体实况」与局部舰体条上
    expect(screen.getAllByText('64%').length).toBeGreaterThan(0);
    // 开局后简报收起，操作提示条出现，返回按钮仍在
    expect(screen.getByText(/鼠标瞄准/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '返回' })).toBeInTheDocument();
  });
});

describe('配电回路：纯逻辑（可解性保证）', () => {
  it('同一 seed + 段号生成的盘面完全一致，且开局必定需要动手', () => {
    const first = createLevel(7, 1);
    const second = createLevel(7, 1);
    expect(first).toEqual(second);
    expect(first.size).toBe(5);
    expect(first.sinks).toHaveLength(2);
    expect(isSolved(first)).toBe(false);
    expect(first.par).toBeGreaterThan(0);
    // 不同 seed 应当给出不同盘面
    expect(createLevel(8, 1)).not.toEqual(first);
  });

  it('任意 seed / 段号的关卡都可由 solutionMoves 解出', () => {
    for (let round = 1; round <= 4; round += 1) {
      for (const seed of [1, 2, 42, 777, 20240921]) {
        const level = createLevel(seed, round);
        let current: CircuitLevel = level;
        for (const move of solutionMoves(level)) current = applyMove(current, move);
        expect(isSolved(current)).toBe(true);
        expect(current.moves).toBe(solutionMoves(level).length);
      }
    }
  });

  it('难度递增：段数越多网格越大、限时越短', () => {
    const first = createLevel(1, 1);
    const last = createLevel(1, CIRCUIT_ROUNDS);
    expect(last.size).toBeGreaterThan(first.size);
    expect(last.sinks.length).toBeGreaterThanOrEqual(first.sinks.length);
    expect(roundSeconds(CIRCUIT_ROUNDS)).toBeLessThan(roundSeconds(1));
  });

  it('固定节点不可旋转，旋转一格只增加一步', () => {
    const level = createLevel(3, 1);
    expect(level.cells[level.source].fixed).toBe(true);
    expect(level.cells[level.sinks[0]].fixed).toBe(true);
    expect(applyMove(level, { index: level.source, dir: 1 })).toBe(level);
    const index = level.cells.findIndex((cell) => !cell.fixed);
    expect(index).toBeGreaterThanOrEqual(0);
    const rotated = applyMove(level, { index, dir: 1 });
    expect(rotated.moves).toBe(1);
    expect(rotated.cells[index].rot).toBe((level.cells[index].rot + 1) % 4);
  });

  it('「重置」按记录的打乱量精确还原初始盘面', () => {
    const level = createLevel(11, 2);
    const scrambled = level.cells.map((cell) => cell.rot);
    let moved = applyMove(level, { index: level.cells.findIndex((cell) => !cell.fixed), dir: 1 });
    moved = applyMove(moved, { index: moved.cells.findIndex((cell) => !cell.fixed), dir: -1 });
    expect(moved.moves).toBe(2);
    const restored = resetLevel(moved);
    expect(restored.cells.map((cell) => cell.rot)).toEqual(scrambled);
    expect(restored.moves).toBe(0);
    expect(isSolved(restored)).toBe(false);
  });

  it('通电集合从反应堆出发，归零后全部输出端口点亮', () => {
    const level = createLevel(5, 1);
    const powered = poweredNodes(level);
    expect(powered.has(level.source)).toBe(true);
    expect(powered.size).toBeLessThanOrEqual(level.cells.length);
    let solved: CircuitLevel = level;
    for (const move of solutionMoves(level)) solved = applyMove(solved, move);
    const solvedPowered = poweredNodes(solved);
    for (const sink of solved.sinks) expect(solvedPowered.has(sink)).toBe(true);
  });

  it('得分随时间余量与省下的步数增加', () => {
    const base = repairScore(1, 30, 20, 20);
    expect(repairScore(1, 40, 20, 20)).toBeGreaterThan(base);
    expect(repairScore(1, 30, 10, 20)).toBeGreaterThan(base);
    expect(repairScore(3, 30, 20, 20)).toBeGreaterThan(base);
    expect(repairScore(1, 0, 99, 20)).toBe(380);
  });
});

describe('货舱调度：纯逻辑（规则与计分）', () => {
  it('装载规则自上而下按优先级判定', () => {
    expect(CARGO_BAYS).toHaveLength(4);
    expect(expectedBay(cargoItem('standard', 12))).toBe(1);
    expect(expectedBay(cargoItem('standard', 39))).toBe(1);
    expect(expectedBay(cargoItem('standard', 40))).toBe(4);
    expect(expectedBay(cargoItem('standard', 55))).toBe(4);
    expect(expectedBay(cargoItem('standard', 55, true))).toBe(3); // 危险品优先于重量
    expect(expectedBay(cargoItem('cold', 55))).toBe(2); // 冷链优先于重量
    expect(expectedBay(cargoItem('cold', 8, true))).toBe(3); // 危险品优先于冷链
    expect(expectedBay(cargoItem('live', 50))).toBe(1);
    expect(expectedBay(cargoItem('fragile', 8))).toBe(1);
  });

  it('正确入舱给分（含速度与连击加成），错误只给货损', () => {
    const item = cargoItem('cold', 6);
    const good = judgeAssignment(item, 2, 6, 3);
    expect(good.correct).toBe(true);
    expect(good.points).toBe(20 + 18 + 12);
    expect(good.integrity).toBe(0);

    const slow = judgeAssignment(item, 2, 0.5, 0);
    expect(slow.correct).toBe(true);
    expect(slow.points).toBeLessThan(good.points);

    const bad = judgeAssignment(item, 1, 6, 5);
    expect(bad.correct).toBe(false);
    expect(bad.points).toBe(0);
    expect(bad.integrity).toBeGreaterThan(0);
    expect(bad.reason).toContain('2 号舱');
  });

  it('正确投放累加得分与连击，错误投放扣货损并清零连击', () => {
    const state = createCargoState(1234);
    const item = state.item;
    expect(item).not.toBeNull();
    const current = item as CargoItem;

    const good = assignCargo(state, expectedBay(current));
    expect(good.events).toContain('correct');
    expect(good.state.score).toBeGreaterThan(0);
    expect(good.state.combo).toBe(1);
    expect(good.state.served).toBe(1);
    expect(good.state.integrity).toBe(100);
    expect(good.state.item).not.toBeNull();

    // 注意：错投的舱位要按「下一件」算 —— good.state.item 已经是新抽出的货箱
    const nextItem = good.state.item as CargoItem;
    const wrongBay = expectedBay(nextItem) === 1 ? 2 : 1;
    const bad = assignCargo(good.state, wrongBay);
    expect(bad.events).toContain('wrong');
    expect(bad.state.integrity).toBe(100 - 12);
    expect(bad.state.combo).toBe(0);
    expect(bad.state.wrong).toBe(1);
    expect(bad.state.served).toBe(2);
  });

  it('超时按错误投放处理，货损归零则调度中止', () => {
    const timedOut = stepCargo(createCargoState(99), itemTime(1) + 0.1);
    expect(timedOut.events).toContain('wrong');
    expect(timedOut.state.integrity).toBe(100 - 12);
    expect(timedOut.state.wrong).toBe(1);

    let current: CargoState = createCargoState(99);
    for (let guard = 0; guard < 20 && current.status === 'running'; guard += 1) {
      const item = current.item as CargoItem;
      current = assignCargo(current, expectedBay(item) === 1 ? 2 : 1).state;
    }
    expect(current.status).toBe('over');
    expect(current.integrity).toBe(0);
    expect(cargoAchievements(current)).toEqual([]);
  });

  it('得分达到 300 才点亮「装载长」', () => {
    const state = createCargoState(7);
    expect(cargoAchievements(state)).toEqual([]);
    expect(cargoAchievements({ ...state, score: CARGO_MASTER_SCORE - 1 })).toEqual([]);
    expect(cargoAchievements({ ...state, score: CARGO_MASTER_SCORE })).toEqual(['cargo-master']);
  });

  it('数字键 1-4 可直接投放，HUD 计件递增', () => {
    const { container } = render(<CargoGame {...props()} hullIntegrity={null} />);
    fireEvent.click(screen.getByRole('button', { name: '开始调度' }));
    const served = container.querySelector('.mg-cargo-served');
    expect(served).toHaveTextContent('0');
    fireEvent.keyDown(window, { key: '1' });
    expect(container.querySelector('.mg-cargo-served')).toHaveTextContent('1');
    expect(screen.getByRole('button', { name: /1 号舱/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /3 号舱/ })).toBeInTheDocument();
  });
});

describe('舰炮演习：纯逻辑（不依赖 WebGL）', () => {
  it('创建状态时继承真实舰况，并保留可玩的局部舰体下限', () => {
    const full = createTurretState(null, 7);
    expect(full.sourceHull).toBe(100);
    expect(full.hull).toBe(100);
    expect(full.timeLeft).toBe(TURRET_RUN_SECONDS);
    expect(full.status).toBe('running');

    const damaged = createTurretState(72, 7);
    expect(damaged.sourceHull).toBe(72);
    expect(damaged.hull).toBe(72);
    // 真实舰况过低时局部舰体也不会一开始就归零
    expect(createTurretState(4, 7).hull).toBe(20);
    expect(createTurretState(140, 7).hull).toBe(100);
  });

  it('stepTurret 是纯函数：不改动入参状态', () => {
    const before = createTurretState(88, 3);
    const snapshot = createTurretState(88, 3);
    const result = stepTurret(before, 0.1, { aimX: 0, aimY: 0, firing: true });
    expect(before).toEqual(snapshot);
    expect(result.state).not.toBe(before);
    expect(result.events).toContain('shot');
    expect(result.state.ammo).toBe(119);
  });

  it('时间推进后生成来袭目标，跑满时限按时间结束', () => {
    let state: TurretState = createTurretState(100, 5);
    for (let tick = 0; tick < 5; tick += 1) {
      state = stepTurret(state, 0.1, { aimX: 0, aimY: 0, firing: false }).state;
    }
    expect(state.targets.length).toBeGreaterThan(0);
    expect(state.timeLeft).toBeLessThan(TURRET_RUN_SECONDS);

    // 每帧清空目标，避免撞舰干扰「时限结束」这条路径
    for (let tick = 0; tick < 700 && state.status === 'running'; tick += 1) {
      state = { ...stepTurret(state, 0.1, { aimX: 0, aimY: 0, firing: false }).state, targets: [] };
    }
    expect(state.status).toBe('over');
    expect(state.endReason).toBe('time');
  });

  it('命中、击毁与脱靶：连击倍率参与计分，脱靶清零', () => {
    const target: TurretTarget = {
      id: 1,
      kind: 'asteroid',
      x: 0.2,
      y: -0.1,
      z: 0.5,
      hp: 1,
      speed: 0,
      radius: 0.2,
      phase: 0,
      flash: 0,
    };
    const aimed = stepTurret({ ...createTurretState(100, 21), targets: [target] }, 0.05, {
      aimX: 0.2,
      aimY: -0.1,
      firing: true,
    });
    expect(aimed.events).toContain('shot');
    expect(aimed.events).toContain('kill');
    expect(aimed.state.kills).toBe(1);
    expect(aimed.state.hits).toBe(1);
    expect(aimed.state.combo).toBe(1);
    expect(aimed.state.score).toBe(10 + 15);
    expect(aimed.state.targets).toHaveLength(0);

    const missed = stepTurret({ ...createTurretState(100, 21), targets: [target], combo: 5 }, 0.05, {
      aimX: 0.95,
      aimY: 0.95,
      firing: true,
    });
    expect(missed.events).toContain('miss');
    expect(missed.state.combo).toBe(0);
    expect(missed.state.score).toBe(0);
    expect(comboMultiplier(5)).toBe(2);
    expect(comboMultiplier(0)).toBe(1);
    expect(comboMultiplier(100)).toBe(6);
  });

  it('目标突防扣减局部舰体，归零立即结束演习', () => {
    const incoming: TurretTarget = {
      id: 7,
      kind: 'drone',
      x: 0,
      y: 0,
      z: 0.01,
      hp: 1,
      speed: 1,
      radius: 0.11,
      phase: 0,
      flash: 0,
    };
    const single = stepTurret({ ...createTurretState(30, 4), targets: [incoming] }, 0.1, {
      aimX: 0,
      aimY: 0,
      firing: false,
    });
    expect(single.events).toContain('impact');
    expect(single.state.hull).toBe(23); // 30 − 7（无人机）
    expect(single.state.targets).toHaveLength(0);

    const lethal = stepTurret(
      {
        ...createTurretState(20, 4),
        targets: [
          { ...incoming, id: 8, kind: 'asteroid' },
          { ...incoming, id: 9, kind: 'asteroid' },
        ],
      },
      0.1,
      { aimX: 0, aimY: 0, firing: false },
    );
    expect(lethal.state.hull).toBe(0);
    expect(lethal.state.status).toBe('over');
    expect(lethal.state.endReason).toBe('hull');
  });

  it('持续扣扳机会过热，过热后温度被压在上限内', () => {
    let state: TurretState = createTurretState(100, 6);
    let sawOverheat = false;
    for (let tick = 0; tick < 60; tick += 1) {
      const result = stepTurret(state, 0.1, { aimX: 0, aimY: 0, firing: true });
      state = result.state;
      if (result.events.includes('overheat')) sawOverheat = true;
    }
    expect(sawOverheat).toBe(true);
    expect(state.overheated).toBe(true);
    expect(state.heat).toBeLessThanOrEqual(100);
    expect(state.shots).toBeGreaterThan(10);
  });

  it('击毁 15 个以上点亮「近防王牌」', () => {
    const state = createTurretState(100, 8);
    expect(TURRET_ACE_KILLS).toBe(15);
    expect(turretAchievements(state)).toEqual([]);
    expect(turretAchievements({ ...state, kills: TURRET_ACE_KILLS })).toEqual(['turret-ace']);
  });
});
