// ui/surface.ts —— 全息屏上的即时模式 UI 工具箱（画到 Canvas，再贴到 3D 曲面屏）。
// 设计：绘制即命中测试 —— 画按钮时把矩形登记进本帧命中表，点击时直接按 id 判定，
// 不需要维护两套布局。

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface Theme {
  accent: string;
  accentDim: string;
  text: string;
  textDim: string;
  ok: string;
  warn: string;
  error: string;
  panel: string;
  panelEdge: string;
  grid: string;
}

export function makeTheme(accent: string): Theme {
  return {
    accent,
    accentDim: hexWithAlpha(accent, 0.35),
    text: '#e6f4ff',
    textDim: '#8fb0c8',
    ok: '#4fe0a0',
    warn: '#ffc861',
    error: '#ff7b7b',
    panel: 'rgba(10, 26, 38, 0.72)',
    panelEdge: hexWithAlpha(accent, 0.55),
    grid: 'rgba(80, 180, 220, 0.08)',
  };
}

export function hexWithAlpha(hex: string, alpha: number): string {
  const value = hex.replace('#', '');
  const r = parseInt(value.slice(0, 2), 16);
  const g = parseInt(value.slice(2, 4), 16);
  const b = parseInt(value.slice(4, 6), 16);
  return 'rgba(' + r + ',' + g + ',' + b + ',' + alpha + ')';
}

export interface TextOptions {
  size?: number;
  color?: string;
  align?: CanvasTextAlign;
  baseline?: CanvasTextBaseline;
  weight?: string;
  maxWidth?: number;
  mono?: boolean;
}

export interface Frame {
  hits: Array<{ id: string; rect: Rect }>;
}

const FONT_STACK = '"Microsoft YaHei", "PingFang SC", "Segoe UI", system-ui, sans-serif';
const MONO_STACK = '"JetBrains Mono", "Cascadia Mono", Consolas, monospace';

export class UiSurface {
  readonly canvas: HTMLCanvasElement;
  readonly ctx: CanvasRenderingContext2D;
  readonly theme: Theme;
  cursor = { x: 0, y: 0, inside: false, down: false };
  hoverId: string | null = null;
  /** 上一次绘制登记的可点击区域（命中测试用） */
  private hits: Array<{ id: string; rect: Rect }> = [];
  private previousHits: Array<{ id: string; rect: Rect }> = [];
  private scroll = new Map<string, number>();
  private time = 0;
  readonly width: number;
  readonly height: number;

  constructor(width: number, height: number, accent: string, canvas?: HTMLCanvasElement) {
    this.width = width;
    this.height = height;
    // 传入画布时直接复用（全息屏的贴图就来自这块画布），否则新建一块
    this.canvas = canvas ?? document.createElement('canvas');
    this.canvas.width = width;
    this.canvas.height = height;
    const ctx = this.canvas.getContext('2d');
    if (!ctx) throw new Error('无法创建 2D 画布上下文');
    this.ctx = ctx;
    this.theme = makeTheme(accent);
  }

