// terminals/props.ts —— 舱室互动点：星图导航、咖啡机、点唱机、生命体征、补给、望远镜、舰长席。

import * as THREE from 'three';

import { Poller, type ApiResult } from '../net/api';
import type { TerminalContext, TerminalController, TerminalDefinition } from '../ui/terminal';
import type { UiSurface } from '../ui/surface';
import { formatDuration, formatNumber, type SystemPayload } from './shared';

const SYSTEM_NAMES = [
  '天鹅座 λ-4', '猎户悬臂 K-17', '南门二 β', '天苑四 ε', '蛇夫座 9',
  '武仙座 τ', '船底座 HD-7', '仙女座 M31-附', '半人马 ζ', '天琴座 Vega-2',
];

// ---------------------------------------------------------------------------
// 星图导航台：设定航线 / 触发跃迁
// ---------------------------------------------------------------------------

export const navigationTerminal: TerminalDefinition = {
  id: 'navigation',
  title: '星图导航台',
  subtitle: '星图 · 跃迁 · NAVIGATION',
  accent: 0x6fd0ff,
  decorate(group, materials) {
    const globe = new THREE.Mesh(
      new THREE.SphereGeometry(0.34, 20, 14),
      new THREE.MeshBasicMaterial({ color: 0x6fd0ff, wireframe: true, transparent: true, opacity: 0.75 }),
    );
    globe.position.set(0, 2.5, -0.7);
    group.add(globe);
    const orbit = new THREE.Mesh(new THREE.TorusGeometry(0.5, 0.012, 6, 40), materials.trim);
    orbit.position.set(0, 2.5, -0.7);
    orbit.rotation.x = Math.PI / 2.4;
    group.add(orbit);
  },
  create(ctx: TerminalContext): TerminalController {
    let index = 0;
    let lastMessage = '';
    return {
      idleAnimated: true,
      draw(ui: UiSurface) {
        const actions = ctx.host.actions;
        const warping = actions.warping();
        ui.panel({ x: 20, y: 130, w: 620, h: 424 }, { title: '星图 / STARCHART' });
        const origin = actions.systemName();
        const target = SYSTEM_NAMES[(index + 1) % SYSTEM_NAMES.length];
        ui.text(44, 200, '当前星系', { size: 16, color: ui.theme.textDim });
        ui.text(44, 236, origin, { size: 30, weight: 'bold' });
        ui.text(44, 292, '目标星系', { size: 16, color: ui.theme.textDim });
        ui.text(44, 328, target, { size: 30, weight: 'bold', color: ui.theme.accent });
        const distance = (4.2 + index * 1.7).toFixed(1);
        ui.keyValue(44, 372, 560, '航程', distance + ' 光年');
        ui.keyValue(44, 400, 560, '预计跃迁耗时', '约 3 秒');
        ui.keyValue(44, 428, 560, '引擎状态', warping ? '跃迁中…' : '就绪');
        if (ui.button('nav-prev', { x: 44, y: 456, w: 120, h: 48 }, '上一个', { size: 17 })) {
          index = (index + SYSTEM_NAMES.length - 1) % SYSTEM_NAMES.length;
        }
        if (ui.button('nav-next', { x: 176, y: 456, w: 120, h: 48 }, '下一个', { size: 17 })) {
          index = (index + 1) % SYSTEM_NAMES.length;
        }
        if (ui.button('nav-jump', { x: 308, y: 456, w: 220, h: 48 }, warping ? '跃迁进行中' : '启动跃迁', {
          disabled: warping,
          tone: ui.theme.accent,
        })) {
          if (actions.triggerWarp(true)) {
            lastMessage = '跃迁引擎已点火：' + target;
            ui.scrollReset('nav');
          }
        }
        ui.text(44, 532, lastMessage || '跃迁会让全舰进入高速航行状态，舷窗外会变成星流。', {
          size: 15,
          color: ui.theme.textDim,
          maxWidth: 560,
        });

        ui.panel({ x: 656, y: 130, w: 348, h: 424 }, { title: '航道提示 / NOTES' });
        ui.text(680, 200, '· 随机跃迁', { size: 17, color: ui.theme.accent });
        ui.text(680, 228, '航行一段时间后，舰载 AI 会', { size: 15, color: ui.theme.textDim });
        ui.text(680, 250, '自动规划一次跃迁。', { size: 15, color: ui.theme.textDim });
        ui.text(680, 296, '· 手动跃迁', { size: 17, color: ui.theme.accent });
        ui.text(680, 324, '在本终端选择目标星系并点火。', { size: 15, color: ui.theme.textDim });
        ui.text(680, 370, '· 观景廊', { size: 17, color: ui.theme.accent });
        ui.text(680, 398, '跃迁后星云配色与行星都会改变，', { size: 15, color: ui.theme.textDim });
        ui.text(680, 420, '去观景廊看看新的星系。', { size: 15, color: ui.theme.textDim });
        const jumpMinutes = ctx.host.jumpIntervalMinutes;
        ui.text(680, 480, jumpMinutes > 0 ? '自动跃迁间隔：约 ' + jumpMinutes + ' 分钟' : '自动跃迁已关闭', {
          size: 15,
          color: ui.theme.textDim,
        });
      },
    };
  },
};

