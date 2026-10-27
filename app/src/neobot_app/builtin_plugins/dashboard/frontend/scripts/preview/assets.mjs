import { readFile } from 'node:fs/promises';
import { Buffer } from 'node:buffer';
import { URL } from 'node:url';
import { json } from './http.mjs';

export function createAssetPreview() {
  const imageFiles = new Map(
    ['icon.webp', 'licon.webp', 'background.webp'].map((name) => [
      name,
      new URL('../../../web/image/' + name, import.meta.url),
    ]),
  );
  // 固定读取仓库源码中的两个页面常量；只提取文本，不加载或执行 Python。
  const bilibiliSource = new URL('../../../bilibili_login.py', import.meta.url);
  async function bilibiliAsset(constant) {
    const source = await readFile(bilibiliSource, 'utf8');
    const match = new RegExp('^' + constant + ' = """([\\s\\S]*?)^"""', 'm').exec(source);
    if (!match) throw new Error('独立登录页演示常量不存在');
    return match[1];
  }
  const bilibiliStates = new Set(['expired', 'pending', 'scanned', 'success', 'error']);
  let bilibiliState = 'expired';
  let bilibiliPolls = 0;
  let bilibiliAutomatic = false;
  // 这是不可扫码的图形占位，不包含真实登录 URL 或二维码凭据。
  const bilibiliPlaceholder =
    'data:image/svg+xml;base64,' +
    Buffer.from(
      '<svg xmlns="http://www.w3.org/2000/svg" width="232" height="232" viewBox="0 0 232 232"><rect width="232" height="232" fill="white"/><g fill="#514139"><path d="M20 20h56v56H20zM156 20h56v56h-56zM20 156h56v56H20z"/><path d="M92 20h24v16H92zM132 44h12v32h-12zM92 60h24v24H92zM20 92h32v12H20zM60 92h16v40H60zM92 100h24v16H92zM132 92h40v16h-40zM188 92h24v32h-24zM20 120h24v12H20zM92 156h16v56H92zM124 172h24v16h-24zM156 140h16v40h-16zM188 156h24v16h-24zM180 188h32v24h-32zM124 204h32v8h-32z"/></g><g fill="white"><path d="M28 28h40v40H28zM164 28h40v40h-40zM28 164h40v40H28z"/></g><g fill="#514139"><path d="M36 36h24v24H36zM172 36h24v24h-24zM36 172h24v24H36z"/></g><rect x="76" y="108" width="104" height="40" rx="7" fill="#fff0e1"/><text x="128" y="134" text-anchor="middle" font-family="sans-serif" font-size="15" fill="#a55a35">DEMO</text></svg>',
    ).toString('base64');
  function bilibiliSnapshot() {
    const messages = {
      expired: '本地演示：二维码已过期，点击刷新查看等待状态。',
      pending: '本地演示：等待扫码。这是不可扫码的占位图，不会连接 B站。',
      scanned: '本地演示：已扫码，等待手机确认。',
      success: '本地演示：虚构账号登录成功，未访问 B站。',
      error: '本地演示：模拟二维码生成失败，可以刷新重试。',
    };
    return {
      ok: true,
      service_available: true,
      logged_in: bilibiliState === 'success',
      uid: bilibiliState === 'success' ? 100000001 : 0,
      uname: bilibiliState === 'success' ? '虚构预览账号（演示）' : '',
      state: bilibiliState,
      message: messages[bilibiliState],
      qr_png: ['pending', 'scanned'].includes(bilibiliState) ? bilibiliPlaceholder : '',
      qr_url: '',
      running: ['pending', 'scanned'].includes(bilibiliState),
    };
  }

  return {
    async loginPage({ path, method, res }) {
      if (path === '/bilibili/login' || path === '/bilibili/login.js') {
        if (method !== 'GET') return json(res, { error: '演示静态页仅接受 GET' }, 405);
        const script = path.endsWith('.js');
        const content = await bilibiliAsset(script ? 'LOGIN_SCRIPT' : 'LOGIN_PAGE');
        res.writeHead(200, {
          'Content-Type': script ? 'text/javascript; charset=utf-8' : 'text/html; charset=utf-8',
          'Cache-Control': 'no-store',
          'X-Neobot-Preview': 'fictional-memory-only',
        });
        return res.end(content);
      }
    },
    async image({ path, res }) {
      if (path.startsWith('/image/')) {
        const filename = path.slice('/image/'.length);
        if (!imageFiles.has(filename)) return json(res, { error: '演示图片不存在' }, 404);
        try {
          const bytes = await readFile(imageFiles.get(filename));
          res.writeHead(200, { 'Content-Type': 'image/webp', 'Cache-Control': 'max-age=3600' });
          return res.end(bytes);
        } catch {
          return json(res, { error: '演示图片不可用' }, 404);
        }
      }
    },
    handle({ path, method, body, res }) {
      if (path === '/api/bilibili/login/status') {
        if (method !== 'GET') return json(res, { error: '演示状态接口仅接受 GET' }, 405);
        if (bilibiliAutomatic) {
          bilibiliPolls++;
          bilibiliState = bilibiliPolls >= 4 ? 'expired' : bilibiliPolls >= 2 ? 'scanned' : 'pending';
          if (bilibiliState === 'expired') bilibiliAutomatic = false;
        }
        return json(res, bilibiliSnapshot());
      }
      if (path === '/api/bilibili/login/start') {
        if (method !== 'POST') return json(res, { error: '演示登录接口仅接受 POST' }, 405);
        bilibiliState = bilibiliStates.has(body.state) ? body.state : 'pending';
        bilibiliAutomatic = !body.state;
        bilibiliPolls = 0;
        return json(res, bilibiliSnapshot());
      }
    },
  };
}
