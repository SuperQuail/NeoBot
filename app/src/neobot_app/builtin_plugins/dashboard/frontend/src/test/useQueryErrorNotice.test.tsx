import { renderHook } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { useQueryErrorNotice } from '../hooks/useQueryErrorNotice';
import { infoBar } from '../notifications/infoBar';

vi.mock('../notifications/infoBar', () => ({ infoBar: vi.fn() }));
beforeEach(() => vi.clearAllMocks());

it('同一轮询失败不刷屏，成功恢复后再次失败会重新通知', () => {
  const view = renderHook(({ error, updatedAt }) => useQueryErrorNotice(error, updatedAt, '列表读取失败'), {
    initialProps: { error: '连接中断' as string | null, updatedAt: 0 },
  });
  expect(infoBar).toHaveBeenCalledTimes(1);
  view.rerender({ error: null, updatedAt: 0 });
  view.rerender({ error: '连接中断', updatedAt: 0 });
  expect(infoBar).toHaveBeenCalledTimes(1);
  view.rerender({ error: null, updatedAt: 100 });
  view.rerender({ error: '连接中断', updatedAt: 100 });
  expect(infoBar).toHaveBeenCalledTimes(2);
  expect(infoBar).toHaveBeenLastCalledWith({ title: '列表读取失败', message: '连接中断', tone: 'err' });
});

it('关闭或暂停的内容不发布通知，打开后报告仍未恢复的失败', () => {
  const view = renderHook(({ enabled }) => useQueryErrorNotice('读取超时', 0, '页面读取失败', enabled), {
    initialProps: { enabled: false },
  });
  expect(infoBar).not.toHaveBeenCalled();
  view.rerender({ enabled: true });
  expect(infoBar).toHaveBeenCalledTimes(1);
});