// ---------------------------------------------------------------------------
// 咖啡机：小互动，喝完提升一点疾跑速度
// ---------------------------------------------------------------------------

interface Drink {
  id: string;
  name: string;
  desc: string;
  boost: 'sprint' | 'jump' | null;
  seconds: number;
}

const DRINKS: Drink[] = [
  { id: 'espresso', name: '双份浓缩', desc: '短时间提升移动速度', boost: 'sprint', seconds: 45 },
  { id: 'cocoa', name: '舰载可可', desc: '暖胃，纯粹好喝', boost: null, seconds: 0 },
  { id: 'tea', name: '合成红茶', desc: '提升跳跃高度一点点', boost: 'jump', seconds: 40 },
];

export const coffeeTerminal: TerminalDefinition = {
  id: 'coffee',
  title: '咖啡机',
  subtitle: '船员补给 · GALLEY',
  accent: 0xffcf8a,
  create(ctx: TerminalContext): TerminalController {
    let selected = 0;
    let poured = 0;
    return {
      draw(ui: UiSurface) {
        ui.panel({ x: 20, y: 130, w: 640, h: 424 }, { title: '菜单 / MENU' });
        DRINKS.forEach((drink, index) => {
          const y = 190 + index * 78;
          const rect = { x: 44, y, w: 592, h: 64 };
          const hovered = ui.isHovered('drink-' + index);
          ui.panel(rect, { tone: selected === index || hovered ? ui.theme.accent : ui.theme.panelEdge });
          ui.text(64, y + 28, drink.name, { size: 22, color: ui.theme.text });
          ui.text(64, y + 52, drink.desc, { size: 15, color: ui.theme.textDim });
          if (ui.button('pour-' + index, { x: 500, y: y + 12, w: 118, h: 40 }, '接一杯', { size: 16 })) {
            selected = index;
            poured += 1;
            ctx.host.actions.playChime('coffee');
            ctx.toast('接了一杯' + drink.name + '，舰桥的空气里都是香味。', 'ok');
            if (drink.boost) {
              ctx.host.actions.boost(drink.boost, drink.seconds);
              ctx.toast('获得增益：' + drink.desc + '（' + drink.seconds + ' 秒）', 'info');
            }
            ctx.host.actions.unlockAchievement('galley-visit', '在休息厅接了一杯饮品');
          }
        });
        ui.panel({ x: 684, y: 130, w: 320, h: 424 }, { title: '状态 / STATUS' });
        ui.text(708, 200, '今日供应', { size: 16, color: ui.theme.textDim });
        ui.text(708, 236, String(poured) + ' 杯', { size: 32, weight: 'bold', color: ui.theme.accent });
        ui.text(708, 300, '增益', { size: 16, color: ui.theme.textDim });
        const sprint = ctx.host.actions.boostRemaining('sprint');
        const jump = ctx.host.actions.boostRemaining('jump');
        ui.text(708, 336, sprint > 0 ? '疾跑 +25%（' + sprint.toFixed(0) + 's）' : '无', { size: 18 });
        ui.text(708, 368, jump > 0 ? '跳跃 +15%（' + jump.toFixed(0) + 's）' : '无', { size: 18 });
        ui.text(708, 440, '提示：按住 Ctrl 疾跑。', { size: 15, color: ui.theme.textDim });
      },
    };
  },
};

