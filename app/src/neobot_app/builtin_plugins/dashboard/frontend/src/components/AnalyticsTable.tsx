import { useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import EmptyState from './ui/EmptyState';

/** 按可用高度分页，避免统计表把工作区撑成一条长页面。 */
export default function AnalyticsTable<T>({
  items,
  label,
  columns,
  renderRow,
  empty = '当前时间范围内没有记录',
  className = '',
}: {
  items: T[];
  label: string;
  columns: string[];
  renderRow: (item: T, index: number) => ReactNode;
  empty?: string;
  className?: string;
}) {
  const regionRef = useRef<HTMLDivElement>(null);
  const [pageSize, setPageSize] = useState(3);
  const [requestedPage, setPage] = useState(0);
  const pages = Math.max(1, Math.ceil(items.length / pageSize));
  const page = Math.min(requestedPage, pages - 1);
  const start = page * pageSize;

  useLayoutEffect(() => {
    const region = regionRef.current;
    if (!region) return;
    const measure = () => {
      const height = region.getBoundingClientRect().height;
      if (height > 0) setPageSize(Math.max(1, Math.min(12, Math.floor((height - 36) / 42))));
    };
    measure();
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(measure);
    observer.observe(region);
    return () => observer.disconnect();
  }, []);

  return (
    <div className="analytics-table">
      {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- 横向溢出表格需要键盘滚动入口。 */}
      <div ref={regionRef} className="analytics-table-region" role="region" aria-label={label} tabIndex={0}>
        {items.length ? (
          <table className={className}>
            <thead>
              <tr>
                {columns.map((column) => (
                  <th key={column}>{column}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {items.slice(start, start + pageSize).map((item, index) => renderRow(item, start + index))}
            </tbody>
          </table>
        ) : (
          <EmptyState compact>{empty}</EmptyState>
        )}
      </div>
      <div className="analytics-pagination">
        <span>
          {items.length
            ? `${start + 1}–${Math.min(start + pageSize, items.length)} / ${items.length} 条`
            : '0 条记录'}
        </span>
        <div>
          <span>
            {page + 1} / {pages}
          </span>
          <button
            type="button"
            className="icon-btn"
            aria-label={`${label}上一页`}
            disabled={page === 0}
            onClick={() => setPage(page - 1)}
          >
            <ChevronLeft size={15} />
          </button>
          <button
            type="button"
            className="icon-btn"
            aria-label={`${label}下一页`}
            disabled={page === pages - 1}
            onClick={() => setPage(page + 1)}
          >
            <ChevronRight size={15} />
          </button>
        </div>
      </div>
    </div>
  );
}
