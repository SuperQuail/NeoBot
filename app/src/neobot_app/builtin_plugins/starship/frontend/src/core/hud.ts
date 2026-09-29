/** Diegetic instruments only: every visible label and control is a Three mesh.
 * The sole HTML control is an invisible IME receiver; there are no DOM panels. */
import * as THREE from 'three';
import { drawProtossCommand } from '../ui/protoss-command';
import { PSIONIC_INSTRUMENTS, type InstrumentTheme } from '../world/style';
export interface DialogOption { label:string; value:string; danger?:boolean; }
interface Label { mesh:THREE.Mesh; canvas:HTMLCanvasElement; texture:THREE.CanvasTexture; text:string; }
interface Switch { mesh:THREE.Mesh; hit:THREE.Mesh; idle:THREE.CanvasTexture; highlight:THREE.CanvasTexture; action:()=>void; base:number; }
export class Hud {
  readonly root:HTMLElement;
  readonly group=new THREE.Group();
  private camera:THREE.PerspectiveCamera|null=null;
  private ray=new THREE.Raycaster();
  private material=new THREE.MeshStandardMaterial({color:0xbfa063,metalness:.65,roughness:.32});
  private dark=new THREE.MeshStandardMaterial({color:0x101e31,metalness:.45,roughness:.4});
  private glow=new THREE.MeshBasicMaterial({color:0x6adcf3});
  private labels:Label[]=[];
  private switches:Switch[]=[];
  private instrument=new THREE.Group();
  private modal=new THREE.Group();
  private modalLabels:Label[]=[];
  private status:Label;
  private prompt:Label;
  private notice:Label;
  private identity:Label;
  private crosshair:THREE.Mesh;
  private input:HTMLInputElement;
  private toastUntil=0;
  private banner='';
  private modalResolve:((s:string|null)=>void)|null=null;
  private onInput:()=>void=()=>{};
  private accept:()=>void=()=>{};
  private composing=false;
  private textEntry=false;
  private entryField:THREE.Mesh|null=null;
  private selected=0;
  private active=false;
  private lastMinigame='';
  get hasModal():boolean {return this.active;}

