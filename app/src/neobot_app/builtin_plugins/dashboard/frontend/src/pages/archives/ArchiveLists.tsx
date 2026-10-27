import type { ArchiveItemSummary, ArchiveTable } from '../../api/types';
import Icon from '../../components/Icon';
import Button from '../../components/ui/Button';
import EmptyState from '../../components/ui/EmptyState';
import { PanelSkeleton } from '../../components/ui/PageSkeleton';
import { formatListTime, formatTime, PAGE_SIZE } from './archiveUtils';

interface ArchiveTableListProps {
  tables: ArchiveTable[];
  table: string;
  loading: boolean;
  hasData: boolean;
  onSelect: (table: string) => void;
}

export function ArchiveTableList({ tables, table, loading, hasData, onSelect }: ArchiveTableListProps) {
  return (
    <section className="card archives-tables" aria-label="档案表清单">
      <div className="card-head">
        <h3>档案表</h3>
        <span className="muted small">{tables.length} 张</span>
      </div>
      {tables.length === 0 && !loading && <EmptyState compact>库里还没有任何档案表</EmptyState>}
      <ul className="archives-table-list viewer-list-scroll">
        {loading && !hasData && (
          <li>
            <PanelSkeleton label="正在读取档案表…" kind="list" rows={5} />
          </li>
        )}
        {tables.map((entry) => {
          const active = entry.table_name === table;
          return (
            <li key={entry.table_name}>
              <button
                type="button"
                className={'record-list-item archives-table-key' + (active ? ' active' : '')}
                aria-current={active}
                aria-label={`${entry.table_name}，${entry.count ?? 0} 条${entry.internal ? '，内部表' : ''}${Number(entry.over_limit_count || 0) > 0 ? `，${entry.over_limit_count} 条超限` : ''}`}
                aria-describedby={
                  entry.note ? `archive-table-note-${encodeURIComponent(entry.table_name)}` : undefined
                }
                onClick={() => onSelect(entry.table_name)}
              >
                <span className="record-list-icon" aria-hidden="true">
                  <Icon name="archive" size={17} />
                </span>
                <span className="record-list-copy">
                  <span className="record-list-title archives-table-name">
                    <code title={entry.table_name}>{entry.table_name}</code>
                    <span className="archive-table-count">{entry.count ?? 0}</span>
                  </span>
                  <span className="record-list-subtitle">
                    最长 {Number(entry.max_value_chars ?? 0).toLocaleString()} 字
                  </span>
                  {(entry.internal || Number(entry.over_limit_count || 0) > 0) && (
                    <span className="record-list-flags">
                      {entry.internal && <span className="tag warn">内部表</span>}
                      {Number(entry.over_limit_count || 0) > 0 && (
                        <span className="tag err">{entry.over_limit_count} 条超限</span>
                      )}
                    </span>
                  )}
                  {entry.note && (
                    <span
                      id={`archive-table-note-${encodeURIComponent(entry.table_name)}`}
                      className="sr-only"
                    >
                      {entry.note}
                    </span>
                  )}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

interface ArchiveEntryListProps {
  items: ArchiveItemSummary[];
  selectedKey: string;
  loading: boolean;
  offset: number;
  hasMore: boolean;
  onSelect: (key: string) => void;
  onPageChange: (offset: number) => void;
}

export function ArchiveEntryList({
  items,
  selectedKey,
  loading,
  offset,
  hasMore,
  onSelect,
  onPageChange,
}: ArchiveEntryListProps) {
  return (
    <>
      <ul className="archive-entry-list viewer-list-scroll">
        {items.map((row) => {
          const active = row.key === selectedKey;
          return (
            <li key={row.key}>
              <button
                type="button"
                className={'record-list-item archive-entry' + (active ? ' active' : '')}
                aria-label={row.key}
                title={row.key}
                aria-current={active}
                onClick={() => void onSelect(row.key)}
              >
                <span className="record-list-copy">
                  <span className="archive-entry-heading">
                    <code>{row.key}</code>
                    {row.internal && <span className="tag warn">内部表</span>}
                  </span>
                  <span className="archives-preview">{row.preview || '（空）'}</span>
                  <span className="archive-entry-meta muted small">
                    <span className="archive-entry-length">
                      {Number(row.total_chars ?? 0).toLocaleString()} 字
                      {row.preview_truncated && <span>预览已截断</span>}
                    </span>
                    <time dateTime={row.updated_at || undefined} title={formatTime(row.updated_at)}>
                      {formatListTime(row.updated_at)}
                    </time>
                  </span>
                </span>
                <span className="archive-entry-chevron" aria-hidden="true">
                  <Icon name="chevron" size={15} />
                </span>
              </button>
            </li>
          );
        })}
        {items.length === 0 && (
          <li>
            {loading ? (
              <PanelSkeleton label="正在读取档案条目…" kind="list" rows={5} />
            ) : (
              <EmptyState compact>没有匹配的档案条目</EmptyState>
            )}
          </li>
        )}
      </ul>

      <div className="archives-pager">
        <span className="muted small" title={`每页 ${PAGE_SIZE} 条`}>
          {items.length === 0 ? 0 : offset + 1}–{offset + items.length} 条
        </span>
        <Button
          size="sm"
          type="button"
          aria-label="上一页"
          title="上一页"
          disabled={offset <= 0 || loading}
          onClick={() => onPageChange(Math.max(0, offset - PAGE_SIZE))}
        >
          <Icon name="chevron" size={16} className="archive-page-previous" />
        </Button>
        <Button
          size="sm"
          type="button"
          aria-label="下一页"
          title="下一页"
          disabled={!hasMore || loading}
          onClick={() => onPageChange(offset + PAGE_SIZE)}
        >
          <Icon name="chevron" size={16} />
        </Button>
      </div>
    </>
  );
}
