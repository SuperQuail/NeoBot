#!/usr/bin/env node
/**
 * 流程图截图器：把 docs/flow/*.md 渲染成 PNG，供评审/交付贴图（spec(13) R4 的配套工具）。
 *
 *   node scripts/flow/screenshot_flow.mjs                          # 全部图 -> docs/flow/shots/
 *   node scripts/flow/screenshot_flow.mjs 00-overview 03-reply-pipeline
 *   node scripts/flow/screenshot_flow.mjs --width 1680 --out docs/flow/shots
 *   node scripts/flow/screenshot_flow.mjs --expanded               # 折叠的细节也展开再截一张
 *   node scripts/flow/screenshot_flow.mjs --url http://127.0.0.1:8791
 *
 * 默认截「收起态」（主流程图 + 时序图 + 折叠的细节）；--expanded 额外截「全展开态」。
 * 依赖：agent-browser（Chrome via CDP）+ scripts/flow/view_flow.py。只写 --out 目录。
 */

import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));

/**
 * 渲染就绪判定：view_flow.py 的 RUNTIME_JS 会在全部 mermaid 渲染完成后给 body 打
 * data-mermaid="ready"（失败打 "error"）。**不要**用页面文字做等待条件 ——
 * agent-browser wait 会把 CLI 的成功回显（"✓ Done"）也算成命中，导致误判。
 */
const READY_ATTR = 'data-mermaid';

function findRepoRoot(start) {
  let current = path.resolve(start);
  for (;;) {
    if (fs.existsSync(path.join(current, 'pyproject.toml'))) return current;
    const parent = path.dirname(current);
    if (parent === current) throw new Error('找不到仓库根（向上没有 pyproject.toml）');
    current = parent;
  }
}

function parseWidth(raw) {
  const value = Number(raw);
  if (!Number.isFinite(value) || value < 640 || value > 3000) {
    throw new Error('--width 需要 640..3000 的数字，收到：' + raw);
  }
  return Math.trunc(value);
}

function parseArgs(argv) {
  const options = {
    stems: [],
    out: 'docs/flow/shots',
    width: 1680,
    url: '',
    expanded: false,
    session: '',
    quiet: false,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--out') options.out = argv[++i];
    else if (arg === '--width') options.width = parseWidth(argv[++i]);
    else if (arg === '--url') options.url = argv[++i];
    else if (arg === '--expanded') options.expanded = true;
    else if (arg === '--session') options.session = argv[++i];
    else if (arg === '--quiet') options.quiet = true;
    else if (arg.startsWith('--')) throw new Error('未知参数：' + arg);
    else options.stems.push(arg);
  }
  return options;
}

function listStems(root) {
  const dir = path.join(root, 'docs', 'flow');
  return fs
    .readdirSync(dir)
    .filter((name) => name.endsWith('.md') && name !== 'README.md')
    .map((name) => name.replace(/\.md$/, ''))
    .sort();
}

/**
 * 只在必要时加引号。
 *
 * cmd.exe 有个反直觉行为：`"agent-browser" "get" "title"` 会报
 * 「系统找不到指定的路径」，而 `agent-browser get title` 正常 —— 带引号的裸命令名
 * 不再走 PATH 搜索。所以「命令名一律不加引号」，只有含空格的参数才加引号。
 */
/**
 * 独立会话参数。
 *
 * agent-browser 的默认会话是全局共享的：并发截图时别人 open 的页面会把你的页面顶掉
 * （实测截到过别人的图）。所以每张图固定用 flow-<图名> 自己的会话。
 */
function sessionArgs(session) {
  return session ? ['--session', session] : [];
}

