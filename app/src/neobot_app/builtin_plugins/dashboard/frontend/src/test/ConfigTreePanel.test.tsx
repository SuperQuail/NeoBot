// 单元测试：ConfigTreePanel —— 左树分区导航 + 右侧只渲染选中分区的搜索/高亮
//
// 这一层的核心风险是「两套判定各说各话」：左树按 fieldMatches / countLeafHits 算命中，
// 右侧却按另一套规则渲染，于是标题说「命中 N 项」、实际渲染出的字段却对不上。
// 所以纯函数与组件行为都要锁住。
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import {
  ConfigTreePanel,
  fieldMatches,
  gatherField,
  groupHasHits,
  type ConfigTreePanelProps,
} from '../pages/config/ConfigTreePanel';
import type { FieldDescriptor } from '../api/types';

function scalar(name: string, path: string[], overrides: Partial<FieldDescriptor> = {}): FieldDescriptor {
  return { name, path, kind: 'scalar', type: 'str', value: '', ...overrides };
}

function group(name: string, fields: FieldDescriptor[], overrides: Partial<FieldDescriptor> = {}): FieldDescriptor {
  return { name, path: [name], kind: 'group', value: {}, fields, ...overrides };
}

describe('fieldMatches：路径或说明命中即算命中', () => {
  const engines = scalar('engines', ['web_search', 'engines'], { description: '搜索引擎回退顺序' });

  it('关键词命中路径片段时为 true（大小写不敏感）', () => {
    expect(fieldMatches(engines, 'web_search')).toBe(true);
    expect(fieldMatches(engines, 'ENGINES')).toBe(true);
  });

  it('关键词只命中 description 时也为 true', () => {
    expect(fieldMatches(engines, '搜索引擎')).toBe(true);
  });

  it('路径与说明都不命中时为 false', () => {
    expect(fieldMatches(engines, '不存在的关键词')).toBe(false);
  });

  it('空关键词一律算命中', () => {
    expect(fieldMatches(engines, '')).toBe(true);
  });
});

describe('gatherField：搜索态收拢字段', () => {
  const engines = scalar('engines', ['web_search', 'engines'], { description: '搜索引擎回退顺序' });
  const maxResults = scalar('max_results', ['web_search', 'max_results'], { description: '单次返回结果条数' });

  it('空关键词原样返回同一个对象（不做无谓克隆）', () => {
    expect(gatherField(engines, '')).toBe(engines);
  });

  it('路径命中的叶子字段保留，不命中的返回 null', () => {
    expect(gatherField(engines, 'engines')).toBe(engines);
    expect(gatherField(maxResults, 'engines')).toBeNull();
  });

  it('说明命中的叶子字段保留', () => {
    expect(gatherField(engines, '搜索引擎')).toBe(engines);
  });

  // 防回归：曾经「说明命中」会把同组的无关字段一起留在渲染里，
  // 左树标题说「命中 1 项」，右侧却渲染出整组字段。
  it('分组部分命中时，分组保留但 fields 只剩命中的子字段', () => {
    const search = group('web_search', [engines, maxResults]);

    const gathered = gatherField(search, '搜索引擎');

    expect(gathered).not.toBeNull();
    expect(gathered!.kind).toBe('group');
    expect(gathered!.fields!.map((field) => field.name)).toEqual(['engines']);
  });

  it('分组内没有任何命中时整组返回 null', () => {
    const search = group('web_search', [engines, maxResults]);
    expect(gatherField(search, '不存在的关键词')).toBeNull();
  });
});

