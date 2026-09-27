/** Sculpted foundry exhibits. World floor is y=0; consoles own |x|<12.
 * Static geometry is batched by material per bay, so culling stays useful.
 * Only temporary construction geometries are disposed here. Final resources,
 * including the shared ship palette, belong to the caller's scene disposal pass.
 */
import * as THREE from 'three';
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';
import type { CollisionWorld } from '../core/collision';
import type { ShipMaterials } from './materials';
import type { RoomBounds } from './ship';
import { buildFoundryArchitecture } from './foundry-architecture';
import { buildStalker, buildDragoon } from './protoss-walkers';
import { buildImmortal, buildColossus } from './protoss-heavy';

type V = [number, number, number];
type Palette = Record<'gold' | 'dark' | 'steel' | 'violet' | 'cyan' | 'ceramic' | 'crystal', THREE.Material>;
const v = (p: V): THREE.Vector3 => new THREE.Vector3(...p);
const Y = new THREE.Vector3(0, 1, 0);

/** A pointed, domed chitin plate, not an ellipsoid or a scaled box.
 * The folded lip and center ridge catch light along the entire silhouette. */
function carapace(width: number, rise: number, length: number): THREE.BufferGeometry {
  const vertices: number[] = [], uv: number[] = [], indices: number[] = [];
  const rows = 16, columns = 16;
  for (let j = 0; j <= rows; j++) {
    const t = j / rows;
    const envelope = Math.pow(Math.max(0.0001, Math.sin(Math.PI * t)), 0.65);
    for (let i = 0; i <= columns; i++) {
      const angle = Math.PI * i / columns;
      const ridge = Math.pow(Math.sin(angle), 5) * 0.16;
      vertices.push(Math.cos(angle) * width * envelope,
        (Math.sin(angle) + ridge) * rise * envelope,
        (t - 0.5) * length);
      uv.push(i / columns, t);
      if (j < rows && i < columns) {
        const a = j * (columns + 1) + i, b = a + columns + 1;
        indices.push(a, a + 1, b, b, a + 1, b + 1);
      }
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
  geometry.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  return geometry;
}

class Bay {
  private readonly batches = new Map<THREE.Material, THREE.BufferGeometry[]>();
  constructor(readonly root: THREE.Group, readonly collision: CollisionWorld,
    readonly x: number, readonly z: number, readonly palette: Palette) {}

  add(geometry: THREE.BufferGeometry, material: THREE.Material, position: V = [0, 0, 0],
    rotation: V = [0, 0, 0], scale: V = [1, 1, 1], solid = false): void {
    geometry.applyMatrix4(new THREE.Matrix4().compose(
      new THREE.Vector3(this.x + position[0], position[1], this.z + position[2]),
      new THREE.Quaternion().setFromEuler(new THREE.Euler(...rotation)), v(scale)));
    if (solid && !material.transparent) {
      // Snapshot before batching/disposal; diagonal rods and oval worktops keep
      // their actual silhouette rather than filling their enclosing AABB.
      this.collision.addStaticGeometry(geometry, new THREE.Matrix4(), {
        tag: 'foundry-prop', owner: 'foundry-bay-' + this.x + '-' + this.z,
        part: geometry.type + '@' + position.join(','),
      });
    }
    // All primitives have position/normal/uv; normalize index layout before merge.
    const flat = geometry.index ? geometry.toNonIndexed() : geometry;
    if (flat !== geometry) geometry.dispose();
    flat.deleteAttribute('uv');
    const list = this.batches.get(material) ?? [];
    list.push(flat);
    this.batches.set(material, list);
  }

  sphere(p: V, size: V, material: THREE.Material, solid = false): void {
    this.add(new THREE.SphereGeometry(1, 20, 12), material, p, [0, 0, 0], size, solid);
  }

  cylinder(p: V, top: number, bottom: number, height: number, material: THREE.Material, solid = false): void {
    if (solid && top === bottom && !material.transparent) {
      this.collision.addCylinder(new THREE.Vector3(this.x + p[0], p[1], this.z + p[2]), top, height,
        { tag: 'foundry-prop', owner: 'foundry-bay-' + this.x + '-' + this.z, part: 'cylinder@' + p.join(',') });
    }
    this.add(new THREE.CylinderGeometry(top, bottom, height, 40), material, p, [0, 0, 0], [1, 1, 1], solid && top !== bottom);
  }

  rod(a: V, b: V, radius: number, material: THREE.Material, endRadius = radius, solid = true): void {
    const start = v(a), end = v(b), delta = end.clone().sub(start);
    const geometry = new THREE.CylinderGeometry(endRadius, radius, delta.length(), 12);
    geometry.applyQuaternion(new THREE.Quaternion().setFromUnitVectors(Y, delta.clone().normalize()));
    this.add(geometry, material, start.add(end).multiplyScalar(0.5).toArray() as V,
      [0, 0, 0], [1, 1, 1], solid);
  }

  tube(points: V[], radius: number, material: THREE.Material): void {
    this.add(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(points.map(v)), 36, radius, 8, false), material);
  }

  ring(p: V, radius: number, tube: number, material: THREE.Material,
    rotation: V = [Math.PI / 2, 0, 0], arc = Math.PI * 2): void {
    this.add(new THREE.TorusGeometry(radius, tube, 6, radius < 1.5 ? 24 : 64, arc), material, p, rotation);
  }

  plate(p: V, size: V, material: THREE.Material, rotation: V = [0, 0, 0]): void {
    this.add(carapace(...size), material, p, rotation);
  }

  /** Convex tapered armor aligned with a bone; bevel comes from a lathed profile. */
  armor(a: V, b: V, radius: number, material: THREE.Material, flatten = 0.65): void {
    const delta = v(b).sub(v(a)), length = delta.length();
    const profile = [[0.15, 0], [0.68, 0.12], [1, 0.3], [0.92, 0.53], [0.56, 0.84], [0.08, 1]];
    const geometry = new THREE.LatheGeometry(profile.map(([r, y]) => new THREE.Vector2(r * radius, y * length)), 12);
    geometry.scale(1, 1, flatten);
    geometry.applyQuaternion(new THREE.Quaternion().setFromUnitVectors(Y, delta.normalize()));
    this.add(geometry, material, a);
  }

  /** Bevelled six-sided armor tile; sharp folded planes instead of inflated shells. */
  panel(p: V, width: number, height: number, depth: number, material: THREE.Material, rotation: V = [0, 0, 0]): void {
    const shape = new THREE.Shape();
    shape.moveTo(0, height * 0.56);
    shape.lineTo(width * 0.5, height * 0.24);
    shape.lineTo(width * 0.39, -height * 0.28);
    shape.lineTo(0, -height * 0.55);
    shape.lineTo(-width * 0.39, -height * 0.28);
    shape.lineTo(-width * 0.5, height * 0.24);
    shape.closePath();
    const geometry = new THREE.ExtrudeGeometry(shape, { depth, bevelEnabled: true,
      bevelSegments: 1, steps: 1, bevelSize: Math.min(width * 0.08, 0.06), bevelThickness: 0.035 });
    geometry.translate(0, 0, -depth / 2);
    this.add(geometry, material, p, rotation, [1, 1, 1], true);
  }

  piston(a: V, b: V, radius = 0.1): void {
    const start = v(a), end = v(b), mid = start.clone().lerp(end, 0.6);
    this.rod(a, mid.toArray() as V, radius * 1.55, this.palette.dark);
    this.rod(mid.toArray() as V, b, radius, this.palette.steel);
    for (const t of [0.1, 0.48, 0.59]) {
      const c = start.clone().lerp(end, t), d = start.clone().lerp(end, t + 0.035);
      this.rod(c.toArray() as V, d.toArray() as V, radius * 1.85, this.palette.gold);
    }
  }

  joint(p: V, radius: number, axis: V = [1, 0, 0]): void {
    const q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 0, 1), v(axis).normalize());
    const transform = (geometry: THREE.BufferGeometry, material: THREE.Material): void => {
      geometry.applyQuaternion(q); this.add(geometry, material, p);
    };
    transform(new THREE.CylinderGeometry(radius, radius, radius * 0.7, 12).rotateX(Math.PI / 2), this.palette.dark);
    for (const side of [-1, 1]) {
      transform(new THREE.TorusGeometry(radius * 0.8, radius * 0.075, 5, 24).translate(0, 0, side * radius * 0.39), this.palette.gold);
      transform(new THREE.CylinderGeometry(radius * 0.4, radius * 0.4, 0.055, 6).rotateX(Math.PI / 2)
        .translate(0, 0, side * radius * 0.43), this.palette.steel);
      for (let i = 0; i < 8; i++) {
        const a = i * Math.PI / 4;
        transform(new THREE.CylinderGeometry(0.045, 0.045, 0.05, 6).rotateX(Math.PI / 2)
          .translate(Math.cos(a) * radius * 0.63, Math.sin(a) * radius * 0.63, side * radius * 0.43), this.palette.steel);
      }
    }
    for (let i = 0; i < 12; i++) {
      const a = i * Math.PI / 6;
      transform(new THREE.BoxGeometry(radius * 0.18, radius * 0.23, radius * 0.52)
        .translate(0, radius * 0.94, 0).rotateZ(a), this.palette.steel);
    }
  }

  gem(p: V, radius: number, stretch = 1.5): void {
    this.add(new THREE.OctahedronGeometry(radius), this.palette.crystal, p, [0, 0, 0], [0.65, stretch, 0.55]);
    for (const side of [-1, 1]) this.panel([p[0] + side * radius * 0.5, p[1], p[2] + 0.03],
      radius * 0.2, radius * stretch * 1.8, 0.07, this.palette.gold, [0, 0, -side * 0.13]);
  }

  finish(name: string): void {
    for (const [material, geometries] of this.batches) {
      const merged = mergeGeometries(geometries, false);
      for (const geometry of geometries) geometry.dispose();
      if (!merged) throw new Error('Incompatible foundry geometry: ' + name);
      merged.computeBoundingSphere();
      const mesh = new THREE.Mesh(merged, material);
      mesh.name = name + '-' + material.name;
      mesh.castShadow = !(material instanceof THREE.MeshBasicMaterial);
      mesh.receiveShadow = true;
      mesh.matrixAutoUpdate = false;
      this.root.add(mesh);
    }
    this.batches.clear();
  }
}

