// pages/plugins/PluginEditorPanel.tsx —— 插件编辑器（工具条 / 详情 / 配置体 / 页脚）
import { useState } from 'react';
import { api } from '../../api/endpoints';
import Icon from '../../components/Icon';
import Button from '../../components/ui/Button';
import EmptyState from '../../components/ui/EmptyState';
import { PanelSkeleton } from '../../components/ui/PageSkeleton';
import SchemaForm from '../../components/SchemaForm';
import InlineAlert from '../../components/ui/InlineAlert';
import Modal from '../../components/Modal';
import TomlEditor from '../../components/TomlEditor';
import type { PluginEditorPanelProps } from './pluginProps';
import { confirmAction } from '../../components/ui/ConfirmDialog';
import { useAuthGate } from '../../auth/AuthContext';
import SpeakingScheduleForm from './SpeakingScheduleForm';

export default function PluginEditorPanel(props: PluginEditorPanelProps) {
  const { canManage: sessionCanManage } = useAuthGate();
  const sessionReadOnly = sessionCanManage === false;
  const [infoOpen, setInfoOpen] = useState(false);
  const {
    selected,
    selectedPresent,
    selectedId,
    itemsCount,
    statusLabels,
    permissions,
    configDocument,
    mode,
    source,
    draft,
    errors,
    configError,
    loading,
    operation,
    dirty,
    isConsole,
    canEdit: editorAvailable,
    canSave: saveAvailable,
    canReload: reloadAvailable,
    canManage: manageAvailable,
    editorVersion,
    actionsRef,
    onBack,
    onModeChange,
    onSourceChange,
    onChangeField,
    onRetryRead,
    act,
    read,
    save,
    applyDocument,
  } = props;
  const canEdit = !sessionReadOnly && editorAvailable;
  const canSave = !sessionReadOnly && saveAvailable;
  const canReload = !sessionReadOnly && reloadAvailable;
  const canManage = !sessionReadOnly && manageAvailable;
  return (
    <section className="workspace-editor" aria-label="在线配置">
      <div className="plugin-editor-body">
        <header className="plugin-editor-toolbar">
          <button className="icon-btn plugin-back" aria-label="返回插件列表" onClick={onBack}>
            <Icon name="back" />
          </button>
          <div className="plugin-identity">
            <div className="plugin-identity-name">
              <h2>{selected?.name || '选择插件'}</h2>
              {selected && (
                <span className={`plugin-identity-status ${selected.status}`}>
                  <i className={`plugin-status-dot ${selected.status}`} />
                  {statusLabels[selected.status] || selected.status}
                </span>
              )}
            </div>
            {selected && (
              <div className="plugin-identity-meta">
                <span>{selected.official ? '官方插件' : '第三方插件'}</span>
                <span>v{selected.version || '—'}</span>
              </div>
            )}
          </div>
          <div className="plugin-toolbar-actions" role="group" aria-label="插件操作">
            <Button
              size="sm"
              disabled={
                sessionReadOnly ||
                !selected ||
                !selectedPresent ||
                !permissions.manage_enabled ||
                !!operation ||
                dirty ||
                isConsole
              }
              aria-label={selected?.enabled === false ? '启用插件' : '停用插件'}
              title={
                isConsole
                  ? '面板自身不能停用'
                  : dirty
                    ? '请先保存或放弃修改'
                    : selected?.enabled === false
                      ? '启用插件'
                      : '停用插件'
              }
              onClick={async () => {
                const enabling = selected?.enabled === false;
                if (
                  !enabling &&
                  !(await confirmAction({
                    title: '停用 ' + (selected?.name ?? '') + '？',
                    description: '依赖它的插件会被联动停用，恢复前置插件后自动重新加载。',
                    confirmLabel: '停用插件',
                    danger: true,
                  }))
                )
                  return;
                const result = await act(
                  'toggle',
                  () => api.pluginToggle(selectedId),
                  enabling ? '插件已启用' : '插件已停用',
                );
                if (result?.ok) void read(selectedId);
              }}
            >
              <Icon name={selected?.enabled === false ? 'play' : 'pause'} />
              {selected?.enabled === false ? '启用插件' : '停用插件'}
            </Button>
            <Button
              size="sm"
              aria-label="重载插件"
              title={isConsole ? '面板自身不能热重载' : dirty ? '请先保存或放弃修改' : '重载插件'}
              disabled={!canReload}
              onClick={() => act('reload', () => api.pluginReload(selectedId), '插件已重载')}
            >
              <Icon name="refresh" />
              重载
            </Button>
            {/* <details>/<summary> 是原生可交互元素，这里只补 Esc 关闭 */}
            {/* eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions */}
            <details
              className="plugin-more"
              ref={actionsRef}
              onKeyDown={(event) => {
                if (event.key === 'Escape') {
                  event.currentTarget.open = false;
                  event.currentTarget.querySelector<HTMLElement>('summary')?.focus();
                }
              }}
            >
              <summary className="icon-btn" aria-label="更多操作" title="更多操作">
                <Icon name="more" />
              </summary>
              <div className="plugin-action-menu" role="group" aria-label="更多插件操作">
                <button
                  disabled={!!operation || !itemsCount}
                  onClick={() => act('check', () => api.pluginsCheckUpdates(), '更新检查完成')}
                >
                  <Icon name="search" />
                  检查全部更新
                </button>
                {selected?.manageable && selected?.repo && (
                  <button
                    disabled={!canManage}
                    onClick={async () => {
                      if (
                        await confirmAction({
                          title: `更新 ${selected.name}？`,
                          description: '更新会重载插件，当前运行中的任务可能中断。',
                          confirmLabel: '更新插件',
                        })
                      ) {
                        const result = await act('update', () => api.pluginUpdate(selectedId), '更新完成');
                        if (result?.ok) await read(selectedId);
                      }
                    }}
                  >
                    <Icon name="download" />
                    更新此插件
                  </button>
                )}
                {canEdit && (
                  <button disabled={!canSave} onClick={() => save(false)}>
                    <Icon name="save" />
                    仅保存配置
                  </button>
                )}
                <button
                  disabled={!dirty || !!operation}
                  onClick={async () => {
                    if (
                      await confirmAction({
                        title: '放弃配置修改？',
                        description: '恢复到上一次读取的插件配置。',
                        confirmLabel: '放弃修改',
                        danger: true,
                      })
                    ) {
                      if (configDocument) applyDocument(configDocument, mode);
                      if (actionsRef.current) actionsRef.current.open = false;
                    }
                  }}
                >
                  <Icon name="undo" />
                  放弃修改
                </button>
                <hr />
                <button
                  className="danger"
                  disabled={!canManage}
                  onClick={async () => {
                    if (
                      await confirmAction({
                        title: `卸载 ${selected?.name ?? ''}？`,
                        description:
                          '插件代码会移入备份目录，独立的数据目录会保留。依赖此插件的扩展会联动停用。',
                        confirmLabel: '卸载插件',
                        danger: true,
                      })
                    )
                      await act('uninstall', () => api.pluginUninstall(selectedId), '已卸载');
                  }}
                >
                  <Icon name="trash" />
                  卸载插件
                </button>
              </div>
            </details>
          </div>
        </header>
        {!selected ? (
          <div className="workspace-empty">
            <Icon name="package" />
            <h2>{selectedId ? '插件已不在列表中' : '选择一个插件'}</h2>
            <p>
              {selectedId && dirty
                ? '尚未保存的内容已保留。请先恢复插件，再保存配置。'
                : '在左侧管理插件，在这里调整配置。'}
            </p>
          </div>
        ) : (
          <>
            {!selectedPresent && (
              <InlineAlert tone="warning" title="插件已不在列表中">
                当前编辑内容已保留，恢复插件后再保存。
              </InlineAlert>
            )}
            <div className="plugin-config-toolbar">
              <div className="plugin-mode-tabs" role="tablist" aria-label="配置编辑方式">
                <button
                  role="tab"
                  aria-selected={mode === 'form'}
                  className={mode === 'form' ? 'active' : ''}
                  disabled={!configDocument?.form_supported || !!operation}
                  onClick={() => onModeChange('form')}
                >
                  <Icon name="settings" size={15} />
                  配置表单
                </button>
                <button
                  role="tab"
                  aria-selected={mode === 'toml'}
                  className={mode === 'toml' ? 'active' : ''}
                  disabled={!configDocument?.source_available || !!operation}
                  onClick={() => onModeChange('toml')}
                >
                  <Icon name="code" size={15} />
                  TOML
                </button>
              </div>
              <Button size="sm" variant="ghost" onClick={() => setInfoOpen(true)}>
                插件信息
                <Icon name="chevron" size={14} />
              </Button>
            </div>
            <div
              className={'workspace-scroll plugin-editor-scroll' + (mode === 'toml' ? ' is-source' : '')}
              key={selectedId}
            >
              {!permissions.manage_enabled ? (
                <EmptyState icon="settings" title="当前为只读模式">
                  <p>
                    请在「插件 → dashboard → 配置」里把 <code>manage_plugins</code> 设为
                    true（该配置属于面板插件自己，不在本体 <code>config.toml</code> 里）。
                  </p>
                </EmptyState>
              ) : (
                <>
                  {!!selected.dependency_issues?.length && !selected.disabled_reason && (
                    <InlineAlert tone="warning">
                      前置插件未满足：{selected.dependency_issues.join('；')}
                    </InlineAlert>
                  )}
                  {selected.disabled_reason && (
                    <InlineAlert tone="warning">
                      已因前置插件未满足自动禁用：{selected.disabled_reason}
                      <span className="muted small">（启用对应前置插件后会自动恢复，无需手动重新启用）</span>
                    </InlineAlert>
                  )}
                  {selected.error && <InlineAlert tone="error">运行错误：{selected.error}</InlineAlert>}
                  {selected.config_error && (
                    <InlineAlert tone="warning">
                      配置告警：{selected.config_error}（已回落到默认值运行）
                    </InlineAlert>
                  )}
                  {configError && (
                    <InlineAlert
                      tone="error"
                      actions={
                        <Button
                          size="sm"
                          disabled={!!operation}
                          onClick={async () => {
                            if (
                              !dirty ||
                              (await confirmAction({
                                title: '重新读取插件配置？',
                                description: '当前尚未保存的插件配置修改会丢失。',
                                confirmLabel: '重新读取',
                                danger: true,
                              }))
                            )
                              onRetryRead();
                          }}
                        >
                          重新读取
                        </Button>
                      }
                    >
                      {configError}
                    </InlineAlert>
                  )}
                  {errors.length > 0 && (
                    <InlineAlert
                      tone="error"
                      items={errors.map((item, index) => (
                        <span key={index}>
                          <code>{item.path || '?'}</code> {item.message}
                        </span>
                      ))}
                    />
                  )}
                  {loading ? (
                    <PanelSkeleton label="正在读取配置…" rows={4} />
                  ) : (
                    configDocument && (
                      <div className="config-body" role="tabpanel">
                        {mode === 'form' && selected.official && selected.name === 'speaking_schedule' ? (
                          <SpeakingScheduleForm
                            key={`${selectedId}-${editorVersion}`}
                            value={draft}
                            disabled={!canEdit || !!operation}
                            onChange={onChangeField}
                          />
                        ) : mode === 'form' ? (
                          <SchemaForm
                            key={`${selectedId}-${editorVersion}`}
                            fields={configDocument.schema || []}
                            showReloadSummary={false}
                            values={draft}
                            baseline={configDocument.config || {}}
                            disabled={!canEdit || !!operation}
                            onChange={onChangeField}
                          />
                        ) : (
                          <TomlEditor
                            ariaLabel="TOML 配置"
                            fileName={`${selected.name}/config.toml`}
                            filePath={configDocument.path}
                            disabled={!!operation}
                            readOnly={!canEdit}
                            value={source}
                            onChange={(value) => {
                              if (canEdit && !operation) onSourceChange(value);
                            }}
                            onSave={() => {
                              if (canSave) void save(true);
                            }}
                            saveDisabled={!canSave}
                          />
                        )}
                      </div>
                    )
                  )}
                </>
              )}
            </div>
          </>
        )}
      </div>
      {selected && (
        <>
          <footer className="plugin-editor-footer">
            <div role="status">
              <span className={dirty ? 'dirty-label' : 'muted'}>
                <i className={`plugin-status-dot ${dirty ? 'pending' : ''}`} />
                {dirty ? '有未保存的修改' : configDocument ? '配置与文件同步' : '等待配置'}
              </span>
              {(operation || selected.config_hot_reload === false) && (
                <span className="muted small">
                  {operation ? '正在处理…' : '配置改动需重启 NeoBot 后生效'}
                </span>
              )}
            </div>
            <Button
              variant="primary"
              disabled={!canSave}
              onClick={() => save(true)}
              title={mode === 'toml' ? '编辑 [config] 及其子表，保存前自动校验。' : undefined}
            >
              <Icon name="save" />
              {operation === 'save' ? '保存中…' : '保存并重载'}
            </Button>
          </footer>
          <Modal open={infoOpen} title={`${selected.name} · 插件信息`} onClose={() => setInfoOpen(false)}>
            <div className="plugin-info-content">
              <p className="plugin-info-description">{selected.description || '暂无插件说明。'}</p>
              <dl className="plugin-info-grid">
                <dt>来源 / 版本</dt>
                <dd>
                  {selected.official ? '官方插件' : '第三方插件'} · v{selected.version || '—'}
                </dd>
                {selected.author && (
                  <>
                    <dt>作者</dt>
                    <dd>{selected.author}</dd>
                  </>
                )}
                <dt>插件更新</dt>
                <dd>
                  {selected.official
                    ? '随 NeoBot 本体更新'
                    : selected.repo
                      ? '在更多操作中检查或更新插件'
                      : '此插件未提供更新仓库'}
                </dd>
                <dt>重载能力</dt>
                <dd>
                  {selected.hot_reload === false ? '插件本体需重启' : '插件本体可热重载'}；
                  {selected.config_hot_reload === false ? '配置改动需重启' : '配置改动可热重载'}
                </dd>
                <dt>配置文件</dt>
                <dd>
                  <code>{configDocument?.path || 'plugins_data/' + selected.name + '/config.toml'}</code>
                </dd>
                {!!selected.dependencies?.length && (
                  <>
                    <dt>前置插件</dt>
                    <dd>{selected.dependencies.join('、')}</dd>
                  </>
                )}
                {!!selected.dependents?.length && (
                  <>
                    <dt>依赖此插件</dt>
                    <dd>
                      {selected.dependents.join('、')}
                      <small>停用或卸载此插件时会联动停用。</small>
                    </dd>
                  </>
                )}
                {!!selected.tags?.length && (
                  <>
                    <dt>标签</dt>
                    <dd>{selected.tags.join(' · ')}</dd>
                  </>
                )}
              </dl>
              {!!selected.command_renames?.length && (
                <div className="plugin-info-notes">
                  <strong>命令名称调整</strong>
                  {selected.command_renames.map((item) => (
                    <p key={item.actual}>
                      {item.message || `原 ${item.requested} → 实际 ${item.actual}（重名）`}
                    </p>
                  ))}
                </div>
              )}
              <p className="plugin-info-notes">
                配置与启停状态分别保存。停用后仍可编辑配置；插件更新会保留独立配置文件。
              </p>
              {selected.repo && /^https?:\/\//i.test(selected.repo) && (
                <a
                  className="plugin-info-link"
                  href={selected.repo}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  访问插件仓库 <Icon name="external" size={14} />
                </a>
              )}
              {selected.homepage && !selected.repo && /^https?:\/\//i.test(selected.homepage) && (
                <a
                  className="plugin-info-link"
                  href={selected.homepage}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  访问插件主页 <Icon name="external" size={14} />
                </a>
              )}
            </div>
          </Modal>
        </>
      )}
    </section>
  );
}
