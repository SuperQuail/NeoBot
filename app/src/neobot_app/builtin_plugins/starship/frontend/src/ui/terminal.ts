// ui/terminal.ts —— 终端运行时：3D 站位 + 全息屏 + 输入路由 + 数据轮询 + 可用性表现。

import * as THREE from 'three';
import type { Input } from '../core/input';
import type { Hud } from '../core/hud';
import type { QualityPreset } from '../config';
import { consoleApi, gameApi, type Pollable } from '../net/api';
import type { ShipMaterials } from '../world/materials';
import { createSignTexture } from '../world/materials';
import type { StationAnchor } from '../world/ship';
import { HoloScreen, createStationRig } from './holo';
import { UiSurface } from './surface';
import type { TextCapture } from './textinput';
import type { Availability, ShellState } from '../state';
import type { GameActions } from '../core/actions';

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
  private active = false;
  private dirty = true;
  private idleAccumulator = 0;
  private availability: Availability = { available: true, reason: '', hint: '', readOnly: false };
  private baseAccent: number;
  private disposed = false;
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
    });
    this.screen = rig.screen;
    this.group.add(rig.group);
    definition.decorate?.(this.group, host.materials);

    // 名牌
    const sign = new THREE.Mesh(
      new THREE.PlaneGeometry(1.15, 0.36),
      new THREE.MeshBasicMaterial({
        map: createSignTexture(definition.title, definition.subtitle, {
          width: 512,
          height: 160,
          accent: '#' + definition.accent.toString(16).padStart(6, '0'),
        }),
        transparent: true,
        side: THREE.DoubleSide,
      }),
    );
    // 名牌挂在全息屏上方的框架上，避免挡住投影
    sign.position.set(0, 2.42, -0.9);
    this.group.add(sign);

    this.group.position.copy(anchor.position);
    this.group.rotation.y = anchor.yaw;
    host.scene.add(this.group);

    // 直接复用全息屏的画布：UiSurface 画的就是贴到曲面屏上的那张图
    this.ui = new UiSurface(
      this.screen.canvas.width,
      this.screen.canvas.height,
      '#33d6ff',
      this.screen.canvas,
    );
    this.controller = definition.create
      ? definition.create({
          host,
          anchor,
          ui: this.ui,
          shell: host.shell,
          redraw: () => this.markDirty(),
          toast: host.toast,
          confirm: host.confirm,
        })
      : null;
    this.drawFrame(true);
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
      availability.readOnly !== this.availability.readOnly;
    this.availability = availability;
    this.screen.setAccent(availability.available ? this.baseAccent : OFFLINE_ACCENT);
    if (changed) this.markDirty();
  }

  /** 聚焦视角：站在弧形屏外侧（凹面正前方）看向屏幕中心 */
  focusView(): { position: THREE.Vector3; target: THREE.Vector3 } {
    const forward = new THREE.Vector3(0, 0, 1).applyAxisAngle(
      new THREE.Vector3(0, 1, 0),
      this.anchor.yaw,
    );
    const distance = this.screen.radius + 0.75;
    const position = this.anchor.position
      .clone()
      .add(forward.multiplyScalar(distance))
      .add(new THREE.Vector3(0, 1.52, 0));
    const target = this.screen.worldCenter(new THREE.Vector3());
    return { position, target };
  }

  focus(): void {
    if (this.active) return;
    this.active = true;
    this.controller?.onFocus?.();
    for (const poller of this.controller?.pollers ?? []) poller.start(true);
    this.markDirty();
  }

  blur(): void {
    if (!this.active) return;
    this.active = false;
    this.controller?.onBlur?.();
    for (const poller of this.controller?.pollers ?? []) poller.stop();
    this.markDirty();
  }

  /** 屏幕射线命中：更新光标位置，返回是否消费了本次点击 */
  handlePointer(intersection: THREE.Intersection | null, clicked: boolean, wheel: number): void {
    if (!intersection || !intersection.uv) {
      this.ui.cursor.inside = false;
      return;
    }
    const x = intersection.uv.x * this.ui.width;
    const y = (1 - intersection.uv.y) * this.ui.height;
    const moved = Math.abs(x - this.ui.cursor.x) > 0.5 || Math.abs(y - this.ui.cursor.y) > 0.5;
    this.ui.cursor.x = x;
    this.ui.cursor.y = y;
    this.ui.cursor.inside = true;
    if (clicked) {
      this.ui.clicked = true;
      this.markDirty();
    }
    if (moved) this.markDirty();
    if (wheel !== 0) {
      const hovered = this.ui.hitTest(x, y);
      if (hovered) {
        const id = hovered.split(':')[0];
        this.ui.scrollBy(id, wheel * 0.05);
        this.markDirty();
      }
    }
  }

  update(dt: number): void {
    if (this.disposed) return;
    const interactive = this.active;
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
      this.drawFrame(interactive);
      this.dirty = false;
    }
  }

  private drawFrame(interactive: boolean): void {
    const ui = this.ui;
    ui.clicked = false;
    ui.hoverId = null;
    if (!this.availability.available) {
      this.drawOffline(ui);
      ui.end();
      return;
    }
    ui.begin(1 / 30, this.definition.title, this.definition.subtitle);
    if (this.availability.reason) {
      ui.text(24, 92, '⚠ ' + this.availability.reason, {
        size: 17,
        color: ui.theme.warn,
      });
      if (this.availability.hint) {
        ui.text(24, 116, this.availability.hint, { size: 15, color: ui.theme.textDim });
      }
    }
    if (this.override) this.override(ui, interactive);
    else this.controller?.draw(ui, interactive);
    ui.end();
    // canvas 改了必须让贴图重新上传，否则屏幕上永远是第一帧
    this.screen.texture.needsUpdate = true;
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
  }
}
