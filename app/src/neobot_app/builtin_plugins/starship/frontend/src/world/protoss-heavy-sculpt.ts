/** Private sculpting toolkit for the two heavy Khalai machines.
 * Continuous shaped armor volumes, tessellated cambered skins, radiused plate
 * boundaries and separate mechanical bearings. No spheres used as body armor. */
import * as THREE from 'three';
import { mergeGeometries, toCreasedNormals } from 'three/addons/utils/BufferGeometryUtils.js';
import { TessellateModifier } from 'three/addons/modifiers/TessellateModifier.js';
import type { ShipMaterials } from './materials';
export type V3 = [number, number, number];
export type V2 = [number, number];
export type Finish = 'gold' | 'edge' | 'bronze' | 'dark' | 'blue' | 'glow' | 'steel';
export interface Section { y: number; w: number; d: number; x?: number; z?: number }
export interface SweepSection { p: V3; w: number; d: number }

/** Four broad faces joined by radiused chamfers, not an inflated sphere. */
function sectional(sections: Section[]): THREE.BufferGeometry {
  const cross: V2[] = [];
  // Corner radii consume only the outside 36%; the primary flats stay flat.
  for (let corner=0;corner<4;corner++) {
    const a=corner*Math.PI/2;
    const cx=Math.cos(a+Math.PI/4)>0?.64:-.64,cz=Math.sin(a+Math.PI/4)>0?.64:-.64;
    for(let j=0;j<=4;j++) {const angle=a+j*Math.PI/8;cross.push([cx+.36*Math.cos(angle),cz+.36*Math.sin(angle)]);}
  }
  const count=cross.length;
  const vertices: number[] = [], index: number[] = [];
  for (const s of sections) for (const [x,z] of cross) vertices.push((s.x ?? 0)+x*s.w,s.y,(s.z ?? 0)+z*s.d);
  for (let i=0;i<sections.length-1;i++) for(let j=0;j<count;j++) {
    const a=i*count+j,b=i*count+(j+1)%count,c=a+count,d=b+count;
    index.push(a,c,b,b,c,d);
  }
  for(let j=1;j<count-1;j++) { index.push(0,j,j+1); const a=(sections.length-1)*count;index.push(a,a+j+1,a+j); }
  const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(vertices,3));g.setIndex(index);
  g.computeVertexNormals(); const creased=toCreasedNormals(g, .50);g.dispose();return creased;
}

