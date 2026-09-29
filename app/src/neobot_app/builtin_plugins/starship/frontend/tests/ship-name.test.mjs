/** HUD naming regressions; browser acceptance remains required separately. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
import ts from 'typescript';
import * as THREE from 'three';
const require=createRequire(import.meta.url), cache=new Map();
const root=path.resolve(import.meta.dirname,'../src');
function load(file){file=path.resolve(file);if(cache.has(file))return cache.get(file).exports;
 const mod={exports:{}};cache.set(file,mod);
 const code=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
 new Function('require','module','exports',code)(id=>id.startsWith('.')?load(path.resolve(path.dirname(file),id+'.ts')):require(id),mod,mod.exports);return mod.exports;
}
const context=new Proxy({}, {get:(_o,key)=>key==='measureText'?text=>({width:text.length*14}):()=>{}});
class Element extends EventTarget {
 constructor(tag){super();this.tagName=tag.toUpperCase();this.value='';this.children=[];}
 setAttribute(){} append(node){this.children.push(node)} appendChild(node){this.append(node)}
 replaceChildren(...children){this.children=children} remove(){} getContext(){return context}
 focus(){document.activeElement=this} blur(){document.activeElement=document.body} select(){} setSelectionRange(){}
}
globalThis.document=Object.assign(new EventTarget(),{createElement:tag=>new Element(tag),body:new Element('body'),activeElement:null,pointerLockElement:null});
globalThis.window=new EventTarget();
const key=(k,extra={})=>{const e=new Event('keydown',{cancelable:true});Object.assign(e,{key:k,...extra});return e};
const storage=new Map();globalThis.localStorage={getItem:k=>storage.get(k)??null,setItem:(k,v)=>storage.set(k,v)};
const configPath=path.join(root,'config.ts');
function freshConfig(){cache.delete(configPath);return load(configPath)}
let config=freshConfig();assert.equal(config.DEFAULT_SHIP_NAME,'亚顿之矛');assert.equal(config.loadShipName(),'亚顿之矛');
storage.set('neobot-starship-ship-name','曙光之矛');config=freshConfig();assert.equal(config.loadShipName(),'亚顿之矛');
assert.equal(storage.get('neobot-starship-ship-name'),'亚顿之矛');
storage.set('neobot-starship-ship-name','自定方舟');config=freshConfig();assert.equal(config.loadShipName(),'自定方舟');
config.saveShipName('曙光之矛');config=freshConfig();assert.equal(config.loadShipName(),'曙光之矛','explicit old-default choice survives migration');
assert.equal(config.saveShipName('  星海远征舰  '),'星海远征舰');
assert.equal(config.normalizeShipName('星'.repeat(24)),'星'.repeat(24));
assert.equal(config.normalizeShipName('🚀'.repeat(24)),'🚀'.repeat(24));
for(const value of ['   ','星'.repeat(25)])assert.throws(()=>config.saveShipName(value),RangeError);
const {Hud}=load(path.join(root,'core/hud.ts'));
const hud=new Hud(new Element('div')), camera=new THREE.PerspectiveCamera(72,1.6,.1,2000000);hud.attach(camera);camera.updateMatrixWorld(true);
const ask=()=>hud.ask({title:'战舰铭文',value:config.loadShipName(),validate:v=>{try{config.normalizeShipName(v);return null}catch{return '请输入1–24个字符'}}});
assert(hud.dark.transparent,'entry field renders in the same late pass as its text');
let answer=ask();hud.input.value='  ';window.dispatchEvent(key('Enter'));assert(hud.hasModal);
hud.input.value='星'.repeat(25);window.dispatchEvent(key('Enter'));assert(hud.hasModal);
hud.input.value='重命名成功';hud.input.dispatchEvent(new Event('input'));
// Lost DOM focus must not accidentally activate the default cancel button.
hud.input.blur();window.dispatchEvent(key('Enter'));assert.equal(await answer,'重命名成功');
answer=ask();hud.input.dispatchEvent(new Event('compositionstart'));
window.dispatchEvent(key('Escape'));window.dispatchEvent(key('Enter'));assert(hud.hasModal,'IME Enter/Escape cannot settle the modal');
hud.input.dispatchEvent(new Event('compositionend'));window.dispatchEvent(key('Enter',{keyCode:229}));assert(hud.hasModal);
window.dispatchEvent(key('Escape'));assert.equal(await answer,null);
answer=ask();window.dispatchEvent(key('Tab'));window.dispatchEvent(key('Enter'));assert.equal(await answer,null,'Tab then Enter explicitly activates cancel');
answer=ask();hud.input.value='点击保存';hud.update({x:0,y:0,clicked:false},.016);
const point=hud.switches[1].hit.getWorldPosition(new THREE.Vector3()).project(camera);
hud.update({x:point.x,y:point.y,clicked:true},.016);assert.equal(await answer,'点击保存');
answer=ask();hud.input.blur();document.dispatchEvent(new Event('pointerlockchange'));assert.equal(document.activeElement,hud.input,'focus restored after async pointer unlock');
window.dispatchEvent(key('Escape'));await answer;
answer=hud.menu('14 item layout',Array.from({length:14},(_,i)=>({label:'room '+i,value:String(i)})));
const slots=hud.switches.map(s=>s.hit.parent.position);
assert.equal(new Set(slots.map(p=>p.x+','+p.y)).size,14,'expanded room menu has no overlapping slots');
assert(hud.switches.every(s=>s.mesh.material.transparent),'modal backgrounds share transparent render pass with labels, above world projections');
assert(slots.every(p=>p.y> -1.2),'expanded menu stays above footer');
window.dispatchEvent(key('Escape'));await answer;
hud.dispose();
const {TextCapture}=load(path.join(root,'ui/textinput.ts'));const capture=new TextCapture();let commit=null;
capture.open({onCommit:v=>commit=v});capture.element.dispatchEvent(new Event('compositionstart'));
capture.element.value='中文输入';capture.element.dispatchEvent(key('Enter'));assert.equal(commit,null);
capture.element.dispatchEvent(new Event('compositionend'));capture.element.dispatchEvent(key('Enter'));assert.equal(commit,'中文输入');capture.dispose();
console.log('PASS: legacy-default migration, custom preservation, Unicode bounds, Hud focus/IME/cancel/raycast/pointer-unlock, TextCapture composition');
