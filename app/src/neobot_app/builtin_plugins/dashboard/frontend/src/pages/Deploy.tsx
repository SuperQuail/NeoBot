// pages/Deploy.tsx —— 快捷部署：只填少数几项就能把 Bot 跑起来
// 最后一步给出 OneBot 反向 WS 的**生效**地址与 access token —— NapCat 侧要填的就是这两样。
import { useCallback, useEffect, useState } from 'react';
import { api } from '../api/endpoints';
import type { DeployStatus } from '../api/types';
import { toast } from '../components/Toast';
import Icon from '../components/Icon';

function CopyRow(props: { label: string; value: string; hint?: string; onCopy: (v: string, l: string) => void }) {
  return (
    <div className="deploy-copy-row">
      <span className="deploy-copy-label">{props.label}</span>
      <code className="deploy-copy-value">{props.value || '—'}</code>
      <button type="button" className="btn-sm" disabled={!props.value}
        onClick={() => props.onCopy(props.value, props.label)}>
        <Icon name="check" /> 复制
      </button>
      {props.hint && <span className="muted small">{props.hint}</span>}
    </div>
  );
}

export default function Deploy() {
  const [doc, setDoc] = useState<DeployStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');
  const [account, setAccount] = useState('');
  const [nickName, setNickName] = useState('');
  const [adminQq, setAdminQq] = useState('');
  const [apiKey, setApiKey] = useState('');

  const read = useCallback(async () => {
    setLoading(true);
    const result = await api.deployStatus();
    setLoading(false);
    if (!result.ok || !result.data) {
      toast(result.error || '读取部署状态失败', 'err');
      return;
    }
    setDoc(result.data);
    setAccount(result.data.values?.bot_account || '');
    setNickName(result.data.values?.bot_nick_name || '');
    setAdminQq((result.data.values?.admin_accounts || [])[0] || '');
  }, []);

  useEffect(() => {
    read();
  }, [read]);

  /** 保存身份与管理员：先读当前配置再深合并 —— 只发改动的那两段会误删同段其它字段。 */
  const saveIdentity = async () => {
    setBusy('identity');
    const current = await api.config();
    if (!current.ok || !current.data) {
      setBusy('');
      toast(current.error || '读取当前配置失败', 'err');
      return;
    }
    const draft = (current.data.config || {}) as Record<string, any>;
    const result = await api.configSave({
      revision: current.data.revision,
      mode: 'form',
      reload: true,
      config: {
        ...draft,
        bot: { ...(draft.bot || {}), account: account.trim(), nick_name: nickName.trim() },
        chat: {
          ...(draft.chat || {}),
          admin_accounts: adminQq.trim() ? [adminQq.trim()] : [],
        },
      },
    });
    setBusy('');
    if (!result.ok) {
      toast(result.error || '保存失败', 'err');
      return;
    }
    toast('机器人身份与管理员已保存', 'ok');
    await read();
  };

  const saveApiKey = async () => {
    if (!apiKey.trim()) {
      toast('请先填 DeepSeek API Key', 'err');
      return;
    }
    setBusy('key');
    const result = await api.envSave({
      updates: { DeepSeek_APIKey: apiKey.trim(), DeepSeek_URL: 'https://api.deepseek.com' },
      deletes: [],
      revision: doc?.env_revision,
      reload: true,
    });
    setBusy('');
    if (!result.ok) {
      toast(result.error || '保存密钥失败', 'err');
      return;
    }
    toast(result.data?.message || '密钥已保存并重载', 'ok');
    setApiKey('');
    await read();
  };

  const generateToken = async () => {
    setBusy('token');
    const result = await api.deployOneBotToken({ revision: doc?.revision });
    setBusy('');
    if (!result.ok) {
      toast(result.error || '生成 access token 失败', 'err');
      return;
    }
    toast(result.data?.message || '已生成并写入 access token', 'ok');
    await read();
  };

  const copy = async (value: string, label: string) => {
    try {
      await navigator.clipboard.writeText(value);
      toast(label + '已复制', 'ok');
    } catch {
      toast('复制失败，请手动选中复制', 'err');
    }
  };

  const onebot = doc?.onebot;
  const steps = doc?.steps || [];

  return (
    <div className="page">
      <section className="card">
        <h1>快捷部署</h1>
        <p className="muted">
          只需填下面几项就能让 Bot 跑起来。每一项配好后会自动打勾；
          最后一步的 OneBot 地址与 access token 直接填进 NapCat 的反向 WS 配置即可。
        </p>
        {loading && <p className="muted">读取中…</p>}
        <ul className="deploy-steps">
          {steps.map((step) => (
            <li key={step.key} className={step.done ? 'done' : ''}>
              <Icon name={step.done ? 'check' : 'more'} />
              <b>{step.label}</b>
              <span className="muted small">{step.hint}</span>
            </li>
          ))}
        </ul>
        {doc?.ready && <p className="deploy-ready"><Icon name="check" /> 全部就绪，Bot 可以正常工作了。</p>}
      </section>

      <section className="card">
        <h2>1. 机器人身份与管理员</h2>
        <div className="deploy-form">
          <label>
            机器人 QQ 号
            <input className="input" value={account} onChange={(e) => setAccount(e.target.value)}
              placeholder="例如 123456789" />
          </label>
          <label>
            机器人昵称
            <input className="input" value={nickName} onChange={(e) => setNickName(e.target.value)}
              placeholder="例如 NeoBot" />
          </label>
          <label>
            超级管理员 QQ（可留空）
            <input className="input" value={adminQq} onChange={(e) => setAdminQq(e.target.value)}
              placeholder="接收余额不足等系统通知" />
          </label>
        </div>
        <button type="button" className="btn" disabled={busy === 'identity'} onClick={saveIdentity}>
          <Icon name="save" /> {busy === 'identity' ? '保存中…' : '保存并重载'}
        </button>
      </section>

      <section className="card">
        <h2>2. 平台密钥（DeepSeek）</h2>
        <p className="muted small">
          默认模型库全部走 DeepSeek，所以只填这一个 Key 就能对话。密钥只写不读，保存后立即重建 provider。
        </p>
        <div className="deploy-form">
          <label>
            DeepSeek API Key
            <input className="input" type="password" value={apiKey}
              onChange={(e) => setApiKey(e.target.value)} placeholder="sk-…" />
          </label>
        </div>
        <button type="button" className="btn" disabled={busy === 'key'} onClick={saveApiKey}>
          <Icon name="save" /> {busy === 'key' ? '保存中…' : '保存密钥'}
        </button>
      </section>

      <section className="card">
        <h2>3. OneBot 连接（给 NapCat 用）</h2>
        <p className="muted small">
          NeoBot 作为**反向 WebSocket 服务端**监听，由 NapCat 主动连过来 —— 所以把下面的地址与
          token 填进 NapCat 的「反向 WS」即可。路径由 NapCat 侧自己配，服务端不限制
          （NapCat 常用 <code>{onebot?.path_hint || '/onebot/v11/ws'}</code>）。
        </p>
        {onebot?.warning && <p className="config-notice warning"><Icon name="more" /> {onebot.warning}</p>}
        <CopyRow label="同机连接" value={onebot?.url_local || ''} hint="NapCat 与 NeoBot 在同一台机器" onCopy={copy} />
        <CopyRow label="局域网连接" value={onebot?.url_lan || ''} hint="NapCat 在另一台机器" onCopy={copy} />
        <CopyRow label="Access Token" value={onebot?.token || ''}
          hint={onebot?.token_enabled ? '填进 NapCat 的同一个字段' : '当前为空：不校验握手，建议生成一个'}
          onCopy={copy} />
        <div className="deploy-actions">
          <button type="button" className="btn" disabled={busy === 'token'} onClick={generateToken}>
            <Icon name="refresh" /> {busy === 'token' ? '生成中…' : (onebot?.token_enabled ? '重新生成 token' : '生成 token')}
          </button>
          <span className="muted small">
            端口与监听地址在「配置管理 → adapter」里改（当前生效：
            {onebot ? onebot.host + ':' + onebot.port : '—'}）。
          </span>
        </div>
      </section>
    </div>
  );
}
