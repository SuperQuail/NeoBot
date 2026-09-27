import * as THREE from 'three';
import { Architecture, type Point } from './geometry';

/** A station describes a CHINED structural shell, never an elliptical leaf.
 * x, y, z, half breadth, dorsal rise, ventral depth, transverse bank. */
export type HullStation = [number, number, number, number, number, number, number];
const profile = [[1,0],[.98,.20],[.86,.68],[.67,.89],[-.43,1],[-.79,.77],[-.97,.20],[-1,0],[-.89,-.72],[-.50,-1],[.58,-.92],[.91,-.60],[1,0]];

/** Loft with convex shoulders and a deep asymmetric section. Separate armour
 * patches sit above a continuous recessed substrate; gaps expose real channel
 * floors and sidewalls. Negative space BETWEEN structural shells stays empty. */
export function sculptShell(a: Architecture, stations: HullStation[], side: number, substrate: THREE.Material) {
  const sample = (t: number): HullStation => {
    const f=THREE.MathUtils.clamp(t,0,1)*(stations.length-1), i=Math.min(stations.length-2,Math.floor(f)), u=f-i;
    return stations[i].map((v,k)=>{
      if(k===2) return THREE.MathUtils.lerp(v,stations[i+1][k],u);
      const prev=stations[Math.max(0,i-1)][k],next=stations[i+1][k],after=stations[Math.min(stations.length-1,i+2)][k];
      const value=(2*u*u*u-3*u*u+1)*v+(u*u*u-2*u*u+u)*(next-prev)*.35+(-2*u*u*u+3*u*u)*next+(u*u*u-u*u)*(after-v)*.35;
      return k>=3&&k<=5 ? Math.max(.08,value) : value;
    }) as HullStation;
  };
  const point = (t: number, u: number, lift=0): THREE.Vector3 => {
    const [x,y,z,w,h,d,bank]=sample(t), p=THREE.MathUtils.clamp(u,0,1)*12,i=Math.min(11,Math.floor(p)),f=p-i;
    const px=THREE.MathUtils.lerp(profile[i][0],profile[i+1][0],f),py=THREE.MathUtils.lerp(profile[i][1],profile[i+1][1],f);
    return new THREE.Vector3(side*(x+px*(w+lift)),y+py*((py>=0?h:d)+lift)+px*w*bank,z);
  };
  const mesh = (t0: number,t1: number,u0: number,u1: number,lift: number,material: THREE.Material, closed: boolean): void => {
    // All laminations share the substrate's station grid and exact chine lines.
    // Arbitrary per-patch grids crossed sharp corners and produced sawtooth seams.
    const sorted=(values:number[])=>values.sort((a,b)=>a-b).filter((v,i,all)=>i===0||v-all[i-1]>1e-7);
    const steps=(stations.length-1)*7;
    const ts=sorted([t0,t1,...Array.from({length:steps+1},(_,i)=>i/steps).filter(t=>t>t0&&t<t1)]);
    if(ts.length<4)ts.splice(1,0,THREE.MathUtils.lerp(t0,t1,1/3),THREE.MathUtils.lerp(t0,t1,2/3));
    const us=sorted([u0,u1,...Array.from({length:37},(_,i)=>i/36).filter(u=>u>u0&&u<u1)]);
    if(us.length<4)us.splice(1,0,THREE.MathUtils.lerp(u0,u1,1/3),THREE.MathUtils.lerp(u0,u1,2/3));
    ts.sort((a,b)=>a-b);us.sort((a,b)=>a-b);
    const nt=ts.length-1,nu=us.length-1;
    const vertices:number[]=[],indices:number[]=[];
    const vertex=(p:THREE.Vector3)=>{vertices.push(p.x,p.y,p.z);return vertices.length/3-1;};
    const tri=(x:number,y:number,z:number)=>{if(side<0) indices.push(x,z,y);else indices.push(x,y,z);};
    for(let i=0;i<=nt;i++) for(let j=0;j<=nu;j++) {
      // Bevel the patch back down toward its inset channel floor at all edges.
      const bevel=closed?1:Math.min(1,i/1.15,(nt-i)/1.15,j/1.1,(nu-j)/1.1);
      vertex(point(ts[i],us[j],lift*(.25+.75*bevel)));
    }
    for(let i=0;i<nt;i++)for(let j=0;j<nu;j++){
      const q=i*(nu+1)+j;tri(q,q+1,q+nu+1);tri(q+1,q+nu+2,q+nu+1);
    }
    if(closed){
      for(const end of [0,nt]){
        const [x,y,z]=sample(end===0?t0:t1);const c=vertex(new THREE.Vector3(side*x,y,z));
        for(let j=0;j<nu;j++){const q=end*(nu+1)+j;if(end===0)tri(c,q+1,q);else tri(c,q,q+1);}
      }
    } else {
      // Physical skirt walls make relief a solid lamination, not floating decals.
      const border:number[]=[];
      for(let j=0;j<=nu;j++)border.push(j);
      for(let i=1;i<=nt;i++)border.push(i*(nu+1)+nu);
      for(let j=nu-1;j>=0;j--)border.push(nt*(nu+1)+j);
      for(let i=nt-1;i>0;i--)border.push(i*(nu+1));
      for(let k=0;k<border.length;k++){
        const q=border[k],r=border[(k+1)%border.length];
        const floor=(id:number)=>point(ts[Math.floor(id/(nu+1))],us[id%(nu+1)],-.12);
        const b=vertex(floor(q)),c=vertex(floor(r));tri(q,b,r);tri(r,b,c);
      }
    }
    const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(vertices,3));g.setIndex(indices);g.computeVertexNormals();
    // Retain longitudinal curvature, but do not average the hard transverse
    // shoulder into a pillow. Evaluate each triangle corner on its own chine.
    const result=g.toNonIndexed(),normals=result.getAttribute('normal');
    const surfaceIndexCount=nt*nu*6;
    for(let face=0;face<surfaceIndexCount;face+=3){
      const js=[indices[face],indices[face+1],indices[face+2]].map(id=>id%(nu+1));
      const midU=(us[js[0]]+us[js[1]]+us[js[2]])/3;
      const facet=Math.min(11,Math.floor(midU*12));
      for(let corner=0;corner<3;corner++){
        const id=indices[face+corner],i=Math.floor(id/(nu+1)),j=id%(nu+1);
        if(!closed&&(i<2||i>nt-2||j<2||j>nu-2))continue; // preserve physical bevel normals
        const t=ts[i],u=us[j];
        const along=point(Math.min(1,t+.001),u,lift).sub(point(Math.max(0,t-.001),u,lift));
        const across=point(t,(facet+1)/12,lift).sub(point(t,facet/12,lift));
        const n=across.cross(along).multiplyScalar(side).normalize();normals.setXYZ(face+corner,n.x,n.y,n.z);
      }
    }
    g.dispose();a.add(result,material);
  };
  mesh(0,1,0,1,0,substrate,true);
  return {
    point:(t:number,u:number,lift=0):Point=>point(t,u,lift).toArray() as Point,
    panel:(t0:number,t1:number,u0:number,u1:number,lift:number,material:THREE.Material)=>mesh(t0,t1,u0,u1,lift,material,false),
  };
}
