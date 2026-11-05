import { afterEach, expect, it, vi } from 'vitest';
import { revealPluginFocus } from '../pages/plugins/pluginViewFocus';

afterEach(() => {
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

function fixture() {
  const shell = document.createElement('div');
  const scroll = document.createElement('div');
  scroll.className = 'workspace-scroll';
  const frame = document.createElement('iframe');
  scroll.append(frame);
  shell.append(scroll);
  document.body.append(shell);
  scroll.getBoundingClientRect = () => new DOMRect(0, 200, 400, 400);
  frame.getBoundingClientRect = () => new DOMRect(20, 100, 360, 600);
  Object.defineProperty(scroll, 'clientHeight', { value: 400 });
  scroll.scrollTop = 400;
  frame.focus();
  return { shell, scroll, frame };
}

it.each([
  [{ left: 0, top: 20, width: 100, height: 44 }, 288],
  [{ left: 0, top: 500, width: 100, height: 60 }, 492],
  [{ left: 0, top: 200, width: 100, height: 44 }, 400],
  [{ left: 0, top: 50, width: 100, height: 800 }, 318],
  [{ left: 400, top: 20, width: 100, height: 44 }, 400],
  [{ left: 0, top: 800, width: 100, height: 44 }, 400],
])('只滚动当前正文来完整显示焦点控件：%j', (rect, expected) => {
  const { shell, scroll, frame } = fixture();
  revealPluginFocus(frame, rect);
  expect(scroll.scrollTop).toBe(expected);
  expect(shell.scrollTop).toBe(0);
});

it('焦点已离开 iframe 时，迟到的请求不拉回滚动位置', () => {
  const { frame, scroll } = fixture();
  const button = document.createElement('button');
  document.body.append(button);
  button.focus();
  revealPluginFocus(frame, { left: 0, top: 20, width: 100, height: 44 });
  expect(scroll.scrollTop).toBe(400);
});
