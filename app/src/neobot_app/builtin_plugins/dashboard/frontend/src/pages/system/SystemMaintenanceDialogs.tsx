import { useState } from 'react';
import Icon from '../../components/Icon';
import Modal, { ModalActions } from '../../components/Modal';
import PasswordSettings, { ChangePasswordDialog } from '../../components/PasswordSettings';
import StarshipToggle from '../../components/StarshipToggle';
import Button from '../../components/ui/Button';
import InlineAlert from '../../components/ui/InlineAlert';
import type { RuntimeControls } from './useSystemState';

export default function SystemMaintenanceDialogs({
  controls,
  readOnly,
}: {
  controls: RuntimeControls;
  readOnly: boolean;
}) {
  const [passwordOpen, setPasswordOpen] = useState(false);
  const {
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
    standby,
    powerAvailable,
    runtimeLabel,
    connectOnebot,
    runtimeDescription,
    runtimeIdle,
  } = controls;
  return (
    <>
      <Modal
        open={controlsOpen}
        title="运行设置"
        className="system-controls-modal"
        onClose={() => setControlsOpen(false)}
        footer={
          <div className="system-process-controls">
            <div>
              <strong>进程操作</strong>
              <span>会断开面板与平台连接</span>
            </div>
            <Button
              disabled={readOnly || !!doRestart.busy}
              onClick={() => {
                setControlsOpen(false);
                setRestartOpen(true);
              }}
            >
              {doRestart.busy ? '重启中…' : '重启进程'}
            </Button>
            <Button
              variant="danger"
              disabled={readOnly || !!doShutdown.busy}
              onClick={() => {
                setControlsOpen(false);
                setShutdownOpen(true);
              }}
            >
              {doShutdown.busy ? '关闭中…' : '关闭 NeoBot'}
            </Button>
          </div>
        }
      >
        <section className="system-settings-section" aria-label="运行控制">
          <div className="system-settings-heading">
            <h4>运行控制</h4>
            <span className={'tag ' + (runtimeIdle ? 'warn' : 'ok')}>{runtimeLabel}</span>
          </div>
          <p className="system-settings-description">{runtimeDescription}</p>
          <div className="system-runtime-controls">
            <label className="field">
              <span>原因（可选）</span>
              <input
                className="input"
                value={reason}
                placeholder="例如：维护模型配置中"
                disabled={readOnly || controlBusy}
                onChange={(event) => setReason(event.target.value)}
              />
            </label>
            <div className="system-control-actions">
              <Button
                disabled={readOnly || !powerAvailable || standby || controlBusy}
                onClick={() => void runControl(() => doStandby.run())}
              >
                <Icon name="pause" />
                {doStandby.busy ? '进入中…' : '进入待机'}
              </Button>
              {standby ? (
                <Button
                  variant="primary"
                  disabled={readOnly || !powerAvailable || controlBusy}
                  onClick={() => void runControl(() => doResume.run())}
                >
                  {doResume.busy ? '启动中…' : '启动运行'}
                </Button>
              ) : (
                <Button
                  variant="primary"
                  disabled={readOnly || !powerAvailable || controlBusy}
                  onClick={() => void runControl(() => doReboot.run())}
                >
                  {doReboot.busy ? '软重启中…' : '软重启运行'}
                </Button>
              )}
            </div>
          </div>
          <label
            className="system-connection-setting"
            htmlFor="system-standby-onebot"
            aria-label="待机时保持 OneBot 连接"
          >
            <span>
              <strong>待机时保持 OneBot 连接</strong>
              <small>
                {!powerAvailable
                  ? '当前连接设置尚未确认'
                  : connectOnebot
                    ? '待机期间不断开连接，恢复后继续使用'
                    : '进入待机时断开连接，减少无效心跳'}
              </small>
            </span>
            <input
              id="system-standby-onebot"
              type="checkbox"
              checked={connectOnebot}
              disabled={readOnly || !powerAvailable || controlBusy || !!doOnebot.busy}
              onChange={(event) => void runControl(() => doOnebot.run(event.target.checked))}
            />
          </label>
          <details className="standby-explainer">
            <summary>运行操作说明</summary>
            <div className="standby-hints muted small">
              <span>进入待机：停掉回复与记忆管线，只保留面板与命令。</span>
              <span>软重启运行：按当前配置重建运行时，不重启进程。</span>
              <span>重启进程：加载代码改动，会短暂断线。</span>
              <span>关闭 NeoBot：优雅收尾后退出进程（记忆总结可能数分钟）；退出后需由外部再次启动。</span>
            </div>
          </details>
        </section>
        <section className="system-settings-section" aria-label="可选扩展">
          <h4>可选扩展</h4>
          <StarshipToggle readOnly={readOnly} disabled={controlBusy} />
        </section>
        <section className="system-settings-section system-settings-security" aria-label="面板安全">
          <div>
            <h4>面板安全</h4>
            <p className="system-settings-description">修改密码后，所有会话需重新登录。</p>
          </div>
          <PasswordSettings
            onOpen={() => {
              setControlsOpen(false);
              setPasswordOpen(true);
            }}
          />
        </section>
        {!powerAvailable && (
          <InlineAlert
            tone="warning"
            title={
              powerState?.available === false
                ? '待机服务不可用，请重启 NeoBot'
                : '运行状态尚未确认，稍后会自动重试'
            }
          />
        )}
        {actionError && <InlineAlert tone="error" title={actionError} />}
      </Modal>
      <ChangePasswordDialog
        open={passwordOpen}
        onClose={() => {
          setPasswordOpen(false);
          setControlsOpen(true);
        }}
      />
      <Modal
        open={shutdownOpen}
        title="关闭 NeoBot"
        onClose={() => {
          if (!doShutdown.busy) setShutdownOpen(false);
        }}
      >
        <p className="muted">
          关闭会先跑完收尾（关闭冲刷、记忆总结等，可能持续数分钟），完成后进程退出。退出后本面板与平台连接都会断开，需要由外部（桌面端、systemd、容器编排）再次启动。
        </p>
        <p className="muted small">若只想重新加载代码改动，请用「重启进程」。</p>
        {doShutdown.error && <InlineAlert tone="error" title={doShutdown.error} />}
        <ModalActions>
          <Button disabled={!!doShutdown.busy} onClick={() => setShutdownOpen(false)}>
            取消
          </Button>
          <Button
            variant="danger"
            disabled={readOnly || !!doShutdown.busy}
            onClick={() => void runControl(() => doShutdown.run())}
          >
            {doShutdown.busy ? '关闭中…' : '确认关闭'}
          </Button>
        </ModalActions>
      </Modal>
      <Modal
        open={restartOpen}
        title="重启进程"
        onClose={() => {
          if (!doRestart.busy) setRestartOpen(false);
        }}
      >
        <p className="muted">
          重启进程用于加载代码改动，会短暂断线（面板与平台连接都会中断几秒到十几秒）。只想按当前配置重建运行时，请用「软重启运行」。
        </p>
        {doRestart.error && <InlineAlert tone="error" title={doRestart.error} />}
        <ModalActions>
          <Button disabled={!!doRestart.busy} onClick={() => setRestartOpen(false)}>
            取消
          </Button>
          <Button
            variant="danger"
            disabled={readOnly || !!doRestart.busy}
            onClick={() => void runControl(() => doRestart.run())}
          >
            {doRestart.busy ? '重启中…' : '确认重启'}
          </Button>
        </ModalActions>
      </Modal>
    </>
  );
}
