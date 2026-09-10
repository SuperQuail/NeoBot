// vitals.ts —— 把真实系统指标映射成「舰况」四项读数
//
// 面板上不能出现编造的数字，所以这里只做一件事：把 /api/system 的真实字段
// 翻译成舰载术语，并保留原始字段名（raw/source）随时可查。
//   energy     ← 电池电量（读不到电池时用 CPU 余量代替，并在 source 里标注）
//   atmosphere ← 内存可用率（生命保障系统）
//   hull       ← 磁盘可用率（舰体外壳完整度）
//   heat       ← 负载温度（CPU × 0.6 + 内存 × 0.4，或 load average）
//
// 数据每 REFRESH_MS 刷新一次；两次刷新之间由渲染层做插值，
// 让读数平滑跳动而不是每 8 秒硬跳一格。

import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../../api/endpoints';
import type { SystemInfo } from '../../api/types';
import type { Vital } from './types';

const REFRESH_MS = 8000;

/** /api/system 里本文件关心的扩展字段（后端未声明，存在才读取） */
interface SystemExtras {
  battery_percent?: number | null;
  battery_plugged?: boolean | null;
}

export type VitalAvailability = 'ok' | 'partial' | 'unavailable';

export interface VitalsState {
  vitals: Vital[];
  system: SystemInfo | null;
  /** 是否拿到过真实数据 */
  availability: VitalAvailability;
  lastUpdated: number;
  refresh: () => void;
  loading: boolean;
}

const clamp = (value: number) => Math.max(0, Math.min(100, value));

function round(value: number): number {
  return Math.round(value * 10) / 10;
}

/** 由系统快照推导舰况；system 为 null 时返回「数据不可用」的占位读数 */
export function deriveVitals(system: SystemInfo | null): { vitals: Vital[]; availability: VitalAvailability } {
  if (!system) {
    const placeholders: Vital[] = [
      { key: 'energy', label: '能源储备', value: 0, unit: '%', source: '等待舰载主机遥测' },
      { key: 'atmosphere', label: '生命保障', value: 0, unit: '%', source: '等待舰载主机遥测' },
      { key: 'hull', label: '舰体完整度', value: 0, unit: '%', source: '等待舰载主机遥测' },
      { key: 'heat', label: '主机温度', value: 0, unit: '%', source: '等待舰载主机遥测' },
    ];
    return { vitals: placeholders, availability: 'unavailable' };
  }

  const extras = system as SystemInfo & SystemExtras;
  const cpu = typeof system.cpu_percent === 'number' ? clamp(system.cpu_percent) : null;
  const mem = typeof system.mem_percent === 'number' ? clamp(system.mem_percent) : null;
  const disk = typeof system.disk_percent === 'number' ? clamp(system.disk_percent) : null;
  const load = Array.isArray(system.load_average) && system.load_average.length > 0 ? system.load_average[0] : null;
  const cores = system.cpu_count && system.cpu_count > 0 ? system.cpu_count : 1;

  // 能源：优先读电池（笔记本/服务器 UPS），否则用 CPU 余量代表反应堆输出裕度
  const battery = typeof extras.battery_percent === 'number' ? clamp(extras.battery_percent) : null;
  const energyValue = battery ?? (cpu === null ? null : clamp(100 - cpu));
  const energySource =
    battery !== null
      ? `电池电量 ${round(battery)}%（battery_percent）`
      : cpu === null
        ? '无 CPU 遥测'
        : `反应堆裕度 = 100 - CPU ${round(cpu)}%（cpu_percent）`;

  const atmosphereValue = mem === null ? null : clamp(100 - mem);
  const hullValue = disk === null ? null : clamp(100 - disk);
  const heatValue =
    load !== null
      ? clamp((load / cores) * 100)
      : cpu === null || mem === null
        ? (cpu ?? mem)
        : clamp(cpu * 0.6 + mem * 0.4);

  const vitals: Vital[] = [
    {
      key: 'energy',
      label: '能源储备',
      value: energyValue === null ? 0 : round(energyValue),
      unit: '%',
      source: energySource,
    },
    {
      key: 'atmosphere',
      label: '生命保障',
      value: atmosphereValue === null ? 0 : round(atmosphereValue),
      unit: '%',
      source:
        mem === null
          ? '无内存遥测'
          : `可用内存 ${round(100 - mem)}% = 100 - 已用 ${round(mem)}%（mem_percent）`,
    },
    {
      key: 'hull',
      label: '舰体完整度',
      value: hullValue === null ? 0 : round(hullValue),
      unit: '%',
      source:
        disk === null
          ? '无磁盘遥测'
          : `磁盘余量 ${round(100 - disk)}% = 100 - 已用 ${round(disk)}%（disk_percent）`,
    },
    {
      key: 'heat',
      label: '主机温度',
      value: heatValue === null ? 0 : round(heatValue),
      unit: '%',
      source:
        load !== null
          ? `load average ${round(load)} / ${cores} 核`
          : cpu === null || mem === null
            ? '遥测不完整，按可用项估算'
            : `加权负载 = CPU ${round(cpu)}% × 0.6 + 内存 ${round(mem)}% × 0.4`,
    },
  ];

  const missing = [energyValue, atmosphereValue, hullValue, heatValue].filter((value) => value === null).length;
  return { vitals, availability: missing === 0 ? 'ok' : missing >= 3 ? 'unavailable' : 'partial' };
}

/** 单项读数是否处于警戒区间（舰内警报与面板高亮共用同一判定） */
export function vitalStatus(key: Vital['key'], value: number): 'nominal' | 'caution' | 'critical' {
  const caution = key === 'heat' ? 70 : 35;
  const critical = key === 'heat' ? 88 : 15;
  if (key === 'heat') {
    if (value >= critical) return 'critical';
    return value >= caution ? 'caution' : 'nominal';
  }
  if (value <= critical) return 'critical';
  return value <= caution ? 'caution' : 'nominal';
}

/** 是否有任何一项处于严重区间（触发舰内红色警报与音效） */
export function hasCritical(vitals: Vital[]): Vital | null {
  return vitals.find((vital) => vitalStatus(vital.key, vital.value) === 'critical') ?? null;
}

export function useVitals(pollMs: number = REFRESH_MS): VitalsState {
  const [system, setSystem] = useState<SystemInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState(0);
  const mounted = useRef(true);
  const timer = useRef<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    const data = await api.system();
    if (!mounted.current) return;
    // api.system() 失败时返回 null：保留上一次读数，避免面板闪成 0
    if (data) {
      setSystem(data);
      setLastUpdated(Date.now());
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    mounted.current = true;
    void load();
    timer.current = window.setInterval(() => void load(), pollMs);
    return () => {
      mounted.current = false;
      if (timer.current !== null) window.clearInterval(timer.current);
    };
  }, [load, pollMs]);

  const { vitals, availability } = deriveVitals(system);

  return {
    vitals,
    system,
    availability,
    lastUpdated,
    loading,
    refresh: () => void load(),
  };
}
