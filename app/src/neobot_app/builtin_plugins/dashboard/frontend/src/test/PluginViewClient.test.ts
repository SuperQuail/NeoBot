import { afterEach, describe, expect, it, vi } from 'vitest';
import type { NeoBotPluginClient, PluginViewContext } from '../../public/assets/plugin-view-sdk';
import script from '../../public/assets/plugin-view-sdk.js?raw';

const disposers: Array<() => void> = [];
afterEach(() => {
  for (const dispose of disposers.splice(0)) dispose();
});

function fixture(mode: 'live' | 'demo' = 'live') {
  const document = window.document.implementation.createHTMLDocument('插件页面');
  const listeners = new Map<string, Set<(event: unknown) => void>>();
  const sent: Array<{ requestId: string; method: string; params: unknown }> = [];
  const parent = { postMessage: vi.fn((value) => sent.push(value)) };
  const disconnected = vi.fn();
  const observed = vi.fn();
  const unobserved = vi.fn();
  const animationFrames: FrameRequestCallback[] = [];
  let resize!: ResizeObserverCallback;
  const root: Record<string, unknown> = {
    document,
    parent,
    crypto: { randomUUID: () => 'client' },
    console,
    innerWidth: 1024,
    innerHeight: 768,
    Event,
    getComputedStyle: window.getComputedStyle.bind(window),
    setTimeout: window.setTimeout.bind(window),
    clearTimeout: window.clearTimeout.bind(window),
    requestAnimationFrame: (callback: FrameRequestCallback) => animationFrames.push(callback),
    ResizeObserver: class {
      constructor(callback: ResizeObserverCallback) {
        resize = callback;
      }
      observe = observed;
      unobserve = unobserved;
      disconnect() {
        disconnected();
      }
    },
    addEventListener: (name: string, listener: (event: unknown) => void) => {
      if (!listeners.has(name)) listeners.set(name, new Set());
      listeners.get(name)!.add(listener);
    },
    removeEventListener: (name: string, listener: (event: unknown) => void) =>
      listeners.get(name)?.delete(listener),
  };
  // 用隔离的窗口对象执行分发的原脚本，验证作者实际使用的入口。
  new Function('globalThis', script)(root);
  const sdk = root.NeoBotPlugin as NeoBotPluginClient;
  disposers.push(() => sdk.dispose());
  const context: PluginViewContext = {
    pluginId: 'demo',
    viewId: 'editor',
    mode,
    permissions: ['manage'],
    available: true,
    suspended: false,
    theme: { '--brand': '#0369a1' },
    reducedMotion: false,
    language: 'zh-CN',
  };
  const emit = (data: unknown, source = parent) => {
    for (const listener of listeners.get('message') ?? []) listener({ source, data });
  };
  const response = (requestId: string, result: unknown, source = parent) =>
    emit(
      { channel: 'neobot-plugin-view', version: 1, kind: 'response', session: 'trusted', requestId, result },
      source,
    );
  const event = (name: string, payload: unknown) =>
    emit({ channel: 'neobot-plugin-view', version: 1, kind: 'event', session: 'trusted', name, payload });
  const ready = async () => {
    const promise = sdk.ready();
    response(sent[0].requestId, context);
    await promise;
  };
  const flushMeasure = () => animationFrames.splice(0).forEach((callback) => callback(0));
  const resizeBody = () => resize([], {} as ResizeObserver);
  return {
    sdk,
    document,
    listeners,
    sent,
    parent,
    response,
    event,
    ready,
    context,
    disconnected,
    flushMeasure,
    resizeBody,
    observed,
    unobserved,
  };
}

