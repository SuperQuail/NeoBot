// HTTP 请求结果与通用趋势序列。

/** getResult 的返回值：带 HTTP 状态码，编辑器需要区分校验失败与网络错误 */
export interface Result<T> {
  ok: boolean;
  data: T | null;
  error: string | null;
  status: number;
}

/** 采样点：趋势接口共用的最小结构 */
export interface SeriesPoint {
  /** 消息趋势以本地日期汇总；延迟采样为 Unix 秒时间戳。 */
  date?: string;
  ts?: number;
  at?: string;
  count?: number;
  ms?: number;
}

export interface SeriesPayload<T = SeriesPoint> {
  series?: T[];
  total?: number;
  last_id?: number;
  current_ms?: number;
  avg_ms?: number;
  success_rate?: number;
}
