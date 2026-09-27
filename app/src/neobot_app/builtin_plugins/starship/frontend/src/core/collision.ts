/** Flat-footed cylindrical player, live AABB doors, and detailed static colliders. */
import * as THREE from 'three';
import { cylinderBox, makeMesh, metadataOf, shapeIntersects, shapeBlocksSegment, meshContainsPoint,
  type CollisionShape, type ColliderMetadata, type MetadataInput, type StaticMeshOptions,
  type StaticMeshShape, type CylinderShape, type OBBShape, type CollisionStats } from './collision-shapes';
export type { CollisionShape, ColliderMetadata, StaticMeshOptions, StaticMeshShape } from './collision-shapes';

export interface Box { min: THREE.Vector3; max: THREE.Vector3; tag?: string; metadata?: ColliderMetadata }
export const PLAYER_RADIUS = 0.42;
export const PLAYER_HEIGHT = 1.78;
export const PLAYER_CROUCH_HEIGHT = 1.15;
export const EYE_HEIGHT = 1.62;
export const EYE_HEIGHT_CROUCH = 1.0;

export class CollisionWorld {
  /** Live references, intentionally NOT indexed: animated door Box3 vectors mutate in place. */
  readonly boxes: Box[] = [];
  readonly shapes: CollisionShape[] = [];
  /** Last movement's narrow-phase counters; useful for performance/debug overlays. */
  readonly stats: CollisionStats = { shapeTests: 0, triangleTests: 0, bvhNodes: 0 };
  add(min: THREE.Vector3, max: THREE.Vector3, tag?: string): void { this.boxes.push({ min, max, tag }); }
  addBox(box: Box): void { this.boxes.push(box); }
  addFromCenter(center: THREE.Vector3, size: THREE.Vector3, tag?: string): void {
    const half = size.clone().multiplyScalar(0.5);
    this.add(center.clone().sub(half), center.clone().add(half), tag);
  }
  /** Legacy AABB query contract remains unchanged; detailed shapes use queryShapes/intersectsPlayer. */
  query(box: Box, out: Box[] = []): Box[] {
    out.length = 0;
    for (const candidate of this.boxes) if (overlap(candidate, box)) out.push(candidate);
    return out;
  }
  queryShapes(box: Box, out: CollisionShape[] = []): CollisionShape[] {
    out.length = 0;
    for (const shape of this.shapes) if (overlap(shape.bounds, box, true)) out.push(shape);
    return out;
  }
  addCylinder(center: THREE.Vector3, radius: number, height: number, metadata: MetadataInput = {}): CylinderShape {
    if (!(radius > 0 && height > 0)) throw new Error('Cylinder dimensions must be positive');
    const half = new THREE.Vector3(radius, height / 2, radius);
    const shape: CylinderShape = { kind: 'cylinder', center: center.clone(), radius, height,
      bounds: new THREE.Box3(center.clone().sub(half), center.clone().add(half)), metadata: metadataOf(metadata) };
    this.shapes.push(shape); return shape;
  }
  /** yaw follows THREE.Euler(0,yaw,0); dimensions are local full extents. */
  addOBB(center: THREE.Vector3, size: THREE.Vector3, yaw: number, metadata: MetadataInput = {}): OBBShape {
    if (Math.min(size.x, size.y, size.z) <= 0) throw new Error('OBB dimensions must be positive');
    const half = size.clone().multiplyScalar(0.5), c = Math.abs(Math.cos(yaw)), s = Math.abs(Math.sin(yaw));
    const extents = new THREE.Vector3(c * half.x + s * half.z, half.y, s * half.x + c * half.z);
    const shape: OBBShape = { kind: 'obb', center: center.clone(), half, yaw,
      bounds: new THREE.Box3(center.clone().sub(extents), center.clone().add(extents)), metadata: metadataOf(metadata) };
    this.shapes.push(shape); return shape;
  }
  addStaticGeometry(geometry: THREE.BufferGeometry, matrixWorld = new THREE.Matrix4(), options: StaticMeshOptions = {}): StaticMeshShape {
    const shape = makeMesh(geometry, matrixWorld, options);
    this.shapes.push(shape); return shape;
  }
  addStaticMesh(root: THREE.Object3D, options?: StaticMeshOptions): StaticMeshShape[];
  addStaticMesh(root: THREE.Object3D, label: string, options?: StaticMeshOptions): StaticMeshShape[];
  addStaticMesh(root: THREE.Object3D, input: StaticMeshOptions | string = {}, extra: StaticMeshOptions = {}): StaticMeshShape[] {
    const options = typeof input === 'string' ? { ...extra, tag: input } : input;
    const handles: StaticMeshShape[] = [];
    root.updateWorldMatrix(true, true);
    root.traverseVisible(object => {
      const mesh = object as THREE.Mesh;
      if (!mesh.isMesh || mesh.userData.nonSolid) return;
      const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
      if (options.filter ? !options.filter(mesh) : materials.some(m => m.transparent)) return;
      handles.push(this.addStaticGeometry(mesh.geometry, mesh.matrixWorld,
        { ...options, part: options.part ?? mesh.name, owner: options.owner ?? root.name }));
    });
    return handles;
  }
  removeShape(shape: CollisionShape): void { const i = this.shapes.indexOf(shape); if (i >= 0) this.shapes.splice(i, 1); }
  /** Snapshots own no GPU resources. Clearing removes all world-held triangle/BVH refs.
   * Owners must also release returned handles; rebuild/re-register when transforms change. */
  clearStatic(): void { this.shapes.length = 0; }
  clear(): void { this.clearStatic(); this.boxes.length = 0; }
  /** Occupancy, including an avatar entirely enclosed by a closed static mesh.
   * Surface narrow phase stays allocation-light in the movement hot path; this
   * interior fallback is for safe spawn/arrival and explicit occupancy queries. */
  intersectsPlayer(position: THREE.Vector3, height: number, radius = PLAYER_RADIUS): boolean {
    const center = new THREE.Vector3(position.x, position.y + height * 0.5, position.z);
    return this.boxes.some(b => cylinderBox(position, height, radius, b.min, b.max)) ||
      this.shapes.some(s => shapeIntersects(s, position, height, radius, this.stats) ||
        (s.kind === 'mesh' && meshContainsPoint(s, center, this.stats)));
  }
  /** Exact line-of-sight against live doors and BVH-backed static shapes. */
  segmentBlocked(start: THREE.Vector3, end: THREE.Vector3, ignoreOwner?: string): boolean {
    const direction = end.clone().sub(start), length = direction.length();
    if (length < 1e-6) return false;
    const ray = new THREE.Ray(start, direction.divideScalar(length)), hit = new THREE.Vector3();
    for (const box of this.boxes) {
      if (ignoreOwner && (box.metadata?.owner === ignoreOwner || box.tag === ignoreOwner)) continue;
      const bounds = new THREE.Box3(box.min, box.max);
      if (bounds.containsPoint(start) || (ray.intersectBox(bounds, hit) && hit.distanceTo(start) < length - 1e-4)) return true;
    }
    return this.shapes.some(shape => (!ignoreOwner || shape.metadata.owner !== ignoreOwner) && shapeBlocksSegment(shape, ray, length, this.stats));
  }
}

