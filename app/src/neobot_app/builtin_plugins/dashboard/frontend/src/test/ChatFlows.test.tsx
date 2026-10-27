// ChatFlows.test.tsx —— 聊天流页（spec(3) 建立 / spec(10) 改纯内存）：display_name、
// 完整提示词（未截断）、逐份 diff 与图片哈希、历史切换、清空、快速预览
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ChatFlows from '../pages/ChatFlows';
import { api } from '../api/endpoints';
import { clearQueries } from '../data/queryCore';
import { POLL } from '../data/queryKeys';
import { useAuthGate } from '../auth/AuthContext';

vi.mock('../auth/AuthContext', () => ({ useAuthGate: vi.fn() }));

vi.mock('../api/endpoints', () => ({
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

/** 默认是内存快照；需要看完整提示词时先切到「完整提示词」tab。 */
async function openFullTab(): Promise<void> {
  await screen.findByText(/共 7 条，快照只保留最近 3 条/);
  fireEvent.click(screen.getByRole('tab', { name: /完整提示词/ }));
  await screen.findByText('完整的系统提示词');
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
  vi.mocked(useAuthGate).mockReturnValue({ canManage: true, setupRequired: false, refresh: async () => {} });
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
  it('只读会话禁用清空历史，保留聊天流与完整提示词查看', async () => {
    vi.mocked(useAuthGate).mockReturnValue({
      canManage: false,
      setupRequired: false,
      refresh: async () => {},
    });
    render(<ChatFlows />);
    await openFullTab();
    expect(screen.getByText(/^当前会话只读/)).toBeInTheDocument();
    const clear = screen.getByRole('button', { name: '清空提示词历史' });
    expect(clear).toBeDisabled();
    fireEvent.click(clear);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(chatFlowPromptClear).not.toHaveBeenCalled();
    expect(screen.getByText('完整的系统提示词')).toBeInTheDocument();
    expect(screen.getByLabelText('只看当前聊天流')).toBeEnabled();
  });

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

  it('默认展示内存快照（快速预览），而不是历史备份', async () => {
    render(<ChatFlows />);

    await waitFor(() => expect(chatFlowDetail).toHaveBeenCalledWith('group:888'));
    expect((await screen.findAllByText('系统提示词原文')).length).toBeGreaterThan(0);
    expect(screen.getByRole('tab', { name: /快速预览/ })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByText('send_reply')).toBeInTheDocument();
    expect(screen.getByText(/共 7 条，快照只保留最近 3 条/)).toBeInTheDocument();
  });

  it('每 5 秒自动跟随最新一份：一轮结束后换成该轮最后一份提示词（无需手动刷新）', async () => {
    vi.useFakeTimers();
    try {
      render(<ChatFlows />);
      await settle();
      expect(screen.getByText(/共 7 条，快照只保留最近 3 条/)).toBeInTheDocument();
      fireEvent.click(screen.getByRole('tab', { name: /完整提示词/ }));
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
    await openFullTab();

    await user.click(screen.getByRole('button', { name: /#7/ }));
    await screen.findByText('更早一份的完整提示词');
    // 不再顶着「实时」标记，而是给出回到最新的入口
    expect(screen.queryByRole('status', { name: /已跟随最新一份/ })).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /回到最新一份/ }));
    await waitFor(() => expect(screen.getByText('完整的系统提示词')).toBeInTheDocument());
    expect(screen.getByRole('status', { name: '已跟随最新一份（#8）' })).toBeInTheDocument();
  });

  it('切换到历史里的其它份时才请求全量接口', async () => {
    const user = userEvent.setup();
    render(<ChatFlows />);
    await openFullTab();

    await user.click(screen.getByRole('button', { name: /#7/ }));

    await waitFor(() => expect(chatFlowPrompt).toHaveBeenCalledWith(7));
    expect(await screen.findByText('更早一份的完整提示词')).toBeInTheDocument();
  });

  it('保留「最近 80 条快速预览」：不读盘、来自内存快照', async () => {
    const user = userEvent.setup();
    render(<ChatFlows />);
    await screen.findByText(/共 7 条，快照只保留最近 3 条/);

    await user.click(screen.getByRole('tab', { name: /快速预览/ }));

    expect(screen.getAllByText('系统提示词原文').length).toBeGreaterThan(0);
    expect(screen.getByText('send_reply')).toBeInTheDocument();
    expect(screen.getByText(/共 7 条，快照只保留最近 3 条/)).toBeInTheDocument();
    expect(screen.getByText(/已截断/)).toBeInTheDocument();

    expect(screen.queryByText('active_task')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /后台任务/ }));
    const tasks = within(screen.getByRole('dialog', { name: '后台任务' }));
    expect(tasks.getByRole('heading', { name: '绘图任务' })).toBeInTheDocument();
    expect(tasks.getByRole('heading', { name: 'd-1' })).toBeInTheDocument();
    expect(tasks.getByText('待发送提醒').nextElementSibling).toHaveTextContent('0 条');
    const rawTasks = tasks.getByText('原始数据').closest('details')!;
    expect(rawTasks).not.toHaveAttribute('open');
    await user.click(tasks.getByText('原始数据'));
    expect(rawTasks).toHaveAttribute('open');
    expect(tasks.getByText(/"task_id": "d-1"/)).toBeInTheDocument();
  });

  it('system 消息默认折叠，展开或独立查看时仍保留完整内容', async () => {
    const user = userEvent.setup();
    render(<ChatFlows />);
    const system = await screen.findByText('系统提示词原文');
    expect(system).not.toBeVisible();
    await user.click(screen.getByText('展开 system 指令'));
    expect(system).toBeVisible();

    await user.click(screen.getByRole('button', { name: /system 提示词/ }));
    const context = within(screen.getByRole('dialog', { name: '最新 system 提示词' }));
    expect(context.getByText('系统提示词原文')).toBeVisible();
    expect(context.getByText(/12 字符/)).toBeInTheDocument();
    await user.click(context.getByRole('button', { name: '关闭对话框' }));
    expect(screen.getByText('send_reply')).toBeInTheDocument();
  });

  it('会话元信息通过独立入口可读，保留模型、迭代与消息统计', async () => {
    const user = userEvent.setup();
    render(<ChatFlows />);
    await screen.findByRole('heading', { name: '测试群' });
    await user.click(screen.getByRole('button', { name: '查看会话信息' }));
    const info = within(screen.getByRole('dialog', { name: '会话信息' }));
    expect(info.getByText('group:888')).toBeVisible();
    expect(info.getByText('deepseek-chat')).toBeVisible();
    expect(info.getByText('迭代').nextElementSibling).toHaveTextContent('3');
    expect(info.getByText('请求消息总数').nextElementSibling).toHaveTextContent('7');
    expect(info.getByText('system 字符数').nextElementSibling).toHaveTextContent('12');
  });

  it('完整提示词正文不截断，调用信息、原始参数与返回均可展开查看', async () => {
    const user = userEvent.setup();
    render(<ChatFlows />);
    await openFullTab();
    const messages = within(screen.getByRole('list', { name: '完整请求消息' }));
    expect(messages.getByText(LONG_TEXT)).toHaveTextContent(LONG_TEXT);
    const rawSummary = messages.getAllByText(/原始 JSON/)[2];
    await user.click(rawSummary);
    expect(messages.getByText(/完整参数/)).toBeVisible();
    await user.click(screen.getByText('response（模型原始返回）'));
    expect(screen.getByText(/"content": "模型原始返回"/)).toBeVisible();
    await user.click(screen.getByText('usage 与其它元数据'));
    expect(screen.getByText(/"prompt_tokens": 100/)).toBeVisible();

    await user.click(screen.getByRole('button', { name: '调用信息' }));
    const info = within(screen.getByRole('dialog', { name: '调用信息' }));
    expect(info.getByText('总字符数').nextElementSibling).toHaveTextContent('30');
    expect(info.getByText('估算 Token').nextElementSibling).toHaveTextContent('40');
    expect(info.getByText('输出字符数').nextElementSibling).toHaveTextContent('5');
    expect(info.getByText('迭代').nextElementSibling).toHaveTextContent('2');
  });

  it('选中的历史正文读取失败时可原位重试，页头不再放刷新按钮', async () => {
    const user = userEvent.setup();
    render(<ChatFlows />);
    await openFullTab();
    chatFlowPrompt.mockResolvedValueOnce(null);
    await user.click(screen.getByRole('button', { name: /#7/ }));
    await screen.findByText('读取完整提示词失败：seq=7');
    const before = chatFlowPrompt.mock.calls.length;
    let finish!: (value: Awaited<ReturnType<typeof api.chatFlowPrompt>>) => void;
    chatFlowPrompt.mockReturnValueOnce(
      new Promise((resolve) => {
        finish = resolve;
      }),
    );
    expect(screen.queryByRole('button', { name: '刷新' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '重新读取' }));
    await act(async () => {
      finish({ ok: true, seq: 7, entry: OLD_ENTRY });
    });
    await screen.findByText('更早一份的完整提示词');
    expect(chatFlowPrompt.mock.calls.length).toBe(before + 1);
    expect(screen.getByText('更早一份的完整提示词')).toBeInTheDocument();
  });

  it('窄屏能往返会话列表、提示词历史与正文并转移焦点', async () => {
    const user = userEvent.setup();
    const original = window.matchMedia;
    const media = vi.spyOn(window, 'matchMedia').mockImplementation((query) => ({
      ...original(query),
      matches: query === '(max-width: 760px)' || query === '(max-width: 1100px)',
    }));
    try {
      render(<ChatFlows />);
      await screen.findByRole('heading', { name: '测试群' });
      await user.click(screen.getByRole('button', { name: /测试群/ }));
      expect(screen.getByRole('region', { name: '聊天流详情' })).toHaveFocus();
      await user.click(screen.getByRole('tab', { name: '完整提示词' }));
      await screen.findByText('完整的系统提示词');
      await user.click(screen.getByRole('button', { name: '历史记录' }));
      expect(screen.getByText('提示词历史').parentElement?.parentElement).toHaveFocus();
      await user.click(screen.getByRole('button', { name: '查看记录 8 的详情' }));
      expect(screen.getByLabelText('记录 8 的详情')).toHaveTextContent('512 B');
      expect(chatFlowPrompt).not.toHaveBeenCalled();
      await user.click(screen.getByRole('button', { name: '返回正文' }));
      expect(screen.getByLabelText('完整提示词正文')).toHaveFocus();
      expect(screen.getByText(LONG_TEXT)).toHaveTextContent(LONG_TEXT);
      await user.click(screen.getByRole('button', { name: '历史记录' }));
      expect(screen.getByRole('button', { name: '查看记录 8 的详情' })).toHaveAttribute(
        'aria-expanded',
        'true',
      );
      await user.click(screen.getByRole('button', { name: /#7/ }));
      await screen.findByText('更早一份的完整提示词');
      expect(screen.getByLabelText('完整提示词正文')).toHaveFocus();
      await user.click(screen.getByRole('button', { name: '返回会话列表' }));
      expect(screen.getByRole('list', { name: '聊天流记录' })).toHaveFocus();
    } finally {
      media.mockRestore();
    }
  });

  it('清空提示词历史需要二次确认（勾选后才能提交）', async () => {
    const user = userEvent.setup();
    render(<ChatFlows />);
    await screen.findByText(/共 7 条，快照只保留最近 3 条/);

    await user.click(screen.getByRole('button', { name: /清空提示词历史/ }));

    const confirm = screen.getByRole('button', { name: /确认清空/ });
    expect(confirm).toBeDisabled();
    expect(screen.getByText(/清空后不可恢复/)).toBeInTheDocument();

    await user.click(screen.getByLabelText(/我已确认：清空后这些完整聊天记录无法恢复/));
    await user.click(screen.getByRole('button', { name: /确认清空/ }));

    await waitFor(() => expect(chatFlowPromptClear).toHaveBeenCalledTimes(1));
  });

  it('文案说明纯内存 + 逐份 diff + 图片哈希，并保留隐私提示', async () => {
    const user = userEvent.setup();
    render(<ChatFlows />);
    await screen.findByText(/共 7 条，快照只保留最近 3 条/);

    expect(screen.getByRole('button', { name: '隐私与记录说明' })).toHaveTextContent('隐私与记录');
    expect(screen.queryByText(/完整提示词也只存在内存里/)).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '隐私与记录说明' }));
    const help = within(screen.getByRole('dialog', { name: '隐私与记录说明' }));
    expect(help.getByText(/完整提示词也只存在内存里/)).toBeInTheDocument();
    expect(help.getByText(/逐份只存相对上一份的 diff/)).toBeInTheDocument();
    expect(help.getByText(/图片只保留 sha256 哈希/)).toBeInTheDocument();
    expect(help.getByText(/属隐私数据/)).toBeInTheDocument();
    expect(help.getByText(/单条上限 4000 字符/)).toBeInTheDocument();
  });

  it('记录详情按需展示完整篇幅、逐份驻留和图片引用，展开不切换正文', async () => {
    const user = userEvent.setup();
    render(<ChatFlows />);
    await openFullTab();

    expect(screen.queryByLabelText('记录 8 的详情')).not.toBeInTheDocument();
    expect(screen.queryByText('驻留补丁')).not.toBeInTheDocument();
    const inspect = screen.getByRole('button', { name: '查看记录 8 的详情' });
    expect(inspect).toHaveAttribute('aria-expanded', 'false');
    await user.click(inspect);
    const details = within(screen.getByLabelText('记录 8 的详情'));
    expect(details.getByText('完整篇幅').nextElementSibling).toHaveTextContent('4.0 KB');
    expect(details.getByText('驻留补丁').nextElementSibling).toHaveTextContent('512 B');
    expect(details.getByText('图片引用').nextElementSibling).toHaveTextContent('1 个');
    expect(details.getByText('模型').nextElementSibling).toHaveTextContent('deepseek-chat');
    expect(details.getByText('聊天流').nextElementSibling).toHaveTextContent('group:888');
    expect(details.getByText('记录时间').nextElementSibling).toHaveTextContent('2026-09-12 10:05:00');
    expect(screen.getByText('完整的系统提示词')).toBeInTheDocument();
    expect(chatFlowPrompt).not.toHaveBeenCalled();
    expect(inspect).toHaveAttribute('aria-expanded', 'true');
    await user.click(inspect);
    expect(screen.queryByLabelText('记录 8 的详情')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '隐私与记录说明' }));
    expect(within(screen.getByRole('dialog')).getByText(/常驻 6\.0 KB/)).toBeInTheDocument();
  });

  it('同日记录共用日期分隔，当前记录与最新记录各自标明', async () => {
    const user = userEvent.setup();
    chatFlowPromptLatest.mockResolvedValue({
      ...PROMPTS,
      seq: 9,
      items: [...PROMPTS.items, { ...PROMPTS.items[1], seq: 9, recorded_at: '2026-09-13T09:00:00' }],
      entry: { ...PROMPTS.entry, recorded_at: '2026-09-13T09:00:00' },
    });
    render(<ChatFlows />);
    await openFullTab();
    const history = within(screen.getByRole('list', { name: '提示词历史记录' }));
    expect(history.getAllByText('2026-09-12')).toHaveLength(1);
    expect(history.getAllByText('2026-09-13')).toHaveLength(1);
    expect(history.getByRole('button', { name: /#9 09:00:00 当前记录 最新记录/ })).toHaveAttribute(
      'aria-current',
      'true',
    );

    await user.click(history.getByRole('button', { name: /#7/ }));
    await screen.findByText('更早一份的完整提示词');
    const current = history.getByRole('button', { name: /#7 10:00:00 当前记录/ });
    expect(current).toHaveAttribute('aria-current', 'true');
    expect(current).toHaveTextContent('2 条消息迭代 1');
    expect(history.getByRole('button', { name: /#9 09:00:00 最新记录/ })).toHaveAttribute(
      'aria-current',
      'false',
    );
    expect(history.getByText('当前')).toBeInTheDocument();
    expect(history.getByText('最新')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '回到最新一份（#9）' })).toBeInTheDocument();
  });

  it('取消当前会话筛选后保留跨会话标识和完整记录入口', async () => {
    const user = userEvent.setup();
    const other = { ...PROMPTS.items[0], seq: 6, pipeline_key: 'private:10001' };
    chatFlowPromptLatest.mockImplementation(async (key) =>
      key ? PROMPTS : { ...PROMPTS, items: [other, ...PROMPTS.items] },
    );
    render(<ChatFlows />);
    await openFullTab();
    const before = chatFlowPromptLatest.mock.calls.length;
    await user.click(screen.getByRole('checkbox', { name: '只看当前聊天流' }));
    await waitFor(() => expect(chatFlowPromptLatest.mock.calls.slice(before)).toContainEqual(['']));
    const history = within(screen.getByRole('list', { name: '提示词历史记录' }));
    expect(await history.findByRole('button', { name: /#6/ })).toHaveTextContent('private:10001');
    expect(history.getByRole('button', { name: /#8/ })).toHaveTextContent('group:888');
    expect(screen.getByRole('status', { name: '已跟随最新一份（#8）' })).toBeInTheDocument();
    expect(screen.getByText(LONG_TEXT)).toHaveTextContent(LONG_TEXT);
    await user.click(history.getByRole('button', { name: '查看记录 6 的详情' }));
    expect(screen.getByLabelText('记录 6 的详情')).toHaveTextContent('private:10001');
    expect(chatFlowPrompt).not.toHaveBeenCalled();
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
