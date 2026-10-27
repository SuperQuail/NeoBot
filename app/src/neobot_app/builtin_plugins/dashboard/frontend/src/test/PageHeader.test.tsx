import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import PageHeader from '../components/ui/PageHeader';

describe('PageHeader', () => {
  it('统一保留标题与操作，不附加说明小字', () => {
    const { container } = render(<PageHeader title="运行概览" actions={<button>刷新</button>} />);
    expect(screen.getByRole('heading', { name: '运行概览', level: 1 })).toBeVisible();
    expect(screen.getByRole('button', { name: '刷新' })).toBeVisible();
    expect(screen.queryByText('消息、连接与资源，一屏掌握。')).not.toBeInTheDocument();
    expect(container.querySelector('.page-description')).toBeNull();
  });
});