describe('公开插件页面客户端', () => {
  it.each([
    ['live', 'inline', false, 1],
    ['live', 'inline', true, 0],
    ['demo', 'inline', false, 0],
    ['live', 'stage', false, 0],
  ] as const)('仅真实内联页请求焦点可见：%s / %s / 暂停 %s', async (mode, layout, suspended, count) => {
    const test = fixture(mode);
    test.context.layout = layout;
    test.context.suspended = suspended;
    test.document.body.innerHTML = '<input>';
    const input = test.document.querySelector('input')!;
    input.getBoundingClientRect = () => new DOMRect(0, 20, 100, 44);
    const active = vi.spyOn(test.document, 'activeElement', 'get').mockReturnValue(input);
    await test.ready();
    input.dispatchEvent(new FocusEvent('focusin', { bubbles: true }));
    test.flushMeasure();
    const reveals = () => test.sent.filter((item) => item.method === 'reveal');
    expect(reveals()).toHaveLength(count);
    if (count)
      expect(reveals()[0].params).toEqual({ rectangle: { left: 0, top: 20, width: 100, height: 44 } });
    input.dispatchEvent(new FocusEvent('focusin', { bubbles: true }));
    active.mockReturnValue(test.document.body);
    test.flushMeasure();
    expect(reveals()).toHaveLength(count);
    test.sdk.dispose();
    active.mockReturnValue(input);
    input.dispatchEvent(new FocusEvent('focusin', { bubbles: true }));
    test.flushMeasure();
    expect(reveals()).toHaveLength(count);
    active.mockRestore();
  });

  it('只上报局部滚动区内可见的锚点，尺寸和滚动改变后清除不可见目标', async () => {
    const test = fixture('demo');
    test.document.body.innerHTML = '<section style="overflow: auto"><div></div></section>';
    const section = test.document.querySelector('section')!;
    const anchor = section.firstElementChild as HTMLElement;
    let clipHeight = 120;
    let anchorTop = 40;
    section.getBoundingClientRect = () => new DOMRect(20, 30, 200, clipHeight);
    Object.defineProperties(section, {
      clientWidth: { value: 200 },
      clientHeight: { get: () => clipHeight },
      offsetWidth: { value: 200 },
      offsetHeight: { get: () => clipHeight },
    });
    anchor.getBoundingClientRect = () => new DOMRect(-10, anchorTop, 400, 300);
    const unregister = test.sdk.registerAnchor('card', anchor);
    await test.ready();
    test.flushMeasure();
    const rectangles = () => test.sent.filter((item) => item.method === 'anchors').at(-1)?.params;
    expect(rectangles()).toEqual({ rectangles: { card: { left: 20, top: 40, width: 200, height: 110 } } });
    expect(test.observed).toHaveBeenCalledWith(section);
    clipHeight = 60;
    test.resizeBody();
    test.flushMeasure();
    expect(rectangles()).toEqual({ rectangles: { card: { left: 20, top: 40, width: 200, height: 50 } } });
    anchorTop = -400;
    section.dispatchEvent(new Event('scroll'));
    test.flushMeasure();
    expect(rectangles()).toEqual({ rectangles: {} });
    unregister();
    unregister();
    expect(test.unobserved.mock.calls.filter(([node]) => node === section)).toHaveLength(1);
  });

  it('贴边、超出视口和卸载后的锚点不会上报越界可见框', async () => {
    const test = fixture('demo');
    test.document.body.innerHTML = '<main></main>';
    const anchor = test.document.querySelector('main')!;
    anchor.getBoundingClientRect = () => new DOMRect(-5, -10, 1100, 900);
    test.sdk.registerAnchor('card', anchor);
    await test.ready();
    test.flushMeasure();
    expect(test.sent.find((item) => item.method === 'anchors')?.params).toEqual({
      rectangles: { card: { left: 0, top: 0, width: 1024, height: 768 } },
    });
    expect(test.document.documentElement.dataset.neobotMode).toBe('demo');
    anchor.remove();
    test.resizeBody();
    test.flushMeasure();
    expect(test.sent.filter((item) => item.method === 'anchors').at(-1)?.params).toEqual({ rectangles: {} });
  });

  it('内联内容增高和缩短都会上报，暂停期间不测量，主题跟随宿主', async () => {
    const test = fixture();
    test.context.layout = 'inline';
    test.context.colorScheme = 'dark';
    test.document.body.style.margin = '0';
    let height = 240;
    test.document.body.getBoundingClientRect = () => ({ height }) as DOMRect;
    await test.ready();
    test.flushMeasure();
    const heights = () => test.sent.filter((item) => item.method === 'resize').map((item) => item.params);
    expect(heights()).toEqual([{ height: 240 }]);
    height = 720;
    test.resizeBody();
    test.flushMeasure();
    height = 120;
    test.resizeBody();
    test.flushMeasure();
    test.resizeBody();
    test.flushMeasure();
    expect(heights()).toEqual([{ height: 240 }, { height: 720 }, { height: 120 }]);
    test.event('context', { ...test.context, suspended: true });
    height = 0;
    test.flushMeasure();
    expect(heights()).toHaveLength(3);
    expect(test.document.documentElement.dataset.neobotLayout).toBe('inline');
    expect(test.document.documentElement.style.colorScheme).toBe('dark');
  });

  it('旧页面保留 body 外边距时，高度仍包含全部内容', async () => {
    const test = fixture();
    test.context.layout = 'inline';
    test.document.body.style.margin = '8px';
    test.document.body.getBoundingClientRect = () => ({ height: 240 }) as DOMRect;
    await test.ready();
    test.flushMeasure();
    expect(test.sent.find((item) => item.method === 'resize')?.params).toEqual({ height: 256 });
  });
  it('只信任父窗口握手，不读取凭据，并接收主题与上下文更新', async () => {
    const test = fixture();
    const contextChanged = vi.fn();
    test.sdk.onContext(contextChanged);
    const ready = test.sdk.ready();
    test.response(test.sent[0].requestId, { ...test.context, mode: 'demo' }, { postMessage: vi.fn() });
    expect(contextChanged).not.toHaveBeenCalled();
    test.response(test.sent[0].requestId, test.context);
    expect(await ready).toEqual(test.context);
    expect(test.document.documentElement.style.getPropertyValue('--brand')).toBe('#0369a1');
    expect(JSON.stringify(test.sent)).not.toMatch(/token|csrf|password/i);
    test.event('context', { ...test.context, suspended: true });
    await expect(test.sdk.action('save', {})).rejects.toMatchObject({ code: 'view_suspended' });
    expect(test.sent).toHaveLength(1);
  });

  it.each(['live', 'demo'] as const)('只在 %s 模式按约定处理样例并定位已注册锚点', async (mode) => {
    const test = fixture(mode);
    test.document.body.innerHTML = '<section><input name="title" value="我的草稿"></section>';
    const anchor = test.document.querySelector('section')!;
    const input = test.document.querySelector('input')!;
    anchor.scrollIntoView = vi.fn();
    anchor.focus = vi.fn();
    const changed = vi.fn();
    input.addEventListener('input', changed);
    const unregister = test.sdk.registerAnchor('title', anchor);
    await test.ready();
    test.event('guide-step', {
      target: 'view.editor.title',
      text: '填写标题',
      mode,
      example: { title: '演示任务' },
    });
    expect(input.value).toBe(mode === 'demo' ? '演示任务' : '我的草稿');
    expect(changed).toHaveBeenCalledTimes(mode === 'demo' ? 1 : 0);
    expect(anchor.getAttribute('data-neobot-guide-current')).toBe('true');
    expect(anchor.scrollIntoView).toHaveBeenCalled();
    expect(anchor.focus).toHaveBeenCalledTimes(mode === 'demo' ? 0 : 1);
    expect(test.sent.some((item) => item.method === 'action')).toBe(false);
    unregister();
  });

  it('关闭时拒绝在途请求并移除观察器、样式和事件监听', async () => {
    const test = fixture();
    await test.ready();
    const action = test.sdk.action('save', { title: '任务' });
    await Promise.resolve();
    const rejected = expect(action).rejects.toThrow('插件页面已关闭');
    test.sdk.dispose();
    await rejected;
    expect(test.disconnected).toHaveBeenCalledTimes(1);
    expect(test.document.head.querySelector('style')).toBeNull();
    expect(test.listeners.get('message')?.size).toBe(0);
    expect(test.listeners.get('resize')?.size).toBe(0);
    expect(test.listeners.get('pagehide')?.size).toBe(0);
  });
});
