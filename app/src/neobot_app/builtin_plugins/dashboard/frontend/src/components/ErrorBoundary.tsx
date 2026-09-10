// ErrorBoundary.tsx —— 页面级错误边界：任何渲染异常都给出可恢复界面，而不是白屏
import { Component } from 'react';
import type { ErrorInfo, ReactNode } from 'react';
import Button from './ui/Button';
import InlineAlert from './ui/InlineAlert';

export interface ErrorBoundaryProps {
  children: ReactNode;
  /** 自定义降级界面 */
  fallback?: (error: Error, reset: () => void) => ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}

export default class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // 面板本身是排障入口，出错时把细节留在控制台便于定位
    console.error('[panel] 渲染异常:', error, info.componentStack);
  }

  reset = (): void => this.setState({ error: null });

  render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;
    if (this.props.fallback) return this.props.fallback(error, this.reset);
    return (
      <div className="page">
        <section className="card">
          <div className="card-head">
            <h3>页面渲染出错</h3>
          </div>
          <InlineAlert tone="error">{error.message || String(error)}</InlineAlert>
          <p className="muted small">
            可以点下面的按钮重试；若持续失败，请查看浏览器控制台或面板日志。
          </p>
          <div className="modal-actions">
            <Button variant="primary" onClick={this.reset}>
              重新渲染
            </Button>
            <Button onClick={() => location.reload()}>刷新页面</Button>
          </div>
        </section>
      </div>
    );
  }
}
