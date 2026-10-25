// pages/Deploy.tsx —— 快捷部署：只填必填项就能把 Bot 跑起来
// 必填：机器人 QQ 号 + 昵称 + 人设 + 平台密钥 + OneBot 连接；超管选填。
// 最后一步给出 OneBot 反向 WS 的**生效**地址与 access token —— NapCat 侧要填的就是这两样。
import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api/endpoints';
import type { DeployStatus } from '../api/types';
import { toast } from '../components/Toast';
import Icon from '../components/Icon';
import Button from '../components/ui/Button';

// 快捷部署草稿：用户填到一半切到别的页面（例如配置编辑页）再回来时，
// 未点「保存并重载」的输入不能丢。只存非敏感字段，API Key 不落浏览器存储。
const DRAFT_KEY = 'neobot.deploy.draft.v1';

interface DeployDraft {
  account: string;
  nickName: string;
  aliases: string;
  persona: string;
  adminQq: string;
  chance: string;
}

function loadDraft(): DeployDraft | null {
  try {
    const raw = sessionStorage.getItem(DRAFT_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<DeployDraft>;
    return {
      account: String(parsed.account ?? ''),
      nickName: String(parsed.nickName ?? ''),
      aliases: String(parsed.aliases ?? ''),
      persona: String(parsed.persona ?? ''),
      adminQq: String(parsed.adminQq ?? ''),
      chance: String(parsed.chance ?? '0.3'),
    };
  } catch {
    return null;
  }
}

function saveDraft(draft: DeployDraft): void {
  try {
    sessionStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
  } catch {
    // 隐私模式/storage 满：草稿丢失不影响主流程
  }
}

function clearDraft(): void {
  try {
    sessionStorage.removeItem(DRAFT_KEY);
  } catch {
    // 同上
  }
}

function CopyRow(props: { label: string; value: string; hint?: string; onCopy: (v: string, l: string) => void }) {
  return (
    <div className="deploy-copy-row">
      <span className="deploy-copy-label">{props.label}</span>
      <code className="deploy-copy-value">{props.value || '—'}</code>
      <Button type="button" size="sm" disabled={!props.value}
        onClick={() => props.onCopy(props.value, props.label)}>
        <Icon name="download" /> 复制
      </Button>
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
  const [aliases, setAliases] = useState('');
  const [persona, setPersona] = useState('');
  const [adminQq, setAdminQq] = useState('');
  const [chance, setChance] = useState('0.3');
  const [apiKey, setApiKey] = useState('');
  const [dirty, setDirty] = useState(false);
  const [restored, setRestored] = useState(false);
  const draftChecked = useRef(false);

  // applyValues=false：只刷新步骤/OneBot 状态与 revision，不回填表单。
  // 「保存密钥 / 生成 token」不应把用户还没点「保存并重载」的身份/人设草稿冲掉。
  const read = useCallback(async (applyValues = true) => {
    setLoading(true);
    const result = await api.deployStatus();
    setLoading(false);
    if (!result.ok || !result.data) {
      toast(result.error || '读取部署状态失败', 'err');
      return;
    }
    setDoc(result.data);
    if (!applyValues) return;
    const values = result.data.values || {};
    // 首次加载优先恢复本 tab 的未保存草稿；之后（保存并重载）才按服务端值回填。
    const draft = draftChecked.current ? null : loadDraft();
    draftChecked.current = true;
    if (draft) {
      setAccount(draft.account);
      setNickName(draft.nickName);
      setAliases(draft.aliases);
      setPersona(draft.persona);
      setAdminQq(draft.adminQq);
      setChance(draft.chance);
      setRestored(true);
      setDirty(true);
      return;
    }
    setAccount(values.bot_account || '');
    setNickName(values.bot_nick_name || '');
    setAliases((values.alias_name || []).join('、'));
    setPersona(values.bot_data || '');
    setAdminQq((values.admin_accounts || [])[0] || '');
    setChance(String(values.group_chat_chance ?? 0.3));
  }, []);

  useEffect(() => {
    read(true);
  }, [read]);

  // 用户改过才写草稿：避免保存后 read(true) 把服务端值又写回草稿。
  useEffect(() => {
    if (!dirty) return;
    saveDraft({ account, nickName, aliases, persona, adminQq, chance });
  }, [dirty, account, nickName, aliases, persona, adminQq, chance]);

  const discardDraft = async () => {
    clearDraft();
    setRestored(false);
    setDirty(false);
    await read(true);
  };

  /** 保存身份 / 人设 / 别名 / 超管 / 回复意愿：先读当前配置再深合并 ——
   *  只发改动的那几段会误删同段其它字段。 */
  const saveAll = async () => {
    setBusy('config');
    const current = await api.config();
    if (!current.ok || !current.data) {
      setBusy('');
      toast(current.error || '读取当前配置失败', 'err');
      return;
    }
    const draft = (current.data.config || {}) as Record<string, any>;
    const parsedChance = Number(chance);
    const result = await api.configSave({
      revision: current.data.revision,
      mode: 'form',
      reload: true,
      config: {
        ...draft,
        bot: {
          ...(draft.bot || {}),
          account: account.trim(),
          nick_name: nickName.trim(),
          alias_name: aliases.split(/[、,，\s]+/).map((s) => s.trim()).filter(Boolean),
          bot_data: persona,
        },
        chat: {
          ...(draft.chat || {}),
          admin_accounts: adminQq.trim() ? [adminQq.trim()] : [],
          group_chat_chance: Number.isFinite(parsedChance) ? parsedChance : 0.3,
        },
      },
    });
    setBusy('');
    if (!result.ok) {
      toast(result.error || '保存失败', 'err');
      return;
    }
    clearDraft();
    setRestored(false);
    setDirty(false);
    toast('配置已保存并重载', 'ok');
    await read(true);
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
    // 只刷新状态：身份/人设等未保存草稿必须保留（用户可能还没点「保存并重载」）。
    await read(false);
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
    await read(false);
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
  const defaults = doc?.defaults || {};

  return (
    <div className="page">
      <section className="card">
        <h1>快捷部署</h1>
        <p className="muted">
          按下面几项填完即可让 Bot 跑起来；带「必填」的项配好后会自动打勾。
          最后一步的 OneBot 地址与 access token 直接填进 NapCat 的反向 WS 配置。
        </p>
        {loading && <p className="muted">读取中…</p>}
        {restored && (
          <p className="config-notice">
            已恢复上次未保存的快捷部署输入（只在本标签页有效）；点下方「保存并重载」会写入并清除草稿。
            <Button type="button" size="sm" onClick={discardDraft}>放弃草稿</Button>
          </p>
        )}
        <ul className="deploy-steps">
          {steps.map((step) => (
            <li key={step.key} className={step.done ? 'done' : ''}>
              <Icon name={step.done ? 'check' : 'more'} />
              <b>{step.label}</b>
              <span className={'deploy-badge' + (step.required ? ' required' : '')}>
                {step.required ? '必填' : '选填'}
              </span>
              <span className="muted small">{step.hint}</span>
            </li>
          ))}
        </ul>
        {doc?.ready && <p className="deploy-ready"><Icon name="check" /> 必填项都已配好，Bot 可以正常工作了。</p>}
      </section>

      <section className="card">
        <h2>1. 机器人身份</h2>
        <div className="deploy-form">
          <label>
            <span>机器人 QQ 号 <em className="deploy-req">必填</em></span>
            <input className="input" value={account} onChange={(e) => { setAccount(e.target.value); setDirty(true); }}
              placeholder={defaults.bot_account ? '出厂占位：' + defaults.bot_account : '例如 123456789'} />
          </label>
          <label>
            <span>机器人昵称 <em className="deploy-req">必填</em></span>
            <input className="input" value={nickName} onChange={(e) => { setNickName(e.target.value); setDirty(true); }}
              placeholder={defaults.bot_nick_name || '例如 NeoBot'} />
          </label>
          <label>
            别名（可留空，多个用「、」分隔）
            <input className="input" value={aliases} onChange={(e) => { setAliases(e.target.value); setDirty(true); }}
              placeholder="别人怎么称呼它，例如：玄天" />
          </label>
        </div>
      </section>

      <section className="card">
        <h2>2. 人设 <span className="deploy-req">必填</span></h2>
        <p className="muted small">
          写清「你是谁、怎么说话、有什么规矩」。它会被插进系统提示词（占位符 <code>{'{bot_data}'}</code>），
          出厂那段只是示例文案，请替换成你自己的。想深度定制提示词模板，去「提示词」页。
        </p>
        <textarea className="input deploy-persona" rows={6} value={persona}
          onChange={(e) => { setPersona(e.target.value); setDirty(true); }}
          placeholder="例如：你是群里的老群友「玄天」，说话简短、偶尔毒舌，不主动聊敏感话题…" />
      </section>

      <section className="card">
        <h2>3. 平台密钥（DeepSeek）</h2>
        <p className="muted small">
          默认模型库全部走 DeepSeek，所以只填这一个 Key 就能对话。密钥只写不读，保存后立即重建 provider。
        </p>
        <div className="deploy-form">
          <label>
            <span>DeepSeek API Key <em className="deploy-req">必填</em></span>
            <input className="input" type="password" value={apiKey}
              onChange={(e) => setApiKey(e.target.value)} placeholder="sk-…" />
          </label>
        </div>
        <Button type="button" disabled={busy === 'key'} onClick={saveApiKey}>
          <Icon name="save" /> {busy === 'key' ? '保存中…' : '保存密钥'}
        </Button>
      </section>

      <section className="card">
        <h2>4. 超级管理员与回复意愿</h2>
        <div className="deploy-form">
          <label>
            超级管理员 QQ（选填）
            <input className="input" value={adminQq} onChange={(e) => { setAdminQq(e.target.value); setDirty(true); }}
              placeholder="接收余额不足等系统通知；留空也能正常跑" />
          </label>
          <label>
            群聊回复意愿系数
            <input className="input" type="number" min="0" max="1" step="0.05" value={chance}
              onChange={(e) => { setChance(e.target.value); setDirty(true); }} />
            <span className="muted small">
              约等于回复概率，具体概率受聊天流场景浮动（有人 @ 你、话题相关时更高）。
              默认 0.3；填 0 表示不主动回复。
            </span>
          </label>
        </div>
        <Button type="button" disabled={busy === 'config'} onClick={saveAll}>
          <Icon name="save" /> {busy === 'config' ? '保存中…' : '保存并重载'}
        </Button>
      </section>

      <section className="card">
        <h2>5. OneBot 连接（给 NapCat 用） <span className="deploy-req">必填</span></h2>
        <p className="muted small">
          NeoBot 作为<b>反向 WebSocket 服务端</b>监听，由 NapCat 主动连过来 —— 所以把下面的地址与
          token 填进 NapCat 的「反向 WS」即可。路径由 NapCat 侧自己配，服务端不限制
          （惯例写法 <code>{onebot?.path_hint || '/onebot'}</code>，填别的也能连上）。
          默认<b>所有聊天流（群聊 / 私聊）都可回复</b>；要限定范围去「配置管理 → chat」。
        </p>
        {onebot?.warning && <p className="config-notice warning"><Icon name="more" /> {onebot.warning}</p>}
        <CopyRow label="同机连接" value={onebot?.url_local || ''} hint="NapCat 与 NeoBot 在同一台机器" onCopy={copy} />
        <CopyRow label="局域网连接" value={onebot?.url_lan || ''} hint="NapCat 在另一台机器" onCopy={copy} />
        <CopyRow label="Access Token" value={onebot?.token || ''}
          hint={onebot?.token_enabled ? '填进 NapCat 的同一个字段' : '当前为空：不校验握手，建议生成一个'}
          onCopy={copy} />
        <div className="deploy-actions">
          <Button type="button" disabled={busy === 'token'} onClick={generateToken}>
            <Icon name="refresh" /> {busy === 'token' ? '生成中…' : (onebot?.token_enabled ? '重新生成 token' : '生成 token')}
          </Button>
          <Button type="button" size="sm" disabled title="装了 NapCat Desktop 后可一键创建连接（后续版本提供）">
            <Icon name="external" /> 自动连接（待 NapCat Desktop 支持）
          </Button>
          <span className="muted small">
            端口与监听地址在「配置管理 → adapter」里改（当前生效：
            {onebot ? onebot.host + ':' + onebot.port : '—'}）。
          </span>
        </div>
      </section>
    </div>
  );
}
