/** 共享自动更新时钟：同一订阅不重叠请求，隐藏/离线暂停，回来后补上错过的读取。 */
export function startAutoRefresh(
  read: () => unknown | Promise<unknown>,
  interval: number,
  canRun: () => boolean = () => true,
) {
  if (interval <= 0) return () => {};
  let disposed = false;
  let running = false;
  let lastStarted = Date.now();
  let timer: ReturnType<typeof setTimeout> | undefined;
  const available = () => document.visibilityState !== 'hidden' && navigator.onLine !== false;
  const schedule = (delay = interval) => {
    clearTimeout(timer);
    if (!disposed) timer = setTimeout(() => void update(), delay);
  };
  const update = async () => {
    if (disposed || running) return;
    if (!available() || !canRun()) {
      schedule();
      return;
    }
    running = true;
    lastStarted = Date.now();
    try {
      await read();
    } catch {
      // 错误由查询/编辑器保留；下一周期仍能恢复，不产生未处理拒绝或重复通知。
    } finally {
      running = false;
      schedule();
    }
  };
  const resume = () => {
    if (!disposed && !running && available() && Date.now() - lastStarted >= interval) void update();
  };
  const afterFocusOut = () => queueMicrotask(resume);
  document.addEventListener('visibilitychange', resume);
  document.addEventListener('focusout', afterFocusOut);
  window.addEventListener('focus', resume);
  window.addEventListener('online', resume);
  schedule();
  return () => {
    disposed = true;
    clearTimeout(timer);
    document.removeEventListener('visibilitychange', resume);
    document.removeEventListener('focusout', afterFocusOut);
    window.removeEventListener('focus', resume);
    window.removeEventListener('online', resume);
  };
}
