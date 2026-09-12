// core/input.ts —— 输入管理：指针锁、键位、鼠标与滚轮、文本输入切换。
// MC 风格操作：WASD 移动、空格跳跃、Shift 潜行、Ctrl 疾跑、鼠标看方向、
// E 与终端交互、Esc 释放鼠标、指针锁定时左键点击 = 激活。

export type InputMode = 'world' | 'terminal' | 'minigame' | 'menu';

export interface PointerState {
  /** 归一化设备坐标（-1..1），终端模式下由真实鼠标位置驱动 */
  x: number;
  y: number;
  clientX: number;
  clientY: number;
  down: boolean;
  /** 本帧内是否发生了一次点击（按下并抬起） */
  clicked: boolean;
  deltaX: number;
  deltaY: number;
  wheel: number;
}

const KEY_ALIASES: Record<string, string> = {
  ArrowUp: 'up',
  ArrowDown: 'down',
  ArrowLeft: 'left',
  ArrowRight: 'right',
  ' ': 'space',
};

export class Input {
  readonly keys = new Set<string>();
  readonly pointer: PointerState = {
    x: 0,
    y: 0,
    clientX: 0,
    clientY: 0,
    down: false,
    clicked: false,
    deltaX: 0,
    deltaY: 0,
    wheel: 0,
  };
  /** 本帧按下的键（用于一次性触发，例如 E / Tab） */
  private pressedThisFrame = new Set<string>();
  private pressedQueue: string[] = [];
  mode: InputMode = 'world';
  locked = false;
  /** 文本输入激活时，键位不再进入游戏逻辑（交给隐藏 input 处理） */
  textMode = false;
  sensitivity = 1;
  invertY = false;

  private readonly element: HTMLElement;
  private readonly listeners: Array<() => void> = [];
  private onClickHandlers: Array<() => void> = [];

  constructor(element: HTMLElement) {
    this.element = element;
    this.bind();
  }

  private on<K extends keyof DocumentEventMap>(
    target: EventTarget,
    type: K,
    handler: (event: DocumentEventMap[K]) => void,
    options?: AddEventListenerOptions,
  ): void {
    target.addEventListener(type, handler as EventListener, options);
    this.listeners.push(() =>
      target.removeEventListener(type, handler as EventListener, options),
    );
  }

  private bind(): void {
    this.on(window, 'keydown', (event) => {
      if (this.textMode) return;
      const key = this.normalize(event);
      if (event.repeat) return;
      if (!this.keys.has(key)) this.pressedQueue.push(key);
      this.keys.add(key);
      if (key === 'space' || key === 'tab') event.preventDefault();
    });
    this.on(window, 'keyup', (event) => {
      this.keys.delete(this.normalize(event));
    });
    this.on(window, 'blur', () => {
      this.keys.clear();
    });
    this.on(document, 'mousemove', (event) => {
      if (this.locked) {
        this.pointer.deltaX += event.movementX || 0;
        this.pointer.deltaY += event.movementY || 0;
      }
      this.pointer.clientX = event.clientX;
      this.pointer.clientY = event.clientY;
      const rect = this.element.getBoundingClientRect();
      this.pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      this.pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    });
    this.on(this.element, 'mousedown', (event) => {
      if (event.button !== 0) return;
      this.pointer.down = true;
    });
    this.on(window, 'mouseup', (event) => {
      if (event.button !== 0) return;
      if (this.pointer.down) {
        this.pointer.clicked = true;
        for (const handler of this.onClickHandlers) handler();
      }
      this.pointer.down = false;
    });
    this.on(
      window,
      'wheel',
      (event) => {
        this.pointer.wheel += event.deltaY;
      },
      { passive: true },
    );
    this.on(document, 'pointerlockchange', () => {
      this.locked = document.pointerLockElement === this.element;
      if (!this.locked && this.mode === 'world') {
        this.onLockLost?.();
      }
    });
  }

  private normalize(event: KeyboardEvent): string {
    if (KEY_ALIASES[event.key]) return KEY_ALIASES[event.key];
    if (event.key === 'Shift') return 'shift';
    if (event.key === 'Control') return 'control';
    if (event.key === 'Escape') return 'escape';
    if (event.key === 'Tab') return 'tab';
    return event.key.length === 1 ? event.key.toLowerCase() : event.key;
  }

  onLockLost: (() => void) | null = null;

  onNextClick(handler: () => void): () => void {
    this.onClickHandlers.push(handler);
    return () => {
      const index = this.onClickHandlers.indexOf(handler);
      if (index >= 0) this.onClickHandlers.splice(index, 1);
    };
  }

  requestLock(): void {
    if (this.locked) return;
    const request = this.element.requestPointerLock?.bind(this.element);
    if (request) {
      const result = request() as unknown as Promise<void> | undefined;
      if (result && typeof result.catch === 'function') result.catch(() => undefined);
    }
  }

  releaseLock(): void {
    if (document.pointerLockElement === this.element) document.exitPointerLock();
  }

  isDown(key: string): boolean {
    return this.keys.has(key);
  }

  /** 本帧是否刚按下（消费式，只返回一次 true） */
  wasPressed(key: string): boolean {
    const index = this.pressedQueue.indexOf(key);
    if (index < 0) return false;
    this.pressedQueue.splice(index, 1);
    return true;
  }

  peekPressed(key: string): boolean {
    return this.pressedQueue.includes(key);
  }

  /** 每帧末尾调用：清理一次性状态 */
  endFrame(): void {
    this.pointer.clicked = false;
    this.pointer.deltaX = 0;
    this.pointer.deltaY = 0;
    this.pointer.wheel = 0;
    this.pressedQueue.length = 0;
    this.pressedThisFrame.clear();
  }

  dispose(): void {
    for (const off of this.listeners) off();
    this.listeners.length = 0;
    this.onClickHandlers.length = 0;
  }
}
