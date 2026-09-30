
const fs = require('fs');
const path = require('path');
function walk(dir, out) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === '__pycache__') continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(full, out);
    else if (entry.name.endsWith('.py')) out.push(full);
  }
  return out;
}
function lines(file) { return fs.readFileSync(file, 'utf8').split(/\r?\n/).length - 1; }
const modules = {};
const appDirs = fs.readdirSync('app/src/neobot_app', { withFileTypes: true })
  .filter(e => e.isDirectory() && e.name !== '__pycache__').map(e => e.name);
for (const name of appDirs) {
  const files = walk(path.join('app/src/neobot_app', name), []);
  modules['app/' + name] = [files.length, files.reduce((a, f) => a + lines(f), 0)];
}
const rootFiles = fs.readdirSync('app/src/neobot_app', { withFileTypes: true })
  .filter(e => e.isFile() && e.name.endsWith('.py')).map(e => path.join('app/src/neobot_app', e.name));
modules['app/(root)'] = [rootFiles.length, rootFiles.reduce((a, f) => a + lines(f), 0)];
for (const pkg of fs.readdirSync('packages', { withFileTypes: true }).filter(e => e.isDirectory()).map(e => e.name)) {
  const src = path.join('packages', pkg, 'src');
  if (!fs.existsSync(src)) continue;
  const files = walk(src, []);
  modules['pkg/' + pkg] = [files.length, files.reduce((a, f) => a + lines(f), 0)];
}
const rows = Object.entries(modules).sort((a, b) => b[1][1] - a[1][1]);
console.log('module, files, lines');
for (const [name, [files, count]] of rows) console.log(name.padEnd(26), String(files).padStart(3), String(count).padStart(7));
const all = walk('app/src', []).concat(...fs.readdirSync('packages').filter(p => p !== 'node_modules').map(p => {
  const src = path.join('packages', p, 'src');
  return fs.existsSync(src) ? walk(src, []) : [];
}));
const top = all.map(f => [f, lines(f)]).sort((a, b) => b[1] - a[1]).slice(0, 22);
console.log('\nTOP FILES');
for (const [f, n] of top) console.log(String(n).padStart(6), f);
