// Procedural deep space: blue-violet nebulae, distant worlds and a clear flight corridor.
// No external textures. Sky + stars cost two draws; the sparse debris belt one.
import * as THREE from 'three';
import { disposeTree } from '../world/ship';
import type { QualityPreset } from '../config';

export interface SpaceSceneOptions { quality: QualityPreset; seed?: number; }
type WarpPhase = 'idle' | 'charging' | 'jumping' | 'arriving';

// Metres, rebased for a 74.4 km ark. Explicit radii keep the sky within the 2 Mm far plane.
const ORBIT_SCALE = 126_000 / 1060;
const SKY_RADIUS = 1_650_000;
const STAR_RADIUS = 1_500_000;

const NOISE = /* glsl */ `
float hash3(vec3 p) {
  p = fract(p * 0.1031);
  p += dot(p, p.yzx + 33.33);
  return fract((p.x + p.y) * p.z);
}
float noise3(vec3 p) {
  vec3 i = floor(p), f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  return mix(mix(mix(hash3(i), hash3(i + vec3(1,0,0)), f.x),
                 mix(hash3(i + vec3(0,1,0)), hash3(i + vec3(1,1,0)), f.x), f.y),
             mix(mix(hash3(i + vec3(0,0,1)), hash3(i + vec3(1,0,1)), f.x),
                 mix(hash3(i + vec3(0,1,1)), hash3(i + vec3(1,1,1)), f.x), f.y), f.z);
}
float fbm(vec3 p) {
  float sum = 0.0, amplitude = 0.52;
  mat3 turn = mat3(0.0,0.8,0.6, -0.8,0.36,-0.48, -0.6,-0.48,0.64);
  for (int i = 0; i < 5; i++) {
    sum += amplitude * noise3(p);
    p = turn * p * 2.04 + vec3(7.1,3.4,1.7);
    amplitude *= 0.49;
  }
  return sum;
}
`;

const SKY_VERTEX = /* glsl */ `
#include <common>
#include <logdepthbuf_pars_vertex>
varying vec3 vDirection;
void main() {
  vDirection = normalize(position);
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  #include <logdepthbuf_vertex>
  // At near=0.1 / far=2e6, ordinary projected Z rounds past W for some
  // million-metre sphere vertices. Log depth only fixes fragment depth, not
  // homogeneous clipping. This background never writes/tests depth, so keep
  // Z safely inside the clip volume instead of xyww (exactly on its edge).
  gl_Position.z = 0.0;
}
`;

const SKY_FRAGMENT = NOISE + /* glsl */ `
#include <logdepthbuf_pars_fragment>
varying vec3 vDirection;
uniform vec3 uNebulaA;
uniform vec3 uNebulaB;
uniform float uSeed;
void main() {
  #include <logdepthbuf_fragment>
  vec3 d = normalize(vDirection);
  vec3 p = d * 2.5 + vec3(uSeed * 0.17);
  float broad = fbm(p);
  float wisps = fbm(p * 2.1 + vec3(broad * 1.8, broad, 0.0));
  float band = exp(-pow((d.y + d.x * 0.35 - d.z * 0.12 + (broad - 0.5) * 0.65) * 2.2, 2.0));
  float clouds = smoothstep(0.23, 0.74, wisps) * band;
  float dust = smoothstep(0.48, 0.7, fbm(p * 4.0)) * band;
  vec3 color = vec3(0.0015, 0.003, 0.009);
  color += mix(uNebulaA, uNebulaB, smoothstep(0.32,0.68,broad)) * clouds * 0.25;
  color += vec3(0.009,0.018,0.045) * band * broad;
  color *= 1.0 - dust * 0.58;
  gl_FragColor = vec4(color, 1.0);
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}
`;

const STAR_VERTEX = /* glsl */ `
#include <common>
#include <logdepthbuf_pars_vertex>
attribute float aSize;
attribute vec3 aColor;
varying vec3 vColor;
void main() {
  vColor = aColor;
  vec4 view = modelViewMatrix * vec4(position,1.0);
  gl_Position = projectionMatrix * view;
  #include <logdepthbuf_vertex>
  // Preserve vFragDepth from the true view-space distance for planet/ship
  // occlusion, but avoid imprecise hardware far-plane clipping of the stars.
  #ifdef USE_LOGDEPTHBUF
    gl_Position.z = 0.0;
  #endif
  gl_PointSize = aSize;
}
`;

