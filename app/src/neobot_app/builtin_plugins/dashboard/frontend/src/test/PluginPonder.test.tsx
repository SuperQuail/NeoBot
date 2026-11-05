import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../api/endpoints';
import type { PluginViewSurface } from '../pages/plugins/pluginViewBridge';
import PluginPonderPlayer from '../pages/plugins/PluginPonderPlayer';
import { infoBar } from '../notifications/infoBar';

vi.mock('../api/endpoints', () => ({ api: { pluginAction: vi.fn(), pluginConfigSave: vi.fn() } }));
vi.mock('../notifications/infoBar', () => ({ infoBar: vi.fn() }));

const surface: PluginViewSurface = {
  available: true,
  source: 'runtime',
  state: 'running',
  permissions: ['read', 'manage'],
  contract: {
    schema_version: 1,
    plugin: { name: 'demo' },
    config: null,
    resources: [],
    actions: [
      {
        id: 'save',
        title: '保存数字',
        permission: 'manage',
        input_schema: {
          type: 'object',
          properties: { count: { type: 'integer', title: '数字', default: 1 } },
        },
        output_schema: null,
      },
      { id: 'ready', title: '查看完成状态', permission: 'read', input_schema: null, output_schema: null },
    ],
    guides: [
      {
        id: 'first',
        title: '第一次设置',
        completion_action: 'ready',
        steps: [
          { target: 'action.save', text: '先填写一个数字。', chapter: '填写数字', example: { count: 3 } },
          { target: 'action.save', text: '确认后再保存。', chapter: '保存记录', example: { count: 4 } },
        ],
        demo: { actions: { save: { saved: true } } },
      },
    ],
  },
};
function props() {
  return {
    pluginId: 'demo',
    surface,
    guide: surface.contract.guides[0],
    guides: surface.contract.guides,
    views: [],
    onClose: vi.fn(),
    onGuideChange: vi.fn(),
  };
}
function caption(text: string) {
  return screen.getByText(text, { selector: '.ponder-caption p' });
}
beforeEach(() => vi.clearAllMocks());

