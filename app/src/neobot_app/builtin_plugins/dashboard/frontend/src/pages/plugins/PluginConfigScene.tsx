import type { FieldDescriptor, JsonSchema, PluginGuideStep } from '../../api/types';
import SchemaForm from '../../components/SchemaForm';
import { getPath } from '../../utils/paths';
import { initialActionInput, resolveSchema } from './pluginActionSchema';
import { sampleField, sampleNumberErrors, sampleValues, schemaFields } from './pluginConfigSamples';

interface Props {
  pluginId: string;
  schema: JsonSchema | null;
  step: PluginGuideStep;
  fields?: FieldDescriptor[];
}

function findField(fields: FieldDescriptor[], path: string): FieldDescriptor | undefined {
  for (const field of fields) {
    if (field.path.join('.') === path) return field;
    const nested = findField(field.fields ?? [], path);
    if (nested) return nested;
  }
}

function fieldSchema(root: JsonSchema | null, path: Array<string | number>): JsonSchema | null {
  if (root === null) return null;
  let field: JsonSchema = root;
  for (const key of path) {
    const parent = resolveSchema(field, root);
    if (typeof parent !== 'object' || !parent.properties?.[key]) return null;
    field = parent.properties[key];
  }
  return resolveSchema(field, root);
}

const phases = [
  ['start', '初始表单'],
  ['edit', '填写字段'],
  ['validate', '校验样例'],
  ['save', '模拟保存'],
  ['saved', '查看生效'],
] as const;

function FullFormScene({ pluginId, schema, step, fields: liveFields }: Props) {
  const fields = (liveFields?.length ? liveFields : schemaFields(schema)).map((field) =>
    sampleField(field, getPath(step.example, field.path), schema),
  );
  const values = sampleValues(fields);
  const errors = step.form === 'validate' ? sampleNumberErrors(fields, schema) : [];
  const phase = step.form ?? 'start';
  const index = phases.findIndex(([value]) => value === phase);
  const status =
    phase === 'validate'
      ? errors.length
        ? '样例存在校验错误，请先修正字段。'
        : '样例数值范围检查通过。'
      : phase === 'save'
        ? '正在演示保存位置，不会写入配置。'
        : phase === 'saved'
          ? '样例已模拟保存；真实配置的生效状态以保存结果为准。'
          : phase === 'edit'
            ? '按步骤填写合成样例，未修改真实配置。'
            : '从空白或公开默认值开始，不读取当前配置。';
  return (
    <div className="ponder-synthetic-stage ponder-config-scene ponder-form-scene" data-form-phase={phase}>
      <div className="ponder-stage-heading">
        <span>配置表单</span>
        <span>独立样例 · 不会保存</span>
      </div>
      <div className="ponder-config-content">
        <p className="ponder-config-path">插件管理 / {pluginId} / 配置表单</p>
        <ol className="ponder-form-phases" aria-label="表单演示流程">
          {phases.map(([value, label], phaseIndex) => (
            <li
              key={value}
              aria-current={phase === value ? 'step' : undefined}
              data-complete={phaseIndex < index || undefined}
            >
              <span aria-hidden="true">{phaseIndex + 1}</span>
              {label}
            </li>
          ))}
        </ol>
        <div
          data-ponder-config-root
          data-ponder-control={
            step.target === 'config' && phase !== 'save' && phase !== 'saved' ? '' : undefined
          }
        >
          <SchemaForm
            key={JSON.stringify([phase, step.example])}
            fields={fields}
            values={values}
            disabled
            onChange={() => {}}
            showReloadSummary={false}
          />
        </div>
        <div className={'ponder-form-status' + (errors.length ? ' is-error' : '')} role="status">
          <strong>{status}</strong>
          {errors.length > 0 && (
            <ul>
              {errors.map((error) => (
                <li key={error.path}>
                  <span>{error.label}</span>：{error.message}
                </li>
              ))}
            </ul>
          )}
          {phase === 'validate' && (
            <p>这里只检查样例的数值范围；真实保存仍由后端完整校验，凭据请在真实表单中填写。</p>
          )}
        </div>
        <footer
          className="ponder-form-save"
          data-ponder-control={phase === 'save' || phase === 'saved' ? '' : undefined}
        >
          <div>
            <strong>{phase === 'saved' ? '模拟保存完成' : '保存配置'}</strong>
            <p>教学演示，不会调用保存接口或执行插件动作。</p>
          </div>
          <button type="button" className="btn primary" disabled>
            {phase === 'saved' ? '已模拟保存' : '模拟保存'}
          </button>
        </footer>
      </div>
    </div>
  );
}

export default function PluginConfigScene({ pluginId, schema, step, fields: liveFields }: Props) {
  if (step.form || step.target === 'config') {
    return <FullFormScene pluginId={pluginId} schema={schema} step={step} fields={liveFields} />;
  }
  const path = step.target.slice('config.'.length).split('.');
  const name = path.at(-1)!;
  const field = fieldSchema(schema, path);
  const declared = getPath(step.example, path);
  const sample = declared !== undefined ? declared : (step.example?.[name] ?? initialActionInput(field));
  const live = findField(liveFields ?? [], path.join('.'));
  const source = live ?? findField(schemaFields(schema), path.join('.'));
  const descriptor = source ? sampleField(source, sample, schema) : undefined;
  const sensitive = descriptor?.sensitive === true;
  if (descriptor) {
    // 名称、路径和控件沿用实际配置表单；演示ID独立，避免覆盖底层编辑器标签。
    descriptor.label = descriptor.label || descriptor.name;
    descriptor.name = name;
    descriptor.path = path;
    descriptor.input_id = `ponder-config-${path.map(encodeURIComponent).join('-')}`;
    if (sensitive) descriptor.value = '';
  }
  const values = descriptor ? sampleValues([descriptor]) : {};
  return (
    <div className="ponder-synthetic-stage ponder-config-scene">
      <div className="ponder-stage-heading">
        <span>配置表单</span>
        <span>样例</span>
      </div>
      <div className="ponder-config-content">
        <p className="ponder-config-path">插件管理 / {pluginId} / 配置表单</p>
        <div data-ponder-control>
          {descriptor ? (
            <SchemaForm
              fields={[descriptor]}
              values={values}
              disabled
              onChange={() => {}}
              showReloadSummary={false}
            />
          ) : (
            <div className="ponder-config-value">
              <code>{path.join('.')}</code>
              <p>此字段暂无可用的表单描述。</p>
            </div>
          )}
        </div>
        {sensitive && <p>在真实配置中填写，说明书不展示凭据。</p>}
      </div>
    </div>
  );
}
