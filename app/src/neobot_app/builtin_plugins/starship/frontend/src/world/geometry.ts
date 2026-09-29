import * as THREE from 'three';
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';
export type Point = [number, number, number];
/** Static geometry batches: one draw call per material, without losing mesh culling. */
export class Architecture {
  private batches = new Map<THREE.Material, THREE.BufferGeometry[]>();
  constructor(readonly root: THREE.Group) {}
  add(g: THREE.BufferGeometry, material: THREE.Material): void {
    if (g.index) { const unindexed = g.toNonIndexed(); g.dispose(); g = unindexed; }
    g.deleteAttribute('uv');
    const batch = this.batches.get(material) ?? [];
    batch.push(g); this.batches.set(material, batch);
  }
  box(size: Point, at: Point, material: THREE.Material): void {
    this.add(new THREE.BoxGeometry(...size).translate(...at), material);
  }
  curve(points: Point[], radius: number, material: THREE.Material, segments = 36): void {
    this.add(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(points.map(p => new THREE.Vector3(...p))), segments, radius, 6, false), material);
  }
  /** Bevelled silhouette plate in XY; depth gives ribs readable carved edges. */
  plate(shape: THREE.Shape, depth: number, at: Point, material: THREE.Material, mirror = false): void {
    const g=new THREE.ExtrudeGeometry(shape,{depth,bevelEnabled:true,bevelThickness:Math.min(.12,depth*.25),bevelSize:.12,bevelSegments:3,steps:1,curveSegments:24});
    if(mirror) { g.scale(-1,1,1); const index=g.index;
      if(index) for(let i=0;i<index.count;i+=3){const b=index.getX(i+1);index.setX(i+1,index.getX(i+2));index.setX(i+2,b);}
      else {const p=g.attributes.position,n=g.attributes.normal,uv=g.attributes.uv;
        for(let i=0;i<p.count;i+=3) for(const attr of [p,n,uv]) if(attr) for(let k=0;k<attr.itemSize;k++) {
          const arr=attr.array;const j=(i+1)*attr.itemSize+k,l=(i+2)*attr.itemSize+k,t=arr[j];arr[j]=arr[l];arr[l]=t;
        }
      }
    }
    g.translate(...at);this.add(g,material);
  }
  ring(radius: number, tube: number, at: Point, material: THREE.Material, vertical = false): void {
    const g = new THREE.TorusGeometry(radius, tube, 6, 80);
    if (!vertical) g.rotateX(Math.PI / 2);
    g.translate(...at); this.add(g, material);
  }
  /** A faceted, closed variable-section armour blade, with actual negative space between blades. */
  blade(sections: [number, number, number, number, number][], material: THREE.Material): void {
    const vertices: number[] = [], indices: number[] = [], n = 24;
    for (const [x,y,z,w,h] of sections) for (let i=0;i<n;i++) {
      const a=i/n*Math.PI*2; vertices.push(x+Math.cos(a)*w,y+Math.sin(a)*h,z);
    }
    for(let j=0;j<sections.length-1;j++) for(let i=0;i<n;i++) {
      const a=j*n+i,b=j*n+(i+1)%n,c=a+n,d=b+n; indices.push(a,b,c,b,d,c);
    }
    for(let i=1;i<n-1;i++) { indices.push(0,i+1,i); const e=(sections.length-1)*n; indices.push(e,e+i,e+i+1); }
    const g=new THREE.BufferGeometry(); g.setAttribute('position',new THREE.Float32BufferAttribute(vertices,3)); g.setIndex(indices); g.computeVertexNormals(); this.add(g,material);
  }
  finish(): void {
    for(const [material,geometries] of this.batches) {
      const g=mergeGeometries(geometries,false);
      for(const source of geometries) source.dispose();
      if(g) this.root.add(new THREE.Mesh(g,material));
    }
    this.batches.clear();
  }
}
