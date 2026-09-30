#!/usr/bin/env node
/**
 * 逐块渲染校验：把每张图里的**每个** mermaid 块都渲染一遍，报出语法错误的块与行。
 *
 *   node scripts/flow/verify_flow_render.mjs                 # 全部图
 *   node scripts/flow/verify_flow_render.mjs 05b-provider-native-vision
 *
 * 为什么需要它：F3 只做结构与规模检查，看不到 mermaid 的语法错误（例如节点文本里
 * 出现未加引号的括号/分号，会导致 Parse error），而截图脚本遇到第一个错误就退出。
 * 这里用页面内的 mermaid.render 逐块渲染，一次跑完并给出准确位置。
 */

import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
let seq = 0;
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'neobot-verify-'));
const SESSION = 'flow-verify';

function findRepoRoot(start) {
  let current = path.resolve(start);
  for (;;) {
    if (fs.existsSync(path.join(current, 'pyproject.toml'))) return current;
    const parent = path.dirname(current);
    if (parent === current) throw new Error('找不到仓库根');
    current = parent;
  }
}

function quote(value) {
  const text = String(value);
  return /[\s"]/.test(text) ? '"' + text.replace(/"/g, '\\"') + '"' : text;
}

function run(command, args, { timeoutMs = 60000 } = {}) {
  let result;
  if (process.platform === 'win32') {
    const file = path.join(TMP, 'c' + (seq += 1) + '.cmd');
    fs.writeFileSync(file, '@echo off\r\n' + command + ' ' + args.map(quote).join(' ') + '\r\n', 'utf8');
    result = spawnSync('cmd.exe', ['/d', '/c', file], { encoding: 'utf8', timeout: timeoutMs });
  } else {
    result = spawnSync(command, args, { encoding: 'utf8', timeout: timeoutMs });
  }
  return { status: result.status, stdout: (result.stdout || '').trim(), stderr: (result.stderr || '').trim() };
}

function ab(args, opts) {
  return run('agent-browser', ['--session', SESSION, ...args], opts);
}

function jsonValue(text) {
  try {
    const payload = JSON.parse(text);
    const inner = payload && payload.data && typeof payload.data === 'object' ? payload.data : payload;
    if (inner && typeof inner === 'object' && 'value' in inner) return inner.value;
  } catch {
    /* 非 JSON 原样返回 */
  }
  return text;
}

/** 抽取 markdown 里的 mermaid 块（含起始行号，便于定位）。 */
function extractBlocks(markdown) {
  const lines = markdown.split(/\r?\n/);
  const blocks = [];
  let index = 0;
  while (index < lines.length) {
    if (!/^\s*\x60\x60\x60\s*mermaid\s*$/i.test(lines[index])) {
      index += 1;
      continue;
    }
    const startLine = index + 1;
    const body = [];
    index += 1;
    while (index < lines.length && !/^\s*\x60\x60\x60\s*$/.test(lines[index])) {
      body.push(lines[index]);
      index += 1;
    }
    index += 1;
    blocks.push({ startLine, code: body.join('\n') });
  }
  return blocks;
}

function listStems(root) {
  return fs
    .readdirSync(path.join(root, 'docs', 'flow'))
    .filter((name) => /^\d{2}[a-z]?-.+\.md$/.test(name))
    .map((name) => name.replace(/\.md$/, ''))
    .sort();
}

async function waitServer(url, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 2000);
    try {
      const response = await fetch(url, { signal: controller.signal });
      clearTimeout(timer);
      await response.arrayBuffer();
      if (response.ok) return true;
    } catch {
      clearTimeout(timer);
    }
    await new Promise((r) => setTimeout(r, 250));
  }
  return false;
}

async function main() {
  const args = process.argv.slice(2).filter((a) => !a.startsWith('--'));
  const root = findRepoRoot(HERE);
  const stems = args.length ? args : listStems(root);
  const port = 8850 + Math.floor(Math.random() * 100);
  const python = fs.existsSync(path.join(root, '.venv', 'Scripts', 'python.exe'))
    ? path.join(root, '.venv', 'Scripts', 'python.exe')
    : 'python';
  const viewer = spawn(python, ['scripts/flow/view_flow.py', '--port', String(port), '--no-open'], {
    cwd: root,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  viewer.stdout.on('data', () => {});
  viewer.stderr.on('data', (chunk) => process.stderr.write('[viewer] ' + chunk));
  const base = 'http://127.0.0.1:' + port;
  if (!(await waitServer(base + '/'))) throw new Error('viewer 启动失败');

  // 首页不加载 mermaid 运行时；用任意一张 view 页把 window.mermaid 带进来
  const anchor = listStems(root)[0];
  ab(['open', base + '/view/' + encodeURIComponent(anchor) + '?bare=1'], { timeoutMs: 45000 });
  const probe = ab(['eval', '-b', Buffer.from('typeof window.mermaid', 'utf8').toString('base64'), '--json'], {
    timeoutMs: 20000,
  });
  if (String(jsonValue(probe.stdout)).includes('undefined')) {
    throw new Error('页面里没有 mermaid 运行时（vendor 缺失？）');
  }
  let failures = 0;
  let checked = 0;
  try {
    for (const stem of stems) {
      const markdown = fs.readFileSync(path.join(root, 'docs', 'flow', stem + '.md'), 'utf8');
      const blocks = extractBlocks(markdown);
      for (let i = 0; i < blocks.length; i += 1) {
        const block = blocks[i];
        const payload = JSON.stringify(block.code);
        // 用页面里的 mermaid 直接渲染：返回 {ok:true} 或 {ok:false,error}
        const script =
          '(async () => { try { await window.mermaid.parse(' + payload + '); return "OK"; }' +
          ' catch (e) { return "ERR:" + (e && e.message ? e.message : String(e)).replace(/\\n/g, " | "); } })()';
        // 用 base64 传脚本，避免引号层数问题（agent-browser eval -b <base64>）
        const encoded = Buffer.from(script, 'utf8').toString('base64');
        const result = ab(['eval', '-b', encoded, '--json'], { timeoutMs: 30000 });
        checked += 1;
        const value = String(jsonValue(result.stdout) ?? '');
        if (value.includes('ERR:')) {
          failures += 1;
          console.log('[verify] ' + stem + ' 第 ' + (i + 1) + ' 块（md 第 ' + block.startLine + ' 行起）渲染失败：');
          console.log('         ' + value.replace(/^ERR:/, '').slice(0, 400));
        }
      }
    }
  } finally {
    ab(['close'], { timeoutMs: 20000 });
    viewer.kill();
    try {
      fs.rmSync(TMP, { recursive: true, force: true });
    } catch {
      /* 忽略 */
    }
  }
  console.log('[verify] 检查 ' + checked + ' 个 mermaid 块，失败 ' + failures + ' 个');
  return failures;
}

main()
  .then((failures) => process.exit(failures ? 1 : 0))
  .catch((error) => {
    console.error('[verify] ' + error.message);
    process.exit(1);
  });
