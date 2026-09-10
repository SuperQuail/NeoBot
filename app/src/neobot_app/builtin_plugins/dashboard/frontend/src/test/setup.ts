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

// 统一抑制组件里用于提示的 console.warn（api client 会在拿不到数据时告警）
vi.spyOn(console, 'warn').mockImplementation(() => {});

afterEach(() => {
  cleanup();
  localStorage.clear();
});