export class HeavySculpt {
  private readonly batches = new Map<Finish, THREE.BufferGeometry[]>();
  private readonly finishes: Record<Finish, THREE.Material>;
  constructor(materials: ShipMaterials) {
    const alloy=(color:number,roughness:number,metalness:number)=>new THREE.MeshStandardMaterial({color,roughness,metalness,
      envMap:materials.hull.envMap,envMapIntensity:.85});
    this.finishes={
      gold:alloy(0xb49a60,.39,.68),edge:alloy(0xe0cb93,.31,.7),bronze:alloy(0x77603c,.44,.65),
      dark:alloy(0x17202b,.47,.45),steel:alloy(0x747984,.32,.76),
      blue:new THREE.MeshPhysicalMaterial({color:0x153f62,emissive:0x064f75,emissiveIntensity:.40,roughness:.23,metalness:.38,clearcoat:.7,clearcoatRoughness:.18}),
      glow:new THREE.MeshBasicMaterial({color:0x59dafa,toneMapped:false}),
    };
  }
  add(g:THREE.BufferGeometry,finish:Finish,p:V3=[0,0,0],r:V3=[0,0,0],s:V3=[1,1,1]):void {
    const flat=g.index?g.toNonIndexed():g.clone();g.dispose();flat.deleteAttribute('uv');
    flat.applyMatrix4(new THREE.Matrix4().compose(new THREE.Vector3(...p),new THREE.Quaternion().setFromEuler(new THREE.Euler(...r)),new THREE.Vector3(...s)));
    const list=this.batches.get(finish)??[];list.push(flat);this.batches.set(finish,list);
  }
  loft(sections:Section[],finish:Finish,p:V3=[0,0,0],r:V3=[0,0,0]):void {this.add(sectional(sections),finish,p,r);}
  /** Continuous sculpted armor volume with broad subtly flattened faces. Width,
   * thickness and centerline are independently controlled, avoiding inflated balls. */
  shell(rows:SweepSection[],finish:Finish,face:V3=[0,0,-1],steps=36,sides=32):void {
    const curve=new THREE.CatmullRomCurve3(rows.map(s=>new THREE.Vector3(...s.p)),false,'centripetal');
    const radii=new THREE.CatmullRomCurve3(rows.map((s,i)=>new THREE.Vector3(s.w,s.d,i)),false,'catmullrom',.35);
    const vertices:number[]=[],indices:number[]=[];
    for(let i=0;i<=steps;i++) {
      const t=i/steps,p=curve.getPoint(t),tangent=curve.getTangent(t).normalize(),rd=radii.getPoint(t);
      let normal=new THREE.Vector3(...face);if(Math.abs(normal.dot(tangent))>.97)normal=new THREE.Vector3(1,0,0);
      const across=normal.clone().cross(tangent).normalize();normal=tangent.clone().cross(across).normalize();
      for(let j=0;j<sides;j++) {
        const angle=j/sides*Math.PI*2,c=Math.cos(angle),s=Math.sin(angle);
        const x=Math.sign(c)*Math.pow(Math.abs(c),.83),z=Math.sign(s)*Math.pow(Math.abs(s),.83);
        const v=p.clone().addScaledVector(across,x*Math.max(.005,rd.x)).addScaledVector(normal,z*Math.max(.005,rd.y));vertices.push(v.x,v.y,v.z);
      }
    }
    for(let i=0;i<steps;i++)for(let j=0;j<sides;j++){const a=i*sides+j,b=i*sides+(j+1)%sides;indices.push(a,b,a+sides,b,b+sides,a+sides);}
    const first=vertices.length/3;vertices.push(...rows[0].p,...rows[rows.length-1].p);
    for(let j=0;j<sides;j++){indices.push(first,(j+1)%sides,j);indices.push(first+1,steps*sides+j,steps*sides+(j+1)%sides);}
    const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(vertices,3));geometry.setIndex(indices);geometry.computeVertexNormals();this.add(geometry,finish);
  }
  /** Thick tessellated panel with sculpted camber. Rounded perimeter plus a shallow
   * double curvature gives a real armor skin rather than a flat hanging badge. */
  curvedPlate(outline:V2[],depth:number,finish:Finish,p:V3,r:V3=[0,0,0],bevel=.07,camber:V3=[0,0,0]):void {
    const points=outline.map(v=>new THREE.Vector3(v[0],v[1],0));
    const curve=new THREE.CatmullRomCurve3(points,true,'centripetal');
    const shape=new THREE.Shape(curve.getPoints(outline.length*5).map(v=>new THREE.Vector2(v.x,v.y)));
    const base=new THREE.ExtrudeGeometry(shape,{depth,steps:1,bevelEnabled:true,bevelThickness:bevel,bevelSize:bevel,bevelSegments:3,curveSegments:1});
    base.translate(0,0,-depth/2);
    const tessellated=new TessellateModifier(.44,5).modify(base);base.dispose();
    const position=tessellated.getAttribute('position');
    for(let i=0;i<position.count;i++){const x=position.getX(i),y=position.getY(i);position.setZ(i,position.getZ(i)+camber[0]*x*x+camber[1]*y*y+camber[2]*y);}
    tessellated.computeVertexNormals();const rounded=toCreasedNormals(tessellated,.72);tessellated.dispose();this.add(rounded,finish,p,r);
  }
  /** Bevel is actual geometry, not a painted outline. The face remains planar. */
  plate(outline:V2[],depth:number,finish:Finish,p:V3=[0,0,0],r:V3=[0,0,0],bevel=.06):void {
    const shape=new THREE.Shape(outline.map(v=>new THREE.Vector2(...v)));shape.closePath();
    const g=new THREE.ExtrudeGeometry(shape,{depth,steps:1,bevelEnabled:bevel>0,bevelThickness:bevel,bevelSize:bevel,bevelSegments:3,curveSegments:1});
    g.translate(0,0,-depth/2);const rounded=toCreasedNormals(g,.50);g.dispose();this.add(rounded,finish,p,r);
  }
  block(p:V3,size:V3,finish:Finish,r:V3=[0,0,0],bevel=.04):void {
    const [x,y,z]=size;const c=Math.min(x,y)*.12;
    this.plate([[-x/2+c,-y/2],[x/2-c,-y/2],[x/2,-y/2+c],[x/2,y/2-c],[x/2-c,y/2],[-x/2+c,y/2],[-x/2,y/2-c],[-x/2,-y/2+c]],z,finish,p,r,bevel);
  }
  /** A straight tapered armor section; callers leave joint gaps between sections. */
  strut(a:V3,b:V3,widthA:number,widthB:number,depthA:number,depthB:number,finish:Finish):void {
    const va=new THREE.Vector3(...a),vb=new THREE.Vector3(...b),delta=vb.clone().sub(va),length=delta.length();
    const g=sectional([{y:0,w:widthA*.85,d:depthA*.85},{y:Math.min(.12,length*.08),w:widthA,d:depthA},
      {y:length-Math.min(.12,length*.08),w:widthB,d:depthB},{y:length,w:widthB*.85,d:depthB*.85}]);
    g.applyQuaternion(new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0,1,0),delta.normalize()));g.translate(...a);this.add(g,finish);
  }
  /** Dark joint drum / metal collar, default axis Z. */
  drum(p:V3,radius:number,depth:number,finish:Finish,r:V3=[Math.PI/2,0,0],s:V3=[1,1,1]):void {
    this.add(new THREE.CylinderGeometry(radius,radius,depth,16,1),finish,p,r,s);
  }
  ring(p:V3,radius:number,thickness:number,finish:Finish,r:V3=[0,0,0],s:V3=[1,1,1],arc=Math.PI*2):void {
    this.add(new THREE.TorusGeometry(radius,thickness,4,32,arc),finish,p,r,s);
  }
  /** Angular recessed graphics/vents, deliberately not free-standing round tubes. */
  line(points:V3[],width:number,finish:Finish):void {
    for(let i=1;i<points.length;i++) {
      const a=new THREE.Vector3(...points[i-1]),b=new THREE.Vector3(...points[i]),delta=b.clone().sub(a);
      const geometry=new THREE.BoxGeometry(width*2,delta.length(),width*.9);
      geometry.applyQuaternion(new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0,1,0),delta.normalize()));
      const center=a.add(b).multiplyScalar(.5);geometry.translate(center.x,center.y,center.z);this.add(geometry,finish);
    }
  }
  surfaceLine(points:V2[],p:V3,r:V3,camber:V3,offset:number,width:number,finish:Finish):void {
    const curve=new THREE.CatmullRomCurve3(points.map(([x,y])=>new THREE.Vector3(x,y,0)));
    const rotation=new THREE.Euler(...r),origin=new THREE.Vector3(...p);
    this.line(curve.getPoints(16).map(v=>{
      v.z=offset+camber[0]*v.x*v.x+camber[1]*v.y*v.y+camber[2]*v.y;
      v.applyEuler(rotation).add(origin);return [v.x,v.y,v.z] as V3;
    }),width,finish);
  }
  /** Bake a mild upper-body pitch without shifting the four grounded contacts. */
  leanAbove(hinge:number,slope:number):void {
    for(const list of this.batches.values())for(const geometry of list) {
      const position=geometry.getAttribute('position'),normal=geometry.getAttribute('normal');
      for(let i=0;i<position.count;i++)if(position.getY(i)>hinge) {
        position.setZ(i,position.getZ(i)-slope*(position.getY(i)-hinge));
        const n=new THREE.Vector3(normal.getX(i),normal.getY(i)+slope*normal.getZ(i),normal.getZ(i)).normalize();
        normal.setXYZ(i,n.x,n.y,n.z);
      }
    }
  }
  finish(kind:string,label:string,height:number,width:number,depth:number,feetRadius:number,radius=Infinity):THREE.Group {
    const group=new THREE.Group();group.name='protoss-'+kind;
    Object.assign(group.userData,{unitKind:kind,label,forward:'-Z',ownsResources:true});
    for(const [finish,list] of this.batches) {
      const geometry=mergeGeometries(list,false);list.forEach(g=>g.dispose());
      if(!geometry) throw new Error('Heavy geometry merge failed: '+kind);
      const mesh=new THREE.Mesh(geometry,this.finishes[finish]);mesh.name=kind+'-'+finish;mesh.castShadow=true;mesh.receiveShadow=true;group.add(mesh);
    }
    for(const key of Object.keys(this.finishes) as Finish[]) if(!this.batches.has(key))this.finishes[key].dispose();
    const box=new THREE.Box3().setFromObject(group),size=box.getSize(new THREE.Vector3());
    const sx=Math.min(1,width/size.x),sy=height/size.y,sz=Math.min(1,depth/size.z);
    const matrix=new THREE.Matrix4().makeScale(sx,sy,sz);
    matrix.setPosition(-(box.max.x+box.min.x)*sx/2,-box.min.y*sy,-(box.max.z+box.min.z)*sz/2);
    let maxR=0,footR=0;
    for(const child of group.children) {
      const geometry=(child as THREE.Mesh).geometry;geometry.applyMatrix4(matrix);
      const pos=geometry.getAttribute('position');
      for(let i=0;i<pos.count;i++) {
        const r=Math.hypot(pos.getX(i),pos.getZ(i));maxR=Math.max(maxR,r);
        if(pos.getY(i)<.6)footR=Math.max(footR,r);
      }
    }
    // Leave a tiny float32 margin so a boundary toe cannot round outside the plinth.
    const fit=Math.min(1,(radius-1e-4)/maxR,(feetRadius-1e-4)/footR);
    for(const child of group.children) {
      const geometry=(child as THREE.Mesh).geometry;geometry.scale(fit,1,fit);geometry.computeBoundingBox();geometry.computeBoundingSphere();
    }
    return group;
  }
}