describe('思索说明书播放器', () => {
  it('进入独立的整屏舞台，章节只出现在分段时间线上', () => {
    render(<PluginPonderPlayer {...props()} />);
    const stage = screen.getByRole('dialog', { name: 'demo · 思索说明书' });
    expect(stage).toHaveClass('ponder-screen');
    expect(stage).not.toHaveClass('modal');
    expect(screen.getByRole('navigation', { name: '思索章节' })).toHaveClass('ponder-timeline');
    expect(screen.getByRole('button', { name: '返回配置' })).toBeVisible();
    expect(screen.getByRole('button', { name: '播放演示' })).toHaveFocus();
  });

  it('首次打开默认手动阅读，不随时间自动跳走', async () => {
    vi.useFakeTimers();
    try {
      render(<PluginPonderPlayer {...props()} />);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(30000);
      });
      expect(caption('先填写一个数字。')).toBeVisible();
      expect(screen.getByRole('button', { name: '播放演示' })).toBeVisible();
      expect(api.pluginAction).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it('键盘回看和切章暂停在目标，空格恢复播放，组合键不触发跳转', () => {
    const value = props();
    const guide = {
      ...value.guide,
      steps: [
        value.guide.steps[0],
        { ...value.guide.steps[0], text: '同章第二个步骤。' },
        value.guide.steps[1],
      ],
    };
    render(<PluginPonderPlayer {...value} guide={guide} guides={[guide]} />);
    const stage = screen.getByRole('dialog');
    fireEvent.keyDown(stage, { key: 'ArrowRight', ctrlKey: true });
    expect(caption('先填写一个数字。')).toBeVisible();
    fireEvent.keyDown(stage, { key: 'ArrowRight' });
    expect(caption('同章第二个步骤。')).toBeVisible();
    expect(screen.getByRole('button', { name: '播放演示' })).toBeVisible();
    fireEvent.keyDown(stage, { key: ']' });
    expect(caption('确认后再保存。')).toBeVisible();
    fireEvent.keyDown(stage, { key: '[' });
    expect(caption('先填写一个数字。')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: '回看第 2 步' }));
    expect(caption('同章第二个步骤。')).toBeVisible();
    fireEvent.keyDown(stage, { key: ' ' });
    expect(screen.getByRole('button', { name: '暂停演示' })).toBeVisible();
    expect(api.pluginAction).not.toHaveBeenCalled();
  });

  it('暂停保留字幕剩余时长，恢复后不从头计时', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'Date', 'performance'] });
    try {
      render(<PluginPonderPlayer {...props()} />);
      fireEvent.click(screen.getByRole('button', { name: '播放演示' }));
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000);
      });
      fireEvent.click(screen.getByRole('button', { name: '暂停演示' }));
      await act(async () => {
        await vi.advanceTimersByTimeAsync(10000);
      });
      expect(caption('先填写一个数字。')).toBeVisible();
      fireEvent.click(screen.getByRole('button', { name: '播放演示' }));
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1600);
      });
      expect(caption('确认后再保存。')).toBeVisible();
    } finally {
      vi.useRealTimers();
    }
  });

  it('重播从当前章开始，切换说明后重新开始并保持同一个整屏容器', () => {
    const value = props();
    const view = render(<PluginPonderPlayer {...value} />);
    const stage = screen.getByRole('dialog');
    fireEvent.click(screen.getByRole('button', { name: '02 保存记录' }));
    fireEvent.click(screen.getByRole('button', { name: '重新播放' }));
    expect(caption('确认后再保存。')).toBeVisible();
    const second = {
      id: 'second',
      title: '第二篇',
      steps: [{ target: 'config.note', text: '新说明第一步。' }],
    };
    view.rerender(<PluginPonderPlayer {...value} guide={second} guides={[value.guide, second]} />);
    expect(screen.getByRole('dialog')).toBe(stage);
    expect(caption('新说明第一步。')).toBeVisible();
  });

  it('只有一份可回看的说明书，播放结束不执行真实动作或完成检查', () => {
    const value = props();
    render(<PluginPonderPlayer {...value} />);
    expect(screen.getAllByRole('dialog')).toHaveLength(1);
    expect(screen.getByRole('dialog', { name: 'demo · 思索说明书' })).toBeVisible();
    expect(screen.getByRole('navigation', { name: '思索章节' })).toBeVisible();
    expect(caption('先填写一个数字。')).toBeVisible();
    expect(screen.queryByRole('button', { name: '跟着做' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '检查是否完成' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '下一步演示' }));
    expect(caption('确认后再保存。')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: '下一步演示' }));
    expect(infoBar).toHaveBeenLastCalledWith(
      expect.objectContaining({ title: expect.stringMatching(/播放.*(完|结束)/), tone: 'info' }),
    );
    expect(api.pluginAction).not.toHaveBeenCalled();
    expect(api.pluginConfigSave).not.toHaveBeenCalled();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '关闭说明' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '返回配置' }));
    expect(value.onClose).toHaveBeenCalledTimes(1);
  });

  it('暂停后不推进，恢复播放按步骤推进，并可按章节回看', async () => {
    vi.useFakeTimers();
    try {
      render(<PluginPonderPlayer {...props()} />);
      fireEvent.click(screen.getByRole('button', { name: '播放演示' }));
      fireEvent.click(screen.getByRole('button', { name: '暂停演示' }));
      await act(async () => {
        await vi.advanceTimersByTimeAsync(9000);
      });
      expect(caption('先填写一个数字。')).toBeVisible();
      fireEvent.click(screen.getByRole('button', { name: '播放演示' }));
      await act(async () => {
        await vi.advanceTimersByTimeAsync(4000);
      });
      expect(caption('确认后再保存。')).toBeVisible();
      fireEvent.click(screen.getByRole('button', { name: '01 填写数字' }));
      expect(caption('先填写一个数字。')).toBeVisible();
      expect(api.pluginAction).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it('减少动态效果时不自动播放，仍能手动选择章节', () => {
    const original = window.matchMedia;
    vi.spyOn(window, 'matchMedia').mockImplementation((query) => ({ ...original(query), matches: true }));
    try {
      render(<PluginPonderPlayer {...props()} />);
      expect(screen.getByRole('button', { name: '播放演示' })).toBeVisible();
      expect(infoBar).toHaveBeenCalledWith(
        expect.objectContaining({ message: expect.stringContaining('已减少动态效果') }),
      );
      fireEvent.click(screen.getByRole('button', { name: '02 保存记录' }));
      expect(caption('确认后再保存。')).toBeVisible();
      expect(screen.queryByRole('button', { name: '跟着做' })).not.toBeInTheDocument();
      expect(api.pluginAction).not.toHaveBeenCalled();
    } finally {
      vi.mocked(window.matchMedia).mockRestore();
    }
  });

  it('相同章节的后台刷新不重置播放计时', async () => {
    vi.useFakeTimers();
    try {
      const value = props();
      const guide = structuredClone(value.guide);
      guide.steps[0].text = '请先填写数字。'.repeat(10);
      const view = render(<PluginPonderPlayer {...value} guide={guide} />);
      fireEvent.click(screen.getByRole('button', { name: '播放演示' }));
      await act(async () => {
        await vi.advanceTimersByTimeAsync(4000);
      });
      view.rerender(
        <PluginPonderPlayer
          {...value}
          guide={structuredClone(guide)}
          onClose={vi.fn()}
          onGuideChange={vi.fn()}
        />,
      );
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2500);
      });
      expect(caption('确认后再保存。')).toBeVisible();
      fireEvent.click(screen.getByRole('button', { name: '下一步演示' }));
      expect(infoBar).toHaveBeenLastCalledWith(
        expect.objectContaining({ title: expect.stringMatching(/播放.*(完|结束)/) }),
      );
    } finally {
      vi.useRealTimers();
    }
  });

  it('目录可阅读全文、搜索命令并回到对应步骤，打开目录暂停播放且不调用真实接口', () => {
    const value = props();
    const guide = {
      ...value.guide,
      steps: [
        value.guide.steps[0],
        {
          ...value.guide.steps[1],
          command: { text: '/核对 17', context: '在机器人私聊中发送', reply: '17' },
        },
      ],
    };
    render(<PluginPonderPlayer {...value} guide={guide} />);
    fireEvent.click(screen.getByRole('button', { name: '播放演示' }));
    const contents = screen.getByRole('button', { name: '目录与全文' });
    fireEvent.click(contents);
    expect(contents).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: '播放演示' })).toBeVisible();
    expect(screen.getByRole('region', { name: '说明目录与全文' })).toBeVisible();
    expect(screen.getByText('先填写一个数字。')).toBeVisible();
    expect(screen.getByText('确认后再保存。')).toBeVisible();
    const search = screen.getByRole('searchbox', { name: '搜索说明' });
    fireEvent.change(search, { target: { value: '不存在' } });
    expect(screen.getByText('没有匹配的说明，请换个关键词。')).toBeVisible();
    fireEvent.change(search, { target: { value: '/核对' } });
    expect(screen.queryByText('先填写一个数字。')).not.toBeInTheDocument();
    expect(screen.getByText('/核对 17')).toBeVisible();
    fireEvent.keyDown(search, { key: 'ArrowLeft' });
    expect(screen.getByRole('region', { name: '说明目录与全文' })).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: '查看第 2 步：保存记录' }));
    expect(caption('确认后再保存。')).toBeVisible();
    expect(screen.queryByRole('region', { name: '说明目录与全文' })).not.toBeInTheDocument();
    expect(contents).toHaveFocus();
    expect(screen.getAllByRole('dialog')).toHaveLength(1);
    expect(api.pluginAction).not.toHaveBeenCalled();
    expect(api.pluginConfigSave).not.toHaveBeenCalled();
  });

  it('连播为长说明及命令场景保留阅读时间，不再八秒强制切换', async () => {
    vi.useFakeTimers();
    try {
      const value = props();
      const guide = {
        ...value.guide,
        steps: [
          { ...value.guide.steps[0], command: { text: '/ping', context: '请先核对目标聊天。'.repeat(15) } },
          value.guide.steps[1],
        ],
      };
      render(<PluginPonderPlayer {...value} guide={guide} />);
      fireEvent.click(screen.getByRole('button', { name: '播放演示' }));
      await act(async () => {
        await vi.advanceTimersByTimeAsync(9000);
      });
      expect(caption('先填写一个数字。')).toBeVisible();
      await act(async () => {
        await vi.advanceTimersByTimeAsync(10000);
      });
      expect(caption('确认后再保存。')).toBeVisible();
    } finally {
      vi.useRealTimers();
    }
  });

  it('多份说明使用内部下拉切换，单份说明不增加选择控件', async () => {
    const value = props();
    const view = render(<PluginPonderPlayer {...value} />);
    expect(screen.queryByRole('combobox', { name: '选择说明' })).not.toBeInTheDocument();
    const second = {
      id: 'advanced',
      title: '更多说明',
      steps: [{ target: 'config.note', text: '更多配置说明。' }],
    };
    view.rerender(<PluginPonderPlayer {...value} guides={[value.guide, second]} />);
    await act(async () => {
      fireEvent.keyDown(screen.getByRole('combobox', { name: '选择说明' }), { key: 'ArrowDown' });
    });
    const option = screen.getByRole('option', { name: '更多说明' });
    await act(async () => {
      option.focus();
      fireEvent.keyDown(option, { key: 'Enter' });
    });
    expect(value.onGuideChange).toHaveBeenCalledWith('advanced');
    expect(screen.getAllByRole('dialog')).toHaveLength(1);
    expect(api.pluginAction).not.toHaveBeenCalled();
  });

  it('相同说明刷新删短步骤后仍保留弹窗，并将播放位置收回有效范围', () => {
    const value = props();
    const view = render(<PluginPonderPlayer {...value} />);
    fireEvent.click(screen.getByRole('button', { name: '02 保存记录' }));
    expect(caption('确认后再保存。')).toBeVisible();
    const shorter = { ...value.guide, steps: value.guide.steps.slice(0, 1) };
    view.rerender(<PluginPonderPlayer {...value} guide={shorter} guides={[shorter]} />);
    expect(screen.getByRole('dialog', { name: 'demo · 思索说明书' })).toBeVisible();
    expect(caption('先填写一个数字。')).toBeVisible();
    expect(screen.getByRole('slider', { name: '演示进度' })).toHaveValue('0');
    expect(screen.getByRole('slider', { name: '演示进度' })).toHaveAttribute('max', '0');
    expect(screen.getByRole('button', { name: '上一步演示' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '返回配置' }));
    expect(value.onClose).toHaveBeenCalledTimes(1);
    expect(api.pluginAction).not.toHaveBeenCalled();
    expect(api.pluginConfigSave).not.toHaveBeenCalled();
  });

  it('后台刷新清空说明步骤后保留可关闭的弹窗，不执行真实请求', () => {
    const value = props();
    const view = render(<PluginPonderPlayer {...value} />);
    const empty = { ...value.guide, steps: [] };
    view.rerender(<PluginPonderPlayer {...value} guide={empty} guides={[empty]} />);
    expect(screen.getAllByRole('dialog')).toHaveLength(1);
    expect(screen.getByRole('dialog', { name: 'demo · 思索说明书' })).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: '返回配置' }));
    expect(value.onClose).toHaveBeenCalledTimes(1);
    expect(api.pluginAction).not.toHaveBeenCalled();
    expect(api.pluginConfigSave).not.toHaveBeenCalled();
  });
});
