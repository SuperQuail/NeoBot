import { now, longText, longUrl } from './scenario.mjs';
import { json } from './http.mjs';

export function createRuntimePreview(scene, configuration, pluginState) {
  const { empty, canManage, label } = scene;
  let scheduledTasks = [
    {
      task_id: 'preview-task-1',
      title: '每天下午喝水',
      detail: '这是虚构提醒，不会发送消息。',
      recurrence: 'daily',
      state: 'active',
      enabled: true,
      start_at: '2026-10-26 15:00',
      end_at: '2026-10-26 15:10',
      start_at_local: '2026-10-26T15:00',
      end_at_local: '2026-10-26T15:10',
      next_run: '2026-10-26 15:00',
      bindings: [{ kind: 'group', id: '100001' }],
      one_shot_notification: true,
    },
    {
      task_id: 'preview-task-2',
      title: '周末项目回顾',
      detail: '整理本周完成的事项和下周计划。',
      recurrence: 'weekly',
      state: 'disabled',
      enabled: false,
      start_at: '2026-10-31 20:00',
      end_at: '2026-10-31 20:15',
      start_at_local: '2026-10-31T20:00',
      end_at_local: '2026-10-31T20:15',
      next_run: '—',
      bindings: [{ kind: 'private', id: '100002' }],
      one_shot_notification: true,
    },
  ];
  let power = {
    ok: true,
    available: true,
    state: 'running',
    standby: false,
    transition: false,
    connect_onebot: true,
    operator: '本地演示',
    reason: '',
  };
  let logs = Array.from({ length: 36 }, (_, index) => ({
    id: index + 1,
    time: `10:${String(index).padStart(2, '0')}:24`,
    datetime: `2026-10-25T10:${String(index).padStart(2, '0')}:24`,
    level: ['INFO', 'DEBUG', 'SUCCESS', 'INFO', 'WARNING'][index % 5],
    module: ['runtime', 'chat', 'memory', 'dashboard'][index % 4],
    message: [
      '本地演示夹具已就绪，所有数据均为虚构。',
      '已处理虚构群聊消息，耗时 238 ms。',
      '示例模型调用完成：输入 1280 / 输出 240 Token。',
      '示例长期记忆已更新。',
      '演示告警：某个可选供应商尚未配置。',
    ][index % 5],
  }));
  function bot() {
    return {
      user_id: '1000000001',
      name: label(configuration.config.bot.nick_name),
      nickname: label(configuration.config.bot.nick_name),
      platform: 'OneBot v11',
      avatar_initial: 'N',
      avatar_url: '/image/icon.webp',
      status: power.standby && !power.connect_onebot ? 'off' : 'on',
      online: !power.standby || power.connect_onebot,
      latency_ms: 28,
      today_messages: 1286,
      total_messages: 48239,
      uptime_seconds: 92840,
      app_name: 'NapCat 演示',
      app_version: '1.0.0',
    };
  }
  function usage(hours = 24, bucket = 'hour') {
    const rows = [
      {
        module: 'chat',
        module_name: 'chat',
        model_name: 'demo-chat',
        provider_name: 'DeepSeek',
        calls: 340,
        input_tokens: 1000000,
        output_tokens: 150000,
        cost_cny: 5.32,
      },
      {
        module: 'agent',
        module_name: 'agent',
        model_name: 'demo-reasoner',
        provider_name: '演示云',
        calls: 88,
        input_tokens: 284500,
        output_tokens: 37200,
        cost_cny: 3.14,
      },
    ];
    rows.push(
      ...Array.from({ length: scene.name === 'long' ? 14 : 7 }, (_, index) => ({
        module: index % 2 ? 'memory' : 'tools',
        module_name: index % 2 ? 'memory' : 'tools',
        model_name: label(`demo-model-${index + 3}`),
        provider_name: index % 2 ? '演示云' : 'DeepSeek',
        calls: 16 + index * 3,
        input_tokens: 12000 + index * 700,
        output_tokens: 2400 + index * 300,
        cost_cny: Number((0.12 + index * 0.06).toFixed(2)),
      })),
    );
    const totals = rows.reduce(
      (sum, row) => ({
        calls: sum.calls + row.calls,
        input_tokens: sum.input_tokens + row.input_tokens,
        output_tokens: sum.output_tokens + row.output_tokens,
        cost_cny: Number((sum.cost_cny + row.cost_cny).toFixed(2)),
      }),
      { calls: 0, input_tokens: 0, output_tokens: 0, cost_cny: 0 },
    );
    return {
      available: true,
      hours,
      bucket,
      totals: empty() ? {} : totals,
      items: empty() ? [] : rows,
      models: empty() ? [] : rows,
      modules: empty() ? [] : rows,
      points: empty()
        ? []
        : Array.from({ length: 18 }, (_, index) => ({
            at:
              bucket === 'day'
                ? `2026-10-${String(index + 8).padStart(2, '0')}`
                : `2026-10-25T${String(index + 1).padStart(2, '0')}:00:00`,
            calls: 12 + index * 2,
            input_tokens: 18000 + index * 2000,
            output_tokens: 1800 + index * 400,
            cost_cny: Number((0.12 + Math.abs(Math.sin(index)) * 0.65).toFixed(3)),
          })),
    };
  }

  return {
    handle({ path, q, body, res }) {
      if (path === '/api/overview')
        return json(res, {
          ...bot(),
          online: !power.standby,
          standby: power.standby,
          bot_nickname: bot().nickname,
          bot_user_id: bot().user_id,
          plugins_loaded: pluginState.items.filter((item) => item.status === 'loaded').length,
          plugins_total: pluginState.items.length,
          notices: [],
        });
      if (path === '/api/bots') return json(res, empty() ? [] : [bot()]);
      if (path === '/api/bot/detail') return json(res, empty() ? { online: false } : bot());
      if (path === '/api/system')
        return json(res, {
          hostname: 'preview-workstation',
          os: 'Windows 11 · 虚构演示',
          python_version: '3.13.7',
          pid: 10000,
          cpu_percent: 12.4,
          cpu_count: 12,
          mem_percent: 36.2,
          mem_used_mb: 5792,
          mem_total_mb: 16000,
          process_memory_mb: 286,
          process_threads: 18,
          disk_percent: 42.8,
          disk_used_gb: 214,
          disk_total_gb: 500,
          load_average: [0.48, 0.36, 0.24],
        });
      if (path === '/api/services')
        return json(res, {
          items: empty()
            ? []
            : ['OneBot 适配器', 'LLM Provider', '长期记忆', '定时任务', '网页面板'].map((name) => ({
                name,
                description: '本地演示服务',
                available: true,
              })),
        });
      if (path === '/api/tasks')
        return json(res, {
          scheduled: empty()
            ? []
            : [
                {
                  task_id: 'demo-summary',
                  description: '长期记忆整理',
                  next_run: '2026-10-26 02:00',
                  status: '等待中',
                },
              ],
          background: empty()
            ? []
            : [
                {
                  task_id: 'demo-inference',
                  kind: '模型调用',
                  pipeline_key: 'group:100001',
                  status: '处理中',
                },
              ],
        });
      if (path === '/api/logs') {
        if (q.has('since') && !empty()) {
          const id = (logs.at(-1)?.id || 0) + 1;
          logs.push({
            id,
            time: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
            datetime: now(),
            level: 'INFO',
            module: 'preview',
            message: scene.name === 'long' ? longText + ' ' + longUrl : '演示日志心跳：面板运行正常。',
          });
        }
        const items = empty()
          ? []
          : logs.filter((item) => item.id > Number(q.get('since') || 0)).slice(-Number(q.get('limit') || 80));
        return json(res, { items, last_id: logs.at(-1)?.id || 0, total: logs.length });
      }
      if (path === '/api/series/messages')
        return json(res, {
          series: empty()
            ? []
            : Array.from({ length: 30 }, (_, index) => ({
                date: new Date(Date.UTC(2026, 8, 27 + index)).toISOString().slice(0, 10),
                count: 180 + ((index * 137) % 620),
              })),
        });
      if (path === '/api/series/latency')
        return json(res, {
          current_ms: 28,
          avg_ms: 31,
          success_rate: 99.8,
          series: empty()
            ? []
            : Array.from({ length: 24 }, (_, index) => ({
                ts: Math.floor(Date.now() / 1000) - (23 - index) * 30,
                ms: 22 + ((index * 7) % 26),
              })),
        });
      if (path === '/api/stats/api-calls')
        return json(res, {
          total_calls: 2864,
          unique_actions: 8,
          items: empty()
            ? []
            : ['send_group_msg', 'get_group_info', 'get_stranger_info', 'get_msg', 'send_private_msg'].map(
                (action, index) => ({ action, count: 900 - index * 160 }),
              ),
        });
      if (path === '/api/stats/active-users')
        return json(res, {
          tracked_users: 82,
          items: empty()
            ? []
            : ['小林（虚构）', '小夏（虚构）', '小北（虚构）'].map((nickname, index) => ({
                user_id: String(100002 + index),
                nickname,
                count: 120 - index * 30,
                last_seen: Date.now() / 1000 - index * 130,
              })),
        });
      if (path === '/api/series/usage' || path === '/api/stats/usage')
        return json(res, usage(Number(q.get('hours') || 24), q.get('bucket') || 'hour'));
      if (path === '/api/stats/usage/records')
        return json(res, {
          available: true,
          hours: Number(q.get('hours') || 24),
          items: empty()
            ? []
            : Array.from({ length: scene.name === 'long' ? 48 : 24 }, (_, index) => ({
                at: new Date(Date.UTC(2026, 9, 25, 10, 30 - index)).toISOString(),
                module: index % 2 ? 'agent' : 'chat',
                model_name: index % 2 ? 'demo-reasoner' : 'demo-chat',
                provider_name: index % 2 ? '演示云' : 'DeepSeek',
                input_tokens: 1200 + index * 80,
                output_tokens: 240 + index * 20,
                cache_hit_tokens: index * 12,
                cache_miss_tokens: 1200 + index * 68,
                cost_cny: index === 6 ? -0.02 : 0.026 + index * 0.012,
                cost_source:
                  index % 3 === 0 ? 'script:demo_pricing' : index === 5 ? 'fallback:演示脚本超时' : 'builtin',
                negative: index === 6,
                cost_detail:
                  q.get('detail') === '1'
                    ? {
                        components: {
                          input: 0.02,
                          output: 0.006,
                          adjustment: index === 6 ? -0.046 : index * 0.012,
                        },
                        note: '虚构计费明细，仅用于界面验证',
                        error: index === 5 ? '演示计费脚本超时，已回退到价格表。' : undefined,
                      }
                    : null,
              })).slice(0, Math.max(1, Math.min(100, Number(q.get('limit') || 24)))),
        });
      if (path === '/api/scheduled-tasks')
        return json(res, {
          ok: true,
          available: true,
          editable: canManage(),
          tasks: empty() ? [] : scheduledTasks.map((task) => ({ ...task, title: label(task.title) })),
        });
      if (path === '/api/scheduled-tasks/action') {
        const task = scheduledTasks.find((item) => item.task_id === body.task_uuid);
        if (body.action === 'create')
          scheduledTasks.push({
            ...body,
            task_id: 'preview-task-' + Date.now(),
            state: 'active',
            enabled: true,
            start_at_local: body.start_at,
            end_at_local: body.end_at,
            next_run: body.start_at,
          });
        else if (body.action === 'delete')
          scheduledTasks = scheduledTasks.filter((item) => item.task_id !== body.task_uuid);
        else if (task)
          Object.assign(
            task,
            body,
            body.action === 'set_state'
              ? { enabled: body.state === 'active' }
              : {
                  start_at_local: body.start_at || task.start_at_local,
                  end_at_local: body.end_at || task.end_at_local,
                },
          );
        return json(res, { message: '定时任务已更新到演示内存，不会发送提醒' });
      }
      if (path === '/api/admin/power') return json(res, power);
      if (path === '/api/admin/standby') {
        power = {
          ...power,
          state: 'standby',
          standby: true,
          operator: '本地演示',
          reason: body.reason,
          standby_seconds: 12,
        };
        return json(res, { ...power, message: '演示已进入待机' });
      }
      if (path === '/api/admin/resume' || path === '/api/admin/reboot') {
        power = { ...power, state: 'running', standby: false };
        return json(res, { ...power, message: '演示运行已恢复' });
      }
      if (path === '/api/admin/standby/onebot') {
        power.connect_onebot = !!body.enabled;
        return json(res, { ...power, message: '演示 OneBot 连接策略已更新' });
      }
      if (path === '/api/admin/restart' || path === '/api/admin/shutdown')
        return json(res, { message: '演示操作已记录；夹具继续运行，不操作任何真实进程' });
    },
  };
}