const STAR_FRAGMENT = /* glsl */ `
#include <logdepthbuf_pars_fragment>
varying vec3 vColor;
void main() {
  #include <logdepthbuf_fragment>
  float r = length(gl_PointCoord - 0.5) * 2.0;
  if (r > 1.0) discard;
  float core = exp(-r*r*8.0);
  float halo = 0.16 * pow(1.0-r,2.0);
  gl_FragColor = vec4(vColor, core + halo);
  #include <colorspace_fragment>
}
`;

const WORLD_VERTEX = /* glsl */ `
#include <common>
#include <logdepthbuf_pars_vertex>
varying vec3 vLocal;
varying vec3 vNormal;
varying vec3 vWorld;
void main() {
  vLocal = normalize(position);
  vNormal = normalize(mat3(modelMatrix) * normal);
  vWorld = (modelMatrix * vec4(position,1.0)).xyz;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0);
  #include <logdepthbuf_vertex>
}
`;

const PLANET_FRAGMENT = NOISE + /* glsl */ `
#include <logdepthbuf_pars_fragment>
varying vec3 vLocal;
varying vec3 vNormal;
varying vec3 vWorld;
uniform vec3 uSun;
uniform vec3 uOcean;
uniform float uSeed;
void main() {
  #include <logdepthbuf_fragment>
  vec3 p = normalize(vLocal);
  vec3 n = normalize(vNormal), view = normalize(cameraPosition-vWorld);
  vec3 terrain = p * 2.7 + vec3(uSeed*0.09);
  float large = fbm(terrain);
  float continent = smoothstep(0.52,0.62,large);
  float coast = smoothstep(0.46,0.55,large) - continent;
  vec3 surface = uOcean * (0.72 + 0.38*large);
  surface = mix(surface, vec3(0.065,0.14,0.145), continent * 0.84);
  surface += vec3(0.01,0.047,0.052) * coast;
  float polar = smoothstep(0.80,0.96,abs(p.y) + (large-0.5)*0.16);
  surface = mix(surface,vec3(0.51,0.66,0.73),polar*0.82);
  // Coherent, stretched cloud fronts instead of unrelated low-resolution speckles.
  vec3 cloudDomain = vec3(p.x*4.0 + sin(p.y*8.0)*0.45,p.y*8.0,p.z*4.0);
  float cloudFlow = fbm(cloudDomain + vec3(uSeed*0.05,0.0,0.0));
  float clouds = smoothstep(0.46,0.69,cloudFlow);
  clouds *= 0.65 + 0.35*sin(p.y*11.0 + large*4.0);
  surface = mix(surface,vec3(0.67,0.77,0.84),clouds*0.86);
  float sun = dot(n,normalize(uSun));
  float daylight = smoothstep(-0.12,0.6,sun);
  vec3 color = surface * (0.055 + daylight*1.05);
  float rim = pow(1.0-max(dot(n,view),0.0),3.5);
  color += vec3(0.07,0.32,0.68) * rim * (0.16+daylight*0.6);
  vec3 halfDir = normalize(normalize(uSun)+view);
  float glint = pow(max(dot(n,halfDir),0.0),70.0) * (1.0-clouds)*(1.0-continent);
  color += vec3(0.25,0.44,0.58) * glint*0.45;
  gl_FragColor = vec4(color,1.0);
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}
`;

const ATMOSPHERE_FRAGMENT = /* glsl */ `
#include <logdepthbuf_pars_fragment>
varying vec3 vNormal;
varying vec3 vWorld;
uniform vec3 uSun;
void main() {
  #include <logdepthbuf_fragment>
  vec3 n = normalize(vNormal), view = normalize(cameraPosition-vWorld);
  float rim = pow(1.0-clamp(abs(dot(n,view)),0.0,1.0),5.0);
  float light = smoothstep(-0.3,0.8,dot(n,normalize(uSun)));
  gl_FragColor = vec4(vec3(0.15,0.43,0.88),rim*(0.13+light*0.52));
  #include <colorspace_fragment>
}
`;

const MOON_FRAGMENT = NOISE + /* glsl */ `
#include <logdepthbuf_pars_fragment>
varying vec3 vLocal;
varying vec3 vNormal;
uniform vec3 uSun;
void main() {
  #include <logdepthbuf_fragment>
  float mare = smoothstep(0.32,0.63,fbm(normalize(vLocal)*3.0));
  vec3 surface = mix(vec3(0.16,0.20,0.26),vec3(0.39,0.43,0.48),mare);
  float light = smoothstep(-0.08,0.85,dot(normalize(vNormal),normalize(uSun)));
  gl_FragColor = vec4(surface*(0.045+light),1.0);
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}
`;

const WARP_VERTEX = /* glsl */ `
varying vec2 vUv;
void main() { vUv = uv; gl_Position = vec4(position.xy,0.0,1.0); }
`;

