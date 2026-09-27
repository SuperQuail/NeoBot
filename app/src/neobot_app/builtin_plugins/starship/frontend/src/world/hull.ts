import * as THREE from 'three';
import { Architecture, type Point } from './geometry';
import type { ShipMaterials } from './materials';
import { sculptShell, type HullStation } from './hull-relief';
import { hullWeb } from './hull-sculpt';

type Outline = [number, number][];

/** Reference study: Spear_of_Adun_Front_LotV.
 * Chined thick shells, open flying buttresses and a suspended reactor nave.
 * -Z is the bow. Spear -500..-250; open nave -250..100; crown 100..500.
 * Authored units are normalized, never habitation metres. ship.ts owns physical scale.
 */
export function buildArkHull(materials: ShipMaterials): THREE.Group {
  const root = new THREE.Group();
  root.name = 'ark-exterior-normalized';
  const a = new Architecture(root);
  const gold = materials.hull.clone(), edge = materials.wallAccent.clone(), bronze = materials.prop;
  gold.color.setHex(0x9d8f59);gold.metalness=.65;gold.roughness=.48;gold.envMapIntensity=.85;
  edge.color.setHex(0xbeac78);edge.roughness=.36;edge.envMapIntensity=.85;
  const recess = materials.ceiling, blue = materials.trim;
  // Dedicated dark structural armour, not near-black cracks in an all-gold shell.
  const inner = materials.wall.clone();
  inner.color.setHex(0x18373f); inner.metalness=.58; inner.roughness=.38;
  inner.name='ark-dark-teal-structure';

  // Small planar parts are bulkheads and the habitation mount, not the main hull.
  const frame = (origin: Point, u: Point, v: Point, depth: Point): THREE.Matrix4 => {
    const m = new THREE.Matrix4().makeBasis(new THREE.Vector3(...u), new THREE.Vector3(...v), new THREE.Vector3(...depth));
    return m.setPosition(...origin);
  };
  const deck = (side: number, y: number, bank = 0, rake = 0): THREE.Matrix4 =>
    frame([0,y,0], [side,bank,0], [0,rake,1], [0,-1,0]);
  const point = (m: THREE.Matrix4, u: number, v: number, w = 0): Point =>
    new THREE.Vector3(u,v,w).applyMatrix4(m).toArray() as Point;
  const shape = (outline: Outline, holes: Outline[] = []): THREE.Shape => {
    const result = new THREE.Shape(outline.map(p => new THREE.Vector2(...p)));
    result.closePath();
    for (const hole of holes) {
      const path = new THREE.Path(hole.map(p => new THREE.Vector2(...p)));
      path.closePath(); result.holes.push(path);
    }
    return result;
  };
  const add = (geometry: THREE.BufferGeometry, m: THREE.Matrix4, material: THREE.Material): void => {
    geometry.applyMatrix4(m);
    // Mirrored port plates must retain outward winding with FrontSide materials.
    if (m.determinant() < 0) {
      if (geometry.index) {
        const ix = geometry.index;
        for (let i=0;i<ix.count;i+=3) { const b=ix.getX(i+1); ix.setX(i+1,ix.getX(i+2)); ix.setX(i+2,b); }
      } else {
        for (const attribute of Object.values(geometry.attributes)) {
          const data=attribute.array, stride=attribute.itemSize;
          for (let i=0;i<attribute.count;i+=3) for (let k=0;k<stride;k++) {
            const b=(i+1)*stride+k,c=(i+2)*stride+k,value=data[b];data[b]=data[c];data[c]=value;
          }
        }
      }
    }
    a.add(geometry,material);
  };
  const plate = (outline: Outline | THREE.Shape, m: THREE.Matrix4, thickness: number, material: THREE.Material, holes: Outline[] = [], bevel = .45): void => {
    const g = new THREE.ExtrudeGeometry(outline instanceof THREE.Shape ? outline : shape(outline,holes), {
      depth: thickness, steps: 1, bevelEnabled: bevel > 0, bevelSize: bevel,
      bevelThickness: bevel*.6, bevelSegments: 2, curveSegments: 32,
    });
    add(g,m,material);
  };
  const engraving = (m: THREE.Matrix4, line: Outline, width = .32, material: THREE.Material = recess, relief = -.12): void => {
    // Hard-cornered, recessed-looking cuts rather than thick glowing noodles.
    for (let i=1;i<line.length;i++) {
      const p=new THREE.Vector3(...point(m,...line[i-1],relief));
      const q=new THREE.Vector3(...point(m,...line[i],relief));
      const delta=q.clone().sub(p);
      const g=new THREE.BoxGeometry(width,width,delta.length()+width*.25);
      g.applyQuaternion(new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0,0,1),delta.normalize()));
      g.translate(...p.add(q).multiplyScalar(.5).toArray() as Point); a.add(g,material);
    }
  };
  const rim = (m: THREE.Matrix4, outline: Outline, material: THREE.Material = bronze, width = .65): void =>
    engraving(m,[...outline,outline[0]],width,material,-.28);
  const beam = (from: Point, to: Point, width: number, depth: number, material: THREE.Material): void => {
    const p=new THREE.Vector3(...from),q=new THREE.Vector3(...to),d=q.clone().sub(p);
    const g=new THREE.BoxGeometry(width,depth,d.length());
    g.applyQuaternion(new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0,0,1),d.normalize()));
    g.translate(...p.add(q).multiplyScalar(.5).toArray() as Point); a.add(g,material);
  };
  const jewel = (m: THREE.Matrix4, u: number, v: number, radius: number, stretch = 1): void => {
    // Round porthole sockets, inset blue cabochons, and a real open annular bezel.
    add(new THREE.CylinderGeometry(radius*1.21,radius*1.27,1.3,32).rotateX(Math.PI/2).translate(u,v,.2),m,recess);
    add(new THREE.TorusGeometry(radius*1.12,.65,6,36).scale(1,stretch,1).translate(u,v,-.7),m,edge);
    add(new THREE.SphereGeometry(radius,24,12).scale(1,stretch,.25).translate(u,v,-.6),m,blue);
    for (const s of [-1,1]) engraving(m,[[u+s*radius*.5,v-radius*.7*stretch],[u+s*radius*.8,v],[u+s*radius*.5,v+radius*.7*stretch]],.35,bronze,-radius*.23-.8);
  };
  // Successfully viewed references (not merely search results):
  // https://static.wikia.nocookie.net/starcraft/images/3/32/Spear_of_Adun_Front_LotV.jpg/revision/latest
  // https://static.wikia.nocookie.net/starcraft/images/1/19/Spear_of_Adun_Rear_LotV.jpg/revision/latest
  // Simon Fuchs highpoly/InGame pages were researched; their old images return HTTP 400.
  // Public Sketchfab 7582ff949a4844e4bbc32ea93de2b8ec side preview also viewed;
  // used only as visual reference, never downloaded/reused as a licensed model.
  const shell=(stations:HullStation[],s=1,cuts=[0,.28,.66,1])=>{
    const body=sculptShell(a,stations,s,inner);
    for(let i=1;i<cuts.length;i++){
      const lo=cuts[i-1]+.005,hi=cuts[i]-.006;
      body.panel(lo,hi,.025,.205,1.4,gold);
      // Stagger dorsal and flank joints instead of complete dark barrel hoops.
      const nextLo=i===1?.006:Math.min(.97,cuts[i-1]+.075),nextHi=i===cuts.length-1?.994:Math.min(.98,cuts[i]+.064);
      body.panel(nextLo,nextHi,.285,.455,1.65,gold);
      body.panel(Math.max(.005,lo-.035),Math.min(.995,hi+.015),.69,.91,.95,bronze);
    }
    // Continuous chamfer follows the OUTER shoulder, not a drawn outline.
    body.panel(.012,.987,.005,.024,.9,edge);
    return body;
  };
  const ribs=(body:ReturnType<typeof sculptShell>,ts:number[],u0=.5,u1=.73)=>{
    for(const t of ts){
      body.panel(t-.007,t+.007,u0,u1,1.0,bronze);
      const p=body.point(t,(u0+u1)*.5,1.25);
      a.add(new THREE.BoxGeometry(.8,.9,1.6).translate(...p),blue);
    }
  };

  // FORE: a narrow deep prow with a chamfered keel and independently rolled cheeks.
  // Habitation is a tiny local pad on a real cheek ridge, not the central valley.
  const mount=new THREE.Vector3();
  const prow=shell([[0,-1,-500,.1,.2,.2,0],[0,-4,-456,6,4,4,0],[0,-10,-394,15,7,11,0],
    [0,-12,-330,25,12,18,0],[0,-13,-280,27,12,17,0],[0,-16,-238,17,8,12,0]],1,[0,.38,.70,1]);
  prow.panel(.22,.51,.21,.28,1.1,recess);
  for(const s of [-1,1]){
    const cheek=shell([[2,0,-482,.15,.3,.4,0],[12,0,-421,5,5,6,-.2],
      [25,1,-352,11,10,16,-.3],[31,3,-292,15,18,20,-.4],[25,0,-238,9,15,14,-.3]],s,[0,.34,.73,1]);
    cheek.panel(.28,.61,.12,.24,1.9,recess);
    cheek.panel(.33,.58,.145,.205,2.1,blue);
    ribs(cheek,[.64,.68,.72,.77,.82],.51,.76);
    if(s===1){
      mount.fromArray(cheek.point((2+32/60)/4,4/12,1.65));
      mount.y+=.65;
      const x=mount.x,z=mount.z,hx=1.38,hz=1.7473;
      // About 200 x 260 metres after physical scaling; embedded in the ridge.
      plate([[x-hx,z-hz],[x+hx,z-hz],[x+hx,z+hz],[x-hx,z+hz]],deck(1,mount.y),2,gold,[],0);
    }
    const saddle=shell([[35,-14,-271,5,5,7,0],[29,12,-248,8,9,8,-.2],
      [12,28,-232,7,5,7,-.3],[4,30,-220,2,2,2,0]],s,[0,.48,1]);
    saddle.panel(.26,.61,.17,.3,2.1,bronze);
  }
  // Nothing is added over the mount point; the tiny face stays horizontal.
  jewel(deck(1,4),0,-390,7,2.4);

  // MIDDLE: load-bearing crescent longrons, thick in SIDE view as well as plan.
  // No skin spans the nave (z -215..-55): these are two independent hollow-frame sides.
  for(const s of [-1,1]){
    const rail=shell([[27,-15,-259,9,12,12,0],[39,-20,-215,15,15,17,-.15],
      [54,-31,-140,19,13,18,-.25],[68,-33,-50,24,15,19,-.18],
      [79,-32,47,27,16,20,-.28],[80,-30,128,27,18,20,-.38],
      [68,-29,188,20,17,20,-.25]],s,[0,.21,.51,.73,1]);
    // Inner channel is a deep blue-gray wall with unequal structural bays.
    rail.panel(.24,.52,.46,.57,.55,recess);
    rail.panel(.56,.74,.46,.57,.55,recess);
    ribs(rail,[.27,.31,.36,.43,.48,.58,.62,.69,.81,.84,.87],.45,.67);
    // Broad overlapping shoulder armour, not little leaf-shaped perforations.
    const shoulder=shell([[53,-18,-102,1,2,3,0],[68,-19,-25,18,13,12,-.3],
      [81,-19,62,24,14,15,-.4],[75,-17,126,24,15,15,-.3],
      [66,-20,174,10,10,10,0]],s,[0,.46,1]);
    shoulder.panel(.22,.63,.26,.39,2.5,bronze);
    shoulder.panel(.28,.57,.28,.35,2.7,recess);
    // Curved upper flying canopy leaves the reactor visible through its central slit.
    const canopy=shell([[8,21,-109,.15,.2,.2,0],[29,29,-61,11,9,11,-.35],
      [45,34,4,18,14,18,-.45],[51,34,76,21,18,22,-.5],
      [41,30,151,22,19,22,-.38],[18,24,229,15,13,16,-.2]],s,[0,.40,.68,1]);
    canopy.panel(.35,.65,.26,.4,2.9,gold);
    canopy.panel(.44,.61,.11,.21,1.95,recess);
    ribs(canopy,[.69,.73,.77,.82,.87],.53,.81);
    // An actual web descending from canopy to rail, with a structural window.
    const web=frame([s*46,0,0],[0,1,0],[0,0,1],[-s,0,0]);
    const webOutline:Outline=[[-24,125],[-12,65],[26,78],[37,125],[24,181],[-7,171]];
    const window:Outline=[[0,104],[18,103],[20,126],[4,147],[-5,142]];
    plate(webOutline,web,7,inner,[window],1.2);
    rim(web,window,bronze,1.5);
    plate([[27,121],[19,165],[4,168],[9,141]],web.clone().multiply(new THREE.Matrix4().makeTranslation(0,0,-1.2)),3,gold,[],.7);
    for(const z of [87,96,156,165])beam([s*47,-6,z],[s*47,18,z+7],1.8,2.2,bronze);
  }

  // REAR: a vaulted engine cathedral. The crown is a broad convex wedge and
  // the outboard forks have rolled flanks; large triangular bays remain open.
  for(const s of [-1,1]){
    const outrigger=shell([[68,-29,114,19,17,20,-.2],[83,-25,180,25,18,23,-.25],
      [91,-25,259,24,19,23,-.22],[96,-23,330,20,17,21,-.2],
      [92,-20,398,15,14,17,-.16],[98,-13,461,5,6,6,0],[105,-10,489,.1,.1,.1,0]],s,[0,.26,.57,.80,1]);
    outrigger.panel(.15,.36,.27,.40,2.9,gold);
    outrigger.panel(.41,.67,.10,.20,1.9,recess);
    ribs(outrigger,[.18,.22,.26,.48,.52,.57,.62,.68,.73],.52,.79);
    // Thick diagonal arms have entirely different cross-sections from the longrons.
    const arch=shell([[14,38,238,18,18,23,-.4],[42,32,276,23,19,26,-.5],
      [66,5,319,25,19,25,-.45],[85,-15,361,21,21,21,-.3],
      [92,-20,413,12,13,15,0]],s,[0,.52,1]);
    arch.panel(.12,.77,.13,.28,2.3,gold);
    arch.panel(.23,.63,.33,.39,1.9,recess);
    ribs(arch,[.18,.23,.28,.69,.74,.8],.54,.79);
    // Lower return arch, well separated vertically from the dorsal arch.
    shell([[17,-30,177,8,9,11,0],[40,-43,227,11,11,11,.2],
      [64,-38,283,13,10,12,.3],[85,-24,339,12,12,13,.2]],s,[0,.37,.74,1]);
    // Forward shoulder reaches up into the core bulkhead instead of hanging free.
    shell([[73,-17,126,10,10,14,0],[61,7,168,16,14,17,-.3],
      [39,32,219,16,14,19,-.45],[10,35,257,11,10,14,-.3]],s,[0,.55,1]);
    // Fork undercut: a shorter fin with thickness concentrated at its root.
    shell([[96,-20,285,8,8,11,0],[107,-22,350,10,8,10,.1],
      [110,-17,409,5,5,7,.1],[115,-9,438,.1,.2,.2,0]],s,[0,.67,1]);
  }
  // The in-game hull carries a long solid machinery nave INSIDE the crown.
  // Keep only the forward quarter open; do not mistake the four flying shoulders
  // for the entire ship. This is kilometre-scale machinery, not the tiny habitat.
  const chamber=shell([[0,-3,42,17,18,20,0],[0,-1,105,31,29,29,0],
    [0,0,184,40,36,34,0],[0,0,267,43,39,36,0],
    [0,0,330,33,34,33,0],[0,0,348,28,30,30,0]],1,[0,.22,.48,.77,1]);
  chamber.panel(.16,.84,.055,.13,2.3,recess);
  chamber.panel(.16,.84,.45,.53,2.3,recess);
  ribs(chamber,[.21,.25,.30,.36,.41,.49,.57,.64,.71,.76],.04,.16);
  // Large dorsal spear crown: raised ridge, broad shoulders, heavy downward chin.
  const crown=shell([[0,31,193,14,10,16,0],[0,39,264,32,20,25,0],
    [0,44,337,43,26,30,0],[0,48,394,34,23,25,0],
    [0,49,452,17,13,16,0],[0,50,500,.1,.2,.3,0]],1,[0,.29,.63,1]);
  crown.panel(.15,.70,.19,.36,3.0,gold);
  crown.panel(.30,.73,.10,.16,2,recess);
  crown.panel(.30,.73,.41,.47,2,recess);
  jewel(deck(1,70),0,337,10.5,2.3);
  // Rear engine cluster seen in Rear_LotV: annular nozzles, recessed throats,
  // and short canted plumbing, not extra decorative blue portholes on the skin.
  const engineFace=frame([0,0,353],[1,0,0],[0,1,0],[0,0,-1]);
  const engineOutline:Outline=[[-17,-42],[17,-42],[30,-30],[37,-10],[35,17],[23,39],[-23,39],[-35,17],[-37,-10],[-30,-30]];
  const engineShape=shape(engineOutline);
  const engines:Point[]=[[0,19,13.5],[0,-19,12.5],[-22,0,8],[22,0,8]];
  for(const [x,y,r] of engines){const hole=new THREE.Path();hole.absarc(x,y,r*1.1,0,Math.PI*2,true);engineShape.holes.push(hole);}
  plate(engineShape,engineFace,19,inner,[],1.0);
  // A substantial shared cassette ties all four bells to the engine room.
  // Gold only trims the rim; the recessed blue-black web remains visually dominant.
  plate(engineOutline,engineFace,5,bronze,[engineOutline.map(([x,y])=>[x*.84,y*.86] as [number,number])],.7);
  for(const s of [-1,1]){
    beam([s*30,21,347],[s*79,-8,348],9,8,inner);
    beam([s*31,-24,347],[s*64,-31,312],7,7,bronze);
    for(const y of [-27,-16,9,20]){
      engraving(engineFace,[[s*28,y],[s*31,y+5],[s*29,y+10]],1.15,bronze,-.8);
      engraving(engineFace,[[s*31,y+1],[s*32,y+5]],.52,blue,-1.0);
    }
    // Engine-side ribbed bays continue forward into the rear chamber.
    const m=frame([s*25,0,0],[0,1,0],[0,0,1],[-s,0,0]);
    plate([[-21,268],[19,275],[25,319],[17,338],[-23,332]],m,3,recess,[],.65);
    for(const z of [278,286,297,309,321]){
      engraving(m,[[-18,z],[-5,z+3],[16,z+2]],1.4,bronze,-1.0);
      engraving(m,[[-9,z+2],[-3,z+3]],.62,blue,-1.8);
    }
  }
  for(const [x,y,r] of engines){
    a.add(new THREE.CylinderGeometry(r*1.32,r*1.1,12,24,1,true).rotateX(Math.PI/2).translate(x,y,350),bronze);
    a.add(new THREE.TorusGeometry(r*1.12,2.2,8,32).translate(x,y,357),edge);
    a.add(new THREE.CircleGeometry(r,32).translate(x,y,352),recess);
    a.add(new THREE.TorusGeometry(r*.76,1.25,6,32).translate(x,y,353),blue);
    a.add(new THREE.CircleGeometry(r*.65,24).translate(x,y,353.1),blue);
    for(let j=0;j<10;j++){
      const theta=j*Math.PI/5;
      beam([x+Math.cos(theta)*r*.8,y+Math.sin(theta)*r*.8,353],[x+Math.cos(theta)*r*1.13,y+Math.sin(theta)*r*1.13,357],1,1,bronze);
    }
  }

  // Central suspended ovoid: its blue body is surrounded, never replaced, by
  // the canopy, side webs, two cradle arms and polygonal meridian cage.
  a.add(new THREE.SphereGeometry(1,40,28).scale(20,20,37).translate(0,0,-22),blue);
  for(let i=0;i<7;i++){
    const angle=i*Math.PI*2/7,path:Point[]=[];
    for(let j=0;j<=22;j++){
      const t=.13+j/22*(Math.PI-.26),r=Math.sin(t);
      path.push([Math.cos(angle)*20.7*r,Math.sin(angle)*20.7*r,-22+Math.cos(t)*38]);
    }
    a.curve(path,.85,i%2?bronze:edge,32);
  }
  for(const z of [15,34,58,85,112]){
    a.add(new THREE.CylinderGeometry(19,20,7,24,1,true).rotateX(Math.PI/2).translate(0,0,z),bronze);
    a.ring(19.4,1.2,[0,0,z+3.6],edge,true);
  }
  // Drive spine supports the exposed reactor without filling the nave.
  a.add(new THREE.CylinderGeometry(13.5,17,100,16).rotateX(Math.PI/2).translate(0,-3,66),recess);
  for(const s of [-1,1]){
    shell([[13,-8,108,5,6,7,0],[29,-25,132,7,9,9,.2],[51,-20,153,8,8,8,0]],s,[0,.5,1]);
    // Uneven service/recess detail concentrates at joints, leaving long calm faces.
    for(const [x,y,z] of [[77,13,92],[90,8,204],[91,11,290],[50,41,118]] as Point[]){
      const m=deck(s,y,-.2);
      jewel(m,x,z,3.1,1.4);
      for(let j=0;j<3;j++)engraving(m,[[x-7+j*2,z-8],[x-5+j*2,z-2],[x-5+j*2,z+4]],.85,bronze,-.2);
    }
  }

  // Public side view shows broad canted blue-black fields on the LOWER nave,
  // plus triangular sails aft; they are not four empty, equally thin needles.
  const field=inner.clone(); field.name='ark-recessed-energy-armour';
  field.color.setHex(0x164b64); field.emissive.setHex(0x0b415d); field.emissiveIntensity=.4;
  field.metalness=.42; field.roughness=.32;
  for(const s of [-1,1]){
    const web=(points:Point[],depth:number,material:THREE.Material=inner)=>{
      const p=points.map(([x,y,z])=>[s*x,y,z] as Point);
      if(s<0)p.reverse();
      hullWeb(a,p,depth,gold,material,material===field?field:recess);
    };
    // Three separate folded shields overlap the inner flank of the lower rail.
    // Kept INBOARD of the thick rail, not buried beneath its dorsal shell.
    web([[19,-26,-228],[32,-9,-194],[44,-11,-119],[25,-30,-131]],2.5,field);
    web([[25,-30,-130],[44,-11,-118],[55,-11,-33],[30,-31,-45]],2.8,field);
    web([[30,-31,-44],[55,-11,-32],[61,-11,60],[35,-27,75]],3,field);
    // A real flared engine buttress ties the long solid nave to the broad rail.
    web([[27,17,153],[43,29,214],[85,-7,254],[66,-28,177]],8,inner);
    web([[28,-17,174],[65,-35,206],[86,-23,303],[43,-29,274]],7,inner);
    // The triangular rear crown windows remain visibly OPEN around these sails.
    // These sails lie FORWARD of the descending rear arch, facing the nave.
    web([[31,49,243],[56,33,224],[70,3,173],[46,8,184]],2.8,field);
    web([[34,-29,170],[64,-30,209],[77,-23,271],[43,-42,240]],2.8,field);
    // Angular inset cheek fields break the former giant blank gold shoulders.
    web([[63,-7,-41],[82,2,29],[88,-3,80],[73,-4,57]],2.4,recess);
    web([[15,47,271],[27,55,315],[25,56,358],[13,55,334]],2.4,inner);
    // Stepped dorsal crown barbs split the former plain oval paddle silhouette.
    shell([[20,42,271,8,7,9,0],[35,48,319,13,9,12,-.15],
      [41,48,370,11,10,12,-.2],[39,50,428,.15,.3,.3,0]],s,[0,.48,1]);
    shell([[30,33,277,8,8,10,0],[47,37,316,10,9,11,-.2],
      [58,37,380,.15,.3,.3,0]],s,[0,.58,1]);
    // Three short sacrificial fork blades per rear flank, rooted in real hull.
    shell([[91,-13,343,9,7,10,0],[103,-12,397,10,7,9,0],
      [112,-8,463,.2,.3,.3,0]],s,[0,.55,1]);
    shell([[85,-27,321,9,7,9,0],[94,-29,375,11,8,10,0],
      [98,-25,426,.1,.2,.2,0]],s,[0,.6,1]);
  }

  a.finish();
  // Preserve the exact established normalization and the metre-scale mount API.
  root.updateMatrixWorld(true);
  const bounds=new THREE.Box3().setFromObject(root), size=bounds.getSize(new THREE.Vector3());
  const scale=new THREE.Vector3(230/size.x,123/size.y,1000/size.z);
  const transform=new THREE.Matrix4().makeScale(scale.x,scale.y,scale.z);
  transform.setPosition(-115-bounds.min.x*scale.x,-70-bounds.min.y*scale.y,-500-bounds.min.z*scale.z);
  root.traverse(object=>{
    if (!(object instanceof THREE.Mesh)) return;
    object.geometry.applyMatrix4(transform);
    object.geometry.computeBoundingBox();object.geometry.computeBoundingSphere();
    object.name='ark-batched-'+(object.material.name || object.material.type);
    object.castShadow=true;object.receiveShadow=true;
  });
  root.userData.mountPoint=mount.applyMatrix4(transform).toArray();
  // Positions are on the OUTER lip, transformed with the actual geometry.
  // The emitter lives outside this group so flames cannot change hull bounds.
  root.userData.engineExhausts=engines.map(([x,y,r])=>({
    position:new THREE.Vector3(x,y,359.2).applyMatrix4(transform).toArray(),
    direction:new THREE.Vector3(0,0,1).transformDirection(transform).toArray(),
    radius:r*Math.min(scale.x,scale.y),
  }));
  root.userData.designDimensions={length:1000,width:230,height:123};
  root.userData.forwardAxis='-z';
  root.userData.silhouette='thick chined spear / open reactor nave / vaulted engine crown';
  root.userData.reference='Spear_of_Adun_Front_LotV + Spear_of_Adun_Rear_LotV (both viewed)';
  return root;
}
