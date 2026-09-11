// Analysis.test.tsx —— 分析页回归测试：总量渲染、展开提示词、单来源错误、不可用态
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import Analysis from '../pages/Analysis';
import { api } from '../api/endpoints';
import { clearQueries } from '../data/queryCore';
import type { PromptAnalysisPayload } from '../api/types';

vi.mock('../api/endpoints.js', () => ({
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
    expect(screen.getByText(/估算口径：中文字符/)).toBeInTheDocument();
    // 中文 kind 标签与占比（1500/2000 = 75%）
    expect(screen.getByText('系统提示词')).toBeInTheDocument();
    expect(screen.getByText('工具定义')).toBeInTheDocument();
    expect(screen.getByText(/75\.0%/)).toBeInTheDocument();
    expect(screen.getByText(/25\.0%/)).toBeInTheDocument();
  });

  it('展开 / 收起 part 可以看到具体提示词，截断 part 有提示', async () => {
    analysisPrompts.mockResolvedValue(PAYLOAD);
    render(<Analysis />);
    await screen.findByText('主 Agent（对话）');

    expect(screen.queryByText('你是 NeoBot，负责群聊。')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '展开 系统提示词（群聊 · 空聊天）' }));
    expect(screen.getByText('你是 NeoBot，负责群聊。')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '展开 工具定义（全部 skill 包）' }));
    expect(screen.getByText('工具清单：search、weather。')).toBeInTheDocument();
    expect(screen.getByText('已截断展示，统计按全文计算')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '收起 系统提示词（群聊 · 空聊天）' }));
    expect(screen.queryByText('你是 NeoBot，负责群聊。')).not.toBeInTheDocument();
  });

  it('单个 agent 装配失败时显示错误并跳过 parts / 合计', async () => {
    analysisPrompts.mockResolvedValue({
      ok: true,
      available: true,
      rule: '估算口径：略',
      agents: [{ name: '工具 Agent', error: '装配失败：缺少模型配置', total_chars: 0, total_tokens: 0, parts: [] }],
    });
    render(<Analysis />);

    expect(await screen.findByText('工具 Agent')).toBeInTheDocument();
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
    expect(screen.getByRole('button', { name: /刷新/ })).toBeInTheDocument();
  });
});
