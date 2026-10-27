import { createElement, useState } from 'react';
import { api, type PowerState } from '../../api/endpoints';
import type { Result } from '../../api/types';
import { useMutation, useQuery, type UseQueryResult } from '../../data/useQuery';
import { POLL, QK } from '../../data/queryKeys';
import { infoBar } from '../../notifications/infoBar';
import { runtimeSummary } from './systemPresentation';

async function readState<T>(request: Promise<T | null>, label: string): Promise<T> {
  const result = await request;
  if (result == null) throw new Error(label + '暂时无法读取，稍后会自动重试');
  return result;
}

async function confirmedAction<T extends { message?: string; ok?: boolean }>(
  request: Promise<Result<T>>,
): Promise<T> {
  const result = await request;
  if (!result?.ok || !result.data || result.data.ok === false) {
    throw new Error(result?.error || result?.data?.message || '未收到操作成功确认，请刷新状态后重试');
  }
  return result.data;
}

/** 状态刷新不重置维护表单或确认弹窗。 */
export function useSystemData(hours: number) {
  const services = useQuery(QK.services, () => readState(api.services(), '宿主服务'), {
    interval: POLL.services,
  });
  const tasks = useQuery(QK.tasks, () => readState(api.tasks(), '任务状态'), { interval: POLL.tasks });
  const usage = useQuery(QK.usage + ':' + hours, () => readState(api.statsUsage(hours), '模型用量'), {
    interval: POLL.usage,
    deps: [hours],
  });
  const system = useQuery(QK.system, () => readState(api.system(), '主机信息'), { interval: POLL.system });
  const power = useQuery(QK.power, () => readState(api.powerStatus(), '运行状态'), { interval: POLL.power });
  const queries = [services, tasks, usage, system, power];
  return { services, tasks, usage, system, power, queries };
}

function notifyControl(title: string, message?: string) {
  infoBar({ title, tone: 'ok', details: message ? createElement('p', null, message) : undefined });
}

/** 运行请求共用错误清理，分别保留忙碌状态和二次确认。 */
export function useRuntimeControls(power: UseQueryResult<PowerState>) {
  const [reason, setReason] = useState('');
  const [controlsOpen, setControlsOpen] = useState(false);
  const [restartOpen, setRestartOpen] = useState(false);
  const [shutdownOpen, setShutdownOpen] = useState(false);
  const doStandby = useMutation(() => confirmedAction(api.standbyEnter(reason)), {
    invalidate: [QK.power],
    onSuccess: (result) => notifyControl('已请求进入待机', result.message),
  });
  const doResume = useMutation(() => confirmedAction(api.resume(reason)), {
    invalidate: [QK.power],
    onSuccess: (result) => notifyControl('已请求启动运行', result.message),
  });
  const doReboot = useMutation(() => confirmedAction(api.reboot(reason)), {
    invalidate: [QK.power],
    onSuccess: (result) => notifyControl('已请求软重启运行', result.message),
  });
  const doOnebot = useMutation((enabled: boolean) => confirmedAction(api.setStandbyOnebot(enabled)), {
    invalidate: [QK.power],
    onSuccess: (result) => notifyControl('已更新 OneBot 连接设置', result.message),
  });
  const doRestart = useMutation(() => confirmedAction(api.restart()), {
    onSuccess: (result) => {
      notifyControl('已请求重启进程', result.message);
      setRestartOpen(false);
    },
  });
  const doShutdown = useMutation(() => confirmedAction(api.shutdownProcess()), {
    onSuccess: (result) => {
      notifyControl('已请求关闭进程', result.message || '清理完成后进程会退出。');
      setShutdownOpen(false);
    },
  });

  const powerState = power.data;
  const controlBusy = !!powerState?.transition || !!doStandby.busy || !!doResume.busy || !!doReboot.busy;
  const actionError =
    doStandby.error ||
    doResume.error ||
    doReboot.error ||
    doOnebot.error ||
    doRestart.error ||
    doShutdown.error;
  const runControl = (action: () => Promise<unknown>) => {
    [doStandby, doResume, doReboot, doOnebot, doRestart, doShutdown].forEach((mutation) => mutation.reset());
    return action();
  };

  return {
    reason,
    setReason,
    controlsOpen,
    setControlsOpen,
    restartOpen,
    setRestartOpen,
    shutdownOpen,
    setShutdownOpen,
    doStandby,
    doResume,
    doReboot,
    doOnebot,
    doRestart,
    doShutdown,
    controlBusy,
    actionError,
    runControl,
    powerState,
    ...runtimeSummary(powerState, power.loading, power.error),
  };
}
export type SystemData = ReturnType<typeof useSystemData>;
export type RuntimeControls = ReturnType<typeof useRuntimeControls>;
