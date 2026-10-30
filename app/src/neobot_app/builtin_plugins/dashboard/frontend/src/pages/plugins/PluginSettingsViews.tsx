import { useEffect, useRef, useState } from 'react';
import type { PluginView } from '../../api/types';
import Button from '../../components/ui/Button';
import { PanelSkeleton } from '../../components/ui/PageSkeleton';
import { useQueryErrorNotice } from '../../hooks/useQueryErrorNotice';
import PluginViewFrame from './PluginViewFrame';
import type { PluginViewConfigAccess, PluginViewSurface, RunPluginAction } from './pluginViewBridge';
import { usePluginViews } from './usePluginViews';

interface Props {
  pluginId: string;
  surface: PluginViewSurface;
  run: RunPluginAction;
  configAccess: PluginViewConfigAccess;
  suspended: boolean;
  declared?: boolean;
  onViewsApplied?: (hasViews: boolean) => void;
  onNavigate: (target: string) => void;
}

function SettingsView({
  view,
  showHeading,
  ...props
}: Props & { view: PluginView & { url: string }; showHeading: boolean }) {
  const [visited, setVisited] = useState(!props.suspended);
  useEffect(() => {
    // 独立页面只延后首次挂载；切换顶层页签时暂停请求并保留输入。
    if (!props.suspended) setVisited(true);
  }, [props.suspended]);
  return (
    <section className="plugin-settings-view" aria-label={view.title}>
      {showHeading && <h3>{view.title}</h3>}
      {visited && (
        <div className="plugin-settings-frame-wrap">
          <PluginViewFrame
            key={view.url}
            {...props}
            view={view}
            mode="live"
            layout="inline"
            suspended={props.suspended || !props.surface.available}
          />
        </div>
      )}
    </section>
  );
}

export default function PluginSettingsViews(props: Props) {
  const declared = props.declared ?? !!props.surface.contract.views?.length;
  const query = usePluginViews(props.pluginId, declared, !props.suspended);
  const root = useRef<HTMLDivElement>(null);
  const [applied, setApplied] = useState<{
    pluginId: string;
    views: Array<PluginView & { url: string }>;
  }>({ pluginId: props.pluginId, views: [] });
  const latest = useRef({ props, declared, data: query.data });
  latest.current = { props, declared, data: query.data };
  useEffect(() => {
    const apply = () => {
      const { props: current, declared, data } = latest.current;
      // 隐藏页、说明书与配置编辑暂停期间保留原窗口；页面内正在输入时同样延后。
      // 每轮读取及返回宿主焦点后重新检查，只应用最新资源集合。
      if (current.suspended || root.current?.contains(document.activeElement)) return;
      if (declared && !data) return;
      const views = declared ? (data ?? []) : [];
      setApplied({ pluginId: current.pluginId, views });
      current.onViewsApplied?.(!!views.length);
    };
    apply();
    document.addEventListener('focusin', apply);
    return () => document.removeEventListener('focusin', apply);
  }, [props.pluginId, props.suspended, declared, query.data]);
  const views = applied.pluginId === props.pluginId ? applied.views : [];
  useQueryErrorNotice(query.error, query.updatedAt, '插件页面读取失败', declared);

  if (!views.length && (!declared || (!query.loading && !query.error))) return null;
  return (
    <div className="plugin-settings-views" ref={root}>
      {query.loading && !views.length ? (
        <PanelSkeleton label="正在读取插件页面…" rows={2} />
      ) : (
        views.map((view) => (
          <SettingsView
            key={`${props.pluginId}:${view.id}`}
            {...props}
            view={view}
            showHeading={views.length > 1}
          />
        ))
      )}
      {query.error && (
        <Button size="sm" variant="ghost" onClick={() => void query.refetch()}>
          重试读取
        </Button>
      )}
    </div>
  );
}
