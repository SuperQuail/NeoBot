import * as THREE from 'three';
import { Architecture, type Point } from './geometry';
import { applyAlloyFinish } from './materials';

/** Dedicated static walker sculpture: cross sections, not stretched primitive bodies. */
export type Section = [x: number, y: number, z: number, halfWidth: number, halfDepth: number];
export class UnitSculpt {
  readonly root = new THREE.Group();
  readonly a = new Architecture(this.root);
  readonly owned: THREE.Material[] = [];

  metal(base: THREE.MeshStandardMaterial, color: number, name: string): THREE.MeshStandardMaterial {
    const m = base.clone(); m.name = name; m.color.setHex(color);
    applyAlloyFinish(m, { scale: 5, colourVariation: .045, roughnessVariation: .09, relief: .000025 });
    this.owned.push(m); return m;
  }

  frame(at: Point, normal: Point, up: Point = [0, 1, 0]): THREE.Matrix4 {
    const z = new THREE.Vector3(...normal).normalize();
    const x = new THREE.Vector3(...up).cross(z).normalize();
    return new THREE.Matrix4().makeBasis(x, z.clone().cross(x), z).setPosition(...at);
  }

  /** Smooth variable-section loft. Partial sectors have real inner surfaces and
   * closed rolled edges; their dark gaps are geometry, not painted lines. */
  shell(stations: Section[], mat: THREE.Material, transform = new THREE.Matrix4(),
    start = 0, end = Math.PI * 2, thickness = .075, facets = 40, sectionPower = 1): void {
    const full = end - start > Math.PI * 1.999;
    const sections: Section[] = [];
    const cubic = (a: number,b: number,c: number,d: number,t: number) =>
      .5 * ((2*b)+(-a+c)*t+(2*a-5*b+4*c-d)*t*t+(-a+3*b-3*c+d)*t*t*t);
    for (let j=0;j<stations.length-1;j++) for (let k=0;k<5;k++) {
      const t=k/5, s=stations[j].map((_,i)=>cubic(stations[Math.max(0,j-1)][i],stations[j][i],
        stations[j+1][i],stations[Math.min(stations.length-1,j+2)][i],t)) as Section;
      s[3]=Math.max(.005,s[3]); s[4]=Math.max(.005,s[4]); sections.push(s);
    }
    sections.push(stations[stations.length-1]);
    const n=Math.max(8,Math.ceil(facets*(end-start)/(Math.PI*2))), stride=n+1;
    const p:number[]=[], idx:number[]=[];
    for(let layer=0;layer<(full?1:2);layer++) for(const [x,y,z,w,d] of sections) for(let i=0;i<=n;i++) {
      const t=start+(end-start)*i/n, inset=layer*thickness;
      const sn=Math.sin(t),cs=Math.cos(t);
      p.push(x+Math.sign(sn)*Math.pow(Math.abs(sn),sectionPower)*Math.max(.004,w-inset),y,
        z+Math.sign(cs)*Math.pow(Math.abs(cs),sectionPower)*Math.max(.004,d-inset));
    }
    const sheet=sections.length*stride;
    for(let layer=0;layer<(full?1:2);layer++) for(let j=0;j<sections.length-1;j++) for(let i=0;i<n;i++) {
      const a=layer*sheet+j*stride+i,b=a+1,c=a+stride;
      if(layer===0) idx.push(a,b,c,b,c+1,c); else idx.push(a,c,b,b,c,c+1);
    }
    if(full) {
      const b=(sections.length-1)*stride;
      for(let i=1;i<n-1;i++) idx.push(0,i+1,i,b,b+i,b+i+1);
    } else {
      for(let j=0;j<sections.length-1;j++) for(const i of [0,n]) {
        const a=j*stride+i,b=a+stride;
        if(i===0) idx.push(a,b,a+sheet,b,b+sheet,a+sheet);
        else idx.push(a,a+sheet,b,b,a+sheet,b+sheet);
      }
      for(let i=0;i<n;i++) for(const j of [0,sections.length-1]) {
        const a=j*stride+i,b=a+1;
        if(j===0) idx.push(a,a+sheet,b,b,a+sheet,b+sheet);
        else idx.push(a,b,a+sheet,b,b+sheet,a+sheet);
      }
    }
    const g=new THREE.BufferGeometry(); g.setAttribute('position',new THREE.Float32BufferAttribute(p,3));
    g.setIndex(idx);g.computeVertexNormals();this.a.add(g.applyMatrix4(transform),mat);
  }