function platform(b: Bay, radius: number, glow: THREE.Material): void {
  const p = b.palette;
  b.cylinder([0, 0.22, 0], radius - 0.08, radius, 0.44, p.dark, true);
  b.cylinder([0, 0.48, 0], radius - 0.28, radius - 0.1, 0.12, p.steel, true);
  b.cylinder([0, 0.56, 0], radius - 0.52, radius - 0.35, 0.08, p.dark, true);
  b.ring([0, 0.4, 0], radius - 0.08, 0.075, glow);
  b.ring([0, 0.62, 0], radius - 0.75, 0.045, glow);
  b.ring([0, 0.615, 0], radius - 1.05, 0.022, p.gold);
  b.ring([0, 0.616, 0], 1.6, 0.025, glow);
  // Replace a featureless disk with individually machined rim sectors and clamps.
  for (let i = 0; i < 16; i++) {
    const angle = i * Math.PI / 8, span = Math.PI / 8 - 0.065;
    const shape = new THREE.Shape();
    shape.absarc(0, 0, radius - 0.13, angle, angle + span, false);
    shape.absarc(0, 0, radius - 0.54, angle + span, angle, true);
    shape.closePath();
    const sector = new THREE.ExtrudeGeometry(shape, { depth: 0.12, bevelEnabled: true,
      bevelSegments: 1, bevelSize: 0.025, bevelThickness: 0.02, steps: 1, curveSegments: 4 });
    sector.rotateX(-Math.PI / 2);
    b.add(sector, i % 4 === 0 ? p.gold : p.steel, [0, 0.55, 0], [0, 0, 0], [1, 1, 1], true);
    const a = angle + span / 2, r = radius - 0.34;
    b.add(new THREE.CylinderGeometry(0.075, 0.075, 0.04, 6), p.dark,
      [Math.cos(a) * r, 0.71, -Math.sin(a) * r]);
    if (i % 2 === 0) {
      const x = Math.cos(a) * (radius - 1.1), z = -Math.sin(a) * (radius - 1.1);
      b.add(new THREE.BoxGeometry(0.46, 0.22, 0.66), p.dark, [x, 0.72, z], [0, a, 0], [1, 1, 1], true);
      b.panel([x, 0.86, z], 0.3, 0.54, 0.07, p.gold, [-Math.PI / 2, 0, a]);
      b.cylinder([x, 0.98, z], 0.08, 0.11, 0.17, glow);
    }
  }
  // The three tapered disk meshes above own the surface and rim collision.
  for (let i = 0; i < 32; i++) {
    const angle = i / 32 * Math.PI * 2, r = radius - 0.37;
    b.add(new THREE.BoxGeometry(0.1, 0.018, i % 4 === 0 ? 0.32 : 0.17),
      i % 4 === 0 ? glow : p.gold,
      [Math.sin(angle) * r, 0.61, Math.cos(angle) * r], [0, angle + 0.35, 0]);
  }
  for (const side of [-1, 1]) {
    b.tube([[side * 2.6, 0.64, 3.6], [side * 2.8, 0.64, 2.6], [side * 1.8, 0.64, 1.8]], 0.027, glow);
  }
}

