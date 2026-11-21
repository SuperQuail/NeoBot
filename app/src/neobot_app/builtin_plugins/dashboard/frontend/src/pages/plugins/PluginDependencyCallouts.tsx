import type { Plugin } from '../../api/types';
import InlineAlert from '../../components/ui/InlineAlert';
import Button from '../../components/ui/Button';

export default function PluginDependencyCallouts({
  plugin,
  updateAvailable,
  onManage,
}: {
  plugin: Plugin;
  updateAvailable?: boolean;
  onManage?: () => void;
}) {
  const slots = plugin.services || [];
  const conflicts = plugin.service_conflicts || [];
  const diagnostics = slots.map((slot) => slot.message).filter(Boolean);
  const isDuplicate = (message: string) => diagnostics.some((diagnostic) => message.includes(diagnostic));
  const legacy =
    plugin.disabled_reason && !isDuplicate(plugin.disabled_reason)
      ? plugin.disabled_reason
      : plugin.dependency_issues?.filter((message) => !isDuplicate(message)).join('；');
  if (!slots.length && !conflicts.length && !legacy && !updateAvailable && !plugin.service_undeclared?.length)
    return null;
  return (
    <section className="plugin-callouts" aria-label="插件依赖状态">
      {updateAvailable && (
        <InlineAlert
          tone="info"
          actions={
            onManage && (
              <Button size="sm" onClick={onManage}>
                前往依赖管理
              </Button>
            )
          }
        >
          当前的插件版本不是最新。
        </InlineAlert>
      )}
      {legacy && <InlineAlert tone="warning">{legacy}</InlineAlert>}
      {slots.map((slot, index) => (
        <InlineAlert
          key={`${slot.kind}-${slot.service}-${index}`}
          tone={
            slot.status === 'loaded'
              ? 'success'
              : slot.status === 'conflict' || slot.kind === 'required'
                ? 'warning'
                : 'info'
          }
          title={`${slot.kind === 'required' ? '必需服务' : slot.kind === 'optional' ? '可选服务' : '提供服务'}：${slot.service}${slot.specifier || ''}`}
        >
          {slot.message}
        </InlineAlert>
      ))}
      {conflicts.map((item, index) => (
        <InlineAlert key={`${item.service}-${index}`} tone="warning">
          {item.message}
        </InlineAlert>
      ))}
      {!!plugin.service_undeclared?.length && (
        <InlineAlert tone="warning">已注册但未声明的服务：{plugin.service_undeclared.join('、')}</InlineAlert>
      )}
    </section>
  );
}
