// minigames/repair.ts —— 损管抢修：在全息屏上把反应堆电力接到各个系统（限时解谜）。
//
// 玩法：网格里每格是一段导线，点击旋转；从左侧堆芯（电源）出发，
// 把电力送到右侧被标记的系统接口。接通全部接口即过关，剩余时间折算分数。

import { registerMinigame, type MinigameContext, type MinigameModule } from './api';
import type { UiSurface } from '../ui/surface';

const COLS = 6;
const ROWS = 4;
const ROUND_TIME = 75;

/** 每格的连接位：bit0=上 bit1=右 bit2=下 bit3=左 */
const DIRS = [1, 2, 4, 8];

interface Cell {
  mask: number;
  fixed: boolean;
  powered: boolean;
}

class RepairGame implements MinigameModule {
  readonly id = 'repair';
  readonly name = '损管抢修';
  readonly description = '反应堆回路被震断，限时把电力接到各个系统。';
  readonly icon = 'wrench';
  readonly mode = 'screen' as const;

  private ctx: MinigameContext | null = null;
  private cells: Cell[] = [];
  private targets: number[] = [];
  private timeLeft = ROUND_TIME;
  private round = 1;
  private score = 0;
  private elapsed = 0;
  private solved = false;
  private failed = false;
  private hint = '点击导线旋转，把电力从左侧堆芯引到右侧系统接口。';
  private lastTick = 0;

  start(ctx: MinigameContext): void {
    this.ctx = ctx;
    this.round = 1;
    this.score = 0;
    this.elapsed = 0;
    this.buildRound();
    ctx.setHud(null);
  }

  private buildRound(): void {
    const ctx = this.ctx;
    if (!ctx) return;
    this.timeLeft = Math.max(35, ROUND_TIME - (this.round - 1) * 10);
    this.solved = false;
    this.failed = false;
    const random = ctx.rng.bind(ctx);

    // 生成一条从左到右的通路，保证有解
    const path: Array<[number, number]> = [];
    let row = Math.floor(random() * ROWS);
    for (let col = 0; col < COLS; col += 1) {
      path.push([col, row]);
      if (col < COLS - 1 && random() > 0.45) {
        const delta = row === 0 ? 1 : row === ROWS - 1 ? -1 : random() > 0.5 ? 1 : -1;
        path.push([col, row + delta]);
        row += delta;
      }
    }

    this.cells = [];
    for (let index = 0; index < COLS * ROWS; index += 1) {
      this.cells.push({ mask: 0, fixed: false, powered: false });
    }
    const connect = (a: [number, number], b: [number, number]): void => {
      const first = this.cells[a[1] * COLS + a[0]];
      const second = this.cells[b[1] * COLS + b[0]];
      if (a[1] > b[1]) first.mask |= DIRS[0];
      if (a[0] < b[0]) first.mask |= DIRS[1];
      if (a[1] < b[1]) first.mask |= DIRS[2];
      if (a[0] > b[0]) first.mask |= DIRS[3];
      if (b[1] < a[1]) second.mask |= DIRS[0];
      if (b[0] > a[0]) second.mask |= DIRS[1];
      if (b[1] > a[1]) second.mask |= DIRS[2];
      if (b[0] < a[0]) second.mask |= DIRS[3];
    };
    // 电源入口
    const source = this.cells[path[0][1] * COLS + 0];
    source.mask |= DIRS[3];
    source.fixed = true;
    for (let index = 0; index < path.length - 1; index += 1) {
      connect(path[index], path[index + 1]);
    }
    const exit = path[path.length - 1];
    this.cells[exit[1] * COLS + (COLS - 1)].mask |= DIRS[1];
    this.targets = [exit[1] * COLS + (COLS - 1)];

    // 随机再挂一个支线系统
    const extraRow = (exit[1] + 2) % ROWS;
    const extraCol = COLS - 1;
    const extraIndex = extraRow * COLS + extraCol;
    if (!this.targets.includes(extraIndex)) {
      this.cells[extraIndex].mask |= DIRS[1];
      this.targets.push(extraIndex);
    }

    // 打乱：非固定的格子随机旋转
    for (const cell of this.cells) {
      if (cell.mask === 0) continue;
      const rotations = Math.floor(random() * 4);
      cell.mask = rotate(cell.mask, rotations);
    }
    this.cells[path[0][1] * COLS].mask = rotate(this.cells[path[0][1] * COLS].mask, 0);
    this.cells[path[0][1] * COLS].mask |= DIRS[3];
  }

