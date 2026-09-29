/** Static collider snapshots. BVH leaves contain <= leafSize triangles, never a model AABB proxy. */
import * as THREE from 'three';

export interface ColliderMetadata { tag?: string; owner?: string; part?: string }
export type MetadataInput = ColliderMetadata | string;
export const metadataOf = (value: MetadataInput = {}): ColliderMetadata =>
  typeof value === 'string' ? { tag: value } : { tag: value.tag, owner: value.owner, part: value.part };
export interface ShapeBase { readonly bounds: THREE.Box3; readonly metadata: ColliderMetadata }
export interface CylinderShape extends ShapeBase {
  readonly kind: 'cylinder'; readonly center: THREE.Vector3; readonly radius: number; readonly height: number;
}
export interface OBBShape extends ShapeBase {
  readonly kind: 'obb'; readonly center: THREE.Vector3; readonly half: THREE.Vector3; readonly yaw: number;
}
interface Node { bounds: THREE.Box3; start: number; end: number; left?: Node; right?: Node }
export interface StaticMeshShape extends ShapeBase {
  readonly kind: 'mesh'; readonly vertices: Float32Array; readonly order: number[];
  readonly tree: Node; readonly triangleCount: number;
  readonly containment: 'union' | 'winding' | 'surface';
  /** Lazily welded closed-component topology, owned and released with this shape. */
  containmentCache?: { components: Int32Array; closed: Uint8Array };
}
export type CollisionShape = CylinderShape | OBBShape | StaticMeshShape;
export interface StaticMeshOptions extends ColliderMetadata {
  /** An explicit filter owns the solid/non-solid material decision. */
  filter?: (mesh: THREE.Mesh) => boolean;
  /** Registration fails rather than silently dropping physical triangles. Default 1 million per mesh. */
  maxTriangles?: number;
  /** BVH leaf budget, default 12. */
  leafSize?: number;
  /** Occupancy only (not movement): closed connected solids are unioned by default.
   * Use winding for oriented nested inner/outer shells defining a cavity, or
   * surface to explicitly disable interior classification for an open sheet. */
  containment?: 'union' | 'winding' | 'surface';
}
export interface CollisionStats { shapeTests: number; triangleTests: number; bvhNodes: number }
export const CONTACT_EPSILON = 1e-5;

export function makeMesh(geometry: THREE.BufferGeometry, matrix: THREE.Matrix4,
  options: StaticMeshOptions): StaticMeshShape {
  const position = geometry.getAttribute('position'), index = geometry.index;
  const count = Math.floor((index?.count ?? position.count) / 3);
  if (count > (options.maxTriangles ?? 1_000_000)) throw new Error('Static collision triangle budget exceeded');
  const vertices = new Float32Array(count * 9), order = Array.from({ length: count }, (_, i) => i);
  const p = new THREE.Vector3();
  for (let i = 0; i < count * 3; i++) {
    p.fromBufferAttribute(position, index ? index.getX(i) : i).applyMatrix4(matrix);
    if (!Number.isFinite(p.x + p.y + p.z)) throw new Error('Non-finite collision geometry');
    vertices.set([p.x, p.y, p.z], i * 3);
  }
  const leafSize = Math.max(2, Math.min(64, options.leafSize ?? 12));
  const build = (start: number, end: number): Node => {
    const bounds = new THREE.Box3();
    for (let j = start; j < end; j++) for (let k = 0; k < 9; k += 3) {
      p.fromArray(vertices, order[j] * 9 + k); bounds.expandByPoint(p);
    }
    const node: Node = { bounds, start, end };
    if (end - start > leafSize) {
      const size = bounds.getSize(new THREE.Vector3());
      const axis = size.x >= size.y && size.x >= size.z ? 0 : size.y >= size.z ? 1 : 2;
      const centroid = (i: number): number => vertices[i * 9 + axis] + vertices[i * 9 + axis + 3] + vertices[i * 9 + axis + 6];
      const sorted = order.slice(start, end).sort((a, b) => centroid(a) - centroid(b));
      for (let i = 0; i < sorted.length; i++) order[start + i] = sorted[i];
      const middle = (start + end) >>> 1;
      node.left = build(start, middle); node.right = build(middle, end);
    }
    return node;
  };
  const tree = build(0, count);
  return { kind: 'mesh', bounds: tree.bounds, metadata: metadataOf(options), vertices, order, tree, triangleCount: count, containment: options.containment ?? 'union' };
}

