// 登录 / 首次设置密码页，共用同一组表单与鉴权流程。
import React, { useState, useEffect, useRef } from 'react';
import { Lock, LogIn, TriangleAlert, Eye, EyeOff } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { apiLogin, apiSetup, authStatus, checkAuth, getToken, setToken } from '../api/client';
import { useAuthGate } from '../auth/AuthContext';
import ThemePicker from '../components/ui/ThemePicker';
import { useLoginIntro } from '../hooks/useLoginIntro';

export default function Login() {
  const scene = useRef<HTMLDivElement>(null);
  useLoginIntro(scene);
  const [mode, setMode] = useState('loading'); // loading | login | setup | blocked
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [reveal, setReveal] = useState(false);
  const navigate = useNavigate();
  const { refresh: refreshAuthGate } = useAuthGate();

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
    return () => {
      alive = false;
    };
  }, [navigate]);

  const onSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (busy || mode === 'loading') return;
    setError('');
    if (mode === 'setup') {
      if (password.length < 8) return setError('密码至少 8 个字符');
      if (password !== confirm) return setError('两次输入的密码不一致');
    } else if (!password) {
      return setError('请输入密码');
    }
    setBusy(true);
    const result = mode === 'setup' ? await apiSetup(password, confirm) : await apiLogin(password);
    setBusy(false);
    if (!result.ok) return setError(result.error || '登录失败');
    setToken(result.token || '', result.csrf);
    // 设置密码会改变「面板是否已配置」——不刷新这份探测结果的话，
    // RequireAuth 仍按旧值（configured=false → setupRequired=true）把我们弹回登录页，
    // 于是在 /login 与 /dashboard 之间来回跳，看着就是「登录页闪烁」（issue #78）。
    await refreshAuthGate();
    navigate('/dashboard', { replace: true });
  };

  const title = mode === 'setup' ? '设置面板密码' : '登录工作台';
  const label = mode === 'setup' ? '新密码' : '面板密码';

  return (
    <div className="login-page" ref={scene}>
      <aside className="login-brand-panel" aria-labelledby="login-neobot">
        <h1 id="login-neobot" className="sr-only">
          NEOBOT
        </h1>
        <div className="login-hero-stack" aria-hidden="true">
          {['outline', 'solid', 'echo'].map((variant) => (
            <div className={`login-hero-row login-hero-row--${variant}`} key={variant} data-login-row>
              {'NEOBOT'.split('').map((letter, index) => (
                <span className="login-hero-letter" data-login-letter key={index}>
                  {letter}
                </span>
              ))}
            </div>
          ))}
        </div>
        <div className="login-hero-sweep" aria-hidden="true" />
      </aside>
      <div className="login-form-panel">
        <div className="login-theme-tools">
          <ThemePicker />
        </div>
        <form className="login-card" onSubmit={onSubmit}>
          <div className="login-header">
            <h2 className="login-title">{mode === 'setup' ? '设置面板密码' : '欢迎回来'}</h2>
            <p className="login-subtitle">
              {mode === 'setup' ? '首次使用，在本机完成这一步。' : '登录 NeoBot，继续管理你的机器人。'}
            </p>
          </div>

          {error && (
            <div className="login-err" role="alert">
              <TriangleAlert size={14} strokeWidth={2.5} aria-hidden="true" />
              <span>{error}</span>
            </div>
          )}

          {mode === 'blocked' ? (
            <div className="login-field">
              <div className="login-field-title">尚未设置面板密码</div>
              <p className="muted small">为安全起见，未配置密码时不允许外网访问面板。请选择其中一种方式：</p>
              <ul className="muted small login-hints">
                <li>在本机浏览器打开面板，按提示设置密码</li>
                <li>
                  由超级管理员在 QQ 私聊中发送 <code>/set_password &lt;新密码&gt;</code>
                </li>
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
                    type={reveal ? 'text' : 'password'}
                    required
                    placeholder={mode === 'setup' ? '至少 8 个字符' : '请输入面板密码'}
                    value={password}
                    autoComplete={mode === 'setup' ? 'new-password' : 'current-password'}
                    disabled={busy || mode === 'loading'}
                    onChange={(e) => setPassword(e.target.value)}
                    data-autofocus
                  />
                  <button
                    type="button"
                    className="login-reveal"
                    aria-label={reveal ? '隐藏密码' : '显示密码'}
                    onClick={() => setReveal(!reveal)}
                  >
                    {reveal ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
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
                      autoComplete="new-password"
                      disabled={busy}
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
                {mode === 'loading' ? '正在连接…' : busy ? '处理中…' : title}
              </button>
            </>
          )}
          <div className="login-footer">
            {mode === 'setup'
              ? '设置密码后，即可从其他设备登录。'
              : '使用面板密码登录，会话在 NeoBot 重启后失效。'}
          </div>
        </form>
      </div>
    </div>
  );
}
