import { useLayoutEffect, useRef, useState } from 'react';
import Button from '../../components/ui/Button';
import { AlignLeft, Maximize2, Minimize2 } from 'lucide-react';

/** 预览只缩放隔离文档；宿主不读取或执行插件 HTML。 */
export default function PluginHtmlPreview({
  html,
  title,
  width = 720,
  height = 900,
  fallbackText,
}: {
  html: string;
  title: string;
  width?: number;
  height?: number;
  fallbackText?: string;
}) {
  const canvas = useRef<HTMLDivElement>(null);
  const [available, setAvailable] = useState(width);
  const [original, setOriginal] = useState(false);
  const [showText, setShowText] = useState(false);
  const documentWidth = Number.isFinite(width) && width > 0 ? Math.min(width, 4096) : 720;
  const documentHeight = Number.isFinite(height) && height > 0 ? Math.min(height, 8192) : 900;
  const scale = original ? 1 : Math.min(1, available / documentWidth, 360 / documentHeight);
  useLayoutEffect(() => {
    const node = canvas.current;
    if (!node) return;
    const measure = () => setAvailable(node.clientWidth || documentWidth);
    measure();
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measure);
    observer?.observe(node);
    return () => observer?.disconnect();
  }, [documentWidth]);
  return (
    <div className="plugin-html-preview">
      <div className="plugin-preview-frame-area">
        <div className={'plugin-preview-canvas' + (original ? ' is-original' : '')} ref={canvas}>
          <div
            style={{
              width: Math.ceil(documentWidth * scale),
              height: Math.ceil(documentHeight * scale),
              position: 'relative',
              // 只收住 iframe 缩放前的布局框，绘制内容恰好等于计算后的画布。
              overflow: 'clip',
            }}
          >
            <iframe
              title={title}
              sandbox=""
              referrerPolicy="no-referrer"
              style={{
                width: documentWidth,
                height: documentHeight,
                transform: `scale(${scale})`,
                transformOrigin: 'top left',
              }}
              srcDoc={`<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data: https:; style-src 'unsafe-inline'; font-src data:">${html}`}
            />
          </div>
        </div>
      </div>
      <div className="plugin-preview-tools">
        <Button size="sm" variant="ghost" onClick={() => setOriginal((value) => !value)}>
          {original ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          {original ? '适应窗口' : '查看原始大小'}
        </Button>
        {fallbackText && (
          <Button
            size="sm"
            variant="ghost"
            aria-expanded={showText}
            onClick={() => setShowText((value) => !value)}
          >
            <AlignLeft size={14} />
            {showText ? '收起文字内容' : '查看文字内容'}
          </Button>
        )}
      </div>
      {showText && <pre className="plugin-preview-text">{fallbackText}</pre>}
    </div>
  );
}