const WARP_FRAGMENT = /* glsl */ `
varying vec2 vUv;
uniform float uWarp;
uniform float uTime;
uniform float uAspect;
void main() {
  vec2 p = (vUv-0.5)*vec2(uAspect,1.0);
  float r = length(p);
  float angle = atan(p.y,p.x);
  float ray = pow(max(sin(angle*91.0 + sin(angle*17.0)*4.0),0.0),28.0);
  float travel = pow(max(sin(r*28.0-uTime*16.0+angle*7.0),0.0),6.0);
  float veil = smoothstep(0.08,0.65,r);
  float alpha = uWarp * (ray*travel*veil*0.7 + veil*0.06);
  gl_FragColor = vec4(vec3(0.22,0.61,0.93),alpha);
}
`;


export class SpaceScene {
  private readonly root = new THREE.Group();
  private readonly sky: THREE.Mesh;
  private readonly skyMaterial: THREE.ShaderMaterial;
  private readonly stars: THREE.Points;
  private readonly planet: THREE.Mesh;
  private readonly planetMaterial: THREE.ShaderMaterial;
  private readonly atmosphere: THREE.Mesh;
  private readonly moon: THREE.Mesh;
  private readonly asteroids: THREE.InstancedMesh;
  private readonly warpOverlay: THREE.Mesh;
  private readonly warpMaterial: THREE.ShaderMaterial;
  private readonly sunLight: THREE.DirectionalLight;
  private readonly ambient: THREE.HemisphereLight;
  private readonly sunlight = new THREE.Vector3(-0.6,0.65,0.8).normalize();
  private readonly quality: QualityPreset;
  private seed: number;
  private randomState: number;
  private warpState: WarpPhase = 'idle';
  private warpTimer = 0;
  private elapsed = 0;
  private onArrive: (() => void) | null = null;
  private disposed = false;

  constructor(
    private readonly scene: THREE.Scene,
    private readonly camera: THREE.PerspectiveCamera,
    options: SpaceSceneOptions,
  ) {
    this.quality = options.quality;
    this.seed = options.seed ?? Math.random()*10000;
    this.randomState = (Math.floor(this.seed*104729) >>> 0) || 1;
    this.root.name = 'space-environment';
    this.skyMaterial = new THREE.ShaderMaterial({
      vertexShader: SKY_VERTEX, fragmentShader: SKY_FRAGMENT,
      side: THREE.BackSide, depthWrite: false, depthTest: false,
      uniforms: {
        uSeed: {value:this.seed},
        uNebulaA: {value:new THREE.Color(0.08,0.16,0.36)},
        uNebulaB: {value:new THREE.Color(0.22,0.10,0.32)},
      },
    });
    this.sky = new THREE.Mesh(new THREE.SphereGeometry(SKY_RADIUS,32,20),this.skyMaterial);
    this.sky.name = 'space-sky';
    this.sky.frustumCulled = false;
    this.sky.renderOrder = -20;
    this.stars = this.createStars();
    this.root.add(this.sky,this.stars);

    this.planetMaterial = new THREE.ShaderMaterial({
      vertexShader:WORLD_VERTEX, fragmentShader:PLANET_FRAGMENT,
      uniforms:{uSun:{value:this.sunlight},uSeed:{value:this.seed},uOcean:{value:new THREE.Color(0.026,0.105,0.27)}},
    });
    this.planet = new THREE.Mesh(new THREE.SphereGeometry(126_000,80,56),this.planetMaterial);
    this.planet.name = 'space-planet';
    this.planet.position.set(-145000,55000,-315000);
    const atmosphereMaterial = new THREE.ShaderMaterial({
      vertexShader:WORLD_VERTEX, fragmentShader:ATMOSPHERE_FRAGMENT,
      uniforms:{uSun:{value:this.sunlight}}, side:THREE.BackSide,
      transparent:true, blending:THREE.AdditiveBlending, depthWrite:false,
    });
    this.atmosphere = new THREE.Mesh(new THREE.SphereGeometry(1085*ORBIT_SCALE,64,48),atmosphereMaterial);
    this.atmosphere.name = 'space-atmosphere';
    this.atmosphere.position.copy(this.planet.position);
    this.atmosphere.renderOrder = 2;
    this.moon = new THREE.Mesh(new THREE.SphereGeometry(225*ORBIT_SCALE,40,28),new THREE.ShaderMaterial({
      vertexShader:WORLD_VERTEX, fragmentShader:MOON_FRAGMENT,uniforms:{uSun:{value:this.sunlight}},
    }));
    this.moon.name = 'space-moon';
    this.moon.position.set(1720,1050,-6200).multiplyScalar(ORBIT_SCALE);
    this.root.add(this.planet,this.atmosphere,this.moon);

    // Soft neutral solar light leaves the gold hull readable without washing out its cyan veins.
    this.sunLight = new THREE.DirectionalLight(0xd8e4ff,.72);
    this.sunLight.position.copy(this.sunlight).multiplyScalar(4000*ORBIT_SCALE);
    this.ambient = new THREE.HemisphereLight(0x557297,0x10141e,.24);
    this.root.add(this.sunLight,this.ambient);
    this.asteroids = this.createAsteroids();
    this.root.add(this.asteroids);
    this.warpMaterial = new THREE.ShaderMaterial({
      vertexShader:WARP_VERTEX, fragmentShader:WARP_FRAGMENT,
      transparent:true, blending:THREE.AdditiveBlending,depthWrite:false,depthTest:false,
      uniforms:{uWarp:{value:0},uTime:{value:0},uAspect:{value:camera.aspect}},
    });
    this.warpOverlay = new THREE.Mesh(new THREE.PlaneGeometry(2,2),this.warpMaterial);
    this.warpOverlay.name = 'space-warp';
    this.warpOverlay.frustumCulled = false;
    this.warpOverlay.renderOrder = 999;
    this.warpOverlay.visible = false;
    camera.add(this.warpOverlay);
    // Preserve the caller's camera parent; game normally already adds the camera.
    if (!camera.parent) scene.add(camera);
    scene.add(this.root);
    scene.fog = null;
  }