  constructor(root:HTMLElement, private readonly theme:Readonly<InstrumentTheme> = PSIONIC_INSTRUMENTS) {
    this.material.color.setHex(theme.frame);this.dark.color.setHex(theme.body);this.glow.color.setHex(theme.energy);
    this.root=root;root.replaceChildren();
    this.group.name='three-dimensional-flight-instruments';
    this.group.renderOrder=1000;
    // Keep every HUD surface in the same late render pass as its labels; otherwise
    // transparent world projections paint over opaque command wells and entry fields.
    for(const material of [this.material,this.dark,this.glow]) {material.depthTest=false;material.depthWrite=false;material.transparent=true;}
    this.group.add(this.instrument,this.modal);this.modal.visible=false;
    // The angled lower-left wrist instrument has a real casing, rails and prism core.
    this.instrument.position.set(-1.38,-.98,-2.7);this.instrument.rotation.set(.14,.22,0);
    this.slab(this.instrument,1.34,.45,.08,0,0,0);
    this.status=this.label(this.instrument,'',1.25,.32,[0,0,.075],21);
    this.identity=this.label(this.group,'',1.3,.17,[-1.4,1.43,-2.8],25);
    this.prompt=this.label(this.group,'',1.85,.1,[0,-1.05,-3.1],18);
    this.notice=this.label(this.group,'',2.05,.12,[0,-1.3,-3.3],18);
    const gem=new THREE.Mesh(new THREE.OctahedronGeometry(.09),this.glow);gem.position.set(-.76,0,.06);this.instrument.add(gem);
    this.crosshair=new THREE.Mesh(new THREE.TorusGeometry(.009,.0018,4,16),this.glow);
    this.crosshair.position.z=-1;this.group.add(this.crosshair);
    this.input=document.createElement('input');this.input.className='text-capture';
    this.input.setAttribute('aria-label','三维控制台文字输入');this.input.autocomplete='off';
    document.body.append(this.input);
    this.input.addEventListener('input',()=>this.onInput());
    this.input.addEventListener('compositionstart',()=>this.composing=true);
    this.input.addEventListener('compositionend',()=>{this.composing=false;this.onInput();});
    window.addEventListener('keydown',this.keydown,true);
    window.addEventListener('mousedown',this.preserveEntryFocus,true);
    window.addEventListener('focus',this.restoreEntryFocus);
    document.addEventListener('pointerlockchange',this.restoreEntryFocus);
  }
  attach(camera:THREE.PerspectiveCamera):void {this.camera=camera;camera.add(this.group);}
  private slab(parent:THREE.Group,w:number,h:number,d:number,x:number,y:number,z:number):THREE.Mesh {
    // Reference command wells use rectangular silver-blue rails with short cuts.
    const shape=new THREE.Shape();const tip=Math.min(h*.12,.035);
    shape.moveTo(-w/2+tip,h/2);shape.lineTo(w/2-tip,h/2);shape.lineTo(w/2,h/2-tip);
    shape.lineTo(w/2,-h/2+tip);shape.lineTo(w/2-tip,-h/2);shape.lineTo(-w/2+tip,-h/2);
    shape.lineTo(-w/2,-h/2+tip);shape.lineTo(-w/2,h/2-tip);shape.closePath();
    const geometry=new THREE.ExtrudeGeometry(shape,{depth:d,bevelEnabled:true,bevelThickness:.018,bevelSize:.018,bevelSegments:2,steps:1});geometry.translate(0,0,-d/2);
    const mesh=new THREE.Mesh(geometry,this.dark);mesh.position.set(x,y,z);parent.add(mesh);
    const rim=new THREE.Mesh(geometry.clone(),this.material);rim.scale.set(1.08,1.22,.75);rim.position.set(x,y,z-d*.35);parent.add(rim);
    // Raised energy inlay and small angular engravings anchor the alien visual language.
    const vein=new THREE.Mesh(new THREE.BoxGeometry(w*.6,.012,.018),this.glow);vein.position.set(x,y-h*.38,z+d*.5+.008);parent.add(vein);
    for(const s of [-1,1]) {
      const rune=new THREE.Mesh(new THREE.OctahedronGeometry(Math.min(.04,h*.12)),this.material);rune.scale.set(.55,1.3,.35);rune.position.set(x+s*w*.38,y,z+d*.5+.028);parent.add(rune);
    }
    return mesh;
  }
  private label(parent:THREE.Group,text:string,w:number,h:number,p:[number,number,number],font=26,modal=false):Label {
    const canvas=document.createElement('canvas');canvas.width=1024;canvas.height=Math.max(80,Math.round(1024*h/w));
    const texture=new THREE.CanvasTexture(canvas);texture.colorSpace=THREE.SRGBColorSpace;texture.generateMipmaps=false;
    texture.minFilter=THREE.LinearFilter;
    const mesh=new THREE.Mesh(new THREE.PlaneGeometry(w,h),new THREE.MeshBasicMaterial({map:texture,transparent:true,depthTest:!modal,depthWrite:false,toneMapped:false}));mesh.position.set(...p);parent.add(mesh);
    const label={mesh,canvas,texture,text:'__initial__'};mesh.userData.font=font;
    (modal?this.modalLabels:this.labels).push(label);this.paint(label,text);return label;
  }
  private paint(label:Label,text:string):void {
    if(text===label.text)return;label.text=text;label.mesh.visible=!!text;
    const ctx=label.canvas.getContext('2d')!;const {width:w,height:h}=label.canvas;
    ctx.clearRect(0,0,w,h);ctx.fillStyle=this.theme.text;ctx.textAlign='center';ctx.textBaseline='middle';
    const lines=text.split('\n');const size=Math.min(h/(lines.length*1.35+.2),label.mesh.userData.font*4.5);
    ctx.font='500 '+size+'px "Microsoft YaHei", sans-serif';
    lines.forEach((line,i)=>ctx.fillText(line,w/2,h/2+(i-(lines.length-1)/2)*size*1.25,w-24));
    label.texture.needsUpdate=true;
  }
  setShipIdentity(name:string):void {this.paint(this.identity,'◈  '+name);this.identity.mesh.visible=false;}
  setCrosshairVisible(visible:boolean,_variant:'dot'|'pointer'='dot'):void {this.crosshair.visible=visible&&!this.active;}
  showPrompt(text:string|null,hint='E'):void {this.paint(this.prompt,text?'[ '+hint+' ]  '+text:'');}
  setStatus(lines:string[]|null):void {
    const simplified=(lines??[]).slice(0,2).map(s=>s.replace(/ · [0-9]+ FPS/,''));
    this.paint(this.status,simplified.join('\n'));
  }
  setBanner(text:string|null,_tone:'info'|'warn'='warn'):void {this.banner=text??'';if(performance.now()>this.toastUntil)this.paint(this.notice,this.banner);}
  setMinigame(info:{title:string;score:string;extra?:string;hint?:string}|null):void {
    this.lastMinigame=info?[info.title,info.score,info.extra,info.hint].filter(Boolean).join(' · '):'';
    if(this.lastMinigame)this.paint(this.notice,this.lastMinigame);
  }
  toast(message:string,_tone:'info'|'ok'|'warn'|'error'='info',ttl=3600):void {this.toastUntil=performance.now()+ttl;this.paint(this.notice,message);}

