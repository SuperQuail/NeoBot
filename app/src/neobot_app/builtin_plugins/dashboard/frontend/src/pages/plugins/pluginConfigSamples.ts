import type { FieldDescriptor, JsonSchema } from '../../api/types';
import { SECRET_RE } from '../../components/schema/fieldTypes';
import { getPath, setPath } from '../../utils/paths';
import { rebaseFieldPaths } from '../config/shared';
import { resolveSchema } from './pluginActionSchema';

/** 即使 JSON 兜底字段没有子描述符，样例和默认值里的凭据也不能显示。 */
function publicValue(value: unknown, raw: JsonSchema = {}, root: JsonSchema = raw): unknown {
  const resolved = resolveSchema(raw, root);
  const schema = typeof resolved === 'object' ? resolved : {};
  if (schema.writeOnly === true || schema.format === 'password') return '';
  if (Array.isArray(value)) {
    const item = schema.items && !Array.isArray(schema.items) ? schema.items : {};
    return value.map((child) => publicValue(child, item, root));
  }
  if (value !== null && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value).map(([key, child]) => [
        key,
        SECRET_RE.test(key) ? '' : publicValue(child, schema.properties?.[key] ?? {}, root),
      ]),
    );
  }
  return value;
}

function blankValue(field: FieldDescriptor): unknown {
  if (field.kind === 'group' || field.kind === 'dict' || field.kind === 'model_params') return {};
  if (field.kind === 'model_list' || field.kind === 'list') return [];
  if (field.type === 'bool') return false;
  return '';
}

/** 只保留声明式控件元数据；绝不把实时 value/items、参数上下文或密钥状态传进教程。 */
export function sampleField(
  field: FieldDescriptor,
  sample: unknown,
  root: JsonSchema | null = null,
): FieldDescriptor {
  const schema = fieldSchema(root, field.path);
  const sensitive =
    field.sensitive === true ||
    SECRET_RE.test(String(field.path.at(-1) ?? field.name)) ||
    schema.writeOnly === true ||
    schema.format === 'password';
  const descriptor: FieldDescriptor = {
    name: field.name,
    label: field.label,
    path: field.path,
    kind: field.kind,
    type: field.type,
    description: field.description,
    readonly: field.readonly,
    hidden: field.hidden,
    options: sensitive ? undefined : field.options,
    option_values: sensitive ? undefined : field.option_values,
    option_labels: sensitive ? undefined : field.option_labels,
    option_groups: sensitive ? undefined : field.option_groups,
    options_strict: field.options_strict,
    multi: field.multi,
    min: field.min,
    max: field.max,
    hot_reload: field.hot_reload,
    restart_reason: field.restart_reason,
    sensitive,
    default: sensitive ? '' : publicValue(field.default, schema, root ?? {}),
    value: sensitive
      ? ''
      : publicValue(
          sample === undefined ? (field.default === undefined ? blankValue(field) : field.default) : sample,
          schema,
          root ?? {},
        ),
    input_id: `ponder-config-${field.path.map(encodeURIComponent).join('-')}`,
  };
  if (sensitive) return descriptor;
  if (field.kind === 'group') {
    descriptor.fields = field.fields?.map((child) =>
      sampleField(child, getPath(descriptor.value, child.path.slice(field.path.length)), root),
    );
    descriptor.value = Object.fromEntries(
      (descriptor.fields ?? []).map((child) => [child.name, child.value]),
    );
    descriptor.default = Object.fromEntries(
      (descriptor.fields ?? []).map((child) => [child.name, child.default]),
    );
  }
  if (field.kind === 'model_list') {
    const template = field.item_fields ?? field.items?.[0]?.fields ?? [];
    const previous = field.item_fields ? field.path : [...field.path, '0'];
    const rows = Array.isArray(descriptor.value) ? descriptor.value : [];
    descriptor.item_fields = rebaseFieldPaths(template, previous, field.path).map((child) =>
      sampleField(child, undefined, root),
    );
    descriptor.items = rows.map((row, index) => {
      const rowPath = [...field.path, String(index)];
      const fields = rebaseFieldPaths(template, previous, rowPath).map((child) =>
        sampleField(child, getPath(row, child.path.slice(rowPath.length)), root),
      );
      return { index, fields };
    });
    descriptor.value = descriptor.items.map((item) =>
      Object.fromEntries(item.fields.map((child) => [child.name, child.value])),
    );
    // 恢复默认提示也不能保留尚未经过子字段清理的对象行。
    descriptor.default = [];
  }
  return descriptor;
}

