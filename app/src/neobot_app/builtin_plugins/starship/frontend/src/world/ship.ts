import * as THREE from 'three';
import { CollisionWorld } from '../core/collision';
import type { LadderVolume } from '../core/player';
import { SECTORS, STATIONS, type StationSpec } from './deckplan';
import { createShipMaterials, createSignTexture, type ShipMaterials } from './materials';
import { Architecture, type Point } from './geometry';
import { buildArkHull } from './hull';
import { ARK_DIMENSIONS } from './scale';
import { buildSanctum } from './sanctum';
import { applyHabitatClearance } from './habitat-clearance';
import { buildInteriorRooms } from './interior';
import { buildArchiveRelief } from './archive-relief';
import { buildGoldenFleet } from '../space/golden-fleet';
import { buildArkExhaust } from './ark-exhaust';

export interface RoomBounds {
  id:string; label:string; description:string; deck:number; min:THREE.Vector3; max:THREE.Vector3;
}
export interface StationAnchor {
  spec:StationSpec; position:THREE.Vector3; yaw:number; roomLabel:string; deck:number;
}
export interface ShipBuild {
  group:THREE.Group; materials:ShipMaterials; rooms:RoomBounds[];
  anchors:Map<string,StationAnchor>; ladders:LadderVolume[];
  spawn:THREE.Vector3; spawnYaw:number; hullBounds:THREE.Box3;
  setName(name:string):void; dispose():void;
}
/** Free-standing cathedral bridge and twin foundries. No legacy tiled corridors. */
export function buildShip(scene:THREE.Scene, collision:CollisionWorld, _notify?:(s:string)=>void):ShipBuild {
  const group=new THREE.Group(); group.name='ark-inhabited-enclave';
  const materials=createShipMaterials(), a=new Architecture(group);
  const gold=materials.hull, pale=materials.wallAccent, dark=materials.wall, glow=materials.trim;
  const solid=(size:Point,at:Point,mat:THREE.Material,tag='architecture')=>{
    a.box(size,at,mat);collision.addFromCenter(new THREE.Vector3(...at),new THREE.Vector3(...size),tag);
  };
  const rooms:RoomBounds[]=SECTORS.map(s=>({id:s.id,label:s.label,description:s.description,deck:0,
    min:new THREE.Vector3(s.bounds[0],0,s.bounds[2]),max:new THREE.Vector3(s.bounds[1],18,s.bounds[3])}));
  solid([48,1.2,42],[0,-.6,-21],materials.floor,'floor');
  solid([10,1.2,14],[0,-.6,7],materials.floor,'floor');
  solid([64,1.2,44],[0,-.6,36],materials.floor,'floor');
  const boundary=(size:Point,at:Point,tag:string)=>collision.addFromCenter(new THREE.Vector3(...at),new THREE.Vector3(...size),tag);
  for(const s of [-1,1]) {
    boundary([.28,24,42],[s*24,12,-21],'shield');
    boundary([.4,40,44],[s*32,20,36],'foundry-rail');
    boundary([19,20,.6],[s*14.5,10,0],'rear-bulkhead');
    boundary([27,40,.6],[s*18.5,20,14],'foundry-bulkhead');
    solid([.6,10,14],[s*5,5,7],dark,'corridor-wall');
    a.box([.07,.04,14],[s*3.7,.055,7],glow);
    for(const z of [1,7,13]) {
      a.curve([[s*4.8,0,z],[s*4.7,5,z],[s*3,8,z],[0,10,z]],.24,gold);
      a.curve([[s*4.5,.4,z],[s*4.4,4.8,z],[s*2.8,7.7,z]],.022,glow);
    }
  }
  boundary([48,24,.28],[0,12,-42],'shield');
  boundary([48,.2,42],[0,24,-21],'shield-roof');

  solid([10,.6,14],[0,10,7],dark,'ceiling');
  // The rear opening now connects to actual rooms; interior.ts owns its aligned door.
  a.finish();
  const sanctum=buildSanctum(materials,collision);group.add(sanctum.group);
  // Match solid curved pylons and rails; never turn the psionic field into a box.
  collision.addStaticMesh(sanctum.group,{tag:'bridge-structure',owner:'sanctum',
    filter:mesh=>{
      const mats=Array.isArray(mesh.material)?mesh.material:[mesh.material];
      return mats.some(mat=>mat instanceof THREE.MeshStandardMaterial&&!mat.transparent&&mat!==materials.trim);
    }});
  const interior=buildInteriorRooms(materials,collision);group.add(interior.group);
  group.add(buildArchiveRelief(materials,collision));
  group.traverse(o=>{if(o instanceof THREE.Mesh)o.receiveShadow=true;});
  const hull=buildArkHull(materials);
  const designBounds=new THREE.Box3().setFromObject(hull),designSize=designBounds.getSize(new THREE.Vector3());
  const dimensions=new THREE.Vector3(ARK_DIMENSIONS.width,ARK_DIMENSIONS.height,ARK_DIMENSIONS.length);
  hull.scale.copy(dimensions.divide(designSize));
  const mount=hull.userData.mountPoint as number[]|undefined;
  const mountPoint=new THREE.Vector3(...(mount??[0,0,-300]) as [number,number,number]);
  hull.position.copy(mountPoint.multiply(hull.scale).negate());hull.position.y-=1.25;
  hull.updateMatrixWorld(true);
  applyHabitatClearance(hull);
  const physicalHullBounds=new THREE.Box3().setFromObject(hull);
  hull.traverse(o=>o.layers.set(1));
  group.add(hull);
  // Activated only by exterior views; light layers alone do not isolate illumination.
  const exteriorKey=new THREE.DirectionalLight(0xffebce,1.9);exteriorKey.position.set(-1,2,-1.2);exteriorKey.layers.set(1);exteriorKey.userData.exteriorOnly=true;exteriorKey.visible=false;group.add(exteriorKey);
  const exteriorRim=new THREE.DirectionalLight(0x8ec6ff,.95);exteriorRim.position.set(2,.5,1);exteriorRim.layers.set(1);exteriorRim.userData.exteriorOnly=true;exteriorRim.visible=false;group.add(exteriorRim);
  const exteriorFill=new THREE.HemisphereLight(0x9ba8bc,0x121a29,.6);exteriorFill.layers.set(1);exteriorFill.userData.exteriorOnly=true;exteriorFill.visible=false;group.add(exteriorFill);
  // Effects and companion craft are separate from the physical 74.4 km hull bounds.
  const fleet=buildGoldenFleet(hull),exhaust=buildArkExhaust(hull);
  group.add(fleet.group,exhaust.group);
  group.userData.update=(dt:number,position?:THREE.Vector3,power=.55)=>{
    sanctum.group.userData.update(dt);
    if(position)interior.update(dt,position);
    fleet.update(dt);exhaust.update(dt,power);
  };
  const sign=(title:string,sub:string,at:Point,width:number,yaw=0)=>{
    const mesh=new THREE.Mesh(new THREE.PlaneGeometry(width,width*.25),new THREE.MeshBasicMaterial({
      map:createSignTexture(title,sub,{width:1024,height:256,accent:'#d3b77c'}),side:THREE.FrontSide}));
    const back=new THREE.Mesh(mesh.geometry,mesh.material);back.rotation.y=Math.PI;back.position.z=-.015;mesh.add(back);
    mesh.position.set(...at);mesh.rotation.y=yaw;group.add(mesh);return mesh;
  };
  sign('战争机械装配车间','WAR COUNCIL / MECHANICAL FORGE',[-18,3.2,14.8],5.5,Math.PI);
  sign('机器人装配车间','AUTOMATON ASSEMBLY',[18,3.2,14.8],5.5,Math.PI);

  const anchors=new Map<string,StationAnchor>();
  for(const spec of STATIONS) {
    const room=rooms.find(r=>r.id===spec.room)!;
    const position=new THREE.Vector3((room.min.x+room.max.x)/2+spec.offset[0],0,(room.min.z+room.max.z)/2+spec.offset[1]);
    anchors.set(spec.id,{spec,position,yaw:spec.yaw,roomLabel:room.label,deck:0});
    // The actual solid console meshes are registered after terminal construction.
  }
  group.add(new THREE.HemisphereLight(0x526e91,0x080b10,.48));
  const key=new THREE.DirectionalLight(0xc7d8e5,.85);key.position.set(-80,150,-120);group.add(key);
  key.castShadow=true;key.shadow.mapSize.set(2048,2048);
  Object.assign(key.shadow.camera,{left:-75,right:75,top:95,bottom:-95,near:1,far:350});
  key.shadow.bias=-.0003;key.shadow.normalBias=.035;
  const rim=new THREE.DirectionalLight(0x396ef0,.9);rim.position.set(80,40,50);group.add(rim);
  const fill=new THREE.PointLight(0x3b74df,38,45,1.7);fill.position.set(0,9,-21);group.add(fill);
  scene.add(group);
  return {group,materials,rooms,anchors,ladders:[],spawn:new THREE.Vector3(0,.08,-11.5),spawnYaw:0,
    hullBounds:physicalHullBounds,
    setName(name:string) {
      sanctum.setName(name);
    },
    dispose(){fleet.dispose();exhaust.dispose();group.remove(fleet.group,exhaust.group);scene.remove(group);disposeTree(group);},
  };
}
/** Dispose unique resources once; terminal rigs must be removed before the ship. */
export function disposeTree(root:THREE.Object3D):void {
  const geometries=new Set<THREE.BufferGeometry>(), mats=new Set<THREE.Material>(), textures=new Set<THREE.Texture>();
  root.traverse(o=>{const m=o as THREE.Mesh;if(m.geometry)geometries.add(m.geometry);
    if(m.material)for(const mat of Array.isArray(m.material)?m.material:[m.material])mats.add(mat);});
  for(const mat of mats){for(const value of Object.values(mat))if(value instanceof THREE.Texture)textures.add(value);mat.dispose();}
  for(const t of textures)t.dispose();for(const g of geometries)g.dispose();
}
export function roomAt(rooms:RoomBounds[],p:THREE.Vector3):RoomBounds|null {
  return rooms.find(r=>p.x>=r.min.x&&p.x<=r.max.x&&p.z>=r.min.z&&p.z<=r.max.z&&p.y>=-.5&&p.y<r.max.y)??null;
}
