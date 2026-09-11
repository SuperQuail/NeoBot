// game.ts —— 游戏主控：渲染循环、模式切换、交互、终端与小游戏的装配。
//
// 性能约束（对应需求「未进入游戏时不增加性能占用」）：
//   * 页面不可见时停掉渲染，不做任何计算；
//   * 只有被聚焦的终端才轮询接口，其余终端按画质档位低频刷新或完全静止；
//   * 服务端侧本插件没有任何后台任务，只有请求到达才工作。

import * as THREE from 'three';
import { AudioKit } from './core/audio';
import type { BoostKind, GameActions } from './core/actions';
import { CollisionWorld } from './core/collision';
import { Hud } from './core/hud';
import { Input } from './core/input';
import { PlayerController } from './core/player';
import {
  QUALITY_PRESETS,
  loadPlayerName,
  loadQuality,
  savePlayerName,
  saveQuality,
  type GameBootstrap,
  type QualityLevel,
} from './config';
import { Poller, consoleApi, gameApi, type ApiResult } from './net/api';
import { SpaceScene } from './space/space';
import { ShellState, type ShipStatus } from './state';
import { TextCapture } from './ui/textinput';
import { Terminal, type TerminalDefinition, type TerminalHost } from './ui/terminal';
import { buildShip, roomAt, type ShipBuild } from './world/ship';
import { decorateShip } from './world/props';
import { terminalDefinitions } from './terminals';
import { minigameRegistry, type MinigameContext, type MinigameModule } from './minigames';

export type GameMode = 'boot' | 'world' | 'terminal' | 'minigame' | 'paused';



export class Game implements GameActions, TerminalHost {
  readonly scene = new THREE.Scene();
  readonly camera: THREE.PerspectiveCamera;
  readonly collision = new CollisionWorld();
  readonly shell = new ShellState();
  readonly hud: Hud;
  readonly input: Input;
  readonly textCapture = new TextCapture();
  readonly materials: ShipBuild['materials'];
  readonly quality = { ...QUALITY_PRESETS.medium };
  readonly actions: GameActions = this;
  readonly jumpIntervalMinutes: number;
  qualityLevel: QualityLevel;

  private renderer: THREE.WebGLRenderer;
  private ship: ShipBuild;
  private space: SpaceScene;
  private player: PlayerController;
  private terminals: Terminal[] = [];
  private audio: AudioKit;
  private raycaster = new THREE.Raycaster();
  private clockLast = 0;
  private rafId = 0;
  private running = false;
  private visible = true;
  private mode: GameMode = 'boot';
  private focused: Terminal | null = null;
  private candidate: Terminal | null = null;
  private focusBlend = 0;
  private focusFrom = new THREE.Vector3();
  private focusLook = new THREE.Vector3();
  private currentLook = new THREE.Vector3();
  private boosts = new Map<BoostKind, { remaining: number }>();
  private unlocked = new Set<string>();
  private statusPoller: Poller<ShipStatus> | null = null;
  private warpCountdown = 0;
  private seated = false;
  private systemIndex = 0;
  private fpsAccumulator = 0;
  private fpsFrames = 0;
  private fps = 0;
  private activeMinigame: MinigameModule | null = null;
  private minigameStation: Terminal | null = null;
  private minigameScreenMode = false;
  private minigameStartedAt = 0;
  private playerName = loadPlayerName();
  private pausedOverlay: HTMLElement | null = null;
  private minigameContext: MinigameContext | null = null;
  private savedView: { position: THREE.Vector3; yaw: number; pitch: number } | null = null;
  private booted = false;

