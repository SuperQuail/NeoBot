// 单元测试：ConfigTreePanel —— 左树分区导航 + 右侧只渲染选中分区的搜索/高亮
//
// 这一层的核心风险是「两套判定各说各话」：左树按 fieldMatches / countLeafHits 算命中，
// 右侧却按另一套规则渲染，于是标题说「命中 N 项」、实际渲染出的字段却对不上。
// 所以纯函数与组件行为都要锁住。
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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

function group(
  name: string,
  fields: FieldDescriptor[],
  overrides: Partial<FieldDescriptor> = {},
): FieldDescriptor {
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
  const maxResults = scalar('max_results', ['web_search', 'max_results'], {
    description: '单次返回结果条数',
  });

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
  it('编辑顶层散字段时保留其余顶层字段与分组内容', () => {
    const props = baseProps('');
    props.schema = [scalar('version', ['version'], { type: 'int', value: 2 }), ...props.schema];
    props.draft = { version: 2, ...props.draft };
    render(<ConfigTreePanel {...props} />);
    fireEvent.change(screen.getByRole('spinbutton', { name: 'version' }), { target: { value: '3' } });
    expect(props.onChange).toHaveBeenCalledWith([], { ...props.draft, version: 3 });
  });

  it('分区只显示一个标题，说明和生效方式按需展开且字段重启例外仍保留', async () => {
    const props = baseProps('');
    props.schema = [
      group(
        'bot',
        [
          scalar('name', ['bot', 'name'], { hot_reload: true, value: '小乔' }),
          scalar('port', ['bot', 'port'], {
            type: 'int',
            hot_reload: false,
            value: 9981,
            restart_reason: '监听端口需重启',
          }),
          group(
            'nested',
            [
              scalar('enabled', ['bot', 'nested', 'enabled'], {
                type: 'bool',
                hot_reload: true,
                value: true,
              }),
            ],
            { path: ['bot', 'nested'], description: '子分组说明仍需保留' },
          ),
        ],
        { description: '机器人身份与人设', hot_reload: false },
      ),
    ];
    props.draft = { bot: { name: '小乔', port: 9981, nested: { enabled: true } } };
    // 根组在独立工作区始终展开，不受旧折叠状态影响。
    props.collapse = { bot: true };
    const { container } = render(<ConfigTreePanel {...props} />);
    expect(screen.getAllByRole('heading', { name: 'bot' })).toHaveLength(1);
    expect(container.querySelector('.cfg-root .cfg-reload-policy')).not.toBeInTheDocument();
    expect(screen.getByText('机器人身份与人设')).not.toBeVisible();
    expect(screen.getByDisplayValue('小乔')).toBeVisible();
    expect(screen.getByRole('heading', { name: 'nested' })).toBeVisible();
    expect(screen.getByText('子分组说明仍需保留')).toBeVisible();
    expect(screen.getByText('需重启')).toHaveAttribute('title', '监听端口需重启');
    await userEvent.click(screen.getByLabelText('查看 bot 分区说明'));
    expect(screen.getByText('机器人身份与人设')).toBeVisible();
    expect(screen.getByText('支持重载配置；需重启项已单独标注')).toBeVisible();
  });

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

  it('下拉分区与导航按钮同步选择，切换不修改草稿且忙碌时两处均禁用', () => {
    const { props, rerender } = renderPanel();
    const select = screen.getByRole('combobox', { name: '选择配置分区' });
    fireEvent.change(select, { target: { value: 'web_search' } });

    expect(select).toHaveValue('web_search');
    expect(screen.getByDisplayValue(SEARCH_VALUE)).toBeInTheDocument();
    expect(screen.queryByDisplayValue(CHAT_VALUE)).not.toBeInTheDocument();
    const nav = screen.getByRole('navigation', { name: '配置分区' });
    expect(within(nav).getByRole('button', { name: /web_search/ })).toHaveAttribute('aria-current', 'true');
    expect(props.onChange).not.toHaveBeenCalled();

    rerender(<ConfigTreePanel {...props} disabled />);
    expect(select).toBeDisabled();
    for (const button of within(nav).getAllByRole('button')) expect(button).toBeDisabled();
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

  it('深层 registry 数组保留字段路径，第二项参数修改及添加不会覆盖其它模型', () => {
    const registry = [
      { name: '日常对话', settings: { temperature: 0.6, enabled_params: [], extra_body: {} } },
      { name: '复杂推理', settings: { temperature: 0.8, enabled_params: [], extra_body: {} } },
    ];
    const items = registry.map((item, index) => {
      const path = ['models', 'registry', String(index)];
      return {
        index,
        fields: [
          scalar('name', [...path, 'name'], { value: item.name }),
          group(
            'settings',
            [
              scalar('temperature', [...path, 'settings', 'temperature'], {
                type: 'float',
                value: item.settings.temperature,
              }),
              {
                name: 'params',
                path: [...path, 'settings', 'params'],
                kind: 'model_params',
                label: '模型参数',
                base_param_names: ['temperature'],
                catalog: [{ name: 'top_p', label: '采样范围', type: 'float', default: 1 }],
                value: { enabled_params: [], extra_body: {}, values: {} },
              },
            ],
            { path: [...path, 'settings'], value: item.settings },
          ),
        ],
      };
    });
    const props: ConfigTreePanelProps = {
      ...baseProps(''),
      schema: [
        group('models', [
          { name: 'registry', path: ['models', 'registry'], kind: 'model_list', value: registry, items },
        ]),
      ],
      draft: { models: { registry } },
    };
    const { container } = render(<ConfigTreePanel {...props} />);
    const temperature = screen.getByRole('spinbutton', {
      name: /^models\.registry\.1\.settings\.\s*temperature$/,
    });
    fireEvent.change(temperature, { target: { value: '0.9' } });
    expect(props.onChange).toHaveBeenLastCalledWith(['models'], {
      registry: [registry[0], { ...registry[1], settings: { ...registry[1].settings, temperature: 0.9 } }],
    });

    const secondItem = temperature.closest('.cfg-item') as HTMLElement;
    expect(within(secondItem).getByRole('heading', { name: 'settings' })).toBeVisible();
    expect(within(secondItem).getByRole('heading', { name: '模型参数' })).toBeVisible();
    fireEvent.change(within(secondItem).getByRole('combobox', { name: '待添加的模型参数' }), {
      target: { value: 'top_p' },
    });
    fireEvent.click(within(secondItem).getByRole('button', { name: '添加' }));
    expect(props.onChange).toHaveBeenLastCalledWith(['models'], {
      registry: [
        registry[0],
        {
          ...registry[1],
          settings: {
            ...registry[1].settings,
            params: { enabled_params: ['top_p'], extra_body: {}, values: { top_p: 1 } },
          },
        },
      ],
    });
    expect(
      container.querySelector('[data-field-path="models.registry.1.settings.params"]'),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '新增' })).toBeEnabled();
  });
});
