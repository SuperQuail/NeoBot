#!/usr/bin/env node
/**
 * 单会话批量截图：一次打开、逐图截，避免每个图重启浏览器（旧实现单图 ~3 分钟）。
 *
 *   node scripts/flow/shoot_flow.mjs                 # 全部图 -> docs/flow/shots/
 *   node scripts/flow/shoot_flow.mjs 00-overview 08-plugins --width 1680
 *   node scripts/flow/shoot_flow.mjs --expanded      # 顺带截一张全展开图
 *
 * 流程：起一次 view_flow.py -> 一个 agent-browser 会话 -> 每张图 open + 就绪判定 + --full 截图。
 * 就绪判定用 **.mermaid-rendered 计数 >= 1 且 .mermaid-error 计数 == 0**（不依赖页面文字）。
 */

import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SESSION = 'flow-shoot';
let seq = 0;
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'neobot-shoot-'));

function findRepoRoot(start) {
  let current = path.resolve(start);
  for (;;) {
    if (fs.existsSync(path.join(current, 'pyproject.toml'))) return current;
    const parent = path.dirname(current);
    if (parent === current) throw new Error('找不到仓库根');
    current = parent;
  }
}

function parseArgs(argv) {
  const options = { stems: [], out: 'docs/flow/shots', width: 1680, expanded: false, port: 0 };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--out') options.out = argv[++i];
    else if (arg === '--width') options.width = Math.trunc(Number(argv[++i]) || 1680);
    else if (arg === '--port') options.port = Math.trunc(Number(argv[++i]) || 0);
    else if (arg === '--expanded') options.expanded = true;
    else if (arg.startsWith('--')) throw new Error('未知参数：' + arg);
    else options.stems.push(arg);
  }
  return options;
}

function quote(value) {
  const text = String(value);
  return /[\s"]/.test(text) ? '"' + text.replace(/"/g, '\\"') + '"' : text;
}

/** 通过临时 .cmd 执行：Node 的 shell:true 会给命令名再包一层引号，cmd 会报「找不到路径」。 */
function run(command, args, { timeoutMs = 60000 } = {}) {
  let result;
  if (process.platform === 'win32') {
    const file = path.join(TMP, 'c' + (seq += 1) + '.cmd');
    fs.writeFileSync(file, '@echo off\r\n' + command + ' ' + args.map(quote).join(' ') + '\r\n', 'utf8');
    result = spawnSync('cmd.exe', ['/d', '/c', file], { encoding: 'utf8', timeout: timeoutMs });
  } else {
    result = spawnSync(command, args, { encoding: 'utf8', timeout: timeoutMs });
  }
  return {
    status: result.status,
    stdout: (result.stdout || '').trim(),
    stderr: (result.stderr || '').trim(),
    error: result.error ? String(result.error.message) : '',
  };
}

function ab(args, opts) {
  return run('agent-browser', ['--session', SESSION, ...args], opts);
}

/** --json 包装：真实值在 data.value。 */
function jsonValue(text) {
  try {
    const payload = JSON.parse(text);
    const inner = payload && payload.data && typeof payload.data === 'object' ? payload.data : payload;
    if (inner && typeof inner === 'object' && 'value' in inner) return String(inner.value ?? '');
  } catch {
    /* 非 JSON 原样返回 */
  }
  return text;
}

function countOf(selector) {
  const out = ab(['get', 'count', selector, '--json'], { timeoutMs: 20000 });
  const value = Number(jsonValue(out.stdout));
  return Number.isFinite(value) ? value : 0;
}

function dataMermaid() {
  const out = ab(['get', 'attr', 'body', 'data-mermaid', '--json'], { timeoutMs: 20000 });
  return jsonValue(out.stdout).trim();
}

/** 就绪判定与 screenshot_flow.mjs 保持同一口径：body[data-mermaid] === 'ready'。 */
function waitReady(timeoutMs = 60000) {
  const deadline = Date.now() + timeoutMs;
  let last = '(空)';
  while (Date.now() < deadline) {
    const value = dataMermaid();
    if (value === 'ready') return { ok: true, detail: 'data-mermaid=ready' };
    if (value === 'error') {
      const text = ab(['get', 'text', '.mermaid-error'], { timeoutMs: 20000 });
      return { ok: false, detail: 'mermaid 渲染失败：' + jsonValue(text.stdout).slice(0, 300) };
    }
    if (value === 'missing') return { ok: false, detail: 'mermaid 运行时未加载（vendor 缺失？）' };
    last = value || '(空)';
    run(process.platform === 'win32' ? 'cmd.exe' : 'sleep',
        process.platform === 'win32' ? ['/d', '/c', 'ping -n 1 -w 300 127.0.0.1 >NUL'] : ['0.3'],
        { timeoutMs: 5000 });
  }
  return { ok: false, detail: '超时（最后 data-mermaid=' + last + '）' };
}

function pngSize(file) {
  const buffer = fs.readFileSync(file);
  return buffer.length < 24 ? null : { width: buffer.readUInt32BE(16), height: buffer.readUInt32BE(20) };
}

async function waitServer(url, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 2000);
    try {
      const response = await fetch(url, { signal: controller.signal });
      clearTimeout(timer);
      // 必须读完 body 再返回：留一个未消费的响应流，会在进程退出时触发
      // undici 的 assert(!this.paused) 崩溃（已踩过）。
      await response.arrayBuffer();
      if (response.ok) return true;
    } catch {
      clearTimeout(timer);
    }
    await new Promise((r) => setTimeout(r, 250));
  }
  return false;
}

