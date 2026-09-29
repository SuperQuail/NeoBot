import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
import ts from 'typescript';
import * as THREE from 'three';
const require=createRequire(import.meta.url),cache=new Map();
function load(file){file=path.resolve(file);if(cache.has(file))return cache.get(file).exports;
 const mod={exports:{}};cache.set(file,mod);
 const code=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
 new Function('require','module','exports',code)(id=>id.startsWith('.')?load(path.resolve(path.dirname(file),id+'.ts')):require(id),mod,mod.exports);return mod.exports;
}
const context=new Proxy({}, {get:(_o,key)=>key==='measureText'?text=>({width:text.length*14}):()=>{}});
const nodes=[];
class Element extends EventTarget {
 constructor(tag){super();this.tagName=tag;this.value='';this.children=[];this.width=0;this.height=0;nodes.push(this);}
 setAttribute(){} append(node){this.children.push(node)} appendChild(node){this.append(node)}
 replaceChildren(...children){this.children=children} remove(){this.removed=true}
 getContext(){return context} focus(){document.activeElement=this} blur(){document.activeElement=document.body} select(){} setSelectionRange(){}
}
globalThis.document=Object.assign(new EventTarget(),{createElement:tag=>new Element(tag),body:new Element('body'),activeElement:null,pointerLockElement:null});
globalThis.window=new EventTarget();
const key=(k,extra={})=>{const e=new Event('keydown',{cancelable:true});Object.assign(e,{key:k,...extra});return e};
const root=path.resolve(import.meta.dirname,'../src');
const {TextCapture}=load(path.join(root,'ui/textinput.ts'));
const capture=new TextCapture();let committed='',canceled=0;
capture.open({initial:'星',onCommit:v=>committed=v,onCancel:()=>canceled++});
capture.element.value='星海';capture.element.dispatchEvent(new Event('input'));
capture.element.dispatchEvent(key('Enter',{isComposing:true}));assert.equal(committed,'');
capture.element.dispatchEvent(key('Enter'));assert.equal(committed,'星海');assert(!capture.isActive);
capture.open({onCommit:()=>assert.fail('escape must not commit'),onCancel:()=>canceled++});
capture.element.dispatchEvent(key('Escape'));assert.equal(canceled,1);
const {Hud}=load(path.join(root,'core/hud.ts'));
const host=new Element('div'),hud=new Hud(host),camera=new THREE.PerspectiveCamera(72,1.6,.1,2000000);
hud.attach(camera);camera.updateMatrixWorld(true);
assert.equal(host.children.length,0,'visible HUD must not contain DOM controls');
let answer=hud.confirm({title:'危险操作',danger:true});window.dispatchEvent(key('Enter'));assert.equal(await answer,false,'Enter on default cancel never confirms');
answer=hud.ask({title:'铭文',validate:v=>v.trim()?'': '不能为空'});
window.dispatchEvent(key('Enter'));assert(hud.hasModal,'invalid text keeps 3D entry open');
hud.input.value='灵能方舟';hud.input.dispatchEvent(new Event('input'));
window.dispatchEvent(key('Enter',{isComposing:true}));assert(hud.hasModal,'IME Enter does not submit');
window.dispatchEvent(key('Enter'));assert.equal(await answer,'灵能方舟');
answer=hud.menu('操作仪',[{label:'舰桥',value:'bridge'},{label:'外观',value:'exterior'}]);
hud.group.updateWorldMatrix(true,true);
const p=new THREE.Vector3();hud.switches[1].mesh.getWorldPosition(p);p.project(camera);
hud.update({x:p.x,y:p.y,clicked:true},.016);assert.equal(await answer,'exterior','actual Three raycast activates the physical button');
assert(!nodes.some(n=>['button','dialog','form'].includes(n.tagName)),'all visible interaction stays in 3D');
hud.dispose();assert(hud.input.removed);
// Actual projected business targets remain raycastable after visual redesign.
window.location = { pathname:'/game/', href:'http://localhost/game/', origin:'http://localhost' };
const {PhysicalTerminal}=load(path.join(root,'terminals/physical.ts'));
const {ShellState}=load(path.join(root,'state.ts'));
const shell=new ShellState();let destination=-1;
const hostApi={get:async()=>({ok:true,data:[],error:null,status:200}),post:async()=>assert.fail('no mutations in visual test')};
const ctx={shell,host:{consoleApi:hostApi,actions:{warping:()=>false,systemName:()=> '天鹅座 λ-4',triggerWarp:(_manual,id)=>destination=id}},redraw(){},toast(){},confirm:async()=>false};
for(const id of ['navigation','system']) {
 const physical=new PhysicalTerminal(id,ctx,0x388fea);physical.onFocus();physical.group.updateMatrixWorld(true);
 assert.equal(physical.targets.length,6);
 assert.equal(physical.targets.filter(t=>t.userData.projected).length,id==='navigation'?6:3);
 for(const target of physical.targets){
   const point=target.getWorldPosition(new THREE.Vector3());
   const origin=point.clone().add(new THREE.Vector3(0,3,4));
   const hits=new THREE.Raycaster(origin,point.clone().sub(origin).normalize()).intersectObject(target,false);
   assert(hits.length>0,'projected/tactile sigil remains an actual mesh hit target');
 }
 if(id==='navigation'){physical.activate(1);physical.activate(2);assert.equal(destination,1);physical.onBlur();physical.activate(1);assert.equal(physical.selected,1);}
 physical.dispose();physical.dispose();
}
console.log('PASS: invisible IME, safe confirmation, 3D raycast, no DOM panels, projected business sigils, warp destination, cleanup');
