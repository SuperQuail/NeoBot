/** Four original-inspired unit silhouettes: scale and assembly contracts. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
import ts from 'typescript';
import * as THREE from 'three';
const require=createRequire(import.meta.url),cache=new Map();
function load(file){file=path.resolve(file);if(cache.has(file))return cache.get(file).exports;
 const module={exports:{}};cache.set(file,module);
 const code=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
 new Function('require','module','exports',code)(id=>id.startsWith('.')?load(path.resolve(path.dirname(file),id+'.ts')):require(id),module,module.exports);return module.exports;}
const context=new Proxy({}, {get:(_o,key)=>key==='measureText'?text=>({width:text.length*14}):key.startsWith('create')?()=>({addColorStop(){}}):()=>{}});
globalThis.document={createElement:()=>({width:0,height:0,getContext:()=>context})};
const root=path.resolve(import.meta.dirname,'../src');
const {createShipMaterials}=load(path.join(root,'world/materials.ts'));
const {buildStalker,buildDragoon}=load(path.join(root,'world/protoss-walkers.ts'));
const {buildImmortal,buildColossus}=load(path.join(root,'world/protoss-heavy.ts'));
const materials=createShipMaterials();const report=[];
for(const [kind,build,minHeight,maxHeight,maxFootprint] of [
 ['stalker',buildStalker,4.5,6.5,8],['dragoon',buildDragoon,4,6.3,9],
 ['immortal',buildImmortal,5.7,8.1,9.5],['colossus',buildColossus,20,27,14.8],
]) {
 const unit=build(materials);assert(unit.isGroup);assert.equal(unit.userData.unitKind,kind);
 const bounds=new THREE.Box3().setFromObject(unit),size=bounds.getSize(new THREE.Vector3());
 assert(Math.abs(bounds.min.y)<.12,kind+' feet stay on the assembly floor');
 assert(size.y>=minHeight&&size.y<=maxHeight,kind+' recognizable height contract');
 assert(size.x<=maxFootprint&&size.z<=maxFootprint,kind+' fits its assembly platform');
 let triangles=0,meshes=0,footRadius=0;
 unit.updateMatrixWorld(true);
 unit.traverse(o=>{if(!o.geometry)return;meshes++;const p=o.geometry.attributes.position;
   assert([...p.array].every(Number.isFinite));triangles+=(o.geometry.index?.count??p.count)/3;
   for(let i=0;i<p.count;i++){const point=new THREE.Vector3().fromBufferAttribute(p,i).applyMatrix4(o.matrixWorld);if(point.y<.2)footRadius=Math.max(footRadius,Math.hypot(point.x,point.z));}
 });
 const plinth={stalker:5.3,dragoon:5.7,immortal:5.7,colossus:7.4}[kind];
 assert(footRadius<=plinth,kind+' feet fit the actual circular assembly plinth');
 assert(meshes<=24,kind+' uses static geometry batching');
 report.push({kind,size:size.toArray().map(n=>Number(n.toFixed(2))),meshes,triangles});
}
assert(report[3].size[1]>report[2].size[1]*2.5,'Colossus towers over Immortal rather than reusing a resized generic model');
console.log('PASS: distinct Protoss units, grounded feet, platform fit and finite batched geometry');
console.log(JSON.stringify(report,null,2));
