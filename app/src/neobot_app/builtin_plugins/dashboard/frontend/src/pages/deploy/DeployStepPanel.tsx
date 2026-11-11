import { RefreshCw } from 'lucide-react';
import Button from '../../components/ui/Button';
import InlineAlert from '../../components/ui/InlineAlert';
import { STEPS } from './deployModel';
import type { DeployEditor } from './useDeployEditor';

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
    qqSecret,
    setQqSecret,
    disabled,
    chanceError,
    updateDraft,
    dirtySteps,
    busy,
    startOfficialBind,
  } = editor;
  const active = STEPS[activeIndex];
  const activeStatus = doc?.steps?.find((step) => step.key === active.key);
  const official = doc?.official;
  const defaults = doc?.defaults || {};
  const TipsList = activeIndex === 4 ? 'ol' : 'ul';

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
                机器人 QQ 号 <span>官方可留空</span>
              </span>
              <input
                id="deploy-account"
                className="input"
                inputMode="numeric"
                value={draft.account}
                disabled={disabled}
                onChange={(event) => updateDraft('account', event.target.value)}
                placeholder={
                  defaults.bot_account
                    ? '官方通道可留空（自动获取）；OneBot 填：' + defaults.bot_account
                    : '官方通道可留空；OneBot 例如 123456789'
                }
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
                超级管理员（QQ号或 openid）<span>选填</span>
              </span>
              <input
                id="deploy-admin"
                className="input"
                inputMode="text"
                value={draft.adminQq}
                disabled={disabled}
                onChange={(event) => updateDraft('adminQq', event.target.value)}
                placeholder="QQ号或官方 openid（控制台聊天流可复制）"
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
          <div className="deploy-official-fields">
            <div className="deploy-official-status">
              <span className="deploy-state-tag">
                {official?.bound
                  ? '已绑定'
                  : official?.bind?.phase === 'pending'
                    ? '等待扫码'
                    : '未绑定'}
              </span>
              {official?.nickname || official?.account ? (
                <span>
                  {official?.nickname || '官方机器人'}
                  {official?.account ? `（${official.account}）` : ''}
                </span>
              ) : null}
              {official?.mode ? <span>当前模式：{official.mode}</span> : null}
            </div>
            {official?.bound ? (
              <InlineAlert tone="success" title="官方机器人已绑定">
                机器人 QQ 号由官方 API 自动获取，无需填写 NapCat 连接信息。
              </InlineAlert>
            ) : (
              <div className="deploy-qr-wrap">
                {official?.bind?.svg ? (
                  <div
                    className="deploy-qr-box"
                    aria-label="官方机器人绑定二维码"
                    dangerouslySetInnerHTML={{ __html: official.bind.svg }}
                  />
                ) : (
                  <div className="deploy-qr-box is-empty">
                    {official?.bind?.error || '点击下方按钮生成二维码'}
                  </div>
                )}
                <div className="deploy-qr-actions">
                  <Button size="sm" disabled={disabled} onClick={() => void startOfficialBind()}>
                    <RefreshCw size={14} />
                    {busy === 'bind' ? '生成中…' : '开始扫码绑定'}
                  </Button>
                  {official?.bind?.url ? (
                    <a href={official.bind.url} target="_blank" rel="noopener noreferrer">
                      打开绑定链接
                    </a>
                  ) : null}
                </div>
                {official?.bind?.error ? (
                  <p className="deploy-field-hint field-error">{official.bind.error}</p>
                ) : null}
              </div>
            )}
            <div className="deploy-fields deploy-official-manual">
              <p className="deploy-field-hint">
                也可以手动填写开放平台信息；AppSecret 只写不读，不会保存到浏览器。
              </p>
              <label className="deploy-field" htmlFor="deploy-qq-appid">
                <span className="deploy-field-label">
                  AppID <span>选填</span>
                </span>
                <input
                  id="deploy-qq-appid"
                  className="input"
                  value={draft.qqAppId}
                  disabled={disabled}
                  onChange={(event) => updateDraft('qqAppId', event.target.value)}
                  placeholder="开放平台机器人 AppID"
                />
              </label>
              <label className="deploy-field" htmlFor="deploy-qq-secret">
                <span className="deploy-field-label">
                  AppSecret <span>{official?.secret_set ? '已设置，留空保留' : '选填'}</span>
                </span>
                <input
                  id="deploy-qq-secret"
                  className="input"
                  type="password"
                  autoComplete="new-password"
                  value={qqSecret}
                  disabled={disabled}
                  onChange={(event) => setQqSecret(event.target.value)}
                  placeholder={official?.secret_set ? '已设置，留空保留' : '填写 AppSecret'}
                />
              </label>
              <span className="deploy-field-hint">
                填写后点「保存并应用」自动切换到官方通道；扫码绑定则不需要手动填写。
              </span>
            </div>
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
