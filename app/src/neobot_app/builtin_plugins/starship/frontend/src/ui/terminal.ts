// ui/terminal.ts —— 终端运行时：3D 站位 + 全息屏 + 输入路由 + 数据轮询 + 可用性表现。

import * as THREE from 'three';
import type { Input } from '../core/input';
import type { Hud } from '../core/hud';
import type { QualityPreset } from '../config';
import { consoleApi, gameApi, type Pollable } from '../net/api';
import type { ShipMaterials } from '../world/materials';
import type { StationAnchor } from '../world/ship';
import { HoloScreen, createStationRig } from './holo';
import { UiSurface } from './surface';
import { surfaceFocus, terminalLayout } from './terminal-layout';
import type { TextCapture } from './textinput';
import type { Availability, ShellState } from '../state';
import type { GameActions } from '../core/actions';
import { createPhysicalTerminal, type PhysicalTerminal } from '../terminals/physical';

export interface TerminalHost {
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  input: Input;
  hud: Hud;
  materials: ShipMaterials;
  shell: ShellState;
  quality: QualityPreset;
  textCapture: TextCapture;
  actions: GameActions;
  jumpIntervalMinutes: number;
  toast(message: string, tone?: 'info' | 'ok' | 'warn' | 'error'): void;
  confirm(options: {
    title: string;
    body?: string;
    confirmLabel?: string;
    danger?: boolean;
  }): Promise<boolean>;
  openMinigame(id: string): void;
  consoleApi: typeof consoleApi;
  gameApi: typeof gameApi;
  requestRedraw(): void;
}

export interface TerminalContext {
  host: TerminalHost;
  anchor: StationAnchor;
  ui: UiSurface;
  shell: ShellState;
  redraw(): void;
  toast(message: string, tone?: 'info' | 'ok' | 'warn' | 'error'): void;
  confirm(options: {
    title: string;
    body?: string;
    confirmLabel?: string;
    danger?: boolean;
  }): Promise<boolean>;
}

export interface TerminalController {
  draw(ui: UiSurface, focused: boolean): void;
  pollers?: Pollable[];
  onFocus?(): void;
  onBlur?(): void;
  dispose?(): void;
  /** 未聚焦时也按低频率重绘（有动画时打开） */
  idleAnimated?: boolean;
}

export interface TerminalDefinition {
  id: string;
  title: string;
  subtitle: string;
  accent: number;
  /** 是否为小游戏 / 道具类互动点 */
  kind?: 'terminal' | 'minigame' | 'prop';
  create(ctx: TerminalContext): TerminalController;
  decorate?(group: THREE.Group, materials: ShipMaterials): void;
}

const OFFLINE_ACCENT = 0xffa63d;

export class Terminal {
  readonly definition: TerminalDefinition;
  readonly anchor: StationAnchor;
  readonly group = new THREE.Group();
  readonly screen: HoloScreen;
  readonly ui: UiSurface;
  private controller: TerminalController | null = null;
  private physical: PhysicalTerminal | null = null;
  private active = false;
  private dirty = true;
  private idleAccumulator = 0;
  private availability: Availability = { available: true, reason: '', hint: '', readOnly: false };
  private baseAccent: number;
  private disposed = false;
  private readonly decoration = new THREE.Group();
  private lastScrollId: string | null = null;
  /** 小游戏接管屏幕时的自定义绘制 */
  private override: ((ui: UiSurface, focused: boolean) => void) | null = null;

