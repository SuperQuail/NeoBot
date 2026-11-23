import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import PluginDependencyCallouts from '../pages/plugins/PluginDependencyCallouts';
import type { Plugin } from '../api/types';

describe('插件服务诊断', () => {
  it('兼容没有服务字段的旧插件', () => {
    const { container } = render(
      <PluginDependencyCallouts plugin={{ name: 'old', status: 'loaded' }} onManage={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
  it('直出后端诊断，声明未加载不会显示为已提供', () => {
    const plugin: Plugin = {
      name: 'demo',
      status: 'disabled',
      services: [
        { service: 'a', kind: 'required', status: 'loaded', message: '必需 a 已加载' },
        { service: 'b', kind: 'required', status: 'missing', message: '缺少 b' },
        { service: 'c', kind: 'optional', status: 'missing', message: '可选 c 未加载' },
        { service: 'd', kind: 'provides', status: 'disabled', message: '启用后将提供 d' },
      ],
      service_conflicts: [{ service: 'x', winner: 'other', loser: 'demo', message: 'x 由 other 提供' }],
    };
    const manage = vi.fn();
    render(<PluginDependencyCallouts plugin={plugin} updateAvailable onManage={manage} />);
    expect(screen.getByText('必需 a 已加载').closest('.inline-alert')).toHaveClass('inline-alert--success');
    expect(screen.getByText('缺少 b').closest('.inline-alert')).toHaveClass('inline-alert--warning');
    expect(screen.getByText('可选 c 未加载').closest('.inline-alert')).toHaveClass('inline-alert--info');
    expect(screen.getByText('启用后将提供 d').closest('.inline-alert')).toHaveClass('inline-alert--info');
    expect(screen.getByText('x 由 other 提供')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '前往依赖管理' }));
    expect(manage).toHaveBeenCalledOnce();
  });
});
