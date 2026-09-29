import * as THREE from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';

/** Sculpted, texture-free escorts; local -Z is forward, length normalized to 1.
 * Viewed original SC2 references (not textures used by these models):
 * https://static.wikia.nocookie.net/starcraft/images/3/3d/Phoenix_SC2_Rend1.jpg
 * https://static.wikia.nocookie.net/starcraft/images/9/94/Phoenix_SC2_Rend2.jpg
 * https://static.wikia.nocookie.net/starcraft/images/a/a8/Phoenix_SC2_Cncpt1.jpg
 * https://static.wikia.nocookie.net/starcraft/images/1/1d/VoidRay_SC2_Rend1.jpg
 */
export type FighterKind = 'phoenix' | 'void-ray';
type Finish = 'gold' | 'bronze' | 'inlay' | 'core' | 'engine';
type Row = [x:number,y:number,z:number,width:number,depth:number];
export interface FighterAsset {
  parts: { geometry:THREE.BufferGeometry; material:THREE.Material; finish:Finish }[];
  dispose():void;
}

/** Cambered solid swept armor. Rings give both a shaped upper and lower surface;
 * the crescent-wing apertures are genuinely empty space, never alpha cutouts. */
function shell(rows:Row[], steps=32):THREE.BufferGeometry {
  const curve=new THREE.CatmullRomCurve3(rows.map(r=>new THREE.Vector3(r[0],r[1],r[2])),false,'centripetal');
  const rings=12, positions:number[]=[], indices:number[]=[];
  for(let i=0;i<=steps;i++) {
    const t=i/steps, p=curve.getPoint(t), tangent=curve.getTangent(t);
    const across=new THREE.Vector3(0,1,0).cross(tangent).normalize();
    const up=tangent.clone().cross(across).normalize();
    const f=t*(rows.length-1),a=Math.min(rows.length-2,Math.floor(f)),v=f-a;
    const w=THREE.MathUtils.lerp(rows[a][3],rows[a+1][3],v),d=THREE.MathUtils.lerp(rows[a][4],rows[a+1][4],v);
    for(let j=0;j<rings;j++) {
      const angle=j/rings*Math.PI*2,c=Math.cos(angle),s=Math.sin(angle);
      const point=p.clone().addScaledVector(across,c*w).addScaledVector(up,Math.sign(s)*Math.pow(Math.abs(s),.75)*d);
      positions.push(point.x,point.y,point.z);
    }
  }
  for(let i=0;i<steps;i++)for(let j=0;j<rings;j++) {
    const a=i*rings+j,b=i*rings+(j+1)%rings,c=a+rings,d=b+rings;
    indices.push(a,b,c,b,d,c);
  }
  for(let j=1;j<rings-1;j++) {indices.push(0,j+1,j);const n=steps*rings;indices.push(n,n+j,n+j+1);}
  const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));g.setIndex(indices);g.computeVertexNormals();return g;
}

