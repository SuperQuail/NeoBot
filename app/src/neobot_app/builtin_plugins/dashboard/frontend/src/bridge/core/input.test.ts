import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createInput, type InputHandle } from './input';

let input: InputHandle;
beforeEach(() => {
  vi.spyOn(document, 'hasFocus').mockReturnValue(true);
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(false);
  Object.defineProperty(document, 'pointerLockElement', { configurable: true, value: null });
});
afterEach(() => {
  input?.dispose();
  document.body.replaceChildren();
  vi.restoreAllMocks();
  Reflect.deleteProperty(document, 'pointerLockElement');
  Reflect.deleteProperty(document, 'exitPointerLock');
});
const mouse = (type: string, target: EventTarget = window, init: MouseEventInit = {}) => {
  const event = new MouseEvent(type, { bubbles: true, cancelable: true, ...init });
  target.dispatchEvent(event);
  return event;
};
const lock = (element: Element | null) => {
  Object.defineProperty(document, 'pointerLockElement', { configurable: true, value: element });
  document.dispatchEvent(new Event('pointerlockchange'));
};
const setup = () => {
  const canvas = document.createElement('canvas');
  const panel = document.createElement('section');
  panel.className = 'panel-anchor';
  panel.innerHTML = '<div><span>Terminal</span></div>';
  document.body.append(canvas, panel);
  const request = vi.fn();
  canvas.requestPointerLock = request;
  input = createInput(canvas, { touch: false, sensitivity: 0.01 });
  return { canvas, panel, child: panel.querySelector('span')!, request };
};
const key = (code: string, target: EventTarget = window) => {
  const event = new KeyboardEvent('keydown', { code, bubbles: true, cancelable: true });
  target.dispatchEvent(event);
  return event;
};
describe('world terminal input', () => {
  it('allows walking with a free cursor and clears motion for modal overlays', () => {
    input = createInput(document.createElement('canvas'), { touch: false });
    expect(input.isLocked()).toBe(false);
    key('KeyW');
    expect(input.readMove().forward).toBe(1);
    input.setEnabled(false);
    key('KeyD');
    expect(input.readMove()).toEqual({ forward: 0, strafe: 0 });
  });
  it('stops held movement when editing and preserves native form keys', () => {
    input = createInput(document.createElement('canvas'), { touch: false });
    key('KeyW'); key('Space');
    const field = document.createElement('textarea');
    document.body.append(field); field.focus();
    expect(input.readMove().forward).toBe(0);
    expect(input.state.jumpPressed).toBe(false);
    for (const code of ['Space', 'Tab', 'ArrowDown', 'KeyW']) {
      expect(key(code, field).defaultPrevented).toBe(false);
    }
    expect(input.readMove().forward).toBe(0);
    expect(input.state.jumpPressed).toBe(false);
  });
});

