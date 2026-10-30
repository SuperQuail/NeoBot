import { useEffect } from 'react';
import { act, render } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import PluginPonderStage from '../pages/plugins/PluginPonderStage';
import type { PluginAnchorRect, PluginViewSurface } from '../pages/plugins/pluginViewBridge';

vi.mock('../pages/plugins/PluginViewFrame', () => ({
  default: function FrameMock({ onAnchors }: { onAnchors: (rects: Record<string, PluginAnchorRect>) => void }) {
    useEffect(() => {
      onAnchors({ card: { left: 0, top: 0, width: 400, height: 240 } });
    }, [onAnchors]);
    return <div>隔离的插件素材</div>;
  },
}));

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

it('插件素材的高亮由宿主绘制，舞台缩小时仍保留四边，卸载释放尺寸观察', () => {
  let width = 400;
  let height = 300;
  let resize!: () => void;
  const disconnect = vi.fn();
  vi.stubGlobal(
    'ResizeObserver',
    class {
      constructor(callback: () => void) {
        resize = callback;
      }
      observe() {}
      disconnect = disconnect;
    },
  );
  vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockImplementation(() => width);
  vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockImplementation(() => height);
  const guide = { id: 'start', title: '开始', steps: [{ target: 'view.editor.card', text: '查看清单' }] };
  const surface: PluginViewSurface = {
    available: true,
    source: 'runtime',
    state: 'running',
    permissions: ['read'],
    contract: {
      schema_version: 1,
      plugin: { name: 'demo' },
      config: null,
      actions: [],
      resources: [],
      guides: [guide],
    },
  };
  const test = render(
    <PluginPonderStage
      pluginId="demo"
      surface={surface}
      guide={guide}
      step={guide.steps[0]}
      views={[{ id: 'editor', title: '素材', entry: 'index.html', anchors: ['card'], url: '/demo' }]}
      reducedMotion
    />,
  );
  const frame = test.container.querySelector('.ponder-focus-frame')!;
  expect(frame).toHaveStyle({ left: '4px', top: '4px', width: '392px', height: '236px' });
  act(() => {
    width = 320;
    height = 180;
    resize();
  });
  expect(frame).toHaveStyle({ left: '4px', top: '4px', width: '312px', height: '172px' });
  test.unmount();
  expect(disconnect).toHaveBeenCalledOnce();
});