  begin(dt: number, title: string, subtitle: string): void {
    this.time += dt;
    this.previousHits = this.hits;
    this.hits = [];
    const ctx = this.ctx;
    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, this.width, this.height);
    const gradient = ctx.createLinearGradient(0, 0, this.width, this.height);
    gradient.addColorStop(0, 'rgba(4, 14, 22, 0.96)');
    gradient.addColorStop(0.55, 'rgba(6, 20, 30, 0.94)');
    gradient.addColorStop(1, 'rgba(3, 10, 18, 0.97)');
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, this.width, this.height);

    ctx.strokeStyle = this.theme.grid;
    ctx.lineWidth = 1;
    for (let x = 0; x < this.width; x += 32) {
      ctx.beginPath();
      ctx.moveTo(x + 0.5, 0);
      ctx.lineTo(x + 0.5, this.height);
      ctx.stroke();
    }
    for (let y = 0; y < this.height; y += 32) {
      ctx.beginPath();
      ctx.moveTo(0, y + 0.5);
      ctx.lineTo(this.width, y + 0.5);
      ctx.stroke();
    }
    // 扫描线
    ctx.fillStyle = 'rgba(120, 220, 255, 0.025)';
    for (let y = 0; y < this.height; y += 4) ctx.fillRect(0, y, this.width, 1);

    // 标题栏
    ctx.fillStyle = hexWithAlpha(this.theme.accent, 0.14);
    ctx.fillRect(0, 0, this.width, 64);
    ctx.fillStyle = this.theme.accent;
    ctx.fillRect(0, 62, this.width, 2);
    ctx.font = 'bold 30px ' + FONT_STACK;
    ctx.fillStyle = this.theme.text;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';
    ctx.fillText(title, 24, 33);
    ctx.font = '18px ' + FONT_STACK;
    ctx.fillStyle = this.theme.textDim;
    ctx.textAlign = 'right';
    ctx.fillText(subtitle, this.width - 24, 34);
    ctx.textAlign = 'left';
  }

  end(): void {
    const ctx = this.ctx;
    // 光标
    if (this.cursor.inside) {
      const { x, y } = this.cursor;
      ctx.save();
      ctx.strokeStyle = this.theme.accent;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(x - 12, y);
      ctx.lineTo(x - 4, y);
      ctx.moveTo(x + 4, y);
      ctx.lineTo(x + 12, y);
      ctx.moveTo(x, y - 12);
      ctx.lineTo(x, y - 4);
      ctx.moveTo(x, y + 4);
      ctx.lineTo(x, y + 12);
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(x, y, 3.5, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
    }
    // 四角装饰
    ctx.strokeStyle = hexWithAlpha(this.theme.accent, 0.8);
    ctx.lineWidth = 3;
    const corner = 26;
    const pad = 8;
    const corners: Array<[number, number, number, number]> = [
      [pad, pad, 1, 1],
      [this.width - pad, pad, -1, 1],
      [pad, this.height - pad, 1, -1],
      [this.width - pad, this.height - pad, -1, -1],
    ];
    for (const [cx, cy, sx, sy] of corners) {
      ctx.beginPath();
      ctx.moveTo(cx + sx * corner, cy);
      ctx.lineTo(cx, cy);
      ctx.lineTo(cx, cy + sy * corner);
      ctx.stroke();
    }
    ctx.restore();
  }

  // ------------------------------------------------------------------
  // 基础图元
  // ------------------------------------------------------------------

  text(x: number, y: number, value: string, options: TextOptions = {}): void {
    const ctx = this.ctx;
    ctx.font =
      (options.weight ? options.weight + ' ' : '') +
      (options.size ?? 18) +
      'px ' +
      (options.mono ? MONO_STACK : FONT_STACK);
    ctx.fillStyle = options.color || this.theme.text;
    ctx.textAlign = options.align || 'left';
    ctx.textBaseline = options.baseline || 'alphabetic';
    if (options.maxWidth) ctx.fillText(value, x, y, options.maxWidth);
    else ctx.fillText(value, x, y);
  }

  panel(rect: Rect, options: { title?: string; tone?: string; glow?: boolean } = {}): void {
    const ctx = this.ctx;
    ctx.save();
    ctx.fillStyle = this.theme.panel;
    ctx.fillRect(rect.x, rect.y, rect.w, rect.h);
    ctx.strokeStyle = options.tone || this.theme.panelEdge;
    ctx.lineWidth = 1.5;
    ctx.strokeRect(rect.x + 0.5, rect.y + 0.5, rect.w - 1, rect.h - 1);
    const cut = 14;
    ctx.beginPath();
    ctx.moveTo(rect.x, rect.y + cut);
    ctx.lineTo(rect.x + cut, rect.y);
    ctx.moveTo(rect.x + rect.w - cut, rect.y);
    ctx.lineTo(rect.x + rect.w, rect.y + cut);
    ctx.moveTo(rect.x, rect.y + rect.h - cut);
    ctx.lineTo(rect.x + cut, rect.y + rect.h);
    ctx.moveTo(rect.x + rect.w - cut, rect.y + rect.h);
    ctx.lineTo(rect.x + rect.w, rect.y + rect.h - cut);
    ctx.strokeStyle = options.tone || this.theme.accent;
    ctx.lineWidth = 3;
    ctx.stroke();
    if (options.title) {
      ctx.fillStyle = options.tone || this.theme.accent;
      ctx.font = 'bold 19px ' + FONT_STACK;
      this.text(rect.x + 14, rect.y + 24, options.title, { size: 19, weight: 'bold', color: options.tone || this.theme.accent });
      ctx.fillStyle = hexWithAlpha('#ffffff', 0.06);
      ctx.fillRect(rect.x + 1, rect.y + 34, rect.w - 2, 1);
    }
    ctx.restore();
  }

  /** 登记命中区域；返回是否被点击 */
  private hit(id: string, rect: Rect): boolean {
    this.hits.push({ id, rect });
    const inside =
      this.cursor.x >= rect.x &&
      this.cursor.x <= rect.x + rect.w &&
      this.cursor.y >= rect.y &&
      this.cursor.y <= rect.y + rect.h;
    if (inside) this.hoverId = id;
    return inside;
  }

  isHovered(id: string): boolean {
    return this.hoverId === id;
  }

  /** 当前光标是否落在 id 上（用于高亮） */
  private hoverRect(id: string, rect: Rect): boolean {
    this.hits.push({ id, rect });
    const inside =
      this.cursor.x >= rect.x &&
      this.cursor.x <= rect.x + rect.w &&
      this.cursor.y >= rect.y &&
      this.cursor.y <= rect.y + rect.h;
    if (inside) this.hoverId = id;
    return inside;
  }

  button(
    id: string,
    rect: Rect,
    label: string,
    options: { disabled?: boolean; tone?: string; hint?: string; size?: number } = {},
  ): boolean {
    const ctx = this.ctx;
    const hovered = this.hoverRect(id, rect);
    const tone = options.tone || this.theme.accent;
    ctx.save();
    ctx.fillStyle = options.disabled
      ? 'rgba(60,70,80,0.35)'
      : hovered
        ? hexWithAlpha(tone, 0.32)
        : hexWithAlpha(tone, 0.12);
    ctx.fillRect(rect.x, rect.y, rect.w, rect.h);
    ctx.strokeStyle = options.disabled ? 'rgba(120,130,140,0.4)' : tone;
    ctx.lineWidth = hovered ? 2.5 : 1.5;
    ctx.strokeRect(rect.x + 0.5, rect.y + 0.5, rect.w - 1, rect.h - 1);
    ctx.font = 'bold ' + (options.size ?? 18) + 'px ' + FONT_STACK;
    ctx.fillStyle = options.disabled ? 'rgba(180,190,200,0.5)' : this.theme.text;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(label, rect.x + rect.w / 2, rect.y + rect.h / 2 + 1, rect.w - 12);
    ctx.restore();
    if (options.disabled) return false;
    return hovered && this.clicked;
  }

  /** 由 Terminal 在点击帧置位 */
  clicked = false;

  toggle(id: string, rect: Rect, label: string, value: boolean): boolean {
    const ctx = this.ctx;
    const hovered = this.hoverRect(id, rect);
    ctx.save();
    ctx.fillStyle = hovered ? 'rgba(40,60,80,0.6)' : 'rgba(20,32,44,0.55)';
    ctx.fillRect(rect.x, rect.y, rect.w, rect.h);
    ctx.strokeStyle = value ? this.theme.ok : this.theme.textDim;
    ctx.lineWidth = 1.5;
    ctx.strokeRect(rect.x + 0.5, rect.y + 0.5, rect.w - 1, rect.h - 1);
    const trackW = 46;
    const trackX = rect.x + rect.w - trackW - 14;
    const trackY = rect.y + rect.h / 2 - 6;
    ctx.fillStyle = value ? hexWithAlpha(this.theme.ok, 0.35) : 'rgba(90,100,110,0.45)';
    ctx.fillRect(trackX, trackY, trackW, 12);
    ctx.fillStyle = value ? this.theme.ok : '#8a949e';
    ctx.fillRect(value ? trackX + trackW - 12 : trackX, trackY - 3, 12, 18);
    this.text(rect.x + 12, rect.y + rect.h / 2 + 6, label, { size: 17 });
    ctx.restore();
    return hovered && this.clicked;
  }

  progress(
    rect: Rect,
    value: number,
    options: { label?: string; color?: string; showValue?: boolean; suffix?: string } = {},
  ): void {
    const ctx = this.ctx;
    const color = options.color || this.theme.accent;
    const clamped = Math.max(0, Math.min(1, value));
    ctx.save();
    ctx.fillStyle = 'rgba(16, 30, 42, 0.85)';
    ctx.fillRect(rect.x, rect.y, rect.w, rect.h);
    const gradient = ctx.createLinearGradient(rect.x, 0, rect.x + rect.w, 0);
    gradient.addColorStop(0, hexWithAlpha(color, 0.55));
    gradient.addColorStop(1, color);
    ctx.fillStyle = gradient;
    ctx.fillRect(rect.x, rect.y, rect.w * clamped, rect.h);
    ctx.strokeStyle = hexWithAlpha(color, 0.7);
    ctx.lineWidth = 1;
    ctx.strokeRect(rect.x + 0.5, rect.y + 0.5, rect.w - 1, rect.h - 1);
    if (options.label) {
      this.text(rect.x, rect.y - 6, options.label, { size: 15, color: this.theme.textDim });
    }
    if (options.showValue !== false) {
      this.text(
        rect.x + rect.w - 8,
        rect.y + rect.h / 2 + 6,
        (clamped * 100).toFixed(0) + '%' + (options.suffix || ''),
        { size: 15, align: 'right', color: this.theme.text },
      );
    }
    ctx.restore();
  }

  sparkline(
    rect: Rect,
    values: number[],
    options: { color?: string; fill?: boolean; label?: string; valueText?: string } = {},
  ): void {
    const ctx = this.ctx;
    const color = options.color || this.theme.accent;
    ctx.save();
    ctx.fillStyle = 'rgba(10, 22, 32, 0.6)';
    ctx.fillRect(rect.x, rect.y, rect.w, rect.h);
    if (values.length > 1) {
      const max = Math.max(...values, 1);
      const min = Math.min(...values, 0);
      const range = Math.max(max - min, 1);
      ctx.beginPath();
      values.forEach((value, index) => {
        const x = rect.x + (index / (values.length - 1)) * rect.w;
        const y = rect.y + rect.h - ((value - min) / range) * (rect.h - 12) - 6;
        if (index === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.stroke();
      if (options.fill) {
        ctx.lineTo(rect.x + rect.w, rect.y + rect.h);
        ctx.lineTo(rect.x, rect.y + rect.h);
        ctx.closePath();
        ctx.fillStyle = hexWithAlpha(color, 0.16);
        ctx.fill();
      }
    }
    ctx.strokeStyle = hexWithAlpha(color, 0.5);
    ctx.lineWidth = 1;
    ctx.strokeRect(rect.x + 0.5, rect.y + 0.5, rect.w - 1, rect.h - 1);
    if (options.label) {
      this.text(rect.x + 8, rect.y + 20, options.label, { size: 15, color: this.theme.textDim });
    }
    if (options.valueText) {
      this.text(rect.x + rect.w - 8, rect.y + 20, options.valueText, {
        size: 16,
        align: 'right',
        color: this.theme.text,
      });
    }
    ctx.restore();
  }

  bars(
    rect: Rect,
    items: Array<{ label: string; value: number; color?: string }>,
    options: { max?: number; label?: string } = {},
  ): void {
    const ctx = this.ctx;
    const max = options.max ?? Math.max(...items.map((item) => item.value), 1);
    const barHeight = Math.min(26, (rect.h - 8) / Math.max(items.length, 1) - 6);
    ctx.save();
    items.forEach((item, index) => {
      const y = rect.y + index * (barHeight + 6);
      const labelWidth = 120;
      const barWidth = rect.w - labelWidth - 70;
      this.text(rect.x, y + barHeight - 6, item.label, { size: 15, color: this.theme.textDim, maxWidth: labelWidth - 8 });
      ctx.fillStyle = 'rgba(20, 36, 50, 0.8)';
      ctx.fillRect(rect.x + labelWidth, y, barWidth, barHeight);
      const ratio = Math.max(0, Math.min(1, item.value / max));
      ctx.fillStyle = item.color || this.theme.accent;
      ctx.fillRect(rect.x + labelWidth, y, barWidth * ratio, barHeight);
      this.text(rect.x + rect.w, y + barHeight - 6, String(item.value), {
        size: 15,
        align: 'right',
        color: this.theme.text,
      });
    });
    ctx.restore();
  }

  /** 可滚动的列表；返回被点击的索引（-1 表示无） */
  list(
    id: string,
    rect: Rect,
    items: Array<{ label: string; sub?: string; badge?: string; tone?: string; active?: boolean }>,
    options: { rowHeight?: number; scrollable?: boolean } = {},
  ): number {
    const ctx = this.ctx;
    const rowHeight = options.rowHeight ?? 44;
    const offset = options.scrollable === false ? 0 : this.scroll.get(id) ?? 0;
    const visible = Math.floor(rect.h / rowHeight);
    const maxOffset = Math.max(0, items.length - visible);
    const clampedOffset = Math.max(0, Math.min(maxOffset, Math.round(offset)));
    this.scroll.set(id, clampedOffset);
    ctx.save();
    ctx.beginPath();
    ctx.rect(rect.x, rect.y, rect.w, rect.h);
    ctx.clip();
    ctx.fillStyle = 'rgba(8, 20, 30, 0.5)';
    ctx.fillRect(rect.x, rect.y, rect.w, rect.h);
    let clickedIndex = -1;
    for (let index = clampedOffset; index < Math.min(items.length, clampedOffset + visible + 1); index += 1) {
      const item = items[index];
      const y = rect.y + (index - clampedOffset) * rowHeight;
      const rowRect: Rect = { x: rect.x, y, w: rect.w - (maxOffset > 0 ? 10 : 0), h: rowHeight - 2 };
      const hovered = this.hoverRect(id + ':' + index, rowRect);
      if (hovered && this.clicked) clickedIndex = index;
      ctx.fillStyle = hovered
        ? 'rgba(60, 120, 160, 0.35)'
        : item.active
          ? 'rgba(40, 90, 120, 0.35)'
          : index % 2 === 0
            ? 'rgba(12, 26, 38, 0.45)'
            : 'rgba(10, 22, 32, 0.35)';
      ctx.fillRect(rowRect.x, rowRect.y, rowRect.w, rowRect.h);
      if (item.tone) {
        ctx.fillStyle = item.tone;
        ctx.fillRect(rect.x, y, 3, rowHeight - 2);
      }
      this.text(rect.x + 14, y + (item.sub ? 19 : rowHeight / 2 + 4), item.label, {
        size: 17,
        maxWidth: rect.w - 140,
      });
      if (item.sub) {
        this.text(rect.x + 14, y + 36, item.sub, {
          size: 14,
          color: this.theme.textDim,
          maxWidth: rect.w - 140,
        });
      }
      if (item.badge) {
        this.text(rect.x + rect.w - 20, y + rowHeight / 2 + 4, item.badge, {
          size: 14,
          align: 'right',
          color: this.theme.textDim,
        });
      }
    }
    ctx.restore();
    // 滚动条
    if (maxOffset > 0) {
      const trackHeight = rect.h;
      const thumbHeight = Math.max(28, (visible / items.length) * trackHeight);
      const thumbY = rect.y + (clampedOffset / maxOffset) * (trackHeight - thumbHeight);
      ctx.fillStyle = 'rgba(80, 140, 180, 0.35)';
      ctx.fillRect(rect.x + rect.w - 6, thumbY, 5, thumbHeight);
    }
    return clickedIndex;
  }

  /** 键值行 */
  keyValue(x: number, y: number, width: number, label: string, value: string, color?: string): void {
    this.text(x, y, label, { size: 16, color: this.theme.textDim });
    this.text(x + width, y, value, { size: 17, align: 'right', color: color || this.theme.text });
  }

  /** 可编辑文本域；返回本帧的（可能被修改的）内容 */
  textField(
    id: string,
    rect: Rect,
    value: string,
    options: { placeholder?: string; focused?: boolean; caret?: number; multiline?: boolean } = {},
  ): { clicked: boolean; hovered: boolean } {
    const ctx = this.ctx;
    const hovered = this.hoverRect(id, rect);
    const clicked = hovered && this.clicked;
    ctx.save();
    ctx.fillStyle = options.focused ? 'rgba(20, 50, 70, 0.85)' : 'rgba(14, 28, 40, 0.75)';
    ctx.fillRect(rect.x, rect.y, rect.w, rect.h);
    ctx.strokeStyle = options.focused ? this.theme.accent : hexWithAlpha(this.theme.accent, 0.4);
    ctx.lineWidth = options.focused ? 2 : 1;
    ctx.strokeRect(rect.x + 0.5, rect.y + 0.5, rect.w - 1, rect.h - 1);
    ctx.beginPath();
    ctx.rect(rect.x + 6, rect.y + 4, rect.w - 12, rect.h - 8);
    ctx.clip();
    const display = value || options.placeholder || '';
    ctx.font = (options.multiline ? '16px ' : '17px ') + MONO_STACK;
    ctx.fillStyle = value ? this.theme.text : this.theme.textDim;
    const lines = options.multiline ? display.split('\n').slice(0, Math.floor(rect.h / 20)) : [display];
    lines.forEach((line, index) => {
      ctx.fillText(line, rect.x + 10, rect.y + 24 + index * 20);
    });
    if (options.focused && Math.floor(this.time * 2) % 2 === 0) {
      const caretLine = options.caret ?? value.length;
      const before = value.slice(0, caretLine);
      const width = ctx.measureText(before).width;
      ctx.fillStyle = this.theme.accent;
      ctx.fillRect(rect.x + 10 + width + 1, rect.y + 8, 2, rect.h - 16);
    }
    ctx.restore();
    return { clicked, hovered };
  }

  /** 环形仪表（3D 感更强，用于关键指标） */
  gauge(
    center: { x: number; y: number },
    radius: number,
    value: number,
    options: { label?: string; color?: string; valueText?: string } = {},
  ): void {
    const ctx = this.ctx;
    const color = options.color || this.theme.accent;
    const clamped = Math.max(0, Math.min(1, value));
    ctx.save();
    ctx.lineWidth = 10;
    ctx.strokeStyle = 'rgba(30, 50, 66, 0.9)';
    ctx.beginPath();
    ctx.arc(center.x, center.y, radius, Math.PI * 0.75, Math.PI * 0.25 + Math.PI * 2 * 0.999);
    ctx.stroke();
    ctx.strokeStyle = color;
    ctx.beginPath();
    ctx.arc(center.x, center.y, radius, Math.PI * 0.75, Math.PI * 0.75 + clamped * Math.PI * 1.5);
    ctx.stroke();
    ctx.fillStyle = color;
    for (let i = 0; i <= 24; i += 1) {
      const angle = Math.PI * 0.75 + (i / 24) * Math.PI * 1.5;
      const inner = radius - 16;
      const outer = radius - 11;
      ctx.globalAlpha = i / 24 <= clamped ? 1 : 0.25;
      ctx.beginPath();
      ctx.moveTo(center.x + Math.cos(angle) * inner, center.y + Math.sin(angle) * inner);
      ctx.lineTo(center.x + Math.cos(angle) * outer, center.y + Math.sin(angle) * outer);
      ctx.lineWidth = 2;
      ctx.strokeStyle = color;
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
    if (options.valueText) {
      this.text(center.x, center.y + 8, options.valueText, {
        size: 26,
        align: 'center',
        color: this.theme.text,
        weight: 'bold',
      });
    }
    if (options.label) {
      this.text(center.x, center.y + radius - 6, options.label, {
        size: 15,
        align: 'center',
        color: this.theme.textDim,
      });
    }
    ctx.restore();
  }

  scrollBy(id: string, delta: number): void {
    const current = this.scroll.get(id) ?? 0;
    this.scroll.set(id, current + delta);
  }

  scrollReset(id: string): void {
    this.scroll.set(id, 0);
  }

  /** 命中测试：把点击坐标交给本帧登记的矩形 */
  hitTest(x: number, y: number): string | null {
    for (let index = this.previousHits.length - 1; index >= 0; index -= 1) {
      const hit = this.previousHits[index];
      if (x >= hit.rect.x && x <= hit.rect.x + hit.rect.w && y >= hit.rect.y && y <= hit.rect.y + hit.rect.h) {
        return hit.id;
      }
    }
    return null;
  }
}
