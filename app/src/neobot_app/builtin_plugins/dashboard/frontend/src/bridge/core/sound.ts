// sound.ts —— 舰载音效合成器（WebAudio，无外部音频资源）
//
// 面板产物要随 Python 包分发，任何 mp3/wav 都会显著增大体积，因此全部音效
// 用振荡器 + 噪声实时合成：开关舰门、终端按键、警报、舰炮、脚步金属声等。
// 浏览器要求音频上下文在用户手势后才能启动，调用方在点击「登舰」时 initSound()。

let ctx: AudioContext | null = null;
let master: GainNode | null = null;
let noiseBuffer: AudioBuffer | null = null;
let ambientNodes: AudioNode[] = [];
let muted = false;

const MUTE_KEY = 'neobot-bridge-muted';

/** 用户手势后初始化；重复调用无副作用 */
export function initSound(): void {
  if (ctx) {
    void ctx.resume();
    return;
  }
  const Ctor =
    window.AudioContext ??
    (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!Ctor) return;
  try {
    ctx = new Ctor();
  } catch {
    ctx = null;
    return;
  }
  master = ctx.createGain();
  master.gain.value = muted ? 0 : 0.5;
  master.connect(ctx.destination);

  // 1 秒白噪声：脚步、爆炸、警报底噪都复用它
  const length = Math.floor(ctx.sampleRate);
  noiseBuffer = ctx.createBuffer(1, length, ctx.sampleRate);
  const data = noiseBuffer.getChannelData(0);
  for (let i = 0; i < length; i += 1) data[i] = Math.random() * 2 - 1;

  try {
    muted = localStorage.getItem(MUTE_KEY) === '1';
  } catch {
    muted = false;
  }
  if (master) master.gain.value = muted ? 0 : 0.5;
}

export function isMuted(): boolean {
  return muted;
}

export function setMuted(next: boolean): void {
  muted = next;
  try {
    localStorage.setItem(MUTE_KEY, next ? '1' : '0');
  } catch {
    // 忽略：无法持久化时仅本次会话生效
  }
  if (master && ctx) master.gain.setTargetAtTime(next ? 0 : 0.5, ctx.currentTime, 0.02);
}

export function toggleMuted(): boolean {
  setMuted(!muted);
  return muted;
}

/** 单音：频率滑移 + 指数衰减包络 */
function tone(
  freq: number,
  duration: number,
  options: {
    type?: OscillatorType;
    gain?: number;
    toFreq?: number;
    delay?: number;
  } = {},
): void {
  if (!ctx || !master || muted) return;
  const { type = 'sine', gain = 0.2, toFreq, delay = 0 } = options;
  const start = ctx.currentTime + delay;
  const osc = ctx.createOscillator();
  const env = ctx.createGain();
  osc.type = type;
  osc.frequency.setValueAtTime(freq, start);
  if (toFreq !== undefined) osc.frequency.exponentialRampToValueAtTime(Math.max(20, toFreq), start + duration);
  env.gain.setValueAtTime(0.0001, start);
  env.gain.exponentialRampToValueAtTime(gain, start + Math.min(0.02, duration * 0.2));
  env.gain.exponentialRampToValueAtTime(0.0001, start + duration);
  osc.connect(env).connect(master);
  osc.start(start);
  osc.stop(start + duration + 0.02);
}

/** 噪声爆破：滤波中心频率决定「金属 / 爆炸 / 气流」的质感 */
function noise(
  duration: number,
  options: { gain?: number; freq?: number; q?: number; type?: BiquadFilterType; sweepTo?: number } = {},
): void {
  if (!ctx || !master || !noiseBuffer || muted) return;
  const { gain = 0.2, freq = 1200, q = 1, type = 'bandpass', sweepTo } = options;
  const start = ctx.currentTime;
  const src = ctx.createBufferSource();
  src.buffer = noiseBuffer;
  const filter = ctx.createBiquadFilter();
  filter.type = type;
  filter.frequency.setValueAtTime(freq, start);
  if (sweepTo !== undefined) filter.frequency.exponentialRampToValueAtTime(Math.max(40, sweepTo), start + duration);
  filter.Q.value = q;
  const env = ctx.createGain();
  env.gain.setValueAtTime(gain, start);
  env.gain.exponentialRampToValueAtTime(0.0001, start + duration);
  src.connect(filter).connect(env).connect(master);
  src.start(start);
  src.stop(start + duration + 0.02);
}

