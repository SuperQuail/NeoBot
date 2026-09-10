// sound.test.ts —— 舰载音效合成器的降级行为
//
// 音效全部由 WebAudio 现场合成，因此最重要的是「拿不到 AudioContext 时不能崩」：
// 远程桌面、被策略禁用音频、无用户手势等场景都可能没有可用的音频上下文。
// jsdom 默认不提供 AudioContext，这里正好覆盖降级路径，并额外验证静音开关的持久化。

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { initSound, isMuted, isSoundReady, setMuted, sfx, startAmbient, toggleMuted } from '../bridge/core/sound';

const MUTE_KEY = 'neobot-bridge-muted';

beforeEach(() => {
  localStorage.clear();
  setMuted(false);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('音效合成器', () => {
  it('jsdom 没有 AudioContext 时初始化不抛错，也不进入就绪态', () => {
    expect(() => initSound()).not.toThrow();
    expect(isSoundReady()).toBe(false);
  });

  it('未初始化音频时所有音效调用都是安全的空操作', () => {
    for (const play of Object.values(sfx)) {
      expect(() => play()).not.toThrow();
    }
  });

  it('环境音在无音频设备时返回可调用的停止函数', () => {
    const stop = startAmbient();
    expect(typeof stop).toBe('function');
    expect(() => stop()).not.toThrow();
  });

  it('静音开关可切换并写入 localStorage', () => {
    expect(isMuted()).toBe(false);
    expect(toggleMuted()).toBe(true);
    expect(isMuted()).toBe(true);
    expect(localStorage.getItem(MUTE_KEY)).toBe('1');
    expect(toggleMuted()).toBe(false);
    expect(localStorage.getItem(MUTE_KEY)).toBe('0');
  });

  it('缺少 AudioContext 时 setMuted 仍然记录状态（用于 UI 同步）', () => {
    vi.stubGlobal('AudioContext', undefined);
    initSound();
    setMuted(true);
    expect(isMuted()).toBe(true);
  });
});
