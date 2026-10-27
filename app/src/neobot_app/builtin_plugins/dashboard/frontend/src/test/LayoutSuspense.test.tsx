import { lazy, useEffect } from 'react';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { expect, it, vi } from 'vitest';
import Layout from '../components/Layout';
import { ConfirmHost } from '../components/ui/ConfirmDialog';
import { MotionProvider } from '../components/ui/PageMotion';
import { useEditorGuard } from '../hooks/useEditorGuard';

vi.mock('../api/endpoints', () => ({
  api: { extensions: async () => ({ items: [] }), powerStatus: async () => null },
}));

it('确认离开后，懒加载骨架期间立即卸载旧编辑器及草稿保护', async () => {
  const cleanup = vi.fn();
  function Editor() {
    useEditorGuard(true, false);
    useEffect(() => cleanup, []);
    return <input aria-label="旧编辑器" defaultValue="待放弃的草稿" />;
  }
  let finish!: (value: { default: () => JSX.Element }) => void;
  const PendingPage = lazy(
    () =>
      new Promise<{ default: () => JSX.Element }>((resolve) => {
        finish = resolve;
      }),
  );
  render(
    <MemoryRouter initialEntries={['/config']}>
      <MotionProvider>
        <Routes>
          <Route element={<Layout />}>
            <Route path="config" element={<Editor />} />
            <Route path="system" element={<PendingPage />} />
          </Route>
        </Routes>
        <ConfirmHost />
      </MotionProvider>
    </MemoryRouter>,
  );
  await screen.findByLabelText('旧编辑器');
  await userEvent.click(screen.getByRole('link', { name: '系统' }));
  await userEvent.click(await screen.findByRole('button', { name: '放弃并离开' }));
  expect(await screen.findByText('正在加载系统状态')).toBeInTheDocument();
  expect(screen.queryByLabelText('旧编辑器')).not.toBeInTheDocument();
  expect(cleanup).toHaveBeenCalledTimes(1);
  await act(async () => {
    finish({ default: () => <div>新页面</div> });
  });
  expect(await screen.findByText('新页面')).toBeInTheDocument();
});
