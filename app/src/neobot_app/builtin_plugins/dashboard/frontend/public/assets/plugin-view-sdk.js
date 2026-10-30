/* 插件页面只通过宿主桥接访问数据，始终不读取宿主登录凭据。 */
(() => {
  const root = globalThis;
  const channel = 'neobot-plugin-view';
  const pending = new Map();
  const anchors = new Map();
  const observed = new Map();
  const contextListeners = new Set();
  const stepListeners = new Set();
  const prefix = root.crypto.randomUUID();
  let counter = 0;
  let session = '';
  let context;
  let readyPromise;
  let currentStep;
  let disposed = false;
  let measuring = false;
  let lastHeight = 0;
  const highlightStyle = root.document.createElement('style');
  highlightStyle.textContent =
    '[data-neobot-guide-current="true"]{scroll-margin:16px}' +
    ':root:not([data-neobot-mode="demo"]) [data-neobot-guide-current="true"]{outline:2px solid var(--brand);outline-offset:-2px;border-radius:var(--radius-control,8px)}';
  root.document.head.append(highlightStyle);

  const request = (method, params = {}) =>
    new Promise((resolve, reject) => {
      if (disposed) return reject(new Error('插件页面已关闭'));
      const requestId = `${prefix}-${++counter}`;
      const timer = root.setTimeout(() => {
        pending.delete(requestId);
        reject(new Error('宿主响应超时，请重新打开插件页面'));
      }, 30000);
      pending.set(requestId, { resolve, reject, timer });
      root.parent.postMessage(
        { channel, version: 1, kind: 'request', requestId, method, params, session },
        '*',
      );
    });

  const publish = (listeners, value) => {
    for (const listener of listeners) {
      try {
        listener(value);
      } catch {
        root.console.warn('插件页面事件处理失败');
      }
    }
  };

  function visibleRectangle(element) {
    const rect = element.getBoundingClientRect();
    let left = Math.max(0, rect.left);
    let top = Math.max(0, rect.top);
    let right = Math.min(root.document.documentElement.clientWidth || root.innerWidth, rect.right);
    let bottom = Math.min(root.document.documentElement.clientHeight || root.innerHeight, rect.bottom);
    // 锚点可能位于局部滚动区；宿主只能看到 iframe，需在这里排除被祖先裁掉的部分。
    for (let parent = element.parentElement; parent; parent = parent.parentElement) {
      const style = root.getComputedStyle(parent);
      const clipsX = /^(auto|scroll|hidden|clip)$/.test(style.overflowX || style.overflow);
      const clipsY = /^(auto|scroll|hidden|clip)$/.test(style.overflowY || style.overflow);
      if (!clipsX && !clipsY) continue;
      const bounds = parent.getBoundingClientRect();
      const scaleX = parent.offsetWidth ? bounds.width / parent.offsetWidth : 1;
      const scaleY = parent.offsetHeight ? bounds.height / parent.offsetHeight : 1;
      const clipLeft = bounds.left + parent.clientLeft * scaleX;
      const clipTop = bounds.top + parent.clientTop * scaleY;
      if (clipsX) {
        left = Math.max(left, clipLeft);
        right = Math.min(right, clipLeft + parent.clientWidth * scaleX);
      }
      if (clipsY) {
        top = Math.max(top, clipTop);
        bottom = Math.min(bottom, clipTop + parent.clientHeight * scaleY);
      }
    }
    if (right <= left || bottom <= top) return null;
    return { left, top, width: right - left, height: bottom - top };
  }

  function measure() {
    if (measuring || disposed || !context) return;
    measuring = true;
    root.requestAnimationFrame(() => {
      measuring = false;
      if (disposed) return;
      if (context.layout === 'inline' && !context.suspended) {
        // 测量内容本身，不读取至少等于 iframe 高度的 scrollHeight，才能在删行后收缩。
        const body = root.document.body;
        const style = root.getComputedStyle(body);
        const margins = (parseFloat(style.marginTop) || 0) + (parseFloat(style.marginBottom) || 0);
        const height = Math.ceil(body.getBoundingClientRect().height + margins);
        if (height > 0 && height !== lastHeight) {
          lastHeight = height;
          void request('resize', { height }).catch(() => {});
        }
      }
      const rectangles = {};
      for (const [id, element] of anchors) {
        if (!element.isConnected) continue;
        const rect = visibleRectangle(element);
        if (rect) rectangles[id] = rect;
      }
      // 几何测量不属于业务操作，页面关闭时不重试或发布业务错误。
      void request('anchors', { rectangles }).catch(() => {});
    });
  }

  function revealFocus(event) {
    const element = event.target;
    if (!element || element === root.document.body || typeof element.getBoundingClientRect !== 'function')
      return;
    root.requestAnimationFrame(() => {
      // 等浏览器先完成 iframe 内的焦点滚动，再让宿主只调整外层正文。
      if (disposed || context?.layout !== 'inline' || context.mode !== 'live' || context.suspended) return;
      if (root.document.activeElement !== element) return;
      const rectangle = visibleRectangle(element);
      if (rectangle) void request('reveal', { rectangle }).catch(() => {});
    });
  }

  function locate(target) {
    if (!context || !target.startsWith(`view.${context.viewId}.`)) return;
    const id = target.slice(`view.${context.viewId}.`.length);
    for (const [name, element] of anchors) {
      if (name !== id) {
        element.removeAttribute('data-neobot-guide-current');
        continue;
      }
      element.setAttribute('data-neobot-guide-current', 'true');
      element.scrollIntoView({ block: 'nearest', behavior: 'instant' });
      // 看演示只移动舞台，焦点留给播放器；跟着做才转到真实控件。
      if (context.mode === 'demo') continue;
      if (!element.hasAttribute('tabindex')) element.tabIndex = -1;
      element.focus({ preventScroll: true });
    }
    measure();
  }

  function fillExample(example) {
    for (const element of root.document.querySelectorAll('input[name], select[name], textarea[name]')) {
      if (element.type === 'file' || !Object.hasOwn(example, element.name)) continue;
      const value = example[element.name];
      if (element.type === 'checkbox') element.checked = value === true;
      else element.value = value == null ? '' : String(value);
      element.dispatchEvent(new root.Event('input', { bubbles: true }));
      element.dispatchEvent(new root.Event('change', { bubbles: true }));
    }
  }

  function applyStep(step) {
    currentStep = step;
    if (context?.mode === 'demo' && step.example) fillExample(step.example);
    publish(stepListeners, step);
    locate(step.target);
  }

  function updateContext(value) {
    context = value;
    for (const [name, color] of Object.entries(value.theme)) {
      if (name.startsWith('--')) root.document.documentElement.style.setProperty(name, color);
    }
    root.document.documentElement.dataset.neobotLayout = value.layout || 'stage';
    root.document.documentElement.dataset.neobotMode = value.mode;
    if (value.colorScheme) root.document.documentElement.style.colorScheme = value.colorScheme;
    publish(contextListeners, context);
    measure();
  }

  function completeRequest(message) {
    const item = pending.get(message.requestId);
    if (!item) return;
    if (session && message.session !== session) return;
    if (!session && typeof message.session === 'string') session = message.session;
    pending.delete(message.requestId);
    root.clearTimeout(item.timer);
    if (!message.error) {
      item.resolve(message.result);
      return;
    }
    const error = new Error(message.error.message);
    error.code = message.error.code;
    if (message.error.status !== undefined) error.status = message.error.status;
    if (message.error.fields) error.fields = message.error.fields;
    item.reject(error);
  }

  function receive(event) {
    const message = event.data;
    if (
      disposed ||
      event.source !== root.parent ||
      !message ||
      message.channel !== channel ||
      message.version !== 1
    )
      return;
    if (message.kind === 'response') return completeRequest(message);
    if (message.kind !== 'event' || message.session !== session) return;
    if (message.name === 'context') updateContext(message.payload);
    if (message.name === 'guide-step') applyStep(message.payload);
    if (message.name === 'locate') locate(message.payload.target);
  }

  function ready() {
    if (!readyPromise) {
      if (root.parent === root) return Promise.reject(new Error('请从 NeoBot 插件面板打开此页面'));
      readyPromise = request('ready').then((value) => {
        observer.observe(root.document.body);
        updateContext(value);
        return value;
      });
    }
    return readyPromise;
  }

  async function action(id, values = {}) {
    await ready();
    if (context.suspended) {
      const error = new Error('页面正在演示，真实操作已暂停');
      error.code = 'view_suspended';
      throw error;
    }
    return request('action', { id, values });
  }

  const observer = new root.ResizeObserver(measure);
  function dispose() {
    if (disposed) return;
    disposed = true;
    root.removeEventListener('message', receive);
    root.removeEventListener('resize', measure);
    root.document.removeEventListener('scroll', measure, true);
    root.document.removeEventListener('focusin', revealFocus);
    observer.disconnect();
    highlightStyle.remove();
    root.removeEventListener('pagehide', dispose);
    for (const item of pending.values()) {
      root.clearTimeout(item.timer);
      item.reject(new Error('插件页面已关闭'));
    }
    pending.clear();
    anchors.clear();
    observed.clear();
    contextListeners.clear();
    stepListeners.clear();
  }

  root.addEventListener('message', receive);
  root.addEventListener('resize', measure);
  root.addEventListener('pagehide', dispose, { once: true });
  root.document.addEventListener('scroll', measure, true);
  root.document.addEventListener('focusin', revealFocus);
  root.NeoBotPlugin = Object.freeze({
    ready,
    action,
    getConfig: async () => {
      await ready();
      return request('getConfig');
    },
    saveConfig: async (values, revision) => {
      await ready();
      return request('saveConfig', { values, revision });
    },
    notify: async (notice) => {
      await ready();
      return request('notify', notice);
    },
    navigate: async (target) => {
      await ready();
      return request('navigate', { target });
    },
    registerAnchor: (id, element) => {
      anchors.set(id, element);
      const parents = [];
      // 局部滚动区单独改变尺寸时，锚点本身可能不变，也要更新裁切范围。
      for (let node = element; node; node = node.parentElement) {
        parents.push(node);
        const count = observed.get(node) || 0;
        if (!count) observer.observe(node);
        observed.set(node, count + 1);
      }
      if (currentStep) locate(currentStep.target);
      measure();
      let registered = true;
      return () => {
        if (!registered) return;
        registered = false;
        for (const node of parents) {
          const count = observed.get(node);
          if (!count) continue;
          if (count > 1) {
            observed.set(node, count - 1);
            continue;
          }
          observed.delete(node);
          // body 仍承担内联页面的整体高度观察。
          if (node !== root.document.body) observer.unobserve(node);
        }
        if (anchors.get(id) === element) anchors.delete(id);
        measure();
      };
    },
    onGuideStep: (listener) => {
      stepListeners.add(listener);
      if (currentStep) listener(currentStep);
      return () => stepListeners.delete(listener);
    },
    onContext: (listener) => {
      contextListeners.add(listener);
      if (context) listener(context);
      return () => contextListeners.delete(listener);
    },
    dispose,
  });
})();
