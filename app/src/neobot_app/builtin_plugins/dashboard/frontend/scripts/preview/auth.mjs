import { json } from './http.mjs';

export const DEMO_PASSWORD = 'neobot-demo';
const TOKEN = 'preview-token';
const CSRF = 'preview-csrf';

/** Demo-only credentials; never reads the application's auth store. */
export function createAuthPreview(scene) {
  const { canManage } = scene;
  let currentPassword = DEMO_PASSWORD;
  return {
    status(res) {
      return json(res, {
        ok: true,
        configured: true,
        authenticated: false,
        loopback: true,
        can_manage: canManage(),
        version: '本地演示夹具',
        base_path: '',
      });
    },
    login(body, res) {
      if (body.password !== currentPassword) return json(res, { error: '演示密码不正确' }, 403);
      res.setHeader('Set-Cookie', 'preview_session=' + TOKEN + '; Path=/; HttpOnly; SameSite=Lax');
      return json(res, { ok: true, token: TOKEN, csrf_token: CSRF });
    },
    requireSession(req, res) {
      const cookieAuthenticated = String(req.headers.cookie || '')
        .split(';')
        .some((part) => part.trim() === 'preview_session=' + TOKEN);
      if (req.headers['x-token'] !== TOKEN && !cookieAuthenticated) {
        json(res, { error: '请先登录本地演示夹具' }, 401);
        return false;
      }
      return true;
    },
    me(res) {
      return json(res, { authenticated: true, can_manage: canManage(), csrf_token: CSRF });
    },
    logout(res) {
      res.setHeader('Set-Cookie', 'preview_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0');
      return json(res, { ok: true, message: '已退出演示会话' });
    },
    requireCsrf(req, res) {
      if (req.headers['x-csrf-token'] === CSRF) return true;
      json(res, { error: '演示 CSRF 不匹配' }, 403);
      return false;
    },
    changePassword(body, res) {
      const { current_password: current, new_password: next, confirm } = body;
      if (![current, next, confirm].every((value) => typeof value === 'string'))
        return json(res, { error: '当前密码、新密码和确认密码均须为字符串' }, 400);
      if (next !== confirm) return json(res, { error: '两次输入的新密码不一致' }, 400);
      if (Array.from(next).length < 8 || Array.from(next).length > 128)
        return json(res, { error: '新密码须为 8–128 个字符' }, 400);
      if (next !== next.trim() || !/[\p{L}\p{N}]/u.test(next))
        return json(res, { error: '密码须包含字母或数字，首尾不能有空白字符' }, 400);
      if (current !== currentPassword) return json(res, { error: '当前密码不正确' }, 403);
      currentPassword = next;
      res.setHeader('Set-Cookie', 'preview_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0');
      return json(res, { ok: true, reauthenticate: true, message: '密码已修改，请重新登录' });
    },
  };
}
