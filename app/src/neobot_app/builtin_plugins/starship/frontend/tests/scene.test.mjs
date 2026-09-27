/** CPU-only geometry, walkability and persistence regression tests; no WebGL needed. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import ts from 'typescript';
import * as THREE from 'three';
const require = createRequire(import.meta.url);
const root = path.resolve(import.meta.dirname, '../src');
const cache = new Map();
function load(file) {
  file = path.resolve(file);
  if (cache.has(file)) return cache.get(file).exports;
  const module = { exports: {} }; cache.set(file, module);
  const code = ts.transpileModule(fs.readFileSync(file, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  new Function('require', 'module', 'exports', code)(id => id.startsWith('.')
    ? load(path.resolve(path.dirname(file), id + '.ts')) : require(id), module, module.exports);
  return module.exports;
}
const context = new Proxy({}, { get: (_o, key) => key === 'measureText' ? text => ({ width: text.length * 14 }) : () => {} });
globalThis.document = { createElement: () => ({ width: 0, height: 0, getContext: () => context }) };
const storage = new Map();
globalThis.localStorage = { getItem: k => storage.get(k) ?? null, setItem: (k,v) => storage.set(k,v) };
const { CollisionWorld, moveWithCollision, PLAYER_HEIGHT } = load(path.join(root, 'core/collision.ts'));
const { buildShip, roomAt } = load(path.join(root, 'world/ship.ts'));
const { decorateShip } = load(path.join(root, 'world/props.ts'));
const scene = new THREE.Scene(), collision = new CollisionWorld();
const ship = buildShip(scene, collision);
const foundry=decorateShip(scene, collision, ship.materials, ship.rooms);
ship.group.add(foundry);
const unitKinds=new Set();foundry.traverse(o=>{if(o.userData.unitKind)unitKinds.add(o.userData.unitKind)});
assert.deepEqual([...unitKinds].sort(),['colossus','dragoon','immortal','stalker'],'four actual Protoss units are integrated, not only exported');
assert.equal(ship.anchors.size, 12);
const shield=ship.group.getObjectByName('bridge-psionic-shield');
assert(shield,'the bridge has actual visible shield geometry');
const panes=[];shield.traverse(o=>{if(o.userData.psionicPane)panes.push(o)});
assert.equal(panes.length,1,'front, sides and roof form one continuous curved canopy');
const canopyBounds=new THREE.Box3().setFromObject(panes[0]);
assert(canopyBounds.min.z<-51&&canopyBounds.max.x>33&&canopyBounds.max.y>22,'ellipsoidal canopy wraps the full bridge, not rectangular panes');
assert([...panes[0].geometry.attributes.normal.array].every(Number.isFinite),'rounded canopy normals are finite');
assert(panes[0].material.fragmentShader.includes('clamp(vUv, vec2(0.0), vec2(1.0))'),'subpixel MSAA UVs cannot overflow the shield edge exponential');
assert(panes[0].material.fragmentShader.includes('clamp(abs(dot('),'grazing-angle roundoff cannot produce a negative fractional-power base');
for(const pane of panes){assert(pane.material.transparent&&!pane.material.depthWrite);assert(pane.material.uniforms.uStrength.value>.5);}
const shieldClock=panes[0].material.uniforms.uTime;
const before=shieldClock.value;ship.group.userData.update(.016);assert(shieldClock.value>before);
const after=shieldClock.value;ship.group.userData.update(NaN);assert.equal(shieldClock.value,after,'invalid dt never poisons GPU uniforms');
// Exterior cavity clones and a later global finish must compose exactly once.
const {applyAlloyFinish}=load(path.join(root,'world/materials.ts'));
ship.group.getObjectByName('ark-exterior-normalized').traverse(o=>{
 if(!o.isMesh||!o.material?.isMeshStandardMaterial)return;
 applyAlloyFinish(o.material,{relief:0});
 const shader={uniforms:{},vertexShader:THREE.ShaderLib.standard.vertexShader,fragmentShader:THREE.ShaderLib.standard.fragmentShader};
 o.material.onBeforeCompile(shader,{});
 assert.equal(shader.vertexShader.split('varying vec3 vArkAlloyPosition;').length-1,1,'no duplicate alloy varying');
 assert.equal(shader.fragmentShader.split('uniform vec4 arkAlloy;').length-1,1,'no duplicate alloy functions');
 assert(shader.fragmentShader.includes('vHabitatWorld.x'),'local hull cavity is retained');
});

assert.equal(roomAt(ship.rooms, ship.spawn).id, 'bridge');
const actualSize=ship.hullBounds.getSize(new THREE.Vector3());
assert(Math.abs(actualSize.z-74400)<.01,'physical hull length is 74.4 km, not just a label');
assert(Math.abs(actualSize.x-17204)<.01,'schematic width is respected');
assert(Math.abs(actualSize.y-9139)<.01,'schematic height is respected');
assert.deepEqual(ship.ladders, []);
let meshes=0, triangles=0;
ship.group.traverse(o => {
  if (!o.geometry) return;
  meshes++;
  const pos=o.geometry.getAttribute('position');
  assert(pos && [...pos.array].every(Number.isFinite), 'all vertices are finite');
  triangles += (o.geometry.index?.count ?? pos.count)/3;
});
// Traverse the full axial connection, not teleporting between disconnected rooms.
let p = new THREE.Vector3(0, .0001, -7);
function advance(delta,steps){for(let i=0;i<steps;i++){ship.group.userData.update(1/60,p);p=moveWithCollision(collision,p,PLAYER_HEIGHT,delta).position;}}
advance(new THREE.Vector3(0,-.01,.1),925);
assert(p.z>84,'bridge and rear sliding doors connect continuously to the reactor: '+JSON.stringify(p.toArray()));
advance(new THREE.Vector3(.1,-.01,0),90);
assert(p.x>8,'reactor ring walkway is accessible');
// The real aft curved buttress occupies x9 beyond z111; follow the central return aisle.
advance(new THREE.Vector3(0,-.01,.1),235);
advance(new THREE.Vector3(-.1,-.01,0),90);
advance(new THREE.Vector3(0,-.01,.1),200);
assert(p.z>115&&p.z<118,'new aft boundary blocks after, not before, the expanded rooms: '+JSON.stringify(p.toArray()));
p.set(9,.001,86);advance(new THREE.Vector3(.1,-.01,0),250);
assert(p.x>30,'reactor and archive connect through both doors');
assert.equal(roomAt(ship.rooms,p)?.id,'archive');
for(const [x,z] of [[-7,18],[7,18],[0,-8]]) {
  const r=moveWithCollision(collision,new THREE.Vector3(x,.08,z),PLAYER_HEIGHT,new THREE.Vector3(0,-.15,0));
  assert(r.grounded && r.position.y>=-.001 && r.position.y<.08,'safe transit lands on the actual thin deck plates');
  assert(!collision.intersectsPlayer(r.position.clone().add(new THREE.Vector3(0,.002,0)),PLAYER_HEIGHT),'arrival is not inside any precise solid');
  assert(collision.intersectsPlayer(r.position.clone().add(new THREE.Vector3(0,-.005,0)),PLAYER_HEIGHT),'arrival has a physical supporting surface');
}
// Every console is approachable from the front without wall/prop intersections.
for(const anchor of ship.anchors.values()) {
  const front=new THREE.Vector3(0,0,2.9).applyAxisAngle(new THREE.Vector3(0,1,0),anchor.yaw).add(anchor.position);
  front.y=.16;
  const landing=moveWithCollision(collision,front,PLAYER_HEIGHT,new THREE.Vector3(0,-.4,0));
  assert(landing.grounded&&landing.position.y<.2,anchor.spec.id+' approach has a walkable floor');
  assert(!collision.intersectsPlayer(landing.position.clone().add(new THREE.Vector3(0,.002,0)),PLAYER_HEIGHT),anchor.spec.id+' approach must clear real meshes, not just boxes');
}
const { loadShipName, saveShipName } = load(path.join(root, 'config.ts'));
assert.equal(saveShipName('  星海方舟  '),'星海方舟');
assert.equal(loadShipName(),'星海方舟');
assert.throws(()=>saveShipName('  '));
assert.equal(saveShipName('🚀'.repeat(24)),'🚀'.repeat(24));
assert.throws(()=>saveShipName('🚀'.repeat(25)));
globalThis.localStorage={getItem(){throw Error('blocked')},setItem(){throw Error('blocked')}};
assert.equal(saveShipName('离线方舟'),'离线方舟');
assert.equal(loadShipName(),'离线方舟');
const registry=load(path.join(root,'world/registry.ts'));
assert.equal(registry.availableVessels().length,1);
assert.throws(()=>registry.vesselDefinition('terran-battlecruiser'));
assert.throws(()=>registry.registerVessel(registry.vesselDefinition(registry.DEFAULT_VESSEL)));
ship.setName('<星海 & 方舟>');
ship.dispose();
assert(!scene.children.includes(ship.group));
console.log(JSON.stringify({result:'PASS',stations:ship.anchors.size,meshes,triangles,collisionBoxes:collision.boxes.length,checks:['geometry','continuous traversal','sealed gate','safe transit','console approach','unicode name','storage fallback','dispose']},null,2));
