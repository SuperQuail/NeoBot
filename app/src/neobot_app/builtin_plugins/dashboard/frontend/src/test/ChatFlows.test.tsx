// ChatFlows.test.tsx —— 聊天流页（spec(3) 建立 / spec(10) 改纯内存）：display_name、
// 完整提示词（未截断）、逐份 diff 与图片哈希、历史切换、清空、快速预览
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ChatFlows from '../pages/ChatFlows';
import { api } from '../api/endpoints';
import { clearQueries } from '../data/queryCore';
import { POLL } from '../data/queryKeys';

vi.mock('../api/endpoints.js', () => ({
  api: {
    chatFlows: vi.fn(),
    chatFlowDetail: vi.fn(),
    chatFlowPromptLatest: vi.fn(),
    chatFlowPrompt: vi.fn(),
    chatFlowPromptClear: vi.fn(),
  },
}));

const chatFlows = vi.mocked(api.chatFlows);
const chatFlowDetail = vi.mocked(api.chatFlowDetail);
const chatFlowPromptLatest = vi.mocked(api.chatFlowPromptLatest);
const chatFlowPrompt = vi.mocked(api.chatFlowPrompt);
const chatFlowPromptClear = vi.mocked(api.chatFlowPromptClear);

/** 单条消息超过内存快照的 4000 字符上限，用于断言完整视图不截断 */
const LONG_TEXT = 'y'.repeat(4500);

/** 假定时器下把已排队的微任务链冲干净（组合请求是 await 两次） */
async function flushPromises(): Promise<void> {
  for (let i = 0; i < 20; i += 1) await Promise.resolve();
}

/** 假定时器下等待 React 把「取数 → 状态更新 → effect（含新 key 的取数）」跑完 */
async function settle(rounds = 4): Promise<void> {
  for (let i = 0; i < rounds; i += 1) {
    await act(async () => {
      await flushPromises();
    });
  }
}

const LIST = {
  ok: true,
  items: [
    {
      pipeline_key: 'group:888',
      display_name: '测试群',
      conversation_kind: 'group',
      conversation_id: '888',
      model: 'deepseek-chat',
      active: true,
      iterations: 3,
      message_count: 4,
      total_messages: 4,
      prompt_chars: 12,
      age_seconds: 12,
    },
    {
      pipeline_key: 'private:10001',
      display_name: '张三',
      conversation_kind: 'private',
      conversation_id: '10001',
      model: 'deepseek-chat',
      active: false,
      iterations: 1,
      message_count: 2,
      total_messages: 2,
      prompt_chars: 5,
      age_seconds: 4000,
    },
  ],
};

const DETAIL = {
  pipeline_key: 'group:888',
  display_name: '测试群',
  model: 'deepseek-chat',
  iterations: 3,
  message_count: 3,
  total_messages: 7,
  prompt_chars: 12,
  system_prompt: '系统提示词原文',
  messages: [
    { role: 'system', content: '系统提示词原文', chars: 12 },
    {
      role: 'assistant',
      content: '',
      chars: 0,
      tool_calls: [{ id: 'c1', name: 'send_reply', arguments: '{"text":"hi"}' }],
    },
    { role: 'tool', tool_call_id: 'c1', content: '工具结果被截断', truncated: true, chars: 800 },
  ],
  background_tasks: { scheduled_task_notifications_pending: 0, active_task: { task_id: 'd-1' } },
};

const PROMPTS = {
  items: [
    {
      seq: 7,
      pipeline_key: 'group:888',
      iteration: 1,
      model: 'deepseek-chat',
      total_messages: 2,
      bytes: 2048,
      patch_bytes: 0,
      images: 0,
      recorded_at: '2026-09-12T10:00:00',
    },
    {
      seq: 8,
      pipeline_key: 'group:888',
      iteration: 2,
      model: 'deepseek-chat',
      total_messages: 3,
      bytes: 4096,
      patch_bytes: 512,
      images: 1,
      recorded_at: '2026-09-12T10:05:00',
    },
  ],
  limit: 100,
  storage_bytes: 6144,
  image_refs: 1,
  seq: 8,
  entry: {
    recorded_at: '2026-09-12T10:05:00',
    stage: 'agent_model_call',
    mode: 'group',
    conversation_kind: 'group',
    conversation_id: '888',
    pipeline_key: 'group:888',
    iteration: 2,
    messages_count: 3,
    total_chars: 30,
    estimated_tokens: 40,
    output_chars: 5,
    usage: { prompt_tokens: 100, cache_hit_tokens: 20 },
    messages: [
      { role: 'system', content: '完整的系统提示词' },
      { role: 'user', content: LONG_TEXT },
      {
        role: 'assistant',
        content: '',
        tool_calls: [{ id: 'c9', name: 'send_reply', arguments: '{"text":"完整参数"}' }],
      },
    ],
    response: { content: '模型原始返回' },
  },
};

