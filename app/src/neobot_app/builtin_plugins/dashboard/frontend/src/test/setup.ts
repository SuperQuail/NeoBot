// Vitest 全局启动文件：补齐 jsdom 缺失的浏览器 API，并注册 jest-dom 断言。
import '@testing-library/jest-dom/vitest';
import { afterEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';

// jsdom 未实现 matchMedia，主题初始化会用到
if (!window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

// jsdom 未实现 scrollTo / scrollIntoView，插件列表与日志视口会调用
if (!Element.prototype.scrollTo) Element.prototype.scrollTo = () => {};
if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = () => {};

// jsdom 没有原生 top layer。nwsapi 对 :modal 的“原生探测”会再次调用
// Element.matches 并递归到栈溢出，Floating UI 每次定位都会触发它。
const matchesSelector = Element.prototype.matches;
Element.prototype.matches = function (selector: string) {
  if (selector === ':modal' || selector === ':popover-open') return false;
  return matchesSelector.call(this, selector);
};

// 统一抑制组件里用于提示的 console.warn（api client 会在拿不到数据时告警）
vi.spyOn(console, 'warn').mockImplementation(() => {});

afterEach(() => {
  cleanup();
  localStorage.clear();
});
