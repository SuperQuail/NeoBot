// core/audio.ts —— WebAudio 实时合成音效（不依赖任何音频文件，随包体积为零）。

export class AudioKit {
  private context: AudioContext | null = null;
  private master: GainNode | null = null;
  private musicGain: GainNode | null = null;
  private musicTimer: number | null = null;
  private musicStep = 0;
  enabled: boolean;

  constructor(enabled: boolean) {
    this.enabled = enabled;
  }

  /** 必须由用户手势触发（浏览器的自动播放策略） */
  resume(): void {
    if (!this.enabled) return;
    if (!this.context) {
      const Ctor = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (!Ctor) {
        this.enabled = false;
        return;
      }
      this.context = new Ctor();
      this.master = this.context.createGain();
      this.master.gain.value = 0.35;
      this.master.connect(this.context.destination);
      this.musicGain = this.context.createGain();
      this.musicGain.gain.value = 0.18;
      this.musicGain.connect(this.master);
    }
    if (this.context.state === 'suspended') void this.context.resume();
  }

  private tone(
    frequency: number,
    duration: number,
    options: { type?: OscillatorType; gain?: number; target?: AudioNode | null; slideTo?: number } = {},
  ): void {
    if (!this.enabled || !this.context || !this.master) return;
    const now = this.context.currentTime;
    const oscillator = this.context.createOscillator();
    const gain = this.context.createGain();
    oscillator.type = options.type || 'sine';
    oscillator.frequency.setValueAtTime(frequency, now);
    if (options.slideTo) {
      oscillator.frequency.exponentialRampToValueAtTime(Math.max(20, options.slideTo), now + duration);
    }
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(options.gain ?? 0.25, now + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + duration);
    oscillator.connect(gain);
    gain.connect(options.target ?? this.master);
    oscillator.start(now);
    oscillator.stop(now + duration + 0.02);
  }

  private noise(duration: number, gainValue = 0.2, filterFrequency = 900): void {
    if (!this.enabled || !this.context || !this.master) return;
    const now = this.context.currentTime;
    const frames = Math.max(1, Math.floor(this.context.sampleRate * duration));
    const buffer = this.context.createBuffer(1, frames, this.context.sampleRate);
    const data = buffer.getChannelData(0);
    for (let index = 0; index < frames; index += 1) {
      data[index] = (Math.random() * 2 - 1) * (1 - index / frames);
    }
    const source = this.context.createBufferSource();
    source.buffer = buffer;
    const filter = this.context.createBiquadFilter();
    filter.type = 'lowpass';
    filter.frequency.value = filterFrequency;
    const gain = this.context.createGain();
    gain.gain.value = gainValue;
    source.connect(filter);
    filter.connect(gain);
    gain.connect(this.master);
    source.start(now);
  }

  chime(kind: string): void {
    const base = kind === 'coffee' ? 520 : kind === 'supply' ? 380 : 660;
    this.tone(base, 0.16, { type: 'triangle', gain: 0.18 });
    window.setTimeout(() => this.tone(base * 1.5, 0.22, { type: 'sine', gain: 0.16 }), 90);
  }

  footstep(running: boolean): void {
    this.noise(0.09, running ? 0.14 : 0.09, running ? 1200 : 800);
  }

  laser(): void {
    this.tone(1200, 0.12, { type: 'square', gain: 0.12, slideTo: 240 });
  }

  explosion(): void {
    this.noise(0.5, 0.28, 420);
    this.tone(90, 0.4, { type: 'sawtooth', gain: 0.14, slideTo: 40 });
  }

  alarm(): void {
    this.tone(680, 0.5, { type: 'square', gain: 0.1, slideTo: 420 });
  }

  warp(): void {
    this.tone(120, 1.6, { type: 'sawtooth', gain: 0.16, slideTo: 1400 });
    this.noise(1.4, 0.16, 2600);
  }

  playMusic(scale: number[]): void {
    this.resume();
    if (!this.enabled || !this.context || !this.musicGain) return;
    this.stopMusic();
    this.musicStep = 0;
    const stepMs = 320;
    this.musicTimer = window.setInterval(() => {
      if (!this.context || !this.musicGain) return;
      const note = scale[this.musicStep % scale.length];
      const octave = this.musicStep % 8 < 4 ? 1 : 0.5;
      this.tone(note * octave, 0.32, { type: 'triangle', gain: 0.22, target: this.musicGain });
      if (this.musicStep % 4 === 0) {
        this.tone(note * 0.5, 0.5, { type: 'sine', gain: 0.3, target: this.musicGain });
      }
      this.musicStep += 1;
    }, stepMs);
  }

  stopMusic(): void {
    if (this.musicTimer !== null) {
      window.clearInterval(this.musicTimer);
      this.musicTimer = null;
    }
  }

  dispose(): void {
    this.stopMusic();
    if (this.context) void this.context.close();
    this.context = null;
    this.master = null;
    this.musicGain = null;
  }
}
