// Authenticate first, then enter the real 3D scene without a 2D boarding menu.
import './styles.css';
import { consoleApiBase, consoleHomeUrl, loadShipName, type GameBootstrap } from './config';
import type { Game } from './game';
import { gameApi } from './net/api';

async function boot(): Promise<void> {
  const container = document.getElementById('app');
  const canvas = document.getElementById('starship-canvas') as HTMLCanvasElement | null;
  const hudRoot = document.getElementById('starship-hud');
  const bootLayer = document.getElementById('starship-boot');
  const bootText = document.getElementById('starship-boot-text');
  if (!container || !canvas || !hudRoot || !bootLayer || !bootText) return;

  let game: Game | null = null;
  let departed = false;
  const authRequest = new AbortController();
  window.addEventListener('pagehide', () => {
    departed = true;
    authRequest.abort();
    game?.dispose();
    game = null;
  }, { once: true });
  // A restored document must not keep showing the disposed WebGL scene.
  window.addEventListener('pageshow', (event) => {
    if (event.persisted && departed) window.location.reload();
  });

  const fail = (message: string, login = false): void => {
    if (departed) return;
    bootLayer.hidden = false;
    bootLayer.inert = false;
    bootLayer.classList.remove('hidden');
    bootLayer.classList.add('error');
    bootText.setAttribute('role', 'alert');
    bootText.textContent = message;
    // These links exist only if startup fails, never as an ordinary game menu.
    const fallback = document.createElement('p');
    const retry = document.createElement('a');
    retry.href = window.location.href;
    retry.textContent = '重新加载';
    const home = document.createElement('a');
    home.href = consoleHomeUrl() + (login ? '#/login' : '');
    home.textContent = login ? '前往面板登录' : '返回面板';
    fallback.append(retry, document.createTextNode(' · '), home);
    bootLayer.append(fallback);
  };

  bootText.textContent = '正在校验面板会话…';
  let token = '';
  try { token = localStorage.getItem('neobot-dashboard-token') || ''; } catch { /* Cookie authentication remains available. */ }
  try {
    const response = await fetch(consoleApiBase() + '/api/auth/me', {
      cache: 'no-store',
      credentials: 'same-origin',
      headers: token ? { 'X-Token': token } : undefined,
      signal: authRequest.signal,
    });
    if (departed) return;
    if (!response.ok) {
      const login = response.status === 401 || response.status === 403;
      fail(login ? '需要先登录网页面板才能进入星舰。' : '会话校验失败，请重新加载。', login);
      return;
    }
  } catch {
    fail('无法连接面板，请检查网络后重新加载。');
    return;
  }

  bootText.textContent = '正在读取舰载配置…';
  const result = await gameApi.get<GameBootstrap>('/api/bootstrap');
  if (departed) return;
  if (!result.ok || !result.data) {
    fail('无法读取舰载配置：' + (result.error || '未知错误'), result.status === 401 || result.status === 403);
    return;
  }

  bootText.textContent = '正在加载三维星舰…';
  try {
    const { Game } = await import('./game');
    if (departed) return;
    const shipName = loadShipName();
    game = new Game(container, hudRoot, result.data, canvas);
    game.hud.setShipIdentity(shipName);
    // Game.start renders immediately; pointer lock/audio wait for a scene gesture.
    game.start();
    document.title = shipName + ' · NeoBot 星舰';
    bootLayer.classList.add('hidden');
    bootLayer.hidden = true;
    bootLayer.inert = true;
    canvas.focus({ preventScroll: true });
  } catch (error) {
    game?.dispose();
    game = null;
    hudRoot.replaceChildren();
    fail('星舰启动失败：' + (error instanceof Error ? error.message : String(error)));
  }
}

void boot();