function gantry(b: Bay, glow: THREE.Material, outer: number): void {
  const p = b.palette;
  // Preserve the original post collision footprints. Wide curved armor now carries
  // the crane, while the much larger temple ribs establish the room silhouette.
  for (const side of [-1, 1]) {
    const x = side * 6.25;
    b.cylinder([x, 0.22, 1.9], 0.61, 0.78, 0.44, p.dark, true);
    b.rod([x, 0.42, 1.9], [x, 7.6, 1.9], 0.23, p.steel, 0.2, true);
    const shape = new THREE.Shape();
    shape.moveTo(side * 6.55, 6.8);
    shape.bezierCurveTo(side * 6.9, 10.8, side * 3.8, 13.9, 0, 13.8);
    shape.bezierCurveTo(side * 3.6, 12.45, side * 5.5, 10.8, side * 5.9, 7.3);
    shape.closePath();
    const armor = new THREE.ExtrudeGeometry(shape, { depth: 0.76, bevelEnabled: true,
      bevelSize: 0.11, bevelThickness: 0.1, bevelSegments: 2, curveSegments: 20, steps: 1 });
    b.add(armor, p.gold, [0, 0, 1.5], [0, 0, 0], [1, 1, 1], true);
    const inset = new THREE.Shape();
    inset.moveTo(side * 6.24, 8.1);
    inset.bezierCurveTo(side * 6.18, 10.7, side * 3.4, 13.14, side * 1.05, 13.43);
    inset.bezierCurveTo(side * 3.8, 12.35, side * 5.54, 10.65, side * 6.24, 8.1);
    b.add(new THREE.ExtrudeGeometry(inset, { depth: 0.06, bevelEnabled: false, curveSegments: 20 }),
      p.dark, [0, 0, 1.36], [0, 0, 0], [1, 1, 1], true);
    b.tube([[x - side * 0.18, 8.05, 1.33], [side * 5.34, 10.72, 1.33],
      [side * 3.45, 12.37, 1.33], [side * 1.1, 13.43, 1.33]], 0.025, glow);
    for (const y of [1.2, 4, 7.4]) b.ring([x, y, 1.9], 0.28, 0.055, p.gold);
    b.panel([x, 4.1, 1.61], 0.64, 4.9, 0.16, p.gold);
    b.panel([x, 4.1, 1.49], 0.29, 3.7, 0.08, p.dark);
  }
  b.rod([-1.4, 12.83, 1.9], [1.4, 12.83, 1.9], 0.3, p.dark);
  b.rod([-0.5, 12.7, 1.9], [-0.5, 9.5, 1.9], 0.027, p.steel);
  b.rod([0.5, 12.7, 1.9], [0.5, 9.5, 1.9], 0.027, p.steel);
  b.rod([-0.9, 9.5, 1.9], [0.9, 9.5, 1.9], 0.12, p.gold);
  b.ring([0, 9.25, 1.9], 0.26, 0.075, p.steel, [0, 0, 0], Math.PI * 1.5);
  mechanicalArm(b, outer * 6.8, -2.9, glow, false);
  mechanicalArm(b, outer * 6.8, 3.8, glow, true);
}

