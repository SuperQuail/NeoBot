import PageHeader from '../components/ui/PageHeader';

/**
 * 机器人通道页：OneBot / 官方机器人状态、扫码与模式切换。
 *
 * 页面的实际内容仍由面板 HTTP 扩展 /qqbot/ 提供（纯 HTML，不依赖 React 构建），
 * 这里只负责把它嵌进面板内容区，让左侧工具栏保持可见。iframe 同源，认证与 CSRF
 * 沿用面板会话；?embed=1 让扩展页隐藏自己的页头，避免双层导航。
 */
export default function BotChannels() {
  const src = new URL('qqbot/?embed=1', window.location.href).toString();
  return (
    <div className="page page--viewport">
      <PageHeader title="机器人通道" />
      <div
        style={{
          flex: 1,
          minHeight: 0,
          overflow: 'hidden',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-large)',
          background: 'var(--panel)',
        }}
      >
        <iframe
          title="机器人通道"
          src={src}
          style={{ display: 'block', width: '100%', height: '100%', border: 0 }}
        />
      </div>
    </div>
  );
}