describe('free cursor right drag look', () => {
  it.each(['canvas', 'panel', 'child'] as const)('uses client deltas from %s without requesting pointer lock', (area) => {
    const scene = setup();
    const down = mouse('mousedown', scene[area], { button: 2, clientX: 100, clientY: 200 });
    expect(down.defaultPrevented).toBe(true);
    mouse('mousemove', window, { clientX: 112, clientY: 194 });
    mouse('mousemove', window, { clientX: 110, clientY: 205 });
    expect(input.state.lookDx).toBeCloseTo(0.1);
    expect(input.state.lookDy).toBeCloseTo(0.05);
    expect(scene.request).not.toHaveBeenCalled();
    expect(input.isLocked()).toBe(false);
    expect(input.isFiring()).toBe(false);
    expect(input.state.actions).toEqual([]);
    input.endFrame();
    mouse('mousemove', window, { clientX: 113, clientY: 203 });
    expect(input.state.lookDx).toBeCloseTo(0.03);
    expect(input.state.lookDy).toBeCloseTo(-0.02);
  });

  it.each([0, 1])('does not look with mouse button %s', (button) => {
    const { canvas } = setup();
    mouse('mousedown', canvas, { button });
    mouse('mousemove', window, { clientX: 30, clientY: 20 });
    expect(input.state.lookDx).toBe(0);
    expect(input.state.lookDy).toBe(0);
  });

  it('does not start outside look areas or while disabled', () => {
    const { canvas } = setup();
    mouse('mousedown', document.body, { button: 2 });
    mouse('mousemove', window, { clientX: 30 });
    expect(input.state.lookDx).toBe(0);
    input.setEnabled(false);
    mouse('mousedown', canvas, { button: 2 });
    input.setEnabled(true);
    mouse('mousemove', window, { clientX: 60 });
    expect(input.state.lookDx).toBe(0);
  });

  it.each([
    '<input>', '<textarea></textarea>', '<select><option>choice</option></select>',
    '<div contenteditable="true"><span>edit</span></div>',
    '<div contenteditable=""><span>edit</span></div>',
    '<div contenteditable="plaintext-only"><span>edit</span></div>',
  ])('preserves editable drag and context menu: %s', (html) => {
    const { panel } = setup();
    panel.innerHTML = html;
    const target = panel.querySelector('span, option') ?? panel.firstElementChild!;
    expect(mouse('mousedown', target, { button: 2 }).defaultPrevented).toBe(false);
    mouse('mousemove', window, { clientX: 30, clientY: 20 });
    expect(input.state.lookDx).toBe(0);
    expect(input.state.lookDy).toBe(0);
    expect(mouse('contextmenu', target).defaultPrevented).toBe(false);
  });

  it('suppresses context menus only in enabled look areas', () => {
    const { canvas, panel, child } = setup();
    for (const target of [canvas, panel, child]) {
      expect(mouse('contextmenu', target).defaultPrevented).toBe(true);
    }
    expect(mouse('contextmenu', document.body).defaultPrevented).toBe(false);
    input.setEnabled(false);
    for (const target of [canvas, panel, child]) {
      expect(mouse('contextmenu', target).defaultPrevented).toBe(false);
    }
  });

  it.each(['mouseup', 'blur', 'disable', 'typing', 'pointerlock', 'hidden'])('stops dragging on %s until a new press', (reason) => {
    const { canvas, panel } = setup();
    mouse('mousedown', canvas, { button: 2 });
    mouse('mousemove', window, { clientX: 10 });
    expect(input.state.lookDx).toBeCloseTo(0.1);
    if (reason === 'mouseup') mouse('mouseup', window, { button: 2 });
    if (reason === 'blur') window.dispatchEvent(new Event('blur'));
    if (reason === 'disable') { input.setEnabled(false); input.setEnabled(true); }
    if (reason === 'typing') {
      const field = document.createElement('textarea');
      panel.append(field);
      field.focus();
      field.blur();
    }
    if (reason === 'pointerlock') { lock(canvas); lock(null); }
    if (reason === 'hidden') {
      vi.mocked(Object.getOwnPropertyDescriptor(document, 'hidden')!.get!).mockReturnValue(true);
      document.dispatchEvent(new Event('visibilitychange'));
    }
    input.endFrame();
    mouse('mousemove', window, { clientX: 50 });
    expect(input.state.lookDx).toBe(0);
    mouse('mousedown', canvas, { button: 2, clientX: 50 });
    mouse('mousemove', window, { clientX: 55 });
    expect(input.state.lookDx).toBeCloseTo(0.05);
  });

  it('keeps pointer-locked relative movement and ignores right drag coordinates', () => {
    const { canvas } = setup();
    lock(canvas);
    mouse('mousedown', canvas, { button: 2, clientX: 100 });
    const move = new MouseEvent('mousemove', { clientX: 999, clientY: 999 });
    Object.defineProperties(move, { movementX: { value: 3 }, movementY: { value: -4 } });
    window.dispatchEvent(move);
    expect(input.state.lookDx).toBeCloseTo(0.03);
    expect(input.state.lookDy).toBeCloseTo(-0.04);
    input.endFrame();
    input.setEnabled(false);
    window.dispatchEvent(move);
    expect(input.state.lookDx).toBe(0);
  });
});