// ---------------------------------------------------------------------------
// 点唱机：合成音律
// ---------------------------------------------------------------------------

const TRACKS = [
  { id: 'bridge', name: '舰桥主题', scale: [220, 277, 330, 415, 494] },
  { id: 'warp', name: '跃迁回响', scale: [196, 233, 294, 349, 392] },
  { id: 'hangar', name: '机库节拍', scale: [262, 311, 392, 466, 523] },
];

export const jukeboxTerminal: TerminalDefinition = {
  id: 'jukebox',
  title: '点唱机',
  subtitle: '船员娱乐 · JUKEBOX',
  accent: 0xc9a2ff,
  create(ctx: TerminalContext): TerminalController {
    let current = -1;
    let beat = 0;
    const bars: number[] = new Array(18).fill(0);
    return {
      idleAnimated: true,
      draw(ui: UiSurface) {
        const playing = current >= 0;
        ui.panel({ x: 20, y: 130, w: 984, h: 424 }, { title: '曲库 / LIBRARY' });
        TRACKS.forEach((track, index) => {
          const y = 178 + index * 56;
          ui.text(48, y + 24, (current === index ? '▶ ' : '· ') + track.name, {
            size: 20,
            color: current === index ? ui.theme.accent : ui.theme.text,
          });
          if (ui.button('track-' + index, { x: 760, y: y + 4, w: 110, h: 40 }, current === index ? '停止' : '播放', { size: 16 })) {
            if (current === index) {
              current = -1;
              ctx.host.actions.stopMusic();
            } else {
              current = index;
              ctx.host.actions.playMusic(track.scale);
            }
          }
        });
        // 频谱
        beat += 1;
        for (let index = 0; index < bars.length; index += 1) {
          const target = playing ? Math.abs(Math.sin(beat * 0.05 + index * 0.7)) * (0.4 + Math.random() * 0.6) : 0.04;
          bars[index] = bars[index] * 0.7 + target * 0.3;
        }
        ui.panel({ x: 48, y: 360, w: 928, h: 170 }, { title: '频谱 / SPECTRUM' });
        bars.forEach((value, index) => {
          const height = Math.max(4, value * 120);
          ui.ctx.fillStyle = index % 2 === 0 ? ui.theme.accent : ui.theme.ok;
          ui.ctx.fillRect(72 + index * 50, 506 - height, 30, height);
        });
        ui.text(48, 546, playing ? '正在播放：' + TRACKS[current].name + '（合成音律，无外部音频文件）' : '点「播放」试试，音效由 WebAudio 实时合成。', {
          size: 15,
          color: ui.theme.textDim,
        });
        ctx.host.actions.setMusicActive(playing);
      },
    };
  },
};

// ---------------------------------------------------------------------------
// 生命体征仪：把系统资源映射成「舰员体征」
// ---------------------------------------------------------------------------

