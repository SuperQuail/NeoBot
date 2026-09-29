/** Reference: Blizzard LOTV bridge campaign preview. A sculpted sanctuary,
 * not a transparent box with repeated ribs. All dimensions remain walkable metres. */
import * as THREE from 'three';
import { Architecture, type Point } from './geometry';
import type { ShipMaterials } from './materials';
import { createSignTexture } from './materials';
import { buildBridgeShield } from './shield';
import { DEFAULT_SHIP_NAME } from '../config';
import type { CollisionWorld } from '../core/collision';

export function buildSanctum(m:ShipMaterials, collision:CollisionWorld) {
  const group=new THREE.Group();group.name='celestial-sanctum';
  const a=new Architecture(group), gold=m.hull, edge=m.wallAccent, dark=m.ceiling, inset=m.wall;
  const placePlate=(shape:THREE.Shape,depth:number,at:Point,mat:THREE.Material,mirror=false)=>a.plate(shape,depth,at,mat,mirror);
  const engraved=(points:Point[],r=.025)=>a.curve(points,r,dark,36);
  const light=new THREE.MeshBasicMaterial({color:0x298df5,transparent:true,opacity:.7});
  const whiteBlue=new THREE.MeshStandardMaterial({color:0x153c77,emissive:0x398eff,emissiveIntensity:2.0,metalness:.35,roughness:.25});
  // Broad curved floor panels and black inset routes. Trim is a thin edge, not a wire grid.
  for(let i=0;i<12;i++) {
    const start=i*Math.PI/6+.016,end=(i+1)*Math.PI/6-.016;
    const shape=new THREE.Shape();shape.absarc(0,0,19.9,start,end,false);
    shape.absarc(0,0,5.7,end,start,true);shape.closePath();
    const g=new THREE.ExtrudeGeometry(shape,{depth:.012,bevelEnabled:true,bevelThickness:.002,bevelSize:.04,bevelSegments:2,curveSegments:32});
    g.rotateX(-Math.PI/2);g.translate(0,.003,-21);a.add(g,i%3===0?m.floor:m.prop);
    const paths:Point[]=[];for(let j=0;j<=30;j++) {const t=start+(end-start)*j/30;paths.push([Math.cos(t)*19.3,.024,-21-Math.sin(t)*19.3]);}
    a.curve(paths,.006,edge,32);
  }
  for(const radius of [4.8,5.0,5.65,20.2])a.ring(radius,.013,[0,.024,-21],radius===5?light:dark);
  // A wide dark inset connects the command table to the celestial arch.
  a.box([2.6,.01,26],[0,.023,-22],dark);
  for(const s of [-1,1]) {
    a.curve([[s*1.25,.033,-40],[s*1.25,.033,-28],[s*1.7,.033,-20],[s*2.4,.033,-10]],.008,edge);
    a.curve([[s*1.12,.036,-37],[s*1.12,.036,-28],[s*1.55,.036,-20]],.006,light);
  }
  // Sweeping engraved leaves in the broad floor plates, rather than a generic sci-fi grid.
  for(let i=0;i<10;i++) {
    const angle=i/10*Math.PI*2+.16;
    const leaf=new THREE.Shape();leaf.moveTo(0,0);leaf.bezierCurveTo(-1.8,2,-1.2,5.5,0,8);
    leaf.bezierCurveTo(.1,4.8,1.8,2,0,0);leaf.closePath();
    const cut=new THREE.Path();cut.moveTo(0,1.1);cut.bezierCurveTo(.7,2.8,.05,4.8,0,6.1);cut.bezierCurveTo(-.6,3.5,-.6,2,0,1.1);cut.closePath();leaf.holes.push(cut);
    const g=new THREE.ShapeGeometry(leaf,30);g.rotateZ(angle);g.rotateX(-Math.PI/2);g.translate(Math.sin(angle)*8,.031,-21-Math.cos(angle)*8);a.add(g,i%2===0?gold:edge);
  }
  // The characteristic forward crescent wing-pylons: thick planar armour with engraved faces.
  const wing=new THREE.Shape();wing.moveTo(24,0);wing.bezierCurveTo(17,.2,16,2.5,17.2,5.5);
  wing.bezierCurveTo(18.1,8.5,17,10.8,13.8,12.9);wing.bezierCurveTo(21.5,11.9,24,8.1,24.2,5.8);
  wing.lineTo(25.6,.7);wing.closePath();
  for(const s of [-1,1]) {
    placePlate(wing,1.8,[0,0,-39],edge,s<0);
    const inner=new THREE.ExtrudeGeometry(wing,{depth:.3,bevelEnabled:true,bevelThickness:.11,bevelSize:.09,bevelSegments:3,curveSegments:36});
    inner.scale(.86,.88,1);inner.translate(3.1,.45,-36.95);
    if(s<0) {inner.scale(-1,1,1);flipWinding(inner);}
    a.add(inner,gold);
    engraved([[s*23.7,1,-36.5],[s*20,2.2,-36.5],[s*19.5,5.7,-36.5],[s*20,8.8,-36.5],[s*17.3,11.1,-36.5]],.07);
    a.curve([[s*23,1,-36.35],[s*20.7,2.6,-36.35],[s*20.6,5.1,-36.35]],.036,light);
    // Layered medallion and inset azure lens. These are surfaces, not a white floating crystal.
    for(const [radius,tube,mat] of [[1.12,.13,dark],[.94,.08,edge],[.75,.05,inset]] as const) {
      const g=new THREE.TorusGeometry(radius,tube,8,64);g.scale(1,1.25,1);g.translate(s*20.4,5.8,-36.2);a.add(g,mat);
    }
    a.add(new THREE.SphereGeometry(.48,24,16).scale(.78,1.25,.35).translate(s*20.4,5.8,-36),whiteBlue);
    for(let j=0;j<7;j++)a.box([.1,.24,.03],[s*(22.65-j*.22),2.2+j*.25,-36.22],light);
  }
  // Ornamented bridge apron sweeps into a central eye, the visual motif in the reference.
  const apron=new THREE.Shape();apron.moveTo(-19,2.1);apron.bezierCurveTo(-11,1.8,-5,4,0,4.2);
  apron.bezierCurveTo(5,4,11,1.8,19,2.1);apron.lineTo(18,1.3);
  apron.bezierCurveTo(9,1.2,4,2.2,0,2.45);apron.bezierCurveTo(-4,2.2,-9,1.2,-18,1.3);apron.closePath();
  placePlate(apron,.9,[0,0,-39.2],dark);
  a.curve([[-18,2.05,-38.16],[-9,2.25,-38.16],[0,3.45,-38.16],[9,2.25,-38.16],[18,2.05,-38.16]],.065,gold,72);
  a.add(new THREE.SphereGeometry(.55,32,20).scale(1.5,.72,.5).translate(0,3.28,-37.9),whiteBlue);
  for(const s of [-1,1]) {
    a.curve([[s*1.1,3.3,-37.95],[s*2.2,4.05,-38],[s*4.6,3.3,-38.1]],.13,edge,24);
    for(const x of [4.8,8.5,12.2])a.ring(.27,.04,[s*x,2.65,-38.1],gold,true);
  }
  // Sweeping side architecture: only two massive, layered buttresses, no greenhouse hoops.
  const buttress=new THREE.Shape();buttress.moveTo(22.6,0);buttress.lineTo(26.6,0);
  buttress.bezierCurveTo(26.5,8,24,15,14,20);buttress.bezierCurveTo(19,15,21,9,21.4,5);buttress.closePath();
  for(const s of [-1,1]) for(const z of [-10,-1]) {
    placePlate(buttress,2.1,[0,0,z],dark,s<0);
    const band=new THREE.Shape();band.moveTo(24,0);band.bezierCurveTo(25,8,23,14,15,19);
    band.bezierCurveTo(21,14,22,8,22.5,0);band.closePath();placePlate(band,.25,[0,0,z+2.15],gold,s<0);
    a.curve([[s*23.6,.5,z+2.52],[s*23.9,6,z+2.52],[s*21.3,12.5,z+2.52],[s*16.7,17.3,z+2.52]],.036,light,48);
    collision.addFromCenter(new THREE.Vector3(s*23.4,2.5,z+1),new THREE.Vector3(2.2,5,2.2),'buttress');
  }
  // Waist-high curving observation balustrades create space without filling it with glass boxes.
  for(const s of [-1,1]) {
    a.curve([[s*23.6,.65,-37],[s*22.7,.8,-27],[s*22.8,.75,-15],[s*23.5,.7,-3]],.31,dark,64);
    a.curve([[s*23.5,1,-37],[s*22.7,1.14,-27],[s*22.8,1.1,-15],[s*23.5,1.05,-3]],.045,gold,64);
    for(const z of [-32,-23,-14]) {
      const fin=new THREE.Shape();fin.moveTo(0,0);fin.bezierCurveTo(.45,.7,.48,1.5,.15,2.2);fin.lineTo(-.26,.9);fin.closePath();
      placePlate(fin,.26,[s*23,.4,z],gold);
      a.add(new THREE.SphereGeometry(.1,12,8).translate(s*23,1.1,z+.3),whiteBlue);
    }
  }
  // Asymmetric engraved memory pylons echo the celestial devices beside Artanis.
  for(const [x,z,h] of [[-8.2,-27,6.6],[8.8,-29,4.8]]) {
    const pylon=new THREE.Shape();pylon.moveTo(-1,0);pylon.bezierCurveTo(-.95,h*.3,-.7,h*.66,0,h);
    pylon.bezierCurveTo(.4,h*.66,1.05,h*.22,1,0);pylon.closePath();
    placePlate(pylon,.55,[x,0,z],edge);
    const g=new THREE.ExtrudeGeometry(pylon,{depth:.17,bevelEnabled:true,bevelSize:.06,bevelThickness:.06,bevelSegments:3,curveSegments:32});g.scale(.74,.85,1);g.translate(x,h*.06,z+.62);a.add(g,dark);
    a.add(new THREE.SphereGeometry(.3,24,16).scale(.75,1.8,.4).translate(x,h*.37,z+.87),whiteBlue);
    a.curve([[x-.55,.5,z+.86],[x-.45,h*.35,z+.86],[x,h*.82,z+.86]],.035,gold);
    a.curve([[x+.55,.5,z+.86],[x+.45,h*.35,z+.86],[x,h*.82,z+.86]],.035,gold);
    for(let j=0;j<6;j++)a.box([.17,.055,.03],[x,h*.54+j*.13,z+.89],light);
    collision.addFromCenter(new THREE.Vector3(x,h/2,z+.35),new THREE.Vector3(2,h,.9),'memory-pylon');
  }
  // Ceiling falls into darkness behind the player; the panoramic front remains open to space.
  a.box([50,1.2,12],[0,17,-1],dark);
  for(const s of [-1,1])a.box([2.4,5,1.2],[s*24.7,2.5,.2],dark);
  for(const s of [-1,1]) {
    a.box([19,16,1.2],[s*14.5,8,.2],dark);
    for(let i=0;i<3;i++) {
      const x=s*(8+i*6),panel=new THREE.Shape();panel.moveTo(x-2,1);panel.lineTo(x+2,1);panel.lineTo(x+2.4,12);panel.lineTo(x,15);panel.lineTo(x-2.4,12);panel.closePath();
      placePlate(panel,.18,[0,0,-.6],i===1?gold:inset);
      a.add(new THREE.OctahedronGeometry(.23).scale(.6,1.6,.4).translate(x,8,-.8),whiteBlue);
    }
  }
  // Heavy pointed threshold leads to the high council/foundry hall.
  for(const s of [-1,1]) {
    a.curve([[s*5.2,0,0],[s*5.1,5,0],[s*3.4,8,0],[0,10,0]],.58,gold);
    a.curve([[s*4.8,.4,-.12],[s*4.7,4.7,-.12],[s*3.1,7.6,-.12],[0,9.5,-.12]],.055,light);
  }
  a.finish();
  const shield=buildBridgeShield(m);group.add(shield);
  group.userData.update=(dt:number)=>shield.userData.update(dt);
  // Vessel identity is engraved into the architecture, not a floating black website banner.
  const plaque=new THREE.Mesh(new THREE.PlaneGeometry(4.8,.6),new THREE.MeshBasicMaterial({map:createSignTexture(DEFAULT_SHIP_NAME,''),transparent:true,depthWrite:false,toneMapped:false}));
  plaque.position.set(0,1.82,-37.85);group.add(plaque);
  const warm=new THREE.PointLight(0xf0c895,32,17,1.6);warm.position.set(-2.5,5.5,-13);group.add(warm);
  const blue=new THREE.PointLight(0x287cff,55,21,1.7);blue.position.set(0,2.6,-17);group.add(blue);
  for(const s of [-1,1]){const light=new THREE.PointLight(0x2265dd,65,23,1.7);light.position.set(s*20,5,-30);group.add(light);}
  group.traverse(o=>{if(o instanceof THREE.Mesh){o.receiveShadow=true;o.castShadow=!((o.material as THREE.Material).transparent);}});
  return {group,setName(name:string){plaque.material.map?.dispose();plaque.material.map=createSignTexture(name,'');plaque.material.needsUpdate=true;}};
}
function flipWinding(g:THREE.BufferGeometry):void {
  if(g.index){for(let i=0;i<g.index.count;i+=3){const b=g.index.getX(i+1);g.index.setX(i+1,g.index.getX(i+2));g.index.setX(i+2,b);}}
  else for(const attr of Object.values(g.attributes)) for(let i=0;i<attr.count;i+=3) for(let k=0;k<attr.itemSize;k++) {
    const a=attr.array,j=(i+1)*attr.itemSize+k,l=(i+2)*attr.itemSize+k,t=a[j];a[j]=a[l];a[l]=t;
  }
}
