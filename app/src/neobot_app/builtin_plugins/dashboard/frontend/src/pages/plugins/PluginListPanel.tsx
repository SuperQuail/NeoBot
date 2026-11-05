// pages/plugins/PluginListPanel.tsx —— 插件列表侧栏（搜索 / 来源筛选 / 状态分组 / 底部状态）
import Icon from '../../components/Icon';
import { PanelSkeleton } from '../../components/ui/PageSkeleton';
import type { PluginListPanelProps } from './pluginProps';

export default function PluginListPanel(props: PluginListPanelProps) {
  const {
    items,
    visible,
    statusLabels,
    statusGroups,
    pluginId,
    selectedId,
    collapsed,
    setCollapsed,
    filter,
    setFilter,
    sourceFilter,
    setSourceFilter,
    sourceFilters,
    searchRef,
    listLoading,
    listError,
    operation,
    proxy,
    onSelect,
    onOpenProxy,
  } = props;
  return (
    <aside className="workspace-panel plugin-sidebar" aria-label="插件列表">
      <div className="plugin-sidebar-body">
        <div className="plugin-sidebar-heading">
          <h2>已安装</h2>
          <span>{items.length} 个插件</span>
        </div>
        <div className="plugin-search">
          <Icon name="search" />
          <input
            ref={searchRef}
            aria-label="搜索插件"
            placeholder="搜索插件…"
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
          />
          <kbd>Ctrl K</kbd>
        </div>
        <div className="plugin-source-filter" role="group" aria-label="按来源筛选">
          {sourceFilters.map(([key, label]) => (
            <button
              key={key}
              className={sourceFilter === key ? 'active' : ''}
              onClick={() => setSourceFilter(key)}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="workspace-scroll plugin-list">
          {listLoading && <PanelSkeleton label="正在读取插件…" kind="list" rows={5} />}
          {!listLoading && !listError && visible.length === 0 && (
            <p className="empty muted">{filter ? '没有匹配的插件' : '还没有安装插件'}</p>
          )}
          {statusGroups.map(([status, label]) => {
            const plugins = visible.filter((plugin) =>
              status === 'other'
                ? !['loaded', 'disabled', 'error'].includes(plugin.status)
                : plugin.status === status,
            );
            return (
              plugins.length > 0 && (
                <section className="plugin-group" key={status}>
                  <h2>
                    <button
                      className="plugin-group-toggle"
                      aria-expanded={!!filter || !collapsed[status]}
                      aria-controls={`plugin-group-${status}`}
                      onClick={() => setCollapsed((current) => ({ ...current, [status]: !current[status] }))}
                    >
                      <Icon name="chevron" />
                      {label}
                      <span>{plugins.length}</span>
                    </button>
                  </h2>
                  <div id={`plugin-group-${status}`} hidden={!filter && collapsed[status]}>
                    {plugins.map((plugin) => (
                      <button
                        key={pluginId(plugin)}
                        className={`plugin-list-item ${selectedId === pluginId(plugin) ? 'selected' : ''}`}
                        disabled={!!operation}
                        onClick={() => onSelect(plugin)}
                        aria-current={selectedId === pluginId(plugin) ? 'true' : undefined}
                      >
                        <span className="plugin-item-icon">
                          <Icon name="package" />
                        </span>
                        <span className="plugin-item-copy">
                          <span>{plugin.name}</span>
                          <small>
                            <span className={'source-badge' + (plugin.official ? ' official' : '')}>
                              {plugin.official ? '官方' : '第三方'}
                            </span>
                            {plugin.version || '未声明版本'}
                            {plugin.auto_disabled && (
                              <span className="source-badge" title={plugin.disabled_reason || '依赖未满足'}>
                                依赖未满足
                              </span>
                            )}
                          </small>
                        </span>
                        <span
                          className={`plugin-status-dot ${plugin.status}`}
                          role="img"
                          aria-label={statusLabels[plugin.status] || plugin.status}
                        />
                      </button>
                    ))}
                  </div>
                </section>
              )
            );
          })}
        </div>
      </div>
      <footer className="plugin-sidebar-footer">
        <span>
          <i className="plugin-status-dot loaded" />
          {items.filter((plugin) => plugin.status === 'loaded').length} 个运行中
        </span>
        <span className="muted small" title={proxy.description || ''}>
          {proxy.description || '代理：跟随系统'}
        </span>
        <button
          className="icon-btn"
          aria-label="插件下载代理设置"
          title="插件下载代理设置"
          disabled={!!operation}
          onClick={onOpenProxy}
        >
          <Icon name="settings" />
        </button>
      </footer>
    </aside>
  );
}
