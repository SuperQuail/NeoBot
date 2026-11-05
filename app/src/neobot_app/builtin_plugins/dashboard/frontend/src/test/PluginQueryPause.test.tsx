import { act, render, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { clearQueries } from '../data/queryCore';
import { useQuery } from '../data/useQuery';

beforeEach(() => clearQueries());
afterEach(() => vi.useRealTimers());

it('暂停的查询不首读，恢复后读取，保留已经显示的数据', async () => {
  const fetcher = vi.fn().mockResolvedValue({ count: 7 });
  function Probe({ enabled }: { enabled: boolean }) {
    const query = useQuery<{ count: number }>('ponder-pause', fetcher, { enabled, refetchOnMount: true });
    return <span>{query.data?.count ?? '等待'}</span>;
  }
  const view = render(<Probe enabled={false} />);
  await act(async () => {});
  expect(fetcher).not.toHaveBeenCalled();
  view.rerender(<Probe enabled />);
  await waitFor(() => expect(view.getByText('7')).toBeInTheDocument());
  expect(fetcher).toHaveBeenCalledTimes(1);
  view.rerender(<Probe enabled={false} />);
  await act(async () => {});
  expect(fetcher).toHaveBeenCalledTimes(1);
  expect(view.getByText('7')).toBeInTheDocument();
});