  constructor(
    definition: TerminalDefinition,
    private readonly host: TerminalHost,
    anchor: StationAnchor,
  ) {
    this.definition = definition;
    this.anchor = anchor;
    this.baseAccent = definition.accent;
    const rig = createStationRig(host.materials, {
      accent: definition.accent,
      title: definition.title,
      stationId: definition.id,
    });
    this.screen = rig.screen;
    this.group.add(rig.group);
    // Keep extension hooks, but seat their ornaments inside the rear machinery.
    definition.decorate?.(this.decoration, host.materials);
    this.decoration.scale.setScalar(0.24);
    this.decoration.position.set(0, 0.2, -0.68);
    this.group.add(this.decoration);

    this.group.position.copy(anchor.position);
    this.group.rotation.y = anchor.yaw;
    host.scene.add(this.group);

    // 直接复用全息屏的画布：UiSurface 画的就是贴到曲面屏上的那张图
    this.ui = new UiSurface(
      this.screen.canvas.width,
      this.screen.canvas.height,
      '#' + definition.accent.toString(16).padStart(6, '0'),
      this.screen.canvas,
    );
    const context: TerminalContext = {
      host, anchor, ui: this.ui, shell: host.shell,
      redraw: () => this.markDirty(),
      toast: (message, tone) => host.toast(message, tone),
      confirm: (options) => host.confirm(options),
    };
    this.physical = createPhysicalTerminal(definition.id, context, definition.accent);
    this.controller = this.physical ?? definition.create?.(context) ?? null;
    if (this.physical) {
      this.screen.setBusinessControls(this.physical.group, this.physical.targets);
      this.decoration.visible = false;
    }
    this.drawFrame(false);
  }

  /** Exact visible solid instrument meshes; projection, text and hidden panels are excluded. */
  solidMeshes(): THREE.Mesh[] {
    this.group.updateWorldMatrix(true, true);
    const meshes: THREE.Mesh[] = [];
    this.group.traverseVisible(object => {
      if (object instanceof THREE.Mesh && object.userData.solidConsole === true) meshes.push(object);
    });
    return meshes;
  }

  get available(): boolean {
    return this.availability.available;
  }

  get focused(): boolean {
    return this.active;
  }

  get interactable(): boolean {
    return this.availability.available;
  }

  /** 不可用时的原因（用于交互提示） */
  get availabilityReason(): string {
    return this.availability.reason || '当前状态不可用';
  }

  markDirty(): void {
    this.dirty = true;
  }

  /** 交给小游戏接管这块屏幕（传 null 恢复终端自身画面） */
  setOverride(renderer: ((ui: UiSurface, focused: boolean) => void) | null): void {
    this.override = renderer;
    this.markDirty();
  }

  setAvailability(availability: Availability): void {
    const changed =
      availability.available !== this.availability.available ||
      availability.reason !== this.availability.reason ||
      availability.hint !== this.availability.hint ||
      availability.readOnly !== this.availability.readOnly;
    this.availability = availability;
    this.physical?.setAvailability(availability.available, availability.reason);
    this.screen.setAccent(availability.available ? this.baseAccent : OFFLINE_ACCENT);
    if (changed) {
      if (this.active) {
        for (const poller of this.controller?.pollers ?? []) {
          if (availability.available) poller.start(true);
          else poller.stop();
        }
      }
      this.markDirty();
    }
  }

  /** Public interaction plane, shared by focus framing and world-side visibility. */
  get operatingSurface(): THREE.Object3D { return this.physical?.operatingSurface ?? this.screen.mesh; }

  /** Align the focus camera with the actual visible operation plane. */
  focusView(): { position: THREE.Vector3; target: THREE.Vector3 } {
    if (this.physical) {
      const layout = terminalLayout(this.definition.id);
      return surfaceFocus(this.physical.operatingSurface, layout.width, layout.height, this.host.camera);
    }
    return surfaceFocus(this.screen.mesh, this.screen.width, this.screen.height, this.host.camera);
  }

  focus(): void {
    if (this.active || this.disposed) return;
    this.active = true;
    this.screen.setFocused(true);
    this.decoration.visible = false;
    this.controller?.onFocus?.();
    if (this.available) for (const poller of this.controller?.pollers ?? []) poller.start(true);
    this.markDirty();
  }

  blur(): void {
    if (!this.active) return;
    this.active = false;
    this.screen.setFocused(false);
    this.decoration.visible = !this.physical;
    this.screen.pressKey(null);
    this.ui.clicked = false;
    this.clearPointer();
    this.controller?.onBlur?.();
    for (const poller of this.controller?.pollers ?? []) poller.stop();
    this.markDirty();
  }

  private clearPointer(): void {
    if (this.ui.cursor.inside) this.markDirty();
    this.ui.cursor.inside = false;
    this.ui.cursor.down = false;
    // UiSurface's legacy hover helpers test coordinates, not cursor.inside.
    this.ui.cursor.x = this.ui.cursor.y = -100000;
    this.ui.clicked = false;
    this.ui.hoverId = null;
  }

