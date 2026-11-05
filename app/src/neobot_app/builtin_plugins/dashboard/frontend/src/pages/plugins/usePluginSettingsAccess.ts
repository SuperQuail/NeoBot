import { api } from '../../api/endpoints';
import type { ConfigDocument, Result } from '../../api/types';
import type { PluginActionHandlers } from './pluginProps';
import type { PluginViewConfigAccess, RunPluginAction } from './pluginViewBridge';

interface Options {
  pluginId: string;
  canWrite: boolean;
  blocked: boolean;
  act: PluginActionHandlers['act'];
  applyDocument: PluginActionHandlers['applyDocument'];
}

/** 独立插件页面与配置编辑器共用写入锁；读取列表不会锁住整个编辑器。 */
export function usePluginSettingsAccess({ pluginId, canWrite, blocked, act, applyDocument }: Options) {
  const run: RunPluginAction = async (action, values) => {
    if (action.permission !== 'read' && (!canWrite || blocked))
      return { ok: false, code: 'action_busy', error: '请先保存或放弃配置修改，并等待当前操作结束' };
    const response =
      action.permission === 'read'
        ? await api.pluginAction(pluginId, action.id, values)
        : await act(
            `action:${action.id}`,
            () => api.pluginAction(pluginId, action.id, values),
            action.title,
            false,
          );
    if (!response) return null;
    return response.data ? response.data : { ok: false, error: response.error || '插件操作失败' };
  };

  const configAccess: PluginViewConfigAccess = {
    get: () => api.pluginConfig(pluginId),
    save: async (values, revision): Promise<Result<ConfigDocument>> => {
      if (!canWrite || blocked)
        return { ok: false, data: null, status: 409, error: '请先保存或放弃配置修改，并等待当前操作结束' };
      const response = await act(
        'view-config',
        () =>
          api.pluginConfigSave(pluginId, {
            mode: 'form',
            config: values,
            revision,
            reload: true,
          }),
        '配置已保存',
        false,
      );
      if (!response) return { ok: false, data: null, status: 409, error: '另一项操作正在执行' };
      if (response.ok && response.data) applyDocument(response.data);
      return response;
    },
  };
  return { run, configAccess };
}
