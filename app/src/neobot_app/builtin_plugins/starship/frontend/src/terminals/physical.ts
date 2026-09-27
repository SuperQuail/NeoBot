// Real business controls mounted on the console, not canvas hit rectangles.
import * as THREE from 'three';
import { terminalLayout, placeOperatingSurface } from '../ui/terminal-layout';
import { drawProtossCommand, drawProtossHeader } from '../ui/protoss-command';
import { Poller, type Pollable } from '../net/api';
import type { TerminalContext, TerminalController } from '../ui/terminal';
import type { UiSurface } from '../ui/surface';
import { formatCost, formatDuration, formatNumber, formatTokens,
  type OverviewPayload, type SystemPayload, type UsagePayload, type PluginListPayload,
  type PluginItem, type LatencyPayload, type PowerPayload, type SimpleMessage } from './shared';

const IDS = new Set(['navigation', 'dashboard', 'system', 'usage', 'bots', 'plugins']);
const DESTINATIONS = ['天鹅座 λ-4', '猎户悬臂 K-17', '南门二 β', '天苑四 ε', '蛇夫座 9',
  '武仙座 τ', '船底座 HD-7', '仙女座 M31-附', '半人马 ζ', '天琴座 Vega-2'];
interface Key { label: string; action: () => void | Promise<void>; disabled?: boolean; danger?: boolean }
interface Readout { title: string; value: string; ratio: number | null; keys: Key[] }
interface Tasks { scheduled?: unknown[]; background?: unknown[] }
interface Services { items?: Array<{ name?: string; available?: boolean }> }

export function createPhysicalTerminal(id: string, ctx: TerminalContext, accent: number): PhysicalTerminal | null {
  return IDS.has(id) ? new PhysicalTerminal(id, ctx, accent) : null;
}

export class PhysicalTerminal implements TerminalController {
  readonly group = new THREE.Group();
  readonly targets: THREE.Mesh[] = [];
  readonly operatingSurface = new THREE.Group();
  readonly pollers: Pollable[] = [];
  private readonly atlas = document.createElement('canvas');
  private readonly texture: THREE.CanvasTexture;
  private readonly labelMaterial: THREE.MeshBasicMaterial;
  private readonly ring: THREE.InstancedMesh;
  private readonly needle: THREE.Mesh;
  private readonly geometry = new Set<THREE.BufferGeometry>();
  private readonly materials = new Set<THREE.Material>();
  private readonly gold = new THREE.MeshStandardMaterial({ color: 0x827452, metalness: 0.65, roughness: 0.44 });
  private readonly dark = new THREE.MeshStandardMaterial({ color: 0x172532, metalness: 0.6, roughness: 0.45 });
  private readonly warning = new THREE.MeshStandardMaterial({ color: 0x9d5034, emissive: 0x3f1006, metalness: 0.5, roughness: 0.3 });
  private readonly touch = new THREE.MeshStandardMaterial({ color: 0x21414a, emissive: 0x103f59, emissiveIntensity: 0.18, metalness: 0.4, roughness: 0.44 });
  private readonly hologram = new THREE.MeshBasicMaterial({ color: 0x228bcc, transparent: true, opacity: 0.105, depthWrite: false, side: THREE.DoubleSide, blending: THREE.AdditiveBlending, toneMapped: false });
  private readonly holoDisabled = new THREE.MeshBasicMaterial({ color: 0x28607c, transparent: true, opacity: 0.035, depthWrite: false, side: THREE.DoubleSide });
  private readonly holoWarning = new THREE.MeshBasicMaterial({ color: 0xdb8751, transparent: true, opacity: 0.13, depthWrite: false, side: THREE.DoubleSide, blending: THREE.AdditiveBlending });
  private readonly runes = new THREE.LineBasicMaterial({ color: 0x4aaadd, transparent: true, opacity: 0.3, depthWrite: false });
  private overview: OverviewPayload | null = null;
  private system: SystemPayload | null = null;
  private usage: UsagePayload | null = null;
  private plugins: PluginListPayload | null = null;
  private bots: Array<Record<string, unknown>> | null = null;
  private latency: LatencyPayload | null = null;
  private power: PowerPayload | null = null;
  private tasks: Tasks | null = null;
  private services: Services | null = null;
  private readonly errors = new Map<string, string>();
  private selected = 0;
  private metric = 0;
  private busy = false;
  private focused = false;
  private disposed = false;
  private available = true;
  private reason = '';
  private signature = '';
  private keys: Key[] = [];
  private hovered: THREE.Object3D | null = null;
  private pressed = false;

