import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';
import SchemaForm from '../components/SchemaForm';
import type { FieldDescriptor } from '../api/types';
import { bindValues } from '../pages/config/shared';
import { getPath, setPath } from '../utils/paths';

describe('配置字段输入别名', () => {
  it('为缺省嵌套 AliasPath 创建数组容器，保留同组其他字段', () => {
    const schema: FieldDescriptor[] = [
      {
        name: 'nested',
        path: ['nested'],
        kind: 'group',
        fields: [
          {
            name: 'interval',
            label: '间隔秒数',
            path: ['nested', 'payload', 0, 'entry'],
            kind: 'scalar',
            type: 'int',
            value: 60,
          },
        ],
      },
    ];
    function Harness() {
      const [draft, update] = useState({ nested: { retained: '保留' } });
      return (
        <>
          <SchemaForm
            fields={bindValues(schema, draft)}
            values={draft}
            onChange={(path, value) => update(setPath(draft, path, value))}
            showReloadSummary={false}
          />
          <output data-testid="draft">{JSON.stringify(draft)}</output>
        </>
      );
    }
    render(<Harness />);
    fireEvent.change(screen.getByRole('spinbutton', { name: /间隔秒数/ }), { target: { value: '15' } });
    expect(JSON.parse(screen.getByTestId('draft').textContent!)).toEqual({
      nested: { retained: '保留', payload: [{ entry: 15 }] },
    });
  });
  it.each([['seconds'], ['payload', 0, 'entry']])('按别名路径编辑现有分组并新增对象行：%j', (...alias) => {
    const child: FieldDescriptor = {
      name: 'interval',
      label: '间隔秒数',
      path: ['routes', ...alias],
      kind: 'scalar',
      type: 'int',
      default: 60,
    };
    const rows: FieldDescriptor = {
      name: 'routes',
      path: ['routes'],
      kind: 'model_list',
      item_fields: [child],
    };
    function Harness() {
      const [draft, update] = useState({ routes: [setPath({}, alias, 30)] });
      return (
        <>
          <SchemaForm
            fields={bindValues([rows], draft)}
            values={draft}
            onChange={(path, value) => update(setPath(draft, path, value))}
            showReloadSummary={false}
          />
          <output data-testid="draft">{JSON.stringify(draft)}</output>
        </>
      );
    }
    render(<Harness />);
    expect(screen.getByRole('spinbutton', { name: /间隔秒数/ })).toHaveValue(30);
    fireEvent.change(screen.getByRole('spinbutton', { name: /间隔秒数/ }), { target: { value: '15' } });
    fireEvent.click(screen.getByRole('button', { name: /新增/ }));
    const draft = JSON.parse(screen.getByTestId('draft').textContent!);
    expect(getPath(draft.routes[0], alias)).toBe(15);
    expect(getPath(draft.routes[1], alias)).toBe(60);
    expect(draft.routes.every((row: object) => !('interval' in row))).toBe(true);
    if (alias.length > 1) expect(Array.isArray(draft.routes[1].payload)).toBe(true);
  });
});
