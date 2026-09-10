// components/schema/fieldRegistry.ts —— kind -> 渲染组件
// 原先是 Field.tsx 里的一串 if/else：后端 schema 每新增一种 kind 都要改渲染函数。
// 改为查表后，新增类型只需在这里注册一行；未注册的 kind 退回 ScalarField（只读文本形态），
// 因此老数据不会因为前端没跟上而消失。
import type { ComponentType } from 'react';
import type { FieldDescriptor } from '../../api/types';
import ComboboxField from './ComboboxField';
import JsonField from './JsonField';
import ModelList from './ModelList';
import ScalarField from './ScalarField';
import type { FieldCallbacks } from './fieldTypes';

type FieldComponent = ComponentType<{ descriptor: FieldDescriptor } & FieldCallbacks>;

export const fieldRegistry: Record<string, FieldComponent> = {
  scalar: ScalarField,
  model_list: ModelList,
  list: JsonField,
  dict: JsonField,
  // 下拉候选型标量：由 ScalarField 内部再次分流到 ComboboxField
  enum: ScalarField,
};

/** 未注册 kind 的兜底：按标量只读展示，避免字段凭空消失 */
export function resolveFieldComponent(kind?: string): FieldComponent {
  if (kind && fieldRegistry[kind]) return fieldRegistry[kind];
  if (kind && kind !== 'scalar') {
    console.warn('[SchemaForm] 未注册的字段类型，回退为标量展示:', kind);
  }
  return ScalarField;
}

export default fieldRegistry;
