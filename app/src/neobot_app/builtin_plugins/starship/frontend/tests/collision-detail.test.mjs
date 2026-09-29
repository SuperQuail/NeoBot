/** CPU-only detailed collision contracts. Run: node tests/collision-detail.test.mjs */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import ts from 'typescript';
import * as THREE from 'three';
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';
const require = createRequire(import.meta.url), cache = new Map();
const root = path.resolve(import.meta.dirname, '../src');
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
const { CollisionWorld, moveWithCollision: move, PLAYER_HEIGHT: H, PLAYER_RADIUS: R, PLAYER_CROUCH_HEIGHT: CH } = load(path.join(root, 'core/collision.ts'));
const v = (x=0,y=0,z=0) => new THREE.Vector3(x,y,z);
const near = (actual, expected, label) => assert(Math.abs(actual-expected)<.002, label+': '+actual+' vs '+expected);
function floor(world) { world.addFromCenter(v(0,-.1,0),v(100,.2,100),'floor'); }
function mesh(world, geometry, position=v(), rotation=v(), owner='fixture') {
  const object=new THREE.Mesh(geometry,new THREE.MeshBasicMaterial());
  object.position.copy(position); object.rotation.set(rotation.x,rotation.y,rotation.z);
  world.addStaticMesh(object,{tag:'detail-fixture',owner}); return object;
}
// A circle's diagonal corners stay empty; radius is not shrunk to make passages work.
{
  const w=new CollisionWorld();floor(w);
  w.addCylinder(v(0,1,0),1.45,2,{tag:'console-pedestal',owner:'console'});
  assert(!w.intersectsPlayer(v(1.4,0,1.4),H),'round corner is genuinely empty');
  const free=move(w,v(1.4,.001,1.6),H,v(0,-.01,-.2));
  near(free.position.z,1.4,'walk beside circle corner');
  const hit=move(w,v(0,.001,3),H,v(0,-.01,-5));
  near(hit.position.z,1.45+R,'pedestal solid at actual radius');assert(hit.collidedZ);
}
// The side of a rotated narrow support is traversable inside its large world AABB.
{
  const w=new CollisionWorld();floor(w);
  w.addOBB(v(0,1.5,0),v(.2,3,4),Math.PI/4,{tag:'rotated-support'});
  assert(!w.intersectsPlayer(v(1,0,-1),H),'OBB empty side remains open');
  const free=move(w,v(.8,.001,-1),H,v(.2,-.01,0));near(free.position.x,1,'rotated support side');
  const hit=move(w,v(-2,.001,0),H,v(4,-.01,0));assert(hit.collidedX&&hit.position.x<-.5);
  assert(!w.segmentBlocked(v(1,1,-1),v(1.1,1,-1)));
  assert(w.segmentBlocked(v(-2,1,0),v(2,1,0)));
}
// True sloping mesh, not a horizontal OBB/AABB enclosing all of a bent arm.
{
  const w=new CollisionWorld();floor(w);
  mesh(w,new THREE.BoxGeometry(.24,5,.24),v(0,2.6,0),v(0,0,Math.PI/4));
  assert(!w.intersectsPlayer(v(-1.4,0,0),H),'air below elevated diagonal arm is walkable');
  const hit=move(w,v(3,.001,0),H,v(-4,-.01,0));assert(hit.collidedX,'low end cannot be penetrated');
  const ceiling=new CollisionWorld();floor(ceiling);
  mesh(ceiling,new THREE.BoxGeometry(4,.12,4),v(0,2.3,0));
  const up=move(ceiling,v(0,.001,0),H,v(0,2,0));assert(up.hitCeiling);near(up.position.y,2.24-H,'physical head clearance');
}
// Four separate feet/legs and a high abdomen must not fill the central corridor.
{
  const w=new CollisionWorld();floor(w);
  const model=new THREE.Group();
  for(const x of [-1.5,1.5])for(const z of [-1.5,1.5]) {
    const foot=new THREE.Mesh(new THREE.BoxGeometry(.7,.6,1),new THREE.MeshBasicMaterial());foot.position.set(x,.3,z);model.add(foot);
    const leg=new THREE.Mesh(new THREE.BoxGeometry(.22,4,.22),foot.material);leg.position.set(x,2.6,z);model.add(leg);
  }
  const belly=new THREE.Mesh(new THREE.BoxGeometry(3,.8,3),new THREE.MeshBasicMaterial());belly.position.y=4.6;model.add(belly);
  w.addStaticMesh(model,{tag:'quadruped',owner:'four-leg-fixture'});
  const passage=move(w,v(0,.601,-3),H,v(0,0,6));near(passage.position.z,3,'leg gap corridor');
  const footHit=move(w,v(1.5,.001,-3),H,v(0,-.01,2));assert(footHit.collidedZ&&footHit.position.z<-2.4,'feet are not ghosted or auto-stepped over');
  const highHit=move(w,v(1.5,3,-3),H,v(0,0,2));assert(highHit.collidedZ,'high leg is solid above former 2.75m cutoff');
  const bellyHit=move(w,v(0,1,0),H,v(0,3,0));assert(bellyHit.hitCeiling);near(bellyHit.position.y,4.2-H,'abdomen underside');
}
// Jump onto circular and mesh plinths; never land on a phantom square corner.
for(const kind of ['cylinder','mesh']) {
  const w=new CollisionWorld();floor(w);
  if(kind==='cylinder')w.addCylinder(v(0,.35,0),2,.7,{tag:'plinth'});
  else mesh(w,new THREE.CylinderGeometry(2,2,.7,64),v(0,.35,0));
  const land=move(w,v(0,3,0),H,v(0,-8,0));assert(land.grounded);near(land.position.y,.7,kind+' landing');
  const corner=move(w,v(2.3,3,2.3),H,v(0,-8,0));near(corner.position.y,0,kind+' corner lands on floor');
  let p=v(0,.001,3),vy=8.4,landed=false;
  for(let i=0;i<70;i++) {vy-=26/60;const r=move(w,p,H,v(0,vy/60,i<28?-.06:0));p=r.position;if(r.grounded&&i>10){landed=true;break;}}
  assert(landed,kind+' simulated jump settles');near(p.y,.7,kind+' jump reaches top');
}
// Live Box3 references: open, close, and sight-line changes require no index rebuild.
{
  const w=new CollisionWorld();floor(w);
  const door=new THREE.Box3(v(-1.5,0,-.08),v(1.5,3,.08));w.addBox(door);
  assert.equal(w.boxes[1],door);
  const run=()=>move(w,v(0,.001,-2),H,v(0,-.01,4));
  assert(run().collidedZ);assert(w.segmentBlocked(v(0,1,-2),v(0,1,2)));
  door.translate(v(4,0,0));near(run().position.z,2,'door translated open');
  assert(!w.segmentBlocked(v(0,1,-2),v(0,1,2)));
  door.translate(v(-4,0,0));assert(run().collidedZ);
  assert.equal(w.query({min:v(-.2,.1,-.2),max:v(.2,2,.2)}).length,1);
}
// Straight-wall, crouch-height, thin panel, ground and step regression.
{
  const w=new CollisionWorld();floor(w);w.addFromCenter(v(0,2,0),v(.1,4,8),'wall');
  const hit=move(w,v(-3,.001,0),H,v(12,-.01,1));near(hit.position.x,-.05-R,'thin straight wall');near(hit.position.z,1,'wall sliding');assert(hit.grounded);
  const low=new CollisionWorld();floor(low);mesh(low,new THREE.BoxGeometry(4,.12,4),v(0,1.4,0));
  assert(low.intersectsPlayer(v(0,0,0),H));assert(!low.intersectsPlayer(v(0,0,0),CH));
  const step=new CollisionWorld();floor(step);step.addFromCenter(v(0,.2,0),v(2,.4,2));
  const climb=move(step,v(-1.6,.001,0),H,v(.4,-.01,0));near(climb.position.x,-1.2,'step does not double horizontal delta');near(climb.position.y,.4,'step actually raises feet');
  step.addFromCenter(v(0,2.02,0),v(4,.1,4));
  assert(move(step,v(-1.6,.001,0),H,v(.4,-.01,0)).collidedX,'no step through low ceiling');
}
// Nested world transforms, transparent projection exclusion, double-sided panel and cleanup.
{
  const w=new CollisionWorld(),parent=new THREE.Group(),root=new THREE.Group();
  parent.position.set(10,0,5);parent.rotation.y=Math.PI/2;parent.add(root);root.position.z=2;
  const solid=new THREE.Mesh(new THREE.PlaneGeometry(2,3),new THREE.MeshBasicMaterial());solid.position.y=1.5;solid.userData.solidConsole=true;root.add(solid);
  const projection=new THREE.Mesh(new THREE.BoxGeometry(10,10,10),new THREE.MeshBasicMaterial({transparent:true}));root.add(projection);
  const handles=w.addStaticMesh(root,{owner:'console',tag:'console-panel'});assert.equal(handles.length,1);
  assert(w.segmentBlocked(v(10,1,5),v(14,1,5)),'matrixWorld panel');
  assert(!w.segmentBlocked(v(10,1,5),v(14,1,5),'console'),'candidate owner can be ignored');
  assert(move(w,v(10,0,5),H,v(4,0,0)).collidedX);assert(move(w,v(14,0,5),H,v(-4,0,0)).collidedX);
  w.removeShape(handles[0]);assert.equal(w.shapes.length,0);assert(!w.segmentBlocked(v(10,1,5),v(14,1,5)));
  w.addStaticMesh(root,'explicit-glass',{filter:m=>m.userData.solidConsole===true});assert.equal(w.shapes.length,1);
  w.clearStatic();assert.equal(w.shapes.length,0);
  assert.throws(()=>w.addStaticMesh(root,{maxTriangles:1}),/budget/);
}
// Safe-arrival occupancy: wholly enclosed avatars need not touch any triangle.
{
  for(const [name,geometry] of [['box',new THREE.BoxGeometry(10,10,10)],['sphere',new THREE.SphereGeometry(5,40,24)]]) {
    const w=new CollisionWorld();mesh(w,geometry,v(0,2,0));
    assert(w.intersectsPlayer(v(0,0,0),H),name+' fully contained standing avatar is occupied');
    assert(w.intersectsPlayer(v(0,0,0),CH),name+' fully contained crouched avatar is occupied');
    assert(!w.intersectsPlayer(v(7,0,0),H),name+' exterior remains empty');
    const shape=w.shapes[0],topology=shape.containmentCache;
    assert(topology,'closed-component topology is cached on the owning shape');
    assert(w.intersectsPlayer(v(.1,.1,.1),H));assert.equal(shape.containmentCache,topology,'repeat query reuses topology');
    w.clearStatic();assert(!w.intersectsPlayer(v(0,0,0),H),'clearing registration clears occupancy');
  }
  const grazing=new CollisionWorld();mesh(grazing,new THREE.BoxGeometry(10,10,10));
  assert(grazing.intersectsPlayer(v(0,3.145-H/2,4.035),H),'ray through a box vertex retries without missing a contained avatar');
  const surfaceOnly=new CollisionWorld();surfaceOnly.addStaticGeometry(new THREE.BoxGeometry(10,10,10),new THREE.Matrix4(),{containment:'surface'});
  assert(!surfaceOnly.intersectsPlayer(v(0,0,0),H),'explicit surface-only registration does not invent an interior');
  const reversed=geometry=>{
    const flat=geometry.toNonIndexed(),p=flat.getAttribute('position');
    for(let i=0;i<p.count;i+=3)for(let k=0;k<3;k++){
      const tmp=p.array[(i+1)*3+k];p.array[(i+1)*3+k]=p.array[(i+2)*3+k];p.array[(i+2)*3+k]=tmp;
    }
    return flat;
  };
  for(const invertSecond of [false,true]) {
    const w=new CollisionWorld();
    const a=new THREE.BoxGeometry(8,8,8).toNonIndexed().translate(-.7,1.5,-.3);
    const b0=new THREE.BoxGeometry(9,9,9),b=(invertSecond?reversed(b0):b0.toNonIndexed()).translate(.8,2,.4);
    mesh(w,mergeGeometries([a,b]));
    assert(w.intersectsPlayer(v(0,0,0),H),'overlapping merged solids do not parity-cancel'+(invertSecond?' even with opposite winding':''));
  }
  // Closed hollow cage built from real walls: each escape ray hits geometry,
  // yet the avatar in the central air pocket must not be considered inside it.
  const shell=[];
  for(const axis of ['x','y','z'])for(const side of [-1,1]){
    const size=v(10,10,10);size[axis]=1;
    const geometry=new THREE.BoxGeometry(size.x,size.y,size.z).toNonIndexed();
    const offset=v();offset[axis]=side*4.5;geometry.translate(offset.x,offset.y,offset.z);shell.push(geometry);
  }
  const hollow=new CollisionWorld();mesh(hollow,mergeGeometries(shell));
  assert(!hollow.intersectsPlayer(v(0,0,0),H),'hollow closed wall assembly does not fill its air pocket');
  assert(hollow.intersectsPlayer(v(4.5,0,0),H),'hollow assembly walls remain solid');
  const torus=new CollisionWorld();mesh(torus,new THREE.TorusGeometry(3,.8,20,48).rotateX(Math.PI/2),v(0,.9,0));
  assert(!torus.intersectsPlayer(v(0,0,0),H),'connected torus hole remains empty');
  // Disconnected oriented inner/outer surfaces are an explicit winding volume.
  const nested=mergeGeometries([new THREE.BoxGeometry(10,10,10).toNonIndexed(),reversed(new THREE.BoxGeometry(7,7,7))]);
  const cavity=new CollisionWorld();cavity.addStaticGeometry(nested,new THREE.Matrix4(),{containment:'winding',tag:'hollow-shell'});
  assert(!cavity.intersectsPlayer(v(0,0,0),H),'oppositely wound inner shell preserves enclosed cavity');
  assert(cavity.intersectsPlayer(v(4.2,0,0),H),'material between nested shells is occupied');
  const legs=new CollisionWorld();
  const pieces=[];
  for(const x of [-2,2])for(const z of [-2,2])pieces.push(new THREE.BoxGeometry(.5,5,.5).toNonIndexed().translate(x,2.5,z));
  pieces.push(new THREE.BoxGeometry(5,1,5).toNonIndexed().translate(0,5,0));
  mesh(legs,mergeGeometries(pieces));
  assert(!legs.intersectsPlayer(v(0,0,0),H),'one merged four-leg model does not fill leg gaps');
  const sheet=new CollisionWorld();mesh(sheet,new THREE.PlaneGeometry(10,10).rotateX(Math.PI/4),v(0,3,0));
  assert(!sheet.intersectsPlayer(v(0,0,0),H),'open slanted sheet does not invent a closed half-space');
}
// Dense triangle budget: querying local support must not visit the whole model.
{
  const w=new CollisionWorld();
  mesh(w,new THREE.PlaneGeometry(100,100,220,220).rotateX(-Math.PI/2));
  const landed=move(w,v(.2,2,.2),H,v(0,-3,0));assert(landed.grounded);near(landed.position.y,0,'dense mesh landing');
  assert(w.stats.triangleTests<1200,'BVH narrow-phase triangle budget: '+w.stats.triangleTests);
  console.log('Dense mesh:',w.shapes[0].triangleCount,'triangles;',w.stats.triangleTests,'triangle tests per landing');
  w.clear();assert.equal(w.boxes.length+w.shapes.length,0);
}
// Actual foundry integration, not just synthetic legs. The renderer's material
// batches are collision snapshots, retaining all four models' physical triangles.
{
  const context=new Proxy({}, {get:(_o,key)=>key==='measureText'?text=>({width:text.length*14}):key.startsWith('create')?()=>({addColorStop(){}}):()=>{}});
  globalThis.document={createElement:()=>({width:0,height:0,getContext:()=>context})};
  const {createShipMaterials}=load(path.join(root,'world/materials.ts'));
  const {buildFoundry}=load(path.join(root,'world/foundry.ts'));
  const w=new CollisionWorld();floor(w);
  const foundry=buildFoundry(w,createShipMaterials(),[{id:'war-forge'},{id:'robot-forge'}]);
  assert(!w.boxes.some(b=>b.tag==='protoss-unit-support'||b.tag==='foundry-platform'),'old raster strips are removed, not layered under precise colliders');
  const report=[];
  for(const [kind,x,z] of [['stalker',-21,46],['immortal',-21,29],['dragoon',21,29],['colossus',21,46]]) {
    const unit=foundry.getObjectByName('foundry-'+kind);
    const shapes=w.shapes.filter(s=>s.metadata.owner===unit.name);
    assert(shapes.length>=4&&shapes.every(s=>s.kind==='mesh'&&s.metadata.tag==='protoss-unit-support'));
    assert(unit.userData.supportCollisionTriangles>50000,kind+' uses real full-height geometry');
    // Isolate each unit from its surrounding gantries, clamps and inscription.
    const units=new CollisionWorld();units.shapes.push(...shapes);
    assert(!units.intersectsPlayer(v(x,.661,z),H),kind+' actual belly/leg air stays unoccupied for safe arrival');
    // Immortal's real low forward apron blocks the front at standing height;
    // its unobstructed passage runs between the left/right leg pairs instead.
    const gap=kind==='immortal' ? move(units,v(x-4,.661,z),H,v(8,0,0)) : move(units,v(x,.661,z-4),H,v(0,0,8));
    const gapTriangleTests=units.stats.triangleTests;
    near(kind==='immortal'?gap.position.x:gap.position.z,kind==='immortal'?x+4:z+4,kind+' actual central leg gap');
    if(kind==='immortal') assert(move(units,v(x,.661,z-4),H,v(0,0,8)).collidedZ,'actual low apron is not removed to open a route');
    const feet=[];
    for(const s of shapes)for(let i=0;i<s.vertices.length;i+=3)if(s.vertices[i+1]<.81)feet.push(v(s.vertices[i],s.vertices[i+1],s.vertices[i+2]));
    assert(feet.length>0,kind+' has physical ground contact');
    const point=feet.reduce((a,b)=>b.x>a.x?b:a);
    const footHit=move(units,v(point.x+1,.67,point.z),H,v(-2,0,0));assert(footHit.collidedX,kind+' actual foot cannot be crossed');
    const centerJump=move(units,v(x,.661,z),H,v(0,30,0));assert(centerJump.hitCeiling,kind+' actual abdomen blocks upward jump');
    const highLeg=shapes.some(s=>s.bounds.max.y>4);assert(highLeg,kind+' collision is not cut at 2.75m');
    report.push({kind,triangles:unit.userData.supportCollisionTriangles,gapTriangleTests});
  }
  // Real oval bench rounded corners are empty despite lying inside its AABB.
  assert(!w.intersectsPlayer(v(30.3,.01,39),H),'oval parts table corner has no false AABB blocker');
  assert(w.intersectsPlayer(v(28.5,.01,37.5),H),'oval parts table pedestal/worktop remain solid');
  const bayLand=move(w,v(-21,1,43.5),H,v(0,-2,0));assert(bayLand.grounded);near(bayLand.position.y,.6,'actual layered plinth inner surface');
  let position=v(21,.6001,44),maxTriangleTests=0;
  const timings=[];
  for(let i=0;i<400;i++) {
    const started=performance.now();
    const r=move(w,position,H,v(0,-.008,i<200?.02:-.02));position=r.position;
    timings.push(performance.now()-started);maxTriangleTests=Math.max(maxTriangleTests,w.stats.triangleTests);
    assert(r.grounded,'walking stays grounded on real Colossus platform');
  }
  near(position.z,44,'actual platform passage supports return trip');
  assert(maxTriangleTests<3000,'per-frame actual foundry narrow phase budget: '+maxTriangleTests);
  timings.sort((a,b)=>a-b);
  console.log('Actual foundry:',JSON.stringify({shapes:w.shapes.length,units:report,maxTriangleTests,frameP95ms:Number(timings[380].toFixed(3))}));
}
console.log('PASS: round corners, OBB sides, sloping arms, actual four-unit gaps/feet/abdomen, jumps/landings, dynamic doors, walls, clearance, LOS and BVH budgets');