/** 插件尚未加载时，仍用公开契约生成同一套 SchemaForm 控件。 */
export function schemaFields(root: JsonSchema | null): FieldDescriptor[] {
  if (root === null) return [];
  const build = (raw: JsonSchema, path: Array<string | number>, ancestors: JsonSchema[]): FieldDescriptor => {
    const resolved = resolveSchema(raw, root);
    const schema = typeof resolved === 'object' ? resolved : {};
    const name = String(path.at(-1));
    const descriptor: FieldDescriptor = {
      name,
      path,
      label: schema.title || name,
      kind: 'json',
      default: schema.default,
      description: schema.description,
      min: schema.minimum,
      max: schema.maximum,
      readonly: schema.readOnly === true,
      sensitive: schema.writeOnly === true || schema.format === 'password' || SECRET_RE.test(name),
    };
    if (ancestors.includes(raw)) return descriptor;
    const next = [...ancestors, raw];
    if (schema.properties) {
      descriptor.kind = 'group';
      descriptor.fields = Object.entries(schema.properties).map(([key, child]) =>
        build(child, [...path, key], next),
      );
    } else if (schema.type === 'array') {
      const item = schema.items && !Array.isArray(schema.items) ? resolveSchema(schema.items, root) : false;
      if (typeof item === 'object' && item.properties) {
        descriptor.kind = 'model_list';
        descriptor.item_fields = Object.entries(item.properties).map(([key, child]) =>
          build(child, [...path, key], next),
        );
      } else {
        descriptor.kind = 'list';
      }
    } else if (['string', 'integer', 'number', 'boolean'].includes(String(schema.type))) {
      descriptor.kind = 'scalar';
      descriptor.type = { string: 'str', integer: 'int', number: 'float', boolean: 'bool' }[
        String(schema.type)
      ];
      if (schema.enum) {
        descriptor.options = schema.enum.map(String);
        descriptor.option_values = Object.fromEntries(
          schema.enum.map((value) => [String(value), value]),
        ) as FieldDescriptor['option_values'];
        descriptor.options_strict = true;
      }
    }
    return descriptor;
  };
  const schema = resolveSchema(root, root);
  return typeof schema === 'object'
    ? Object.entries(schema.properties ?? {}).map(([key, child]) => build(child, [key], []))
    : [];
}

export function sampleValues(fields: FieldDescriptor[]): Record<string, unknown> {
  return fields.reduce((values, field) => setPath(values, field.path, field.value), {});
}

function fieldSchema(root: JsonSchema | null, path: Array<string | number>): Exclude<JsonSchema, boolean> {
  if (root === null) return {};
  let field: JsonSchema = root;
  for (const part of path) {
    let parent = resolveSchema(field, root);
    if (typeof parent !== 'object') return {};
    if (parent.type === 'array' && parent.items && !Array.isArray(parent.items)) {
      field = parent.items;
      if (/^\d+$/.test(String(part))) continue;
      parent = resolveSchema(field, root);
      if (typeof parent !== 'object') return {};
    }
    field = parent.properties?.[part] ?? false;
  }
  const resolved = resolveSchema(field, root);
  return typeof resolved === 'object' ? resolved : {};
}

export function sampleNumberErrors(
  fields: FieldDescriptor[],
  root: JsonSchema | null,
): Array<{ path: string; label: string; message: string }> {
  return fields.flatMap((field) => {
    const errors: string[] = [];
    if (!field.sensitive && typeof field.value === 'number') {
      const schema = fieldSchema(root, field.path);
      const min = field.min ?? schema.minimum;
      const max = field.max ?? schema.maximum;
      if (typeof min === 'number' && field.value < min) errors.push(`不能小于 ${min}`);
      if (typeof max === 'number' && field.value > max) errors.push(`不能大于 ${max}`);
    }
    return [
      ...errors.map((message) => ({ path: field.path.join('.'), label: field.label || field.name, message })),
      ...sampleNumberErrors(field.fields ?? [], root),
      ...(field.items ?? []).flatMap((item) => sampleNumberErrors(item.fields, root)),
    ];
  });
}
