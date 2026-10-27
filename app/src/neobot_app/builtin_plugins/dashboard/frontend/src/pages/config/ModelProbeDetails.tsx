import type { ModelProbeResult } from '../../api/types';

/** 测试详情由统一通知按需展开，不中断当前模型编辑。 */
export default function ModelProbeDetails({ probe }: { probe: ModelProbeResult }) {
  const rows = [
    { label: '模型引用名', value: <code>{probe.model_ref || '（未保存草稿）'}</code> },
    {
      label: '供应商 / 模型名',
      value: (
        <>
          {probe.provider || '—'} / <code>{probe.model_name || '—'}</code>
        </>
      ),
    },
    { label: '请求地址', value: probe.url || '—' },
    { label: '代理', value: probe.proxy ? '跟随系统代理' : '直连（不使用代理）' },
    { label: '网络可达', value: probe.reachable ? '是' : '否' },
    { label: '鉴权', value: probe.authorized ? '通过' : '未通过' },
    {
      label: '模型是否存在',
      value:
        probe.model_found === true ? '已找到' : probe.model_found === false ? '未在模型列表中' : '未检查',
    },
    {
      label: 'HTTP / 耗时',
      value: (
        <>
          {probe.status ?? '—'} / {probe.latency_ms != null ? `${probe.latency_ms} ms` : '—'}
        </>
      ),
    },
  ];
  return (
    <div className="probe-result">
      <p>{probe.message || (probe.ok ? '连接正常' : '测试未通过')}</p>
      <div className="config-table-scroll">
        <table className="model-table">
          <tbody>
            {rows.map((row) => (
              <tr key={row.label}>
                <th>{row.label}</th>
                <td>{row.value}</td>
              </tr>
            ))}
            {probe.detail && (
              <tr>
                <th>详情</th>
                <td>{probe.detail}</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
