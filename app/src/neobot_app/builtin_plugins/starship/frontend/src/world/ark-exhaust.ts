import * as THREE from 'three';

/** Normalized hull LOCAL coordinates, before hull.scale / hull.position. */
export interface ArkEngineExhaust {
  position:[number,number,number];
  direction:[number,number,number];
  radius:number;
}
export interface ArkExhaust {
  group:THREE.Group;
  readonly metadataReady:boolean;
  update(dt:number,power?:number):void;
  dispose():void;
}

/** Closed volume of revolution, +Z exhaust direction. Not sprites or cards. */
function plumeGeometry():THREE.BufferGeometry {
  const vertices:number[]=[],uv:number[]=[],index:number[]=[],rings=32,sides=24;
  for(let i=0;i<=rings;i++) {
    const t=i/rings;
    const radius=Math.max(.001,(.72+.32*Math.sin(Math.min(1,t*2)*Math.PI))*Math.pow(Math.max(0,1-t),.7));
    for(let j=0;j<=sides;j++) {
      const angle=j/sides*Math.PI*2;vertices.push(Math.cos(angle)*radius,Math.sin(angle)*radius,t);uv.push(j/sides,t);
    }
  }
  for(let i=0;i<rings;i++)for(let j=0;j<sides;j++) {
    const a=i*(sides+1)+j,b=a+1,c=a+sides+1,d=c+1;index.push(a,b,c,b,d,c);
  }
  for(let j=1;j<sides;j++)index.push(0,j+1,j);
  const end=rings*(sides+1);for(let j=1;j<sides;j++)index.push(end,end+j,end+j+1);
  const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(vertices,3));
  g.setAttribute('uv',new THREE.Float32BufferAttribute(uv,2));g.setIndex(index);g.computeVertexNormals();g.computeBoundingBox();g.computeBoundingSphere();return g;
}

const vertexShader=/* glsl */`
  varying vec2 vPlumeUv;
  varying vec3 vPlumeNormal;
  varying vec3 vPlumeView;
  #include <common>
  #include <logdepthbuf_pars_vertex>
  void main() {
    vPlumeUv=uv;
    vec4 mvPosition=modelViewMatrix*vec4(position,1.0);
    vPlumeView=-mvPosition.xyz;
    vPlumeNormal=normalMatrix*normal;
    gl_Position=projectionMatrix*mvPosition;
    #include <logdepthbuf_vertex>
  }
`;
const fragmentShader=/* glsl */`
  uniform float uTime;
  uniform float uPower;
  uniform float uCore;
  varying vec2 vPlumeUv;
  varying vec3 vPlumeNormal;
  varying vec3 vPlumeView;
  #include <common>
  #include <logdepthbuf_pars_fragment>
  void main() {
    #include <logdepthbuf_fragment>
    // MSAA extrapolates varyings: clamp BEFORE powers, angles and exp.
    vec2 st=clamp(vPlumeUv,vec2(0.0),vec2(1.0));
    float angle=clamp(st.x*6.2831853,0.0,6.2831853);
    float t=clamp(st.y,0.0,1.0);
    vec3 n=vPlumeNormal/max(length(vPlumeNormal),0.00001);
    vec3 v=vPlumeView/max(length(vPlumeView),0.00001);
    float facing=clamp(abs(dot(n,v)),0.0,1.0);
    float edge=pow(clamp(facing,0.0,1.0),0.65);
    float fade=exp(-clamp(t*4.3,0.0,12.0))*(1.0-smoothstep(0.66,1.0,t));
    float throat=smoothstep(0.0,0.035,t);
    float flow=0.93+0.07*sin(clamp(t*23.0-angle*2.0-uTime*1.7,-100000.0,100000.0));
    float breath=0.96+0.04*sin(uTime*0.8);
    vec3 cold=vec3(0.055,0.29,0.80);
    vec3 hot=mix(vec3(0.20,0.63,0.98),vec3(0.70,0.88,1.0),uCore);
    vec3 color=mix(hot,cold,smoothstep(0.02,0.72,t));
    float alpha=clamp(mix(0.37,0.76,uCore)*fade*throat*flow*breath*edge*(0.75+0.25*uPower),0.0,0.82);
    if(alpha<0.002)discard;
    gl_FragColor=vec4(clamp(color,vec3(0.0),vec3(1.0)),alpha);
    #include <colorspace_fragment>
  }
`;

