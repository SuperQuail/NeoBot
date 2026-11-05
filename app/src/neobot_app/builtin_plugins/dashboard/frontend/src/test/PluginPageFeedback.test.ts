import { afterEach, describe, expect, it, vi } from 'vitest';
import markup from '../../../../streaming_parser/web/subscriptions/index.html?raw';
import script from '../../../../streaming_parser/web/subscriptions/app.js?raw';

const cleanups: Array<() => void> = [];
afterEach(() => {
  cleanups.splice(0).forEach((cleanup) => cleanup());
  vi.useRealTimers();
});

async function pageFixture(polling = false, mode: 'live' | 'demo' = 'live') {
  const document = new DOMParser().parseFromString(markup, 'text/html');
  const context = { available: true, suspended: false, permissions: ['manage'], mode };
  const health = {
    running: true,
    subscriptions: 0,
    checked_at: null,
    error: '',
    message: '尚未添加订阅',
  };
  const settings = {
    group_id: 20001,
    card_style: 'minimal',
    ai_reply_live: false,
    ai_reply_live_end: false,
    default_push_live: true,
    default_push_live_end: true,
    inherited: false,
  };
  let guideListener: ((step: Record<string, unknown>) => void) | undefined;
  const notify = vi.fn().mockResolvedValue(null);
  const action = vi.fn(async (name: string): Promise<unknown> => {
    if (name === 'subscriptions.groups') return { items: [{ group_id: 20001, name: '测试群' }] };
    if (name === 'subscriptions.list') return { items: [] };
    if (name === 'subscriptions.health') return health;
    if (name === 'groups.settings.get') return { ...settings };
    throw new Error('预览服务暂不可用');
  });
  const sdk = {
    ready: () => Promise.resolve(context),
    action,
    notify,
    registerAnchor: () => () => {},
    onContext: () => () => {},
    onGuideStep: (listener: (step: Record<string, unknown>) => void) => {
      guideListener = listener;
      return () => {};
    },
  };
  let closePage = () => {};
  const root = {
    NeoBotPlugin: sdk,
    addEventListener: (name: string, listener: () => void) => {
      if (name === 'pagehide') closePage = listener;
    },
  };
  // 执行实际分发给插件 iframe 的脚本，隔离宿主窗口并停用定时轮询。
  new Function('window', 'document', 'Option', 'ResizeObserver', 'setTimeout', 'clearTimeout', script)(
    root,
    document,
    Option,
    class {
      observe() {}
      disconnect() {}
    },
    polling ? setTimeout : () => 1,
    polling ? clearTimeout : () => {},
  );
  cleanups.push(() => closePage());
  const button = (id: string) => document.getElementById(id) as HTMLButtonElement;
  const group = document.getElementById('group_id') as HTMLSelectElement;
  const target = document.getElementById('target-input') as HTMLInputElement;
  await vi.waitFor(() => expect(action).toHaveBeenCalledWith('subscriptions.groups', {}));
  if (mode === 'live') {
    await vi.waitFor(() => expect(action).toHaveBeenCalledWith('subscriptions.health', {}));
    await vi.waitFor(() => expect(button('show-preview').disabled).toBe(false));
  }
  return {
    document,
    notify,
    action,
    health,
    settings,
    button,
    group,
    target,
    guide: (example: Record<string, unknown>) =>
      guideListener?.({
        mode: 'demo',
        target: 'view.subscriptions.group',
        example,
      }),
  };
}