  /** A UV hit addresses the inset canvas; a no-UV key hit addresses solid hardware. */
  handlePointer(intersection: THREE.Intersection | null, clicked: boolean, wheel: number): void {
    this.screen.pressKey(null);
    if (!this.active || !this.available || this.disposed) {
      this.clearPointer();
      return;
    }
    if (this.physical) {
      this.clearPointer();
      const index = intersection?.object.userData.physicalAction;
      this.physical.hover(typeof index === 'number' ? intersection!.object : null, this.host.input.pointer.down);
      if (clicked && typeof index === 'number') this.physical.activate(index);
      return;
    }
    const key = intersection?.object.userData.consoleKey;
    if (key) {
      this.clearPointer();
      if (this.host.input.pointer.down || clicked) this.screen.pressKey(intersection!.object);
      // Screen-mode minigames own their click dispatch and must not refresh API data.
      if (clicked && !this.override) {
        if (key === 'refresh') {
          for (const poller of this.controller?.pollers ?? []) void poller.tick();
          this.host.toast('控制台数据已请求刷新', 'info');
        } else if (this.lastScrollId) {
          this.ui.scrollBy(this.lastScrollId, key === 'scroll-up' ? -3 : 3);
        } else {
          this.host.toast('先将光标移到列表，再使用上下实体键', 'info');
        }
        this.markDirty();
      }
      return;
    }
    if (!intersection?.uv) {
      this.clearPointer();
      return;
    }
    const x = THREE.MathUtils.clamp(intersection.uv.x, 0, 1) * this.ui.width;
    const y = (1 - THREE.MathUtils.clamp(intersection.uv.y, 0, 1)) * this.ui.height;
    const moved = !this.ui.cursor.inside || Math.abs(x - this.ui.cursor.x) > 0.5 || Math.abs(y - this.ui.cursor.y) > 0.5;
    this.ui.cursor.x = x;
    this.ui.cursor.y = y;
    this.ui.cursor.inside = true;
    this.ui.cursor.down = this.host.input.pointer.down;
    const hovered = this.ui.hitTest(x, y);
    // Only list row IDs end with a numeric suffix; ordinary buttons aren't scroll targets.
    const row = hovered?.match(/^(.*):[0-9]+$/);
    if (row) this.lastScrollId = row[1];
    if (clicked) this.ui.clicked = true;
    if (moved || clicked) this.markDirty();
    if (wheel !== 0 && row) {
      this.ui.scrollBy(row[1], wheel * 0.05);
      this.markDirty();
    }
  }

  update(dt: number): void {
    if (this.disposed) return;
    const interactive = this.active;
    // Geometry animation never uploads canvas textures or starts API polling.
    this.screen.update(dt, interactive);
    if (this.physical && interactive) this.physical.sync();
    if (!interactive) {
      this.ui.cursor.inside = false;
      const animated = this.definition.id !== '' && this.controller?.idleAnimated === true;
      const interval = this.host.quality.refreshIdleTerminals ? 1 : animated ? 0.4 : 0;
      if (interval > 0) {
        this.idleAccumulator += dt;
        if (this.idleAccumulator >= interval) {
          this.idleAccumulator = 0;
          this.markDirty();
        }
      }
    }
    if (this.dirty) {
      // Controller callbacks can request another frame while drawing; don't erase it.
      this.dirty = false;
      this.drawFrame(interactive);
    }
  }

  private drawFrame(interactive: boolean): void {
    const ui = this.ui;
    if (this.physical) { this.physical.sync(); ui.clicked = false; return; }
    // Consume AFTER the immediate-mode controller sees it, never before. Also accept
    // legacy game callers that assign ui.clicked directly, but reject off-surface clicks.
    ui.clicked = ui.clicked && interactive && ui.cursor.inside && this.available;
    const consumedClick = ui.clicked;
    ui.hoverId = null;
    ui.begin(1 / 30, this.definition.title, this.definition.subtitle);
    try {
      if (!this.available) {
        this.drawOffline(ui);
      } else if (!interactive) {
        this.drawStandby(ui);
      } else {
        if (this.availability.reason) {
          ui.text(24, 92, '⚠ ' + this.availability.reason, { size: 17, color: ui.theme.warn });
          if (this.availability.hint) ui.text(24, 116, this.availability.hint, { size: 15, color: ui.theme.textDim });
        }
        if (this.override) this.override(ui, interactive);
        else this.controller?.draw(ui, interactive);
      }
    } finally {
      ui.end();
      ui.clicked = false;
      this.screen.texture.needsUpdate = true;
      // Local tab/page state can change without calling ctx.redraw(). Refresh it once.
      if (consumedClick) this.markDirty();
    }
  }

