import type { CSSProperties } from 'react';

interface Props {
  chapters: Array<{ title: string; index: number }>;
  chapterIndex: number;
  index: number;
  count: number;
  duration: number;
  active: boolean;
  ended: boolean;
  replay: number;
  onSeek: (index: number) => void;
}

/** 一条时间线同时表达章节与当前章的步骤，所有落点都有键盘可达的按钮。 */
export default function PluginPonderTimeline(props: Props) {
  const { chapters, chapterIndex, index, count, duration, active, ended, replay, onSeek } = props;
  return (
    <nav className="ponder-timeline" aria-label="思索章节">
      {chapters.map((chapter, position) => {
        const current = position === chapterIndex;
        const end = chapters[position + 1]?.index ?? count;
        const length = end - chapter.index;
        const start = (index - chapter.index) / length;
        return (
          <div
            className="ponder-segment"
            key={`${chapter.title}-${chapter.index}`}
            data-current={current || undefined}
            data-past={position < chapterIndex || undefined}
          >
            <button
              className="ponder-chapter-hit"
              type="button"
              aria-label={`${String(position + 1).padStart(2, '0')} ${chapter.title}`}
              aria-current={current ? 'step' : undefined}
              onClick={() => onSeek(chapter.index)}
            >
              <span className="ponder-chapter-tip">{chapter.title}</span>
            </button>
            <span className="ponder-track" aria-hidden="true">
              <span
                key={`${index}:${replay}`}
                className="ponder-progress"
                style={
                  {
                    '--ponder-from': ended ? 1 : start,
                    '--ponder-to': (index - chapter.index + 1) / length,
                    animationDuration: `${duration}ms`,
                    animationPlayState: active ? 'running' : 'paused',
                  } as CSSProperties
                }
              />
            </span>
            {current &&
              length > 1 &&
              Array.from({ length }, (_, offset) => (
                <button
                  type="button"
                  key={offset}
                  className="ponder-step-tick"
                  aria-label={`回看第 ${chapter.index + offset + 1} 步`}
                  aria-pressed={index === chapter.index + offset}
                  style={{ left: `${((offset + 0.5) / length) * 100}%` }}
                  onClick={() => onSeek(chapter.index + offset)}
                />
              ))}
          </div>
        );
      })}
      <input
        className="ponder-accessible-seek"
        type="range"
        aria-label="演示进度"
        min={0}
        max={count - 1}
        value={index}
        onChange={(event) => onSeek(Number(event.target.value))}
      />
    </nav>
  );
}