describe('插件页面操作反馈', () => {
  it.each(['group_id', 'target-input', 'refresh'])(
    '聚焦 %s 时后台刷新不禁用控件，失焦后恢复且手动刷新仍可用',
    async (id) => {
      vi.useFakeTimers();
      const page = await pageFixture(true);
      page.target.value = '尚未识别的直播间';
      const control = page.document.getElementById(id)!;
      const focused = vi.spyOn(page.document, 'hasFocus').mockReturnValue(true);
      const active = vi.spyOn(page.document, 'activeElement', 'get').mockReturnValue(control);
      page.action.mockClear();
      await vi.advanceTimersByTimeAsync(10000);
      expect(page.action).not.toHaveBeenCalled();
      expect(page.target.disabled).toBe(false);
      expect(page.group.disabled).toBe(false);
      expect(page.target.value).toBe('尚未识别的直播间');
      page.button('refresh').click();
      await vi.waitFor(() => expect(page.action).toHaveBeenCalledWith('subscriptions.health', {}));
      await vi.waitFor(() => expect(page.button('refresh').disabled).toBe(false));
      page.action.mockClear();
      focused.mockReturnValue(false);
      await vi.advanceTimersByTimeAsync(5000);
      expect(page.action).toHaveBeenCalledWith('subscriptions.list', {});
      active.mockRestore();
      focused.mockRestore();
    },
  );

  it('缺少直播间时只通知，不插入错误条或清空已选择的群', async () => {
    const page = await pageFixture();
    page.group.value = '20001';
    page.button('show-preview').click();
    await vi.waitFor(() =>
      expect(page.notify).toHaveBeenCalledWith({
        title: '操作未完成',
        message: '粘贴直播间链接或输入房间号。',
        tone: 'err',
      }),
    );
    expect(page.notify).toHaveBeenCalledTimes(1);
    expect(page.group.value).toBe('20001');
    expect(page.document.querySelector('[role="alert"]')).toBeNull();
    expect(page.document.body.textContent).not.toContain('粘贴直播间链接或输入房间号。');
    expect(page.action).not.toHaveBeenCalledWith('subscriptions.preview', expect.anything());
  });

  it('动作失败只通知一次，并保留用户填写的链接', async () => {
    const page = await pageFixture();
    page.group.value = '20001';
    page.target.value = 'https://live.bilibili.com/610001';
    page.button('show-preview').click();
    await vi.waitFor(() =>
      expect(page.notify).toHaveBeenCalledWith({
        title: '操作未完成',
        message: '预览服务暂不可用',
        tone: 'err',
      }),
    );
    expect(page.notify).toHaveBeenCalledTimes(1);
    expect(page.target.value).toBe('https://live.bilibili.com/610001');
    expect(page.document.body.textContent).not.toContain('预览服务暂不可用');
  });

  it.each([
    ['view_suspended', false],
    ['permission_denied', true],
  ] as const)('仅忽略明确暂停错误 %s，并保留当前草稿', async (code, shouldNotify) => {
    const page = await pageFixture();
    page.group.value = '20001';
    page.target.value = 'https://live.bilibili.com/610001';
    const error = Object.assign(new Error('页面正在演示，真实操作已暂停'), { code });
    page.action.mockRejectedValue(error);
    page.button('show-preview').click();
    await vi.waitFor(() =>
      expect(page.action).toHaveBeenCalledWith('subscriptions.preview', {
        group_id: 20001,
        target: 'https://live.bilibili.com/610001',
      }),
    );
    await vi.waitFor(() => expect(page.button('show-preview').disabled).toBe(false));
    expect(page.notify).toHaveBeenCalledTimes(shouldNotify ? 1 : 0);
    if (shouldNotify)
      expect(page.notify).toHaveBeenCalledWith({
        title: '操作未完成',
        message: error.message,
        tone: 'err',
      });
    expect(page.group.value).toBe('20001');
    expect(page.target.value).toBe('https://live.bilibili.com/610001');
  });

  it('重复的轮询错误不刷屏，错误变化时重新通知', async () => {
    const page = await pageFixture();
    page.health.error = '直播间读取超时';
    page.button('refresh').click();
    await vi.waitFor(() => expect(page.notify).toHaveBeenCalledTimes(1));
    await vi.waitFor(() => expect(page.button('refresh').disabled).toBe(false));
    page.button('refresh').click();
    await vi.waitFor(() => expect(page.button('refresh').disabled).toBe(false));
    expect(page.notify).toHaveBeenCalledTimes(1);
    page.health.error = '直播服务连接中断';
    page.button('refresh').click();
    await vi.waitFor(() => expect(page.notify).toHaveBeenCalledTimes(2));
    expect(page.document.getElementById('health')?.textContent).toBe('检查异常');
    expect(page.document.body.textContent).not.toContain('直播间读取超时');
    expect(page.document.body.textContent).not.toContain('直播服务连接中断');
  });

  it('定时刷新拒绝时去重，手动失败仍反馈，刷新恢复后同类错误重新通知', async () => {
    vi.useFakeTimers();
    const page = await pageFixture(true);
    page.action.mockRejectedValue(new Error('网络连接中断'));
    await vi.advanceTimersByTimeAsync(5000);
    expect(page.notify).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(5000);
    expect(page.notify).toHaveBeenCalledTimes(1);

    page.button('refresh').click();
    await vi.waitFor(() => expect(page.notify).toHaveBeenCalledTimes(2));
    await vi.waitFor(() => expect(page.button('refresh').disabled).toBe(false));
    page.button('refresh').click();
    await vi.waitFor(() => expect(page.notify).toHaveBeenCalledTimes(3));
    await vi.waitFor(() => expect(page.button('refresh').disabled).toBe(false));

    page.action.mockResolvedValueOnce({ items: [] }).mockResolvedValueOnce(page.health);
    await vi.advanceTimersByTimeAsync(5000);
    expect(page.action).toHaveBeenLastCalledWith('subscriptions.health', {});
    expect(page.notify).toHaveBeenCalledTimes(3);
    await vi.advanceTimersByTimeAsync(5000);
    expect(page.notify).toHaveBeenCalledTimes(4);
    expect(page.notify).toHaveBeenLastCalledWith({
      title: '操作未完成',
      message: '网络连接中断',
      tone: 'err',
    });
  });
  it('刷新得到不同的群设置后，旧预览失效且不能直接开始监听', async () => {
    const page = await pageFixture();
    page.group.value = '20001';
    page.group.dispatchEvent(new Event('change'));
    await vi.waitFor(() =>
      expect((page.document.getElementById('settings-style') as HTMLSelectElement).disabled).toBe(false),
    );
    const original = page.action.getMockImplementation()!;
    page.action.mockImplementation(async (name) =>
      name === 'subscriptions.preview'
        ? {
            target: { name: '演示主播', room_id: 610001 },
            style: 'minimal',
            html: '<p>原通知</p>',
            fallback_text: '原通知',
          }
        : original(name),
    );
    page.target.value = '1001';
    page.button('show-preview').click();
    await vi.waitFor(() => expect(page.button('subscribe').disabled).toBe(false));
    page.settings.card_style = 'neon';
    page.button('reload-groups').click();
    await vi.waitFor(() =>
      expect((page.document.getElementById('settings-style') as HTMLSelectElement).value).toBe('neon'),
    );
    expect(page.button('subscribe').disabled).toBe(true);
    expect((page.document.getElementById('preview-canvas') as HTMLElement).hidden).toBe(true);
    expect(page.target.value).toBe('1001');
  });

  it('教程退回初始表单时清空后续章节的群设置，而不是只清空群和链接', async () => {
    const page = await pageFixture(false, 'demo');
    page.guide({ group_id: 20001, target: '' });
    const style = page.document.getElementById('settings-style') as HTMLSelectElement;
    const push = page.document.getElementById('settings-push-live') as HTMLInputElement;
    await vi.waitFor(() => expect(style.value).toBe('minimal'));
    expect(push.checked).toBe(true);
    page.guide({ group_id: 0, target: '' });
    await vi.waitFor(() => expect(page.group.value).toBe(''));
    expect(style.value).toBe('random');
    expect(push.checked).toBe(false);
    expect(page.target.value).toBe('');
  });
});