const OLD_ENTRY = {
  recorded_at: '2026-09-12T10:00:00',
  pipeline_key: 'group:888',
  iteration: 1,
  messages_count: 2,
  messages: [{ role: 'system', content: '更早一份的完整提示词' }],
  response: null,
};

beforeEach(() => {
  clearQueries();
  vi.clearAllMocks();
  chatFlows.mockResolvedValue(LIST);
  chatFlowDetail.mockResolvedValue(DETAIL);
  chatFlowPromptLatest.mockResolvedValue(PROMPTS);
  chatFlowPrompt.mockResolvedValue({ ok: true, seq: 7, entry: OLD_ENTRY });
  chatFlowPromptClear.mockResolvedValue({
    ok: true,
    data: { message: '已清空 2 份完整提示词历史' },
    error: null,
    status: 200,
  });
});

describe('ChatFlows', () => {
  it('列表与详情标题用 display_name，pipeline_key 作为副标题常驻', async () => {
    render(<ChatFlows />);

    // display_name（群名 / 昵称）出现在列表与详情标题
    expect(await screen.findByRole('heading', { name: '测试群' })).toBeInTheDocument();
    expect(screen.getByText('张三')).toBeInTheDocument();
    // pipeline_key 仍常驻（列表项 + 详情副标题）
    expect(screen.getAllByText('group:888').length).toBeGreaterThan(0);
    expect(screen.getByText('运行中')).toBeInTheDocument();
    expect(screen.getByText('1 小时前')).toBeInTheDocument();
  });

  it('默认展示最新一份完整提示词，且完整内容不截断', async () => {
    render(<ChatFlows />);

    // 默认按当前聊天流过滤，进入页面即请求最新一份
    await waitFor(() => expect(chatFlowPromptLatest).toHaveBeenCalledWith('group:888'));
    // 最新那一份不再重复请求全量接口（已随列表一起读回）
    expect(chatFlowPrompt).not.toHaveBeenCalled();

    expect(await screen.findByText('完整的系统提示词')).toBeInTheDocument();
    expect(screen.getByText(/^y{4500}$/)).toBeInTheDocument();
    expect(screen.getByText(/messages（3 条，完整未截断）/)).toBeInTheDocument();
    expect(screen.getAllByText(/迭代 2/).length).toBeGreaterThan(0);
    // 历史列表默认选中最新一份（#8）
    expect(screen.getByRole('button', { name: /#8/ })).toHaveAttribute('aria-current', 'true');
  });

  it('每 5 秒自动跟随最新一份：一轮结束后换成该轮最后一份提示词（无需手动刷新）', async () => {
    vi.useFakeTimers();
    try {
      render(<ChatFlows />);
      await settle();
      expect(screen.getByText('完整的系统提示词')).toBeInTheDocument();

      // 后端又记了一份（seq=9）：一轮对话跑完（回复已发出 / 被取消）后的那份提示词
      chatFlowPromptLatest.mockResolvedValue({
        ...PROMPTS,
        seq: 9,
        items: [...PROMPTS.items, { ...PROMPTS.items[1], seq: 9, recorded_at: '2026-09-12T10:09:00' }],
        entry: {
          ...PROMPTS.entry,
          iteration: 3,
          recorded_at: '2026-09-12T10:09:00',
          messages: [{ role: 'system', content: '那一轮结束后的完整提示词' }],
          response: { content: '这一轮的回复' },
        },
      });

      await act(async () => {
        await vi.advanceTimersByTimeAsync(POLL.chatFlowPrompts + 100);
      });
      await settle();

      expect(screen.getByText('那一轮结束后的完整提示词')).toBeInTheDocument();
      expect(screen.queryByText('完整的系统提示词')).not.toBeInTheDocument();
      expect(chatFlowPromptLatest.mock.calls.length).toBeGreaterThan(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it('手动翻到更早的一份时停在那一份，可一键回到最新', async () => {
    const user = userEvent.setup();
    render(<ChatFlows />);
    await screen.findByText('完整的系统提示词');

    await user.click(screen.getByRole('button', { name: /#7/ }));
    await screen.findByText('更早一份的完整提示词');
    // 不再顶着「实时」标记，而是给出回到最新的入口
    expect(screen.queryByText(/已跟随最新一份/)).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /回到最新一份/ }));
    await waitFor(() => expect(screen.getByText('完整的系统提示词')).toBeInTheDocument());
    expect(screen.getByText(/已跟随最新一份（#8）/)).toBeInTheDocument();
  });

  it('切换到历史里的其它份时才请求全量接口', async () => {
    const user = userEvent.setup();
    render(<ChatFlows />);
    await screen.findByText('完整的系统提示词');

    await user.click(screen.getByRole('button', { name: /#7/ }));

    await waitFor(() => expect(chatFlowPrompt).toHaveBeenCalledWith(7));
    expect(await screen.findByText('更早一份的完整提示词')).toBeInTheDocument();
  });

  it('保留「最近 80 条快速预览」：不读盘、来自内存快照', async () => {
    const user = userEvent.setup();
    render(<ChatFlows />);
    await screen.findByText('完整的系统提示词');

    await user.click(screen.getByRole('tab', { name: /快速预览/ }));

    expect(screen.getAllByText('系统提示词原文').length).toBeGreaterThan(0);
    expect(screen.getByText('send_reply')).toBeInTheDocument();
    expect(screen.getByText(/active_task/)).toBeInTheDocument();
    expect(screen.getByText(/共 7 条，快照只保留最近 3 条/)).toBeInTheDocument();
  });

  it('清空提示词历史需要二次确认（勾选后才能提交）', async () => {
    const user = userEvent.setup();
    render(<ChatFlows />);
    await screen.findByText('完整的系统提示词');

    await user.click(screen.getByRole('button', { name: /清空提示词历史/ }));

    const confirm = screen.getByRole('button', { name: /确认清空/ });
    expect(confirm).toBeDisabled();
    expect(screen.getByText(/清空后不可恢复/)).toBeInTheDocument();

    await user.click(screen.getByLabelText(/我已确认：清空后这些完整聊天记录无法恢复/));
    await user.click(screen.getByRole('button', { name: /确认清空/ }));

    await waitFor(() => expect(chatFlowPromptClear).toHaveBeenCalledTimes(1));
  });

  it('文案说明纯内存 + 逐份 diff + 图片哈希，并保留隐私提示', async () => {
    render(<ChatFlows />);
    await screen.findByText('完整的系统提示词');

    expect(screen.getByText(/完整提示词也只存在内存里/)).toBeInTheDocument();
    expect(screen.getByText(/逐份只存相对上一份的 diff/)).toBeInTheDocument();
    expect(screen.getByText(/图片只保留 sha256 哈希/)).toBeInTheDocument();
    expect(screen.getByText(/属隐私数据/)).toBeInTheDocument();
  });

  it('历史列表展示完整篇幅与逐份驻留成本', async () => {
    render(<ChatFlows />);
    await screen.findByText('完整的系统提示词');

    expect(screen.getByText(/常驻 6\.0 KB/)).toBeInTheDocument();
    expect(screen.getByText(/驻留 512 B/)).toBeInTheDocument();
    expect(screen.getByText(/图片 1/)).toBeInTheDocument();
  });

  it('切换聊天流后按新 key 拉取详情与提示词历史', async () => {
    const user = userEvent.setup();
    render(<ChatFlows />);
    await screen.findByRole('heading', { name: '测试群' });

    await user.click(screen.getByRole('button', { name: /张三/ }));

    await waitFor(() => expect(chatFlowDetail).toHaveBeenCalledWith('private:10001'));
    await waitFor(() => expect(chatFlowPromptLatest).toHaveBeenCalledWith('private:10001'));
  });

  it('没有记录时给出空态', async () => {
    chatFlows.mockResolvedValue({ ok: true, items: [] });
    render(<ChatFlows />);

    expect(await screen.findByText(/还没有聊天流记录/)).toBeInTheDocument();
  });

  it('登记处缺失时显示不可用态', async () => {
    chatFlows.mockResolvedValue({
      ok: false,
      error: '聊天流登记处不可用（未注入 chat_flow_registry）',
    });
    render(<ChatFlows />);

    expect(await screen.findByText('聊天流不可用')).toBeInTheDocument();
    expect(screen.getByText(/chat_flow_registry/)).toBeInTheDocument();
  });
});