describe('groupHasHits：分组里有没有命中项', () => {
  const engines = scalar('engines', ['web_search', 'engines'], { description: '搜索引擎回退顺序' });
  const maxResults = scalar('max_results', ['web_search', 'max_results']);

  it('组内某个叶子命中即为 true', () => {
    expect(groupHasHits(group('web_search', [engines, maxResults]), '搜索引擎')).toBe(true);
    expect(groupHasHits(group('web_search', [engines, maxResults]), 'engines')).toBe(true);
  });

  it('嵌套子组里的叶子命中也算（递归统计）', () => {
    const nested = group('nested', [scalar('deep', ['web_search', 'nested', 'deep'])]);
    expect(groupHasHits(group('web_search', [nested]), 'deep')).toBe(true);
  });

  it('组内没有任何命中为 false，空关键词为 true', () => {
    expect(groupHasHits(group('web_search', [engines, maxResults]), '不存在的关键词')).toBe(false);
    expect(groupHasHits(group('web_search', [engines]), '')).toBe(true);
  });
});

const CHAT_VALUE = '聊天提示词';
const SEARCH_VALUE = 'bing';

function baseProps(filter: string, onFilterChange = vi.fn()): ConfigTreePanelProps {
  const chat = group(
    'chat',
    [scalar('group_prompt_template', ['chat', 'group_prompt_template'], { value: CHAT_VALUE })],
    { value: { group_prompt_template: CHAT_VALUE } },
  );
  const search = group(
    'web_search',
    [scalar('engines', ['web_search', 'engines'], { value: SEARCH_VALUE, description: '搜索引擎回退顺序' })],
    { value: { engines: SEARCH_VALUE } },
  );
  return {
    schema: [chat, search],
    draft: { chat: { group_prompt_template: CHAT_VALUE }, web_search: { engines: SEARCH_VALUE } },
    history: {},
    collapse: {},
    filter,
    onFilterChange,
    onChange: vi.fn(),
    onToggleCollapse: vi.fn(),
  };
}

function renderPanel(filter = '') {
  const props = baseProps(filter);
  const view = render(<ConfigTreePanel {...props} />);
  return { ...view, props };
}

describe('ConfigTreePanel 组件：树导航与搜索', () => {
  it('默认选中第一个分组，右侧只渲染该分组的字段', () => {
    renderPanel();

    const nav = screen.getByRole('navigation', { name: '配置分区' });
    const buttons = within(nav).getAllByRole('button');
    expect(buttons).toHaveLength(2);
    expect(buttons[0]).toHaveAttribute('aria-current', 'true');
    expect(buttons[1]).toHaveAttribute('aria-current', 'false');

    expect(screen.getByDisplayValue(CHAT_VALUE)).toBeInTheDocument();
    expect(screen.queryByDisplayValue(SEARCH_VALUE)).not.toBeInTheDocument();
  });

  it('点击左侧第二个分组后，右侧换成该分组的字段', () => {
    renderPanel();

    const nav = screen.getByRole('navigation', { name: '配置分区' });
    fireEvent.click(within(nav).getByRole('button', { name: /web_search/ }));

    expect(screen.getByDisplayValue(SEARCH_VALUE)).toBeInTheDocument();
    expect(screen.queryByDisplayValue(CHAT_VALUE)).not.toBeInTheDocument();
    expect(within(nav).getByRole('button', { name: /web_search/ })).toHaveAttribute('aria-current', 'true');
  });

  it('搜索态左侧只列有命中的分组', () => {
    renderPanel('搜索引擎');

    const nav = screen.getByRole('navigation', { name: '配置分区' });
    expect(within(nav).getByRole('button', { name: /web_search/ })).toBeInTheDocument();
    expect(within(nav).queryByRole('button', { name: /chat/ })).not.toBeInTheDocument();
  });

  it('命中片段渲染成 <mark> 高亮（分组名也要标出来）', () => {
    const { container } = renderPanel('web');

    const marks = Array.from(container.querySelectorAll('mark'));
    expect(marks.length).toBeGreaterThan(0);
    expect(marks.map((mark) => mark.textContent)).toContain('web');

    // 左树分组名的高亮由本组件负责，不依赖字段组件是否透传 filter
    const nav = screen.getByRole('navigation', { name: '配置分区' });
    const navMarks = Array.from(nav.querySelectorAll('mark'));
    expect(navMarks.map((mark) => mark.textContent)).toEqual(['web']);
  });
});
