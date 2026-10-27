import { vi } from 'vitest';

/** 通过真实 change 事件驱动偏好订阅，保留其它媒体查询的默认行为。 */
export function mockReducedEffects(initial = false) {
  let reduced = initial;
  const events = new EventTarget();
  const original = window.matchMedia;
  const media = {
    get matches() {
      return reduced;
    },
    media: '(prefers-reduced-motion: reduce)',
    onchange: null,
    addEventListener: events.addEventListener.bind(events),
    removeEventListener: events.removeEventListener.bind(events),
    addListener: (listener: EventListener) => events.addEventListener('change', listener),
    removeListener: (listener: EventListener) => events.removeEventListener('change', listener),
    dispatchEvent: events.dispatchEvent.bind(events),
  } as MediaQueryList;
  const mock = vi
    .spyOn(window, 'matchMedia')
    .mockImplementation((query) => (query.includes('prefers-reduced-motion') ? media : original(query)));
  return {
    set(value: boolean) {
      reduced = value;
      const event = new Event('change');
      Object.defineProperty(event, 'matches', { value });
      events.dispatchEvent(event);
    },
    restore: () => mock.mockRestore(),
  };
}
