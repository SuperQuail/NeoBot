/** Real focus camera + whole-label routing/frustum/occlusion tests, not center-only rays. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import ts from 'typescript';
import * as THREE from 'three';
const require = createRequire(import.meta.url), cache = new Map();
const root = path.resolve(import.meta.dirname, '../src');
function load(file) {
  file = path.resolve(file); if (cache.has(file)) return cache.get(file).exports;
  const mod = { exports: {} }; cache.set(file, mod);
  const code = ts.transpileModule(fs.readFileSync(file, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  new Function('require', 'module', 'exports', code)(id => id.startsWith('.') ? load(path.resolve(path.dirname(file), id + '.ts')) : require(id), mod, mod.exports);
  return mod.exports;
}
const context = new Proxy({}, { get: (o, k) => k in o ? o[k] : k === 'measureText' ? s => ({ width: s.length * 22 }) : k === 'createLinearGradient' ? () => ({ addColorStop() {} }) : () => {} });
globalThis.document = { createElement: () => ({ width: 0, height: 0, getContext: () => context }) };
globalThis.window = { location: { pathname: '/game/', href: 'http://localhost/game/', origin: 'http://localhost' } };
const { Terminal } = load(path.join(root, 'ui/terminal.ts'));
const { ShellState } = load(path.join(root, 'state.ts'));
const { terminalLayout } = load(path.join(root, 'ui/terminal-layout.ts'));
const physicalIds = ['navigation', 'dashboard', 'system', 'usage', 'bots', 'plugins'];
const fallbackIds = ['config', 'logs', 'analysis', 'turret', 'repair', 'scores'];
let routed = 0, sampled = 0;
function visible(object) { for (let o = object; o; o = o.parent) if (!o.visible) return false; return true; }
function points(mesh, xs = [-0.49, -0.3, 0, 0.3, 0.49], ys = [-0.48, 0, 0.48]) {
  const { width, height } = mesh.geometry.parameters;
  return xs.flatMap(x => ys.map(y => mesh.localToWorld(new THREE.Vector3(x * width, y * height, 0))));
}
const summaries = [];
for (const aspect of [16 / 9, 16 / 10, 21 / 9]) for (const id of [...physicalIds, ...fallbackIds]) {
  const scene = new THREE.Scene(), camera = new THREE.PerspectiveCamera(54, aspect, 0.1, 1000);
  let reads = 0, writes = 0, canvasActions = 0;
  const host = { scene, camera, materials: {}, shell: new ShellState(), quality: {}, input: { pointer: { down: false } },
    actions: { warping: () => false, systemName: () => '天鹅座 λ-4', triggerWarp() {} },
    consoleApi: { get: async () => { reads++; return { ok: true, data: [], status: 200 }; }, post: async () => { writes++; throw Error('writes forbidden'); } },
    toast() {}, confirm: async () => false };
  const definition = { id, title: id, subtitle: 'test', accent: 0x388fea, create: () => ({ draw(ui) { if (ui.button('edge-action', { x: 30, y: 110, w: 320, h: 50 }, '文字边缘操作')) canvasActions++; } }) };
  const terminal = new Terminal(definition, host, { position: new THREE.Vector3(12, 0, -9), yaw: 0.63 });
  // Offline focus is inspectable but doesn't poll or accept input.
  terminal.setAvailability({ available: false, reason: '只读观察', hint: '', readOnly: true }); terminal.focus();
  assert(terminal.focused); assert.equal(reads, 0);
  terminal.blur(); terminal.setAvailability({ available: true, reason: '', hint: '', readOnly: false });
  // Avoid timers while retaining the real focused-state drawing/routing.
  if (terminal.physical) terminal.physical.pollers.length = 0;
  terminal.focus(); terminal.update(0.016);
  const view = terminal.focusView(); camera.position.copy(view.position); camera.lookAt(view.target); camera.updateMatrixWorld(true);
  scene.updateMatrixWorld(true);
  const visibleMeshes = []; terminal.group.traverse(o => { if (o.isMesh && visible(o)) visibleMeshes.push(o); });
  const solids = terminal.solidMeshes();
  assert(solids.length > 0, id + ' missing solid collision geometry');
  for (const mesh of solids) {
    assert(visible(mesh)); assert(mesh.material.isMeshStandardMaterial && !mesh.material.transparent);
    assert.notEqual(mesh, terminal.screen.mesh);
    assert(!mesh.userData.readout && mesh.userData.physicalAction === undefined, 'text/projection cannot become an invisible collision slab');
  }
  // Footprint is local to the station, independent of anchor yaw/translation.
  const inverse = terminal.group.matrixWorld.clone().invert(), footprint = new THREE.Box3();
  for (const mesh of visibleMeshes) {
    const pos = mesh.geometry.getAttribute('position');
    for (let i = 0; i < pos.count; i++) footprint.expandByPoint(new THREE.Vector3().fromBufferAttribute(pos, i).applyMatrix4(mesh.matrixWorld).applyMatrix4(inverse));
  }
  assert(footprint.max.x <= 1.45 && footprint.min.x >= -1.45 && footprint.max.z <= 1.45 && footprint.min.z >= -1.45, id + ' exceeds narrow footprint ' + JSON.stringify(footprint));
  const targets = terminal.physical ? [...terminal.physical.targets, ...terminal.physical.operatingSurface.children.filter(m => m.userData.readout)] : [terminal.screen.mesh];
  for (const mesh of targets) {
    if (terminal.physical) {
      assert(mesh.material.depthWrite, 'focused text must occlude rear transparent ornaments');
      assert.equal(mesh.material.opacity, 1, 'focused glyphs must not blend with scene');
      assert(mesh.material.map.image.width >= 2048, 'wide readouts require adequate horizontal texture density');
    }
    const normal = new THREE.Vector3(0, 0, 1).transformDirection(mesh.matrixWorld);
    assert(normal.dot(camera.position.clone().sub(mesh.getWorldPosition(new THREE.Vector3())).normalize()) > 0.72, id + ' oblique text');
    const fontSize = mesh.userData.readout ? 32 : 44;
    const glyph = [new THREE.Vector3(0, -mesh.geometry.parameters.height * fontSize / 256, 0), new THREE.Vector3(0, mesh.geometry.parameters.height * fontSize / 256, 0)].map(p => mesh.localToWorld(p).project(camera));
    if (terminal.physical) assert(Math.abs(glyph[1].y - glyph[0].y) * 720 / 2 >= (mesh.userData.readout ? 15 : 20), id + ' glyph too small at 720p');
    for (const point of points(mesh)) {
      const ndc = point.clone().project(camera); sampled++;
      assert(Math.abs(ndc.x) < 0.99 && Math.abs(ndc.y) < 0.99 && ndc.z > -1 && ndc.z < 1, id + ' clipped label edge');
      const ray = new THREE.Raycaster(camera.position, point.clone().sub(camera.position).normalize());
      const hit = ray.intersectObject(terminal.screen.mesh, false)[0];
      if (!mesh.userData.readout) {
        assert(hit, id + ' label edge misses screen.mesh dispatcher');
        if (terminal.physical) { assert.equal(hit.object.userData.physicalAction, mesh.userData.physicalAction); assert.equal(hit.uv, undefined); routed++; }
        else { assert.equal(hit.object, mesh); assert(hit.uv); }
      }
      // Check actual scene geometry too: correct invisible routing is not visual proof.
      const targetDistance = camera.position.distanceTo(point);
      const occluders = ray.intersectObjects(visibleMeshes.filter(m => m !== terminal.screen.mesh && m !== mesh), false)
        .filter(h => h.distance < targetDistance - 0.006 && h.object.material.opacity > 0.05);
      assert.equal(occluders.length, 0, id + ' content occluded by ' + occluders.map(h => h.object.name || h.object.type).join(','));
    }
  }
  if (!terminal.physical) {
    const utilityKeys = []; terminal.group.traverse(o => { if (o.userData.consoleKey) utilityKeys.push(o); });
    assert.equal(utilityKeys.length, 3);
    for (const key of utilityKeys) assert(key.getObjectByName('utility-key-glyph'), 'utility keys need visible meaning, not blank blocks');
    const corners = points(terminal.screen.mesh, [-0.5, 0.5], [-0.5, 0.5]).map(p => p.project(camera));
    const width = (Math.max(...corners.map(p => p.x)) - Math.min(...corners.map(p => p.x))) / 2;
    const height = (Math.max(...corners.map(p => p.y)) - Math.min(...corners.map(p => p.y))) / 2;
    assert(width >= 0.6 && height >= 0.5, id + ' too small: ' + width + ' x ' + height);
    summaries.push({ id, aspect: +aspect.toFixed(2), width: +width.toFixed(2), height: +height.toFixed(2) });
    // A screen-mesh ray near both ends of an actual drawn label must dispatch the same button.
    for (const x of [32, 348]) {
      const point = terminal.screen.mesh.localToWorld(new THREE.Vector3((x / 1024 - 0.5) * terminal.screen.width, (0.5 - 135 / 576) * terminal.screen.height, 0));
      const hit = new THREE.Raycaster(camera.position, point.sub(camera.position).normalize()).intersectObject(terminal.screen.mesh, false)[0];
      terminal.handlePointer(hit, true, 0); terminal.update(0.016);
    }
    assert.equal(canvasActions, 2, id + ' UV edge routing does not activate button exactly once per click');
    terminal.update(0.016); assert.equal(canvasActions, 2, 'click cannot replay in next frame');
    // Minigame override consumes the same UV route without the legacy controller firing.
    let overrideClicks = 0;
    terminal.setOverride(ui => { if (ui.button('override', { x: 30, y: 110, w: 320, h: 50 }, '演练操作')) overrideClicks++; });
    terminal.update(0.016);
    const point = terminal.screen.mesh.localToWorld(new THREE.Vector3((32 / 1024 - 0.5) * terminal.screen.width, (0.5 - 135 / 576) * terminal.screen.height, 0));
    terminal.handlePointer(new THREE.Raycaster(camera.position, point.sub(camera.position).normalize()).intersectObject(terminal.screen.mesh, false)[0], true, 0);
    terminal.update(0.016); assert.equal(overrideClicks, 1); assert.equal(canvasActions, 2);
  }
  assert.equal(writes, 0); terminal.dispose();
}
assert.equal(new Set(physicalIds.map(id => terminalLayout(id).kind)).size, 6);
console.log(JSON.stringify({ result: 'PASS', sampled, noUvEdgeRoutes: routed, screens: summaries }, null, 2));
