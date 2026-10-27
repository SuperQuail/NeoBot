import { clone, now, longText, created } from './scenario.mjs';
import { json, PREVIEW_HOST } from './http.mjs';

export function createArchivePreview(scene) {
  const { empty, canManage } = scene;
  const archiveRows = new Map([
    [
      'user_profile|user:100002',
      {
        table_name: 'user_profile',
        key: 'user:100002',
        value:
          '虚构用户小林喜欢编程、摄影和咖啡。偏好简短、有步骤的回答。\n此记录仅用于本地界面演示，不对应任何真实用户。',
        tags: ['偏好', '演示'],
        version: 3,
        editable: true,
        created_at: created,
        updated_at: created,
        internal: false,
      },
    ],
    [
      'user_profile|user:100003',
      {
        table_name: 'user_profile',
        key: 'user:100003',
        value: longText.repeat(16),
        tags: ['超限', '演示'],
        version: 2,
        editable: true,
        created_at: created,
        updated_at: created,
        internal: false,
      },
    ],
    [
      'group_profile|group:100001',
      {
        table_name: 'group_profile',
        key: 'group:100001',
        value: '虚构开发群，主要讨论产品设计、代码评审与周末活动。',
        tags: ['开发'],
        version: 1,
        editable: true,
        created_at: created,
        updated_at: created,
        internal: false,
      },
    ],
    [
      'memory_counter|group:100001',
      {
        table_name: 'memory_counter',
        key: 'group:100001',
        value: '{"pending_messages": 12, "last_summary": "演示"}',
        tags: [],
        version: 1,
        editable: false,
        created_at: created,
        updated_at: created,
        internal: true,
        note: '内部计数表，禁止手工编辑。',
      },
    ],
  ]);
  const archiveSnapshots = [];
  const summarizeTasks = new Map();
  function summarize(row, target) {
    const snapshot = {
      ...clone(row),
      id: archiveSnapshots.length + 1,
      total_chars: row.value.length,
      chars_before: row.value.length,
      chars_after: Math.min(target, row.value.length),
      reason: 'manual',
      operator_ip: PREVIEW_HOST,
      created_at: now(),
    };
    archiveSnapshots.push(snapshot);
    row.value = row.value.slice(0, target);
    row.version++;
    row.updated_at = now();
    return snapshot;
  }

  return {
    handle({ path, method, q, body, res }) {
      if (path === '/api/archives')
        return json(res, {
          ok: true,
          items: empty()
            ? []
            : ['user_profile', 'group_profile', 'memory_counter'].map((name) => {
                const items = [...archiveRows.values()].filter((row) => row.table_name === name);
                return {
                  table_name: name,
                  count: items.length,
                  max_value_chars: Math.max(0, ...items.map((row) => row.value.length)),
                  over_limit_count: items.filter((row) => row.value.length > 5000).length,
                  internal: name === 'memory_counter',
                  note:
                    name === 'memory_counter' ? '内部计数表，禁止手工编辑。' : '虚构档案，仅用于本地预览。',
                };
              }),
          max_total_chars: 5000,
          min_target_chars: 200,
          max_target_chars: 5000,
          delete_enabled: true,
          can_manage: canManage(),
          summarize_available: true,
        });
      if (path === '/api/archives/items') {
        const rows = empty()
          ? []
          : [...archiveRows.values()].filter(
              (row) =>
                row.table_name === q.get('table') &&
                row.key.includes(q.get('key_query') || '') &&
                row.value.includes(q.get('value_query') || '') &&
                (!q.get('tags') || row.tags.some((tag) => q.get('tags').includes(tag))) &&
                (q.get('over_limit') !== '1' || row.value.length > 5000),
            );
        const offset = Number(q.get('offset') || 0);
        const limit = Number(q.get('limit') || 50);
        return json(res, {
          ok: true,
          items: rows.slice(offset, offset + limit).map(({ value, ...row }) => ({
            ...row,
            total_chars: value.length,
            preview: value.slice(0, 80),
            preview_truncated: value.length > 80,
          })),
          table: q.get('table'),
          offset,
          limit,
          has_more: rows.length > offset + limit,
        });
      }
      if (path === '/api/archives/item') {
        const key = method === 'GET' ? q.get('table') + '|' + q.get('key') : body.table + '|' + body.key;
        const row = archiveRows.get(key);
        if (!row) return json(res, { error: '演示档案不存在' }, 404);
        if (method === 'GET') return json(res, { ...clone(row), total_chars: row.value.length });
        if (body.version !== row.version)
          return json(res, { error: '档案已被其他会话修改', current: clone(row) }, 409);
        if (method === 'DELETE') {
          archiveRows.delete(key);
          return json(res, { message: '演示档案已从内存删除' });
        }
        if (!row.editable) return json(res, { error: '演示内部表不允许编辑' }, 403);
        Object.assign(row, {
          value: String(body.value || ''),
          tags: body.tags || [],
          version: row.version + 1,
          updated_at: now(),
        });
        return json(res, { ...row, total_chars: row.value.length, message: '演示档案已保存' });
      }
      if (path === '/api/archives/snapshots')
        return json(res, {
          ok: true,
          items: archiveSnapshots
            .filter((item) => item.table_name === q.get('table') && item.key === q.get('key'))
            .map((item) => {
              const snapshot = clone(item);
              delete snapshot.value;
              return snapshot;
            }),
          keep_per_key: 10,
          restore_supported: false,
        });
      if (path === '/api/archives/snapshot')
        return json(res, {
          ok: true,
          snapshot: archiveSnapshots.find((item) => item.id === Number(q.get('id'))),
        });
      if (path === '/api/archives/summarize' || path === '/api/archives/summarize/over-limit') {
        if (method === 'GET')
          return json(
            res,
            summarizeTasks.get(q.get('task_id')) || { ok: false, status: 'failed', error: '演示任务不存在' },
          );
        const target = Math.max(200, Math.min(5000, Number(body.target_chars || 5000)));
        const rows = path.endsWith('/over-limit')
          ? [...archiveRows.values()].filter((row) => row.editable && row.value.length > target).slice(0, 20)
          : [archiveRows.get(body.table + '|' + body.key)].filter(Boolean);
        const items = rows.map((row) => {
          const snapshot = summarize(row, target);
          return {
            table: row.table_name,
            key: row.key,
            status: 'done',
            chars_before: snapshot.chars_before,
            chars_after: row.value.length,
            snapshot_id: snapshot.id,
          };
        });
        const task = {
          ok: true,
          task_id: 'demo-summary-' + (summarizeTasks.size + 1),
          kind: path.endsWith('/over-limit') ? 'batch' : 'single',
          status: 'done',
          table: body.table,
          key: body.key,
          target_chars: target,
          chars_before: items[0]?.chars_before,
          chars_after: items[0]?.chars_after,
          snapshot_id: items[0]?.snapshot_id,
          items,
          succeeded: items.length,
          failed: 0,
          skipped: [],
          message: '演示压缩已完成：仅截取虚构内容，不调用模型',
        };
        summarizeTasks.set(task.task_id, task);
        return json(res, { ...task, status: 'running', message: '演示压缩处理中，下一次轮询返回完成结果' });
      }
    },
  };
}
