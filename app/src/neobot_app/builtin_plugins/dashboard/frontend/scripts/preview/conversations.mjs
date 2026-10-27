import { clone, longText, longUrl } from './scenario.mjs';
import { json } from './http.mjs';

export function createConversationPreview(scene, configuration) {
  const { empty, canManage, label } = scene;
  let promptSections = [
    {
      name: 'group_chat',
      customized: true,
      keys: [
        {
          path: 'template',
          label: '群聊系统提示词',
          kind: 'template',
          value: '你是{bot_name}。\n{bot_data}\n当前时间：{current_time}\n请根据聊天上下文自然回复。',
          default: '你是{bot_name}，请友善回复。',
          custom: '你是{bot_name}。\n{bot_data}',
          overridden: true,
          placeholders: ['bot_name', 'bot_data', 'current_time'],
        },
      ],
    },
    {
      name: 'private_chat',
      customized: false,
      keys: [
        {
          path: 'template',
          label: '私聊系统提示词',
          kind: 'template',
          value: '你是{bot_name}。认真回答用户的问题。',
          default: '你是{bot_name}。认真回答用户的问题。',
          custom: null,
          overridden: false,
          placeholders: ['bot_name'],
        },
      ],
    },
    {
      name: 'problem_solver',
      customized: false,
      keys: [
        {
          path: 'description',
          label: '复杂问题说明',
          kind: 'text',
          value: '将复杂问题拆成可验证的小步骤。',
          default: '将复杂问题拆成可验证的小步骤。',
          custom: null,
          overridden: false,
          placeholders: [],
        },
      ],
    },
  ];
  const promptSeeds = [
    ['group_context', '群聊上下文：结合近期聊天记录回答。'],
    ['friend_context', '私聊上下文：优先回答用户刚刚提出的问题。'],
    ['friend_chat_hint', '私聊补充说明：不要重复已经解释的内容。'],
    ['long_task_progress', '长任务进行中时，简短说明当前阶段。'],
    ['current_time', '当前时间：{current_time}'],
    ['current_time_short', '现在是 {current_time}。'],
    ['avoid_repeat', '避免重复发送相同的回复。'],
    ['silent_nudge', '任务仍在处理，完成后给出结果。'],
    ['group_chat_resume', '对话恢复时先回顾最近的有效消息。'],
    ['new_member_profiles', '遇到新成员时保持友善，不推测私人信息。'],
    ['native_vision', '根据图像中实际可见的信息回答。'],
    ['tool_result_compressed', '概括工具返回的关键结果，保留来源。'],
    ['tool_result_compressed_detail', '展开工具结果中的必要细节。'],
    ['long_reply_fallback', '回复过长时优先给出用户需要的结论。'],
    ['self_heal', '检查失败原因，给出可执行的恢复步骤。'],
    ['maintenance', '说明维护内容以及预计受影响的功能。'],
    ['wake_up', '恢复处理先前等待中的任务。'],
    ['at_mention_wait', '被提及时，如用户尚未说完，稍等片刻再回复。'],
    ['sleep_cmd', '已进入休眠，收到唤醒指令后继续工作。'],
    ['awake_cmd', '已恢复工作。'],
    ['human_feel', '使用自然、简洁的中文表达。'],
    ['stale_topic', '辨别过期话题，不打断当前对话。'],
    ['跨会话上下文压缩与长期记忆衔接规则（长名称演示）', '结合有效记忆回答，保留当前对话的具体上下文。'],
  ];
  function templateKey(value, path = 'template', overridden = false) {
    return {
      path,
      label: path,
      kind: 'template',
      value,
      default: value,
      custom: overridden ? value : null,
      overridden,
      placeholders: [...value.matchAll(/\{([a-zA-Z_]+)\}/g)].map((match) => match[1]),
    };
  }
  promptSections.push(
    ...promptSeeds.map(([name, value], index) => ({
      name,
      customized: index % 7 === 0,
      keys: [templateKey(value, 'template', index % 7 === 0)],
    })),
  );
  promptSections
    .find((section) => section.name === 'problem_solver')
    .keys.push(
      templateKey('你是{bot_name}，请将复杂问题拆分为步骤并检查结果。', 'system_prompt'),
      templateKey('执行时记录关键假设、依据与尚未解决的问题。', 'runtime.template'),
    );
  promptSections.push(
    ...Array.from({ length: 10 }, (_, index) => ({
      name: `长内容附加分区 ${index + 1} · ${longText.slice(0, 48)}`,
      customized: false,
      keys: [templateKey(longText + '\n{bot_name} · {current_time}')],
    })),
  );
  const flowSeeds = [
    {
      pipeline_key: 'group:100001',
      display_name: '演示开发交流群',
      conversation_kind: 'group',
      conversation_id: '100001',
      model: 'demo-chat',
      active: true,
      iterations: 2,
      message_count: 8,
      total_messages: 8,
      prompt_chars: 3840,
      age_seconds: 16,
    },
    {
      pipeline_key: 'private:100002',
      display_name: '演示用户小林',
      conversation_kind: 'private',
      conversation_id: '100002',
      model: 'demo-reasoner',
      active: false,
      iterations: 1,
      message_count: 3,
      total_messages: 3,
      prompt_chars: 1200,
      age_seconds: 180,
    },
  ];
  const chatMessages = [
    { role: 'system', content: '你是演示小乔，一个友善的虚构群聊助手。' },
    { role: 'user', content: '周末一起做一个新面板吧，先把功能清单整理一下。' },
    { role: 'assistant', content: '可以，先从运行概览、配置、插件和诊断工作区开始。' },
    { role: 'user', content: '配置修改时要保留草稿，日志也要能快速筛选。' },
  ];
  let promptHistory = Array.from({ length: 4 }, (_, index) => ({
    seq: index + 1,
    pipeline_key: index === 0 ? 'private:100002' : 'group:100001',
    iteration: index + 1,
    model: 'demo-chat',
    total_messages: chatMessages.length,
    bytes: 4820 + index * 340,
    patch_bytes: 230 + index * 80,
    images: 0,
    recorded_at: `2026-10-25T10:0${index}:00`,
  }));

  return {
    handle({ path, q, body, res }) {
      if (path === '/api/prompts')
        return json(res, {
          sections: empty()
            ? []
            : clone(scene.name === 'long' ? promptSections : promptSections.slice(0, 26)).map((section) => ({
                ...section,
                customized: section.keys.some((item) => item.overridden),
              })),
          editable: canManage(),
          default_file: '演示数据/default/prompts.toml',
          custom_file: '演示数据/custom/prompts.toml',
        });
      if (path === '/api/prompts/preview') {
        const values = {
          bot_name: configuration.config.bot.nick_name,
          bot_data: configuration.config.bot.bot_data,
          current_time: '2026-10-25 10:30',
          ...body.values,
        };
        const unresolved = [];
        const rendered = String(body.template || '').replace(/\{([a-zA-Z_]+)\}/g, (match, key) =>
          key in values ? values[key] : (unresolved.push(key), match),
        );
        return json(res, { rendered, unresolved, values, placeholders: Object.keys(values) });
      }
      if (path === '/api/prompts/save' || path === '/api/prompts/reset') {
        const item = promptSections
          .find((section) => section.name === body.section)
          ?.keys.find((entry) => entry.path === body.path);
        if (!item) return json(res, { error: '演示模板不存在' }, 404);
        if (path.endsWith('/reset'))
          Object.assign(item, { value: item.default || '', custom: null, overridden: false });
        else Object.assign(item, { value: body.value, custom: body.value, overridden: true });
        return json(res, { message: '提示词已更新到演示内存' });
      }
      if (path === '/api/analysis/prompts')
        return json(res, {
          ok: true,
          available: true,
          rule: '演示估算口径：中文约 1.5 字符 / token，仅供界面展示。',
          generated_at: Date.now() / 1000,
          agents: empty()
            ? []
            : ['主对话 Agent', '记忆总结 Agent', '问题求解 Agent'].map((name, index) =>
                index === 2
                  ? {
                      name,
                      model: 'demo-reasoner',
                      error: '演示：自定义提示词存在未解析的占位符，暂时无法装配。',
                      parts: [],
                    }
                  : {
                      name: label(name),
                      model: 'demo-chat',
                      note: '虚构装配结果，用于验证来源选择、预览与统计布局。',
                      total_chars: 3480 + index * 600,
                      total_tokens: 2320 + index * 400,
                      parts: [
                        {
                          kind: 'system',
                          label: '系统提示词',
                          chars: 1200,
                          tokens: 800,
                          text: scene.name === 'long' ? longText : configuration.config.bot.bot_data,
                        },
                        {
                          kind: 'tools',
                          label: '工具定义',
                          chars: 600,
                          tokens: 400,
                          text: '演示工具：搜索、查看档案、创建提醒。',
                        },
                        {
                          kind: 'history',
                          label: '历史上下文',
                          chars: 600 + index * 600,
                          tokens: 400 + index * 400,
                          text: chatMessages.map((message) => message.content).join('\n'),
                        },
                        {
                          kind: 'instructions',
                          label: '角色与回复规则',
                          chars: 240,
                          tokens: 160,
                          text: '简洁回答当前问题，引用可以核验的依据。',
                        },
                        {
                          kind: 'instructions',
                          label: '可用工具与调用限制',
                          chars: 360,
                          tokens: 240,
                          text: '演示工具均不访问真实服务；避免重复调用，错误时说明原因。',
                        },
                        {
                          kind: 'instructions',
                          label: '长期记忆摘要',
                          chars: 480,
                          tokens: 320,
                          text: longText.slice(0, 180),
                          truncated: true,
                        },
                      ],
                    },
              ),
        });
      if (path === '/api/chat-flows')
        return json(res, {
          ok: true,
          items: empty()
            ? []
            : flowSeeds.map((flow) => ({ ...flow, display_name: label(flow.display_name) })),
        });
      if (path === '/api/chat-flows/detail') {
        const flow = flowSeeds.find((item) => item.pipeline_key === q.get('key')) || flowSeeds[0];
        return json(res, {
          ...flow,
          display_name: label(flow.display_name),
          system_prompt: scene.name === 'long' ? longText : configuration.config.bot.bot_data,
          messages: chatMessages,
          background_tasks: { memory_summary: { status: 'waiting', pending: 12 } },
        });
      }
      if (path === '/api/chat-flows/prompts')
        return json(res, {
          ok: true,
          items: empty()
            ? []
            : promptHistory.filter((item) => !q.get('key') || item.pipeline_key === q.get('key')),
          limit: 100,
          storage_bytes: 28640,
          image_refs: 0,
        });
      if (path === '/api/chat-flows/prompt') {
        const meta = promptHistory.find((item) => item.seq === Number(q.get('seq')));
        return json(res, {
          ok: !!meta,
          seq: meta?.seq,
          entry: meta
            ? {
                ...meta,
                recorded_at: meta.recorded_at,
                stage: 'reply',
                mode: 'chat',
                messages_count: chatMessages.length,
                total_chars: 3840,
                estimated_tokens: 2560,
                output_chars: 28,
                messages:
                  scene.name === 'long'
                    ? [...chatMessages, { role: 'user', content: longText + '\n' + longUrl }]
                    : chatMessages,
                response: { role: 'assistant', content: '可以，先把页面和交互状态梳理完整。' },
                usage: { input_tokens: 1280, output_tokens: 240 },
              }
            : null,
        });
      }
      if (path === '/api/chat-flows/prompts/clear') {
        promptHistory = [];
        return json(res, { message: '演示提示词历史已清空（仅内存）' });
      }
    },
  };
}
