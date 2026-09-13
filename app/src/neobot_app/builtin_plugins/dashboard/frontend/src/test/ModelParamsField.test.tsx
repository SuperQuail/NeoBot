// 模型参数三段式（spec(4) Part B）—— A17/A18/A19 + 自定义参数校验
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import SchemaForm from '../components/SchemaForm';
import ModelParamsField from '../components/schema/ModelParamsField';
import type { FieldDescriptor } from '../api/types';

const BASE_PARAMS = ['temperature', 'max_output_tokens', 'timeout_seconds', 'top_p'];

const CATALOG = [
  {
    name: 'frequency_penalty',
    group: 'openai',
    label: '频率惩罚',
    type: 'float',
    default: 0,
    options: [],
    scope: { providers: ['openai', 'deepseek'] },
  },
  {
    name: 'presence_penalty',
    group: 'openai',
    label: '存在惩罚',
    type: 'float',
    default: 0,
    options: [],
    scope: { providers: ['openai', 'deepseek'] },
  },
  {
    name: 'image_api',
    group: 'image',
    label: '生图接口形态',
    type: 'str',
    default: 'auto',
    options: ['auto', 'edits', 'generations'],
    scope: { model_types: ['image'] },
  },
  {
    name: 'image_reference_param',
    group: 'image',
    label: '参考图字段名',
    type: 'str',
    default: 'image',
    options: [],
    scope: { model_types: ['image'] },
  },
  {
    name: 'deepseek_thinking_mode',
    group: 'deepseek',
    label: '思考模式',
    type: 'str',
    default: 'enabled',
    options: ['enabled', 'disabled', 'random'],
    scope: { providers: ['deepseek'], model_types: ['chat', 'vision', 'other'] },
  },
  {
    name: 'deepseek_reasoning_effort',
    group: 'deepseek',
    label: '思考强度',
    type: 'str',
    default: 'high',
    options: ['high', 'max'],
    scope: { providers: ['deepseek'], model_types: ['chat', 'vision', 'other'] },
  },
  {
    name: 'deepseek_random_thinking_probability',
    group: 'deepseek',
    label: '随机思考概率',
    type: 'float',
    default: 0.6,
    options: [],
    scope: { providers: ['deepseek'], model_types: ['chat', 'vision', 'other'] },
  },
];

function makeField(overrides: Partial<FieldDescriptor> = {}): FieldDescriptor {
  return {
    name: 'params',
    path: ['settings', 'params'],
    kind: 'model_params',
    label: '模型参数',
    base_param_names: BASE_PARAMS,
    enabled_params: [],
    catalog: CATALOG,
    unknown_params: [],
    inapplicable_params: [],
    extra_body: {},
    provider: 'OpenAI',
    model_type: 'chat',
    value: { enabled_params: [], extra_body: {}, values: {} },
    ...overrides,
  };
}

