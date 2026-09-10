// Login.jsx —— 登录 / 首次设置密码页（沿用原视觉风格）
import React, { useState, useEffect } from 'react';
import { Lock, LogIn, Moon, TriangleAlert } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { apiLogin, apiSetup, authStatus, checkAuth, getToken, setToken } from '../api/client';

const THEME_KEY = 'neobot-dashboard-theme';

function toggleTheme() {
  const cur = document.documentElement.dataset.theme || 'light';
  const next = cur === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = next;
  localStorage.setItem(THEME_KEY, next);
}

export default function Login() {
  const [mode, setMode] = useState('loading'); // loading | login | setup | blocked
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    let alive = true;
    (async () => {
      const status = await authStatus();
      if (!alive) return;
      if (status && status.authenticated) {
        navigate('/dashboard', { replace: true });
        return;
      }
      if (status && status.configured === false) {
        setMode(status.loopback ? 'setup' : 'blocked');
        return;
      }
      setMode('login');
      const t = getToken();
      if (t && (await checkAuth(t))) navigate('/dashboard', { replace: true });
    })();
    return () => { alive = false; };
  }, [navigate]);

  const onSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError('');
    if (mode === 'setup') {
      if (password.length < 8) return setError('密码至少 8 个字符');
      if (password !== confirm) return setError('两次输入的密码不一致');
    } else if (!password) {
      return setError('请输入密码');
    }
    setBusy(true);
    const result = mode === 'setup'
      ? await apiSetup(password, confirm)
      : await apiLogin(password);
    setBusy(false);
    if (!result.ok) return setError(result.error || '登录失败');
    setToken(result.token || '', result.csrf);
    navigate('/dashboard', { replace: true });
  };

  const title = mode === 'setup' ? '设置面板密码' : '登 录';
  const label = mode === 'setup' ? '新密码' : '面板密码';

  return (
    <div className="login-page">
      <button className="login-theme-toggle" onClick={toggleTheme} aria-label="切换主题">
        <Moon size={16} strokeWidth={2} aria-hidden="true" />
      </button>

      <form className="login-card" onSubmit={onSubmit} autoComplete="off">
        <div className="login-header">
          <div className="login-logo">
            <img src="./image/icon.webp" alt="NeoBot Logo" onError={(e) => ((e.target as HTMLElement).style.display = 'none')} />
          </div>
          <div className="login-title">
            <span className="title-main">NeoBot</span>
            <span className="title-login">{mode === 'setup' ? 'Setup' : 'Login'}</span>
          </div>
        </div>

        {error && (
          <div className="login-err flex items-center gap-1.5">
            <TriangleAlert size={14} strokeWidth={2.5} aria-hidden="true" />
            <span>{error}</span>
          </div>
        )}

        {mode === 'blocked' ? (
          <div className="login-field">
            <div className="login-field-title">尚未设置面板密码</div>
            <p className="muted small">
              为安全起见，未配置密码时不允许外网访问面板。请选择其中一种方式：
            </p>
            <ul className="muted small login-hints">
              <li>在本机浏览器打开面板，按提示设置密码</li>
              <li>由超级管理员在 QQ 私聊中发送 <code>/set_password &lt;新密码&gt;</code></li>
            </ul>
          </div>
        ) : (
          <>
            <div className="login-field">
              <label htmlFor="password">{label}</label>
              <div className="login-input-wrap">
                <Lock className="login-input-icon" size={15} strokeWidth={2} aria-hidden="true" />
                <input
                  id="password"
                  type="password"
                  required
                  placeholder={mode === 'setup' ? '至少 8 个字符' : '请输入面板密码'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  data-autofocus
                />
              </div>
            </div>

            {mode === 'setup' && (
              <div className="login-field">
                <label htmlFor="confirm">确认密码</label>
                <div className="login-input-wrap">
                  <Lock className="login-input-icon" size={15} strokeWidth={2} aria-hidden="true" />
                  <input
                    id="confirm"
                    type="password"
                    required
                    placeholder="再次输入新密码"
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value)}
                  />
                </div>
              </div>
            )}

            {mode === 'setup' && (
              <p className="muted small">
                仅本机可设置。设置后外网即可通过密码登录；忘记密码时可由超级管理员在 QQ 私聊执行
                <code> /set_password </code> 重置。
              </p>
            )}

            <button type="submit" className="login-btn" disabled={busy || mode === 'loading'}>
              <LogIn size={14} strokeWidth={2.5} aria-hidden="true" />
              {busy ? '处理中…' : title}
            </button>
          </>
        )}
      </form>
    </div>
  );
}