export const sfx = {
  /** 终端按键 */
  beep(): void {
    tone(880, 0.08, { type: 'square', gain: 0.07 });
    tone(1320, 0.06, { type: 'square', gain: 0.04, delay: 0.05 });
  },
  /** 打开全息面板 */
  open(): void {
    tone(420, 0.22, { type: 'triangle', gain: 0.12, toFreq: 900 });
    noise(0.18, { gain: 0.05, freq: 2600, sweepTo: 800 });
  },
  /** 关闭面板 */
  close(): void {
    tone(880, 0.18, { type: 'triangle', gain: 0.1, toFreq: 320 });
  },
  /** 金属脚步（甲板是钢板，脚步带一点咔哒） */
  step(): void {
    noise(0.09, { gain: 0.05, freq: 260, q: 0.8 });
    tone(120 + Math.random() * 30, 0.06, { type: 'square', gain: 0.03 });
  },
  /** 跳跃 / 落地 */
  jump(): void {
    tone(320, 0.12, { type: 'sine', gain: 0.08, toFreq: 520 });
  },
  land(): void {
    noise(0.12, { gain: 0.09, freq: 180, q: 0.7 });
  },
  /** 舰门开合 */
  door(): void {
    noise(0.5, { gain: 0.07, freq: 400, sweepTo: 160, q: 0.6 });
    tone(90, 0.5, { type: 'sawtooth', gain: 0.05, toFreq: 60 });
  },
  /** 拾取物资 */
  pickup(): void {
    tone(784, 0.09, { type: 'triangle', gain: 0.1 });
    tone(1175, 0.12, { type: 'triangle', gain: 0.08, delay: 0.07 });
  },
  /** 成就 / 任务完成 */
  achievement(): void {
    [523.25, 659.25, 783.99, 1046.5].forEach((freq, index) =>
      tone(freq, 0.2, { type: 'triangle', gain: 0.09, delay: index * 0.09 }),
    );
  },
  /** 舰炮射击 */
  shot(): void {
    tone(220, 0.14, { type: 'sawtooth', gain: 0.12, toFreq: 70 });
    noise(0.12, { gain: 0.1, freq: 1800, sweepTo: 300 });
  },
  /** 命中 */
  hit(): void {
    noise(0.14, { gain: 0.09, freq: 900, sweepTo: 200, q: 0.9 });
  },
  /** 受损 / 舰体警报 */
  alarm(): void {
    tone(660, 0.35, { type: 'square', gain: 0.09, toFreq: 440 });
    tone(660, 0.35, { type: 'square', gain: 0.09, toFreq: 440, delay: 0.4 });
  },
  /** 操作失败 */
  deny(): void {
    tone(180, 0.22, { type: 'square', gain: 0.09, toFreq: 120 });
  },
  /** 超空间跃迁 */
  warp(): void {
    tone(80, 1.4, { type: 'sawtooth', gain: 0.09, toFreq: 1200 });
    noise(1.4, { gain: 0.07, freq: 200, sweepTo: 4200 });
  },
  /** 反应堆脉冲 */
  pulse(): void {
    tone(140, 0.6, { type: 'sine', gain: 0.11, toFreq: 420 });
    noise(0.5, { gain: 0.05, freq: 320, sweepTo: 1200 });
  },
};

/**
 * 引擎低频环境音：让舰内「有底噪」。
 * 返回停止函数，切换场景或卸载时调用。
 */
export function startAmbient(): () => void {
  if (!ctx || !master || ambientNodes.length > 0) return () => {};
  const start = ctx.currentTime;

  const rumble = ctx.createOscillator();
  rumble.type = 'sine';
  rumble.frequency.value = 42;
  const rumbleGain = ctx.createGain();
  rumbleGain.gain.setValueAtTime(0.0001, start);
  rumbleGain.gain.exponentialRampToValueAtTime(0.05, start + 2);
  rumble.connect(rumbleGain).connect(master);
  rumble.start(start);

  const air = ctx.createBufferSource();
  if (noiseBuffer) {
    air.buffer = noiseBuffer;
    air.loop = true;
    const filter = ctx.createBiquadFilter();
    filter.type = 'lowpass';
    filter.frequency.value = 320;
    const airGain = ctx.createGain();
    airGain.gain.setValueAtTime(0.0001, start);
    airGain.gain.exponentialRampToValueAtTime(0.03, start + 3);
    air.connect(filter).connect(airGain).connect(master);
    air.start(start);
    ambientNodes = [rumble, rumbleGain, air, filter, airGain];
  } else {
    ambientNodes = [rumble, rumbleGain];
  }

  return () => {
    if (!ctx) return;
    const stop = ctx.currentTime;
    for (const node of ambientNodes) {
      if (node instanceof GainNode) node.gain.setTargetAtTime(0, stop, 0.2);
      else if (node instanceof OscillatorNode || node instanceof AudioBufferSourceNode) {
        try {
          node.stop(stop + 0.6);
        } catch {
          // 已经停止
        }
      }
    }
    ambientNodes = [];
  };
}

/** 供测试使用：判断音频是否已就绪 */
export function isSoundReady(): boolean {
  return ctx !== null;
}
