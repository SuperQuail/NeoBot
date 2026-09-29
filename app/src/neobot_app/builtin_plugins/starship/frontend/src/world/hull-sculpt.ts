import * as THREE from 'three';
import { Architecture, type Point } from './geometry';

/** Solid, folded inset web. These are structural infill surfaces, not emissive
 * lines: the rim, bevel, recessed field and back skin all have real thickness.
 * Points must describe a convex perimeter; non-coplanar corners make a fold. */
export function hullWeb(a: Architecture, corners: Point[], thickness: number,
  rim: THREE.Material, field: THREE.Material, back: THREE.Material): void {
  const outer=corners.map(p=>new THREE.Vector3(...p));
  const center=outer.reduce((sum,p)=>sum.add(p),new THREE.Vector3()).multiplyScalar(1/outer.length);
  const normal=outer[1].clone().sub(outer[0]).cross(outer[2].clone().sub(outer[0])).normalize();
  const inner=outer.map(p=>p.clone().lerp(center,.14).addScaledVector(normal,-thickness*.22));
  const rear=outer.map(p=>p.clone().addScaledVector(normal,-thickness));
  const innerRear=outer.map(p=>p.clone().lerp(center,.14).addScaledVector(normal,-thickness*.78));
  const emit=(vertices:THREE.Vector3[],material:THREE.Material)=>{
    const g=new THREE.BufferGeometry();
    g.setAttribute('position',new THREE.Float32BufferAttribute(vertices.flatMap(p=>p.toArray()),3));
    g.computeVertexNormals(); a.add(g,material);
  };
  const edges:THREE.Vector3[]=[],skin:THREE.Vector3[]=[],underside:THREE.Vector3[]=[];
  const inset=center.clone().addScaledVector(normal,-thickness*.22);
  const bottom=center.clone().addScaledVector(normal,-thickness*.78);
  for(let i=0;i<outer.length;i++){
    const j=(i+1)%outer.length;
    edges.push(outer[i],outer[j],inner[j],outer[i],inner[j],inner[i]);
    edges.push(outer[j],outer[i],rear[i],outer[j],rear[i],rear[j]);
    skin.push(inner[i],inner[j],inset);
    // The back is also an inset field bounded by metal, not a solid blue card.
    edges.push(rear[j],rear[i],innerRear[i],rear[j],innerRear[i],innerRear[j]);
    underside.push(innerRear[j],innerRear[i],bottom);
  }
  emit(edges,rim); emit(skin,field); emit(underside,back);
}