  private computePower(): boolean {
    for (const cell of this.cells) cell.powered = false;
    const queue: number[] = [];
    for (let row = 0; row < ROWS; row += 1) {
      const index = row * COLS;
      if (this.cells[index].mask & DIRS[3]) {
        this.cells[index].powered = true;
        queue.push(index);
      }
    }
    while (queue.length > 0) {
      const index = queue.shift() as number;
      const col = index % COLS;
      const row = Math.floor(index / COLS);
      const mask = this.cells[index].mask;
      const neighbours: Array<[number, number, number, number]> = [
        [0, -1, DIRS[0], DIRS[2]],
        [1, 0, DIRS[1], DIRS[3]],
        [0, 1, DIRS[2], DIRS[0]],
        [-1, 0, DIRS[3], DIRS[1]],
      ];
      for (const [dx, dy, own, other] of neighbours) {
        if ((mask & own) === 0) continue;
        const nextCol = col + dx;
        const nextRow = row + dy;
        if (nextCol < 0 || nextCol >= COLS || nextRow < 0 || nextRow >= ROWS) continue;
        const next = nextRow * COLS + nextCol;
        if ((this.cells[next].mask & other) === 0) continue;
        if (this.cells[next].powered) continue;
        this.cells[next].powered = true;
        queue.push(next);
      }
    }
    return this.targets.every((index) => this.cells[index].powered);
  }

  update(dt: number, ctx: MinigameContext): void {
    if (this.solved || this.failed) return;
    this.elapsed += dt;
    this.timeLeft -= dt;
    if (this.timeLeft <= 0) {
      this.failed = true;
      ctx.audio.alarm();
      void ctx
        .submitScore('repair', this.score, Math.round(this.elapsed * 1000), '第 ' + this.round + ' 轮超时')
        .then((result) => {
          ctx.finish({
            title: '抢修超时',
            lines: [
              '完成轮数：' + (this.round - 1),
              '本次得分：' + this.score,
              result.ok ? '历史最佳 ' + (result.best ?? this.score) : '成绩未保存：' + (result.error || ''),
            ],
            score: this.score,
            canRetry: true,
          });
        });
    }
    if (this.timeLeft < 10 && performance.now() - this.lastTick > 1000) {
      this.lastTick = performance.now();
      ctx.audio.alarm();
    }
  }