  constructor(readonly id: string, private readonly ctx: TerminalContext, private readonly accent: number) {
    this.group.name = 'physical-business-' + id;
    this.atlas.width = 2048;
    this.atlas.height = 1024;
    this.texture = new THREE.CanvasTexture(this.atlas);
    this.texture.colorSpace = THREE.SRGBColorSpace;
    this.texture.generateMipmaps = false;
    this.texture.minFilter = THREE.LinearFilter;
    const labelMaterial = this.labelMaterial = new THREE.MeshBasicMaterial({
      map: this.texture, transparent: true, depthWrite: true, alphaTest: 0.02, toneMapped: false,
    });
    const light = new THREE.MeshBasicMaterial({ color: 0xffffff, toneMapped: false });
    [this.gold, this.dark, this.warning, this.touch, this.hologram, this.holoDisabled, this.holoWarning, this.runes, labelMaterial, light].forEach(m => this.materials.add(m));
    const layout = terminalLayout(id);
    placeOperatingSurface(this.operatingSurface, layout);
    this.group.add(this.operatingSurface);
    // Each visible label IS the action mesh. No detached text outside a tiny cap.
    const label = (slot: number, w: number, h: number, x: number, y: number) => {
      const geometry = new THREE.PlaneGeometry(w, h);
      const uv = geometry.getAttribute('uv');
      for (let i = 0; i < uv.count; i++) uv.setY(i, (7 - slot + uv.getY(i)) / 8);
      this.geometry.add(geometry);
      const mesh = new THREE.Mesh(geometry, labelMaterial);
      mesh.name = slot < 6 ? "action-label" : "business-readout-" + slot;
      mesh.userData.readout = slot >= 6;
      mesh.position.set(x, y, 0.035);
      this.operatingSurface.add(mesh);
      return mesh;
    };
    const columns = layout.columns, rows = 6 / columns;
    const keyWidth = columns === 2 ? (id === 'bots' ? 0.92 : 0.94) : 0.76;
    const keyHeight = 0.245;
    for (let i = 0; i < 6; i++) {
      const x = (i % columns - (columns - 1) / 2) * (layout.width / columns);
      const y = 0.12 - Math.floor(i / columns) * 0.31;
      const key = label(i, keyWidth, keyHeight, x, y);
      key.name = id + '-business-key-' + i;
      key.userData.physicalAction = i;
      key.userData.projected = id === 'navigation' || i >= 3;
      key.userData.labelWidth = keyWidth;
      key.userData.labelHeight = keyHeight;
      this.targets.push(key);
      // Recessed sensor housing follows its visible surface, not a radial yaw.
      const seatGeometry = new THREE.BoxGeometry(keyWidth + 0.022, keyHeight + 0.018, 0.018);
      this.geometry.add(seatGeometry);
      const seat = new THREE.Mesh(seatGeometry, key.userData.projected ? this.hologram : this.touch);
      seat.userData.solidConsole = !key.userData.projected;
      seat.position.set(x, y, 0.009); this.operatingSurface.add(seat);
    }
    label(6, layout.width - 0.08, 0.19, 0, 0.42);
    label(7, layout.width - 0.08, 0.19, 0, 0.12 - rows * 0.31);
    // Telemetry becomes a blue segmented gauge inside the pool, not an upright dial.
    const segment = new THREE.BoxGeometry(0.038, 0.022, 0.085);
    this.geometry.add(segment);
    this.ring = new THREE.InstancedMesh(segment, light, 24);
    const helper = new THREE.Object3D();
    for (let i = 0; i < 24; i++) {
      const angle = -Math.PI * 0.8 + i / 23 * Math.PI * 1.6;
      helper.position.set(Math.sin(angle) * 0.7, 0.858, Math.cos(angle) * 0.7);
      helper.rotation.y = angle; helper.updateMatrix();
      this.ring.setMatrixAt(i, helper.matrix); this.ring.setColorAt(i, new THREE.Color(0x1b2a32));
    }
    this.group.add(this.ring);
    const needleGeometry = new THREE.ConeGeometry(0.025, 0.105, 4);
    needleGeometry.rotateX(Math.PI / 2); needleGeometry.translate(0, 0, 0.58);
    this.geometry.add(needleGeometry);
    this.needle = new THREE.Mesh(needleGeometry, this.gold);
    this.needle.position.set(0, 0.875, 0); this.group.add(this.needle);
    this.configurePolling();
    this.sync();
  }

