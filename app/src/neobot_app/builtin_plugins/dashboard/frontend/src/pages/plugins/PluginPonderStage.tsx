import { useLayoutEffect, useRef, useState } from 'react';
import { MousePointer2 } from 'lucide-react';
import type { PluginGuide, PluginGuideStep, PluginView } from '../../api/types';
import type { PluginAnchorRect, PluginViewSurface } from './pluginViewBridge';
import PluginViewFrame from './PluginViewFrame';
import PluginCommandScene from './PluginCommandScene';
import PluginConfigScene from './PluginConfigScene';
import { ponderGeometry } from './ponderGeometry';

interface Props {
  pluginId: string;
  surface: PluginViewSurface;
  guide: PluginGuide;
  step: PluginGuideStep;
  views: Array<PluginView & { url: string }>;
  reducedMotion: boolean;
}

export default function PluginPonderStage({ pluginId, surface, guide, step, views, reducedMotion }: Props) {
  const viewport = useRef<HTMLDivElement>(null);
  const [rectangles, setRectangles] = useState<Record<string, PluginAnchorRect>>({});
  const [control, setControl] = useState<PluginAnchorRect>();
  const [size, setSize] = useState({ width: 0, height: 0 });
  const view = step.command ? undefined : views.find((item) => step.target.startsWith(`view.${item.id}.`));
  const action = surface.contract.actions.find((item) => step.target === `action.${item.id}`);
  const resource = surface.contract.resources.find((item) => step.target === `resource.${item.id}`);
  const anchor = view ? step.target.slice(`view.${view.id}.`.length) : '';
  const rectangle = view ? rectangles[anchor] : control;
  // iframe 已经裁出局部滚动区中的可见范围，不能再向外扩展。
  const highlight = ponderGeometry(rectangle, size.width, size.height, view ? 0 : 6);
  const samples = Object.entries(step.example ?? {}).map(([key, value]) => ({
    key,
    label: key,
    text: typeof value === 'object' ? JSON.stringify(value) : String(value),
  }));

  useLayoutEffect(() => {
    const stage = viewport.current;
    if (!stage) return;
    const configPath =
      step.form && step.target.startsWith('config.') && step.form !== 'save' && step.form !== 'saved'
        ? step.target.slice('config.'.length)
        : undefined;
    const configControl = configPath
      ? Array.from(stage.querySelectorAll<HTMLElement>('[data-field-path]')).find(
          (element) => element.dataset.fieldPath === configPath,
        )
      : undefined;
    const target = view ? null : (configControl ?? stage.querySelector<HTMLElement>('[data-ponder-control]'));
    const measure = (reveal = false) => {
      setSize({ width: stage.clientWidth, height: stage.clientHeight });
      if (!target) {
        setControl(undefined);
        return;
      }
      const scroll = stage.querySelector<HTMLElement>('.ponder-synthetic-stage');
      if (reveal && scroll) {
        const area = scroll.getBoundingClientRect();
        const item = target.getBoundingClientRect();
        if (item.top < area.top + 8 || item.height > scroll.clientHeight - 16)
          scroll.scrollTop += item.top - area.top - 8;
        else if (item.bottom > area.bottom - 8) scroll.scrollTop += item.bottom - area.bottom + 8;
      }
      const bounds = stage.getBoundingClientRect();
      const rect = target.getBoundingClientRect();
      setControl({
        left: rect.left - bounds.left - stage.clientLeft,
        top: rect.top - bounds.top - stage.clientTop,
        width: rect.width,
        height: rect.height,
      });
    };
    measure(true);
    // 内容异步撑高、舞台缩放或场景滚动，都重新计算可见高亮。
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(() => measure(true));
    observer?.observe(stage);
    if (target) observer?.observe(target);
    const onScroll = () => measure();
    const onResize = () => measure(true);
    window.addEventListener('resize', onResize);
    stage.addEventListener('scroll', onScroll, true);
    return () => {
      observer?.disconnect();
      window.removeEventListener('resize', onResize);
      stage.removeEventListener('scroll', onScroll, true);
    };
  }, [step, view]);

  return (
    <div className="ponder-stage-viewport" ref={viewport} data-reduced-motion={reducedMotion || undefined}>
      {step.command ? (
        <PluginCommandScene command={step.command} />
      ) : step.target === 'config' || step.target.startsWith('config.') ? (
        <PluginConfigScene
          pluginId={pluginId}
          schema={surface.contract.config}
          fields={surface.configFields}
          step={step}
        />
      ) : view ? (
        <PluginViewFrame
          key={`${view.id}:${view.url}`}
          pluginId={pluginId}
          view={view}
          surface={surface}
          mode="demo"
          demo={guide.demo}
          step={step}
          run={async () => null}
          onNavigate={() => {}}
          onAnchors={setRectangles}
        />
      ) : (
        <div className="ponder-synthetic-stage">
          <div className="ponder-stage-heading">
            <span>{action?.title || resource?.title || step.chapter || guide.title}</span>
            <span>功能说明</span>
          </div>
          <div className="ponder-stage-content" data-ponder-control>
            {samples.length ? (
              samples.map((sample) => (
                <div className="ponder-reference-value" key={sample.key}>
                  <span>{sample.label}</span>
                  <pre>{sample.text}</pre>
                </div>
              ))
            ) : (
              <div className="ponder-sample-empty">
                <p>{step.chapter || '了解这一步'}</p>
                <span>{step.text}</span>
              </div>
            )}
          </div>
        </div>
      )}
      {highlight && (
        <>
          <div className="ponder-focus-frame" aria-hidden="true" style={highlight.frame} />
          {highlight.cursor && (
            <div className="ponder-cursor" aria-hidden="true" style={highlight.cursor}>
              <MousePointer2 size={29} fill="currentColor" />
            </div>
          )}
        </>
      )}
    </div>
  );
}