describe('ModelParamsField', () => {
  it('基础区恰为四项基础参数（A17）', () => {
    render(<ModelParamsField descriptor={makeField()} value={makeField().value} onChange={() => {}} />);
    for (const name of BASE_PARAMS) {
      expect(screen.getByText(name)).toBeInTheDocument();
    }
    // 可选参数默认不在「基础区」，只作为下拉候选出现
    expect(screen.queryByText('频率惩罚')).not.toBeInTheDocument();
  });

  it('下拉候选按 scope 过滤：生图模型看不到 DeepSeek 三项（A18）', () => {
    const field = makeField({ provider: 'DeepSeek', model_type: 'image' });
    render(<ModelParamsField descriptor={field} value={field.value} onChange={() => {}} />);
    expect(screen.getByRole('option', { name: /生图接口形态/ })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: /思考模式/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('option', { name: /思考强度/ })).not.toBeInTheDocument();
  });

  it('provider 归一化：deepseek-offical 也能看到 DeepSeek 三项（A18）', () => {
    const field = makeField({ provider: 'deepseek-offical', model_type: 'chat' });
    render(<ModelParamsField descriptor={field} value={field.value} onChange={() => {}} />);
    expect(screen.getByRole('option', { name: /思考模式/ })).toBeInTheDocument();
  });

  it('添加参数后 onChange 同步 enabled_params（A19）', () => {
    const onChange = vi.fn();
    const field = makeField();
    render(<ModelParamsField descriptor={field} value={field.value} onChange={onChange} />);
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'frequency_penalty' } });
    fireEvent.click(screen.getByRole('button', { name: '添加' }));
    expect(onChange).toHaveBeenCalledWith({
      enabled_params: ['frequency_penalty'],
      extra_body: {},
      values: { frequency_penalty: 0 },
    });
  });

  it('移除参数只删名、值保留（A19 / R12）', () => {
    const onChange = vi.fn();
    const field = makeField({
      enabled_params: ['frequency_penalty'],
      value: { enabled_params: ['frequency_penalty'], extra_body: {}, values: { frequency_penalty: 0.5 } },
    });
    render(<ModelParamsField descriptor={field} value={field.value} onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: /移除/ }));
    expect(onChange).toHaveBeenCalledWith({
      enabled_params: [],
      extra_body: {},
      values: { frequency_penalty: 0.5 },
    });
    expect(screen.getByText(/值已保留/)).toBeInTheDocument();
  });

  it('自定义参数按 JSON 解析；__ 前缀被拒绝且不提交', () => {
    const onChange = vi.fn();
    const field = makeField();
    render(<ModelParamsField descriptor={field} value={field.value} onChange={onChange} />);
    const [keyInput, valueInput] = screen.getAllByRole('textbox');

    fireEvent.change(keyInput, { target: { value: '__bad__' } });
    fireEvent.change(valueInput, { target: { value: '1' } });
    fireEvent.click(screen.getByRole('button', { name: '添加自定义' }));
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByText(/不得以 __ 开头/)).toBeInTheDocument();

    fireEvent.change(keyInput, { target: { value: 'top_k' } });
    fireEvent.change(valueInput, { target: { value: '40' } });
    fireEvent.click(screen.getByRole('button', { name: '添加自定义' }));
    expect(onChange).toHaveBeenCalledWith({
      enabled_params: [],
      extra_body: { top_k: 40 },
      values: {},
    });
  });

  it('未知参数与不适用参数渲染成警告行', () => {
    const field = makeField({
      enabled_params: ['no_such_param', 'image_api'],
      unknown_params: ['no_such_param'],
      inapplicable_params: ['image_api'],
      value: {
        enabled_params: ['no_such_param', 'image_api'],
        extra_body: {},
        values: {},
      },
    });
    render(<ModelParamsField descriptor={field} value={field.value} onChange={() => {}} />);
    expect(screen.getAllByText(/不在参数目录中/).length).toBeGreaterThan(0);
    expect(screen.getByText(/当前模型不适用/)).toBeInTheDocument();
  });

  it('含参数区的分组不再单独渲染 hidden 可选字段（A17，两条路径共用）', () => {
    const pseudo = makeField({ base_param_names: [] });
    const fields: FieldDescriptor[] = [
      {
        name: 'settings',
        path: ['settings'],
        kind: 'group',
        value: {},
        fields: [
          { name: 'temperature', path: ['settings', 'temperature'], kind: 'scalar', type: 'float', value: 1 },
          {
            name: 'frequency_penalty',
            path: ['settings', 'frequency_penalty'],
            kind: 'scalar',
            type: 'float',
            value: 0,
            hidden: true,
          },
          pseudo,
        ],
      },
    ];
    render(<SchemaForm fields={fields} values={{ settings: {} }} onChange={() => {}} />);
    expect(screen.getByText('temperature')).toBeInTheDocument();
    expect(screen.getByText('模型参数')).toBeInTheDocument();
    expect(screen.queryByText('frequency_penalty')).not.toBeInTheDocument();
  });
});