function mechanicalArm(b: Bay, x: number, z: number, glow: THREE.Material, high: boolean): void {
  const p = b.palette, side = Math.sign(x);
  b.cylinder([x, 0.32, z], 0.64, 0.86, 0.64, p.dark, true);
  b.cylinder([x, 0.77, z], 0.44, 0.55, 0.34, p.gold, true);
  b.ring([x, 0.78, z], 0.5, 0.06, glow);
  const base: V = [x, 1.1, z], elbow: V = [x + side * 0.05, high ? 5.5 : 3.8, z + 0.3];
  const wrist: V = [x - side * 2.2, high ? 6.7 : 4.9, z - 0.5];
  b.rod(base, elbow, 0.25, p.dark, 0.21, true);
  b.rod(elbow, wrist, 0.18, p.dark, 0.13);
  for (const offset of [-0.27, 0.27]) {
    b.rod([base[0], base[1], base[2] + offset], [elbow[0], elbow[1], elbow[2] + offset], 0.085, p.steel);
    b.piston([x - side * 0.2, 1.5, z + offset], [elbow[0] - side * 0.26, elbow[1] - 0.18, elbow[2] + offset], 0.085);
    b.piston([elbow[0], elbow[1] - 0.28, elbow[2] + offset],
      [wrist[0] + side * 0.24, wrist[1] - 0.25, wrist[2] + offset], 0.07);
  }
  for (let i = 0; i < 3; i++) {
    const c = v(base).lerp(v(elbow), 0.25 + i * 0.24);
    b.panel([c.x, c.y, c.z - 0.25], 0.56, 0.77, 0.14, i === 1 ? p.dark : p.gold);
  }
  for (const pt of [base, elbow, wrist]) {
    b.joint(pt, 0.34, [0, 0, 1]);
    b.ring([pt[0], pt[1], pt[2] - 0.18], 0.22, 0.028, glow, [0, 0, 0]);
  }
  b.tube([[x + side * 0.28, 1, z], [x + side * 0.4, elbow[1], z + 0.3],
    [wrist[0], wrist[1] + 0.25, wrist[2]]], 0.047, p.dark);
  for (const tine of [-1, 1]) {
    b.rod([wrist[0], wrist[1], wrist[2] + tine * 0.16],
      [wrist[0] - side * 0.52, wrist[1] - 0.42, wrist[2] + tine * 0.24], 0.06, p.steel);
    b.rod([wrist[0] - side * 0.52, wrist[1] - 0.42, wrist[2] + tine * 0.24],
      [wrist[0] - side * 0.62, wrist[1] - 0.6, wrist[2] + tine * 0.1], 0.045, p.gold);
  }
  b.sphere([wrist[0] - side * 0.4, wrist[1] - 0.3, wrist[2]], [0.08, 0.08, 0.08], glow);
}

