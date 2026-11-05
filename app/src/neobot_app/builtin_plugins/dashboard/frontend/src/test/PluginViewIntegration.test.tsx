import { act, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { PluginViewSurface } from '../pages/plugins/pluginViewBridge';
import PluginViewFrame from '../pages/plugins/PluginViewFrame';
import { infoBar } from '../notifications/infoBar';

vi.mock('../notifications/infoBar', () => ({ infoBar: vi.fn() }));

const view = {
  id: 'editor',
  title: '插件设置',
  entry: 'web/index.html',
  anchors: ['note', 'save'],
  url: '/plugins-ui/demo/editor/?revision=one',
};
const surface: PluginViewSurface = {
  available: true,
  state: 'loaded',
  source: 'runtime',
  permissions: ['read', 'manage'],
  contract: {
    schema_version: 1,
    plugin: { name: 'demo' },
    config: { type: 'object' },
    resources: [],
    views: [view],
    actions: [
      { id: 'save', title: '保存记录', permission: 'manage', input_schema: null, output_schema: null },
    ],
    guides: [
      {
        id: 'first',
        title: '设置入门',
        steps: [
          {
            target: 'view.editor.note',
            text: '先填写备注',
            chapter: '填写备注',
            example: { note: '演示备注' },
          },
          { target: 'view.editor.save', text: '检查后保存', chapter: '保存设置' },
        ],
        demo: { config: { note: '合成配置' }, actions: { save: { saved: 'synthetic' } } },
      },
    ],
  },
};

beforeEach(() => vi.clearAllMocks());

async function connect(frame: HTMLIFrameElement) {
  const source = frame.contentWindow!;
  const messages: Array<Record<string, unknown>> = [];
  vi.spyOn(source, 'postMessage').mockImplementation((message) => {
    messages.push(message);
  });
  let counter = 0;
  let session = '';
  const send = (method: string, params: unknown = {}, requestId = 'request-' + ++counter) => {
    act(() =>
      window.dispatchEvent(
        new MessageEvent('message', {
          source,
          data: {
            channel: 'neobot-plugin-view',
            version: 1,
            kind: 'request',
            requestId,
            method,
            params,
            session,
          },
        }),
      ),
    );
    return requestId;
  };
  const response = async (requestId: string) => {
    await waitFor(() =>
      expect(
        messages.find((message) => message.kind === 'response' && message.requestId === requestId),
      ).toBeDefined(),
    );
    return messages.find((message) => message.kind === 'response' && message.requestId === requestId)!;
  };
  const ready = await response(send('ready'));
  session = String(ready.session);
  return {
    messages,
    send,
    response,
    request: async (method: string, params?: unknown) => response(send(method, params)),
  };
}

function liveProps() {
  return {
    pluginId: 'demo',
    view,
    surface,
    run: vi.fn().mockResolvedValue({ ok: true, result: { saved: 'live' } }),
    onNavigate: vi.fn(),
    configAccess: {
      get: vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        error: null,
        data: {
          revision: '00000000000000000000000000000007',
          config: { note: '已保存' },
          source: '不发给iframe',
          path: '配置磁盘路径',
        },
      }),
      save: vi.fn(),
    },
  };
}
async function renderLive() {
  const props = liveProps();
  const rendered = render(<PluginViewFrame {...props} />);
  const frame = screen.getByTitle<HTMLIFrameElement>('插件设置');
  const bridge = await connect(frame);
  return { ...rendered, props, frame, bridge };
}

