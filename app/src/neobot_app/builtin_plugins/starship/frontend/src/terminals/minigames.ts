// terminals/minigames.ts —— 小游戏站点终端：吸引画面 + 排行榜 + 一键开始。

import { Poller, type ApiResult } from '../net/api';
import type { TerminalContext, TerminalController, TerminalDefinition } from '../ui/terminal';
import type { UiSurface } from '../ui/surface';
import { formatNumber, type ScorePayload } from './shared';

function makeMinigameStation(options: {
  id: string;
  title: string;
  subtitle: string;
  accent: number;
  description: string;
  howTo: string[];
  scoreLabel: string;
}): TerminalDefinition {
  return {
    id: options.id,
    title: options.title,
    subtitle: options.subtitle,
    accent: options.accent,
    kind: 'minigame',
    create(ctx: TerminalContext): TerminalController {
      let scores: ScorePayload | null = null;
      let best = 0;
      const pollers = [
        new Poller<ScorePayload>(
          () =>
            ctx.host.gameApi.get<ScorePayload>(
              '/api/scores?game=' + encodeURIComponent(options.id) + '&limit=5',
            ) as Promise<ApiResult<ScorePayload>>,
          20000,
          (data) => {
            scores = data;
            best = Math.max(best, Number((data.items || [])[0]?.score ?? 0));
            ctx.redraw();
          },
        ),
      ];
      return {
        pollers,
        idleAnimated: true,
        draw(ui: UiSurface) {
          ui.panel({ x: 20, y: 130, w: 600, h: 424 }, { title: '演练说明 / BRIEFING' });
          ui.text(44, 190, options.description, { size: 20, maxWidth: 552 });
          options.howTo.forEach((line, index) => {
            ui.text(44, 236 + index * 30, '· ' + line, { size: 17, color: ui.theme.textDim, maxWidth: 552 });
          });
          if (
            ui.button('start', { x: 44, y: 470, w: 240, h: 60 }, '开始演练', {
              tone: ui.theme.accent,
              disabled: !ctx.shell.status.standby === false,
            })
          ) {
            ctx.host.actions.openMinigame(options.id, ctx.anchor.spec.id);
          }
          ui.text(300, 508, '按 E 离开终端 · 演练中按 E / Esc 可随时退出', {
            size: 15,
            color: ui.theme.textDim,
          });

          ui.panel({ x: 640, y: 130, w: 364, h: 424 }, { title: '最佳成绩 / BEST' });
          const items = scores?.items || [];
          if (items.length === 0) {
            ui.text(664, 200, '还没有记录，去创造第一份成绩。', { size: 17, color: ui.theme.textDim, maxWidth: 320 });
          }
          items.forEach((item, index) => {
            const y = 196 + index * 40;
            ui.text(664, y, String(index + 1) + '. ' + String(item.player || '舰长'), { size: 18 });
            ui.text(984, y, formatNumber(item.score), { size: 18, align: 'right', color: ui.theme.accent });
          });
          ui.text(664, 470, options.scoreLabel, { size: 15, color: ui.theme.textDim });
          ui.text(664, 500, '当前最佳：' + formatNumber(best), { size: 18 });
        },
      };
    },
  };
}

export const turretStation = makeMinigameStation({
  id: 'turret',
  title: '炮塔模拟器',
  subtitle: '舱外炮塔 · TURRET',
  accent: 0xff8a6a,
  description: '小行星群正在接近。坐上舷侧炮塔，把它们打成碎片。',
  howTo: [
    '移动鼠标瞄准，左键开火（每 0.18 秒一发）',
    '小行星撞上舰体会扣完整度，归零即演练失败',
    '每 14 秒来一波，波次越高速度越快',
    '完整度越高，结算奖励分越多',
  ],
  scoreLabel: '击毁得分（含完整度奖励）',
});

export const repairStation = makeMinigameStation({
  id: 'repair',
  title: '损管终端',
  subtitle: '损管抢修 · DAMAGE CONTROL',
  accent: 0xffc861,
  description: '反应堆回路被震断，限时把电力从堆芯接到各个系统。',
  howTo: [
    '点击导线格子让它旋转 90°',
    '绿色表示已通电，橙色边框是必须接通的系统',
    '接通全部系统即过关，剩余时间折算分数',
    '共三轮，每轮时间更短、网格更乱',
  ],
  scoreLabel: '抢修得分（含剩余时间奖励）',
});

export const minigameStations: TerminalDefinition[] = [turretStation, repairStation];
