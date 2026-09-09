// Login.jsx —— 登录页(移植自旧 login.html)
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiLogin, checkAuth, getToken, setToken } from '../api/client.js';

const THEME_KEY = 'neobot-dashboard-theme';

function toggleTheme() {
  const cur = document.documentElement.dataset.theme || 'light';
  const next = cur === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = next;
  localStorage.setItem(THEME_KEY, next);
}

export default function Login() {
  const [token, setTok] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  // 已有有效 token → 直接进主页
  useEffect(() => {
    (async () => {
      const t = getToken();
      if (t && (await checkAuth(t))) navigate('/dashboard', { replace: true });
    })();
  }, [navigate]);

  const onSubmit = async (e) => {
    e.preventDefault();
    setError('');
    const t = token.trim();
    if (!t) return setError('请输入 access_token');
    setBusy(true);
    const r = await apiLogin(t);
    setBusy(false);
    if (!r.ok) return setError(r.error);
    setToken(r.token);
    navigate('/dashboard', { replace: true });
  };

  return (
    <div className="login-page">
      <button className="login-theme-toggle" onClick={toggleTheme} aria-label="切换主题">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" width="16" height="16">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
        </svg>
      </button>

      <form className="login-card" onSubmit={onSubmit} autoComplete="off">
        <div className="login-header">
          <div className="login-logo">
            <img src={import.meta.env.BASE_URL + 'image/icon.webp'} alt="NeoBot Logo" onError={(e) => (e.target.style.display = 'none')} />
          </div>
          <div className="login-title">
            <span className="title-main">NeoBot</span>
            <span className="title-login">Login</span>
          </div>
        </div>

        {error && <div className="login-err">{error}</div>}

        <div className="login-field">
          <label htmlFor="token">Access Token</label>
          <div className="login-input-wrap">
            <svg className="login-input-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4" />
            </svg>
            <input
              id="token"
              type="password"
              required
              placeholder="粘贴启动日志里的 Access Token"
              value={token}
              onChange={(e) => setTok(e.target.value)}
              autoFocus
            />
          </div>
        </div>

        <button type="submit" className="login-btn" disabled={busy}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4" />
            <polyline points="10 17 15 12 10 7" />
            <line x1="15" y1="12" x2="3" y2="12" />
          </svg>
          {busy ? '验证中…' : '登 录'}
        </button>
      </form>
    </div>
  );
}
