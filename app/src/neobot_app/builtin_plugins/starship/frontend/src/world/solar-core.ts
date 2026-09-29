/** Solar Core containment chamber, reconstructed from Blizzard's in-game Karax room.
 * Reference (closed containment state, NOT the Solarite allocation UI):
 * https://bnetcmsus-a.akamaihd.net/cms/content_folder_media/r2/R2ENCXY6TTCZ1415234276295.jpg
 * The visible giant object is an armoured vessel: olive electrum plates, cold
 * indicator apertures, rooted machinery and a vaulted layered chamber. No blue egg.
 * Owns no floor bounds, door or station; interior.ts preserves those contracts. */
import * as THREE from 'three';
import { Architecture, type Point } from './geometry';
import type { ShipMaterials } from './materials';
import type { CollisionWorld } from '../core/collision';

export function buildSolarCore(m: ShipMaterials, collision: CollisionWorld) {
  const group=new THREE.Group();group.name='solar-core-reference-chamber';
  group.userData.reference='https://bnetcmsus-a.akamaihd.net/cms/content_folder_media/r2/R2ENCXY6TTCZ1415234276295.jpg';
  group.userData.containmentState='closed-armoured-vessel';
  const staticParts=new THREE.Group();staticParts.name='solar-core-static-machinery';group.add(staticParts);
  const a=new Architecture(staticParts), detail=new Architecture(group);
  const metal=(name:string,color:number,roughness=.48,metalness=.72)=>{
    const mat=new THREE.MeshStandardMaterial({color,roughness,metalness});mat.name=name;return mat;
  };
  const armour=metal('solar-core-olive-electrum',0x777347,.43);
  const armourShade=metal('solar-core-aged-lower-plates',0x82734b,.5);
  const edge=metal('solar-core-burnished-seams',0xa19662,.37);
  const dark=metal('solar-core-recessed-structure',0x17222a,.52);
  const steel=metal('solar-core-vault-blue-steel',0x3b4650,.51);
  const deck=metal('solar-core-dark-alloy-deck',0x35434b,.64,.4);
  const deckAlt=metal('solar-core-deck-inset',0x2c3942,.64,.4);
  const blue=new THREE.MeshStandardMaterial({color:0x4b95b4,emissive:0x5ebeff,emissiveIntensity:2.1,metalness:.35,roughness:.24});
  const windowBlue=new THREE.MeshStandardMaterial({color:0x18567f,emissive:0x167ed5,emissiveIntensity:1.05,metalness:.12,roughness:.38});
  windowBlue.name='solar-core-blue-inspection-window';
  const dimBlue=new THREE.MeshBasicMaterial({color:0x417494});
  const pearl=new THREE.MeshBasicMaterial({color:0xa1e6ff});
  const geometryMesh=(name:string,g:THREE.BufferGeometry,mat:THREE.Material,parent=staticParts)=>{
    const mesh=new THREE.Mesh(g,mat);mesh.name=name;mesh.receiveShadow=true;parent.add(mesh);return mesh;
  };
  const profile=(shape:THREE.Shape,depth:number,position:Point,mat:THREE.Material,name:string)=>{
    const g=new THREE.ExtrudeGeometry(shape,{depth,steps:1,bevelEnabled:true,bevelSize:.09,bevelThickness:.09,bevelSegments:2,curveSegments:28});
    g.translate(position[0],position[1],position[2]-depth/2);return geometryMesh(name,g,mat);
  };
  // The walkable slab stays level. Swept metal sectors have shallow seams, not a checkerboard.
  detail.box([35.15,.018,39.1],[0,.014,98],deck);
  for(let i=0;i<12;i++){
    const t=i*Math.PI/6,shape=new THREE.Shape();
    shape.absarc(0,0,15.2,t+.009,t+Math.PI/6-.009,false);
    shape.quadraticCurveTo(Math.cos(t+.33)*10,Math.sin(t+.33)*10,Math.cos(t+.22)*6.15,Math.sin(t+.22)*6.15);
    shape.absarc(0,0,6.15,t+.22,t+.015,true);shape.closePath();
    const g=new THREE.ShapeGeometry(shape,36);g.rotateX(-Math.PI/2);g.translate(0,.033,100);
    detail.add(g,i%3===0?deckAlt:deck);
    const seam:Point[]=[];for(let j=0;j<=24;j++){const r=6.2+j/24*8.8,angle=t+.13*Math.sin(j/24*Math.PI);seam.push([Math.cos(angle)*r,.051,100+Math.sin(angle)*r]);}
    detail.curve(seam,.018,dark,32);
  }
  for(const side of [-1,1]){
    detail.curve([[side*3.7,.05,78.5],[side*3.7,.05,85],[side*6.3,.05,90],[side*9,.05,95]],.024,dimBlue,36);
    detail.curve([[side*9,.05,95],[side*10.9,.05,103],[side*8.9,.05,111],[side*4,.05,116]],.02,edge,40);
  }
  // Thick curved ribs rise out of wall haunches and converge above the vessel.
  // The entrance and archive-link keep their existing rectangular clear apertures.
  for(const z of [81,93,109,116])for(const side of [-1,1]){
    const rib=new THREE.Shape();rib.moveTo(side*16.45,0);rib.lineTo(side*17.5,0);
    rib.bezierCurveTo(side*17.6,8,side*14.7,14.3,side*9,16.6);
    rib.quadraticCurveTo(side*4.9,18.1,0,18.1);rib.lineTo(0,16.75);
    rib.quadraticCurveTo(side*5.8,16.7,side*9.8,14.5);
    rib.bezierCurveTo(side*14.6,12,side*15.8,5.1,side*16.45,0);rib.closePath();
    profile(rib,1.35,[0,0,z],steel,'solar-vault-curved-load-rib');
    const band=new THREE.Shape();band.moveTo(side*16.55,.5);
    band.bezierCurveTo(side*16.4,7,side*13.9,13.4,side*8.8,15.4);
    band.quadraticCurveTo(side*4.6,17,0,17.25);band.lineTo(0,17.6);
    band.quadraticCurveTo(side*5.6,17.4,side*9.2,15.8);
    band.bezierCurveTo(side*14.4,13.8,side*16.9,7,side*16.9,.5);band.closePath();
    profile(band,.16,[0,0,z-.82],edge,'solar-vault-inset-arch-band');
    detail.curve([[side*16.2,2,z-.96],[side*15.4,8,z-.96],[side*11.5,13.6,z-.96],[side*5.8,16.1,z-.96]],.027,dimBlue,40);
  }
  // Layered wall leaves, placed behind the ribs, make deep service cavities.
  for(const side of [-1,1])for(const z of [96,111]){
    const leaf=new THREE.Shape();leaf.moveTo(0,0);leaf.bezierCurveTo(-3,2,-4,6,-3,10);
    leaf.quadraticCurveTo(-1.7,12,0,13.7);leaf.quadraticCurveTo(2.7,10.5,3.7,7);
    leaf.bezierCurveTo(4,3,2,1,0,0);leaf.closePath();
    const g=new THREE.ExtrudeGeometry(leaf,{depth:.38,steps:1,bevelEnabled:true,bevelSize:.1,bevelThickness:.1,bevelSegments:2,curveSegments:30});
    g.rotateY(side<0?Math.PI/2:-Math.PI/2);g.translate(side*17.15,1,z);a.add(g,dark);
    detail.curve([[side*16.72,2,z],[side*16.73,5,z+1.5],[side*16.72,9,z+2],[side*16.72,13,z]],.07,edge,36);
  }
  // Star-like depth wells are bounded blue cavities between structural ribs,
  // not exterior holes. Low brightness preserves the metal containment silhouette.
  const wellMaterial=new THREE.ShaderMaterial({side:THREE.DoubleSide,depthWrite:true,
    uniforms:{},vertexShader:`varying vec2 vUv;
#include <common>
#include <logdepthbuf_pars_vertex>
void main(){vUv=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);
#include <logdepthbuf_vertex>
}`,fragmentShader:`varying vec2 vUv;
#include <common>
#include <logdepthbuf_pars_fragment>
float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
void main(){
#include <logdepthbuf_fragment>
vec2 q=vUv*vec2(13.,6.);float cloud=.5+.25*sin(q.x+sin(q.y*1.8))+.2*sin(q.y*2.1+q.x*.7);vec2 cell=floor(vUv*vec2(190.,88.));float star=step(.996,hash(cell))*pow(max(0.,1.-length(fract(vUv*vec2(190.,88.))-.5)*2.),4.);vec3 c=mix(vec3(.006,.012,.022),vec3(.022,.055,.092),cloud)+star*vec3(.24,.36,.43);gl_FragColor=vec4(c,1.);
#include <tonemapping_fragment>
#include <colorspace_fragment>
}`});
  for(const side of [-1,1]){
    const well=new THREE.Mesh(new THREE.PlaneGeometry(24,11),wellMaterial);
    well.name='solar-core-bounded-star-depth-well';well.position.set(side*17.5,11.7,103);well.rotation.y=side<0?Math.PI/2:-Math.PI/2;
    group.add(well);
  }
  // Layered supporting island, with actual narrow supports rather than a solid giant block.
  detail.add(new THREE.CylinderGeometry(5.4,5.7,.65,80).translate(0,.325,100),dark);
  collision.addCylinder(new THREE.Vector3(0,.325,100),5.7,.65,{tag:'core-plinth',owner:'solar-core',part:'lower-plinth'});
  detail.add(new THREE.CylinderGeometry(3.3,4.3,1.2,48).translate(0,1.2,100),armourShade);
  collision.addCylinder(new THREE.Vector3(0,1.2,100),4.3,1.2,{tag:'core-plinth',owner:'solar-core',part:'upper-seat'});
  a.add(new THREE.CylinderGeometry(1.9,2.6,2.5,20).translate(0,2.75,100),dark);
  a.add(new THREE.CylinderGeometry(3.1,2.1,.65,24).translate(0,4.25,100),armour);
  // Six stationary hooked cradle arms. Empty air remains visible between them.
  for(let i=0;i<6;i++){
    const angle=i*Math.PI/3+.1,arm=new THREE.Shape();
    const frontPair=i===1||i===2,shoulder=frontPair?4.25:5.4,tip=frontPair?4.65:5.9;
    arm.moveTo(1.6,.7);arm.lineTo(4.8,.7);arm.bezierCurveTo(6,1.7,6,3.2,5.2,shoulder);
    arm.lineTo(4.65,tip);arm.bezierCurveTo(5.1,3.2,4.3,2,2,1.7);arm.closePath();
    const g=new THREE.ExtrudeGeometry(arm,{depth:.85,steps:1,bevelEnabled:true,bevelSize:.13,bevelThickness:.13,bevelSegments:3,curveSegments:24});
    g.translate(0,0,-.425);g.rotateY(angle);g.translate(0,0,100);a.add(g,i%2?armourShade:steel);
  }
  // Huge CLOSED containment vessel. Fine panel gaps expose its dark structural skin.
  const center=new THREE.Vector3(0,10,100),radii=new THREE.Vector3(6.65,6.65,5.9);
  const shell=geometryMesh('solar-core-armoured-containment',new THREE.SphereGeometry(1,80,48),dark);
  shell.position.copy(center);shell.scale.copy(radii);
  const surface=(theta:number,phi:number,lift=0)=>{
    const twist=.12*Math.sin(phi*2);
    return new THREE.Vector3((radii.x+lift)*Math.sin(phi)*Math.sin(theta+twist),
      center.y+(radii.y+lift)*Math.cos(phi),center.z-(radii.z+lift)*Math.sin(phi)*Math.cos(theta+twist));
  };
  const panelPatch=(theta0:number,theta1:number,phi0:number,phi1:number,mat:THREE.Material)=>{
    const vertices:number[]=[],indices:number[]=[],nx=9,ny=10,layer=(nx+1)*(ny+1);
    for(let back=0;back<2;back++)for(let y=0;y<=ny;y++)for(let x=0;x<=nx;x++){
      const v=y/ny,u=x/nx,phi=phi0+(phi1-phi0)*v;
      const wave=.035*Math.sin(phi*2),theta=theta0+(theta1-theta0)*u+wave;
      const p=surface(theta,phi,back?0:.14);vertices.push(p.x,p.y,p.z);
    }
    for(let y=0;y<ny;y++)for(let x=0;x<nx;x++){
      const i=y*(nx+1)+x,j=i+nx+1;indices.push(i,i+1,j,i+1,j+1,j,layer+i,layer+j,layer+i+1,layer+i+1,layer+j,layer+j+1);
    }
    const connect=(i:number,j:number)=>indices.push(i,j,i+layer,j,j+layer,i+layer);
    for(let x=0;x<nx;x++){connect(x,x+1);connect(ny*(nx+1)+x+1,ny*(nx+1)+x);}
    for(let y=0;y<ny;y++){connect((y+1)*(nx+1),y*(nx+1));connect(y*(nx+1)+nx,(y+1)*(nx+1)+nx);}
    const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(vertices,3));g.setIndex(indices);g.computeVertexNormals();a.add(g,mat);
    const seam:Point[]=[];for(let k=0;k<=22;k++){const phi=phi0+(phi1-phi0)*k/22,p=surface(theta0+.035*Math.sin(phi*2),phi,.175);seam.push(p.toArray() as Point);}
    detail.curve(seam,.025,edge,28);
  };
  for(let i=0;i<10;i++)for(let j=0;j<3;j++){
    // Offset seams by longitude; shared meridians use phi-based twist, so plates never overlap.
    const stagger=(i%2?1:-1)*.035;
    const p0=[.14,.98+stagger,1.93+stagger][j]+.006,p1=[.98+stagger,1.93+stagger,3.0][j]-.006;
    panelPatch(i*Math.PI/5+.006,(i+1)*Math.PI/5-.006,p0,p1,j===2?armourShade:armour);
  }
  // The front's long pointed central plate is its defining campaign silhouette.
  const frontPlate=new THREE.Shape();frontPlate.moveTo(0,-4.7);frontPlate.bezierCurveTo(-1.5,-2.8,-2,1,-1.3,4.4);
  frontPlate.quadraticCurveTo(-.6,5.25,0,5.5);frontPlate.quadraticCurveTo(.6,5.25,1.3,4.4);
  frontPlate.bezierCurveTo(2,1,1.5,-2.8,0,-4.7);frontPlate.closePath();
  const front=new THREE.ExtrudeGeometry(frontPlate,{depth:.12,steps:1,bevelEnabled:false,curveSegments:40});
  const pos=front.getAttribute('position');for(let i=0;i<pos.count;i++){
    const x=pos.getX(i),y=pos.getY(i),z=-Math.sqrt(Math.max(.025,1-x*x/(6.8*6.8)-y*y/(6.8*6.8)))*6.08-pos.getZ(i);
    pos.setXYZ(i,x,10+y,100+z);
  }
  // Mapping extrusion depth toward -Z reverses handedness: restore outward winding.
  for(let i=0;i<pos.count;i+=3){const x=pos.getX(i+1),y=pos.getY(i+1),z=pos.getZ(i+1);pos.setXYZ(i+1,pos.getX(i+2),pos.getY(i+2),pos.getZ(i+2));pos.setXYZ(i+2,x,y,z);}
  front.computeVertexNormals();a.add(front,armourShade);
  const crest=geometryMesh('solar-containment-diamond-crest',new THREE.OctahedronGeometry(.4),blue,group);
  crest.position.set(0,14.45,95.4);crest.scale.set(.7,1,.32);
  // Sparse embedded blue-white status ticks, not an emissive blue surface.
  for(const theta of [-.66,.66,2.5,3.8]){
    for(let j=0;j<10;j++){
      const p=surface(theta,1.08+j*.035,.2),tick=new THREE.BoxGeometry(.07,.095,.04);
      tick.rotateY(-theta);tick.translate(p.x,p.y,p.z);detail.add(tick,j%3===0?pearl:blue);
    }
    for(const phi of [.53,1.9]){const p=surface(theta,phi,.2);detail.add(new THREE.SphereGeometry(.075,10,6).translate(p.x,p.y,p.z),pearl);}
  }
  // Three compact, recessed blue oval ports, not protruding fluorescent tubes.
  for(const x of [-.8,0,.8]){
    a.add(new THREE.CylinderGeometry(.34,.38,1.35,16).translate(x,3.45,94.9),dark);
    detail.add(new THREE.SphereGeometry(1,24,16).scale(.21,.45,.10).translate(x,3.5,94.51),windowBlue);
    a.add(new THREE.TorusGeometry(.245,.045,8,36).scale(1,1.9,.7).translate(x,3.5,94.4),edge);
    for(const y of [2.72,4.16])a.add(new THREE.CylinderGeometry(.38,.38,.13,16).translate(x,y,94.9),edge);
  }
  const manifoldFork=new THREE.Shape();manifoldFork.moveTo(-1.8,.65);manifoldFork.lineTo(-1.2,2.5);
  manifoldFork.lineTo(1.2,2.5);manifoldFork.lineTo(1.8,.65);manifoldFork.lineTo(.9,.65);
  manifoldFork.lineTo(.4,1.6);manifoldFork.lineTo(-.4,1.6);manifoldFork.lineTo(-.9,.65);manifoldFork.closePath();
  profile(manifoldFork,1.1,[0,0,94.9],armourShade,'solar-inspection-manifold-fork');
  a.box([4.25,.3,1.4],[0,2.5,94.9],armour);
  for(let i=0;i<11;i++)detail.box([.055,.55,.03],[(i-5)*.27,2.01,94.17],blue);
  // Low segmented service wings echo the reference's sculpted apron; station
  // fronts at x=±9.1,z=98 and all four approach routes remain unobstructed.
  for(const side of [-1,1]){
    const wing=new THREE.Shape();wing.moveTo(side*6.2,0);wing.lineTo(side*15.3,0);
    wing.lineTo(side*15.3,1.65);wing.quadraticCurveTo(side*11.2,2.5,side*6.2,1.1);wing.closePath();
    profile(wing,1.25,[0,0,112],dark,'solar-low-service-wing');
    const brow=new THREE.Shape();brow.moveTo(side*6.3,1);brow.quadraticCurveTo(side*11.2,2.35,side*15.3,1.55);
    brow.lineTo(side*15.3,1.9);brow.quadraticCurveTo(side*11.2,2.8,side*6.3,1.35);brow.closePath();
    profile(brow,1.4,[0,0,112],armour,'solar-wing-armoured-brow');
    detail.add(new THREE.OctahedronGeometry(.32).scale(1,1,.35).translate(side*12.5,1.66,111.2),blue);
  }
  // Only non-solid optical traces animate. Every mechanical piece is static and
  // snapshots its real triangles (including holes between cradle arms).
  const optical=new THREE.Group();optical.name='solar-core-non-solid-energy-projection';optical.userData.nonSolid=true;group.add(optical);
  const glowMaterial=new THREE.MeshBasicMaterial({color:0x78ceff,transparent:true,opacity:.28,depthWrite:false,blending:THREE.AdditiveBlending});
  for(let i=0;i<3;i++){
    const trace=new THREE.Mesh(new THREE.TorusGeometry(.20,.01,5,36,Math.PI*1.3),glowMaterial);
    trace.position.set((i-1)*.8,3.5,94.39);trace.rotation.y=.1;optical.add(trace);
  }
  a.finish();detail.finish();
  collision.addStaticMesh(staticParts,{tag:'core-heart',owner:'solar-core',part:'static-containment-and-vault'});
  const lamp=(at:Point,color:number,power:number,distance:number)=>{const l=new THREE.PointLight(color,power,distance,2);l.position.set(...at);group.add(l);};
  lamp([0,7,90],0xd7d5b7,280,26);lamp([0,4,93],0x65c5ff,23,11);
  for(const side of [-1,1]){lamp([side*11,11,97],0x9aaeca,155,28);lamp([side*13,7,110],0x3f77ad,90,24);}
  let elapsed=0;
  const update=(dt:number)=>{if(!Number.isFinite(dt)||dt<=0)return;elapsed+=Math.min(dt,.1);optical.children.forEach((o,i)=>{o.rotation.z=elapsed*.8+i;});glowMaterial.opacity=.23+Math.sin(elapsed*1.7)*.055;};
  group.userData.update=update;group.userData.clearApproaches=[[-9.1,98],[9.1,98],[0,86],[20,86]];
  return {group,update};
}