  private poll<T>(path: string, interval: number, receive: (data: T) => void): void {
    this.pollers.push(new Poller<T>(() => this.ctx.host.consoleApi.get<T>(path), interval, data => {
      if (this.disposed) return;
      this.errors.delete(path);
      receive(data);
      this.ctx.redraw();
      this.sync();
    }, error => { this.errors.set(path, error); this.ctx.redraw(); this.sync(); }));
  }

  private configurePolling(): void {
    if (this.id === 'system') {
      this.poll<SystemPayload>('/api/system', 3000, d => this.system = d);
      this.poll<Tasks>('/api/tasks', 15000, d => this.tasks = d);
      this.poll<Services>('/api/services', 30000, d => this.services = d);
    } else if (this.id === 'usage') {
      this.poll<UsagePayload>('/api/stats/usage?hours=24', 30000, d => this.usage = d);
    } else if (this.id === 'plugins') {
      this.poll<PluginListPayload>('/api/plugins', 12000, d => {
        this.plugins = d;
        if (typeof d.manage_enabled === 'boolean') this.ctx.shell.setManageEnabled(d.manage_enabled);
        this.selected = Math.min(this.selected, Math.max(0, (d.items?.length ?? 0) - 1));
      });
    } else if (this.id === 'bots') {
      this.poll<Array<Record<string, unknown>>>('/api/bots', 10000, d => { this.bots = d; this.selected = Math.min(this.selected, Math.max(0, d.length - 1)); });
      this.poll<LatencyPayload>('/api/series/latency', 10000, d => this.latency = d);
    } else if (this.id === 'dashboard') {
      this.poll<OverviewPayload>('/api/overview', 5000, d => this.overview = d);
      this.poll<PowerPayload>('/api/admin/power', 5000, d => this.power = d);
      this.poll<LatencyPayload>('/api/series/latency', 8000, d => this.latency = d);
    }
  }

  private refresh = (): void => { for (const poller of this.pollers) void poller.tick(); };
  private choose(delta: number, count: number): void { this.selected = (this.selected + delta + Math.max(1, count)) % Math.max(1, count); }
  private readonly refreshKey: Key = { label: '刷新遥测', action: () => this.refresh() };
  private selectMetric(index: number): void { this.metric = index; }

