// input.ts —— 第一人称操作层（键盘 / 指针锁定 / 触屏）
//
// 操作映射沿用 MC 的手感，但在舰内语境里重新命名并给出设定内提示：
//   W A S D   前后左右             Space   喷射跳（舰内低重力辅助）
//   Shift     推进冲刺             Ctrl    蹲伏（钻低矮管线区）
//   E         物资清单             F / 左键 交互（接入终端 / 拾取 / 开火）
//   1-8       快接终端             Q       舰内导航（跃迁到舱室）
//   Tab       终端总览             Esc     断开终端 / 释放鼠标
//   M         静音                 H       操作手册

export interface InputState {
  /** 鼠标锁定时累积的视角增量（弧度），由渲染循环读取后清零 */
  lookDx: number;
  lookDy: number;
  /** 本帧请求的一次性动作 id（见 ACTION 与 'terminal:N'） */
  actions: string[];
  /** 本帧是否刚按下跳跃 */
  jumpPressed: boolean;
}

export const ACTION = {
  interact: 'interact',
  inventory: 'inventory',
  nav: 'nav',
  terminals: 'terminals',
  close: 'close',
  mute: 'mute',
  help: 'help',
} as const;

export type ActionId = (typeof ACTION)[keyof typeof ACTION] | `terminal:${string}` | 'jump' | 'sprint' | 'crouch';

const KEY_TO_ACTION: Record<string, string> = {
  KeyF: ACTION.interact,
  KeyE: ACTION.inventory,
  KeyQ: ACTION.nav,
  Tab: ACTION.terminals,
  Escape: ACTION.close,
  KeyM: ACTION.mute,
  KeyH: ACTION.help,
};

/** 快接终端顺序，与 STATIONS 的数组顺序一致 */
export const HOTKEY_ORDER = ['1', '2', '3', '4', '5', '6', '7', '8'] as const;

export interface InputHandle {
  state: InputState;
  /** 本帧移动向量（已归一化，长度 ≤ 1），触屏摇杆与键盘合并 */
  readMove(): { forward: number; strafe: number };
  /** 是否按住冲刺 / 蹲伏 */
  isSprinting(): boolean;
  isCrouching(): boolean;
  /** 每帧渲染结束后调用，清理一次性状态 */
  endFrame(): void;
  /** 面板 / 小游戏接管输入时禁用移动 */
  setEnabled(enabled: boolean): void;
  isEnabled(): boolean;
  /** 请求指针锁定（必须在用户手势回调里调用） */
  requestLock(): void;
  exitLock(): void;
  isLocked(): boolean;
  /** 是否按住交互键（左键或 F），舰炮持续开火需要 */
  isFiring(): boolean;
  dispose(): void;
}

export interface InputOptions {
  /** 指针锁定状态变化（用于显示「点击继续」遮罩） */
  onLockChange?: (locked: boolean) => void;
  /** 视角灵敏度（弧度 / 像素） */
  sensitivity?: number;
  /** 是否启用触屏摇杆（移动端） */
  touch?: boolean;
}

const MOVEMENT_KEYS = new Set([
  'KeyW',
  'KeyA',
  'KeyS',
  'KeyD',
  'ArrowUp',
  'ArrowDown',
  'ArrowLeft',
  'ArrowRight',
  'Space',
  'ShiftLeft',
  'ShiftRight',
  'ControlLeft',
  'ControlRight',
]);