function partsTable(b: Bay, robotParts: boolean): void {
  const p = b.palette, glow = robotParts ? p.cyan : p.violet;
  // A machined oval table between the two bays, out against the exterior wall.
  b.cylinder([0, 0.58, 0], 0.48, 0.72, 1.16, p.dark, true);
  b.add(new THREE.CylinderGeometry(1, 1.07, 0.22, 40), p.steel, [0, 1.24, 0], [0, 0, 0], [1.65, 1, 1.25], true);
  b.ring([0, 1.37, 0], 1, 0.025, glow);
  if (robotParts) {
    b.sphere([-0.5, 1.76, 0], [0.33, 0.43, 0.3], p.dark);
    b.plate([-0.5, 1.73, 0], [0.37, 0.25, 0.95], p.gold, [Math.PI / 2, 0, 0]);
    b.sphere([-0.5, 1.83, -0.31], [0.21, 0.045, 0.04], p.cyan);
    b.add(new THREE.OctahedronGeometry(0.34), p.crystal, [0.65, 1.75, 0], [0, 0.3, 0.2], [0.65, 1.2, 0.65]);
  } else {
    b.plate([-0.3, 1.39, 0], [0.66, 0.35, 1.8], p.gold, [0, 0.2, 0]);
    b.rod([0.86, 1.48, -0.65], [0.86, 1.48, 0.65], 0.12, p.steel);
  }
  // Indexed spare-component array: couplings, actuator rods and caged energy cells.
  for (let i = 0; i < 4; i++) {
    const x = -1.08 + i * 0.62;
    b.cylinder([x, 1.4, 0.69], 0.2, 0.23, 0.075, p.dark);
    b.joint([x, 1.58, 0.68], 0.15, [0, 1, 0]);
    b.rod([x, 1.56, 0.68], [x, 1.9 + (i % 2) * 0.14, 0.68], 0.072, p.steel);
    b.ring([x, 1.82, 0.68], 0.09, 0.025, glow);
  }
  for (const side of [-1, 1]) {
    b.piston([side * 1.27, 1.46, -0.5], [side * 1.27, 1.46, 0.35], 0.048);
    b.rod([side * 0.52, 0.21, 0], [side * 1.24, 1.14, 0], 0.06, p.steel);
  }
  // Sloped physical diagnostic face (not an interactive duplicate console).
  b.add(new THREE.BoxGeometry(0.8, 0.08, 0.52), p.dark, [0, 1.41, -0.86], [0.28, 0, 0], [1, 1, 1], true);
  for (let i = 0; i < 4; i++) b.add(new THREE.BoxGeometry(0.46 - i * 0.065, 0.012, 0.025), glow,
    [0, 1.465 + i * 0.02, -1.01 + i * 0.072], [0.28, 0, 0]);
}

