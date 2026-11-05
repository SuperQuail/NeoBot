import { useCallback, useEffect, useRef, useState } from 'react';
import { useReducedEffects } from '../../hooks/useReducedEffects';
import { infoBar } from '../../notifications/infoBar';
import type { PluginGuideDemo, PluginGuideStep, PluginView } from '../../api/types';
import {
  createPluginViewBridge,
  type RunPluginAction,
  type PluginAnchorRect,
  type PluginViewContext,
  type PluginViewConfigAccess,
  type PluginViewSurface,
} from './pluginViewBridge';
import { revealPluginFocus } from './pluginViewFocus';

interface Props {
  pluginId: string;
  view: PluginView & { url: string };
  surface: PluginViewSurface;
  run: RunPluginAction;
  demo?: PluginGuideDemo;
  step?: PluginGuideStep;
  locate?: string;
  locateRequest?: number;
  onNavigate: (target: string) => void;
  onAnchors?: (rectangles: Record<string, PluginAnchorRect>) => void;
  suspended?: boolean;
  layout?: 'inline' | 'stage';
}

type FrameProps = Props &
  ({ mode?: 'live'; configAccess: PluginViewConfigAccess } | { mode: 'demo'; configAccess?: never });

const COLORS = [
  '--bg',
  '--panel',
  '--panel-2',
  '--text',
  '--muted',
  '--brand',
  '--brand-soft',
  '--border',
  '--border-soft',
  '--ok',
  '--warn',
  '--err',
  '--font-sans',
  '--font-cjk',
  '--font-display',
  '--font-mono',
  '--surface-field',
  '--text-secondary',
  '--text-on-brand',
  '--brand-hover',
  '--focus-ring',
  '--focus-outline-offset',
  '--radius-control',
  '--control-height',
];

export default function PluginViewFrame(props: FrameProps) {
  const frame = useRef<HTMLIFrameElement>(null);
  const [height, setHeight] = useState<number>();
  const current = useRef(props);
  current.current = props;
  const reducedMotion = useReducedEffects();
  const reduced = useRef(reducedMotion);
  reduced.current = reducedMotion;
  const bridge = useRef<ReturnType<typeof createPluginViewBridge>>();
  // 契约轮询会创建等内容的新对象，只有步骤内容改变才重新定位。
  const stepSignature = props.step ? JSON.stringify({ ...props.step, mode: props.mode ?? 'live' }) : '';
  const context = useCallback((): PluginViewContext => {
    const value = current.current;
    const style = getComputedStyle(document.documentElement);
    return {
      pluginId: value.pluginId,
      viewId: value.view.id,
      mode: value.mode ?? 'live',
      permissions: value.mode === 'demo' ? ['read', 'operate', 'manage'] : value.surface.permissions,
      available: value.mode === 'demo' || value.surface.available,
      suspended: !!value.suspended,
      theme: Object.fromEntries(COLORS.map((key) => [key, style.getPropertyValue(key).trim()])),
      reducedMotion: reduced.current,
      language: 'zh-CN',
      layout: value.layout ?? 'stage',
      colorScheme: style.colorScheme,
    };
  }, []);

  useEffect(() => {
    let revealFrame: number | undefined;
    const source = frame.current?.contentWindow ?? null;
    const instance = createPluginViewBridge({
      source: () => source,
      post: (message) => source?.postMessage(message, '*'),
      contract: () => current.current.surface.contract,
      context,
      demo: () => current.current.demo,
      run: (...arguments_) => current.current.run(...arguments_),
      notify: infoBar,
      navigate: (target) => current.current.onNavigate(target),
      anchors: (rectangles) => current.current.onAnchors?.(rectangles),
      resize: setHeight,
      reveal: (rectangle) => {
        if (revealFrame !== undefined) cancelAnimationFrame(revealFrame);
        // 焦点跨文档时宿主也会进行原生滚动，等本窗口布局完成后再校正正文。
        revealFrame = requestAnimationFrame(() => {
          revealFrame = undefined;
          const value = current.current;
          if (value.layout !== 'inline' || value.mode === 'demo' || value.suspended) return;
          revealPluginFocus(frame.current, rectangle);
        });
      },
      configuration: () => {
        const value = current.current;
        if (value.mode === 'demo') return { mode: 'demo', values: value.demo?.config ?? {} };
        return { mode: 'live', access: value.configAccess };
      },
      ready: () => {
        const value = current.current;
        if (value.step) instance.event('guide-step', { ...value.step, mode: value.mode ?? 'live' });
        if (value.locate) instance.event('locate', { target: value.locate });
      },
      session: crypto.randomUUID(),
    });
    bridge.current = instance;
    const receive = (event: MessageEvent) => {
      void instance.receive(event);
    };
    window.addEventListener('message', receive);
    const observer = new MutationObserver(() => instance.event('context', context()));
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme', 'class', 'style'],
    });
    return () => {
      if (revealFrame !== undefined) cancelAnimationFrame(revealFrame);
      instance.dispose();
      observer.disconnect();
      window.removeEventListener('message', receive);
    };
  }, [context, props.pluginId, props.view.id, props.view.url]);

  useEffect(() => {
    bridge.current?.event('context', context());
  }, [reducedMotion, props.surface.available, props.surface.permissions, props.suspended, context]);
  useEffect(() => {
    const value = current.current;
    if (value.step) bridge.current?.event('guide-step', { ...value.step, mode: value.mode ?? 'live' });
  }, [stepSignature]);
  useEffect(() => {
    if (props.locate) bridge.current?.event('locate', { target: props.locate });
  }, [props.locate, props.locateRequest]);

  return (
    <iframe
      key={`${props.pluginId}:${props.view.id}:${props.view.url}`}
      ref={frame}
      className="plugin-view-frame"
      style={props.layout === 'inline' ? { height: height ?? 420 } : undefined}
      title={props.view.title}
      src={props.view.url}
      sandbox="allow-scripts allow-forms"
      referrerPolicy="no-referrer"
    />
  );
}
