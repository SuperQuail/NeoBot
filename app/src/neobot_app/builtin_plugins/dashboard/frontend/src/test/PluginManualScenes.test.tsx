import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { PluginGuide, PluginGuideStep, PluginSurfaceContract } from '../api/types';
import PluginPonderStage from '../pages/plugins/PluginPonderStage';
import { infoBar } from '../notifications/infoBar';

vi.mock('../notifications/infoBar', () => ({ infoBar: vi.fn() }));

const contract: PluginSurfaceContract = {
  schema_version: 1,
  plugin: { name: 'demo' },
  config: {
    type: 'object',
    properties: {
      default_card_style: {
        type: 'string',
        title: '卡片风格',
        default: 'random',
        enum: ['random', 'minimal'],
      },
      enabled: { type: 'boolean', default: true },
      extra: { type: 'array', items: { type: 'string' } },
      nested: { $ref: '#/$defs/Settings' },
      cookie: { type: 'string', format: 'password' },
    },
    $defs: { Settings: { type: 'object', properties: { count: { type: 'integer', default: 4 } } } },
  },
  actions: [
    { id: 'subscribe', title: '添加监听', permission: 'manage', input_schema: null, output_schema: null },
  ],
  resources: [],
  guides: [],
};

function scene(step: PluginGuideStep) {
  const guide: PluginGuide = { id: 'start', title: '开始使用', steps: [step] };
  return render(
    <PluginPonderStage
      pluginId="demo"
      surface={{ contract, permissions: ['read'], available: true, state: 'loaded', source: 'runtime' }}
      guide={guide}
      step={step}
      views={[]}
      reducedMotion
    />,
  );
}

describe('说明书场景对应真实入口', () => {
  it('配置演示从目标字段生成同一套控件，不受无关集合字段影响', () => {
    scene({
      target: 'config.default_card_style',
      text: '选择默认风格。',
      example: { default_card_style: 'minimal' },
    });
    expect(screen.getByText('插件管理 / demo / 配置表单')).toBeInTheDocument();
    expect(screen.getByLabelText('卡片风格')).toHaveValue('minimal');
    expect(screen.getByLabelText('卡片风格')).toBeDisabled();
    expect(screen.getByLabelText('卡片风格')).toHaveAttribute('id', 'ponder-config-default_card_style');
    expect(screen.queryByText('继续下一步')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '保存' })).not.toBeInTheDocument();
  });

  it('嵌套引用字段保留真实路径和零值，演示控件ID不占用真实编辑器ID', () => {
    scene({ target: 'config.nested.count', text: '设置数量。', example: { nested: { count: 0 } } });
    const input = screen.getByRole('spinbutton');
    expect(input).toHaveValue(0);
    expect(input.id).toBe('ponder-config-nested-count');
    expect(screen.getByText('nested.')).toBeInTheDocument();
  });

  it('布尔样例保留false，敏感字段不显示作者样例', () => {
    const rendered = scene({ target: 'config.enabled', text: '关闭默认开关。', example: { enabled: false } });
    expect(screen.getByRole('checkbox')).not.toBeChecked();
    rendered.unmount();
    scene({ target: 'config.cookie', text: '按需配置凭据。', example: { cookie: 'private-sample-value' } });
    expect(screen.queryByDisplayValue('private-sample-value')).not.toBeInTheDocument();
    expect(screen.getByText('在真实配置中填写，说明书不展示凭据。')).toBeInTheDocument();
  });

  it('根配置目标渲染完整表单、保留凭据空白，并仅提供禁用的模拟保存', () => {
    const rendered = scene({
      target: 'config',
      text: '模拟保存',
      form: 'save',
      example: { default_card_style: 'minimal', enabled: false, cookie: 'private-example-cookie' },
    });
    expect(screen.getByLabelText('卡片风格')).toHaveValue('minimal');
    expect(screen.getByRole('checkbox')).not.toBeChecked();
    expect(screen.getByRole('spinbutton')).toHaveValue(4);
    expect(screen.getByLabelText('cookie')).toHaveValue('');
    expect(screen.queryByDisplayValue('private-example-cookie')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '模拟保存' })).toBeDisabled();
    expect(rendered.container.querySelector('[data-ponder-control]')).toContainElement(
      screen.getByRole('button', { name: '模拟保存' }),
    );
    expect(rendered.container.querySelector('.ponder-stage-viewport')).toHaveAttribute(
      'data-reduced-motion',
      'true',
    );
  });

  it('聊天步骤明确实际场景和命令，不生成业务表单或发送按钮', () => {
    scene({
      target: 'action.subscribe',
      text: '在目标群添加监听。',
      command: { text: '/监听 610001', context: '目标QQ群，先 @机器人；需要次级管理员', reply: '已添加监听' },
    });
    expect(screen.getByText('目标QQ群，先 @机器人；需要次级管理员')).toBeInTheDocument();
    expect(screen.getByText('/监听 610001')).toBeInTheDocument();
    expect(screen.getByText('已添加监听')).toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '发送' })).not.toBeInTheDocument();
  });

  it('复制只写剪贴板，结果通过InfoBar反馈', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
    scene({
      target: 'action.subscribe',
      text: '添加监听。',
      command: { text: '/监听 610001', context: '目标QQ群' },
    });
    fireEvent.click(screen.getByRole('button', { name: '复制命令' }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('/监听 610001'));
    expect(infoBar).toHaveBeenCalledWith(expect.objectContaining({ title: '命令已复制' }));
    expect(screen.queryByText('命令已复制')).not.toBeInTheDocument();
  });

  it('旧动作说明只展示用途与样例，不冒充设置入口', () => {
    scene({ target: 'action.subscribe', text: '了解这项能力。', example: { room: 610001 } });
    expect(screen.getByText('添加监听')).toBeInTheDocument();
    expect(screen.getByText('610001')).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(screen.queryByText('继续下一步')).not.toBeInTheDocument();
  });
});