  private drawStandby(ui: UiSurface): void {
    const ctx = ui.ctx;
    ctx.strokeStyle = ui.theme.accent;
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(512, 145); ctx.lineTo(574, 244); ctx.lineTo(512, 340);
    ctx.lineTo(450, 244); ctx.closePath(); ctx.stroke();
    ui.text(512, 402, '神 经 链 接 · 待 命', { size: 30, align: 'center', color: ui.theme.accent });
    ui.text(512, 450, '靠近并按 E 接入控制台', { size: 24, align: 'center' });
    ui.text(512, 520, 'KHALAI COMMAND INTERFACE', { size: 16, align: 'center', color: ui.theme.textDim });
  }

  /** 未启用面板在游戏内的表现：熄屏 + 低功耗提示 + 恢复指引 */
  private drawOffline(ui: UiSurface): void {
    const ctx = ui.ctx;
    const time = performance.now() / 1000;
    const width = ui.width;
    const height = ui.height;
    ctx.save();
    ctx.fillStyle = 'rgba(4, 8, 12, 0.97)';
    ctx.fillRect(0, 0, width, height);
    ctx.strokeStyle = 'rgba(255, 166, 61, 0.35)';
    ctx.lineWidth = 2;
    for (let i = 0; i < 14; i += 1) {
      const y = ((i / 14) * height + time * 26) % height;
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
      ctx.stroke();
    }
    ctx.fillStyle = 'rgba(255, 166, 61, ' + (0.55 + 0.35 * Math.sin(time * 3)).toFixed(3) + ')';
    ctx.font = 'bold 42px "Microsoft YaHei", system-ui, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('终 端 已 下 线', width / 2, height / 2 - 60);
    ctx.font = '24px "Microsoft YaHei", system-ui, sans-serif';
    ctx.fillStyle = 'rgba(255, 200, 150, 0.9)';
    ctx.fillText(this.availability.reason || '该面板当前不可用', width / 2, height / 2 + 4);
    if (this.availability.hint) {
      ctx.font = '20px "Microsoft YaHei", system-ui, sans-serif';
      ctx.fillStyle = 'rgba(200, 220, 235, 0.75)';
      ctx.fillText(this.availability.hint, width / 2, height / 2 + 44);
    }
    ctx.font = '18px "Microsoft YaHei", system-ui, sans-serif';
    ctx.fillStyle = 'rgba(255, 166, 61, 0.7)';
    ctx.fillText('LOW POWER MODE · ' + this.definition.title, width / 2, height - 40);
    ctx.restore();
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.blur();
    this.controller?.dispose?.();
    this.host.scene.remove(this.group);
    this.screen.dispose();
    // Decorations may borrow ship-wide materials/textures. Never dispose those.
    const sharedMaterials = new Set<THREE.Material>(Object.values(this.host.materials));
    const sharedTextures = new Set<THREE.Texture>();
    for (const material of sharedMaterials) {
      for (const value of Object.values(material)) if (value instanceof THREE.Texture) sharedTextures.add(value);
    }
    const geometries = new Set<THREE.BufferGeometry>();
    const materials = new Set<THREE.Material>();
    const textures = new Set<THREE.Texture>();
    this.decoration.traverse((object) => {
      if (!(object instanceof THREE.Mesh)) return;
      geometries.add(object.geometry);
      for (const material of Array.isArray(object.material) ? object.material : [object.material]) {
        if (sharedMaterials.has(material)) continue;
        materials.add(material);
        for (const value of Object.values(material)) {
          if (value instanceof THREE.Texture && !sharedTextures.has(value)) textures.add(value);
        }
      }
    });
    geometries.forEach((geometry) => geometry.dispose());
    materials.forEach((material) => material.dispose());
    textures.forEach((texture) => texture.dispose());
    this.group.clear();
  }
}