/** Exact disk/rectangle footprint (not the player's enclosing square). */
export function cylinderBox(position: THREE.Vector3, height: number, radius: number,
  min: THREE.Vector3, max: THREE.Vector3): boolean {
  if (position.y + height <= min.y + CONTACT_EPSILON || position.y >= max.y - CONTACT_EPSILON) return false;
  const x = Math.max(min.x, Math.min(max.x, position.x)) - position.x;
  const z = Math.max(min.z, Math.min(max.z, position.z)) - position.z;
  return x * x + z * z < radius * radius - CONTACT_EPSILON * CONTACT_EPSILON;
}

type Point = { x: number; y: number; z: number };
function clipY(input: Point[], y: number, above: boolean): Point[] {
  const out: Point[] = [];
  for (let i = 0; i < input.length; i++) {
    const a = input[i], b = input[(i + 1) % input.length];
    const ia = above ? a.y >= y : a.y <= y, ib = above ? b.y >= y : b.y <= y;
    if (ia) out.push(a);
    if (ia !== ib) {
      const t = (y - a.y) / (b.y - a.y);
      out.push({ x: a.x + (b.x - a.x) * t, y, z: a.z + (b.z - a.z) * t });
    }
  }
  return out;
}
/** Clip a triangle to the actual flat-footed player cylinder's vertical slab,
 * then intersect its convex XZ projection with the player's disk. Double-sided:
 * physical panels cannot be crossed from the back; there is no inflated torso box. */
function triangleCylinder(vertices: Float32Array, offset: number, p: THREE.Vector3, height: number, radius: number): boolean {
  let polygon: Point[] = [];
  for (let k = 0; k < 9; k += 3) polygon.push({ x: vertices[offset + k], y: vertices[offset + k + 1], z: vertices[offset + k + 2] });
  polygon = clipY(clipY(polygon, p.y + CONTACT_EPSILON, true), p.y + height - CONTACT_EPSILON, false);
  if (!polygon.length) return false;
  let positive = false, negative = false, area = 0;
  for (let i = 0; i < polygon.length; i++) {
    const a = polygon[i], b = polygon[(i + 1) % polygon.length];
    const dx = b.x - a.x, dz = b.z - a.z, len = dx * dx + dz * dz;
    const t = len ? THREE.MathUtils.clamp(((p.x - a.x) * dx + (p.z - a.z) * dz) / len, 0, 1) : 0;
    const x = a.x + t * dx - p.x, z = a.z + t * dz - p.z;
    if (x * x + z * z < radius * radius - CONTACT_EPSILON * CONTACT_EPSILON) return true;
    const cross = dx * (p.z - a.z) - dz * (p.x - a.x);
    positive ||= cross > 1e-10; negative ||= cross < -1e-10;
    area += a.x * b.z - b.x * a.z;
  }
  return Math.abs(area) > 1e-10 && !(positive && negative);
}

const local = new THREE.Vector3(), min = new THREE.Vector3(), max = new THREE.Vector3();
export function shapeIntersects(shape: CollisionShape, p: THREE.Vector3, height: number, radius: number,
  stats: CollisionStats): boolean {
  stats.shapeTests++;
  if (!cylinderBox(p, height, radius, shape.bounds.min, shape.bounds.max)) return false;
  if (shape.kind === 'cylinder') {
    const total = radius + shape.radius;
    return (p.x - shape.center.x) ** 2 + (p.z - shape.center.z) ** 2 < total * total - 1e-10;
  }
  if (shape.kind === 'obb') {
    const c = Math.cos(shape.yaw), s = Math.sin(shape.yaw), x = p.x - shape.center.x, z = p.z - shape.center.z;
    local.set(c * x - s * z, p.y - shape.center.y, s * x + c * z);
    min.copy(shape.half).negate(); max.copy(shape.half);
    return cylinderBox(local, height, radius, min, max);
  }
  // Mesh bounds can be zero-thickness (a plane). Use inclusive expanded BVH tests.
  const visit = (node: Node): boolean => {
    stats.bvhNodes++;
    const b = node.bounds;
    if (p.x + radius < b.min.x || p.x - radius > b.max.x || p.z + radius < b.min.z || p.z - radius > b.max.z ||
      p.y + height <= b.min.y + CONTACT_EPSILON || p.y >= b.max.y - CONTACT_EPSILON) return false;
    if (node.left) return visit(node.left) || visit(node.right!);
    for (let j = node.start; j < node.end; j++) {
      stats.triangleTests++;
      if (triangleCylinder(shape.vertices, shape.order[j] * 9, p, height, radius)) return true;
    }
    return false;
  };
  return visit(shape.tree);
}

