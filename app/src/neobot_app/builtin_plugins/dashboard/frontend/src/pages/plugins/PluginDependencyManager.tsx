import type { Plugin } from '../../api/types';
import Modal from '../../components/Modal';
import Button from '../../components/ui/Button';
import PluginDependencyCallouts from './PluginDependencyCallouts';

export default function PluginDependencyManager({
  plugin,
  items,
  open,
  busy,
  canInstall,
  onClose,
  onSelect,
  onInstall,
}: {
  plugin: Plugin;
  items: Plugin[];
  open: boolean;
  busy: boolean;
  canInstall: boolean;
  onClose: () => void;
  onSelect: (plugin: Plugin) => void;
  onInstall: () => void;
}) {
  const names = new Set((plugin.services || []).map((slot) => slot.provider).filter(Boolean));
  for (const dependency of plugin.dependencies || []) names.add(dependency.split(/[<>=!~]/)[0].trim());
  const providers = items.filter((item) => names.has(item.name) && item.name !== plugin.name);
  return (
    <Modal open={open} title={`${plugin.name} · 依赖管理`} onClose={onClose}>
      <div className="plugin-info-content">
        <PluginDependencyCallouts plugin={plugin} />
        {!!plugin.dependencies?.length && <p>前置插件：{plugin.dependencies.join('、')}</p>}
        <p className="muted small">打开提供者后，可使用其启用、更新和配置入口；切换前会确认未保存的配置。</p>
        {providers.map((provider) => (
          <div className="plugin-info-item" key={provider.id || provider.name}>
            <strong>
              {provider.name} · {provider.version || '未声明版本'}
            </strong>
            <Button disabled={busy} onClick={() => onSelect(provider)}>
              管理提供者 {provider.name}
            </Button>
          </div>
        ))}
        {names.has('__host__') && <p className="muted small">宿主服务随 NeoBot 本体管理。</p>}
        <p className="muted small">未安装的提供者需要先取得插件 GitHub 仓库地址，再通过现有安装流程安装。</p>
        <Button disabled={!canInstall || busy} onClick={onInstall}>
          安装提供者插件
        </Button>
        <Button disabled={busy} onClick={() => onSelect(plugin)}>
          管理当前插件（启用 / 更新）
        </Button>
      </div>
    </Modal>
  );
}