function quoteArg(value) {
  const text = String(value);
  if (text === '' || !/[\s"]/.test(text)) return text;
  return '"' + text.replace(/"/g, '\\"') + '"';
}

let scriptSeq = 0;

const TMP_DIR = fs.mkdtempSync(path.join(os.tmpdir(), 'neobot-flow-'));

/**
 * 执行外部命令。
 *
 * Windows 坑：Node 的 shell:true 会把整条命令行再包一层引号，如果命令名本身也被引号
 * 包住就会变成 '\"agent-browser\"'，cmd.exe 直接报「系统找不到指定的路径」。所以这里
 * 改成「写一个临时 .cmd 再让 cmd.exe 执行它」—— 干净、可复现，也方便出错时回看命令。
 */
function run(command, args, { allowFailure = false } = {}) {
  let result;
  if (process.platform === 'win32') {
    const script = path.join(TMP_DIR, 'cmd-' + (scriptSeq += 1) + '.cmd');
    const lines = ['@echo off', command + ' ' + args.map(quoteArg).join(' ')];
    fs.writeFileSync(script, lines.join('\r\n') + '\r\n', 'utf8');
    result = spawnSync('cmd.exe', ['/d', '/c', script], { encoding: 'utf8' });
  } else {
    result = spawnSync(command, args, { encoding: 'utf8' });
  }
  if (result.error) throw result.error;
  if (result.status !== 0 && !allowFailure) {
    throw new Error(
      command +
        ' ' +
        args.join(' ') +
        ' 失败（exit ' +
        result.status +
        '）：' +
        (result.stderr || result.stdout || '').trim(),
    );
  }
  return {
    status: result.status,
    stdout: (result.stdout || '').trim(),
    stderr: (result.stderr || '').trim(),
  };
}

function cleanup() {
  try {
    fs.rmSync(TMP_DIR, { recursive: true, force: true });
  } catch {
    /* 临时目录清不掉不影响结果 */
  }
}

function pythonBin(root) {
  const venv = path.join(root, '.venv', 'Scripts', 'python.exe');
  if (fs.existsSync(venv)) return venv;
  const posix = path.join(root, '.venv', 'bin', 'python');
  if (fs.existsSync(posix)) return posix;
  return process.platform === 'win32' ? 'python' : 'python3';
}

function pngSize(file) {
  const buffer = fs.readFileSync(file);
  if (buffer.length < 24) return null;
  return { width: buffer.readUInt32BE(16), height: buffer.readUInt32BE(20) };
}

async function waitForServer(url, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url, { method: 'GET' });
      if (response.ok) return true;
    } catch {
      /* 还没起来 */
    }
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
  return false;
}

function capture(baseUrl, stem, target, { expanded, width, session }) {
  // agent-browser 没有 --width 参数（历史事故：1660 被当成输出路径）。
  // 视口宽度用 `set viewport <w> <h>` 设置，高度给足，再由 --full 截整页。
  run('agent-browser', [...sessionArgs(session), 'set', 'viewport', String(width), '1200']);
  const url = baseUrl + '/shot/' + encodeURIComponent(stem) + (expanded ? '?expand=1' : '');
  run('agent-browser', [...sessionArgs(session), 'open', url]);
  const ready = waitForRender(stem, session);
  if (!ready.ok) throw new Error(stem + ' 渲染未就绪（' + ready.detail + '）');
  void READY_ATTR;
  const errors = run('agent-browser', [...sessionArgs(session), 'get', 'count', '.mermaid-error'], {
    allowFailure: true,
  });
  if (errors.stdout && errors.stdout !== '0') {
    throw new Error(stem + ' 有 ' + errors.stdout + ' 个 mermaid 块渲染失败');
  }
  // 先截到固定文件名再搬走：即使 --width 被 CLI 吞掉（历史事故：参数被当成保存路径），
  // 也不会在仓库根留下莫名其妙的大文件。
  const temp = path.join(TMP_DIR, 'shot-' + (scriptSeq += 1) + '.png');
  run('agent-browser', [...sessionArgs(session), 'screenshot', '--full', temp]);
  if (!fs.existsSync(temp)) throw new Error(stem + ' 截图未落地：' + temp);
  fs.copyFileSync(temp, target);
  return pngSize(target);
}

/** 读 body 的 data-mermaid。必须带 --json，否则拿到的是 CLI 回显而不是属性值。 */
function readDataMermaid(session) {
  const result = run(
    'agent-browser',
    [...sessionArgs(session), 'get', 'attr', 'body', 'data-mermaid', '--json'],
    { allowFailure: true, timeoutMs: 20000 },
  );
  const text = result.stdout.trim();
  try {
    const payload = JSON.parse(text);
    // agent-browser --json 的返回形如：
    //   {"success":true,"data":{"origin":"…","value":"ready"},"error":null}
    const inner = payload && typeof payload === 'object' && payload.data && typeof payload.data === 'object'
      ? payload.data
      : payload;
    if (inner && typeof inner === 'object' && 'value' in inner) {
      return String(inner.value ?? '').trim();
    }
  } catch {
    /* 不是 JSON 就当地址原样用 */
  }
  return text;
}

/** 轮询页面状态：mermaid 全部渲染完成（data-mermaid=ready）才算好。 */
function waitForRender(stem, session, timeoutMs = 40000) {
  const deadline = Date.now() + timeoutMs;
  let detail = '超时';
  while (Date.now() < deadline) {
    const value = readDataMermaid(session);
    if (value === 'ready') return { ok: true, detail: value };
    if (value === 'error') {
      const text = run('agent-browser', [...sessionArgs(session), 'get', 'text', '.mermaid-error'], {
        allowFailure: true,
      });
      return { ok: false, detail: 'mermaid 渲染失败：' + text.stdout.slice(0, 300) };
    }
    detail = '当前 data-mermaid=' + JSON.stringify(value) + '（' + stem + '）';
    spawnSync(process.platform === 'win32' ? 'cmd.exe' : 'sleep', 
      process.platform === 'win32' ? ['/d', '/c', 'ping -n 1 -w 250 127.0.0.1 >NUL'] : ['0.25'],
      { encoding: 'utf8' });
  }
  return { ok: false, detail };
}

function describe(size) {
  return size ? size.width + 'x' + size.height : '尺寸未知';
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const root = findRepoRoot(HERE);
  const outDir = path.isAbsolute(options.out) ? options.out : path.join(root, options.out);
  const stems = options.stems.length ? options.stems : listStems(root);
  if (!stems.length) throw new Error('docs/flow 下没有可截图的图');

  let server = null;
  let baseUrl = options.url.replace(/\/$/, '');
  if (!baseUrl) {
    const port = 8700 + Math.floor(Math.random() * 200);
    server = spawn(pythonBin(root), ['scripts/flow/view_flow.py', '--port', String(port), '--no-open'], {
      cwd: root,
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    server.stdout.on('data', (chunk) => {
      if (!options.quiet) process.stdout.write('[viewer] ' + chunk);
    });
    server.stderr.on('data', (chunk) => process.stderr.write('[viewer] ' + chunk));
    baseUrl = 'http://127.0.0.1:' + port;
    const up = await waitForServer(baseUrl + '/');
    if (!up) throw new Error('view_flow.py 未能在 30s 内启动：' + baseUrl);
  }

  fs.mkdirSync(outDir, { recursive: true });
  const shots = [];
  try {
    for (const stem of stems) {
      const target = path.join(outDir, stem + '.png');
      const size = capture(baseUrl, stem, target, { ...options, session: options.session || 'flow-' + stem });
      shots.push({ stem, size });
      console.log('[flow-shot] ' + stem + ' -> ' + path.relative(root, target) + ' ' + describe(size));
      if (options.expanded) {
        const full = path.join(outDir, stem + '.expanded.png');
        const fullSize = capture(baseUrl, stem, full, {
          ...options,
          expanded: true,
          session: options.session || 'flow-' + stem,
        });
        shots.push({ stem: stem + '.expanded', size: fullSize });
        console.log(
          '[flow-shot] ' + stem + '.expanded -> ' + path.relative(root, full) + ' ' + describe(fullSize),
        );
      }
    }
  } finally {
    run('agent-browser', ['close'], { allowFailure: true });
    if (server) server.kill();
  }

  const tall = shots.filter((shot) => shot.size && shot.size.height > 16000);
  if (tall.length) {
    console.warn(
      '[flow-shot] 以下截图非常高，建议把细节拆得更细：' +
        tall.map((shot) => shot.stem + '(' + shot.size.height + 'px)').join('、'),
    );
  }
  console.log('[flow-shot] 完成 ' + shots.length + ' 张截图，输出目录 ' + path.relative(root, outDir));
}

main()
  .catch((error) => {
    console.error('[flow-shot] ' + error.message);
    process.exitCode = 1;
  })
  .finally(cleanup);