const PREVENT_DEFAULT = new Set(['Tab', 'Space', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight']);

export function createInput(canvas: HTMLCanvasElement, options: InputOptions = {}): InputHandle {
  const sensitivity = options.sensitivity ?? 0.0022;
  const enableTouch = options.touch ?? true;
  const held = new Set<string>();
  const state: InputState = {
    lookDx: 0,
    lookDy: 0,
    actions: [],
    jumpPressed: false,
  };
  const touchMove = { x: 0, y: 0 };
  let enabled = true;
  let firing = false;
  let moveTouchId: number | null = null;
  let lookTouchId: number | null = null;
  let moveOrigin = { x: 0, y: 0 };
  let lookLast = { x: 0, y: 0 };
  let longPressTimer: number | null = null;

  const isLocked = () => document.pointerLockElement === canvas;
  let wasLocked = isLocked();
  let exitLockRequested = false;
  let focusLoss = false;
  let dragLast: { x: number; y: number } | null = null;

  const isTypingTarget = (target: EventTarget | null): boolean => {
    if (!(target instanceof Element)) return false;
    const editable = target.closest('[contenteditable]');
    return Boolean(
      target.closest('input, textarea, select') ||
      (target instanceof HTMLElement && target.isContentEditable) ||
      (editable && editable.getAttribute('contenteditable')?.toLowerCase() !== 'false')
    );
  };

  const onKeyDown = (event: KeyboardEvent) => {
    if (!enabled) return;
    if (isTypingTarget(event.target)) {
      // 表单里只保留 Esc（关闭面板），其余按键交给输入框
      if (event.code === 'Escape') state.actions.push(ACTION.close);
      return;
    }
    if (PREVENT_DEFAULT.has(event.code) || MOVEMENT_KEYS.has(event.code)) event.preventDefault();
    if (event.repeat) {
      held.add(event.code);
      return;
    }
    held.add(event.code);

    const action = KEY_TO_ACTION[event.code];
    if (action) {
      state.actions.push(action);
      return;
    }
    if (event.code === 'Space') {
      state.jumpPressed = true;
      return;
    }
    if (event.code.startsWith('Digit')) {
      const digit = event.code.slice(5);
      if ((HOTKEY_ORDER as readonly string[]).includes(digit)) state.actions.push(`terminal:${digit}`);
    }
  };

  const onKeyUp = (event: KeyboardEvent) => {
    held.delete(event.code);
  };

  const isLookTarget = (target: EventTarget | null) =>
    target instanceof Element && !isTypingTarget(target) &&
    (target === canvas || Boolean(target.closest('.panel-anchor')));

  const onMouseMove = (event: MouseEvent) => {
    if (!enabled) return;
    if (isLocked()) {
      state.lookDx += event.movementX * sensitivity;
      state.lookDy += event.movementY * sensitivity;
    } else if (dragLast) {
      state.lookDx += (event.clientX - dragLast.x) * sensitivity;
      state.lookDy += (event.clientY - dragLast.y) * sensitivity;
      dragLast = { x: event.clientX, y: event.clientY };
    }
  };

  const onMouseDown = (event: MouseEvent) => {
    if (event.button === 0) firing = true;
    if (event.button === 2 && enabled && !isLocked() && isLookTarget(event.target)) {
      dragLast = { x: event.clientX, y: event.clientY };
      event.preventDefault();
    }
  };
  const onMouseUp = (event: MouseEvent) => {
    if (event.button === 0) firing = false;
    if (event.button === 2) dragLast = null;
  };
  const onContextMenu = (event: MouseEvent) => {
    if (enabled && isLookTarget(event.target)) event.preventDefault();
  };

  const onLockChange = () => {
    const locked = isLocked();
    const browserUnlock = wasLocked && !locked && !exitLockRequested &&
      !focusLoss && !document.hidden && document.hasFocus();
    wasLocked = locked;
    exitLockRequested = false;
    focusLoss = false;
    dragLast = null;
    if (!locked) {
      firing = false;
      held.clear();
      touchMove.x = 0;
      touchMove.y = 0;
    }
    if (browserUnlock) canvas.dispatchEvent(new CustomEvent('bridge-pointer-unlock'));
    options.onLockChange?.(locked);
  };

  // ---- 触屏：左半屏拖动移动，右半屏拖动转视角，长按交互 ----
  const onTouchStart = (event: TouchEvent) => {
    if (!enabled || !enableTouch) return;
    for (const touch of Array.from(event.changedTouches)) {
      const half = window.innerWidth / 2;
      if (touch.clientX < half && moveTouchId === null) {
        moveTouchId = touch.identifier;
        moveOrigin = { x: touch.clientX, y: touch.clientY };
      } else if (touch.clientX >= half && lookTouchId === null) {
        lookTouchId = touch.identifier;
        lookLast = { x: touch.clientX, y: touch.clientY };
      }
    }
    if (event.touches.length === 1) {
      longPressTimer = window.setTimeout(() => {
        state.actions.push(ACTION.interact);
        longPressTimer = null;
      }, 320);
    }
  };

  const clearLongPress = () => {
    if (longPressTimer !== null) {
      window.clearTimeout(longPressTimer);
      longPressTimer = null;
    }
  };

  const onTouchMove = (event: TouchEvent) => {
    if (!enabled || !enableTouch) return;
    clearLongPress();
    for (const touch of Array.from(event.changedTouches)) {
      if (touch.identifier === moveTouchId) {
        // 摇杆半径 60px，超出按满偏处理
        const max = 60;
        const dx = (touch.clientX - moveOrigin.x) / max;
        const dy = (touch.clientY - moveOrigin.y) / max;
        const length = Math.hypot(dx, dy);
        const scale = length > 1 ? 1 / length : 1;
        touchMove.x = dx * scale;
        touchMove.y = dy * scale;
      } else if (touch.identifier === lookTouchId) {
        state.lookDx += (touch.clientX - lookLast.x) * sensitivity * 1.4;
        state.lookDy += (touch.clientY - lookLast.y) * sensitivity * 1.4;
        lookLast = { x: touch.clientX, y: touch.clientY };
      }
    }
    event.preventDefault();
  };

  const onTouchEnd = (event: TouchEvent) => {
    clearLongPress();
    for (const touch of Array.from(event.changedTouches)) {
      if (touch.identifier === moveTouchId) {
        moveTouchId = null;
        touchMove.x = 0;
        touchMove.y = 0;
      } else if (touch.identifier === lookTouchId) {
        lookTouchId = null;
      }
    }
  };

  const clearHeldInput = () => {
    dragLast = null;
    held.clear();
    firing = false;
    touchMove.x = 0;
    touchMove.y = 0;
  };

  const onBlur = () => {
    if (wasLocked) focusLoss = true;
    clearHeldInput();
  };
  const onVisibilityChange = () => {
    if (document.hidden) onBlur();
  };

  const onFocusIn = (event: FocusEvent) => {
    if (isTypingTarget(event.target)) {
      clearHeldInput();
      state.jumpPressed = false;
    }
  };

  document.addEventListener('focusin', onFocusIn);
  document.addEventListener('visibilitychange', onVisibilityChange);
  window.addEventListener('contextmenu', onContextMenu);
  window.addEventListener('keydown', onKeyDown);
  window.addEventListener('keyup', onKeyUp);
  window.addEventListener('mousemove', onMouseMove);
  window.addEventListener('mousedown', onMouseDown);
  window.addEventListener('mouseup', onMouseUp);
  window.addEventListener('blur', onBlur);
  document.addEventListener('pointerlockchange', onLockChange);
  if (enableTouch) {
    canvas.addEventListener('touchstart', onTouchStart, { passive: true });
    canvas.addEventListener('touchmove', onTouchMove, { passive: false });
    canvas.addEventListener('touchend', onTouchEnd, { passive: true });
    canvas.addEventListener('touchcancel', onTouchEnd, { passive: true });
  }

  return {
    state,
    readMove() {
      let forward = 0;
      let strafe = 0;
      if (held.has('KeyW') || held.has('ArrowUp')) forward += 1;
      if (held.has('KeyS') || held.has('ArrowDown')) forward -= 1;
      if (held.has('KeyD') || held.has('ArrowRight')) strafe += 1;
      if (held.has('KeyA') || held.has('ArrowLeft')) strafe -= 1;
      // 触屏输入优先，避免与键盘叠加导致速度翻倍
      if (Math.abs(touchMove.x) > 0.06 || Math.abs(touchMove.y) > 0.06) {
        strafe = touchMove.x;
        forward = -touchMove.y;
      }
      const length = Math.hypot(forward, strafe);
      if (length > 1) {
        forward /= length;
        strafe /= length;
      }
      return { forward, strafe };
    },
    isSprinting: () => held.has('ShiftLeft') || held.has('ShiftRight'),
    isCrouching: () => held.has('ControlLeft') || held.has('ControlRight'),
    endFrame() {
      state.lookDx = 0;
      state.lookDy = 0;
      state.jumpPressed = false;
      state.actions.length = 0;
    },
    setEnabled(next: boolean) {
      enabled = next;
      if (!next) clearHeldInput();
    },
    isEnabled: () => enabled,
    requestLock() {
      if (document.pointerLockElement === canvas) return;
      const request = canvas.requestPointerLock as
        | ((options?: { unadjustedMovement?: boolean }) => Promise<void> | void)
        | undefined;
      try {
        const result = request?.call(canvas);
        // 新版浏览器返回 Promise，被拒绝（尚未获得用户手势）时会 reject
        if (result && typeof (result as Promise<void>).catch === 'function') {
          (result as Promise<void>).catch(() => {});
        }
      } catch {
        // 极老实现直接抛错：忽略，遮罩会继续提示点击
      }
    },
    exitLock() {
      if (isLocked()) {
        exitLockRequested = true;
        try {
          document.exitPointerLock();
        } catch (error) {
          exitLockRequested = false;
          throw error;
        }
      }
    },
    isLocked,
    isFiring: () => firing || held.has('KeyF'),
    dispose() {
      clearLongPress();
      document.removeEventListener('focusin', onFocusIn);
      document.removeEventListener('visibilitychange', onVisibilityChange);
      window.removeEventListener('contextmenu', onContextMenu);
      window.removeEventListener('keydown', onKeyDown);
      window.removeEventListener('keyup', onKeyUp);
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mousedown', onMouseDown);
      window.removeEventListener('mouseup', onMouseUp);
      window.removeEventListener('blur', onBlur);
      document.removeEventListener('pointerlockchange', onLockChange);
      canvas.removeEventListener('touchstart', onTouchStart);
      canvas.removeEventListener('touchmove', onTouchMove);
      canvas.removeEventListener('touchend', onTouchEnd);
      canvas.removeEventListener('touchcancel', onTouchEnd);
    },
  };
}