function listStems(root) {
  return fs
    .readdirSync(path.join(root, 'docs', 'flow'))
    .filter((name) => /^\d{2}[a-z]?-.+\.md$/.test(name))
    .map((name) => name.replace(/\.md$/, ''))
    .sort();
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const root = findRepoRoot(HERE);
  const outDir = path.isAbsolute(options.out) ? options.out : path.join(root, options.out);
  const stems = options.stems.length ? options.stems : listStems(root);
  fs.mkdirSync(outDir, { recursive: true });

  const port = options.port || 8800 + Math.floor(Math.random() * 150);
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
  if (!(await waitServer(base + '/'))) throw new Error('viewer 启动失败：' + base);

  ab(['set', 'viewport', String(options.width), '1200']);
  const shots = [];
  try {
    for (const stem of stems) {
      // 每张图都先截「收起态」（/view 纯文档渲染），再按需截「展开态」
      // （/shot?expand=1 在服务端就把所有 <details> 标成 open）。
      // 两态写不同文件名，避免互相覆盖 —— 早期版本用同一个目标名，后跑的会把前一张盖掉。
      const states = options.expanded
        ? [
            { suffix: '', url: '/view/' + encodeURIComponent(stem) + '?bare=1' },
            { suffix: '.expanded', url: '/shot/' + encodeURIComponent(stem) + '?expand=1' },
          ]
        : [{ suffix: '', url: '/view/' + encodeURIComponent(stem) + '?bare=1' }];
      for (const state of states) {
        const opened = ab(['open', base + state.url], { timeoutMs: 60000 });
        if (opened.status !== 0) throw new Error(stem + ' 打开失败：' + (opened.stderr || opened.error));
        const ready = waitReady();
        if (!ready.ok) throw new Error(stem + ' 渲染未就绪（' + ready.detail + '）');
        const target = path.join(outDir, stem + state.suffix + '.png');
        const temp = path.join(TMP, 's' + (seq += 1) + '.png');
        const shot = ab(['screenshot', '--full', temp], { timeoutMs: 90000 });
        if (!fs.existsSync(temp)) {
          throw new Error(stem + ' 截图未落地：' + (shot.stderr || shot.error));
        }
        fs.copyFileSync(temp, target);
        const size = pngSize(target);
        shots.push({ stem: stem + state.suffix, size });
        console.log('[shoot] ' + stem + state.suffix + ' -> ' + size.width + 'x' + size.height);
      }
    }
  } finally {
    ab(['close'], { timeoutMs: 20000 });
    viewer.kill();
    try {
      fs.rmSync(TMP, { recursive: true, force: true });
    } catch {
      /* 临时目录清不掉不影响结果 */
    }
  }
  console.log('[shoot] 完成 ' + shots.length + ' 张 -> ' + path.relative(root, outDir));
}

main()
  .then(() => process.exit(0)) // agent-browser 子进程可能留下句柄，显式退出
  .catch((error) => {
    console.error('[shoot] ' + error.message);
    process.exit(1);
  });
