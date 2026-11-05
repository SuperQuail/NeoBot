import { useCallback, useEffect, useRef, useState } from 'react';
import type { PluginGuide } from '../../api/types';
import { infoBar } from '../../notifications/infoBar';

/** 字幕停留时间与进度条共用时钟；暂停、后台隐藏都保留剩余时长。 */
export function usePonderPlayback(guide: PluginGuide, reducedMotion: boolean) {
  const [stepIndex, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [ended, setEnded] = useState(false);
  const [replay, setReplay] = useState(0);
  const [visible, setVisible] = useState(!document.hidden);
  const elapsed = useRef(0);
  const index = Math.min(stepIndex, Math.max(0, guide.steps.length - 1));
  const step = guide.steps[index];
  const text = step?.text;
  const readingLength = [text, step?.command?.text, step?.command?.context, step?.command?.reply].reduce(
    (length, value) => length + (value?.length ?? 0),
    0,
  );
  const duration = Math.max(3500, Math.min(30000, readingLength * 80));
  const active = playing && visible && text !== undefined;
  const chapters = guide.steps.reduce<Array<{ title: string; index: number }>>((items, step, position) => {
    const title = step.chapter || guide.title;
    if (items.at(-1)?.title !== title) items.push({ title, index: position });
    return items;
  }, []);
  const chapterIndex = chapters.reduce(
    (current, chapter, position) => (index >= chapter.index ? position : current),
    0,
  );
  const finish = useCallback(() => {
    setPlaying(false);
    setEnded(true);
    infoBar({ title: '本篇说明已播放完', message: '可以选择章节回看。', tone: 'info' });
  }, []);
  const seek = (position: number) => {
    setIndex(Math.max(0, Math.min(position, guide.steps.length - 1)));
    setEnded(false);
    setPlaying(false);
    setReplay((value) => value + 1);
  };
  const next = () => (index < guide.steps.length - 1 ? seek(index + 1) : finish());
  const restart = () => {
    seek(chapters[chapterIndex]?.index ?? 0);
    setPlaying(!reducedMotion);
  };
  const toggle = () => {
    if (ended) {
      seek(0);
      setPlaying(true);
      return;
    }
    setPlaying((value) => !value);
  };
  const pause = () => setPlaying(false);
  useEffect(() => {
    elapsed.current = 0;
  }, [index, replay, text]);
  useEffect(() => {
    if (reducedMotion) setPlaying(false);
  }, [reducedMotion]);
  useEffect(() => {
    const update = () => setVisible(!document.hidden);
    document.addEventListener('visibilitychange', update);
    return () => document.removeEventListener('visibilitychange', update);
  }, []);
  useEffect(() => {
    if (!active) return;
    const started = performance.now();
    const timer = window.setTimeout(
      () => {
        if (index < guide.steps.length - 1) setIndex(index + 1);
        else finish();
      },
      Math.max(0, duration - elapsed.current),
    );
    return () => {
      window.clearTimeout(timer);
      elapsed.current += performance.now() - started;
    };
  }, [active, duration, index, replay, guide.steps.length, finish, text]);
  return {
    index,
    playing,
    active,
    ended,
    replay,
    duration,
    chapters,
    chapterIndex,
    seek,
    next,
    restart,
    toggle,
    pause,
  };
}