  private readout(): Readout {
    if (this.id === 'navigation') {
      const warping = this.ctx.host.actions.warping();
      return { title: '航点 ' + (this.selected + 1) + '/10 · ' + DESTINATIONS[this.selected],
        value: warping ? '跃迁引擎工作中' : '当前位置：' + this.ctx.host.actions.systemName(), ratio: this.selected / 9,
        keys: [
          { label: '上一航点', action: () => this.choose(-1, 10) },
          { label: '下一航点', action: () => this.choose(1, 10) },
          { label: '启动跃迁', disabled: warping, action: () => { this.ctx.host.actions.triggerWarp(true, this.selected); } },
          { label: '天鹅座 λ-4', action: () => { this.selected = 0; } },
          { label: '南门二 β', action: () => { this.selected = 2; } },
          { label: '天琴座 Vega', action: () => { this.selected = 9; } },
        ] };
    }
    if (this.id === 'plugins') {
      const items = this.plugins?.items ?? [];
      const item = items[this.selected];
      const locked = !item?.id || item.manageable === false || this.ctx.shell.availability('plugins').readOnly || this.plugins?.manage_enabled === false;
      const details = item ? [item.status || (item.enabled ? '已启用' : '已停用'),
        item.disabled_reason || item.dependency_issues?.join('；') || '依赖：' + (item.dependencies?.join(', ') || '无'),
        'v' + (item.version ?? '—') + ' · ' + (item.author ?? '未知作者')] : ['尚无模块数据'];
      return { title: item ? '模块 ' + (this.selected + 1) + '/' + items.length + ' · ' + item.name : '模块装配架',
        value: locked && item ? '只读 · ' + details[this.metric % details.length] : details[this.metric % details.length],
        ratio: item ? (item.status === 'running' ? 1 : item.enabled === false ? 0 : 0.5) : null,
        keys: [
          { label: '上个模块', disabled: !items.length, action: () => this.choose(-1, items.length) },
          { label: '下个模块', disabled: !items.length, action: () => this.choose(1, items.length) },
          { label: item?.enabled === false ? '装载模块' : '停用模块', disabled: locked, danger: item?.enabled !== false, action: () => this.pluginOperation('toggle') },
          { label: '重载模块', disabled: locked || item?.official === true || item?.hot_reload === false, danger: true, action: () => this.pluginOperation('reload') },
          { label: '状态 / 依赖', action: () => { this.metric++; } }, this.refreshKey,
        ] };
    }
    if (this.id === 'bots') {
      const bots = this.bots ?? [];
      const bot = bots[this.selected];
      const online = bot ? Boolean(bot.online) : null;
      const data = !bot ? ['尚无机器人数据'] : [
        (online ? '链路在线' : '链路离线') + ' · ' + String(bot.user_id ?? '—'),
        '今日消息 ' + formatNumber(Number(bot.today_messages ?? 0)) + ' / 累计 ' + formatNumber(Number(bot.total_messages ?? 0)),
        '平台 ' + String(bot.platform || bot.app_name || '—') + ' · 在线 ' + formatDuration(Number(bot.uptime_seconds ?? 0)),
        '链路延迟 ' + String(bot.latency_ms ?? this.latency?.current_ms ?? '—') + ' ms',
      ];
      return { title: bot ? '机器人 ' + (this.selected + 1) + '/' + bots.length + ' · ' + String(bot.nickname || bot.name || '未命名') : '通讯链路选择器',
        value: data[this.metric % data.length], ratio: online === null ? null : online ? 1 : 0,
        keys: [ { label: '上个机器人', disabled: !bots.length, action: () => this.choose(-1, bots.length) },
          { label: '下个机器人', disabled: !bots.length, action: () => this.choose(1, bots.length) },
          { label: '连接状态', action: () => this.selectMetric(0) },
          { label: '消息 / 平台', action: () => this.selectMetric(this.metric === 1 ? 2 : 1) },
          { label: '链路延迟', action: () => this.selectMetric(3) }, this.refreshKey ] };
    }
    if (this.id === 'system') {
      const info = this.system;
      const values = [info?.cpu_percent, info?.mem_percent, info?.disk_percent];
      const names = ['CPU 负载', '内存占用', '磁盘占用', '后台任务', '宿主服务'];
      const value = this.metric < 3 ? values[this.metric] == null ? '等待真实遥测' : values[this.metric]!.toFixed(1) + '%'
        : this.metric === 3 ? this.tasks ? '定时 ' + (this.tasks.scheduled?.length ?? 0) + ' · 后台 ' + (this.tasks.background?.length ?? 0) : '任务数据未加载'
        : this.services ? (this.services.items ?? []).map(s => (s.available === false ? '○ ' : '● ') + s.name).join(' / ') || '无已注册服务' : '服务数据未加载';
      return { title: '太阳核心 · ' + names[this.metric], value,
        ratio: this.metric < 3 && values[this.metric] != null ? values[this.metric]! / 100 : null,
        keys: [...names.map((label, i) => ({ label, action: () => this.selectMetric(i) })), this.refreshKey] };
    }
    if (this.id === 'usage') {
      const items = this.usage?.items ?? [];
      const totals = this.selected === 0 ? this.usage?.totals : items[this.selected - 1];
      const values = [totals?.calls, totals?.input_tokens, totals?.output_tokens, totals?.cost_cny];
      const names = ['调用次数', '输入 Token', '输出 Token', '花费'];
      const value = values[this.metric];
      // The scale is explicitly a display range, not a fabricated capacity/budget.
      const ranges = [200, 500000, 200000, 20];
      return { title: '24h · ' + (this.selected === 0 ? '全模块' : items[this.selected - 1]?.module ?? '未知模块') + ' · ' + names[this.metric],
        value: this.usage?.available === false ? '用量数据库不可用' : value == null ? '等待真实用量' :
          (this.metric === 3 ? formatCost(value) : this.metric === 0 ? formatNumber(value) : formatTokens(value)) + ' · 刻度上限 ' + ranges[this.metric],
        ratio: value == null ? null : value / ranges[this.metric],
        keys: [ { label: '调用次数', action: () => this.selectMetric(0) },
          { label: '输入 / 输出', action: () => this.selectMetric(this.metric === 1 ? 2 : 1) },
          { label: '实际花费', action: () => this.selectMetric(3) },
          { label: '上个模块', action: () => this.choose(-1, items.length + 1) },
          { label: '下个模块', action: () => this.choose(1, items.length + 1) }, this.refreshKey ] };
    }
    const status = this.ctx.shell.status;
    const info = this.overview;
    const standby = this.power?.standby ?? status.standby;
    const titles = ['全舰总览', '插件装载', '消息吞吐', '链路延迟'];
    const values = [ (standby ? '待机' : '运行') + ' · ' + (status.online ? '通讯在线' : '通讯离线') + ' · ' + formatDuration(info?.uptime_seconds ?? status.uptime_seconds),
      '运行 ' + status.plugins.running + '/' + status.plugins.total + ' · 错误 ' + status.plugins.error,
      info ? '今日 ' + formatNumber(info.today_messages) + ' · 累计 ' + formatNumber(info.total_messages) : '等待消息数据',
      this.latency?.current_ms == null ? '等待链路数据' : this.latency.current_ms.toFixed(0) + ' ms' ];
    return { title: '主控台 · ' + titles[this.metric % 4], value: values[this.metric % 4],
      ratio: this.metric % 4 === 1 && status.plugins.total ? status.plugins.running / status.plugins.total : null,
      keys: [ { label: '切换监控', action: () => { this.metric = (this.metric + 1) % 4; } }, this.refreshKey,
        { label: standby ? '恢复运行' : '进入待机', danger: !standby, action: () => this.powerOperation(standby ? 'resume' : 'standby') },
        { label: '软重启运行', danger: true, action: () => this.powerOperation('reboot') },
        { label: '重启 NeoBot', danger: true, action: () => this.powerOperation('restart') },
        { label: '插件监控', action: () => this.selectMetric(1) } ] };
  }