interface AnimatedBay { ring: THREE.Mesh; phase: number }

interface FoundryUnit {
  kind: 'immortal' | 'stalker' | 'dragoon' | 'colossus';
  label: string;
  stage: string;
  side: number;
  z: number;
  radius: number;
  build: (materials: ShipMaterials) => THREE.Group;
}

/** Small physical inscriptions face the aisle, not the camera or DOM. */
function unitInscription(b: Bay, unit: FoundryUnit): void {
  const canvas = document.createElement('canvas');
  canvas.width = 1024; canvas.height = 320;
  const ctx = canvas.getContext('2d')!;
  ctx.fillStyle = '#061018'; ctx.fillRect(0, 0, 1024, 320);
  ctx.strokeStyle = '#75684d'; ctx.lineWidth = 6; ctx.strokeRect(8, 8, 1008, 304);
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.fillStyle = '#bcd4dc'; ctx.font = 'bold 65px "Microsoft YaHei", sans-serif';
  ctx.fillText(unit.label + ' · ' + unit.kind.toUpperCase(), 512, 82, 950);
  ctx.fillStyle = '#95abb7'; ctx.font = '44px "Microsoft YaHei", sans-serif';
  ctx.fillText(unit.stage, 512, 174, 950);
  ctx.fillStyle = '#819096'; ctx.font = '36px "Microsoft YaHei", sans-serif';
  ctx.fillText('静态装配展示 · 不提供生产功能', 512, 257, 950);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  const material = new THREE.MeshBasicMaterial({ map: texture, toneMapped: true });
  material.name = 'protoss-unit-inscription';
  const plaque = new THREE.Mesh(new THREE.PlaneGeometry(3.4, 1.06), material);
  plaque.name = unit.kind + '-name-and-assembly-stage';
  plaque.userData.unitLabel = unit.label;
  plaque.userData.assemblyStage = unit.stage;
  plaque.userData.decorativeOnly = true;
  const x = -unit.side * (unit.radius - 0.2);
  plaque.position.set(b.x + x - unit.side * 0.08, 1.28, b.z - 0.4);
  plaque.rotation.y = -unit.side * Math.PI / 2;
  b.root.add(plaque);
  b.add(new THREE.BoxGeometry(0.12, 1.2, 3.55), b.palette.gold, [x, 1.28, -0.4], [0, 0, 0], [1, 1, 1], true);
  b.add(new THREE.BoxGeometry(0.18, 0.52, 0.22), b.palette.dark, [x, 0.78, -0.4], [0, 0, 0], [1, 1, 1], true);
}