/** Identify closed triangle islands after welding UV/normal seams. This is lazy:
 * occupancy candidates only, never a per-frame movement or triangle-query scan.
 * Open plates do not acquire a fictitious interior just because their AABB is big. */
function closedComponents(shape: StaticMeshShape): { components: Int32Array; closed: Uint8Array } {
  if (shape.containmentCache) return shape.containmentCache;
  const count = shape.triangleCount, parents = new Int32Array(count), active = new Uint8Array(count);
  for (let i = 0; i < count; i++) parents[i] = i;
  const root = (id: number): number => {
    while (parents[id] !== id) { parents[id] = parents[parents[id]]; id = parents[id]; }
    return id;
  };
  const weld = new Map<string, number>();
  const edges = new Map<string, { triangle: number; count: number; balance: number }>();
  const vertex = (offset: number): number => {
    const a = shape.vertices;
    const key = Math.round(a[offset] * 1e5) + ',' + Math.round(a[offset + 1] * 1e5) + ',' + Math.round(a[offset + 2] * 1e5);
    let id = weld.get(key);
    if (id === undefined) { id = weld.size; weld.set(key, id); }
    return id;
  };
  for (let i = 0; i < count; i++) {
    const a = vertex(i * 9), b = vertex(i * 9 + 3), c = vertex(i * 9 + 6);
    if (a === b || a === c || b === c) continue;
    active[i] = 1;
    for (const [from, to] of [[a, b], [b, c], [c, a]]) {
      const key = Math.min(from, to) + ':' + Math.max(from, to), sign = from < to ? 1 : -1;
      const edge = edges.get(key);
      if (edge) {
        parents[root(i)] = root(edge.triangle);
        edge.count++; edge.balance += sign;
      } else edges.set(key, { triangle: i, count: 1, balance: sign });
    }
  }
  const components = new Int32Array(count), closed = new Uint8Array(count);
  for (let i = 0; i < count; i++) { components[i] = active[i] ? root(i) : -1; if (active[i]) closed[components[i]] = 1; }
  for (const edge of edges.values()) if (edge.count % 2 !== 0 || edge.balance !== 0) closed[root(edge.triangle)] = 0;
  shape.containmentCache = { components, closed };
  return shape.containmentCache;
}

interface WindingHit { triangle: number; distance: number; sign: number }
const occupancyDirections = [
  new THREE.Vector3(1, 0.371, 0.193), new THREE.Vector3(-0.317, 0.719, -1),
  new THREE.Vector3(0.231, -1, 0.617), new THREE.Vector3(-1, -0.419, 0.827),
  new THREE.Vector3(0.613, 0.277, 1), new THREE.Vector3(0.853, -0.691, -0.137),
].map(direction => direction.normalize());
/** Interior occupancy fallback. A positive and negative overlap are NOT combined
 * with global odd/even parity: each closed solid gets its own signed winding.
 * Hollow connected shells (torus/pipe) retain zero winding in their open cavity.
 * The winding mode additionally preserves cavities between disconnected inner
 * and outer shells with opposite orientation. Surface movement remains separate. */
