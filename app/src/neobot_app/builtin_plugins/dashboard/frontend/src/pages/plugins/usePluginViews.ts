import { api } from '../../api/endpoints';
import type { PluginView } from '../../api/types';
import { QK, POLL } from '../../data/queryKeys';
import { useQuery } from '../../data/useQuery';

export function usePluginViews(pluginId: string, declared: boolean, enabled = true) {
  return useQuery<Array<PluginView & { url: string }>>(
    QK.pluginViews(pluginId),
    async () => {
      const response = await api.pluginViews(pluginId);
      if (!response.ok || !response.data?.ok) throw new Error(response.error || '插件页面读取失败');
      return response.data.items.map((view) => {
        if (!view.url) throw new Error('插件页面缺少入口地址');
        return { ...view, url: view.url };
      });
    },
    {
      interval: POLL.pluginSurface,
      refetchOnMount: true,
      deps: [declared],
      enabled: declared && enabled,
    },
  );
}