describe('browser pointer unlock notification', () => {
  it('notifies the canvas once per browser-initiated locked-to-unlocked transition', () => {
    const { canvas } = setup();
    const unlock = vi.fn();
    canvas.addEventListener('bridge-pointer-unlock', unlock);
    lock(null);
    expect(unlock).not.toHaveBeenCalled();
    lock(canvas);
    lock(canvas);
    lock(null);
    lock(null);
    expect(unlock).toHaveBeenCalledTimes(1);
    expect(unlock.mock.calls[0][0]).toBeInstanceOf(Event);
    lock(canvas);
    lock(null);
    expect(unlock).toHaveBeenCalledTimes(2);
  });

  it('suppresses explicit exitLock but allows subsequent browser unlocks', () => {
    const { canvas } = setup();
    const unlock = vi.fn();
    canvas.addEventListener('bridge-pointer-unlock', unlock);
    const exit = vi.fn();
    Object.defineProperty(document, 'exitPointerLock', { configurable: true, value: exit });
    input.exitLock();
    expect(exit).not.toHaveBeenCalled();
    lock(canvas);
    input.exitLock();
    expect(exit).toHaveBeenCalledTimes(1);
    lock(null);
    lock(null);
    expect(unlock).not.toHaveBeenCalled();
    input.exitLock();
    lock(canvas);
    lock(null);
    expect(unlock).toHaveBeenCalledTimes(1);
  });

  it('marks explicit exits before synchronous pointerlockchange delivery', () => {
    const { canvas } = setup();
    const unlock = vi.fn();
    canvas.addEventListener('bridge-pointer-unlock', unlock);
    Object.defineProperty(document, 'exitPointerLock', { configurable: true, value: () => lock(null) });
    lock(canvas);
    input.exitLock();
    expect(unlock).not.toHaveBeenCalled();
  });

  it.each(['blur', 'hidden', 'unfocused'])('does not notify on %s lock loss', (reason) => {
    const { canvas } = setup();
    const unlock = vi.fn();
    canvas.addEventListener('bridge-pointer-unlock', unlock);
    lock(canvas);
    if (reason === 'blur') window.dispatchEvent(new Event('blur'));
    if (reason === 'unfocused') vi.mocked(document.hasFocus).mockReturnValue(false);
    if (reason === 'hidden') vi.mocked(Object.getOwnPropertyDescriptor(document, 'hidden')!.get!).mockReturnValue(true);
    lock(null);
    expect(unlock).not.toHaveBeenCalled();
    vi.mocked(document.hasFocus).mockReturnValue(true);
    vi.mocked(Object.getOwnPropertyDescriptor(document, 'hidden')!.get!).mockReturnValue(false);
    lock(canvas);
    lock(null);
    expect(unlock).toHaveBeenCalledTimes(1);
  });

  it('observes a lock already held at initialization', () => {
    const canvas = document.createElement('canvas');
    lock(canvas);
    input = createInput(canvas, { touch: false });
    const unlock = vi.fn();
    canvas.addEventListener('bridge-pointer-unlock', unlock);
    lock(null);
    expect(unlock).toHaveBeenCalledTimes(1);
  });

  it('removes all registered listeners on dispose', () => {
    const windowAdd = vi.spyOn(window, 'addEventListener');
    const documentAdd = vi.spyOn(document, 'addEventListener');
    const windowRemove = vi.spyOn(window, 'removeEventListener');
    const documentRemove = vi.spyOn(document, 'removeEventListener');
    const canvas = document.createElement('canvas');
    document.body.append(canvas);
    const canvasAdd = vi.spyOn(canvas, 'addEventListener');
    const canvasRemove = vi.spyOn(canvas, 'removeEventListener');
    input = createInput(canvas);
    const registrations = [windowAdd, documentAdd, canvasAdd].map(spy => [...spy.mock.calls]);
    const unlock = vi.fn();
    canvas.addEventListener('bridge-pointer-unlock', unlock);
    lock(canvas);
    input.dispose();
    for (const [index, remove] of [windowRemove, documentRemove, canvasRemove].entries()) {
      for (const [type, listener] of registrations[index]) {
        expect(remove).toHaveBeenCalledWith(type, listener);
      }
    }
    lock(null);
    mouse('mousedown', canvas, { button: 2 });
    mouse('mousemove', window, { clientX: 100 });
    key('KeyW');
    expect(unlock).not.toHaveBeenCalled();
    expect(input.state.lookDx).toBe(0);
    expect(input.readMove().forward).toBe(0);
    expect(mouse('contextmenu', canvas).defaultPrevented).toBe(false);
  });
});