export const vitalsTerminal: TerminalDefinition = {
  id: 'vitals',
  title: '生命体征仪',
  subtitle: '舰体诊断 · MEDBAY',
  accent: 0x8affd0,
  create(ctx: TerminalContext): TerminalController {
    let system: SystemPayload | null = null;
    const history: number[] = [];
    const pollers = [
      new Poller<SystemPayload>(
        () => ctx.host.consoleApi.get<SystemPayload>('/api/system') as Promise<ApiResult<SystemPayload>>,
        3000,
        (data) => {
          system = data;
          history.push(Number(data.cpu_percent || 0));
          if (history.length > 120) history.shift();
          ctx.redraw();
        },
      ),
    ];
    return {
      pollers,
      draw(ui: UiSurface) {
        const info = system || {};
        ui.panel({ x: 20, y: 130, w: 984, h: 424 }, { title: '舰体体征 / VITALS' });
        const pulse = 0.5 + 0.5 * Math.sin(performance.now() / 380);
        ui.gauge({ x: 180, y: 300 }, 88, Number(info.cpu_percent || 0) / 100, {
          valueText: String(Math.round(Number(info.cpu_percent || 0))) + '%',
          label: '神经活动（CPU）',
          color: ui.theme.ok,
        });
        ui.gauge({ x: 440, y: 300 }, 88, Number(info.mem_percent || 0) / 100, {
          valueText: String(Math.round(Number(info.mem_percent || 0))) + '%',
          label: '体液循环（内存）',
        });
        ui.gauge({ x: 700, y: 300 }, 88, pulse, {
          valueText: '正常',
          label: '心跳（进程）',
          color: ui.theme.accent,
        });
        ui.sparkline({ x: 836, y: 240, w: 148, h: 120 }, history.slice(-80), { label: '心电图', fill: true, color: ui.theme.ok });
        ui.keyValue(48, 420, 400, '舰体运行时长', formatDuration(ctx.shell.status.uptime_seconds));
        ui.keyValue(48, 450, 400, '进程内存', formatNumber(info.process_memory_mb) + ' MB');
        ui.keyValue(48, 480, 400, '线程数', formatNumber(info.process_threads));
        ui.keyValue(520, 420, 460, '磁盘占用', (info.disk_used_gb ?? 0).toFixed(1) + ' / ' + (info.disk_total_gb ?? 0).toFixed(1) + ' GB');
        ui.keyValue(520, 450, 460, '主机', String(info.hostname || '—'));
        ui.keyValue(520, 480, 460, '系统', String(info.os || '—'));
        ui.text(48, 528, '医务室建议：CPU 长期高于 85% 时，考虑减少并发任务。', { size: 15, color: ui.theme.textDim });
      },
    };
  },
};

// ---------------------------------------------------------------------------
// 补给箱
// ---------------------------------------------------------------------------

export const suppliesTerminal: TerminalDefinition = {
  id: 'supplies',
  title: '补给箱',
  subtitle: '随身物资 · SUPPLIES',
  accent: 0xffd27f,
  create(ctx: TerminalContext): TerminalController {
    let opened = 0;
    return {
      draw(ui: UiSurface) {
        ui.panel({ x: 20, y: 130, w: 984, h: 424 }, { title: '物资清单 / INVENTORY' });
        ui.text(48, 200, '已开启补给：' + opened + ' 箱', { size: 24 });
        const items = [
          ['应急口粮', opened > 0 ? '×1' : '未领取'],
          ['磁力靴保养包', opened > 1 ? '×1' : '未领取'],
          ['备用氧烛', opened > 2 ? '×1' : '未领取'],
        ];
        items.forEach((item, index) => {
          ui.keyValue(48, 256 + index * 40, 460, item[0], item[1]);
        });
        if (ui.button('open-supply', { x: 48, y: 420, w: 220, h: 56 }, '开启补给箱', { tone: ui.theme.warn })) {
          opened += 1;
          ctx.host.actions.playChime('supply');
          ctx.toast('补给箱已开启（第 ' + opened + ' 箱）。', 'ok');
          ctx.host.actions.unlockAchievement('supply-run', '开启货舱补给箱');
          ctx.redraw();
        }
        ui.text(48, 512, '补给只是仪式感：真正让这艘船运转的是后排那台服务器。', {
          size: 15,
          color: ui.theme.textDim,
        });
      },
    };
  },
};

// ---------------------------------------------------------------------------
// 天文望远镜
// ---------------------------------------------------------------------------

