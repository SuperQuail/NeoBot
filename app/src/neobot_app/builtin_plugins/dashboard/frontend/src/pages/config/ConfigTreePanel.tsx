// ConfigTreePanel.tsx —— 方案 B：左侧分组树 + 右侧只渲染选中组
//
// 为什么不是「一长条嵌套折叠」：实测 schema 有 17 个顶层分区，`chat` 直属 77 项、
// `agent` 子树 109 项、`models` 里还套着 registry 列表（三层盒子）。
// 叠盒子在大分区上既难定位也难看清层级；改为「左树定位 + 右区渲染」后，
// 一屏只有一个分组的字段，滚动量与层级深度都降到 1。
import { useMemo, useState } from 'react';
import SchemaForm from '../../components/SchemaForm';
import Icon from '../../components/Icon';
import { Highlight } from '../../components/schema/Highlight';
import { countLeafHits, gatherField, groupHasHits } from '../../components/schema/searchHit';
import type { FieldDescriptor } from '../../api/types';
import { bindValues, type HistoryMap } from './shared';

export interface ConfigTreePanelProps {
  schema: FieldDescriptor[];
  draft: Record<string, any>;
  baseline?: Record<string, any>;
  history: HistoryMap;
  collapse: Record<string, boolean>;
  disabled?: boolean;
  filter: string;
  onFilterChange: (value: string) => void;
  onChange: (path: string[], value: unknown) => void;
  onToggleCollapse: (key: string) => void;
  onRestore?: (path: string[], value: unknown) => void;
}

/** 搜索命中判定与收拢统一在 components/schema/searchHit.ts（Field 与这里共用同一套规则）。 */
export { fieldMatches, gatherField, groupHasHits, countLeafHits } from '../../components/schema/searchHit';

/**
 * 顶层散字段的伪分区名。
 *
 * schema 里并非每个字段都在分组内（真实配置里 `version` 就是顶层标量）。
 * 左树只列 group 的话这些字段会**彻底消失**——用户既看不到也改不了，
 * 所以给它们一个伪分区收着，保证「任何字段都有入口」。
 */
export const LOOSE_SECTION = '（顶层）';

export function ConfigTreePanel(props: ConfigTreePanelProps) {
  const {
    schema, draft, baseline, history, collapse, disabled, filter,
    onFilterChange, onChange, onToggleCollapse, onRestore,
  } = props;

  const keyword = filter.trim();
  const groups = useMemo(() => {
    const real = schema.filter((field) => field.kind === 'group');
    const loose = schema.filter((field) => field.kind !== 'group');
    // 顶层散字段收进伪分区，排在最前（它们通常是最基础的开关）
    return loose.length
      ? [{ name: LOOSE_SECTION, path: [], kind: 'group', fields: loose } as FieldDescriptor, ...real]
      : real;
  }, [schema]);
  const [selected, setSelected] = useState<string>(() => groups[0]?.name || '');

  // 搜索态：左侧树只留「有命中」的分区，并各自带命中数
  const tree = useMemo(
    () =>
      groups
        .map((group) => ({
          group,
          hits: keyword ? countLeafHits(group.fields, keyword) : 0,
          keep: groupHasHits(group, keyword),
        }))
        .filter((entry) => entry.keep),
    [groups, keyword],
  );

  const active = useMemo(() => {
    const wanted = tree.find((entry) => entry.group.name === selected) || tree[0];
    return wanted?.group;
  }, [tree, selected]);

  /**
   * 右侧要渲染的字段。
   *
   * 两件事必须同时做对，否则界面会「看着对、改不动」：
   *   1. bindValues：把**草稿**值贴到描述符上。Form 只认描述符上的 value，
   *      不绑定的话永远显示 schema 快照，改了也不回来。
   *   2. 搜索态先收拢：收拢规则必须与 countLeafHits 一致，否则
   *      「命中 N 项」与实际渲染条数会对不上。
   */
  const activeFields = useMemo(() => {
    if (!active) return [];
    const gathered = keyword ? gatherField(active, keyword) : active;
    if (!gathered) return [];
    if (gathered.name === LOOSE_SECTION) {
      // 伪分区没有父级可递归绑定，直接把草稿值逐个贴到字段上
      return [
        {
          ...gathered,
          value: {},
          fields: (gathered.fields || []).map((field) => ({
            ...field,
            value: draft && field.name in draft ? draft[field.name] : field.value,
          })),
        },
      ];
    }
    return bindValues([gathered], draft);
  }, [active, keyword, draft]);

  const totalHits = useMemo(
    () => tree.reduce((sum, entry) => sum + (keyword ? entry.hits : 0), 0),
    [tree, keyword],
  );

  return (
    <div className="cfg-tree">
      <aside className="cfg-tree-side">
        <div className="cfg-tree-cap">
          {keyword ? (
            <span>命中 <b>{totalHits}</b> 项 / {tree.length} 个分区</span>
          ) : (
            <span>{groups.length} 个分区</span>
          )}
        </div>
        <nav className="cfg-tree-nav" aria-label="配置分区">
          {tree.map(({ group, hits }) => (
            <button
              type="button"
              key={group.name}
              className={'cfg-tree-item' + (group.name === active?.name ? ' on' : '') + (keyword && hits > 0 ? ' hit' : '')}
              aria-current={group.name === active?.name}
              onClick={() => setSelected(group.name)}
            >
              <span className="cfg-tree-name">
                <Highlight text={group.name} keyword={keyword || undefined} />
              </span>
              <span className="cfg-tree-count">{keyword ? hits : (group.fields || []).length}</span>
              {keyword && hits > 0 && <span className="cfg-tree-badge">命中</span>}
            </button>
          ))}
          {tree.length === 0 && <p className="cfg-tree-empty">没有匹配「{keyword}」的配置项</p>}
        </nav>
      </aside>

      <section className="cfg-tree-body">
        {active ? (
          <>
            <header className="cfg-tree-head">
              <h3><Highlight text={active.name} keyword={keyword || undefined} /></h3>
              <span className="muted small">
                {countLeafHits(active.fields, keyword)} 项{keyword ? '命中' : ''}
              </span>
            </header>
            {active.description && <p className="muted small cfg-hint">{active.description}</p>}
            <SchemaForm
              fields={activeFields}
              values={draft}
              baseline={baseline}
              disabled={disabled}
              // 字段已由 gatherField 收拢过：这里再过滤一遍不会丢东西，
              // 但需要它把 filter 透给 Field 才能做命中高亮。
              filter={filter}
              history={history}
              collapse={collapse}
              onToggleCollapse={onToggleCollapse}
              onRestore={onRestore}
              onChange={onChange}
            />
          </>
        ) : (
          <div className="workspace-empty">
            <Icon name="settings" />
            <h3>没有匹配的配置项</h3>
            <p>换个关键词，或清空搜索框看全部分区。</p>
            {keyword && <button type="button" className="btn-sm" onClick={() => onFilterChange('')}>清空搜索</button>}
          </div>
        )}
      </section>
    </div>
  );
}

export default ConfigTreePanel;
