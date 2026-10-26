"""卡片公共样式（主题变量 + 组件；全部用 var(--x, fallback) 保持可缺失）。"""

from __future__ import annotations

_COMMON_CSS = """\
/* ── 缺省视觉变量（主题 :root 优先级更高，缺键时用这里的兜底） ── */
:where(:root) {
  --card-pad: 22px 24px 18px;
  --card-shadow: 0 12px 32px rgba(0, 0, 0, 0.35);
  --card-border-width: 1px;
  --card-font-size: 15px;
  --font-smoothing: antialiased;
  --line: 1.6;
  --block-gap: 14px;
  --panel-bg: rgba(255, 255, 255, 0.035);
  --panel-border: var(--card-border);
  --panel-radius: 12px;
  --panel-pad: 13px 15px;
  --panel-shadow: none;
  --tile-bg: rgba(255, 255, 255, 0.05);
  --tile-radius: 10px;
  --grid-gap: 12px;
  --hairline: var(--card-border);
  --zebra: rgba(255, 255, 255, 0.025);
  --table-head-bg: rgba(255, 255, 255, 0.04);
  --table-font-size: 13.5px;
  --cell-pad: 6px 10px;
  --kv-label-width: 38%;
  --title-font: var(--card-font);
  --title-size: 22px;
  --title-weight: 700;
  --title-tracking: 0.01em;
  --title-color: var(--card-fg);
  --title-shadow: none;
  --head-rule: linear-gradient(90deg, var(--accent), rgba(0, 0, 0, 0));
  --head-rule-width: 80px;
  --heading-size: 15px;
  --heading-color: var(--accent);
  --heading-tracking: 0.05em;
  --subheading-color: var(--card-muted);
  --accent-soft: rgba(127, 127, 127, 0.16);
  --danger: #f85149;
  --danger-soft: rgba(248, 81, 73, 0.13);
  --danger-border: rgba(248, 81, 73, 0.55);
  --ok: #3fb950;
  --ok-soft: rgba(63, 185, 80, 0.13);
  --warn: #d29922;
  --warn-soft: rgba(210, 153, 34, 0.14);
  --muted-soft: rgba(139, 148, 158, 0.14);
  --stat-label-size: 11px;
  --stat-value-size: 16px;
  --emblem-size: 34px;
  --emblem-opacity: 0.95;
  --muted-size: 12px;
  --card-bg-position: 0 0;
  --card-bg-size: auto;
  --card-bg-repeat: repeat;
  --card-bg-opacity: 1;
  --pager-bg: rgba(255, 255, 255, 0.05);
  --pager-border: var(--card-border);
  --note-bg: rgba(127, 127, 127, 0.12);
  --note-bar: var(--accent);
  --cell-line-gap: 2px;
}

/* ── 卡片外壳 ── */
* { box-sizing: border-box; }
html, body {
  margin: 0;
  padding: 0;
  background: var(--card-bg);
  color: var(--card-fg);
  font-family: var(--card-font);
  font-size: var(--card-font-size);
  line-height: var(--line);
  -webkit-font-smoothing: var(--font-smoothing);
}
.card {
  position: relative;
  isolation: isolate;
  overflow: hidden;
  padding: var(--card-pad);
  border: var(--card-border-width) solid var(--card-border);
  border-radius: var(--radius);
  background: var(--card-bg);
  box-shadow: var(--card-shadow);
  color: var(--card-fg);
  font-family: var(--card-font);
  font-size: var(--card-font-size);
}
.card-veil {
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  background-image: var(--card-bg-image, none);
  background-size: var(--card-bg-size);
  background-repeat: var(--card-bg-repeat);
  background-position: var(--card-bg-position);
  opacity: var(--card-bg-opacity);
}
.nb-decor {
  position: absolute;
  inset: 0;
  z-index: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}
.card > .card-head, .card > .card-body, .card > .card-footer {
  position: relative;
  z-index: 1;
}

/* ── 标题区 ── */
.card-head {
  position: relative;
  display: flex;
  align-items: center;
  gap: 14px;
  padding-bottom: 13px;
  border-bottom: 1px solid var(--hairline);
  margin-bottom: 15px;
}
.card-head::after {
  content: "";
  position: absolute;
  left: 0;
  bottom: -1px;
  width: var(--head-rule-width);
  height: 2px;
  border-radius: 2px;
  background: var(--head-rule);
}
.card-head-main { flex: 1 1 auto; min-width: 0; }
.card-title {
  margin: 0;
  font-family: var(--title-font);
  font-size: var(--title-size);
  font-weight: var(--title-weight);
  letter-spacing: var(--title-tracking);
  line-height: 1.25;
  color: var(--title-color);
  text-shadow: var(--title-shadow);
}
.card-subtitle {
  margin-top: 6px;
  font-size: 12.5px;
  letter-spacing: 0.02em;
  color: var(--card-muted);
}
.card-emblem {
  flex: 0 0 auto;
  width: var(--emblem-size);
  height: var(--emblem-size);
  opacity: var(--emblem-opacity);
  color: var(--accent);
  display: flex;
  align-items: center;
  justify-content: center;
}
.card-emblem svg { display: block; width: 100%; height: 100%; }

/* ── 内容区与分区 ── */
.card-body { display: block; }
.block { position: relative; margin: 0 0 var(--block-gap); }
.block:last-child { margin-bottom: 0; }
.block--kv, .block--rows {
  padding: var(--panel-pad);
  border: 1px solid var(--panel-border);
  border-radius: var(--panel-radius);
  background: var(--panel-bg);
  box-shadow: var(--panel-shadow);
}
.block--heading, .block--stats, .block--note, .block--grid { padding: 0; border: 0; background: none; box-shadow: none; }
.block--heading { margin-bottom: 9px; }
.block--heading:not(:first-child) { margin-top: 6px; }
.block--slot, .block--marker { padding: 0; border: 0; background: none; box-shadow: none; }
.card-slot:empty { display: none; }

.block-heading {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: var(--heading-size);
  font-weight: 700;
  letter-spacing: var(--heading-tracking);
  color: var(--heading-color);
}
.block-heading::before {
  content: "";
  flex: 0 0 auto;
  width: 4px;
  height: 0.98em;
  border-radius: 2px;
  background: var(--heading-color);
}
.block-subheading {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0 0 8px;
  font-size: 12.5px;
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--subheading-color);
}
.block-subheading::before {
  content: "";
  flex: 0 0 auto;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: currentColor;
  opacity: 0.85;
}

/* ── 告警 / 状态色调 ── */
.tone-danger { --panel-border: var(--danger-border); --panel-bg: var(--danger-soft); --heading-color: var(--danger); --subheading-color: var(--danger); --note-bar: var(--danger); --note-bg: var(--danger-soft); }
.tone-warn { --panel-border: var(--warn); --panel-bg: var(--warn-soft); --heading-color: var(--warn); --subheading-color: var(--warn); --note-bar: var(--warn); --note-bg: var(--warn-soft); }
.tone-ok { --heading-color: var(--ok); --subheading-color: var(--ok); --note-bar: var(--ok); }
.tone-muted { --heading-color: var(--card-muted); --subheading-color: var(--card-muted); --note-bar: var(--card-muted); }
.tone-danger.block--kv::before, .tone-danger.block--rows::before {
  content: "";
  position: absolute;
  left: 0;
  top: 7px;
  bottom: 7px;
  width: 3px;
  border-radius: 0 3px 3px 0;
  background: var(--danger);
}
.tone-warn.block--kv::before, .tone-warn.block--rows::before {
  content: "";
  position: absolute;
  left: 0;
  top: 7px;
  bottom: 7px;
  width: 3px;
  border-radius: 0 3px 3px 0;
  background: var(--warn);
}

/* ── 键值表 ── */
table.kv, table.rows {
  width: 100%;
  border-collapse: collapse;
  border-spacing: 0;
  font-size: var(--table-font-size);
}
.kv th, .kv td { padding: var(--cell-pad); text-align: left; vertical-align: top; border-bottom: 1px solid var(--hairline); }
.kv tr:last-child th, .kv tr:last-child td { border-bottom: 0; }
.kv th { width: var(--kv-label-width); font-weight: 500; color: var(--card-muted); letter-spacing: 0.01em; }
.grid .kv th { width: var(--grid-kv-label-width, 46%); }
.kv td { font-variant-numeric: tabular-nums; font-weight: 550; }

/* ── 数据表（表头 + 斑马纹） ── */
.rows thead th {
  padding: var(--cell-pad);
  text-align: left;
  font-size: 11.5px;
  font-weight: 600;
  letter-spacing: 0.10em;
  color: var(--card-muted);
  background: var(--table-head-bg);
  border-bottom: 1px solid var(--hairline);
}
.rows thead th:first-child { border-top-left-radius: 6px; }
.rows thead th:last-child { border-top-right-radius: 6px; }
.rows tbody td { padding: var(--cell-pad); text-align: left; vertical-align: top; border-bottom: 1px solid var(--hairline); }
.rows tbody tr:last-child td { border-bottom: 0; }
.rows tbody tr:nth-child(odd) { background: var(--zebra); }
.rows--commands { table-layout: fixed; font-size: 13px; }
.rows--commands thead th, .rows--commands tbody td { padding: 4px 10px; line-height: 1.45; }
.rows--commands tbody td:first-child { color: var(--card-fg); font-weight: 600; overflow-wrap: anywhere; }
.rows--commands tbody td:nth-child(2) { overflow-wrap: anywhere; }
.rows--commands tbody td:last-child { white-space: nowrap; font-size: 11.5px; color: var(--card-muted); }
.cell-line { display: block; }
.cell-line + .cell-line { margin-top: var(--cell-line-gap); color: var(--card-muted); }
.cell--mono { font-family: ui-monospace, "Cascadia Mono", Consolas, monospace; font-size: 0.97em; }
.cell--chip {
  display: inline-block;
  padding: 1px 9px;
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 0.92em;
}
.cell--ok { color: var(--ok); font-weight: 650; }
.cell--warn { color: var(--warn); font-weight: 650; }
.cell--danger { color: var(--danger); font-weight: 650; }
.cell--muted { color: var(--card-muted); }
.cell--accent { color: var(--accent); font-weight: 650; }

/* ── 指标卡片（stats） ── */
.stats { display: grid; grid-template-columns: repeat(var(--stat-cols, 3), minmax(0, 1fr)); gap: 9px; }
.stat {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
  padding: 9px 11px;
  border: 1px solid var(--panel-border);
  border-radius: var(--tile-radius);
  background: var(--tile-bg);
}
.stat-label { font-size: var(--stat-label-size); letter-spacing: 0.08em; color: var(--card-muted); }
.stat-value {
  font-size: var(--stat-value-size);
  font-weight: 650;
  font-variant-numeric: tabular-nums;
  overflow-wrap: anywhere;
}
.stat--ok .stat-value { color: var(--ok); }
.stat--warn .stat-value { color: var(--warn); }
.stat--danger .stat-value { color: var(--danger); }
.stat--accent .stat-value { color: var(--accent); }
.stat--muted .stat-value { color: var(--card-muted); }

/* ── 栅格分组（grid） ── */
.grid { display: grid; grid-template-columns: repeat(var(--grid-cols, 2), minmax(0, 1fr)); gap: var(--grid-gap); align-items: start; }
.grid-cell { min-width: 0; }
.grid .block { margin-bottom: 0; }

/* ── 提示条 ── */
.note {
  display: block;
  padding: 11px 14px;
  border-left: 3px solid var(--note-bar);
  border-radius: 8px;
  background: var(--note-bg);
  color: var(--card-fg);
}

/* ── 页码条 ── */
.card-pager {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
  padding: 7px 13px;
  border: 1px solid var(--pager-border);
  border-radius: 999px;
  background: var(--pager-bg);
  font-size: var(--muted-size);
  color: var(--card-muted);
}
.pager-page { font-weight: 700; letter-spacing: 0.04em; color: var(--accent); }
.pager-sep { opacity: 0.45; }
.pager-dots { display: flex; align-items: center; gap: 4px; margin-left: auto; }
.pager-dot { width: 6px; height: 6px; border-radius: 999px; background: var(--card-muted); opacity: 0.35; }
.pager-dot.is-current { width: 16px; border-radius: 999px; background: var(--accent); opacity: 1; }

/* ── 空态与页脚 ── */
.empty, td.empty { color: var(--card-muted); }
td.empty { text-align: center; padding: 14px 8px; }
.block--empty .empty { display: block; text-align: center; padding: 12px 0; }
.card-footer {
  display: flex;
  align-items: center;
  gap: 9px;
  margin-top: 15px;
  padding-top: 11px;
  border-top: 1px solid var(--hairline);
  font-size: var(--muted-size);
  letter-spacing: 0.03em;
  color: var(--card-muted);
}
.card-footer::before {
  content: "";
  flex: 0 0 auto;
  width: 16px;
  height: 2px;
  border-radius: 2px;
  background: var(--head-rule);
}
"""
