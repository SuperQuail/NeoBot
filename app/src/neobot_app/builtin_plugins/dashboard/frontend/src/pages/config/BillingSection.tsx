// pages/config/BillingSection.tsx —— 模型编辑弹窗的「计费」区（spec(4) Part A）
//
// 计价脚本按模型条目绑定：billing_script 选脚本（留空 = 固定计费），
// billing_config 传脚本参数（键值行），并可只读试算（POST /api/config/billing/preview）。
import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../../api/endpoints';
import type { BillingPayload, BillingPreviewResult } from '../../api/types';
import { toast } from '../../components/Toast';

export interface BillingSectionProps {
  modelKey?: string;
  script: string;
  config: Record<string, unknown>;
  disabled?: boolean;
  onChangeScript: (value: string) => void;
  onChangeConfig: (value: Record<string, unknown>) => void;
}

interface ConfigPair {
  key: string;
  value: string;
}

function valueToText(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function toPairs(config?: Record<string, unknown>): ConfigPair[] {
  return Object.entries(config || {}).map(([key, value]) => ({ key, value: valueToText(value) }));
}

/** 键值行 -> 脚本参数：能解析成数字/布尔就转，其余保留字符串。 */
export function parseConfigValue(text: string): unknown {
  const trimmed = text.trim();
  if (trimmed === '') return '';
  if (trimmed === 'true') return true;
  if (trimmed === 'false') return false;
  if (trimmed === 'null') return null;
  if (/^-?\d+(\.\d+)?([eE][-+]?\d+)?$/.test(trimmed)) {
    const num = Number(trimmed);
    if (!Number.isNaN(num)) return num;
  }
  return text;
}

export function pairsToConfig(pairs: ConfigPair[]): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const pair of pairs) {
    const key = pair.key.trim();
    if (!key) continue;
    out[key] = parseConfigValue(pair.value);
  }
  return out;
}

function fmtCost(value?: number | null): string {
  const num = Number(value || 0);
  if (num === 0) return '¥0';
  if (Math.abs(num) < 0.01) return '¥' + num.toFixed(6);
  if (Math.abs(num) < 1) return '¥' + num.toFixed(4);
  return '¥' + num.toFixed(2);
}

/** 来源标签（与用量页共用同一套口径） */
export function sourceLabel(source?: string | null): string {
  const text = String(source || 'builtin');
  if (text.startsWith('script:')) return '脚本: ' + (text.slice(7) || '未命名');
  if (text.startsWith('fallback:')) return '兜底: ' + (text.slice(9) || 'unknown');
  return '固定计费';
}

