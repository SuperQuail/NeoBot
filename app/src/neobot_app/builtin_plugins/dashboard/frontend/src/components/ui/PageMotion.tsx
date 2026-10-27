import { useLayoutEffect, type ReactNode } from 'react';
import { LazyMotion, MotionConfig, domAnimation, useAnimate } from 'motion/react';
import { cn } from '../../utils/cn';
import { useReducedEffects } from '../../hooks/useReducedEffects';

const ENTER_TARGETS = [
  '.page-header',
  '.card',
  '.workspace',
  '.monitor-stats',
  '.monitor-grid > *',
  '.system-metrics',
  '.system-panels > *',
  '.analytics-summary',
  '.analytics-charts > *',
  '.scheduled-task-card',
  '.inline-alert',
  '.cfg-root',
  '[role="tabpanel"]',
  '[data-motion-enter]',
].join(',');

export function MotionProvider({ children }: { children: ReactNode }) {
  const reduced = useReducedEffects();
  return (
    <LazyMotion features={domAnimation}>
      <MotionConfig
        reducedMotion={reduced ? 'always' : 'never'}
        transition={{ duration: 0.2, ease: [0.22, 0.75, 0.25, 1] }}
      >
        {children}
      </MotionConfig>
    </LazyMotion>
  );
}

/** 页面与新挂载的内容统一入场，不保留旧页面，也不重新挂载现有编辑器。 */
export default function PageMotion({ children, className }: { children: ReactNode; className?: string }) {
  const [scope, animate] = useAnimate<HTMLDivElement>();
  const reduced = useReducedEffects();

  useLayoutEffect(() => {
    const root = scope.current;
    if (!root || reduced || window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return;

    const seen = new WeakSet<Element>();
    const running = new Set<ReturnType<typeof animate>>();
    const originals = new Map<HTMLElement, { opacity: string; transform: string }>();
    let disposed = false;
    let queued = false;

    const enter = (element: HTMLElement, delay = 0, distance = 5) => {
      originals.set(element, { opacity: element.style.opacity, transform: element.style.transform });
      const controls = animate(
        element,
        { opacity: [0.5, 1], y: [distance, 0] },
        {
          duration: 0.22,
          delay,
          ease: [0.22, 0.75, 0.25, 1],
        },
      );
      running.add(controls);
      void controls.then(() => {
        running.delete(controls);
        const original = originals.get(element);
        if (!disposed && original) {
          element.style.opacity = original.opacity;
          element.style.transform = original.transform;
          originals.delete(element);
        }
      });
    };

    const reveal = () => {
      queued = false;
      if (disposed) return;
      const candidates = [...root.querySelectorAll<HTMLElement>(ENTER_TARGETS)].filter((element) => {
        if (seen.has(element) || element.closest('[hidden], [data-motion="off"]')) return false;
        const style = getComputedStyle(element);
        return style.display !== 'none' && style.visibility !== 'hidden';
      });
      const batch = new Set(candidates);
      let index = 0;
      for (const element of candidates) {
        seen.add(element);
        let parent = element.parentElement;
        while (parent && parent !== root && !batch.has(parent)) parent = parent.parentElement;
        if (parent && batch.has(parent)) continue;
        enter(element, Math.min(index++, 5) * 0.025);
      }
    };

    // 组件挂载后才启动；懒加载页面、切换面板和首次加载的数据也沿用相同节奏。
    enter(root, 0, 3);
    reveal();
    const observer = new MutationObserver((records) => {
      if (queued) return;
      // 数值轮询与代码编辑的文本变动不触发全树扫描。
      const hasEntrance = records.some((record) =>
        [...record.addedNodes].some(
          (node) =>
            node instanceof HTMLElement && (node.matches(ENTER_TARGETS) || node.querySelector(ENTER_TARGETS)),
        ),
      );
      if (!hasEntrance) return;
      queued = true;
      queueMicrotask(reveal);
    });
    observer.observe(root, { childList: true, subtree: true });
    return () => {
      disposed = true;
      observer.disconnect();
      for (const controls of running) controls.stop();
      for (const [element, original] of originals) {
        element.style.opacity = original.opacity;
        element.style.transform = original.transform;
      }
    };
  }, [animate, reduced, scope]);

  return (
    <div ref={scope} className={cn('route-stage', className)}>
      {children}
    </div>
  );
}
