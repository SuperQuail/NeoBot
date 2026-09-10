// pages/plugins/PluginEditorPanel.tsx —— 插件编辑器（工具条 / 详情 / 配置体 / 页脚）
import { api } from '../../api/endpoints';
import Icon from '../../components/Icon';
import SchemaForm from '../../components/SchemaForm';
import InlineAlert from '../../components/ui/InlineAlert';
import type { PluginEditorPanelProps } from './pluginProps';

export default function PluginEditorPanel(props: PluginEditorPanelProps) {
  const { selected, selectedId, itemsCount, statusLabels, permissions, configDocument, mode, source, draft,
    errors, configError, notice, loading, operation, dirty, isConsole, canEdit, canSave, canReload, canManage,
    editorVersion, actionsRef, onBack, onModeChange, onSourceChange, onChangeField, onRetryRead,
    act, read, save, applyDocument } = props;
  return <section className="workspace-editor" aria-label="在线配置">
      <header className="plugin-editor-toolbar">
        <button className="icon-btn plugin-back" aria-label="返回插件列表" onClick={onBack}><Icon name="back" /></button>
        <div className="plugin-breadcrumb"><Icon name="package" /><span>插件</span><Icon name="chevron" /><strong>{selected?.name || '选择插件'}</strong>
          {dirty && <span className="unsaved-dot" title="有未保存的修改" />}</div>
        <div className="plugin-toolbar-actions" role="group" aria-label="插件操作">
          <button className="icon-btn" disabled={!selected || !permissions.manage_enabled || !!operation}
            aria-label={selected?.enabled ? '停用插件' : '启用插件'}
            title={dirty ? '请先保存或放弃修改' : selected?.enabled ? '停用插件' : '启用插件'}
            onClick={async () => { const result = await act('toggle', () => api.pluginToggle(selectedId), '状态已更新'); if (result?.ok) read(selectedId); }}>
            <Icon name={selected?.enabled ? 'pause' : 'play'} /></button>
          <button className="icon-btn" aria-label="重载插件" title={isConsole ? '面板自身不能热重载' : dirty ? '请先保存或放弃修改' : '重载插件'} disabled={!canReload}
            onClick={() => act('reload', () => api.pluginReload(selectedId), '插件已重载')}><Icon name="refresh" /></button>
          <span className="toolbar-divider" />
          <button className="btn primary" disabled={!canSave} onClick={() => save(true)}><Icon name="save" />
            {operation === 'save' ? '保存中…' : '保存并重载'}</button>
          {/* <details>/<summary> 是原生可交互元素，这里只补 Esc 关闭 */}
          {/* eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions */}
          <details className="plugin-more" ref={actionsRef} onKeyDown={(event) => {
            if (event.key === 'Escape') { event.currentTarget.open = false; event.currentTarget.querySelector<HTMLElement>('summary')?.focus(); }
          }}>
            <summary className="icon-btn" aria-label="更多操作" title="更多操作"><Icon name="more" /></summary>
            <div className="plugin-action-menu" role="group" aria-label="更多插件操作">
              <button disabled={!!operation || !itemsCount}
                onClick={() => act('check', () => api.pluginsCheckUpdates(), '更新检查完成')}><Icon name="search" />检查全部更新</button>
              {selected?.manageable && selected?.repo && <button disabled={!canManage}
                onClick={() => { if (confirm(`更新 ${selected.name}？这会重载插件，当前运行中的任务可能中断。`)) act('update', () => api.pluginUpdate(selectedId), '更新完成').then((result) => { if (result?.ok) read(selectedId); }); }}><Icon name="download" />更新此插件</button>}
              {canEdit && <button disabled={!canSave} onClick={() => save(false)}><Icon name="save" />仅保存配置</button>}
              <button disabled={!dirty || !!operation} onClick={() => {
                if (confirm('放弃所有未保存的修改？')) { if (configDocument) applyDocument(configDocument, mode); if (actionsRef.current) actionsRef.current.open = false; }
              }}><Icon name="undo" />放弃修改</button>
              <hr />
              <button className="danger" disabled={!canManage}
                onClick={() => { if (confirm(`确认卸载 ${selected?.name ?? ''}？插件代码会被移入备份目录，独立的数据目录会保留。`)) act('uninstall', () => api.pluginUninstall(selectedId), '已卸载'); }}><Icon name="trash" />卸载插件</button>
            </div>
          </details>
        </div>
      </header>
      {!selected ? <div className="workspace-empty"><Icon name="package" /><h2>{selectedId ? '插件已不在列表中' : '选择一个插件'}</h2>
        <p>{selectedId && dirty ? '尚未保存的内容已保留。请先恢复插件，再保存配置。' : '在左侧管理插件，在这里调整配置。'}</p></div> : <>
        <div className="workspace-scroll plugin-editor-scroll">
          <div className="plugin-intro">
            <div className="plugin-title-row"><div className="plugin-large-icon"><Icon name="package" /></div>
              <div><div className="plugin-title"><h2>{selected.name}</h2><span className={`plugin-state ${selected.status}`}>
                <i className={`plugin-status-dot ${selected.status}`} />{statusLabels[selected.status] || selected.status}</span></div>
                <p>{selected.description || '在这里管理插件并编辑运行配置。'}</p></div></div>
            <div className="plugin-meta">
              <span className={'source-badge' + (selected.official ? ' official' : '')}>{selected.official ? '官方插件' : '第三方插件'}</span>
              <span className="meta-chip">v{selected.version || '—'}</span>
              <span className={'hot-badge ' + (selected.hot_reload === false ? 'cold' : 'hot')}
                title={selected.hot_reload === false ? '插件本体不支持热重载，改动需重启 NeoBot' : '可在面板内直接重载插件'}>
                {selected.hot_reload === false ? '本体需重启' : '可热重载'}
              </span>
              <span className={'hot-badge ' + (selected.config_hot_reload === false ? 'cold' : 'hot')}
                title={selected.config_hot_reload === false ? '插件配置改动需重启 NeoBot' : '插件配置改动可不重启生效'}>
                {selected.config_hot_reload === false ? '配置需重启' : '配置可热重载'}
              </span>
              {selected.author && <span className="meta-chip">{selected.author}</span>}
              {selected.repo && /^https?:\/\//i.test(selected.repo) && <a className="meta-chip" href={selected.repo} target="_blank" rel="noopener noreferrer">插件仓库 <Icon name="external" /></a>}
              {selected.homepage && !selected.repo && /^https?:\/\//i.test(selected.homepage) && <a className="meta-chip" href={selected.homepage} target="_blank" rel="noopener noreferrer">主页 <Icon name="external" /></a>}
              {(selected.tags || []).map((tag) => <span className="meta-chip" key={tag}>{tag}</span>)}
            </div>
          </div>
          {!permissions.manage_enabled ? <div className="workspace-empty"><Icon name="settings" /><h3>当前为只读模式</h3>
            <p>请在「配置管理 → 本体配置 → dashboard」中开启 manage_plugins。</p></div> : <>
            <>
              {selected.official && (
                <div className="config-notice" role="status">
                  <Icon name="settings" />
                  官方插件配置来自本体 <code>config.toml</code> 的 <code>[{configDocument?.section || selected.config_section || selected.name}]</code> 分区，保存后写回该分区。
                </div>
              )}
              <div className="config-tabs"><div role="tablist" aria-label="配置编辑方式">
                <button role="tab" aria-selected={mode === 'form'} className={mode === 'form' ? 'active' : ''}
                  disabled={!configDocument?.form_supported || !!operation} onClick={() => onModeChange('form')}><Icon name="settings" />配置表单</button>
                <button role="tab" aria-selected={mode === 'toml'} className={mode === 'toml' ? 'active' : ''}
                  disabled={!configDocument?.source_available || !!operation} onClick={() => onModeChange('toml')}><Icon name="code" />TOML</button>
              </div><span className="muted small">{selected.official ? 'config.toml / ' + (configDocument?.section || selected.config_section || selected.name) : 'plugin.toml / config'}</span></div>
              {notice && <InlineAlert tone={notice.warning ? 'warning' : 'success'}>{notice.text}</InlineAlert>}
              {selected.error && <InlineAlert tone="error">运行错误：{selected.error}</InlineAlert>}
              {configError && (
                <InlineAlert
                  tone="error"
                  actions={
                    <button className="btn-sm" disabled={!!operation} onClick={() => { if (!dirty || confirm('重新读取会放弃当前修改，是否继续？')) onRetryRead(); }}>重新读取</button>
                  }
                >
                  {configError}
                </InlineAlert>
              )}
              {errors.length > 0 && (
                <InlineAlert
                  tone="error"
                  items={errors.map((item, index) => (
                    <span key={index}><code>{item.path || '?'}</code> {item.message}</span>
                  ))}
                />
              )}
              {loading ? <p className="empty muted" role="status">正在读取配置…</p> : configDocument && <div className="config-body" role="tabpanel">
                {mode === 'form' ? <SchemaForm key={`${selectedId}-${editorVersion}`} fields={configDocument.schema || []} values={draft}
                  baseline={configDocument.config || {}}
                  disabled={!!operation} onChange={onChangeField} /> : <>
                  <p className="muted small">编辑 [config] 及其子表。插件名称、版本等信息保持不变。</p>
                  <textarea className="toml-editor" aria-label="TOML 配置" spellCheck={false} disabled={!!operation}
                    value={source} onChange={(event) => onSourceChange(event.target.value)} />
                </>}
              </div>}
            </>
          </>}
        </div>
        <footer className="plugin-editor-footer" role="status"><span className={dirty ? 'dirty-label' : 'muted'}>
          <i className={`plugin-status-dot ${dirty ? 'pending' : ''}`} />{dirty ? '有未保存的修改' : configDocument ? '配置与文件同步' : '等待配置'}</span>
          <span className="muted">{operation ? '正在处理…' : selected.official ? '官方插件随本体更新' : '支持保存后热重载'}</span></footer>
      </>}
  </section>;
}
