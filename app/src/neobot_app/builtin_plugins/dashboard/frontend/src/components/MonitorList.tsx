import { useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import EmptyState from './ui/EmptyState';
import { PanelSkeleton } from './ui/PageSkeleton';

/** 按实际可用高度分页；总览不依赖滚动，也不丢掉屏幕外的记录。 */
export default function MonitorList<T>({
  items,
  label,
  empty,
  renderItem,
  rowHeight = 42,
  loading = false,
}: {
  items: T[];
  label: string;
  empty: string;
  renderItem: (item: T, index: number) => ReactNode;
  rowHeight?: number;
  loading?: boolean;
}) {
  const listRef = useRef<HTMLUListElement>(null);
  const [pageSize, setPageSize] = useState(3);
  const [requestedPage, setPage] = useState(0);
  const pages = Math.max(1, Math.ceil(items.length / pageSize));
  const page = Math.min(requestedPage, pages - 1);
  const start = page * pageSize;

  useLayoutEffect(() => {
    const list = listRef.current;
    if (!list) return;
    const update = () => {
      const height = list.getBoundingClientRect().height;
      if (height > 0) setPageSize(Math.max(1, Math.min(8, Math.floor(height / rowHeight))));
    };
    update();
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(update);
    observer.observe(list);
    return () => observer.disconnect();
  }, [rowHeight]);

  return (
    <div className="monitor-list">
      <ul ref={listRef} className="monitor-list-items" aria-label={label}>
        {items.slice(start, start + pageSize).map((item, index) => (
          <li className="monitor-list-row" key={start + index}>
            {renderItem(item, start + index)}
          </li>
        ))}
      </ul>
      {items.length === 0 &&
        (loading ? (
          <PanelSkeleton kind="list" rows={3} label={`正在读取${label}`} />
        ) : (
          <EmptyState compact>{empty}</EmptyState>
        ))}
      {items.length > 0 && (
        <div className="monitor-list-pager">
          <span>
            {start + 1}–{Math.min(start + pageSize, items.length)} / {items.length}
          </span>
          <div>
            <button
              className="icon-btn"
              disabled={page === 0}
              aria-label={`${label}上一页`}
              onClick={() => setPage(page - 1)}
            >
              <ChevronLeft size={14} />
            </button>
            <button
              className="icon-btn"
              disabled={page === pages - 1}
              aria-label={`${label}下一页`}
              onClick={() => setPage(page + 1)}
            >
              <ChevronRight size={14} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
