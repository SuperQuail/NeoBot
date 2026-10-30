import type { FieldDescriptor, JsonSchema } from '../../api/types';
import { SECRET_RE } from '../../components/schema/fieldTypes';

type SchemaObject = Exclude<JsonSchema, boolean>;

export function initialActionInput(schema: JsonSchema | null): unknown {
  if (schema === null || typeof schema !== 'object') return {};
  if (schema.default !== undefined) return structuredClone(schema.default);
  switch (schema.type) {
    case 'array':
      return [];
    case 'string':
      return '';
    case 'integer':
    case 'number':
      return 0;
    case 'boolean':
      return false;
    case 'null':
      return null;
    default:
      return initialActionValues(schema);
  }
}

export function resolveSchema(schema: JsonSchema, root: JsonSchema): JsonSchema {
  if (typeof schema !== 'object' || !schema.$ref) return schema;
  const { $ref, ...siblings } = schema;
  if (!$ref.startsWith('#/')) return false;
  let value: unknown = root;
  for (const part of $ref.slice(2).split('/')) {
    if (typeof value !== 'object' || value === null) return false;
    const key = part.replace(/~1/g, '/').replace(/~0/g, '~');
    value = (value as Record<string, unknown>)[key];
  }
  // 默认值和标题可声明在引用点，展开枚举定义时仍需保留这些字段元数据。
  return typeof value === 'object' && value !== null ? { ...(value as SchemaObject), ...siblings } : false;
}

export function initialActionValues(schema: JsonSchema | null): Record<string, unknown> {
  if (schema === null || typeof schema !== 'object') return {};
  if (schema.default && typeof schema.default === 'object' && !Array.isArray(schema.default)) {
    return structuredClone(schema.default as Record<string, unknown>);
  }
  const entries: Array<[string, unknown]> = [];
  for (const [key, raw] of Object.entries(schema.properties ?? {})) {
    const field = resolveSchema(raw, schema);
    if (typeof field !== 'object') continue;
    const value =
      field.default === undefined && field.type === 'boolean' && schema.required?.includes(key)
        ? false
        : field.default;
    if (value !== undefined) entries.push([key, structuredClone(value)]);
  }
  return Object.fromEntries(entries);
}

/** 只映射无损的标量；对象、数组、联合与未知类型保留 JSON 编辑。 */
export function actionFields(
  schema: JsonSchema | null,
  values: Record<string, unknown>,
): FieldDescriptor[] | null {
  if (schema === null) return [];
  if (typeof schema !== 'object' || schema.$ref || schema.anyOf || schema.oneOf || schema.allOf) return null;
  if (schema.type && schema.type !== 'object') return null;
  if (schema.additionalProperties !== undefined && schema.additionalProperties !== false) return null;
  if (!schema.properties) return Object.keys(schema).length === 0 ? [] : null;
  const descriptors: FieldDescriptor[] = [];
  for (const [key, raw] of Object.entries(schema.properties)) {
    const field = resolveSchema(raw, schema);
    if (typeof field !== 'object' || field.anyOf || field.oneOf || field.allOf || field.$ref) return null;
    const type = field.type;
    if (!['string', 'integer', 'number', 'boolean'].includes(String(type))) return null;
    const options = field.enum;
    if (options?.some((item) => item !== null && typeof item === 'object')) return null;
    if (options && new Set(options.map(String)).size !== options.length) return null;
    const descriptor: FieldDescriptor = {
      name: field.title || key,
      path: [key],
      kind: 'scalar',
      type: options?.length
        ? 'str'
        : { string: 'str', integer: 'int', number: 'float', boolean: 'bool' }[String(type)],
      value: values[key],
      default: field.default,
      description: field.description,
      readonly: field.readOnly === true,
      sensitive:
        type === 'string' && (field.writeOnly === true || field.format === 'password' || SECRET_RE.test(key)),
      min: field.minimum,
      max: field.maximum,
    };
    if (options?.length) {
      const choices = options.map(String);
      descriptor.options = choices.includes('') ? choices : ['', ...choices];
      descriptor.option_labels = { '': '请选择' };
      descriptor.options_strict = true;
    }
    descriptors.push(descriptor);
  }
  return descriptors;
}

export function actionFieldValue(schema: JsonSchema | null, key: string, value: unknown): unknown {
  if (schema === null || typeof schema !== 'object') return value;
  const field = resolveSchema(schema.properties?.[key] ?? false, schema);
  if (typeof field !== 'object' || !field.enum) return value;
  return field.enum.find((item) => String(item) === String(value));
}
