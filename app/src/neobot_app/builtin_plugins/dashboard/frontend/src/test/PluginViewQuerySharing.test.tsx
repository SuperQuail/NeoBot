import { render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { api } from '../api/endpoints';
import { QK } from '../data/queryKeys';
import { fetchQuery } from '../data/queryCore';
import { usePluginViews } from '../pages/plugins/usePluginViews';

vi.mock('../api/endpoints', () => ({ api: { pluginViews: vi.fn() } }));

function SettingsAndManual({ hasScenes }: { hasScenes: boolean }) {
  const settings = usePluginViews('shared-view', true);
  usePluginViews('shared-view', hasScenes, false);
  return <p>{settings.data?.map((view) => view.title).join(', ')}</p>;
}

it('没有页面场景的说明书不会清空同一插件的真实设置缓存', async () => {
  vi.mocked(api.pluginViews).mockResolvedValue({
    ok: true,
    status: 200,
    error: '',
    data: { ok: true, items: [{ id: 'live', title: '直播订阅', entry: 'web/index.html', anchors: [], url: '/plugins-ui/demo/live/' }] },
  });
  const { rerender } = render(<SettingsAndManual hasScenes />);
  await screen.findByText('直播订阅');
  rerender(<SettingsAndManual hasScenes={false} />);
  await fetchQuery(QK.pluginViews('shared-view'), { force: true });
  await waitFor(() => expect(api.pluginViews).toHaveBeenCalledTimes(2));
  expect(screen.getByText('直播订阅')).toBeInTheDocument();
});
