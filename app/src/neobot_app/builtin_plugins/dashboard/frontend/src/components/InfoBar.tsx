// 固定位置的统一通知宿主；发布 API 不依赖这个展示组件。
import { useState, useEffect, useLayoutEffect, useRef, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, m, useAnimationControls, usePresence } from 'motion/react';
import { CheckCircle2, Info, TriangleAlert, CircleAlert, X } from 'lucide-react';
import { cn } from '../utils/cn';
import { useReducedEffects } from '../hooks/useReducedEffects';
import Modal from './Modal';
import {
  connectInfoBarHost,
  createInfoBarItem,
  type InfoBarItem,
  type InfoBarOptions,
} from '../notifications/infoBar';

type PauseReason = 'pointer' | 'focus' | 'details';
const STATUS_ICONS = { info: Info, ok: CheckCircle2, warn: TriangleAlert, err: CircleAlert };

function InfoBarMessage({
  item,
  onDismiss,
  onDetails,
}: {
  item: InfoBarItem;
  onDismiss: (id: number) => void;
  onDetails: (item: InfoBarItem) => void;
}) {
  const [present, safeToRemove] = usePresence();
  const reducedMotion = useReducedEffects();
  const controls = useAnimationControls();
  const enteredId = useRef<number | null>(null);

  useLayoutEffect(() => {
    let disposed = false;
    controls.stop();
    if (reducedMotion) {
      controls.set({ opacity: present ? 1 : 0, y: 0 });
      if (!present) safeToRemove?.();
    } else {
      if (present && enteredId.current !== item.id) controls.set({ opacity: 0.7, y: 8 });
      void controls
        .start(
          { opacity: present ? 1 : 0, y: present ? 0 : 4 },
          { duration: present ? 0.18 : 0.12, ease: 'easeOut' },
        )
        .then(() => {
          if (!disposed && !present) safeToRemove?.();
        });
    }
    if (present) enteredId.current = item.id;
    return () => {
      disposed = true;
      controls.stop();
    };
  }, [controls, present, reducedMotion, safeToRemove, item.id]);
  const StatusIcon = STATUS_ICONS[item.tone];
  const hasDetails =
    Boolean(item.message) ||
    (item.details != null && item.details !== false) ||
    item.title !== item.fullTitle;

  return (
    <m.div
      className={cn('info-bar', item.tone)}
      role={present ? 'group' : undefined}
      aria-label={present ? item.title : undefined}
      aria-hidden={present ? undefined : true}
      initial={{ opacity: reducedMotion ? 1 : 0.7, y: reducedMotion ? 0 : 8 }}
      animate={controls}
      style={{ pointerEvents: present ? 'auto' : 'none' }}
    >
      <StatusIcon className="info-bar-icon" size={18} aria-hidden="true" />
      <div className="info-bar-content">
        <strong className="info-bar-title" title={item.fullTitle}>
          {item.title}
        </strong>
        {item.message && <p className="info-bar-message">{item.message}</p>}
        {hasDetails && (
          <button
            className="info-bar-details"
            disabled={!present}
            tabIndex={present ? 0 : -1}
            onClick={() => onDetails(item)}
          >
            查看详情
          </button>
        )}
      </div>
      <button
        className="info-bar-close"
        aria-label="关闭通知"
        disabled={!present}
        tabIndex={present ? 0 : -1}
        onClick={() => onDismiss(item.id)}
      >
        <X size={15} aria-hidden="true" />
      </button>
    </m.div>
  );
}

export function InfoBarHost() {
  const [item, setItem] = useState<InfoBarItem | null>(null);
  const [detailsItem, setDetailsItem] = useState<InfoBarItem | null>(null);
  const current = useRef<InfoBarItem | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const remaining = useRef(0);
  const deadline = useRef(0);
  const pauses = useRef(new Set<PauseReason>());
  const statusRef = useRef<HTMLDivElement>(null);

  const clearTimer = useCallback(() => {
    if (timer.current !== null) clearTimeout(timer.current);
    timer.current = null;
  }, []);

  const dismiss = useCallback(
    (id: number) => {
      if (current.current?.id !== id) return;
      clearTimer();
      current.current = null;
      remaining.current = 0;
      pauses.current.delete('pointer');
      pauses.current.delete('focus');
      setItem(null);
    },
    [clearTimer],
  );

  const schedule = useCallback(() => {
    const active = current.current;
    if (!active || active.duration <= 0 || pauses.current.size > 0) return;
    clearTimer();
    deadline.current = Date.now() + remaining.current;
    timer.current = setTimeout(() => dismiss(active.id), remaining.current);
  }, [clearTimer, dismiss]);

  const pause = useCallback(
    (reason: PauseReason) => {
      if (pauses.current.has(reason)) return;
      pauses.current.add(reason);
      if (timer.current !== null) remaining.current = Math.max(0, deadline.current - Date.now());
      clearTimer();
    },
    [clearTimer],
  );

  const resume = useCallback(
    (reason: PauseReason) => {
      if (!pauses.current.delete(reason)) return;
      if (pauses.current.size === 0) schedule();
    },
    [schedule],
  );

  const closeDetails = useCallback(() => {
    setDetailsItem(null);
    resume('details');
  }, [resume]);

  const push = useCallback(
    (options: InfoBarOptions) => {
      const incoming = createInfoBarItem(options);
      const previous = current.current;
      if (previous?.fullTitle === incoming.fullTitle && previous.tone === incoming.tone) {
        incoming.id = previous.id;
        if (
          previous.message === incoming.message &&
          previous.details === incoming.details &&
          previous.duration === incoming.duration
        )
          return;
      }
      clearTimer();
      current.current = incoming;
      remaining.current = incoming.duration;
      setItem(incoming);
      schedule();
    },
    [clearTimer, schedule],
  );

  useEffect(() => {
    const disconnect = connectInfoBarHost({ push, closeDetails });
    return () => {
      disconnect();
      clearTimer();
    };
  }, [push, closeDetails, clearTimer]);

  useLayoutEffect(() => {
    if (!statusRef.current?.contains(document.activeElement)) resume('focus');
  }, [item?.id, resume]);

  // 通知与弹窗同属 body，避免被应用容器的堆叠上下文遮挡。
  return createPortal(
    <>
      <div
        ref={statusRef}
        className="info-bar-host"
        role="status"
        aria-live="polite"
        aria-atomic="true"
        data-details-open={detailsItem ? 'true' : undefined}
        onMouseEnter={() => pause('pointer')}
        onMouseLeave={() => resume('pointer')}
        onFocusCapture={() => pause('focus')}
        onBlurCapture={(event) => {
          if (!(event.relatedTarget instanceof Node) || !event.currentTarget.contains(event.relatedTarget))
            resume('focus');
        }}
      >
        <AnimatePresence initial={false}>
          {item && (
            <InfoBarMessage
              key="info-bar"
              item={item}
              onDismiss={dismiss}
              onDetails={(selected) => {
                pause('details');
                setDetailsItem(selected);
              }}
            />
          )}
        </AnimatePresence>
      </div>
      <Modal open={detailsItem !== null} title="通知详情" onClose={closeDetails} size="wide">
        {detailsItem && (
          <div className="info-bar-detail-content">
            <h4>{detailsItem.fullTitle}</h4>
            {detailsItem.message && <p>{detailsItem.message}</p>}
            {detailsItem.details != null && (
              <div className="info-bar-detail-extra">{detailsItem.details}</div>
            )}
          </div>
        )}
      </Modal>
    </>,
    document.body,
  );
}