function overlap(a: Box, b: Box, inclusive = false): boolean {
  return inclusive ? a.max.x >= b.min.x && a.min.x <= b.max.x && a.max.y >= b.min.y && a.min.y <= b.max.y && a.max.z >= b.min.z && a.min.z <= b.max.z :
    a.max.x > b.min.x && a.min.x < b.max.x && a.max.y > b.min.y && a.min.y < b.max.y && a.max.z > b.min.z && a.min.z < b.max.z;
}
export interface MoveResult { position: THREE.Vector3; grounded: boolean; hitCeiling: boolean; collidedX: boolean; collidedZ: boolean }
type Axis = 'x' | 'y' | 'z';

/** Bounded displacement samples plus contact bisection, independent of frame rate.
 * Radius/5 spacing prevents sprint/fall tunnelling across thin panels. BVH limits
 * narrow phase to nearby triangles; registration/baking never occurs in this path. */
function moveAxis(world: CollisionWorld, p: THREE.Vector3, height: number, axis: Axis, amount: number): boolean {
  if (!amount) return false;
  const before = p[axis], target = before + amount, radius = PLAYER_RADIUS;
  const min = new THREE.Vector3(p.x - radius, p.y, p.z - radius);
  const max = new THREE.Vector3(p.x + radius, p.y + height, p.z + radius);
  if (amount < 0) min[axis] += amount; else max[axis] += amount;
  const boxes = world.query({ min, max }), shapes = world.queryShapes({ min, max });
  if (!boxes.length && !shapes.length) { p[axis] = target; return false; }
  const collides = (): boolean => boxes.some(b => cylinderBox(p, height, radius, b.min, b.max)) ||
    shapes.some(s => shapeIntersects(s, p, height, radius, world.stats));
  const steps = Math.max(1, Math.ceil(Math.abs(amount) / (radius / 5)));
  let safe = before;
  for (let i = 1; i <= steps; i++) {
    p[axis] = before + amount * i / steps;
    if (collides()) {
      let blocked = p[axis];
      for (let j = 0; j < 14; j++) {
        p[axis] = (safe + blocked) * 0.5;
        if (collides()) blocked = p[axis]; else safe = p[axis];
      }
      p[axis] = safe;
      return true;
    }
    safe = p[axis];
  }
  return false;
}

export function moveWithCollision(world: CollisionWorld, position: THREE.Vector3, height: number, delta: THREE.Vector3): MoveResult {
  world.stats.shapeTests = world.stats.triangleTests = world.stats.bvhNodes = 0;
  const p = position.clone();
  const result: MoveResult = { position: p, grounded: false, hitCeiling: false, collidedX: false, collidedZ: false };
  const support = position.clone();
  const supported = delta.y <= 0 && moveAxis(world, support, height, 'y', -0.12);
  result.collidedX = moveAxis(world, p, height, 'x', delta.x);
  result.collidedZ = moveAxis(world, p, height, 'z', delta.z);
  // Try a genuine step from the ORIGINAL position: no doubled X/Z displacement,
  // no teleport through low ceilings, no airborne wall climbing.
  if (supported && (result.collidedX || result.collidedZ)) {
    const raised = position.clone();
    if (!moveAxis(world, raised, height, 'y', 0.55)) {
      const xBlocked = moveAxis(world, raised, height, 'x', delta.x);
      const zBlocked = moveAxis(world, raised, height, 'z', delta.z);
      if (!xBlocked && !zBlocked && moveAxis(world, raised, height, 'y', -0.55 - 0.12) && raised.y >= position.y - 0.12) {
        p.copy(raised); result.collidedX = result.collidedZ = false;
      }
    }
  }
  const yBlocked = moveAxis(world, p, height, 'y', delta.y);
  result.grounded = yBlocked && delta.y < 0;
  result.hitCeiling = yBlocked && delta.y > 0;
  if (delta.y <= 0 && !result.grounded) {
    const probe = p.clone();
    if (moveAxis(world, probe, height, 'y', 0 - (supported ? 0.12 : 0.002))) {
      p.y = probe.y; result.grounded = true;
    }
  }
  return result;
}