  private async pluginOperation(action: 'toggle' | 'reload'): Promise<void> {
    const item: PluginItem | undefined = this.plugins?.items?.[this.selected];
    if (!item?.id || item.manageable === false || this.plugins?.manage_enabled === false || this.ctx.shell.availability('plugins').readOnly) return;
    if (action === 'reload' && (item.official === true || item.hot_reload === false)) return;
    const enable = item.enabled === false;
    const title = (action === 'reload' ? '重载模块 ' : enable ? '装载模块 ' : '停用模块 ') + item.name;
    await this.confirmPost(title, action === 'reload' ? '重新导入并重启模块，期间功能暂不可用。' : enable ? '立即装载并启动模块。' :
      '立即停止模块，依赖它的模块会被联动停用。' + (item.dependents?.length ? ' 被依赖：' + item.dependents.join('、') : ''),
      '/api/plugins/' + encodeURIComponent(item.id) + '/' + action, {}, true,
      () => !this.ctx.shell.availability('plugins').readOnly && this.plugins?.manage_enabled !== false &&
        this.plugins?.items?.some(p => p.id === item.id && p.manageable !== false && p.enabled === item.enabled) === true);
  }

  private async powerOperation(action: 'resume' | 'standby' | 'reboot' | 'restart'): Promise<void> {
    const titles = { resume: '恢复运行', standby: '进入待机', reboot: '软重启运行', restart: '重启 NeoBot 进程' };
    await this.confirmPost(titles[action], action === 'restart' ? '整个 NeoBot 进程将重启，网页连接会暂时断开。' :
      action === 'standby' ? '停止回复与记忆管线，仅保留核心服务与面板。' : '重新装配运行时，消息处理会短暂中断。',
      '/api/admin/' + action, action === 'restart' ? {} : { reason: '星舰实体主控台' + titles[action] }, action !== 'resume');
  }

  private async confirmPost(title: string, body: string, path: string, payload: unknown, danger: boolean, stillAllowed = () => true): Promise<void> {
    // Lock BEFORE confirmation, not after it; double clicks can't spawn two writes.
    if (this.busy || this.disposed || !this.focused) return;
    this.busy = true;
    this.sync();
    try {
      if (!await this.ctx.confirm({ title, body, confirmLabel: '确认执行', danger })) return;
      if (this.disposed || !this.focused || !this.available || !stillAllowed()) return;
      const result = await this.ctx.host.consoleApi.post<SimpleMessage>(path, payload);
      if (this.disposed) return;
      this.ctx.toast(result.ok ? result.data?.message || '指令已执行' : result.error || '操作失败', result.ok ? 'ok' : 'error');
      this.refresh();
    } catch (error) {
      if (!this.disposed) this.ctx.toast(error instanceof Error ? error.message : '指令失败', 'error');
    } finally {
      this.busy = false;
      if (!this.disposed) { this.ctx.redraw(); this.sync(); }
    }
  }

  activate(index: number): void {
    if (!this.focused || !this.available || this.busy || this.disposed) return;
    this.keys = this.readout().keys;
    const key = this.keys[index];
    if (!key || key.disabled) return;
    void key.action();
    this.ctx.redraw();
    this.sync();
  }

