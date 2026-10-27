import { useState } from 'react';
import { useAuthGate } from '../auth/AuthContext';
import Icon from '../components/Icon';
import Button from '../components/ui/Button';
import PageHeader from '../components/ui/PageHeader';
import InlineAlert from '../components/ui/InlineAlert';
import { useSystemData, useRuntimeControls } from './system/useSystemState';
import { hostDetails, systemMetrics, type SystemDetail } from './system/systemPresentation';
import {
  SystemActivityPanel,
  SystemUsagePanel,
  SystemResourceStrip,
  SystemDetailDialogs,
} from './system/SystemPanels';
import SystemMaintenanceDialogs from './system/SystemMaintenanceDialogs';

export default function System() {
  const { canManage } = useAuthGate();
  const readOnly = canManage === false;
  const [hours, setHours] = useState(24);
  const [detail, setDetail] = useState<SystemDetail | null>(null);
  const [taskDetail, setTaskDetail] = useState<unknown>(null);
  const [compactView, setCompactView] = useState<'activity' | 'usage'>('activity');
  const { services, tasks, usage, system, power, queries } = useSystemData(hours);
  const controls = useRuntimeControls(power);
  const {
    controlsOpen,
    setControlsOpen,
    restartOpen,
    shutdownOpen,
    actionError,
    powerState,
    runtimeLabel,
    runtimeDescription,
    runtimeIdle,
  } = controls;
  const sys = system.data || {};
  const metrics = systemMetrics(sys);
  const hostDetail = hostDetails(sys, metrics);
  return (
    <div className="page page--viewport system-page system-workspace">
      <PageHeader
        title="系统状态"
        actions={
          <Button className="system-settings-button" onClick={() => setControlsOpen(true)}>
            <Icon name="settings" />
            运行设置
          </Button>
        }
      />
      {readOnly && (
        <InlineAlert tone="info" title="当前会话只读">
          运行操作需要管理权限。
        </InlineAlert>
      )}
      {queries.some((query) => query.error) && (
        <InlineAlert
          tone="warning"
          title="部分系统状态暂时无法读取"
          actions={
            <Button
              size="sm"
              disabled={queries.some((query) => query.loading)}
              onClick={() =>
                void Promise.all(queries.filter((query) => query.error).map((query) => query.refetch()))
              }
            >
              重试读取
            </Button>
          }
        >
          已保留最近一次数据，稍后会自动重试。
        </InlineAlert>
      )}
      {actionError && !controlsOpen && !restartOpen && !shutdownOpen && (
        <InlineAlert tone="error" title={actionError} />
      )}

      <div className="system-runtime-line">
        <span className={'system-runtime-status' + (runtimeIdle ? ' is-idle' : '')}>
          <i />
          {runtimeLabel}
        </span>
        <span className="system-host-name" title={sys.hostname}>
          {sys.hostname || (system.loading ? '正在读取主机' : '主机信息待确认')}
        </span>
        <span className="system-runtime-note" title={powerState?.reason || runtimeDescription}>
          {powerState?.reason || runtimeDescription}
        </span>
        <button className="system-text-button" onClick={() => setDetail(hostDetail)}>
          主机信息
          <Icon name="chevron" size={14} />
        </button>
      </div>

      <SystemResourceStrip metrics={metrics} />

      <div className="system-compact-switch" aria-label="系统信息视图">
        <button aria-pressed={compactView === 'activity'} onClick={() => setCompactView('activity')}>
          服务与任务
        </button>
        <button aria-pressed={compactView === 'usage'} onClick={() => setCompactView('usage')}>
          模型用量
        </button>
      </div>
      <div className="system-panels" data-view={compactView}>
        <SystemActivityPanel
          services={services}
          tasks={tasks}
          setDetail={setDetail}
          setTaskDetail={setTaskDetail}
        />
        <SystemUsagePanel usage={usage} hours={hours} setHours={setHours} setDetail={setDetail} />
      </div>
      <SystemMaintenanceDialogs controls={controls} readOnly={readOnly} />
      <SystemDetailDialogs
        detail={detail}
        setDetail={setDetail}
        taskDetail={taskDetail}
        setTaskDetail={setTaskDetail}
      />
    </div>
  );
}
