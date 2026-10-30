import { api } from '../../api/endpoints';
import type { PluginSurfacePayload } from '../../api/types';
import { QK, POLL } from '../../data/queryKeys';
import { useQuery } from '../../data/useQuery';

/** 设置和说明书共用契约缓存，运行状态与权限随宿主自动同步。 */
export function usePluginSurface(pluginId: string) {
  return useQuery<PluginSurfacePayload>(
    QK.pluginSurface(pluginId),
    async () => {
      const response = await api.pluginSurface(pluginId);
      if (!response.ok || !response.data || response.data.ok === false)
        throw new Error(response.error || '插件能力读取失败');
      return response.data;
    },
    { interval: POLL.pluginSurface, refetchOnMount: true, enabled: !!pluginId },
  );
}