  draw(ui: UiSurface, ctx: MinigameContext): void {
    const boardX = 40;
    const boardY = 150;
    const cellSize = 118;
    ui.panel({ x: 20, y: 130, w: boardX + COLS * cellSize + 20, h: ROWS * cellSize + 60 }, { title: '电力回路 / CIRCUIT' });
    for (let row = 0; row < ROWS; row += 1) {
      for (let col = 0; col < COLS; col += 1) {
        const index = row * COLS + col;
        const cell = this.cells[index];
        const x = boardX + col * cellSize;
        const y = boardY + row * cellSize;
        const rect = { x: x + 6, y: y + 6, w: cellSize - 12, h: cellSize - 12 };
        const isTarget = this.targets.includes(index);
        const hovered = ui.isHovered('cell-' + index);
        ui.ctx.fillStyle = cell.powered
          ? 'rgba(80, 220, 160, 0.22)'
          : hovered
            ? 'rgba(90, 150, 200, 0.22)'
            : 'rgba(14, 28, 40, 0.6)';
        ui.ctx.fillRect(rect.x, rect.y, rect.w, rect.h);
        ui.ctx.strokeStyle = isTarget ? ui.theme.warn : 'rgba(90, 150, 190, 0.45)';
        ui.ctx.lineWidth = isTarget ? 3 : 1.5;
        ui.ctx.strokeRect(rect.x + 0.5, rect.y + 0.5, rect.w - 1, rect.h - 1);
        const cx = rect.x + rect.w / 2;
        const cy = rect.y + rect.h / 2;
        const half = rect.w * 0.32;
        const color = cell.powered ? ui.theme.ok : 'rgba(150, 190, 220, 0.55)';
        ui.ctx.strokeStyle = cell.powered ? ui.theme.ok : color;
        ui.ctx.lineWidth = 9;
        ui.ctx.lineCap = 'round';
        const segments: Array<[number, number, number, number]> = [
          [cx, cy, cx, cy - half],
          [cx, cy, cx + half, cy],
          [cx, cy, cx, cy + half],
          [cx, cy, cx - half, cy],
        ];
        segments.forEach((segment, dir) => {
          if ((cell.mask & DIRS[dir]) === 0) return;
          ui.ctx.beginPath();
          ui.ctx.moveTo(segment[0], segment[1]);
          ui.ctx.lineTo(segment[2], segment[3]);
          ui.ctx.stroke();
        });
        ui.ctx.beginPath();
        ui.ctx.arc(cx, cy, 6, 0, Math.PI * 2);
        ui.ctx.fillStyle = cell.powered ? ui.theme.ok : color;
        ui.ctx.fill();
        if (cell.powered) {
          const pulse = 0.5 + 0.5 * Math.sin(performance.now() / 200 + index);
          ui.ctx.globalAlpha = 0.25 * pulse;
          ui.ctx.fillStyle = ui.theme.ok;
          ui.ctx.fillRect(rect.x, rect.y, rect.w, rect.h);
          ui.ctx.globalAlpha = 1;
        }
      }
    }
    ui.panel({ x: boardX + COLS * cellSize + 40, y: 130, w: 230, h: ROWS * cellSize + 60 }, { title: '抢修进度 / STATUS' });
    ui.text(boardX + COLS * cellSize + 64, 190, '剩余时间', { size: 16, color: ui.theme.textDim });
    ui.text(boardX + COLS * cellSize + 64, 232, Math.max(0, this.timeLeft).toFixed(1) + ' s', {
      size: 30,
      weight: 'bold',
      color: this.timeLeft < 15 ? ui.theme.error : ui.theme.text,
    });
    ui.progress({ x: boardX + COLS * cellSize + 64, y: 250, w: 182, h: 14 }, this.timeLeft / ROUND_TIME, {
      color: this.timeLeft < 15 ? ui.theme.error : ui.theme.accent,
      showValue: false,
    });
    const poweredTargets = this.targets.filter((index) => this.cells[index].powered).length;
    ui.text(boardX + COLS * cellSize + 64, 310, '已接通系统', { size: 16, color: ui.theme.textDim });
    ui.text(boardX + COLS * cellSize + 64, 350, poweredTargets + ' / ' + this.targets.length, { size: 30, weight: 'bold' });
    ui.text(boardX + COLS * cellSize + 64, 400, '当前轮次', { size: 16, color: ui.theme.textDim });
    ui.text(boardX + COLS * cellSize + 64, 436, String(this.round), { size: 28, weight: 'bold', color: ui.theme.accent });
    ui.text(boardX + COLS * cellSize + 64, 500, '得分 ' + this.score, { size: 20, color: ui.theme.accent });
    ui.text(40, boardY + ROWS * cellSize + 30, this.hint, { size: 15, color: ui.theme.textDim });
    void ctx;
  }

  /** 由 Game 在屏幕被点击时调用（坐标换算成格子） */
  onScreenClick(ui: UiSurface): void {
    const boardX = 40;
    const boardY = 150;
    const cellSize = 118;
    const col = Math.floor((ui.cursor.x - boardX) / cellSize);
    const row = Math.floor((ui.cursor.y - boardY) / cellSize);
    if (col < 0 || col >= COLS || row < 0 || row >= ROWS) return;
    const index = row * COLS + col;
    const cell = this.cells[index];
    if (!cell || cell.mask === 0) return;
    cell.mask = rotate(cell.mask, 1);
    this.ctx?.audio.chime('repair');
    if (this.computePower()) {
      this.solved = true;
      const bonus = Math.round(this.timeLeft * 40 + 500);
      this.score += bonus;
      this.ctx?.toast('回路接通！本轮 +' + bonus + ' 分', 'ok');
      window.setTimeout(() => {
        const ctx = this.ctx;
        if (!ctx) return;
        this.round += 1;
        if (this.round > 3) {
          void ctx.submitScore('repair', this.score, Math.round(this.elapsed * 1000), '完成 3 轮抢修').then((result) => {
            ctx.finish({
              title: '抢修完成',
              lines: [
                '完成轮数：3',
                '剩余时间奖励已计入',
                result.ok ? '本次得分 ' + this.score + '，历史最佳 ' + (result.best ?? this.score) + '，排名第 ' + (result.rank ?? 1) : '成绩未保存：' + (result.error || ''),
              ],
              score: this.score,
              canRetry: true,
            });
          });
        } else {
          this.buildRound();
        }
      }, 900);
    }
  }
}

function rotate(mask: number, times: number): number {
  let result = mask;
  for (let index = 0; index < ((times % 4) + 4) % 4; index += 1) {
    result = ((result << 1) | (result >> 3)) & 0b1111;
  }
  return result;
}

export const repairGame = new RepairGame();
registerMinigame(repairGame);