function BillingSection({
  modelKey,
  script,
  config,
  disabled,
  onChangeScript,
  onChangeConfig,
}: BillingSectionProps) {
  const [overview, setOverview] = useState<BillingPayload | null>(null);
  const [pairs, setPairs] = useState<ConfigPair[]>(() => toPairs(config));
  const [busy, setBusy] = useState('');
  const [inputTokens, setInputTokens] = useState('1000000');
  const [outputTokens, setOutputTokens] = useState('1000000');
  const [occurredAt, setOccurredAt] = useState('');
  const [preview, setPreview] = useState<BillingPreviewResult | null>(null);

  const load = useCallback(async () => {
    const result = await api.configBilling();
    if (!result.ok || !result.data) {
      toast(result.error || '读取计费脚本清单失败', 'err');
      return;
    }
    setOverview(result.data);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    setPairs(toPairs(config));
  }, [config]);

  const options = useMemo(() => {
    const names = [...(overview?.scripts || [])];
    for (const name of overview?.templates || []) {
      if (!names.includes(name)) names.push(name);
    }
    return names.sort((a, b) => a.localeCompare(b));
  }, [overview]);

  const binding = useMemo(
    () => (overview?.bindings || []).find((item) => item.model_key === modelKey) || null,
    [overview, modelKey],
  );

  const commitPairs = (next: ConfigPair[]) => {
    setPairs(next);
    onChangeConfig(pairsToConfig(next));
  };

  const runPreview = async () => {
    setBusy('preview');
    const usage: Record<string, unknown> = {};
    const input = Number(inputTokens);
    const output = Number(outputTokens);
    if (!Number.isNaN(input) && inputTokens.trim() !== '') usage.input_tokens = input;
    if (!Number.isNaN(output) && outputTokens.trim() !== '') usage.output_tokens = output;
    const body: {
      model_key?: string;
      billing_script?: string;
      billing_config?: Record<string, unknown>;
      usage?: Record<string, unknown>;
      occurred_at?: string;
    } = {
      billing_script: script,
      billing_config: pairsToConfig(pairs),
      usage,
    };
    if (modelKey) body.model_key = modelKey;
    if (occurredAt) body.occurred_at = new Date(occurredAt).toISOString();
    const result = await api.configBillingPreview(body);
    setBusy('');
    if (!result.ok || !result.data) {
      toast(result.error || '试算失败', 'err');
      return;
    }
    setPreview(result.data);
  };

  const reload = async () => {
    setBusy('reload');
    const result = await api.configBillingReload();
    setBusy('');
    if (!result.ok) {
      toast(result.error || '重载计费脚本失败', 'err');
      return;
    }
    const errors = Object.keys(result.data?.errors || {});
    toast(
      errors.length ? '重载完成，但有脚本加载失败: ' + errors.join('、') : '计费脚本已重载',
      errors.length ? 'err' : 'ok',
    );
    load();
  };

  return (
    <section className="cfg-group billing-section">
      <div className="cfg-section-heading">
        <h3>计费</h3>
        <span className="muted small">
          {overview?.enabled
            ? '已启用计价脚本（[billing].enabled=true）'
            : '全局关闭：全部模型走固定计费（[billing].enabled=false）'}
        </span>
        <div className="spacer" />
        <button type="button" className="btn-sm" disabled={!!disabled || !!busy} onClick={reload}>
          {busy === 'reload' ? '重载中…' : '重载脚本'}
        </button>
      </div>

      <div className="cfg-row">
        <div className="cfg-label"><label htmlFor="billing-script">计价脚本</label></div>
        <div className="cfg-control">
          <select
            id="billing-script"
            className="input"
            value={script || ''}
            disabled={!!disabled}
            onChange={(event) => onChangeScript(event.target.value)}
          >
            <option value="">（留空 = 固定计费）</option>
            {options.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
            {script && !options.includes(script) && <option value={script}>{script}（文件缺失）</option>}
          </select>
          <p className="muted small cfg-hint">
            对应 &lt;数据目录&gt;/Billing/&lt;名字&gt;.py；留空即按模型价格表固定计费。
            生效需 [billing].enabled=true（全局配置页）。
          </p>
        </div>
      </div>

      {script && binding && !binding.available && (
        <p className="field-error" role="alert">
          脚本不可用：{binding.error || binding.source || '未加载'}
        </p>
      )}

      <div className="cfg-row">
        <div className="cfg-label"><span>脚本参数</span></div>
        <div className="cfg-control">
          {pairs.length === 0 && (
            <p className="muted small">暂无参数；按次计费模板需要 price_per_call</p>
          )}
          {pairs.map((pair, index) => (
            <div className="billing-kv" key={index}>
              <input
                type="text"
                className="input"
                placeholder="键（如 price_per_call）"
                value={pair.key}
                disabled={!!disabled}
                onChange={(event) => {
                  const next = pairs.slice();
                  next[index] = { ...pair, key: event.target.value };
                  commitPairs(next);
                }}
              />
              <input
                type="text"
                className="input"
                placeholder="值（如 0.01）"
                value={pair.value}
                disabled={!!disabled}
                onChange={(event) => {
                  const next = pairs.slice();
                  next[index] = { ...pair, value: event.target.value };
                  commitPairs(next);
                }}
              />
              <button
                type="button"
                className="btn-sm danger"
                disabled={!!disabled}
                onClick={() => commitPairs(pairs.filter((_item, i) => i !== index))}
              >
                删除
              </button>
            </div>
          ))}
          <button
            type="button"
            className="btn-sm"
            disabled={!!disabled}
            onClick={() => commitPairs([...pairs, { key: '', value: '' }])}
          >
            添加参数
          </button>
        </div>
      </div>

      <div className="cfg-row">
        <div className="cfg-label"><span>试算</span></div>
        <div className="cfg-control">
          <div className="billing-kv">
            <input
              type="number"
              min="0"
              className="input"
              placeholder="输入 tokens"
              value={inputTokens}
              disabled={!!disabled}
              onChange={(event) => setInputTokens(event.target.value)}
            />
            <input
              type="number"
              min="0"
              className="input"
              placeholder="输出 tokens"
              value={outputTokens}
              disabled={!!disabled}
              onChange={(event) => setOutputTokens(event.target.value)}
            />
            <input
              type="datetime-local"
              className="input"
              title="发生时间（本地时区）；留空 = 现在。峰谷脚本按此时间判定"
              value={occurredAt}
              disabled={!!disabled}
              onChange={(event) => setOccurredAt(event.target.value)}
            />
            <button type="button" className="btn-sm" disabled={!!disabled || !!busy} onClick={runPreview}>
              {busy === 'preview' ? '试算中…' : '试算'}
            </button>
          </div>
          {preview && (
            <div className="probe-result">
              <p className={preview.source && preview.source.startsWith('script:') ? 'probe-headline ok' : 'probe-headline'}>
                金额 <strong>{fmtCost(preview.cost_cny)}</strong>
                {' · 来源 '}
                <code>{sourceLabel(preview.source)}</code>
                {preview.elapsed_ms != null && <span className="muted small"> · {preview.elapsed_ms} ms</span>}
                {preview.note && <span className="muted small"> · {preview.note}</span>}
              </p>
              {preview.error && <p className="field-error">{preview.error}</p>}
              {preview.components && Object.keys(preview.components).length > 0 && (
                <table className="model-table">
                  <tbody>
                    {Object.entries(preview.components).map(([key, value]) => (
                      <tr key={key}>
                        <th>{key}</th>
                        <td>{fmtCost(value)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              <p className="muted small">
                固定计费对照：{fmtCost(preview.builtin_cost_cny)}
                {preview.local_time
                  ? ' · 判定时间 ' + preview.local_time + (preview.tzname ? ' (' + preview.tzname + ')' : '')
                  : ''}
              </p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

export { BillingSection };