/** Five material batches, shared by every instance of a type. */
export function buildFighterAsset(kind:FighterKind, envMap:THREE.Texture|null=null):FighterAsset {
  const bins=new Map<Finish,THREE.BufferGeometry[]>();
  const add=(g:THREE.BufferGeometry,finish:Finish)=>{
    const flat=g.index?g.toNonIndexed():g.clone();g.dispose();flat.deleteAttribute('uv');
    const list=bins.get(finish)??[];list.push(flat);bins.set(finish,list);
  };
  const loft=(rows:Row[],finish:Finish='gold')=>add(shell(rows),finish);
  const jewel=(at:THREE.Vector3,scale:THREE.Vector3,finish:Finish='core')=>add(new THREE.SphereGeometry(1,16,10).scale(scale.x,scale.y,scale.z).translate(at.x,at.y,at.z),finish);
  const vein=(points:THREE.Vector3[],radius:number,finish:Finish='bronze')=>add(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(points),24,radius,5,false),finish);
  const mirrored=(rows:Row[],s:number):Row[]=>rows.map(([x,y,z,w,d])=>[x*s,y,z,w,d]);
  if(kind==='phoenix') {
    // Central armored teardrop and split forward mandibles, not a triangular hull.
    loft([[0,-.3,-19,.08,.12],[0,0,-11,3.3,1.6],[0,0,-2,5.3,2.3],[0,0,8,3.6,1.8],[0,0,17,.2,.3]]);
    loft([[0,-1,-14,.1,.1],[0,-1.1,-1,4.7,1.45],[0,-.9,11,2.6,.9],[0,0,18,.05,.1]],'bronze');
    for(const s of [-1,1]) {
      // Two broad, cambered sickle wings. Curving return tips leave open notches.
      const wing:Row[]=[[4,0,7,2.1,1.2],[11,.1,5,4.5,1.3],[19,.8,-1,4.2,1.05],[22,1.5,-10,2.6,.65],[19,2,-20,1,.35],[13,2.3,-27,.05,.04]];
      loft(mirrored(wing,s));
      loft(mirrored([[7,1.08,6,1.2,.15],[12,1.38,3,2.35,.2],[18,1.8,-3,2.4,.17],[20,2.15,-10,1.2,.12],[18,2.35,-17,.03,.03]],s),'inlay');
      vein([[6,1.55,5],[12,1.9,2],[17,2.3,-4],[18.8,2.6,-11]].map(p=>new THREE.Vector3(p[0]*s,p[1],p[2])),.12,'core');
      // Forked pointed beak enclosing the blue cockpit; aft spires flank drives.
      loft(mirrored([[2,0,-5,1.5,1.1],[3,0,-14,1.7,.9],[1.4,-.3,-24,.03,.04]],s));
      loft(mirrored([[5,-.6,3,1.9,1.2],[8,-.3,13,2.8,1.65],[8,.5,21,1.5,.85],[6.2,1,29,.04,.04]],s));
      loft(mirrored([[7,1.25,11,1.2,.18],[8,1.5,17,1,.2],[6.5,1.55,26,.03,.03]],s),'inlay');
      // Solid engine collars and compact three-dimensional ion tails.
      add(new THREE.TorusGeometry(1.25,.36,8,16).translate(s*7,-.65,17),'bronze');
      jewel(new THREE.Vector3(s*7,-.65,17.25),new THREE.Vector3(1.04,1.04,.35),'core');
      loft(mirrored([[7,-.65,17.5,.85,.85],[7,-.65,21,.6,.6],[7,-.65,26,.025,.025]],s),'engine');
      for(let j=0;j<3;j++)vein([[s*(4+j*.5),1.8,2+j*2],[s*(6+j*.7),1.45,4+j*2]].map(p=>new THREE.Vector3(...p as [number,number,number])),.13);
    }
    jewel(new THREE.Vector3(0,2,-5),new THREE.Vector3(2.15,1.25,3.65),'bronze');
    jewel(new THREE.Vector3(0,2.7,-5.2),new THREE.Vector3(1.55,.95,2.8),'core');
    loft([[0,1.8,-.6,.4,.4],[0,3.8,5,1.2,1.5],[0,3.3,10,.5,.7],[0,1.5,16,.04,.04]]);
  } else {
    // Void Ray: split armored forebody, exposed focusing crystal and upswept
    // paired drive nacelles. Distinct from the Phoenix crescent planform.
    loft([[0,0,-13,1.8,2.8],[0,0,-3,4,3.1],[0,0,7,3.7,2.7],[0,0,16,.2,.4]],'bronze');
    for(const s of [-1,1]) {
      loft(mirrored([[1.9,1.2,-25,.04,.04],[4,2,-16,2.1,2.1],[6,2.5,-4,3.6,2.3],[4,1.5,8,2.8,1.8],[2,1,15,.05,.05]],s));
      loft(mirrored([[3.2,3,-17,.05,.05],[5.2,4,-7,1.4,.25],[4.6,3.2,3,1.5,.3],[3.2,2.5,9,.05,.05]],s),'inlay');
      loft(mirrored([[3,0,1,1.2,1.1],[8,1,10,1.35,1.2],[11,5,17,1.65,1.5],[11,6,23,.6,.7]],s),'bronze');
      loft(mirrored([[11,5,11,.1,.1],[12,6,18,2.6,2],[12,7,27,2,1.7],[10,8,36,.04,.04]],s));
      loft(mirrored([[12,7.4,16,.1,.1],[12,8,23,1.2,.3],[10.8,8.5,32,.03,.03]],s),'inlay');
      jewel(new THREE.Vector3(s*11,5,18),new THREE.Vector3(1.5,1.5,1),'core');
      loft(mirrored([[11,5,21,1.1,1.1],[11,5,27,.9,.9],[11,5,32,.04,.04]],s),'engine');
      jewel(new THREE.Vector3(s*5.3,4.15,-2),new THREE.Vector3(1.15,.4,1.6),'core');
      vein([[s*3,3,-18],[s*5,4.4,-8],[s*5.7,4.9,-3]].map(p=>new THREE.Vector3(...p as [number,number,number])),.18);
    }
    add(new THREE.OctahedronGeometry(3.9).scale(.8,.9,1.9).translate(0,-.9,-20),'core');
    add(new THREE.TorusGeometry(3.6,.6,8,12).translate(0,-.9,-19),'gold');
    jewel(new THREE.Vector3(0,3,3),new THREE.Vector3(1.5,.8,2.6),'core');
  }
  const materials:Record<Finish,THREE.Material>={
    gold:new THREE.MeshStandardMaterial({color:0xb89a50,roughness:.56,metalness:.64,envMap,envMapIntensity:.7,emissive:0x6b5224,emissiveIntensity:.35}),
    bronze:new THREE.MeshStandardMaterial({color:0x57422a,roughness:.65,metalness:.55,envMap,envMapIntensity:.5}),
    inlay:new THREE.MeshStandardMaterial({color:0x17425c,roughness:.4,metalness:.42,emissive:0x096289,emissiveIntensity:.45}),
    core:new THREE.MeshBasicMaterial({color:0x5bc6ed,toneMapped:false}),
    engine:new THREE.MeshBasicMaterial({color:0x268bd1,transparent:true,opacity:.48,depthWrite:false,toneMapped:false}),
  };
  const parts:FighterAsset['parts']=[];
  const bounds=new THREE.Box3();
  for(const [finish,list] of bins) {
    const geometry=mergeGeometries(list,false)!;for(const g of list)g.dispose();
    geometry.computeBoundingBox();bounds.union(geometry.boundingBox!);parts.push({geometry,material:materials[finish],finish});
  }
  const length=bounds.max.z-bounds.min.z,center=bounds.getCenter(new THREE.Vector3());
  for(const part of parts) {
    part.geometry.translate(-center.x,-center.y,-center.z).scale(1/length,1/length,1/length);
    part.geometry.computeBoundingBox();part.geometry.computeBoundingSphere();
  }
  let disposed=false;
  return {parts,dispose(){if(disposed)return;disposed=true;for(const p of parts)p.geometry.dispose();for(const m of Object.values(materials))m.dispose();}};
}
