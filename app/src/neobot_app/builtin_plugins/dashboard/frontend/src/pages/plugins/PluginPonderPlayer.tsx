import { useCallback, useEffect, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight, List, Pause, Play, RotateCcw } from 'lucide-react';
import type { PluginGuide, PluginView } from '../../api/types';
import Button from '../../components/ui/Button';
import SelectControl from '../../components/ui/SelectControl';
import { useReducedEffects } from '../../hooks/useReducedEffects';
import { infoBar } from '../../notifications/infoBar';
import PluginPonderStage from './PluginPonderStage';
import PluginPonderScreen from './PluginPonderScreen';
import PluginPonderTimeline from './PluginPonderTimeline';
import PluginPonderContents from './PluginPonderContents';
import { usePonderPlayback } from './usePonderPlayback';
import type { PluginViewSurface } from './pluginViewBridge';

interface Props {
  pluginId: string;
  surface: PluginViewSurface;
  guide: PluginGuide;
  views: Array<PluginView & { url: string }>;
  guides: PluginGuide[];
  onGuideChange: (id: string) => void;
  onClose: () => void;
}

function PonderLesson({ pluginId, surface, guide, views }: Props) {
  const reducedMotion = useReducedEffects();
  const playback = usePonderPlayback(guide, reducedMotion);
  const {
    index,
    playing,
    chapters,
    chapterIndex,
    seek: seekStep,
    next: nextStep,
    toggle: togglePlayback,
  } = playback;
  const [reading, setReading] = useState(false);
  const contentsButton = useRef<HTMLButtonElement | null>(null);
  const showStage = useCallback(() => {
    if (reading) contentsButton.current?.focus();
    setReading(false);
  }, [reading]);
  const seek = useCallback(
    (position: number) => {
      showStage();
      seekStep(position);
    },
    [showStage, seekStep],
  );
  const next = useCallback(() => {
    showStage();
    nextStep();
  }, [showStage, nextStep]);
  const toggle = useCallback(() => {
    showStage();
    togglePlayback();
  }, [showStage, togglePlayback]);
  const restart = () => {
    showStage();
    playback.restart();
  };
  const step = guide.steps[index];
  useEffect(() => {
    infoBar({
      title: '演示使用样例数据',
      message: reducedMotion
        ? '不会发送消息或保存记录。已减少动态效果，请手动切换步骤。'
        : '不会发送消息或保存真实记录。默认手动阅读，也可点击播放连续观看。',
      tone: 'info',
    });
  }, [reducedMotion]);

  useEffect(() => {
    const handleKeys = (event: KeyboardEvent) => {
      // 选择器、输入框和原生按钮先处理自己的键，浏览器组合快捷键保持可用。
      const target = event.target as HTMLElement;
      if (
        !target.closest('.ponder-screen') ||
        event.altKey ||
        event.ctrlKey ||
        event.metaKey ||
        target.closest(
          'input, textarea, select, [contenteditable="true"], [role="combobox"], [role="listbox"]',
        )
      )
        return;
      if (event.key === ' ' && target.closest('button')) return;
      switch (event.key) {
        case 'ArrowLeft':
          seek(index - 1);
          break;
        case 'ArrowRight':
          next();
          break;
        case '[':
          seek(chapters[Math.max(0, chapterIndex - 1)]?.index ?? 0);
          break;
        case ']':
          seek(chapters[Math.min(chapters.length - 1, chapterIndex + 1)]?.index ?? 0);
          break;
        case ' ':
          toggle();
          break;
        default:
          return;
      }
      event.preventDefault();
      event.stopPropagation();
    };
    window.addEventListener('keydown', handleKeys, true);
    return () => window.removeEventListener('keydown', handleKeys, true);
  }, [index, chapterIndex, chapters, seek, next, toggle]);

  if (!step)
    return (
      <div className="ponder-empty">
        <p>本篇说明暂无内容。</p>
      </div>
    );
  return (
    <div className="ponder-lesson">
      <div className="ponder-main" data-reading={reading || undefined}>
        {reading ? (
          <PluginPonderContents guide={guide} index={index} onSelect={seek} />
        ) : (
          <PluginPonderStage
            pluginId={pluginId}
            surface={surface}
            guide={guide}
            step={step}
            views={views}
            reducedMotion={reducedMotion}
          />
        )}
        <div className="ponder-playback">
          <Button
            size="sm"
            variant="ghost"
            aria-label="上一步演示"
            disabled={index === 0}
            onClick={() => seek(index - 1)}
          >
            <ChevronLeft size={18} />
          </Button>
          <Button
            size="sm"
            variant="primary"
            className="ponder-play-toggle"
            aria-label={playing ? '暂停演示' : '播放演示'}
            data-autofocus
            onClick={toggle}
          >
            {playing ? <Pause size={18} /> : <Play size={18} />}
          </Button>
          <Button size="sm" variant="ghost" aria-label="下一步演示" onClick={next}>
            <ChevronRight size={18} />
          </Button>
          <PluginPonderTimeline {...playback} count={guide.steps.length} onSeek={seek} />
          <Button size="sm" variant="ghost" aria-label="重新播放" onClick={restart}>
            <RotateCcw size={16} />
          </Button>
          <Button
            size="sm"
            variant="ghost"
            aria-pressed={reading}
            onClick={(event) => {
              contentsButton.current = event.currentTarget;
              playback.pause();
              setReading(!reading);
            }}
          >
            <List size={16} /> 目录与全文
          </Button>
        </div>
        {!reading && (
          <div className="ponder-caption" aria-live="polite">
            <div className="ponder-caption-heading">
              <span>
                {String(chapterIndex + 1).padStart(2, '0')} / {String(chapters.length).padStart(2, '0')}
              </span>
              <strong>{step.chapter || guide.title}</strong>
              <span className="ponder-position">
                步骤 {index + 1} / {guide.steps.length}
              </span>
            </div>
            <p>{step.text}</p>
          </div>
        )}
      </div>
      <footer className="ponder-legend" aria-label="思索快捷键">
        <span>
          <kbd>←</kbd>
          <kbd>→</kbd> 回看步骤
        </span>
        <span>
          <kbd>[</kbd>
          <kbd>]</kbd> 切换章节
        </span>
        <span>
          <kbd>Space</kbd> 播放 / 暂停
        </span>
      </footer>
    </div>
  );
}

export default function PluginPonderPlayer(props: Props) {
  return (
    <PluginPonderScreen
      pluginId={props.pluginId}
      onClose={props.onClose}
      title={
        props.guides.length > 1 ? (
          <SelectControl
            label="选择说明"
            value={props.guide.id}
            onValueChange={props.onGuideChange}
            options={props.guides.map((guide) => ({ value: guide.id, label: guide.title }))}
          />
        ) : (
          <strong>{props.guide.title}</strong>
        )
      }
    >
      <PonderLesson key={props.guide.id} {...props} />
    </PluginPonderScreen>
  );
}