describe('内部页面桥接与说明书演示隔离', () => {
  it('页面卸载后在途操作完成仍反馈一次，避免已销毁窗口接收结果', async () => {
    const test = await renderLive();
    let finish!: (value: unknown) => void;
    test.props.run.mockReturnValueOnce(
      new Promise((resolve) => {
        finish = resolve;
      }),
    );
    test.bridge.send('action', { id: 'save', values: {} });
    await waitFor(() => expect(test.props.run).toHaveBeenCalledTimes(1));
    test.unmount();
    await act(async () => finish({ ok: true, result: { saved: true } }));
    await waitFor(() => expect(infoBar).toHaveBeenCalledTimes(1));
    expect(infoBar).toHaveBeenLastCalledWith(
      expect.objectContaining({ title: '保存记录执行完成', tone: 'ok' }),
    );
    expect(test.bridge.messages.filter((message) => message.kind === 'response')).toHaveLength(1);
  });

  it('动作失败由页面发布一次InfoBar，桥接不重复通知', async () => {
    const test = await renderLive();
    test.props.run.mockResolvedValueOnce({ ok: false, error: '内容无效', code: 'invalid_input' });
    expect(await test.bridge.request('action', { id: 'save', values: {} })).toMatchObject({
      error: { code: 'invalid_input', message: '内容无效' },
    });
    expect(infoBar).not.toHaveBeenCalled();
    await test.bridge.request('notify', { title: '保存失败', message: '内容无效', tone: 'err' });
    expect(infoBar).toHaveBeenCalledTimes(1);
    expect(infoBar).toHaveBeenLastCalledWith({ title: '保存失败', message: '内容无效', tone: 'err' });
  });

  it('相同说明对象刷新不重播旧步骤，显式切步和定位请求仍发送', async () => {
    const props = liveProps();
    const initial = surface.contract.guides[0].steps[0];
    const test = render(
      <PluginViewFrame {...props} step={initial} locate={initial.target} locateRequest={1} />,
    );
    const frame = screen.getByTitle<HTMLIFrameElement>('插件设置');
    const bridge = await connect(frame);
    const guidance = () =>
      bridge.messages.filter(
        (message) => message.kind === 'event' && (message.name === 'guide-step' || message.name === 'locate'),
      );
    expect(guidance()).toHaveLength(2);
    bridge.messages.length = 0;
    const refreshed = structuredClone(surface);
    test.rerender(
      <PluginViewFrame
        {...props}
        surface={refreshed}
        view={{ ...view }}
        step={refreshed.contract.guides[0].steps[0]}
        locate={initial.target}
        locateRequest={1}
      />,
    );
    expect(screen.getByTitle('插件设置')).toBe(frame);
    expect(guidance()).toEqual([]);
    const next = refreshed.contract.guides[0].steps[1];
    test.rerender(
      <PluginViewFrame {...props} surface={refreshed} step={next} locate={next.target} locateRequest={2} />,
    );
    expect(guidance()).toEqual([
      expect.objectContaining({
        name: 'guide-step',
        payload: expect.objectContaining({ target: next.target }),
      }),
      expect.objectContaining({ name: 'locate', payload: { target: next.target } }),
    ]);
    bridge.messages.length = 0;
    test.rerender(
      <PluginViewFrame
        {...props}
        surface={structuredClone(refreshed)}
        step={{ ...next }}
        locate={next.target}
        locateRequest={3}
      />,
    );
    expect(guidance()).toEqual([
      expect.objectContaining({ name: 'locate', payload: { target: next.target } }),
    ]);
  });

  it('新 iframe 握手接收当前步骤，旧窗口无法调用新窗口动作', async () => {
    const props = liveProps();
    const step = surface.contract.guides[0].steps[0];
    const test = render(
      <PluginViewFrame key={view.url} {...props} step={step} locate={step.target} locateRequest={1} />,
    );
    const initial = screen.getByTitle<HTMLIFrameElement>('插件设置');
    const old = await connect(initial);
    const changed = { ...view, url: '/plugins-ui/demo/editor/?revision=two' };
    test.rerender(
      <PluginViewFrame
        key={changed.url}
        {...props}
        view={changed}
        step={{ ...step }}
        locate={step.target}
        locateRequest={1}
      />,
    );
    const fresh = screen.getByTitle<HTMLIFrameElement>('插件设置');
    expect(fresh).not.toBe(initial);
    old.send('action', { id: 'save', values: {} });
    expect(props.run).not.toHaveBeenCalled();
    const bridge = await connect(fresh);
    expect(bridge.messages).toContainEqual(
      expect.objectContaining({
        name: 'guide-step',
        payload: expect.objectContaining({ target: step.target }),
      }),
    );
    expect(bridge.messages).toContainEqual(
      expect.objectContaining({ name: 'locate', payload: { target: step.target } }),
    );
    expect(await bridge.request('action', { id: 'save', values: {} })).toMatchObject({
      result: { saved: 'live' },
    });
    expect(props.run).toHaveBeenCalledTimes(1);
  });

  it('资源更新无需父组件 key 也会隔离新会话与旧异步响应', async () => {
    const test = await renderLive();
    let finish!: (value: unknown) => void;
    test.props.run.mockReturnValueOnce(
      new Promise((resolve) => {
        finish = resolve;
      }),
    );
    test.bridge.send('action', { id: 'save', values: {} });
    await waitFor(() => expect(test.props.run).toHaveBeenCalledTimes(1));
    const changed = { ...view, url: '/plugins-ui/demo/editor/?revision=two' };
    test.rerender(<PluginViewFrame {...test.props} view={changed} />);
    const fresh = screen.getByTitle<HTMLIFrameElement>('插件设置');
    expect(fresh).not.toBe(test.frame);
    const bridge = await connect(fresh);
    test.bridge.send('action', { id: 'save', values: {} });
    await act(async () => finish({ ok: true, result: { saved: 'old' } }));
    expect(test.props.run).toHaveBeenCalledTimes(1);
    expect(test.bridge.messages.filter((message) => message.kind === 'response')).toHaveLength(1);
    expect(bridge.messages.filter((message) => message.kind === 'response')).toHaveLength(1);
    expect(await bridge.request('action', { id: 'save', values: {} })).toMatchObject({
      result: { saved: 'live' },
    });
    expect(test.props.run).toHaveBeenCalledTimes(2);
  });

  it('演示只读合成结果与配置，不能执行真实动作或保存真实配置', async () => {
    const run = vi.fn();
    render(
      <PluginViewFrame
        pluginId="demo"
        view={view}
        surface={surface}
        mode="demo"
        demo={surface.contract.guides[0].demo}
        step={surface.contract.guides[0].steps[0]}
        run={run}
        onNavigate={vi.fn()}
      />,
    );
    const frame = screen.getByTitle<HTMLIFrameElement>('插件设置');
    expect(frame).toHaveAttribute('sandbox', 'allow-scripts allow-forms');
    expect(frame).toHaveAttribute('referrerpolicy', 'no-referrer');
    const bridge = await connect(frame);
    expect(await bridge.request('action', { id: 'save', values: { note: '演示' } })).toMatchObject({
      result: { saved: 'synthetic' },
    });
    expect(await bridge.request('getConfig')).toMatchObject({
      result: { config: { note: '合成配置' }, revision: '' },
    });
    expect(await bridge.request('saveConfig', { values: {}, revision: '' })).toMatchObject({
      error: { code: 'demo_read_only' },
    });
    expect(run).not.toHaveBeenCalled();
  });

  it('隐藏内部页面拒绝新业务调用，恢复后仍使用同一窗口', async () => {
    const props = liveProps();
    const test = render(<PluginViewFrame {...props} suspended />);
    const frame = screen.getByTitle<HTMLIFrameElement>('插件设置');
    const bridge = await connect(frame);
    expect(await bridge.request('action', { id: 'save', values: {} })).toMatchObject({
      error: { code: 'view_suspended' },
    });
    expect(await bridge.request('saveConfig', { values: {}, revision: '' })).toMatchObject({
      error: { code: 'view_suspended' },
    });
    expect(props.run).not.toHaveBeenCalled();
    expect(props.configAccess.save).not.toHaveBeenCalled();
    test.rerender(<PluginViewFrame {...props} suspended={false} />);
    expect(screen.getByTitle('插件设置')).toBe(frame);
    expect(await bridge.request('action', { id: 'save', values: {} })).toMatchObject({
      result: { saved: 'live' },
    });
  });

  it('配置桥接保留不透明revision、冲突诊断及公开字段边界', async () => {
    const test = await renderLive();
    expect(await test.bridge.request('getConfig')).toMatchObject({
      result: { config: { note: '已保存' }, revision: '00000000000000000000000000000007' },
    });
    expect(test.props.configAccess.get).toHaveBeenCalledTimes(1);
    test.props.configAccess.save.mockResolvedValueOnce({
      ok: false,
      status: 409,
      data: null,
      error: '文件版本已变化',
    });
    expect(
      await test.bridge.request('saveConfig', {
        values: { note: '我的草稿' },
        revision: '00000000000000000000000000000007',
      }),
    ).toMatchObject({ error: { code: 'config_conflict', status: 409, message: '文件版本已变化' } });
    expect(test.props.configAccess.save).toHaveBeenCalledWith(
      { note: '我的草稿' },
      '00000000000000000000000000000007',
    );
    expect(JSON.stringify(test.bridge.messages)).not.toMatch(/不发给iframe|配置磁盘路径|csrf|token/i);
  });
});