export const telescopeTerminal: TerminalDefinition = {
  id: 'telescope',
  title: '天文望远镜',
  subtitle: '舰外观测 · TELESCOPE',
  accent: 0xa8e0ff,
  create(ctx: TerminalContext): TerminalController {
    const targets = ['主行星', '伴星卫星', '小行星带', '航道上的货船'];
    let selected = 0;
    let zoom = 1;
    return {
      draw(ui: UiSurface) {
        ui.panel({ x: 20, y: 130, w: 640, h: 424 }, { title: '观测目标 / TARGETS' });
        targets.forEach((target, index) => {
          if (ui.button('target-' + index, { x: 44, y: 180 + index * 60, w: 360, h: 48 }, target, {
            tone: selected === index ? ui.theme.accent : ui.theme.textDim,
          })) {
            selected = index;
            ctx.host.actions.lookAtTarget(target);
            ctx.host.actions.unlockAchievement('stargazer', '用望远镜观测舰外天体');
          }
        });
        ui.text(44, 452, '倍率', { size: 16, color: ui.theme.textDim });
        ui.progress({ x: 44, y: 466, w: 360, h: 16 }, zoom, { label: '', color: ui.theme.accent });
        if (ui.button('zoom-in', { x: 424, y: 452, w: 90, h: 40 }, '放大', { size: 16 })) {
          zoom = Math.min(1, zoom + 0.2);
          ctx.host.actions.zoomView(1.2);
        }
        if (ui.button('zoom-out', { x: 524, y: 452, w: 90, h: 40 }, '缩小', { size: 16 })) {
          zoom = Math.max(0.1, zoom - 0.2);
          ctx.host.actions.zoomView(1 / 1.2);
        }
        ui.panel({ x: 684, y: 130, w: 320, h: 424 }, { title: '观测记录 / LOG' });
        ui.text(708, 200, '当前目标是「' + targets[selected] + '」。', { size: 17, maxWidth: 280 });
        ui.text(708, 244, '放大/缩小会改变视野（FOV），', { size: 15, color: ui.theme.textDim, maxWidth: 280 });
        ui.text(708, 266, '把光标对准舷窗外即可观察。', { size: 15, color: ui.theme.textDim, maxWidth: 280 });
        ui.text(708, 330, '提示：观景廊的舷窗视野最好。', { size: 15, color: ui.theme.textDim, maxWidth: 280 });
      },
    };
  },
};

// ---------------------------------------------------------------------------
// 舰长席
// ---------------------------------------------------------------------------

export const captainChairTerminal: TerminalDefinition = {
  id: 'captain-chair',
  title: '舰长席',
  subtitle: '指挥席 · CAPTAIN',
  accent: 0xffd0a0,
  create(ctx: TerminalContext): TerminalController {
    return {
      draw(ui: UiSurface) {
        const seated = ctx.host.actions.isSeated();
        ui.panel({ x: 20, y: 130, w: 984, h: 424 }, { title: '舰长日志 / CAPTAIN LOG' });
        ui.text(48, 210, seated ? '已就座：视野降低，移动暂停。' : '尚未就座。', { size: 24 });
        if (ui.button('seat', { x: 48, y: 260, w: 220, h: 56 }, seated ? '起身' : '坐下', { tone: ui.theme.accent })) {
          ctx.host.actions.setSeated(!seated);
          ctx.redraw();
        }
        const status = ctx.shell.status;
        ui.keyValue(48, 360, 900, '舰船状态', status.standby ? '低功耗待机' : '全系统运行');
        ui.keyValue(48, 392, 900, '在位插件', String(status.plugins.running) + ' / ' + String(status.plugins.total));
        ui.keyValue(48, 424, 900, '通讯链路', status.online ? '正常' : '中断');
        ui.keyValue(48, 456, 900, '运行时长', formatDuration(status.uptime_seconds));
        ui.text(48, 512, '舰长须知：所有面板都在舰上；待机时部分终端会进入低功耗。', {
          size: 15,
          color: ui.theme.textDim,
        });
      },
    };
  },
};

export const propTerminals: TerminalDefinition[] = [
  navigationTerminal,
  coffeeTerminal,
  jukeboxTerminal,
  vitalsTerminal,
  suppliesTerminal,
  telescopeTerminal,
  captainChairTerminal,
];
void THREE;
