/** Inhabited compartments, in metres. Owns rear floors and real, collidable walls.
 * The caller retains bridge/front-corridor/foundry slabs; remove the old z=58 gate.
 * No decorative object here registers an interaction or pretends to be a feature. */
import * as THREE from 'three';
import { Architecture, type Point } from './geometry';
import { buildSolarCore } from './solar-core';
import { createSignTexture, type ShipMaterials } from './materials';
import { PLAYER_RADIUS, type Box, type CollisionWorld } from '../core/collision';

export interface InteriorRooms {
  group: THREE.Group;
  /** Feet in world coordinates; call before player collision movement each frame. */
  update(dt: number, playerPosition: THREE.Vector3): void;
}
interface SlidingDoor {
  id: string; x: number; z: number; alongX: boolean; width: number;
  fraction: number; hold: number;
  leaves: { mesh: THREE.Group; box: Box; sign: number }[];
}

export function buildInteriorRooms(m: ShipMaterials, collision: CollisionWorld): InteriorRooms {
  const group = new THREE.Group(); group.name = 'inhabited-interior-rooms';
  const a = new Architecture(group), doors: SlidingDoor[] = [];
  const finish = (name: string, color: number, metalness = .35) => {
    const mat = new THREE.MeshStandardMaterial({ color, metalness, roughness: .57 });
    mat.name = name; return mat;
  };
  const warmFloor = finish('war-forge-bronze-deck', 0x54483c, .55);
  const coolFloor = finish('robot-forge-blue-ceramic-deck', 0x34515e);
  const ivory = finish('archive-ivory-ceramic', 0xada58d, .18);
  const slate = finish('core-slate-blue-deck', 0x33485e, .45);
  const panel = finish('interior-warm-stone-panels', 0x726c60);
  const navy = finish('solar-core-deep-navy', 0x07172f, .65);
  navy.emissive.setHex(0x09275e); navy.emissiveIntensity = .6;
  const blue = new THREE.MeshBasicMaterial({ color: 0x4b99ce });
  const amber = new THREE.MeshBasicMaterial({ color: 0xc4a367 });
  const violet = new THREE.MeshBasicMaterial({ color: 0x7c8cac });
  const solid = (size: Point, at: Point, mat: THREE.Material, tag: string) => {
    a.box(size, at, mat);
    collision.addFromCenter(new THREE.Vector3(...at), new THREE.Vector3(...size), tag);
  };
  const floor = (x0: number, x1: number, z0: number, z1: number, mat: THREE.Material) =>
    solid([x1-x0, 1.2, z1-z0], [(x0+x1)/2, -.6, (z0+z1)/2], mat, 'floor');
  const light = (name: string, at: Point, color: number, power: number, distance: number) => {
    const lamp = new THREE.PointLight(color, power, distance, 2);
    lamp.name = name; lamp.position.set(...at); group.add(lamp);
  };
  const sign = (title: string, sub: string, at: Point, width: number, yaw = 0) => {
    const mesh = new THREE.Mesh(new THREE.PlaneGeometry(width, width/4),
      new THREE.MeshBasicMaterial({ map: createSignTexture(title, sub, { width: 1024, height: 256, accent: '#c5ad7e' }), side: THREE.DoubleSide }));
    mesh.position.set(...at); mesh.rotation.y = yaw; group.add(mesh);
  };
  // Local u is across the doorway, v is its wall normal. Shared dimensions mean
  // the lintel, jambs, panels and moving AABBs cannot disagree about the opening.
  const door = (id: string, x: number, z: number, alongX: boolean, width = 6, height = 6) => {
    const world = (u: number, y: number, v: number): Point => alongX ? [x+u,y,z+v] : [x+v,y,z+u];
    const size = (u: number, y: number, v: number): Point => alongX ? [u,y,v] : [v,y,u];
    const d: SlidingDoor = { id, x, z, alongX, width, fraction: 0, hold: 0, leaves: [] };
    for (const s of [-1,1]) {
      // A 3cm rebate overlaps the wall reveal, avoiding coplanar side-face shimmer.
      solid(size(.36,height,.9), world(s*(width/2+.15),height/2,0), m.hull, 'door-jamb');
      a.box(size(.035,height-.2,.94),world(s*(width/2+.025),height/2,0),blue);
      // Recessed pockets keep the moving leaves out of circulation space.
      a.box(size(width/2+.25,height+.3,.12),world(s*(width*.75+.2),height/2,.34),m.wall);
      const leaf = new THREE.Group(); leaf.name = id + (s<0 ? '-left-leaf' : '-right-leaf');
      const b = new Architecture(leaf);
      b.box(size(width/2,height,.26), [0,height/2,0], m.wall);
      b.box(size(width/2-.2,height-.3,.3), [0,height/2,0], panel);
      for (const face of [-1,1]) {
        b.box(size(.13,height-.5,.01), alongX ? [s*(width/4-.15),height/2,face*.155] : [face*.155,height/2,s*(width/4-.15)], m.hull);
        b.box(size(.035,height*.56,.01), alongX ? [-s*(width/4-.14),height/2,face*.155] : [face*.155,height/2,-s*(width/4-.14)], blue);
        b.box(size(width/2-.6,.13,.01), alongX ? [0,height*.75,face*.155] : [face*.155,height*.75,0], m.hull);
      }
      b.finish(); group.add(leaf);
      const box: Box = { min: new THREE.Vector3(), max: new THREE.Vector3(), tag: 'door:' + id };
      collision.addBox(box); d.leaves.push({ mesh: leaf, box, sign: s });
    }
    solid(size(width+.6,.35,.9),world(0,height+.175,0),m.hull,'door-lintel');
    // Flat, flush threshold; never a raised trip block.
    a.box(size(width,.012,.8),world(0,.018,0),m.hull);
    const place = () => {
      for (const leaf of d.leaves) {
        const u = leaf.sign*(width/4 + d.fraction*(width/2+.18));
        leaf.mesh.position.set(...world(u,0,0));
        const half = new THREE.Vector3(...size(width/2,height,.32)).multiplyScalar(.5);
        const center = new THREE.Vector3(...world(u,height/2,0));
        leaf.box.min.copy(center).sub(half); leaf.box.max.copy(center).add(half);
      }
    };
    place(); doors.push(d); return place;
  };
  const placeDoors: (() => void)[] = [];
  // Solid wall containing exact rectangular apertures, with no unmatched arch void.
  const wall = (alongX: boolean, fixed: number, lo: number, hi: number, height: number,
    openings: { center: number; width: number; height: number; id: string }[] = [], thickness = .6, mat: THREE.Material = panel) => {
    const piece = (from: number, to: number, bottom: number, top: number) => {
      if (to <= from || top <= bottom) return;
      solid(alongX ? [to-from,top-bottom,thickness] : [thickness,top-bottom,to-from],
        alongX ? [(from+to)/2,(top+bottom)/2,fixed] : [fixed,(top+bottom)/2,(from+to)/2],mat,'interior-wall');
    };
    let cursor = lo;
    for (const o of openings) {
      piece(cursor,o.center-o.width/2,0,height);
      piece(o.center-o.width/2,o.center+o.width/2,o.height,height);
      placeDoors.push(door(o.id,alongX ? o.center : fixed,alongX ? fixed : o.center,alongX,o.width,o.height));
      cursor = o.center+o.width/2;
    }
    piece(cursor,hi,0,height);
  };

  // Two separate 34 m high industrial chambers, preserving the 25 m colossus.
  // 30 cm partition skins leave all old x=±9 console approaches clear.
  for (const side of [-1,1]) {
    const x0 = side<0 ? -32 : 5.5, x1 = side<0 ? -5.5 : 32;
    const deck = side<0 ? warmFloor : coolFloor, glow = side<0 ? amber : blue;
    wall(false,side*5.5,14,58,34,[
      {center:29,width:6,height:6,id:side<0?'war-fore':'robot-fore'},
      {center:43,width:6,height:6,id:side<0?'war-aft':'robot-aft'},
    ],.3,m.wall);
    wall(false,side*32,14,58,34,[],.6,m.wall);
    for (const z of [14,58]) wall(true,z,x0,x1,34,[],.6,m.wall);
    solid([26.5,.5,44],[(x0+x1)/2,34.25,36],m.ceiling,'ceiling');
    // Longitudinal workshop panels vs cross-laid robot tiles: visibly different floors.
    for(let ix=0;ix<4;ix++) for(let iz=0;iz<8;iz++) {
      const w=(x1-x0)/4, d=44/8;
      a.box([w-.09,.016,d-.1],[x0+w*(ix+.5),.015,14+d*(iz+.5)],(ix+iz)%4===0?m.floor:deck);
      if(side<0) a.box([.055,.009,d-.5],[x0+w*(ix+.5),.029,14+d*(iz+.5)],m.hull);
      else a.box([w-.5,.009,.045],[x0+w*(ix+.5),.029,14+d*(iz+.5)],m.wallAccent);
    }
    // Doorways and consoles remain unobstructed; ornament is above head height.
    for(const z of [19,36,53]) {
      a.box([.08,3.5,3.6],[side*5.69,10,z],m.hull);
      a.box([.1,2.5,2.8],[side*5.7,10,z],deck);
      a.box([.13,.08,2.3],[side*5.71,10,z],glow);
      a.box([.35,30,.6],[side*31.5,15,z],m.hull);
    }
    // Broad raised armour fields catch local light: not a black empty box.
    for(const z of [25,46]) {
      a.box([.16,20,12],[side*31.55,12,z],side<0?warmFloor:coolFloor);
      const shield=new THREE.Shape();shield.moveTo(-4,0);shield.lineTo(-4.7,10);
      shield.quadraticCurveTo(-4.2,16,0,19);shield.quadraticCurveTo(4.2,16,4.7,10);
      shield.lineTo(4,0);shield.lineTo(0,2);shield.closePath();
      const relief=new THREE.ExtrudeGeometry(shield,{depth:.22,bevelEnabled:true,bevelSize:.08,bevelThickness:.05,bevelSegments:2,steps:1});
      relief.rotateY(side<0?Math.PI/2:-Math.PI/2);relief.translate(side*31.35,2,z);a.add(relief,side<0?m.hull:m.wallAccent);
      a.box([.1,11,.16],[side*31.02,11,z],glow);
      a.box([.24,.28,13],[side*31.2,4,z],m.hull);
    }
    for(const z of [29,43]) {
      sign(side<0?'战争机械':'机器人装配','ASSEMBLY / SIDE ACCESS',[side*5.31,7.6,z],4,side<0?Math.PI/2:-Math.PI/2);
      a.box([3.6,.025,.07],[side*7.5,.043,z],glow);
    }
    light(side<0?'war-warm-service':'robot-cool-service',[side*10,7,36],side<0?0xd7b27b:0x8ab8d7,130,34);
  }
  // Axial route is deliberately lighter than the two work floors.
  for(let z=16;z<58;z+=4) a.box([9.8,.018,3.9],[0,.022,z],slate);
  for(const side of [-1,1]) a.box([.06,.02,44],[side*3.9,.045,36],blue);
  solid([11,.4,44],[0,10.6,36],m.ceiling,'ceiling');
  for(const z of [22,38,52]) { a.box([7,.08,.4],[0,10.34,z],amber); light('axis-downlight',[0,7.5,z],0x9cb7d3,95,22); }

  floor(-6,6,58,78,slate);
  wall(true,58,-5.5,5.5,10.8,[{center:0,width:7.2,height:7,id:'rear-transit'}],.7,m.wall);
  for(const side of [-1,1]) {
    wall(false,side*6,58,78,11,[],.6,panel);
    a.box([.075,.02,20],[side*3.8,.04,68],blue);
    for(const z of [62,68,74]) {
      a.box([.08,5,1.1],[side*5.65,4,z],m.hull);
      a.box([.09,3.6,.18],[side*5.59,4,z],blue);
    }
  }
  for(let z=60;z<78;z+=4) a.box([7.2,.015,3.8],[0,.018,z],m.floor);
  solid([12,.5,20],[0,11.25,68],m.ceiling,'ceiling');
  light('rear-corridor-fill',[0,6,68],0x9ab4d3,135,26);
  sign('太阳核心 / 记忆资料室','SOLAR CORE / ARCHIVES',[0,8.2,57.57],5.8,Math.PI);

  // Core: an enclosed rotunda expressed inside a rectangular airtight shell.
  floor(-18,18,78,118,slate);
  wall(true,78,-18,18,18,[{center:0,width:8,height:8,id:'core-entry'}],.8,m.wall);
  wall(true,118,-18,18,18,[],.8,m.wall);
  // Explicit final sealed boundary, not the old gate at z=58.
  collision.addFromCenter(new THREE.Vector3(0,35,118),new THREE.Vector3(36,70,.8),'sealed-sector');
  wall(false,-18,78,118,18,[],.8,m.wall);
  wall(false,18,78,118,18,[{center:86,width:8,height:7,id:'archive-entry'}],.8,m.wall);
  solid([36,.6,40],[0,18.3,98],m.ceiling,'ceiling');
  const solarCore=buildSolarCore(m,collision);group.add(solarCore.group);
  // A visible, solid end cap is the sole remaining sealed expansion door.
  a.box([7,8,.1],[0,4,117.5],m.hull);a.box([6.4,7.4,.12],[0,4,117.42],m.wall);
  a.box([.05,6.5,.14],[0,4,117.33],amber);
  sign('后部封存舱','SEALED / END OF INHABITED DECK',[0,9.6,117.3],6,Math.PI);
  sign('太阳核心','SOLAR CORE / SYSTEM / USAGE',[0,10,78.45],7);

  // Short side connection is floored, roofed, and walled, not a teleport seam.
  floor(18,22,82,90,ivory);
  for(const z of [82,90]) wall(true,z,18,22,9,[],.5,panel);
  solid([4,.5,8],[20,9.25,86],m.ceiling,'ceiling');
  for(const z of [83,89]) a.box([4,.02,.06],[20,.04,z],amber);

  // Archives: warm pale floor, low coffered ceiling, crystal shelves; no core clone.
  floor(22,54,74,106,ivory);
  wall(false,22,74,106,12,[{center:86,width:8,height:7,id:'archive-inner'}],.6,panel);
  wall(false,54,74,106,12,[],.6,panel);
  for(const z of [74,106]) wall(true,z,22,54,12,[],.6,panel);
  solid([32,.5,32],[38,12.25,90],m.ceiling,'ceiling');
  for(let ix=0;ix<8;ix++) for(let iz=0;iz<8;iz++)
    a.box([3.9,.012,3.9],[24+ix*4,.02,76+iz*4],(ix+iz)%3===0?panel:ivory);
  for(const x of [26,38,50]) {
    a.box([.3,.24,30],[x,11.8,90],m.hull);
    a.box([.16,.06,25],[x,11.63,90],amber);
  }
  for(const z of [78,90,102]) a.box([29,.24,.3],[38,11.8,z],m.hull);
  const shelf = (x: number, z: number, alongX: boolean) => {
    const w=alongX?6:1.4,d=alongX?1.4:6;
    solid([w,5.4,d],[x,2.7,z],m.wall,'archive-shelf');
    for(const y of [.3,1.7,3.1,4.5,5.5]) a.box([w+.1,.12,d+.1],[x,y,z],m.hull);
    for(let i=0;i<5;i++) for(const y of [1,2.4,3.8]) {
      const px=alongX?x+(i-2)*1.02:x-.77,pz=alongX?z-.77:z+(i-2)*1.02;
      a.add(new THREE.OctahedronGeometry(.35).scale(.55,1.35,.55).translate(px,y,pz),violet);
    }
  };
  for(const x of [28,38,48]) shelf(x,75.6,true);
  for(const z of [82,94,102]) shelf(52.4,z,false);
  // Quiet central reading sculpture, not another fake console.
  solid([6,.55,3],[38,.275,90],panel,'archive-reading-island');
  a.add(new THREE.OctahedronGeometry(1.4).scale(.7,1.8,.7).translate(38,3,90),navy);
  a.ring(1.8,.12,[38,1,90],m.hull);
  for(const side of [-1,1]) {
    solid([4,.65,1],[38, .325,90+side*3.6],m.wallAccent,'archive-bench');
    a.box([4,.09,1.1],[38,.69,90+side*3.6],m.hull);
  }
  // Main route to terminals runs behind the reading island, never through shelves.
  a.box([24,.02,.06],[34,.044,86],amber);
  a.box([.06,.02,11],[27,.044,91.5],amber);
  a.box([20,.02,.06],[37,.044,97],amber);
  sign('记忆资料室','ARCHIVES / CONFIGURATION / LOGS',[22.39,8.3,86],6,Math.PI/2);
  for(const x of [29,46]) light('archive-warm-reading-light',[x,8,90],0xe3d2b0,200,30);
  a.finish();
  group.traverse(o=>{if(o instanceof THREE.Mesh) o.receiveShadow=true;});
  group.userData.layout={floorY:0,finalBoundaryZ:118,doorIds:doors.map(d=>d.id),centralRoute:[-5.5,5.5,14,78]};
  group.userData.doors=doors;
  const update=(dt:number, playerPosition:THREE.Vector3):void=>{
    if(!Number.isFinite(dt)||dt<=0) return;
    const step=Math.min(dt,.1);solarCore.update(step);
    if(!playerPosition||![playerPosition.x,playerPosition.y,playerPosition.z].every(Number.isFinite)) return;
    doors.forEach((d,i)=>{
      const tangent=d.alongX?playerPosition.x-d.x:playerPosition.z-d.z;
      const normal=d.alongX?playerPosition.z-d.z:playerPosition.x-d.x;
      const near=Math.abs(normal)<6&&Math.abs(tangent)<d.width/2+1.2&&playerPosition.y<8;
      // Pocket-inclusive safety volume prevents closing on people waiting beside a leaf.
      const safety=Math.abs(normal)<1.2&&Math.abs(tangent)<d.width+PLAYER_RADIUS&&playerPosition.y<8;
      d.hold=near||safety?1.5:Math.max(0,d.hold-step);
      const target=d.hold>0?1:0;
      d.fraction=THREE.MathUtils.clamp(d.fraction+(target?1:-1)*step*2.4,0,1);
      // Teleports / a long first frame cannot trap a player in a newly instantiated door.
      if(safety) d.fraction=1;
      placeDoors[i]();
    });
  };
  group.userData.update=update;
  return {group,update};
}
