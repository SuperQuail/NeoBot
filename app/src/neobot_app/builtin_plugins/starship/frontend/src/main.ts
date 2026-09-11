// main.ts —— 入口：鉴权检查 → 拉取启动配置 → 引导页 → 启动游戏。
// 未进入游戏前不做任何 3D 初始化，也不轮询接口（零额外开销）。

import './styles.css';
import { GameBootstrap, consoleApiBase, consoleHomeUrl } from './config';
import { Game } from './game';
import { gameApi } from './net/api';
import './minigames';

async function boot(): Promise<void> {
  const container = document.getElementById('app');
  const canvas = document.getElementById('starship-canvas') as HTMLCanvasElement | null;
  const hudRoot = document.getElementById('starship-hud');
  const bootLayer = document.getElementById('starship-boot');
  const bootText = document.getElementById('starship-boot-text');
  if (!container || !canvas || !hudRoot || !bootLayer || !bootText) return;

  const setBootText = (text: string): void => {
    bootText.textContent = text;
  };

  setBootText('正在校验面板会话…');
  // /api/auth/me 由面板鉴权中间件处理：未登录返回 401，已登录返回会话信息
  let authenticated = true;
  try {
    const token = localStorage.getItem('neobot-dashboard-token') || '';
    const response = await fetch(consoleApiBase() + '/api/auth/me', {
      cache: 'no-store',
      headers: token ? { 'X-Token': token } : undefined,
    });
    authenticated = response.ok;
  } catch {
    authenticated = true;
  }
  if (!authenticated) {
    bootLayer.classList.add('error');
    bootText.innerHTML =
      '需要先登录网页面板才能登舰。<br /><a href="' + consoleHomeUrl() + '#/login">前往登录</a>';
    return;
  }

  setBootText('正在读取舰载配置…');
  const bootstrapResult = await gameApi.get<GameBootstrap>('/api/bootstrap');
  if (!bootstrapResult.ok || !bootstrapResult.data) {
    bootLayer.classList.add('error');
    bootText.textContent = '无法读取游戏配置：' + (bootstrapResult.error || '未知错误');
    return;
  }
  const bootstrap = bootstrapResult.data;

  setBootText('正在装配星舰…');
  let game: Game | null = null;
  const enter = (): void => {
    if (game) return;
    bootLayer.classList.add('hidden');
    try {
      game = new Game(container, hudRoot, bootstrap, canvas);
      game.start();
      const resize = () => game?.dispose();
      void resize;
    } catch (error) {
      bootLayer.classList.remove('hidden');
      bootLayer.classList.add('error');
      bootText.textContent = '星舰装配失败：' + (error as Error).message;
    }
  };

  bootLayer.innerHTML =
    '<div class="boot-panel">' +
    '<h1>' + escape(bootstrap.title) + '</h1>' +
    '<p class="boot-sub">NEOBOT STARSHIP · ' + escape(bootstrap.version || '') + '</p>' +
    '<ul class="boot-list">' +
    '<li>WASD 移动 · 鼠标看方向 · 空格跳跃 · Shift 潜行 · Ctrl 疾跑</li>' +
    '<li>走近全息终端按 <kbd>E</kbd> 使用（主控台、插件、配置、系统、用量、分析、通讯、日志）</li>' +
    '<li>机库与观景廊可以进入小游戏：舱外炮塔、损管抢修</li>' +
    '<li>舰桥的星图导航台可以手动跃迁；航行中也会自动跃迁</li>' +
    '</ul>' +
    '<button class="boot-enter">登舰</button>' +
    '<p class="boot-hint">进入后浏览器会请求鼠标指针锁定；按 Esc 可释放并打开菜单。</p>' +
    '</div>';
  const enterButton = bootLayer.querySelector('.boot-enter');
  enterButton?.addEventListener('click', enter);
  document.addEventListener(
    'keydown',
    (event) => {
      if (event.key === 'Enter' && !bootLayer.classList.contains('hidden')) enter();
    },
    { once: false },
  );
}

function escape(text: string): string {
  return String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

void boot();