  constructor(
    private readonly container: HTMLElement,
    private readonly hudRoot: HTMLElement,
    private readonly bootstrap: GameBootstrap,
    canvas: HTMLCanvasElement,
  ) {
    this.qualityLevel = loadQuality(bootstrap.quality);
    const preset = QUALITY_PRESETS[this.qualityLevel];
    Object.assign(this.quality, preset);
    this.jumpIntervalMinutes = bootstrap.jump_interval_minutes;

    this.renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: preset.antialias,
      powerPreference: 'high-performance',
    });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, preset.pixelRatio));
    this.renderer.setSize(container.clientWidth, Math.max(1, container.clientHeight), false);
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.3;
    this.renderer.setClearColor(0x03060b, 1);

    this.camera = new THREE.PerspectiveCamera(
      72,
      container.clientWidth / Math.max(1, container.clientHeight),
      0.1,
      preset.viewDistance,
    );

    this.hud = new Hud(hudRoot);
    this.input = new Input(canvas);
    this.audio = new AudioKit(bootstrap.enable_audio);
    this.shell.playerName = this.playerName;

    this.ship = buildShip(this.scene, this.collision, (message) => this.hud.toast(message, 'info', 1200));
    this.materials = this.ship.materials;
    decorateShip(this.scene, this.collision, this.materials, this.ship.rooms);
    this.player = new PlayerController(this.ship.ladders);
    this.player.spawn(this.ship.spawn, this.ship.spawnYaw);
    this.space = new SpaceScene(this.scene, this.camera, { quality: preset });
    this.systemIndex = Math.floor(Math.random() * 1000);
    this.warpCountdown = this.nextWarpDelay();
    this.buildTerminals();

    this.input.onLockLost = () => {
      if (this.mode === 'world' && this.booted) this.showPauseOverlay();
    };
    window.addEventListener('resize', this.handleResize);
    document.addEventListener('visibilitychange', this.handleVisibility);
    window.addEventListener('keydown', this.handleKeyDown, true);
    // 调试/自动化入口（也方便玩家在控制台里查看状态）
    (window as unknown as { __neobotStarship?: Game }).__neobotStarship = this;
  }

  // ------------------------------------------------------------------
  // 生命周期
  // ------------------------------------------------------------------

  start(): void {
    if (this.running) return;
    this.running = true;
    this.booted = true;
    this.mode = 'world';
    this.clockLast = performance.now();
    this.audio.resume();
    this.input.requestLock();
    this.statusPoller = new Poller<ShipStatus>(
      () => gameApi.get<ShipStatus>('/api/status') as Promise<ApiResult<ShipStatus>>,
      5000,
      (data) => this.applyStatus(data),
      () => undefined,
    );
    this.statusPoller.start(true);
    this.rafId = requestAnimationFrame(this.frame);
    this.hud.toast(
      '欢迎登舰，' + this.playerName + '。WASD 移动，走近终端按 E 使用，Esc 打开菜单。',
      'info',
      7000,
    );
  }

  dispose(): void {
    this.running = false;
    cancelAnimationFrame(this.rafId);
    this.statusPoller?.stop();
    this.space.dispose();
    this.ship.dispose();
    for (const terminal of this.terminals) terminal.dispose();
    this.input.dispose();
    this.textCapture.close();
    this.audio.dispose();
    window.removeEventListener('resize', this.handleResize);
    document.removeEventListener('visibilitychange', this.handleVisibility);
    window.removeEventListener('keydown', this.handleKeyDown, true);
    this.renderer.dispose();
  }

  private handleResize = (): void => {
    const width = Math.max(1, this.container.clientWidth);
    const height = Math.max(1, this.container.clientHeight);
    this.renderer.setSize(width, height, false);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
  };

  private handleVisibility = (): void => {
    this.visible = !document.hidden;
    if (this.visible) this.clockLast = performance.now();
  };

  private handleKeyDown = (event: KeyboardEvent): void => {
    if (this.mode === 'minigame' && this.activeMinigame && !this.minigameScreenMode) {
      if (event.key === 'Escape' || event.key === 'e' || event.key === 'E') {
        this.exitMinigame('已被玩家终止');
        event.preventDefault();
        return;
      }
      this.activeMinigame.onKey?.(event.key, this.ensureMinigameContext());
      return;
    }
    if (event.key === 'Escape') {
      if (this.mode === 'terminal' || this.minigameScreenMode) {
        if (this.minigameScreenMode) this.exitMinigame('已被玩家终止');
        else this.blurTerminal();
        event.preventDefault();
      }
      return;
    }
    if (event.key === 'e' || event.key === 'E') {
      if (this.minigameScreenMode) this.exitMinigame('已被玩家终止');
      else if (this.mode === 'terminal') this.blurTerminal();
      else if (this.mode === 'world') this.interact();
      return;
    }
    if (event.key === 'f' || event.key === 'F') {
      if (this.mode === 'world') this.toggleSeat();
      return;
    }
    if (event.key === 'm' || event.key === 'M') {
      if (this.mode === 'world' && !this.pausedOverlay) this.showPauseOverlay();
    }
  };

  // ------------------------------------------------------------------
  // 终端装配
  // ------------------------------------------------------------------

  private buildTerminals(): void {
    const byId = new Map<string, TerminalDefinition>();
    for (const definition of terminalDefinitions()) byId.set(definition.id, definition);
    for (const anchor of this.ship.anchors.values()) {
      const target = anchor.spec.target;
      const definition = byId.get(target);
      if (!definition) continue;
      if (anchor.spec.kind === 'minigame' && definition.id !== target) continue;
      const terminal = new Terminal(definition, this, anchor);
      this.terminals.push(terminal);
    }
    this.applyStatusAvailability();
  }

  private applyStatusAvailability(): void {
    for (const terminal of this.terminals) {
      terminal.setAvailability(this.shell.availability(terminal.definition.id));
    }
  }

  // ------------------------------------------------------------------
  // TerminalHost / GameActions 实现
  // ------------------------------------------------------------------

  toast(message: string, tone: 'info' | 'ok' | 'warn' | 'error' = 'info'): void {
    this.hud.toast(message, tone);
  }

  confirm(options: {
    title: string;
    body?: string;
    confirmLabel?: string;
    danger?: boolean;
  }): Promise<boolean> {
    return this.hud.confirm(options);
  }

  openMinigame(id: string, stationId?: string): void {
    const station = stationId
      ? this.terminals.find((item) => item.anchor.spec.id === stationId) ?? null
      : null;
    this.startMinigame(id, station);
  }

  get consoleApi(): typeof consoleApi {
    return consoleApi;
  }

  get gameApi(): typeof gameApi {
    return gameApi;
  }

  requestRedraw(): void {
    for (const terminal of this.terminals) terminal.markDirty();
  }

  triggerWarp(manual: boolean): boolean {
    if (this.space.warping) return false;
    const started = this.space.triggerWarp(() => {
      this.systemIndex += 1;
      this.hud.toast('已抵达新星系：' + this.systemName(), 'ok', 5000);
      this.unlockAchievement('first-jump', manual ? '手动跃迁' : '自动跃迁');
    });
    if (started) {
      this.audio.warp();
      this.hud.setBanner('跃迁引擎点火 · 全舰注意', 'info');
      window.setTimeout(() => {
        if (!this.space.warping && !this.shell.status.standby) this.hud.setBanner(null);
      }, 4200);
    }
    return started;
  }

  warping(): boolean {
    return this.space.warping;
  }

  warpPhase(): string {
    return this.space.warpPhase;
  }

  systemName(): string {
    const names = [
      '天鹅座 λ-4', '猎户悬臂 K-17', '南门二 β', '天苑四 ε', '蛇夫座 9',
      '武仙座 τ', '船底座 HD-7', '仙女座 M31-附', '半人马 ζ', '天琴座 Vega-2',
    ];
    return names[this.systemIndex % names.length];
  }

  playChime(kind: string): void {
    this.audio.chime(kind);
  }

  playMusic(scale: number[]): void {
    this.audio.playMusic(scale);
  }

  stopMusic(): void {
    this.audio.stopMusic();
  }

  setMusicActive(active: boolean): void {
    if (!active) this.audio.stopMusic();
  }

  boost(kind: BoostKind, seconds: number): void {
    this.boosts.set(kind, { remaining: seconds });
  }

  boostRemaining(kind: BoostKind): number {
    return this.boosts.get(kind)?.remaining ?? 0;
  }

  unlockAchievement(key: string, detail = ''): void {
    if (this.unlocked.has(key)) return;
    this.unlocked.add(key);
    void gameApi.post('/api/achievements', { key, detail });
  }

  setSeated(seated: boolean): void {
    this.seated = seated;
    this.player.velocity.set(0, 0, 0);
  }

  isSeated(): boolean {
    return this.seated;
  }

  lookAtTarget(name: string): void {
    const targets: Record<string, THREE.Vector3> = {
      主行星: new THREE.Vector3(1400, -260, -900),
      伴星卫星: new THREE.Vector3(900, 180, 1200),
      小行星带: new THREE.Vector3(-600, 120, 900),
      航道上的货船: new THREE.Vector3(400, 60, -500),
    };
    const target = targets[name] || targets['主行星'];
    const direction = target.clone().sub(this.camera.position).normalize();
    this.player.yaw = Math.atan2(-direction.x, -direction.z);
    this.player.pitch = Math.asin(THREE.MathUtils.clamp(direction.y, -1, 1));
    this.hud.toast('望远镜已对准：' + name, 'info');
  }

  zoomView(factor: number): void {
    this.camera.fov = Math.max(18, Math.min(96, this.camera.fov / factor));
    this.camera.updateProjectionMatrix();
  }

  private nextWarpDelay(): number {
    if (this.jumpIntervalMinutes <= 0) return Number.POSITIVE_INFINITY;
    return this.jumpIntervalMinutes * 60 * (0.6 + Math.random() * 0.7);
  }

  // ------------------------------------------------------------------
  // 主循环
  // ------------------------------------------------------------------

  private frame = (now: number): void => {
    this.rafId = requestAnimationFrame(this.frame);
    if (!this.visible) {
      this.clockLast = now;
      return;
    }
    const dt = Math.min(0.05, Math.max(0, (now - this.clockLast) / 1000));
    this.clockLast = now;
    this.fpsAccumulator += dt;
    this.fpsFrames += 1;
    if (this.fpsAccumulator > 0.5) {
      this.fps = Math.round(this.fpsFrames / this.fpsAccumulator);
      this.fpsAccumulator = 0;
      this.fpsFrames = 0;
    }

    this.updateBoosts(dt);
    this.space.update(dt);

    if (this.mode === 'minigame' && this.activeMinigame && !this.minigameScreenMode) {
      this.updateWorldMinigame(dt);
    } else if (this.focused && (this.mode === 'terminal' || this.mode === 'minigame')) {
      this.updateFocusedTerminal(dt);
    } else {
      this.updateWorld(dt);
    }

    for (const terminal of this.terminals) {
      if (terminal === this.focused) continue;
      terminal.update(dt);
    }
    this.focused?.update(dt);

    this.updateHud();
    this.renderer.render(this.scene, this.camera);
    this.input.endFrame();
  };

  private updateBoosts(dt: number): void {
    for (const [kind, boost] of this.boosts) {
      boost.remaining -= dt;
      if (boost.remaining <= 0) this.boosts.delete(kind);
    }
  }

  private updateWorld(dt: number): void {
    const locked = this.input.locked;
    const sprintBoost = this.boostRemaining('sprint') > 0 ? 1.25 : 1;
    this.player.update(dt, this.collision, this.input, {
      enabled: locked && !this.seated,
      speedScale: sprintBoost,
      jumpScale: this.boostRemaining('jump') > 0 ? 1.15 : 1,
      onStep: (running) => this.audio.footstep(running),
    });
    this.camera.position.copy(this.player.eyePosition());
    if (this.seated) this.camera.position.y -= 0.5;
    this.camera.rotation.set(this.player.pitch, this.player.yaw, 0, 'YXZ');

    this.candidate = this.findCandidate();
    this.updatePrompt();

    if (!this.space.warping && Number.isFinite(this.warpCountdown)) {
      this.warpCountdown -= dt;
      if (this.warpCountdown <= 0) {
        this.warpCountdown = this.nextWarpDelay();
        if (this.triggerWarp(false)) {
          this.hud.toast('舰载 AI 规划了一次自动跃迁。', 'info', 4000);
        }
      }
    }
  }

  private updateFocusedTerminal(dt: number): void {
    const terminal = this.focused;
    if (!terminal) {
      this.mode = 'world';
      return;
    }
    this.focusBlend = Math.min(1, this.focusBlend + dt * 4.5);
    const view = terminal.focusView();
    const blend = easeOut(this.focusBlend);
    this.camera.position.lerpVectors(this.focusFrom, view.position, blend);
    this.currentLook.copy(this.focusLook).lerp(view.target, blend);
    this.camera.lookAt(this.currentLook);

    this.raycaster.setFromCamera(
      new THREE.Vector2(this.input.pointer.x, this.input.pointer.y),
      this.camera,
    );
    const hits = this.raycaster.intersectObject(terminal.screen.mesh, false);
    const intersection = hits.length > 0 ? hits[0] : null;
    terminal.handlePointer(intersection, false, this.input.pointer.wheel);

    if (this.input.pointer.clicked) {
      if (this.activeMinigame && this.minigameScreenMode) {
        if (intersection) this.activeMinigame.onScreenClick?.(terminal.ui, this.ensureMinigameContext());
      } else {
        terminal.ui.clicked = true;
        terminal.markDirty();
      }
    }

    if (this.activeMinigame && this.minigameScreenMode) {
      this.activeMinigame.update?.(dt, this.ensureMinigameContext());
      terminal.markDirty();
    }
  }

  private updateWorldMinigame(dt: number): void {
    const module = this.activeMinigame;
    if (!module) {
      this.mode = 'world';
      return;
    }
    const ctx = this.ensureMinigameContext();
    module.update?.(dt, ctx);
    if (this.input.pointer.deltaX !== 0 || this.input.pointer.deltaY !== 0) {
      module.onPointerMove?.(this.input.pointer.deltaX, this.input.pointer.deltaY, ctx);
    }
    if (this.input.pointer.clicked) module.onPointerDown?.(ctx);
  }

  private updateHud(): void {
    if (this.mode === 'terminal') {
      this.hud.setCrosshairVisible(false);
      const hint = this.minigameScreenMode
        ? '演练中：点击操作 · E / Esc 退出'
        : this.focused?.definition.id === 'logs'
          ? '日志终端 · 点击条目查看 · E / Esc 离开'
          : '终端已聚焦 · 鼠标操作 · E / Esc 离开';
      this.hud.setStatus([hint + ' · ' + this.fps + ' FPS']);
      return;
    }
    if (this.mode === 'minigame') {
      this.hud.setCrosshairVisible(!this.minigameScreenMode, 'pointer');
      return;
    }
    const room = roomAt(this.ship.rooms, this.player.position);
    const lines: string[] = [];
    lines.push((room ? room.label : '舰内') + ' · ' + this.fps + ' FPS');
    const warpLabel = this.space.warping ? '跃迁中' : '巡航';
    lines.push(
      (this.shell.status.standby ? '低功耗待机' : warpLabel + ' · ' + this.systemName()) +
        ' · 插件 ' +
        this.shell.status.plugins.running +
        '/' +
        this.shell.status.plugins.total +
        (this.shell.status.online ? ' · 通讯正常' : ' · 通讯中断'),
    );
    const boostText: string[] = [];
    if (this.boostRemaining('sprint') > 0) boostText.push('疾跑增益 ' + this.boostRemaining('sprint').toFixed(0) + 's');
    if (this.boostRemaining('jump') > 0) boostText.push('跳跃增益 ' + this.boostRemaining('jump').toFixed(0) + 's');
    if (boostText.length > 0) lines.push(boostText.join(' · '));
    if (!this.input.locked) lines.push('点击画面继续操作 · M 打开菜单');
    else lines.push('WASD 移动 · Shift 潜行 · Ctrl 疾跑 · 空格跳跃 · E 交互 · F 就座 · M 菜单');
    this.hud.setStatus(lines);
    this.hud.setCrosshairVisible(this.input.locked && !this.seated, this.candidate ? 'pointer' : 'dot');
  }

  private findCandidate(): Terminal | null {
    const eye = this.camera.position;
    const forward = new THREE.Vector3();
    this.camera.getWorldDirection(forward);
    let best: Terminal | null = null;
    let bestScore = 0;
    for (const terminal of this.terminals) {
      const target = terminal.screen.worldCenter(new THREE.Vector3());
      const toTarget = target.clone().sub(eye);
      const distance = toTarget.length();
      if (distance > 4.2) continue;
      const alignment = toTarget.normalize().dot(forward);
      if (alignment < 0.45) continue;
      const score = alignment * 2 - distance * 0.12;
      if (score > bestScore) {
        bestScore = score;
        best = terminal;
      }
    }
    return best;
  }

  private updatePrompt(): void {
    const candidate = this.candidate;
    if (!candidate) {
      this.hud.showPrompt(null);
      return;
    }
    const spec = candidate.anchor.spec;
    if (!candidate.interactable) {
      this.hud.showPrompt(spec.label + ' · 终端已下线（' + candidate.availabilityReason + '）');
      return;
    }
    this.hud.showPrompt(spec.label + ' · ' + spec.hint);
  }

  // ------------------------------------------------------------------
  // 交互
  // ------------------------------------------------------------------

  private interact(): void {
    const candidate = this.candidate;
    if (!candidate) return;
    if (!candidate.interactable) {
      this.hud.toast(candidate.availabilityReason || '该终端当前不可用', 'warn');
      this.audio.alarm();
      return;
    }
    if (candidate.definition.kind === 'minigame') {
      this.startMinigame(candidate.definition.id, candidate);
      return;
    }
    this.focusTerminal(candidate);
  }

  focusTerminal(terminal: Terminal): void {
    this.focused = terminal;
    this.mode = 'terminal';
    this.input.mode = 'terminal';
    this.input.releaseLock();
    this.focusFrom.copy(this.camera.position);
    this.focusLook.copy(this.camera.position).add(
      new THREE.Vector3(0, 0, -1).applyQuaternion(this.camera.quaternion).multiplyScalar(8),
    );
    this.focusBlend = 0;
    terminal.focus();
    this.hud.showPrompt(null);
    this.audio.chime('terminal');
  }

  blurTerminal(): void {
    if (this.focused) this.focused.blur();
    this.focused = null;
    this.mode = 'world';
    this.input.mode = 'world';
    this.textCapture.close();
    this.focusBlend = 0;
    this.input.requestLock();
  }

  toggleSeat(): void {
    this.seated = !this.seated;
    this.hud.toast(this.seated ? '已就座（按 F 起身）' : '已起身', 'info');
  }

  // ------------------------------------------------------------------
  // 小游戏
  // ------------------------------------------------------------------

  private startMinigame(id: string, station: Terminal | null): void {
    const module = minigameRegistry.get(id);
    if (!module) {
      this.hud.toast('该小游戏没有客户端模块（可能需要更新游戏前端）', 'warn');
      return;
    }
    if (this.activeMinigame) this.stopMinigameModule();
    if (!station) station = this.terminals.find((item) => item.definition.id === id) ?? null;
    this.minigameStation = station;
    this.activeMinigame = module;
    this.minigameScreenMode = module.mode === 'screen';
    this.minigameStartedAt = performance.now();
    this.savedView = {
      position: this.player.position.clone(),
      yaw: this.player.yaw,
      pitch: this.player.pitch,
    };
    const ctx = this.ensureMinigameContext();
    module.start?.(ctx);

    if (module.mode === 'world') {
      const view = module.viewpoint?.(ctx);
      if (view) {
        this.player.yaw = view.yaw;
        this.player.pitch = view.pitch;
        this.camera.position.copy(view.position);
        this.camera.rotation.set(view.pitch, view.yaw, 0, 'YXZ');
      }
      this.mode = 'minigame';
      this.input.mode = 'minigame';
      this.input.requestLock();
      this.hud.showPrompt(null);
      this.audio.alarm();
    } else {
      this.mode = 'minigame';
      this.input.mode = 'terminal';
      if (station) {
        this.focused = station;
        this.focusFrom.copy(this.camera.position);
        this.focusLook.copy(this.camera.position);
        this.focusBlend = 0;
        station.setOverride((ui, focused) => module.draw?.(ui, this.ensureMinigameContext()) ?? void focused);
        station.focus();
      } else {
        this.hud.toast('未找到演练终端（' + id + '），已取消', 'warn');
        this.activeMinigame = null;
        this.mode = 'world';
        return;
      }
      this.input.releaseLock();
    }
    this.hud.toast('进入演练：' + module.name + ' · ' + module.description, 'ok', 5000);
  }

  private ensureMinigameContext(): MinigameContext {
    if (this.minigameContext) return this.minigameContext;
    this.minigameContext = {
      scene: this.scene,
      camera: this.camera,
      input: this.input,
      hud: this.hud,
      audio: this.audio,
      shell: this.shell,
      quality: this.quality,
      actions: this,
      playerPosition: this.player.position,
      submitScore: async (game, score, durationMs, detail) => {
        const result = await gameApi.post<{ best?: number; rank?: number; error?: string }>('/api/scores', {
          game,
          score,
          duration_ms: durationMs,
          detail,
          player: this.playerName,
        });
        if (result.ok) return { ok: true, best: result.data?.best, rank: result.data?.rank };
        return { ok: false, error: result.error || '保存失败' };
      },
      leaderboard: (game, limit) =>
        gameApi.get('/api/scores?game=' + encodeURIComponent(game) + '&limit=' + limit),
      toast: (message, tone) => this.hud.toast(message, tone || 'info'),
      exit: (reason) => this.exitMinigame(reason || '演练结束'),
      finish: (summary) => this.finishMinigame(summary),
      setHud: (info) => this.hud.setMinigame(info),
      rng: () => Math.random(),
    };
    return this.minigameContext;
  }

  private finishMinigame(summary: { title: string; lines: string[]; score: number; canRetry: boolean }): void {
    this.hud.setMinigame(null);
    const id = this.activeMinigame?.id ?? '';
    void this.hud
      .confirm({
        title: summary.title,
        body: summary.lines.join('\n') + '\n\n本次得分：' + summary.score,
        confirmLabel: summary.canRetry ? '再来一局' : '结束',
        cancelLabel: '返回舰内',
      })
      .then((retry) => {
        const station = this.minigameStation;
        if (retry && id) {
          this.stopMinigameModule();
          this.startMinigame(id, station);
        } else {
          this.exitMinigame('演练结束');
        }
      });
  }

  private stopMinigameModule(): void {
    if (this.activeMinigame) {
      this.activeMinigame.dispose?.(this.ensureMinigameContext());
      this.activeMinigame = null;
    }
    this.minigameStation?.setOverride(null);
  }

  exitMinigame(reason: string): void {
    if (!this.activeMinigame && this.mode !== 'minigame') return;
    const id = this.activeMinigame?.id;
    this.stopMinigameModule();
    this.hud.setMinigame(null);
    if (this.minigameStation) this.minigameStation.blur();
    this.minigameStation = null;
    this.minigameScreenMode = false;
    this.focused = null;
    this.mode = 'world';
    this.input.mode = 'world';
    if (this.savedView) {
      this.player.spawn(this.savedView.position, this.savedView.yaw);
      this.player.pitch = this.savedView.pitch;
      this.savedView = null;
    } else {
      this.player.spawn(this.ship.spawn, this.ship.spawnYaw);
    }
    this.camera.fov = 72;
    this.camera.updateProjectionMatrix();
    this.input.requestLock();
    this.hud.toast('已返回舰内（' + reason + '）', 'info');
    if (id) this.unlockAchievement('minigame-' + id, '完成一次演练');
  }

  // ------------------------------------------------------------------
  // 状态与设置
  // ------------------------------------------------------------------

  private applyStatus(status: ShipStatus): void {
    this.shell.update(status);
    this.applyStatusAvailability();
    this.requestRedraw();
    if (status.standby) {
      this.hud.setBanner(
        '舰船处于低功耗待机：' + (status.reason || '未说明原因') + ' · 可在主控台恢复运行',
        'warn',
      );
    } else {
      this.hud.setBanner(null);
    }
  }

  showPauseOverlay(): void {
    if (this.pausedOverlay) return;
    const overlay = document.createElement('div');
    overlay.className = 'game-menu-overlay';
    overlay.innerHTML =
      '<div class="game-menu">' +
      '<h2>NeoBot 星舰</h2>' +
      '<p class="menu-sub">舰长：' + escapeHtml(this.playerName) + ' · ' + escapeHtml(this.systemName()) + '</p>' +
      '<div class="menu-rows">' +
      row('画质', ['low', 'medium', 'high'], this.qualityLevel, 'quality') +
      row('鼠标灵敏度', ['0.5', '1', '1.5', '2'], String(this.input.sensitivity), 'sens') +
      row('垂直视角', ['normal', 'inverted'], this.input.invertY ? 'inverted' : 'normal', 'invert') +
      '</div>' +
      '<div class="menu-actions">' +
      '<button data-action="resume" class="primary">继续游戏</button>' +
      '<button data-action="name">修改舰长名</button>' +
      '<button data-action="console">返回控制台</button>' +
      '</div>' +
      '<p class="menu-hint">提示：走近终端按 E 使用；待机状态下部分终端会离线。</p>' +
      '</div>';
    overlay.addEventListener('click', (event) => {
      const target = event.target as HTMLElement;
      const action = target.dataset.action;
      const value = target.dataset.value;
      if (action === 'resume') {
        this.closePauseOverlay();
        this.input.requestLock();
      } else if (action === 'console') {
        window.location.href = new URL('../', window.location.href).toString();
      } else if (action === 'name') {
        void this.hud.ask({ title: '舰长名', value: this.playerName }).then((name) => {
          if (name) {
            this.playerName = name.slice(0, 32);
            savePlayerName(this.playerName);
            this.shell.playerName = this.playerName;
          }
          this.closePauseOverlay();
          this.showPauseOverlay();
        });
      } else if (action === 'quality' && value) {
        this.applyQuality(value as QualityLevel);
        this.closePauseOverlay();
        this.showPauseOverlay();
      } else if (action === 'sens' && value) {
        this.input.sensitivity = Number(value);
        this.closePauseOverlay();
        this.showPauseOverlay();
      } else if (action === 'invert' && value) {
        this.input.invertY = value === 'inverted';
        this.closePauseOverlay();
        this.showPauseOverlay();
      }
    });
    this.hudRoot.appendChild(overlay);
    this.pausedOverlay = overlay;
    this.input.releaseLock();
  }

  closePauseOverlay(): void {
    this.pausedOverlay?.remove();
    this.pausedOverlay = null;
  }

  private applyQuality(level: QualityLevel): void {
    this.qualityLevel = level;
    saveQuality(level);
    const preset = QUALITY_PRESETS[level];
    Object.assign(this.quality, preset);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, preset.pixelRatio));
    this.camera.far = preset.viewDistance;
    this.camera.updateProjectionMatrix();
    this.space.dispose();
    this.space = new SpaceScene(this.scene, this.camera, { quality: preset });
    this.hud.toast('画质已切换为「' + preset.label + '」', 'ok');
  }
}

function easeOut(value: number): number {
  return 1 - Math.pow(1 - value, 3);
}

function escapeHtml(text: string): string {
  return String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function row(label: string, values: string[], current: string, action: string): string {
  return (
    '<div class="menu-row"><span>' + escapeHtml(label) + '</span><div>' +
    values
      .map(
        (value) =>
          '<button data-action="' + action + '" data-value="' + value + '" class="' +
          (value === current ? 'active' : '') + '">' + escapeHtml(value) + '</button>',
      )
      .join('') +
    '</div></div>'
  );
}
