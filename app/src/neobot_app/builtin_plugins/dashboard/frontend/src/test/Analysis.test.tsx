// Analysis.test.tsx —— 分析页回归测试：总量渲染、展开提示词、单来源错误、不可用态
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import Analysis from '../pages/Analysis';
import { api } from '../api/endpoints';
import { clearQueries } from '../data/queryCore';
import type { PromptAnalysisPayload } from '../api/types';
import { POLL } from '../data/queryKeys';

vi.mock('../api/endpoints', () => ({
  api: { analysisPrompts: vi.fn() },
}));

const analysisPrompts = vi.mocked(api.analysisPrompts);

const PAYLOAD: PromptAnalysisPayload = {
  ok: true,
  available: true,
  rule: '估算口径：中文字符 × 0.6 + 其他字符 × 0.3（非真实计费 token）',
  generated_at: 1730000000,
  agents: [
    {
      name: '主 Agent（对话）',
      kind: 'agent',
      note: '空聊天（不含历史与记忆）',
      model: 'gpt-4o-mini',
      total_chars: 2000,
      total_tokens: 987.5,
      parts: [
        {
          label: '系统提示词（群聊 · 空聊天）',
          kind: 'system',
          chars: 1500,
          tokens: 750.5,
          truncated: false,
          text: '你是 NeoBot，负责群聊。',
        },
        {
          label: '工具定义（全部 skill 包）',
          kind: 'tools',
          chars: 500,
          tokens: 237.2,
          truncated: true,
          text: '工具清单：search、weather。',
        },
      ],
    },
  ],
};

beforeEach(() => {
  clearQueries();
});

describe('Analysis', () => {
  it('渲染 agent 名称 / note / 模型 / 总量，并展示接口返回的口径', async () => {
    analysisPrompts.mockResolvedValue(PAYLOAD);
    render(<Analysis />);

    expect(await screen.findByText('主 Agent（对话）')).toBeInTheDocument();
    expect(screen.getByText('空聊天（不含历史与记忆）')).toBeInTheDocument();
    expect(screen.getByText('gpt-4o-mini')).toBeInTheDocument();
    // 总字符数带千分位，token 保留 1 位小数
    expect(screen.getByText('2,000')).toBeInTheDocument();
    expect(screen.getByText('987.5')).toBeInTheDocument();
    // 口径说明来自接口，不在前端硬编码
    fireEvent.click(screen.getByRole('button', { name: '统计口径' }));
    expect(screen.getByText(/估算口径：中文字符/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '关闭对话框' }));
    // 中文 kind 标签与占比（1500/2000 = 75%）
    expect(screen.getByText('系统提示词')).toBeInTheDocument();
    expect(screen.getByText('工具定义')).toBeInTheDocument();
    expect(screen.getByText(/75\.0%/)).toBeInTheDocument();
    expect(screen.getByText(/25\.0%/)).toBeInTheDocument();
  });

  it('按需选择来源查看文本，切换来源保留截断说明', async () => {
    analysisPrompts.mockResolvedValue(PAYLOAD);
    render(<Analysis />);
    await screen.findByText('主 Agent（对话）');

    expect(screen.queryByText('你是 NeoBot，负责群聊。')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '查看 系统提示词（群聊 · 空聊天）' }));
    expect(screen.getByText('你是 NeoBot，负责群聊。')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '查看 工具定义（全部 skill 包）' }));
    expect(screen.getByText('工具清单：search、weather。')).toBeInTheDocument();
    expect(screen.getByText('已截断展示，统计按全文计算')).toBeInTheDocument();

    expect(screen.queryByText('你是 NeoBot，负责群聊。')).not.toBeInTheDocument();
  });

  it('单个 agent 装配失败时显示错误并跳过 parts / 合计', async () => {
    analysisPrompts.mockResolvedValue({
      ok: true,
      available: true,
      rule: '估算口径：略',
      agents: [
        { name: '工具 Agent', error: '装配失败：缺少模型配置', total_chars: 0, total_tokens: 0, parts: [] },
      ],
    });
    render(<Analysis />);

    expect(await screen.findByRole('combobox', { name: '选择 Agent' })).toHaveTextContent(
      '工具 Agent · 装配失败',
    );
    expect(screen.getByRole('alert')).toHaveTextContent('装配失败：缺少模型配置');
    expect(screen.queryByText('总字符数')).not.toBeInTheDocument();
    expect(screen.queryByText('系统提示词')).not.toBeInTheDocument();
  });

  it('available=false 时显示不可用与后端错误', async () => {
    analysisPrompts.mockResolvedValue({
      ok: false,
      available: false,
      error: '提示词分析不可用（未注入分析器）',
    });
    render(<Analysis />);

    expect(await screen.findByText('提示词分析不可用')).toBeInTheDocument();
    expect(screen.getByText(/未注入分析器/)).toBeInTheDocument();
  });

  it('接口 503（getJSON 返回 null）时显示不可用而非报错崩溃', async () => {
    analysisPrompts.mockResolvedValue(null);
    render(<Analysis />);

    expect(await screen.findByText('提示词分析不可用')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重试读取' })).toBeInTheDocument();
  });

  it('后台刷新失败后继续保留上次报告与已选来源', async () => {
    vi.useFakeTimers();
    try {
      analysisPrompts.mockResolvedValueOnce(PAYLOAD).mockResolvedValueOnce(null);
      render(<Analysis />);
      await act(async () => {});
      fireEvent.click(screen.getByRole('button', { name: '查看 系统提示词（群聊 · 空聊天）' }));
      expect(screen.queryByRole('button', { name: '刷新' })).not.toBeInTheDocument();
      await act(async () => {
        await vi.advanceTimersByTimeAsync(POLL.analysis);
      });
      expect(screen.getByText('刷新失败，正在展示上次结果')).toBeInTheDocument();
      expect(screen.getByText('你是 NeoBot，负责群聊。')).toBeInTheDocument();
      expect(screen.getByText('2,000')).toBeInTheDocument();
      analysisPrompts.mockResolvedValueOnce(PAYLOAD);
      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: '重试读取' }));
      });
      expect(screen.queryByText('刷新失败，正在展示上次结果')).not.toBeInTheDocument();
      expect(screen.getByText('你是 NeoBot，负责群聊。')).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it('Agent 切换与来源分页能访问全部分析内容', async () => {
    analysisPrompts.mockResolvedValue({
      ...PAYLOAD,
      agents: [
        PAYLOAD.agents![0],
        {
          name: '工具 Agent',
          total_chars: 600,
          total_tokens: 300,
          parts: Array.from({ length: 6 }, (_, index) => ({
            kind: 'tools',
            label: `工具来源 ${index}`,
            chars: 100,
            tokens: 50,
            text: `来源内容 ${index}`,
          })),
        },
      ],
    });
    render(<Analysis />);
    await screen.findByText('主 Agent（对话）');
    await act(async () => {
      fireEvent.keyDown(screen.getByRole('combobox', { name: '选择 Agent' }), { key: 'ArrowDown' });
    });
    const option = screen.getByRole('option', { name: '工具 Agent' });
    await act(async () => {
      option.focus();
      fireEvent.keyDown(option, { key: 'Enter' });
    });
    expect(screen.queryByText('gpt-4o-mini')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '查看 工具来源 0' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '提示词来源下一页' }));
    fireEvent.click(screen.getByRole('button', { name: '查看 工具来源 5' }));
    expect(screen.getByText('来源内容 5')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '返回来源组成' }));
    expect(screen.getByRole('button', { name: '来源组成' })).toHaveAttribute('aria-pressed', 'true');
  });
});
