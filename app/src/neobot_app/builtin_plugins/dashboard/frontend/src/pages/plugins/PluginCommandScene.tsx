import { Copy, MessageSquare } from 'lucide-react';
import type { PluginGuideStep } from '../../api/types';
import Button from '../../components/ui/Button';
import { infoBar } from '../../notifications/infoBar';

export default function PluginCommandScene({
  command,
}: {
  command: NonNullable<PluginGuideStep['command']>;
}) {
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(command.text);
      infoBar({ title: '命令已复制', message: '到对应聊天中核对参数后发送。', tone: 'ok' });
    } catch {
      infoBar({ title: '复制失败', message: '可以选中命令手动复制。', tone: 'err' });
    }
  };
  return (
    <div className="ponder-synthetic-stage ponder-command-scene">
      <div className="ponder-stage-heading">
        <span>
          <MessageSquare size={17} /> 聊天命令
        </span>
        <span>样例</span>
      </div>
      <div className="ponder-command-content">
        <p className="ponder-command-context">{command.context}</p>
        <div className="ponder-command-message" data-ponder-control>
          <span>你发送</span>
          <code>{command.text}</code>
          <Button size="sm" variant="ghost" aria-label="复制命令" onClick={copy}>
            <Copy size={15} /> 复制
          </Button>
        </div>
        {command.reply && (
          <div className="ponder-command-reply">
            <span>机器人回复示例</span>
            <p>{command.reply}</p>
          </div>
        )}
      </div>
    </div>
  );
}
