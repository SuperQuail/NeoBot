import { cn } from '../../utils/cn';

export type SkeletonKind = 'overview' | 'workspace' | 'table';

function Shape({ className }: { className?: string }) {
  return <span className={cn('skeleton-shape', className)} />;
}

export function PanelSkeleton({
  rows = 5,
  label = '正在读取内容',
  className,
  kind = 'fields',
}: {
  rows?: number;
  label?: string;
  className?: string;
  kind?: 'fields' | 'list' | 'text';
}) {
  return (
    <div
      className={cn('panel-skeleton', `skeleton-${kind}`, className)}
      role="status"
      aria-busy="true"
      data-motion="off"
    >
      <span className="sr-only">{label}</span>
      <div aria-hidden="true">
        {Array.from({ length: rows }, (_, index) => (
          <div className="skeleton-row" key={index}>
            <Shape className="skeleton-label" />
            <Shape className="skeleton-value" />
            {kind === 'list' && <Shape className="skeleton-meta" />}
          </div>
        ))}
      </div>
    </div>
  );
}

export default function PageSkeleton({
  kind = 'workspace',
  label = '正在加载页面',
}: {
  kind?: SkeletonKind;
  label?: string;
}) {
  return (
    <div
      className={cn('page page-skeleton', `page-skeleton-${kind}`)}
      role="status"
      aria-busy="true"
      data-motion="off"
    >
      <span className="sr-only">{label}</span>
      <div className="page-skeleton-head" aria-hidden="true">
        <Shape className="skeleton-title" />
        <Shape className="skeleton-actions" />
      </div>
      {kind === 'overview' ? (
        <>
          <div className="skeleton-metrics" aria-hidden="true">
            {[0, 1, 2, 3].map((item) => (
              <div key={item}>
                <Shape className="skeleton-label" />
                <Shape className="skeleton-number" />
              </div>
            ))}
          </div>
          <div className="skeleton-overview" aria-hidden="true">
            {[0, 1, 2, 3].map((item) => (
              <div key={item}>
                <Shape className="skeleton-label" />
                <Shape className="skeleton-chart" />
              </div>
            ))}
          </div>
        </>
      ) : kind === 'workspace' ? (
        <div className="skeleton-workspace" aria-hidden="true">
          <aside>
            {[0, 1, 2, 3, 4, 5].map((item) => (
              <Shape key={item} className="skeleton-menu-item" />
            ))}
          </aside>
          <div>
            <Shape className="skeleton-editor-toolbar" />
            {[0, 1, 2, 3, 4].map((item) => (
              <div className="skeleton-row" key={item}>
                <Shape className="skeleton-label" />
                <Shape className="skeleton-value" />
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="skeleton-table" aria-hidden="true">
          <Shape className="skeleton-editor-toolbar" />
          {[0, 1, 2, 3, 4, 5].map((item) => (
            <div key={item} className="skeleton-row">
              <Shape className="skeleton-label" />
              <Shape className="skeleton-value" />
              <Shape className="skeleton-meta" />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
