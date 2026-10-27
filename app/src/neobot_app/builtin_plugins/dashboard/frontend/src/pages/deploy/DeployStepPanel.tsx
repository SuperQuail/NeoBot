import { Copy, RefreshCw } from 'lucide-react';
import { notify } from '../../notifications/infoBar';
import Button from '../../components/ui/Button';
import InlineAlert from '../../components/ui/InlineAlert';
import { STEPS } from './deployModel';
import type { DeployEditor } from './useDeployEditor';

function CopyRow({
  label,
  value,
  hint,
  onCopy,
}: {
  label: string;
  value: string;
  hint: string;
  onCopy: (value: string, label: string) => void;
}) {
  return (
    <div className="deploy-connection-row">
      <div className="deploy-connection-label">
        <strong>{label}</strong>
        <span>{hint}</span>
      </div>
      <code className="deploy-connection-value">{value || '—'}</code>
      <Button size="sm" disabled={!value} onClick={() => onCopy(value, label)}>
        <Copy size={14} /> 复制
      </Button>
    </div>
  );
}

export default function DeployStepPanel({
  activeIndex,
  editor,
}: {
  activeIndex: number;
  editor: DeployEditor;
}) {
  const {
    doc,
    draft,
    apiKey,
    setApiKey,
    disabled,
    chanceError,
    updateDraft,
    dirtySteps,
    busy,
    generateToken,
  } = editor;
  const active = STEPS[activeIndex];
  const activeStatus = doc?.steps?.find((step) => step.key === active.key);
  const onebot = doc?.onebot;
  const defaults = doc?.defaults || {};
  const TipsList = activeIndex === 4 ? 'ol' : 'ul';
  const copy = async (value: string, label: string) => {
    try {
      await navigator.clipboard.writeText(value);
      notify(label + '已复制', 'ok');
    } catch {
      notify('复制失败，请手动选中复制', 'err');
    }
  };

  return (
    <section
      className="deploy-step-panel"
      id={'deploy-panel-' + active.key}
      role="tabpanel"
      aria-labelledby={'deploy-tab-' + active.key}
    >
      <div className="deploy-step-main">
        <div className="deploy-step-heading">
          <h2>{active.title}</h2>
          <p>{active.description}</p>
        </div>
        {activeIndex === 0 && (
          <div className="deploy-fields deploy-identity-fields">
            <label className="deploy-field" htmlFor="deploy-account">
              <span className="deploy-field-label">
                机器人 QQ 号 <span>必填</span>
              </span>
              <input
                id="deploy-account"
                className="input"
                inputMode="numeric"
                value={draft.account}
                disabled={disabled}
                onChange={(event) => updateDraft('account', event.target.value)}
                placeholder={defaults.bot_account ? '出厂占位：' + defaults.bot_account : '例如 123456789'}
              />
            </label>
            <label className="deploy-field" htmlFor="deploy-name">
              <span className="deploy-field-label">
                机器人昵称 <span>必填</span>
              </span>
              <input
                id="deploy-name"
                className="input"
                value={draft.nickName}
                disabled={disabled}
                onChange={(event) => updateDraft('nickName', event.target.value)}
                placeholder={defaults.bot_nick_name || '例如 NeoBot'}
              />
            </label>
            <label className="deploy-field deploy-field-wide" htmlFor="deploy-aliases">
              <span className="deploy-field-label">
                别名 <span>选填</span>
              </span>
              <input
                id="deploy-aliases"
                className="input"
                value={draft.aliases}
                disabled={disabled}
                onChange={(event) => updateDraft('aliases', event.target.value)}
                placeholder="例如：小玄、玄天"
              />
              <span className="deploy-field-hint">多个称呼用「、」分隔。</span>
            </label>
          </div>
        )}
        {activeIndex === 1 && (
          <label className="deploy-field" htmlFor="deploy-persona">
            <span className="deploy-field-label">
              机器人设定 <span>必填</span>
            </span>
            <textarea
              id="deploy-persona"
              className="input deploy-persona-editor"
              rows={9}
              value={draft.persona}
              disabled={disabled}
              onChange={(event) => updateDraft('persona', event.target.value)}
              placeholder="例如：你是群里的老群友「玄天」，说话简短，偶尔开玩笑；不主动聊敏感话题。"
            />
            <span className="deploy-field-hint">请替换出厂示例。完整提示词模板可在「提示词」页调整。</span>
          </label>
        )}
        {activeIndex === 2 && (
          <div className="deploy-fields">
            <div className="deploy-provider-summary">
              <div>
                <strong>DeepSeek</strong>
                <span>模型供应商</span>
              </div>
              <span className="deploy-state-tag">{activeStatus?.done ? '密钥已设置' : '尚未配置'}</span>
            </div>
            <label className="deploy-field" htmlFor="deploy-api-key">
              <span className="deploy-field-label">
                DeepSeek API Key <span>{activeStatus?.done ? '留空保留' : '必填'}</span>
              </span>
              <input
                id="deploy-api-key"
                className="input"
                type="password"
                autoComplete="new-password"
                value={apiKey}
                disabled={disabled}
                onChange={(event) => setApiKey(event.target.value)}
                placeholder="sk-…"
              />
              <span className="deploy-field-hint">
                点击下方「保存并应用」后，密钥会立即生效，输入框随即清空。
              </span>
            </label>
          </div>
        )}
        {activeIndex === 3 && (
          <div className="deploy-fields">
            <label className="deploy-field" htmlFor="deploy-admin">
              <span className="deploy-field-label">
                超级管理员 QQ <span>选填</span>
              </span>
              <input
                id="deploy-admin"
                className="input"
                inputMode="numeric"
                value={draft.adminQq}
                disabled={disabled}
                onChange={(event) => updateDraft('adminQq', event.target.value)}
                placeholder="接收余额不足等系统通知"
              />
            </label>
            <div className="deploy-field">
              <label className="deploy-field-label" htmlFor="deploy-chance">
                群聊回复意愿系数
              </label>
              <div className="deploy-chance-control">
                <input
                  type="range"
                  aria-label="调整群聊回复意愿"
                  min="0"
                  max="1"
                  step="0.05"
                  value={draft.chance || '0'}
                  disabled={disabled}
                  onChange={(event) => updateDraft('chance', event.target.value)}
                />
                <input
                  id="deploy-chance"
                  className="input"
                  type="number"
                  min="0"
                  max="1"
                  step="0.05"
                  value={draft.chance}
                  aria-invalid={!!chanceError}
                  aria-describedby={chanceError ? 'deploy-chance-error' : undefined}
                  disabled={disabled}
                  onChange={(event) => updateDraft('chance', event.target.value)}
                />
              </div>
              {chanceError && (
                <span id="deploy-chance-error" className="field-error" role="alert">
                  {chanceError}
                </span>
              )}
              <span className="deploy-field-hint">
                默认 0.3；填 0 表示不主动回复。实际回复概率会随聊天场景浮动。
              </span>
            </div>
          </div>
        )}
        {activeIndex === 4 && (
          <div className="deploy-connection-fields">
            {onebot?.warning && (
              <InlineAlert tone="warning" title="连接提醒">
                {onebot.warning}
              </InlineAlert>
            )}
            <CopyRow
              label="同机连接"
              value={onebot?.url_local || ''}
              hint="NapCat 与 NeoBot 在同一台机器"
              onCopy={copy}
            />
            <CopyRow
              label="局域网连接"
              value={onebot?.url_lan || ''}
              hint="NapCat 在另一台机器"
              onCopy={copy}
            />
            <CopyRow
              label="Access Token"
              value={onebot?.token || ''}
              hint={onebot?.token_enabled ? '填入 NapCat 的同名字段' : '当前未校验握手，建议生成令牌'}
              onCopy={copy}
            />
            <div className="deploy-token-actions">
              <Button size="sm" disabled={disabled} onClick={() => void generateToken()}>
                <RefreshCw size={14} />
                {busy === 'token' ? '生成中…' : onebot?.token_enabled ? '重新生成 token' : '生成 token'}
              </Button>
              <span>生成后立即生效，需要同步更新 NapCat。</span>
            </div>
            <details className="deploy-connection-details">
              <summary>连接参数与自动连接</summary>
              <p>
                当前监听 {onebot?.host || '—'}:{onebot?.port || '—'}，可在「配置管理 → adapter」中修改。路径由
                NapCat 设置，惯例为 <code>{onebot?.path_hint || '/onebot'}</code>，服务端不限制路径。
              </p>
              <p>默认允许所有群聊与私聊回复，需要限定范围时前往「配置管理 → chat」。</p>
              <Button size="sm" disabled title={onebot?.auto_connect?.reason || '后续版本提供'}>
                自动连接（待 NapCat Desktop 支持）
              </Button>
            </details>
          </div>
        )}
      </div>
      <aside className="deploy-step-help">
        <span className="deploy-state-tag">
          {dirtySteps[active.key]
            ? '此步骤有未保存更改'
            : activeStatus?.done
              ? '已配置'
              : active.required
                ? '需要配置'
                : '可选配置'}
        </span>
        <h3>{active.helpTitle}</h3>
        <TipsList>
          {active.tips.map((tip) => (
            <li key={tip}>{tip}</li>
          ))}
        </TipsList>
      </aside>
    </section>
  );
}