  line(points: Point[], radius: number, mat: THREE.Material): void {
    this.a.curve(points,radius,mat,Math.max(12,points.length*7));
  }

  /** Curved solid armour/tendon along an arbitrary limb, with a lenticular section. */
  limb(from: Point,to: Point,normal: Point,profile: [number,number,number,number][],mat: THREE.Material, armored=false): void {
    const v=new THREE.Vector3(...to).sub(new THREE.Vector3(...from)),length=v.length();
    const up=v.normalize(),n=new THREE.Vector3(...normal);n.addScaledVector(up,-up.dot(n)).normalize();
    const m=this.frame(from,n.toArray() as Point,up.toArray() as Point);
    this.shell(profile.map(([t,w,d,bow])=>[0,t*length,bow,w,d]),mat,m,
      armored?-1.92:0,armored?1.92:Math.PI*2,.07,32,armored?.64:1);
  }

  plate(shape: THREE.Shape, mat: THREE.Material, transform: THREE.Matrix4, depth=.10): void {
    const g=new THREE.ExtrudeGeometry(shape,{depth,steps:1,bevelEnabled:true,bevelSize:.028,
      bevelThickness:.023,bevelSegments:3,curveSegments:20});
    this.a.add(g.applyMatrix4(transform),mat);
  }

  optic(at: Point,normal: Point,width: number,height: number,edge: THREE.Material,
    dark: THREE.Material,glass: THREE.Material,glow: THREE.Material): void {
    const m=this.frame(at,normal);
    const add=(g:THREE.BufferGeometry,mat:THREE.Material)=>this.a.add(g.applyMatrix4(m),mat);
    add(new THREE.CylinderGeometry(1,1,.09,32).rotateX(Math.PI/2).scale(width*1.22,height*1.18,1),dark);
    add(new THREE.TorusGeometry(1,.105,8,48).scale(width,height,.6).translate(0,0,.035),edge);
    add(new THREE.SphereGeometry(1,28,16).scale(width*.88,height*.89,.075).translate(0,0,.034),glass);
    add(new THREE.TorusGeometry(1,.025,6,40).scale(width*.77,height*.80,.5).translate(0,0,.103),glow);
  }

  joint(at: Point,axis: Point,r: number,edge: THREE.Material,dark: THREE.Material,glass: THREE.Material): void {
    const m=this.frame(at,axis), add=(g:THREE.BufferGeometry,mat:THREE.Material)=>this.a.add(g.applyMatrix4(m),mat);
    add(new THREE.CylinderGeometry(r,r,.22,24).rotateX(Math.PI/2),dark);
    add(new THREE.TorusGeometry(r*.79,r*.11,8,32).translate(0,0,.12),edge);
    add(new THREE.CylinderGeometry(r*.44,r*.44,.045,16).rotateX(Math.PI/2).translate(0,0,.135),glass);
    for(let i=0;i<5;i++) {const t=i*Math.PI*2/5;
      add(new THREE.CylinderGeometry(.023,.023,.025,8).rotateX(Math.PI/2)
        .translate(Math.cos(t)*r*.77,Math.sin(t)*r*.77,.15),dark);
    }
  }

  finish(kind:'stalker'|'dragoon',height:number,maxWidth:number,maxDepth:number): THREE.Group {
    this.a.finish();
    const bounds=new THREE.Box3().setFromObject(this.root),size=bounds.getSize(new THREE.Vector3());
    // The Dragoon is a low, broad crawler, not the Stalker's taller spider stance.
    const sy=height/size.y,stance=kind==='dragoon'?1.12:1;
    const sx=Math.min(sy*stance,maxWidth/size.x),sz=Math.min(sy*stance,maxDepth/size.z);
    const center=bounds.getCenter(new THREE.Vector3());
    const m=new THREE.Matrix4().makeScale(sx,sy,sz).setPosition(-center.x*sx,-bounds.min.y*sy,-center.z*sz);
    this.root.traverse(o=>{if(o instanceof THREE.Mesh){o.geometry.applyMatrix4(m);o.geometry.computeBoundingBox();
      o.geometry.computeBoundingSphere();o.castShadow=true;o.receiveShadow=true;o.name=kind+'-'+o.material.name;}});
    this.root.name='protoss-'+kind;
    this.root.userData={unitKind:kind,label:kind==='stalker'?'追猎者':'龙骑士',forwardAxis:'-z',
      ownedMaterials:this.owned,displayDimensions:[size.x*sx,height,size.z*sz]};
    return this.root;
  }
}
