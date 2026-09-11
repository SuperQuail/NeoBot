// ChatFlows.test.tsx —— 聊天流页：列表、详情（提示词/消息/后台任务）、空态与不可用态
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import ChatFlows from '../pages/ChatFlows';
import { api } from '../api/endpoints';
import { clearQueries } from '../data/queryCore';

vi.mock('../api/endpoints.js', () => ({
  api: { chatFlows: vi.fn(), chatFlowDetail: vi.fn() },
}));

const chatFlows = vi.mocked(api.chatFlows);
const chatFlowDetail = vi.mocked(api.chatFlowDetail);

const LIST = {
  ok: true,
  items: [
    {
      pipeline_key: 'group:888',
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

beforeEach(() => {
  clearQueries();
  vi.clearAllMocks();
});

describe('ChatFlows', () => {
  it('列出聊天流并自动选中第一条，展示提示词/消息/后台任务', async () => {
    chatFlows.mockResolvedValue(LIST);
    chatFlowDetail.mockResolvedValue(DETAIL);
    render(<ChatFlows />);

    expect(await screen.findByText('group:888')).toBeInTheDocument();
    expect(screen.getByText('private:10001')).toBeInTheDocument();
    expect(screen.getByText('运行中')).toBeInTheDocument();
    expect(screen.getByText('1 小时前')).toBeInTheDocument();

    // 提示词同时出现在「最新 system 提示词」与消息列表的 system 条目里
    expect((await screen.findAllByText('系统提示词原文')).length).toBeGreaterThan(0);
    expect(screen.getByText('send_reply')).toBeInTheDocument();
    expect(screen.getByText('工具结果被截断')).toBeInTheDocument();
    expect(screen.getByText(/#3 · 800 字符 · 已截断/)).toBeInTheDocument();
    expect(screen.getByText(/active_task/)).toBeInTheDocument();
    expect(screen.getByText('共 7 条，显示最近 3 条')).toBeInTheDocument();
  });

  it('切换聊天流后按新 key 拉取详情', async () => {
    chatFlows.mockResolvedValue(LIST);
    chatFlowDetail.mockResolvedValue(DETAIL);
    render(<ChatFlows />);
    await screen.findByText('group:888');

    fireEvent.click(screen.getByRole('button', { name: /private:10001/ }));

    await vi.waitFor(() => expect(chatFlowDetail).toHaveBeenCalledWith('private:10001'));
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
