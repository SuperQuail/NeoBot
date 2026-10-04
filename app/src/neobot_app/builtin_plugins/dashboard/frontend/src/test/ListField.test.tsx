// 单元测试：ListField —— 数组编辑器按内容在「chip 墙 / 拖拽列表 / JSON 兜底」之间选形态
//
// 形态判定既决定用户看到什么，也决定「编辑后类型会不会被悄悄改掉」：
//   - 路径/URL、长元素 -> 拖拽列表（顺序有语义、chip 墙挤成一团）
//   - 短值            -> chip 墙
//   - 含对象/数组     -> 只能走 JSON（不能渲染成 [object Object] 假装能编辑）
// 这里既锁纯函数的判定规则，也锁组件确实把规则用在了渲染上。
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import ListField, {
  hasComplexItems,
  listValues,
  preferDragList,
  typeWillChange,
} from '../components/schema/ListField';
import type { FieldDescriptor } from '../api/types';

function listDescriptor(value: unknown, overrides: Partial<FieldDescriptor> = {}): FieldDescriptor {
  return {
    name: 'allowed_read_dirs',
    path: ['web_search', 'allowed_read_dirs'],
    kind: 'list',
    type: 'str',
    value,
    ...overrides,
  };
}

function renderList(value: unknown, overrides: Partial<FieldDescriptor> = {}) {
  const onChange = vi.fn();
  const view = render(
    <ListField descriptor={listDescriptor(value, overrides)} value={value} onChange={onChange} />,
  );
  return { ...view, onChange };
}

describe('preferDragList：按内容挑形态', () => {
  it('空数组、短值走 chip 墙', () => {
    expect(preferDragList([])).toBe(false);
    expect(preferDragList(['bing', 'duckduckgo'])).toBe(false);
  });

  it('含路径分隔符（目录 / URL）走拖拽列表', () => {
    expect(preferDragList(['/var/log/neobot'])).toBe(true);
    expect(preferDragList(['C:\\data\\logs'])).toBe(true);
    expect(preferDragList(['https://example.com/search'])).toBe(true);
  });

  it('任一元素超过 24 字符走拖拽列表，24 字符以内仍走 chip 墙', () => {
    expect(preferDragList(['a'.repeat(24)])).toBe(false);
    expect(preferDragList(['a'.repeat(25)])).toBe(true);
  });
});

describe('listValues：把配置值收敛成字符串数组', () => {
  it('非数组输入一律得到空数组', () => {
    expect(listValues(undefined)).toEqual([]);
    expect(listValues(null)).toEqual([]);
    expect(listValues('a,b')).toEqual([]);
    expect(listValues({ 0: 'a' })).toEqual([]);
  });

  it('null/undefined 元素变空串，数字/布尔变字符串', () => {
    expect(listValues([null, undefined, 'x', 5, true])).toEqual(['', '', 'x', '5', 'true']);
  });
});

describe('hasComplexItems：识别可视化编辑表达不了的结构', () => {
  it('含对象或嵌套数组时为 true', () => {
    expect(hasComplexItems([{ mode: 'fast' }])).toBe(true);
    expect(hasComplexItems(['a', ['b']])).toBe(true);
  });

  it('纯字符串（含 null 元素）与空数组为 false', () => {
    expect(hasComplexItems([])).toBe(false);
    expect(hasComplexItems(['a', 'b'])).toBe(false);
    expect(hasComplexItems([null, 'a'])).toBe(false);
    expect(hasComplexItems('not-an-array')).toBe(false);
  });
});

describe('typeWillChange：可视化编辑会改类型时提前警告', () => {
  it('数组里混着非字符串元素（数字/布尔）时为 true', () => {
    expect(typeWillChange(['1', '2'], [1, 2])).toBe(true);
    expect(typeWillChange(['true'], [true])).toBe(true);
  });

  it('纯字符串数组且 element_type 为空时为 false', () => {
    expect(typeWillChange(['a', 'b'], ['a', 'b'])).toBe(false);
    expect(typeWillChange(['a'], ['a'], '')).toBe(false);
    expect(typeWillChange(['a'], ['a'], 'str')).toBe(false);
  });

  it('element_type 声明为 int/float/bool 且数组非空时为 true', () => {
    expect(typeWillChange(['1'], ['1'], 'int')).toBe(true);
    expect(typeWillChange(['1.5'], ['1.5'], 'float')).toBe(true);
    expect(typeWillChange(['true'], ['true'], 'bool')).toBe(true);
  });

  it('声明为 int 但数组为空时不警告（没有元素会被改类型）', () => {
    expect(typeWillChange([], [], 'int')).toBe(false);
  });
});

describe('ListField 组件渲染', () => {
  it('chip 墙渲染每项与各自的删除按钮；删除后只提交剩下的元素', () => {
    const { onChange } = renderList(['111111', '222222']);

    expect(screen.getByText('111111')).toBeInTheDocument();
    expect(screen.getByText('222222')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '删除 111111' }));

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith(['222222']);
  });

  it('空数组显示「空」占位', () => {
    renderList([]);

    expect(screen.getByText('空')).toBeInTheDocument();
    expect(screen.getByText('0 项 · 紧凑')).toBeInTheDocument();
  });

  it('含对象元素的数组不渲染 chip，改用 JSON 并说明原因', () => {
    const { container } = renderList([{ mode: 'fast' }]);

    expect(screen.getByText('元素里含对象/数组，只能用 JSON 编辑')).toBeInTheDocument();
    // 不能把对象渲染成 "[object Object]" 假装可编辑——那会把坏数据写回配置
    expect(screen.queryByText('[object Object]')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '添加' })).not.toBeInTheDocument();
    expect(container.querySelector('textarea')).not.toBeNull();
  });

  it('默认形态由 preferDragList 决定：长路径走拖拽列表（每行一个「拖拽排序」手柄）', () => {
    renderList(['/var/log/neobot', '/tmp']);

    expect(screen.getByText('2 项 · 列表（可拖排序）')).toBeInTheDocument();
    expect(screen.getAllByTitle('拖拽排序')).toHaveLength(2);
  });

  it('短值默认 chip 墙，切换按钮可以切到拖拽列表', () => {
    renderList(['bing', 'duckduckgo']);

    expect(screen.getByText('2 项 · 紧凑')).toBeInTheDocument();
    expect(screen.queryByTitle('拖拽排序')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '切换为列表' }));

    expect(screen.getByText('2 项 · 列表（可拖排序）')).toBeInTheDocument();
    expect(screen.getAllByTitle('拖拽排序')).toHaveLength(2);
  });
});