/** Full-height static triangle BVHs preserve individual feet, bent legs and
 * under-belly clearance, including the Colossus supports above the old 2.75m cut. */
function addUnitSupportCollision(unit: THREE.Group, collision: CollisionWorld): void {
  const handles = collision.addStaticMesh(unit, { tag: 'protoss-unit-support', owner: unit.name, leafSize: 12 });
  unit.userData.supportCollisionMeshes = handles.length;
  unit.userData.supportCollisionTriangles = handles.reduce((sum, shape) => sum + shape.triangleCount, 0);
  unit.userData.supportCollisionBoxes = 0;
}

export function buildFoundry(collision: CollisionWorld, materials: ShipMaterials, rooms: RoomBounds[]): THREE.Group {
  const root = new THREE.Group();
  // Use the ship's antique electrum / dark teal finish, including its environment
  // response and brushed-alloy shader. No independent bright-gold exhibit palette.
  const gold = materials.hull, dark = materials.ceiling;
  const ceramic = materials.wallAccent, steel = materials.wall;
  const violet = new THREE.MeshBasicMaterial({ color: 0x697caa }); violet.name = 'quiet-violet-assembly';
  const cyan = new THREE.MeshBasicMaterial({ color: 0x6598ad }); cyan.name = 'quiet-blue-assembly';
  const crystal = new THREE.MeshStandardMaterial({ color: 0x739db2, emissive: 0x245076,
    emissiveIntensity: 0.35, metalness: 0.38, roughness: 0.23, flatShading: true });
  crystal.name = 'cut-psionic-crystal';
  const palette: Palette = { gold, dark, ceramic, violet, cyan, crystal, steel };
  const animated: AnimatedBay[] = [];
  const activeSides = [-1, 1].filter(side => rooms.some(room => room.id === (side < 0 ? 'war-forge' : 'robot-forge')));
  root.add(buildFoundryArchitecture(materials, activeSides));
  const units: FoundryUnit[] = [
    { kind: 'immortal', label: '不朽者', stage: '装配阶段：护盾矩阵校准', side: -1, z: 29, radius: 5.7, build: buildImmortal },
    { kind: 'stalker', label: '追猎者', stage: '装配阶段：相位驱动校验', side: -1, z: 46, radius: 5.3, build: buildStalker },
    { kind: 'dragoon', label: '龙骑士', stage: '装配阶段：粒子炮阵列检修', side: 1, z: 29, radius: 5.7, build: buildDragoon },
    { kind: 'colossus', label: '巨像', stage: '装配阶段：长足底盘联调', side: 1, z: 46, radius: 7.4, build: buildColossus },
  ].filter(unit => activeSides.includes(unit.side)) as FoundryUnit[];
  for (const spec of units) {
    const { side, z, radius } = spec;
    const isColossus = spec.kind === 'colossus', glow = side > 0 ? cyan : violet;
    const b = new Bay(root, collision, side * 21, z, palette);
    platform(b, radius, glow);
    const unit = spec.build(materials);
    unit.name = 'foundry-' + spec.kind;
    unit.position.set(side * 21, 0.66, z);
    unit.userData.unitKind = spec.kind;
    unit.userData.label = spec.label;
    unit.userData.assemblyStage = spec.stage;
    unit.userData.decorativeOnly = true;
    unit.userData.productionEnabled = false;
    root.add(unit);
    addUnitSupportCollision(unit, collision);
    if (isColossus) {
      // The 25 m walker needs an open silhouette: no old 13 m crane cutting
      // through its body. Low service arms only attend the exterior ankle zone.
      mechanicalArm(b, 8.2, -2.9, glow, false);
      mechanicalArm(b, 8.2, 3.8, glow, true);
    } else {
      gantry(b, glow, side);
    }
    unitInscription(b, spec);
    b.finish(spec.kind + '-assembly-mount');
    // A quiet inspection sweep stays on the floor, never obscuring unit anatomy.
    const ring = new THREE.Mesh(new THREE.TorusGeometry(radius - 0.95, 0.023, 6, 72, Math.PI * 1.4), glow);
    ring.name = spec.kind + '-non-solid-inspection-sweep';
    ring.rotation.x = Math.PI / 2;
    ring.position.set(side * 21, 0.77, z);
    root.add(ring);
    animated.push({ ring, phase: z * 0.12 + side });
    const light = new THREE.PointLight(side > 0 ? 0x9bc1d2 : 0xa8acd3, 14, 15, 2);
    light.name = spec.kind + '-assembly-local-fill';
    light.position.set(side * 18, 7, z - 3);
    root.add(light);
    const key = new THREE.SpotLight(0xc2cddd, isColossus ? 300 : 100,
      isColossus ? 38 : 24, 0.55, 0.8, 2);
    key.name = spec.kind + '-assembly-armor-key';
    key.position.set(side * 16.5, isColossus ? 31 : 11.5, z - 5);
    key.target.position.set(side * 21, isColossus ? 15 : 4.2, z);
    root.add(key, key.target);
    if (isColossus) {
      const rim = new THREE.PointLight(0x7296cd, 45, 18, 2);
      rim.name = 'colossus-upper-carapace-blue-rim';
      rim.position.set(28, 24, z + 3);
      root.add(rim);
    }
  }
  for (const side of activeSides) {
    const table = new Bay(root, collision, side * 28.5, 37.5, palette);
    partsTable(table, side > 0);
    table.finish(side > 0 ? 'robot-parts-bench' : 'war-parts-bench');
  }
  let elapsed = 0;
  root.userData.update = (dt: number): void => {
    if (!Number.isFinite(dt) || dt <= 0) return;
    elapsed += Math.min(dt, 0.1);
    for (const item of animated) {
      item.ring.rotation.z = elapsed * 0.19 + item.phase;
    }
  };
  root.userData.layout = {
    floorY: 0,
    clearCenter: [-4, 4],
    consoleKeepOutRadius: 3,
    exhibitCenters: activeSides.flatMap(side => [[side * 21, 29], [side * 21, 46]]),
    units: units.map(({ kind, label, stage, side, z, radius }) => ({ kind, label, stage, x: side * 21, z, radius })),
    decorativeOnly: true,
    collision: 'Exact tapered plinth meshes; full-height unit triangle BVHs; precise solid rods, physical panels and oval benches. Transparent projections are non-solid.',
  };
  return root;
}