  private random(): number {
    this.randomState = (Math.imul(this.randomState,1664525)+1013904223) >>> 0;
    return this.randomState/4294967296;
  }

  private createStars(): THREE.Points {
    const count = Math.min(6500,Math.max(1800,this.quality.starCount));
    const positions = new Float32Array(count*3);
    const colors = new Float32Array(count*3);
    const sizes = new Float32Array(count);
    for (let i=0;i<count;i++) {
      const y = this.random()*2-1;
      const a = this.random()*Math.PI*2;
      const h = Math.sqrt(1-y*y);
      positions.set([Math.cos(a)*h*STAR_RADIUS,y*STAR_RADIUS,Math.sin(a)*h*STAR_RADIUS],i*3);
      const bright = this.random();
      sizes[i] = bright>0.988 ? 3.7 : bright>0.9 ? 2.2 : 1.2;
      const warm = this.random()>0.8;
      const intensity = 0.55 + bright*0.45;
      colors.set(warm ? [intensity,intensity*0.84,intensity*0.65] : [intensity*0.7,intensity*0.85,intensity],i*3);
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position',new THREE.BufferAttribute(positions,3));
    geometry.setAttribute('aColor',new THREE.BufferAttribute(colors,3));
    geometry.setAttribute('aSize',new THREE.BufferAttribute(sizes,1));
    const points = new THREE.Points(geometry,new THREE.ShaderMaterial({
      vertexShader:STAR_VERTEX,fragmentShader:STAR_FRAGMENT,
      transparent:true,depthWrite:false,blending:THREE.AdditiveBlending,
    }));
    points.name = 'space-stars';
    points.frustumCulled = false;
    points.renderOrder = -19;
    return points;
  }

  private createAsteroids(): THREE.InstancedMesh {
    // Identical positions receive identical displacement: continuous, closed rock surfaces.
    // No independently randomized triangle vertices, no fractured low-poly splinters.
    const geometry = new THREE.IcosahedronGeometry(1,2);
    const position = geometry.getAttribute('position');
    for (let i=0;i<position.count;i++) {
      const x=position.getX(i),y=position.getY(i),z=position.getZ(i);
      const r=1+0.1*Math.sin(x*5+y*3)*Math.cos(z*4-x*2)+0.05*Math.sin(y*7+z*3);
      position.setXYZ(i,x*r,y*r*0.82,z*r*0.92);
    }
    geometry.computeVertexNormals();
    const count = Math.min(16,Math.max(6,Math.floor(this.quality.asteroidCount/21)));
    const mesh = new THREE.InstancedMesh(geometry,new THREE.MeshStandardMaterial({
      color:0x727984,roughness:0.97,metalness:0.02,
    }),count);
    mesh.name = 'space-distant-asteroids';
    mesh.frustumCulled = false;
    this.placeAsteroids(mesh);
    return mesh;
  }

  private placeAsteroids(mesh: THREE.InstancedMesh): void {
    const dummy = new THREE.Object3D();
    for (let i=0;i<mesh.count;i++) {
      // At full scale the 74.4 km hull fits within a 50 km radius. The belt starts
      // at |x| >=273 km and has no inward drift: >220 km clearance even for the
      // largest rock. z >=-60 km excludes the distant forward planet view.
      dummy.position.set((i%2 ? 1 : -1)*(2300+this.random()*2000),-1200+this.random()*1900,-500+this.random()*4200).multiplyScalar(ORBIT_SCALE);
      dummy.rotation.set(this.random()*6,this.random()*6,this.random()*6);
      dummy.scale.setScalar((8+this.random()*19)*ORBIT_SCALE);
      dummy.updateMatrix();
      mesh.setMatrixAt(i,dummy.matrix);
    }
    mesh.instanceMatrix.needsUpdate = true;
  }

  triggerWarp(onArrive?: () => void): boolean {
    if (this.disposed || this.warpState!=='idle') return false;
    this.warpState='charging';
    this.warpTimer=0;
    this.onArrive=onArrive ?? null;
    this.warpOverlay.visible=true;
    return true;
  }

  get warping(): boolean { return this.warpState!=='idle'; }
  get warpPhase(): string { return this.warpState; }
  get phase(): string { return this.warpState; }
  get nebulaColors(): [number,number] {
    return [(this.skyMaterial.uniforms.uNebulaA.value as THREE.Color).getHex(),(this.skyMaterial.uniforms.uNebulaB.value as THREE.Color).getHex()];
  }

  reroll(): void {
    if (this.disposed) return;
    this.seed=this.random()*10000;
    this.skyMaterial.uniforms.uSeed.value=this.seed;
    this.planetMaterial.uniforms.uSeed.value=this.seed;
    const hue=this.random();
    (this.skyMaterial.uniforms.uNebulaA.value as THREE.Color).setRGB(0.055+hue*0.04,0.12+hue*0.04,0.31+hue*0.08);
    (this.skyMaterial.uniforms.uNebulaB.value as THREE.Color).setRGB(0.17+hue*0.08,0.08+hue*0.045,0.28+hue*0.07);
    (this.planetMaterial.uniforms.uOcean.value as THREE.Color).setRGB(0.022,0.085+this.random()*0.045,0.23+this.random()*0.08);
    this.planet.position.set(-1150+this.random()*1300,550+this.random()*650,-4100-this.random()*900).multiplyScalar(ORBIT_SCALE);
    this.planet.rotation.set(this.random()*0.3,this.random()*Math.PI*2,0.08);
    this.atmosphere.position.copy(this.planet.position);
    this.moon.position.set(1500+this.random()*1000,650+this.random()*1100,-5700-this.random()*900).multiplyScalar(ORBIT_SCALE);
    this.stars.rotation.set(this.random()*Math.PI,this.random()*Math.PI,0);
    this.placeAsteroids(this.asteroids);
  }

  update(dt: number): void {
    if (this.disposed) return;
    dt=Number.isFinite(dt) ? Math.max(0,dt) : 0;
    this.elapsed+=dt;
    this.camera.getWorldPosition(this.sky.position);
    this.stars.position.copy(this.sky.position);
    this.planet.rotation.y+=dt*0.002;
    this.moon.rotation.y+=dt*0.003;
    if (this.warpState==='idle') return;
    this.warpTimer+=dt;
    let amount=0;
    if (this.warpState==='charging') {
      amount=Math.min(0.3,this.warpTimer/1.1*0.3);
      if (this.warpTimer>=1.1) { this.warpState='jumping'; this.warpTimer=0; }
    } else if (this.warpState==='jumping') {
      amount=Math.min(1,0.3+this.warpTimer*0.5);
      if (this.warpTimer>=2.4) {
        this.warpState='arriving'; this.warpTimer=0;
        this.reroll();
        const callback=this.onArrive;
        this.onArrive=null;
        callback?.();
      }
    } else {
      amount=Math.max(0,1-this.warpTimer/1.1);
      if (this.warpTimer>=1.1) { this.warpState='idle'; amount=0; this.warpOverlay.visible=false; }
    }
    this.warpMaterial.uniforms.uWarp.value=amount;
    this.warpMaterial.uniforms.uTime.value=this.elapsed;
    this.warpMaterial.uniforms.uAspect.value=this.camera.aspect;
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed=true;
    this.onArrive=null;
    this.warpState='idle';
    this.camera.remove(this.warpOverlay);
    this.root.add(this.warpOverlay);
    this.scene.remove(this.root);
    disposeTree(this.root);
    this.sunLight.dispose();
    this.ambient.dispose();
    this.root.clear();
  }
}