  hover(object: THREE.Object3D | null, pressed: boolean): void {
    const changed = this.hovered !== object || this.pressed !== pressed;
    this.hovered = object;
    this.pressed = pressed;
    for (const cap of this.targets) {
      const focus = cap === object ? 1.035 : 1;
      cap.scale.set(focus, focus, cap === object && pressed ? 0.7 : 1);
    }
    if (changed) this.sync();
  }

  setAvailability(available: boolean, reason: string): void { this.available = available; this.reason = reason; this.sync(); }
  onFocus(): void { this.focused = true; this.sync(); }
  onBlur(): void { this.focused = false; this.hover(null, false); this.sync(); }
  draw(_ui: UiSurface): void { this.sync(); }

  sync(): void {
    if (this.disposed) return;
    const state = this.readout();
    this.keys = state.keys;
    const error = this.errors.values().next().value as string | undefined;
    const lines = [...state.keys.map(k => k.label), state.title,
      !this.available ? this.reason || '设备离线' : this.busy ? '等待确认 / 执行指令…' : error ? '遥测异常：' + error : state.value];
    const disabled = state.keys.map(k => !this.available || this.busy || !!k.disabled);
    const signature = JSON.stringify([lines, disabled, state.ratio, this.focused, this.hovered?.userData.physicalAction, this.pressed]);
    if (signature === this.signature) return;
    this.signature = signature;
    // Focused text writes depth, so rear transparent star orbits cannot sort over it.
    // Idle projections stay subdued without moving solid sensor seats/collision meshes.
    this.labelMaterial.depthWrite = this.focused;
    this.labelMaterial.opacity = this.focused ? 1 : 0.38;
    const ctx = this.atlas.getContext('2d')!;
    // Keep logical slot metrics, but supersample horizontal glyphs on long readouts.
    ctx.setTransform(4, 0, 0, 1, 0, 0);
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.clearRect(0, 0, 512, 1024);
    for (let i = 0; i < 8; i++) {
      const hovered = i < 6 && this.hovered === this.targets[i];
      ctx.globalAlpha = this.focused ? 1 : 0.68;
      const slot = { x: 0, y: i * 128, w: 512, h: 128 };
      if (i < 6) drawProtossCommand(ctx, slot, { hovered, pressed: hovered && this.pressed,
        disabled: disabled[i], danger: state.keys[i].danger });
      else if (i === 6) drawProtossHeader(ctx, slot);
      else { ctx.fillStyle = '#071423'; ctx.fillRect(slot.x, slot.y, slot.w, slot.h); }
      ctx.globalAlpha = this.focused ? 1 : 0.55;
      ctx.fillStyle = i < 6 && disabled[i] ? '#a8b7c4' : i === 7 && error ? '#ffc69a' : '#edf9ff';
      ctx.font = (i < 6 ? '600 44px' : '32px') + ' "Microsoft YaHei", system-ui, sans-serif';
      ctx.save(); ctx.translate(256, i * 128 + 64);
      const layout = terminalLayout(this.id);
      const aspectCorrection = i < 6 ? 4 * this.targets[i].userData.labelHeight / this.targets[i].userData.labelWidth : 4 * 0.19 / (layout.width - 0.08);
      ctx.scale(aspectCorrection, 1); ctx.fillText(lines[i] ?? '', 0, 0, 462 / aspectCorrection); ctx.restore();
    }
    ctx.globalAlpha = 1;
    this.runes.opacity = this.focused ? 0.5 : 0.24;
    this.hologram.opacity = this.focused ? 0.13 : 0.07;
    this.texture.needsUpdate = true;
    const ratio = state.ratio == null || !this.available ? null : THREE.MathUtils.clamp(state.ratio, 0, 1);
    for (let i = 0; i < 24; i++) this.ring.setColorAt(i, new THREE.Color(ratio != null && i < Math.ceil(ratio * 24) ? this.accent : 0x192b37));
    if (this.ring.instanceColor) this.ring.instanceColor.needsUpdate = true;
    this.needle.visible = ratio != null;
    this.needle.rotation.y = Math.PI * 0.8 - (ratio ?? 0) * Math.PI * 1.6;
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.pollers.forEach(p => p.stop());
    this.geometry.forEach(g => g.dispose());
    this.materials.forEach(m => m.dispose());
    this.ring.dispose();
    this.texture.dispose();
    this.group.removeFromParent();
  }
}
