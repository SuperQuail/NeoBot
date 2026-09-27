/**
 * Reference-derived command-slot grammar (procedural art, no copied game assets).
 * Actually inspected: https://www.gamingcfg.com/img/2502/starcraft-2-protoss.jpg
 * and https://tl.net/staff/Plexa/LotV/Campaign/solarcoreoptions.jpg .
 * Protoss command cells are recessed blue rectangles with small corner clamps;
 * the organic bronze shoulders belong to their surrounding instrument/header.
 */
export interface CommandRect { x: number; y: number; w: number; h: number }
export interface CommandState { hovered?: boolean; selected?: boolean; pressed?: boolean; disabled?: boolean; danger?: boolean }

function verticalRamp(ctx: CanvasRenderingContext2D, y: number, height: number, stops: Array<[number, string]>): CanvasGradient | string {
  const gradient = ctx.createLinearGradient(0, y, 0, y + height);
  // Geometry/input-only Canvas adapters may expose drawing no-ops rather than a GPU paint.
  if (!gradient) return stops[0][1];
  for (const [offset, color] of stops) gradient.addColorStop(offset, color);
  return gradient;
}

function bevelPath(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, cut: number): void {
  ctx.beginPath(); ctx.moveTo(x + cut, y); ctx.lineTo(x + w - cut, y);
  ctx.lineTo(x + w, y + cut); ctx.lineTo(x + w, y + h - cut);
  ctx.lineTo(x + w - cut, y + h); ctx.lineTo(x + cut, y + h);
  ctx.lineTo(x, y + h - cut); ctx.lineTo(x, y + cut); ctx.closePath();
}

/** Draw ONLY within the original full rectangular action area; text/raycast do not move. */
export function drawProtossCommand(ctx: CanvasRenderingContext2D, r: CommandRect, state: CommandState = {}): void {
  const { x, y, w, h } = r;
  const rail = Math.max(2, h * 0.055), cut = Math.min(9, h * 0.105);
  const active = (state.hovered || state.selected) && !state.disabled;
  ctx.save();
  // Heavy socket seam, not a bright outline floating on an empty leaf.
  ctx.fillStyle = '#030912'; ctx.fillRect(x, y, w, h);
  const metal = verticalRamp(ctx, y, h, [
    [0, state.disabled ? '#71818a' : active ? '#e0c887' : '#aeb9b9'],
    [0.2, active ? '#8e713b' : '#586970'], [0.52, '#223344'], [0.86, '#344456'],
    [1, active ? '#bda05d' : '#74848c'],
  ]);
  ctx.fillStyle = metal; bevelPath(ctx, x + 1, y + 1, w - 2, h - 2, cut); ctx.fill();
  const inner = { x: x + rail, y: y + rail, w: w - rail * 2, h: h - rail * 2 };
  const well = verticalRamp(ctx, y + rail, h - rail * 2, [
    [0, state.disabled ? '#15202a' : state.pressed ? '#030913' : '#12305a'],
    [0.3, '#061323'], [0.72, active ? '#12355d' : '#07172c'], [1, active ? '#25588b' : '#123461'],
  ]);
  ctx.fillStyle = well; bevelPath(ctx, inner.x, inner.y, inner.w, inner.h, cut * 0.55); ctx.fill();
  ctx.lineWidth = Math.max(1, h * 0.014);
  ctx.strokeStyle = state.disabled ? '#577184' : active ? '#f1d28a' : '#639bd5'; ctx.stroke();
  // Inset pale-blue light strip, with a dark seam between it and the metal bevel.
  ctx.strokeStyle = state.disabled ? '#2d465c' : active ? '#bce5ff' : '#244f9a';
  ctx.lineWidth = Math.max(1, rail * 0.24);
  bevelPath(ctx, inner.x + 2, inner.y + 2, inner.w - 4, inner.h - 4, cut * 0.45); ctx.stroke();
  // Four compact angled clamps distinguish carved command sockets from web buttons.
  const span = Math.min(w * 0.09, h * 0.2);
  for (const sx of [-1, 1]) for (const sy of [-1, 1]) {
    const cx = sx < 0 ? x + rail * 0.65 : x + w - rail * 0.65;
    const cy = sy < 0 ? y + rail * 0.65 : y + h - rail * 0.65;
    ctx.beginPath(); ctx.moveTo(cx - sx * span, cy);
    ctx.lineTo(cx - sx * rail, cy); ctx.lineTo(cx, cy - sy * rail);
    ctx.lineTo(cx, cy - sy * span); ctx.lineTo(cx - sx * rail * 0.6, cy - sy * rail * 1.6);
    ctx.lineTo(cx - sx * span, cy - sy * rail * 0.6); ctx.closePath();
    ctx.fillStyle = state.disabled ? '#73828b' : active ? '#e9cf91' : '#b6b9ae'; ctx.fill();
  }
  // Amber is a warning/selection accent, not the default fill of every command.
  if (state.danger) {
    ctx.fillStyle = state.disabled ? '#766959' : '#d49b62';
    ctx.fillRect(x + w * 0.38, y + h - rail * 0.7, w * 0.24, Math.max(1, rail * 0.3));
  }
  ctx.restore();
}

/** Sculpted shoulder rail belongs to the header, outside its legible central text band. */
export function drawProtossHeader(ctx: CanvasRenderingContext2D, r: CommandRect): void {
  const { x, y, w, h } = r;
  ctx.save(); ctx.fillStyle = '#071423'; ctx.fillRect(x, y, w, h);
  const metal = verticalRamp(ctx, y, h * 0.23, [[0, '#d2c5a1'], [0.3, '#84775c'], [0.65, '#484a45'], [1, '#202f40']]);
  for (const side of [-1, 1]) {
    ctx.save(); ctx.translate(side < 0 ? x : x + w, y); ctx.scale(side < 0 ? 1 : -1, 1);
    ctx.beginPath(); ctx.moveTo(0, h * 0.21); ctx.lineTo(0, h * 0.03);
    ctx.lineTo(w * 0.1, h * 0.03); ctx.quadraticCurveTo(w * 0.15, h * 0.025, w * 0.18, h * 0.1);
    ctx.lineTo(w * 0.46, h * 0.1); ctx.lineTo(w * 0.43, h * 0.17);
    ctx.lineTo(w * 0.16, h * 0.17); ctx.lineTo(w * 0.13, h * 0.21); ctx.closePath();
    ctx.fillStyle = metal; ctx.fill();
    ctx.strokeStyle = '#92b1c8'; ctx.lineWidth = Math.max(1, h * 0.012); ctx.stroke();
    ctx.restore();
  }
  ctx.fillStyle = '#477ba7'; ctx.fillRect(x + 6, y + h - 3, w - 12, 1);
  ctx.fillStyle = '#958768'; ctx.fillRect(x + w * 0.35, y + h - 2, w * 0.3, 1);
  // Small blue coupling at each edge, never an ornament over the glyph band.
  for (const px of [x + 10, x + w - 10]) {
    ctx.fillStyle = '#14395c'; ctx.fillRect(px - 4, y + h * 0.4, 8, h * 0.22);
    ctx.fillStyle = '#78b8e8'; ctx.fillRect(px - 1, y + h * 0.44, 2, h * 0.14);
  }
  ctx.restore();
}