/** Add OUTSIDE hull AFTER measuring its 74,400m physical bounds. Missing metadata
 * is not guessed: metadataReady=false, and update() accepts metadata arriving later.
 * Owns its geometry/materials, never the hull's resources. */
export function buildArkExhaust(hull:THREE.Object3D):ArkExhaust {
  const group=new THREE.Group();group.name='ark-engine-exhaust';
  group.userData.coordinateSpace='hull-parent';group.userData.excludedFromPhysicalBounds=true;
  const geometry=plumeGeometry(),time={value:0},powerUniform={value:.5};
  const material=(core:number)=>new THREE.ShaderMaterial({
    uniforms:{uTime:time,uPower:powerUniform,uCore:{value:core}},vertexShader,fragmentShader,
    transparent:true,depthWrite:false,depthTest:true,side:THREE.FrontSide,
    blending:THREE.NormalBlending,toneMapped:false,
  });
  const tailMaterial=material(0),coreMaterial=material(1);
  const nozzles:{root:THREE.Group;radius:number;length:number;phase:number}[]=[];
  let ready=false,disposed=false,elapsed=0,currentPower=.5;
  const initialize=()=>{
    const raw:unknown=hull.userData.engineExhausts;
    if(!Array.isArray(raw)||raw.length===0)return;
    const entries=raw.filter((e):e is ArkEngineExhaust=>
      e&&Array.isArray(e.position)&&e.position.length===3&&e.position.every(Number.isFinite)&&
      Array.isArray(e.direction)&&e.direction.length===3&&e.direction.every(Number.isFinite)&&
      Number.isFinite(e.radius)&&e.radius>0&&Math.hypot(...e.direction)>1e-8);
    if(!entries.length)return;
    hull.updateWorldMatrix(true,true);
    const inverseParent=hull.parent?.matrixWorld.clone().invert()??new THREE.Matrix4();
    const transform=inverseParent.multiply(hull.matrixWorld);
    const scale=new THREE.Vector3().setFromMatrixScale(transform);
    const radiusScale=(Math.abs(scale.x)+Math.abs(scale.y)+Math.abs(scale.z))/3;
    for(let i=0;i<entries.length;i++) {
      const e=entries[i],root=new THREE.Group();root.name='ark-plume-'+i;
      const direction=new THREE.Vector3(...e.direction).transformDirection(transform);
      const radius=e.radius*radiusScale,length=radius*13.5;
      root.position.set(...e.position).applyMatrix4(transform).addScaledVector(direction,radius*.06);
      root.quaternion.setFromUnitVectors(new THREE.Vector3(0,0,1),direction);
      const tail=new THREE.Mesh(geometry,tailMaterial),core=new THREE.Mesh(geometry,coreMaterial);
      tail.name='fading-blue-volume';core.name='blue-white-throat';core.scale.set(.43,.43,.30);
      for(const mesh of [tail,core]) {mesh.layers.set(1);mesh.frustumCulled=true;mesh.renderOrder=2;root.add(mesh);}
      group.add(root);nozzles.push({root,radius,length,phase:i*.83});
    }
    ready=true;group.userData.metadataReady=true;group.userData.nozzleCount=nozzles.length;
  };
  const update=(dt:number,power=.5)=>{
    if(disposed)return;if(!ready)initialize();
    const step=Number.isFinite(dt)?THREE.MathUtils.clamp(dt,0,.1):0;
    const target=Number.isFinite(power)?THREE.MathUtils.clamp(power,0,1):.5;
    // 20pi is a common period for the .8 and 1.7 shader frequencies.
    elapsed=(elapsed+step)%(Math.PI*20);time.value=elapsed;
    currentPower+=(target-currentPower)*(1-Math.exp(-step*1.4));powerUniform.value=currentPower;
    for(const n of nozzles) {
      const breathe=1+.025*Math.sin(elapsed*.8+n.phase);
      // Idle flight still has a sustained tail; power is NOT visibility.
      n.root.scale.set(n.radius,n.radius,n.length*(.72+.48*currentPower)*breathe);
    }
  };
  group.userData.metadataReady=false;update(0);
  return {group,get metadataReady(){return ready;},update,dispose(){
    if(disposed)return;disposed=true;group.removeFromParent();group.clear();nozzles.length=0;
    geometry.dispose();tailMaterial.dispose();coreMaterial.dispose();
  }};
}
