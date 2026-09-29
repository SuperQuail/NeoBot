import * as THREE from 'three';
import type { ShipMaterials } from './materials';

/** Actual curved psionic glazing; metre-scale pattern, not a camera overlay. */
const VERTEX = /* glsl */ `
#include <common>
#include <logdepthbuf_pars_vertex>
attribute float rimDistance;
varying float vRimDistance;
varying vec2 vUv;
varying vec3 vNormal;
varying vec3 vView;
void main() {
  vUv = uv;
  vRimDistance = rimDistance;
  vec4 view = modelViewMatrix * vec4(position, 1.0);
  vView = -view.xyz;
  vNormal = normalize(normalMatrix * normal);
  gl_Position = projectionMatrix * view;
  #include <logdepthbuf_vertex>
}
`;
const FRAGMENT = /* glsl */ `
#include <logdepthbuf_pars_fragment>
uniform float uTime;
uniform vec2 uSpan;
uniform float uStrength;
varying float vRimDistance;
varying vec2 vUv;
varying vec3 vNormal;
varying vec3 vView;
float hexEdge(vec2 p) {
  vec2 repeat = vec2(1.0, 1.7320508);
  vec2 a = mod(p, repeat) - repeat * .5;
  vec2 b = mod(p - repeat * .5, repeat) - repeat * .5;
  vec2 q = dot(a,a) < dot(b,b) ? a : b;
  q = abs(q);
  float d = max(q.x, dot(q, vec2(.5, .8660254)));
  float aa = max(fwidth(d) * 1.2, .010);
  return 1.0 - smoothstep(.010, .010 + aa, abs(d - .5));
}
void main() {
  #include <logdepthbuf_fragment>
  // MSAA can interpolate outside a subpixel triangle at orbital distances.
  // Never exponentiate a negative edge distance: it explodes into a white flare.
  vec2 uv = clamp(vUv, vec2(0.0), vec2(1.0));
  vec2 field = uv * uSpan;
  float edgeDistance = max(0.0, vRimDistance);
  float border = exp(-edgeDistance * 1.7);
  float facing = clamp(abs(dot(normalize(vNormal), normalize(vView))), 0.0, 1.0);
  float fresnel = pow(1.0 - facing, 2.1);
  float ripple = pow(.5 + .5 * sin(field.y * .64 - uTime * .32 + sin(field.x * .21) * 1.4), 26.0);
  float cells = hexEdge(field / 1.25);
  float seams = 1.0 - smoothstep(.018, .055, edgeDistance);
  float alpha = (.13 + fresnel * .19 + border * .19 + cells * .027 + ripple * .025) * uStrength;
  vec3 color = mix(vec3(.015,.13,.37), vec3(.065,.39,.88), clamp(fresnel * .55 + border * .65, 0.0, 1.0));
  color += vec3(.04,.23,.48) * (cells * .25 + ripple * .5 + seams * 1.6);
  gl_FragColor = vec4(color, clamp(alpha, .07, .53));
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}
`;

/** A single ellipsoidal canopy, clipped only at the rear bulkhead and sill.
 * Front, sides and roof have one continuous analytic normal field: no box faces
 * or 90-degree glass joints. The inner deck/rail still defines the walkable edge. */
export function buildBridgeShield(materials:ShipMaterials):THREE.Group {
  const root=new THREE.Group();root.name='bridge-psionic-shield';
  const A=34,B=24.5,C=31,cy=-2,cz=-21,sill=.25;
  const floorScale=Math.sqrt(1-((sill-cy)/B)**2),front=cz-C*floorScale;
  const slices=112,rows=88,positions:number[]=[],normals:number[]=[],uvs:number[]=[],rims:number[]=[],indices:number[]=[];
  for(let row=0;row<=rows;row++) {
    const z=front+(0-front)*row/rows,s=(z-cz)/C,r=Math.sqrt(Math.max(0,1-s*s));
    const limit=Math.acos(Math.min(1,(sill-cy)/(B*r)));
    for(let col=0;col<=slices;col++) {
      const angle=-limit+2*limit*col/slices;
      const x=A*r*Math.sin(angle),y=cy+B*r*Math.cos(angle);
      positions.push(x,y,z);
      const n=new THREE.Vector3(x/(A*A),(y-cy)/(B*B),(z-cz)/(C*C)).normalize();
      normals.push(n.x,n.y,n.z);
      uvs.push(.5+angle/Math.PI,(Math.asin(s)+Math.PI/2)/Math.PI);
      rims.push(Math.max(0,Math.min((limit-Math.abs(angle))*Math.sqrt(A*B)*r,-z)));
      if(row<rows&&col<slices){const i=row*(slices+1)+col;indices.push(i,i+1,i+slices+1,i+1,i+slices+2,i+slices+1);}
    }
  }
  const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));
  geometry.setAttribute('normal',new THREE.Float32BufferAttribute(normals,3));geometry.setAttribute('uv',new THREE.Float32BufferAttribute(uvs,2));
  geometry.setAttribute('rimDistance',new THREE.Float32BufferAttribute(rims,1));geometry.setIndex(indices);geometry.computeBoundingSphere();
  const material=new THREE.ShaderMaterial({name:'continuous-psionic-canopy',vertexShader:VERTEX,fragmentShader:FRAGMENT,
    uniforms:{uTime:{value:0},uSpan:{value:new THREE.Vector2(93,88)},uStrength:{value:.92}},
    transparent:true,depthWrite:false,side:THREE.DoubleSide,blending:THREE.NormalBlending});
  const canopy=new THREE.Mesh(geometry,material);canopy.name='continuous-ellipsoidal-field';canopy.userData.psionicPane=true;root.add(canopy);
  const rearAngle=Math.acos(cz/(C*floorScale));
  const rim:THREE.Vector3[]=[];
  for(let i=0;i<=160;i++){const a=-rearAngle+2*rearAngle*i/160;rim.push(new THREE.Vector3(A*floorScale*Math.sin(a),sill,cz-C*floorScale*Math.cos(a)));}
  const rimGeometry=new THREE.TubeGeometry(new THREE.CatmullRomCurve3(rim),200,.055,6,false);
  const rail=new THREE.Mesh(rimGeometry,materials.trim);rail.name='curved-field-sill';root.add(rail);
  const crystal=new THREE.MeshStandardMaterial({color:0x234683,emissive:0x369eff,emissiveIntensity:1.5,roughness:.3,metalness:.25});
  for(const a of [-1.9,-1.2,-.55,0,.55,1.2,1.9]) {
    const x=A*floorScale*Math.sin(a),z=cz-C*floorScale*Math.cos(a);
    const socket=new THREE.Mesh(new THREE.CylinderGeometry(.3,.4,1.5,12),materials.hull);socket.position.set(x,-.45,z);root.add(socket);
    const gem=new THREE.Mesh(new THREE.OctahedronGeometry(.16),crystal);gem.scale.y=1.5;gem.position.set(x,.5,z);root.add(gem);
  }
  root.userData.update=(dt:number)=>{if(Number.isFinite(dt)&&dt>0)material.uniforms.uTime.value+=Math.min(dt,.1);};
  root.userData.paneCount=1;root.userData.surface='continuous ellipsoid';
  root.userData.bounds={frontZ:front,halfWidth:A,roofApex:cy+B,rearZ:0};
  return root;
}