export function meshContainsPoint(shape: StaticMeshShape, point: THREE.Vector3, stats: CollisionStats): boolean {
  if (shape.containment === 'surface' || !shape.bounds.containsPoint(point)) return false;
  const a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3();
  const hit = new THREE.Vector3(), normal = new THREE.Vector3(), edge = new THREE.Vector3(), bary = new THREE.Vector3();
  // Retry edge/vertex-grazing rays instead of deduplicating by hit distance:
  // coincident faces can be TWO overlapping solids and must both contribute.
  const probes: WindingHit[][] = [];
  for (const direction of occupancyDirections) {
    const ray = new THREE.Ray(point, direction), hits: WindingHit[] = [];
    let ambiguous = false;
    const visit = (node: Node): void => {
      stats.bvhNodes++;
      if (!ray.intersectsBox(node.bounds)) return;
      if (node.left) { visit(node.left); visit(node.right!); return; }
      for (let i = node.start; i < node.end; i++) {
        stats.triangleTests++;
        const triangle = shape.order[i], offset = triangle * 9;
        a.fromArray(shape.vertices, offset); b.fromArray(shape.vertices, offset + 3); c.fromArray(shape.vertices, offset + 6);
        if (!ray.intersectTriangle(a, b, c, false, hit)) continue;
        const distance = hit.distanceTo(point);
        if (distance < CONTACT_EPSILON) continue; // surface contact was tested first
        THREE.Triangle.getBarycoord(hit, a, b, c, bary);
        if (Math.min(Math.abs(bary.x), Math.abs(bary.y), Math.abs(bary.z)) < 1e-9) { ambiguous = true; continue; }
        normal.subVectors(b, a).cross(edge.subVectors(c, a));
        const dot = normal.dot(direction);
        if (Math.abs(dot) > 1e-12) hits.push({ triangle, distance, sign: Math.sign(dot) });
      }
    };
    visit(shape.tree);
    if (ambiguous) continue;
    // A point with a clear escape ray is not enclosed. This avoids even building
    // topology for the usual empty areas between a batched model's legs.
    if (!hits.length) return false;
    probes.push(hits);
    if (probes.length === 2) break;
  }
  if (!probes.length) return false;
  const { components, closed } = closedComponents(shape);
  let possible: Set<number> | undefined;
  let windingSign = 0;
  for (const hits of probes) {
    hits.sort((a, b) => a.distance - b.distance);
    const counts = new Map<number, number>();
    for (const hit of hits) {
      const component = components[hit.triangle];
      if (component < 0 || !closed[component]) continue;
      counts.set(component, (counts.get(component) ?? 0) + hit.sign);
    }
    if (shape.containment === 'winding') {
      const sum = [...counts.values()].reduce((total, count) => total + count, 0);
      if (!sum || (windingSign && Math.sign(sum) !== windingSign)) return false;
      windingSign = Math.sign(sum);
    } else {
      const inside = new Set([...counts].filter(([, count]) => count !== 0).map(([component]) => component));
      possible = possible ? new Set([...possible].filter(component => inside.has(component))) : inside;
      if (!possible.size) return false;
    }
  }
  return shape.containment === 'winding' ? windingSign !== 0 : !!possible?.size;
}

/** BVH segment traversal; no allocation or raycaster scan per triangle. */
export function shapeBlocksSegment(shape: CollisionShape, ray: THREE.Ray, length: number, stats: CollisionStats): boolean {
  const hit = new THREE.Vector3();
  const hitsBox = (box: THREE.Box3): boolean => box.containsPoint(ray.origin) ||
    !!(ray.intersectBox(box, hit) && hit.distanceTo(ray.origin) < length - 1e-4);
  if (!hitsBox(shape.bounds)) return false;
  if (shape.kind === 'obb') {
    const matrix = new THREE.Matrix4().makeRotationY(shape.yaw).setPosition(shape.center).invert();
    const localRay = ray.clone().applyMatrix4(matrix);
    const bounds = new THREE.Box3(shape.half.clone().negate(), shape.half);
    return bounds.containsPoint(localRay.origin) || !!(localRay.intersectBox(bounds, hit) && hit.distanceTo(localRay.origin) < length - 1e-4);
  }
  if (shape.kind === 'cylinder') {
    const x = ray.origin.x - shape.center.x, z = ray.origin.z - shape.center.z;
    const bottom = shape.bounds.min.y, top = shape.bounds.max.y;
    if (x*x + z*z <= shape.radius**2 && ray.origin.y >= bottom && ray.origin.y <= top) return true;
    const a = ray.direction.x**2 + ray.direction.z**2, b = 2*(x*ray.direction.x + z*ray.direction.z);
    const c = x*x + z*z - shape.radius**2, d = b*b - 4*a*c;
    if (a > 1e-12 && d >= 0) for (const t of [(-b-Math.sqrt(d))/(2*a),(-b+Math.sqrt(d))/(2*a)]) {
      const y = ray.origin.y + ray.direction.y*t;
      if (t >= 0 && t < length-1e-4 && y >= bottom && y <= top) return true;
    }
    if (Math.abs(ray.direction.y) > 1e-12) for (const y of [bottom,top]) {
      const t = (y-ray.origin.y)/ray.direction.y;
      if (t >= 0 && t < length-1e-4 && (x+ray.direction.x*t)**2+(z+ray.direction.z*t)**2 <= shape.radius**2) return true;
    }
    return false;
  }
  const a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3();
  const visit = (node: Node): boolean => {
    stats.bvhNodes++;
    if (!hitsBox(node.bounds)) return false;
    if (node.left) return visit(node.left) || visit(node.right!);
    for (let i=node.start;i<node.end;i++) {
      stats.triangleTests++;
      const offset=shape.order[i]*9;
      a.fromArray(shape.vertices,offset); b.fromArray(shape.vertices,offset+3); c.fromArray(shape.vertices,offset+6);
      if (ray.intersectTriangle(a,b,c,false,hit) && hit.distanceTo(ray.origin)<length-1e-4) return true;
    }
    return false;
  };
  return visit(shape.tree);
}