  menu(title:string,options:DialogOption[],body=''):Promise<string|null> {
    return this.open(title,body,options);
  }
  confirm(options:{title:string;body?:string;confirmLabel?:string;cancelLabel?:string;danger?:boolean}):Promise<boolean> {
    return this.open(options.title,options.body??'',[
      {label:options.cancelLabel??'取消',value:'cancel'},
      {label:options.confirmLabel??'确认',value:'ok',danger:options.danger},
    ]).then(v=>v==='ok');
  }
  ask(options:{title:string;placeholder?:string;value?:string;hint?:string;validate?:(v:string)=>string|null}):Promise<string|null> {
    const promise=this.open(options.title,options.hint??'输入文字 · Enter 确认 · Esc 取消',[
      {label:'取消',value:'cancel'},{label:'保存铭文',value:'input'},
    ],true);
    this.input.value=options.value??'';
    const field=this.slab(this.modal,2.75,.45,.13,0,.1,.12);
    field.name='engraved-text-entry';this.entryField=field;this.selected=-1;
    const text=this.label(this.modal,'',2.6,.33,[0,.1,.235],32,true);
    const feedback=this.label(this.modal,'',2.8,.2,[0,-.3,.2],24,true);
    this.onInput=()=>this.paint(text,this.input.value+' ▏');this.onInput();
    this.accept=()=>{
      if(this.composing)return;
      const error=options.validate?.(this.input.value);
      if(error){this.paint(feedback,error);this.selected=-1;this.restoreEntryFocus();return;}
      this.finish(this.input.value);
    };
    this.switches[1].action=this.accept;
    this.input.focus({preventScroll:true});this.input.select();
    return promise;
  }
  private open(title:string,body:string,options:DialogOption[],input=false):Promise<string|null> {
    this.finish(null);this.clearModal();this.active=true;this.modal.visible=true;this.group.visible=true;
    this.modal.position.set(0,0,-3.4);this.instrument.visible=false;
    this.selected=0;this.textEntry=input;this.composing=false;
    // The operation array is a projection emitted by a small ceremonial focus,
    // not a wall of large extruded website buttons.
    const focus=new THREE.Mesh(new THREE.SphereGeometry(.16,28,20),new THREE.MeshBasicMaterial({color:0x247de5,transparent:true,opacity:.32,wireframe:true}));
    focus.position.set(0,options.length>3?-.35:1.0,0);this.modal.add(focus);
    for(const radius of [.23,.29,.36]) {
      const ring=new THREE.Mesh(new THREE.TorusGeometry(radius,.006,5,72),this.glow);
      ring.position.copy(focus.position);ring.rotation.x=radius*1.6;ring.rotation.y=.3;this.modal.add(ring);
    }
    this.label(this.modal,title,2.9,.22,[0,1.14,.04],27,true);
    if(body)this.label(this.modal,body,3.05,input?.28:.18,[0,input?.72:.83,.03],18,true);
    const isArray=options.length>3;
    const rows=Math.ceil(options.length/2),spacing=Math.min(.31,1.55/Math.max(1,rows-1));
    options.forEach((option,i)=>{
      const side=isArray?(i<rows?-1:1):i===0?-1:1;
      const row=isArray?i%rows:0;
      const x=isArray?side*1.04:side*.72,y=input?-.72:isArray?.51-row*spacing:-.45;
      const socket=new THREE.Group();socket.position.set(x,y,isArray?-.08-Math.abs(row-(rows-1)/2)*.04:0);socket.rotation.y=-side*.09;this.modal.add(socket);
      const w=isArray?1.32:1.2,h=isArray?Math.min(.245,spacing*.88):.245;
      // Use the same reference-derived recessed command cell as physical terminals.
      // These remain world-space projection meshes, not HTML panels.
      const texture=(selected:boolean)=>{
        const canvas=document.createElement('canvas');canvas.width=1024;canvas.height=Math.round(1024*h/w);
        drawProtossCommand(canvas.getContext('2d')!,{x:0,y:0,w:canvas.width,h:canvas.height},{selected,danger:option.danger});
        const map=new THREE.CanvasTexture(canvas);map.colorSpace=THREE.SRGBColorSpace;
        map.generateMipmaps=false;map.minFilter=THREE.LinearFilter;return map;
      };
      const idle=texture(false),highlight=texture(true);
      const key=new THREE.Mesh(new THREE.PlaneGeometry(w,h),new THREE.MeshBasicMaterial({map:idle,transparent:true,side:THREE.DoubleSide,depthWrite:false,toneMapped:false}));socket.add(key);
      this.label(socket,option.label,w*.82,Math.min(.105,h*.55),[0,0,.03],21,true);
      if(isArray) {
        const curve=new THREE.CatmullRomCurve3([new THREE.Vector3(side*.31,-.35,-.12),new THREE.Vector3(side*.46,y,-.12),new THREE.Vector3(x-side*w*.51,y,socket.position.z)]);
        const line=new THREE.Mesh(new THREE.TubeGeometry(curve,24,.002,3,false),new THREE.MeshBasicMaterial({color:0x226bb7,transparent:true,opacity:.22,depthWrite:false}));this.modal.add(line);
      }
      // Keep the full inscription hit area independent of decorative pixels.
      const hit=new THREE.Mesh(new THREE.PlaneGeometry(w,h),new THREE.MeshBasicMaterial({transparent:true,opacity:0,depthWrite:false,side:THREE.DoubleSide}));
      hit.position.z=.035;socket.add(hit);
      this.switches.push({mesh:key,hit,idle,highlight,action:()=>this.finish(option.value==='cancel'?null:option.value),base:0});
    });
    this.label(this.modal,'选择投影符文 · Tab 切换 · Enter 激活 · Esc 返回',2.8,.11,[0,-1.43,.04],17,true);
    this.modal.traverse(object=>{
      object.renderOrder=1000;
      const mesh=object as THREE.Mesh;
      if(mesh.material)for(const material of Array.isArray(mesh.material)?mesh.material:[mesh.material]) {material.depthTest=false;material.depthWrite=false;}
    });
    if(document.pointerLockElement)document.exitPointerLock();
    return new Promise(resolve=>this.modalResolve=resolve);
  }
  private finish(value:string|null):void {
    const resolve=this.modalResolve;this.modalResolve=null;this.active=false;this.modal.visible=false;this.instrument.visible=false;
    this.textEntry=false;this.entryField=null;this.composing=false;
    this.onInput=()=>{};this.accept=()=>{};this.input?.blur();resolve?.(value);
  }
  private clearModal():void {
    const shared=new Set<THREE.Material>([this.material,this.dark,this.glow]);
    this.modal.traverse(o=>{const m=o as THREE.Mesh;m.geometry?.dispose();if(m.material)for(const mat of Array.isArray(m.material)?m.material:[m.material])if(!shared.has(mat))mat.dispose();});
    for(const button of this.switches){button.idle.dispose();button.highlight.dispose();}
    for(const label of this.modalLabels)label.texture.dispose();this.modalLabels=[];this.modal.clear();this.switches=[];
  }
  private restoreEntryFocus=():void=>{
    if(this.active&&this.textEntry&&!document.pointerLockElement)this.input.focus({preventScroll:true});
  };
  private preserveEntryFocus=(event:MouseEvent):void=>{
    if(!this.active||!this.textEntry||event.button!==0)return;
    // Canvas clicks otherwise blur the invisible IME receiver before our RAF
    // raycast. Preserve native editing; do not consume the game's click event.
    if((event.target as HTMLElement|null)?.tagName==='CANVAS') {
      event.preventDefault();this.restoreEntryFocus();
    }
  };
  private keydown=(event:KeyboardEvent):void=>{
    if(!this.active)return;
    // Composition Enter/Escape belongs to the IME, never to the dialog.
    event.stopPropagation();
    if(event.isComposing||this.composing||event.keyCode===229)return;
    if(event.key==='Escape'){event.preventDefault();event.stopImmediatePropagation();this.finish(null);return;}
    if(event.key==='Tab'){
      event.preventDefault();event.stopImmediatePropagation();
      const count=this.switches.length+(this.textEntry?1:0),offset=this.textEntry?1:0;
      this.selected=(this.selected+offset+(event.shiftKey?-1:1)+count)%count-offset;
      return;
    }
    if(event.key==='Enter'){
      event.preventDefault();event.stopImmediatePropagation();
      if(event.repeat)return;
      if(this.textEntry&&this.selected===-1)this.accept();else this.switches[this.selected]?.action();
    } else if(this.textEntry) {
      this.selected=-1;this.restoreEntryFocus();
    }
  };
  update(pointer:{x:number;y:number;clicked:boolean},_dt:number):void {
    if(performance.now()>this.toastUntil)this.paint(this.notice,this.lastMinigame||this.banner);
    if(!this.camera)return;
    // Keep instruments within the horizontal frustum even on narrow viewports.
    const half=Math.tan(THREE.MathUtils.degToRad(this.camera.fov/2))*2.7*this.camera.aspect;
    this.instrument.position.x=-Math.max(0,Math.min(1.38,half-.8));
    this.identity.mesh.position.x=this.instrument.position.x;
    this.modal.scale.setScalar(Math.min(1,half/2.1));
    this.instrument.visible=false;
    if(!this.active)return;
    this.group.updateWorldMatrix(true,true);this.ray.setFromCamera(new THREE.Vector2(pointer.x,pointer.y),this.camera);
    const hits=this.ray.intersectObjects(this.switches.map(s=>s.hit),false);
    const hovered=hits[0]?.object;
    this.switches.forEach((s,i)=>{
      const selected=hovered===s.hit||(!hovered&&i===this.selected);
      s.mesh.position.z=selected?.008:s.base;
      const mat=s.mesh.material as THREE.MeshBasicMaterial;mat.map=selected?s.highlight:s.idle;
    });
    if(pointer.clicked) {
      if(hovered)this.switches.find(s=>s.hit===hovered)?.action();
      else if(this.entryField&&this.ray.intersectObject(this.entryField,false).length) {
        this.selected=-1;this.restoreEntryFocus();
      }
    }
  }
  dispose():void {
    this.finish(null);this.clearModal();window.removeEventListener('keydown',this.keydown,true);
    window.removeEventListener('mousedown',this.preserveEntryFocus,true);
    window.removeEventListener('focus',this.restoreEntryFocus);
    document.removeEventListener('pointerlockchange',this.restoreEntryFocus);this.input.remove();
    for(const l of this.labels)l.texture.dispose();
    this.group.traverse(o=>{const m=o as THREE.Mesh;m.geometry?.dispose();if(m.material)for(const mat of Array.isArray(m.material)?m.material:[m.material])mat.dispose();});
    this.group.removeFromParent();
  }
}
export function escapeHtml(text:string):string {return String(text).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
