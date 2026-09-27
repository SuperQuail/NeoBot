/** Non-playable foundry depth. No floor, interaction, or collision is registered here.
 * The opaque shell closes every view beyond the removed 32 m glass sidewalls.
 * Broad extruded profiles, rather than tubes, carry the cathedral silhouette. */
import * as THREE from 'three';
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';
import type { ShipMaterials } from './materials';

type V = [number, number, number];

class ArchitectureBatch {
  private readonly batches = new Map<THREE.Material, THREE.BufferGeometry[]>();
  constructor(readonly group: THREE.Group) {}
  add(geometry: THREE.BufferGeometry, material: THREE.Material, p: V = [0, 0, 0], r: V = [0, 0, 0]): void {
    geometry.applyMatrix4(new THREE.Matrix4().compose(new THREE.Vector3(...p),
      new THREE.Quaternion().setFromEuler(new THREE.Euler(...r)), new THREE.Vector3(1, 1, 1)));
    const flat = geometry.index ? geometry.toNonIndexed() : geometry;
    if (flat !== geometry) geometry.dispose();
    flat.deleteAttribute('uv');
    const list = this.batches.get(material) ?? [];
    list.push(flat); this.batches.set(material, list);
  }
  box(p: V, size: V, material: THREE.Material): void {
    this.add(new THREE.BoxGeometry(...size), material, p);
  }
  profile(shape: THREE.Shape, depth: number, material: THREE.Material, p: V, r: V = [0, 0, 0], bevel = 0.12): void {
    const geometry = new THREE.ExtrudeGeometry(shape, { depth, steps: 1, curveSegments: 18,
      bevelEnabled: bevel > 0, bevelSize: bevel, bevelThickness: bevel, bevelSegments: 2 });
    geometry.translate(0, 0, -depth / 2);
    this.add(geometry, material, p, r);
  }
  finish(): void {
    let index = 0;
    for (const [material, geometries] of this.batches) {
      const geometry = mergeGeometries(geometries, false);
      geometries.forEach(g => g.dispose());
      if (!geometry) throw new Error('Incompatible foundry architecture geometry');
      geometry.computeBoundingSphere();
      const mesh = new THREE.Mesh(geometry, material);
      mesh.name = this.group.name + '-surface-' + index++;
      mesh.receiveShadow = true;
      mesh.matrixAutoUpdate = false;
      this.group.add(mesh);
    }
  }
}

/** A blade with a convex shoulder, tapering to a carved point. In its local XY plane. */
function blade(width: number, height: number): THREE.Shape {
  const s = new THREE.Shape();
  s.moveTo(0, -height * 0.52);
  s.bezierCurveTo(-width * 0.42, -height * 0.25, -width * 0.56, height * 0.18, -width * 0.31, height * 0.31);
  s.quadraticCurveTo(-width * 0.1, height * 0.43, 0, height * 0.53);
  s.quadraticCurveTo(width * 0.1, height * 0.43, width * 0.31, height * 0.31);
  s.bezierCurveTo(width * 0.56, height * 0.18, width * 0.42, -height * 0.25, 0, -height * 0.52);
  return s;
}

/** Full-height load-bearing rib: 6 m thick at the haunch, sharp at its crown. */
function vaultRib(): THREE.Shape {
  const s = new THREE.Shape();
  s.moveTo(30.6, 0);
  s.bezierCurveTo(32.8, 12, 32, 25, 26, 33);
  s.bezierCurveTo(21, 40, 12, 44, 4.8, 48);
  s.bezierCurveTo(18, 48, 31, 43, 36.1, 31);
  s.bezierCurveTo(40.8, 20, 37.3, 7, 36.9, 0);
  s.closePath();
  return s;
}

function ribInset(): THREE.Shape {
  const s = new THREE.Shape();
  s.moveTo(33.05, 6);
  s.bezierCurveTo(36, 21, 31.6, 32, 27, 36.5);
  s.quadraticCurveTo(19, 43, 10.4, 46.2);
  s.bezierCurveTo(22, 44, 32.5, 38.8, 35, 29);
  s.quadraticCurveTo(39, 17, 33.05, 6);
  return s;
}

function ribInlay(): THREE.Shape {
  const s = new THREE.Shape();
  s.moveTo(31.8, 8);
  s.bezierCurveTo(34, 24, 29, 34, 21, 40.2);
  s.quadraticCurveTo(14, 45, 7.8, 47);
  s.quadraticCurveTo(14, 44.6, 20.9, 40);
  s.bezierCurveTo(28.6, 33.6, 33.5, 23.8, 31.65, 8);
  return s;
}

/** Rounded, pointed suspended apron, shaped in plan rather than a box balcony. */
function terrace(): THREE.Shape {
  const s = new THREE.Shape();
  s.moveTo(79, -8.3); s.lineTo(79, 8.3);
  s.bezierCurveTo(67, 8.5, 48, 7.8, 37.5, 0);
  s.bezierCurveTo(48, -7.8, 67, -8.5, 79, -8.3);
  return s;
}

/** Quiet distant sentinel/armature, deliberately not another smooth sphere. */
function dockedArmature(b: ArchitectureBatch, x: number, y: number, z: number, m: ShipMaterials, glow: THREE.Material): void {
  // Profiles face into the hall (local profile Z becomes world X).
  const face: V = [0, -Math.PI / 2, 0];
  b.profile(blade(3.7, 7.2), 1.2, m.ceiling, [x, y + 7, z], face);
  b.profile(blade(2.8, 5.8), 0.3, m.prop, [x - 0.78, y + 7.2, z], face);
  b.profile(blade(1.35, 4.3), 0.17, m.ceiling, [x - 1, y + 7.2, z], face);
  b.profile(blade(0.36, 2), 0.08, glow, [x - 1.14, y + 7.5, z], face, 0.025);
  for (const side of [-1, 1]) {
    b.profile(blade(1.2, 5.3), 0.7, m.hull, [x, y + 3.2, z + side * 1.4],
      [side * 0.21, -Math.PI / 2, 0]);
    b.profile(blade(0.9, 5.9), 0.65, m.prop, [x + 0.35, y + 7.2, z + side * 2.7],
      [-side * 0.33, -Math.PI / 2, 0]);
    b.box([x - 0.15, y + 1, z + side * 1.85], [2.1, 0.5, 0.62], m.ceiling);
  }
  b.profile(blade(1.7, 3.4), 0.7, m.hull, [x, y + 11.7, z], face);
  b.profile(blade(0.35, 1.7), 0.08, glow, [x - 0.45, y + 11.9, z], face, 0.02);
}

export function buildFoundryArchitecture(materials: ShipMaterials, activeSides: number[]): THREE.Group {
  const root = new THREE.Group();
  root.name = 'foundry-temple-architecture';
  root.userData.nonPlayable = true;
  root.userData.layers = [15, 32, 50];
  root.userData.opaqueEnvelope = { x: [-82, 82], y: [-23, 71], z: [13, 59] };
  // Blue comes from deep opaque recesses, not transparent glazing or overpowered lamps.
  const abyss = new THREE.MeshBasicMaterial({ color: 0x071323, toneMapped: true });
  abyss.name = 'foundry-blue-abyss';
  const rim = new THREE.MeshBasicMaterial({ color: 0x4b7b9e, toneMapped: true });
  rim.name = 'foundry-muted-cold-inlay';
  const farRim = new THREE.MeshBasicMaterial({ color: 0x203d60, toneMapped: true });
  farRim.name = 'foundry-distance-blue';
  const m = materials;
  for (const side of activeSides) {
    const wing = new THREE.Group();
    wing.name = side < 0 ? 'war-forge-temple-wing' : 'robot-forge-temple-wing';
    wing.scale.x = side;
    root.add(wing);
    const b = new ArchitectureBatch(wing);
    // Solid architectural envelope. The far wall is not an exterior window.
    b.box([81, 24, 36], [2, 94, 46], m.ceiling);
    b.box([56.5, -21, 36], [51, 2, 46], m.ceiling);
    b.box([41, 70, 36], [82, 2, 46], m.ceiling);
    for (const z of [13.5, 58.5]) {
      b.box([57, 24, z], [50, 94, 1], m.ceiling);
      // Align the scenic end returns to the inhabited ±5.5 m axial partitions.
      // Interior owns the actual rear door and corridor; no scenic slab intrudes.
      b.box([18.75, 7.5, z], [26.5, 15, 1], m.ceiling);
      b.box([16, 43, z], [32, 56, 1], m.ceiling);
      for (const x of [12, 25]) {
        b.profile(blade(9, 23), 1, m.prop, [x, 12, z + (z < 36 ? 0.75 : -0.75)]);
        b.profile(blade(7.2, 20.5), 0.24, m.ceiling, [x, 12, z + (z < 36 ? 1.5 : -1.5)]);
      }
    }
    b.box([79.8, 24, 36], [0.2, 89, 43], abyss);
    // Blue light wells, interrupted by the three projecting tiers.
    for (const z of [18.5, 36.5, 54.5]) {
      b.profile(blade(4.6, 78), 0.3, farRim, [79.4, 25, z], [0, -Math.PI / 2, 0]);
      b.profile(blade(1.2, 66), 0.32, rim, [79.1, 25, z], [0, -Math.PI / 2, 0]);
    }
    for (const z of [15.5, 36.5, 57]) {
      b.profile(vaultRib(), 3, m.prop, [0, 0, z], [0, 0, 0], 0.24);
      for (const face of [-1, 1]) {
        b.profile(ribInset(), 0.2, m.ceiling, [0, 0, z + face * 1.66]);
        b.profile(ribInlay(), 0.08, rim, [0, 0, z + face * 1.8], [0, 0, 0], 0.01);
        // Nested engraved scales on the lower haunch create relief without striping the whole room.
        for (let i = 0; i < 4; i++) {
          const x = 34.2 + Math.sin(i * 0.6) * 0.4;
          b.profile(blade(2.5, 5.2), 0.22, m.hull, [x, 5.5 + i * 5.2, z + face * 1.82]);
          b.profile(blade(1.5, 3.8), 0.16, m.ceiling, [x, 5.5 + i * 5.2, z + face * 1.99]);
        }
      }
      // A second, farther order reads through the gaps, at a different scale.
      for (let tier = 0; tier < 3; tier++) {
        const x = 57 + tier * 6, y = 14 + tier * 17;
        b.profile(blade(7, 23), 3.2, m.hull, [x, y + 5, z]);
        b.profile(blade(4.4, 18), 0.3, m.ceiling, [x, y + 5, z - 1.85]);
        b.profile(blade(0.3, 12), 0.1, farRim, [x - 0.8, y + 6, z - 2.05]);
      }
    }
    for (let tier = 0; tier < 3; tier++) {
      const y = [15, 32, 50][tier];
      for (const z of [26, 47]) {
        // Massive cantilever with a dark top, an antique-gold apron and a keel below.
        b.profile(terrace(), 1.55, m.prop, [0, y, z], [Math.PI / 2, 0, 0], 0.2);
        b.profile(terrace(), 0.16, m.ceiling, [0, y + 0.98, z], [Math.PI / 2, 0, 0], 0.05);
        const keel = new THREE.Shape();
        keel.moveTo(39, 0); keel.bezierCurveTo(48, -1, 64, -3, 78, -10);
        keel.lineTo(79, 0); keel.closePath();
        b.profile(keel, 2.7, m.hull, [0, y - 0.5, z]);
        b.profile(blade(2.6, 8), 0.35, m.ceiling, [55, y - 4.1, z - 1.6], [0, 0, -0.62]);
        // Only a hairline cold edge; no rail that implies an accessible route.
        const edge = new THREE.Shape();
        edge.moveTo(39, 0); edge.bezierCurveTo(50, -6.3, 68, -7.65, 78, -7.5);
        edge.lineTo(78, -7.37); edge.bezierCurveTo(67, -7.5, 50, -6.1, 39, 0);
        b.profile(edge, 0.07, tier === 0 ? rim : farRim, [0, y + 0.98, z], [Math.PI / 2, 0, 0], 0);
        // Backing shrine: wide black recess nested inside a heavy gold pointed surround.
        const dockX = 60 + tier * 5;
        b.profile(blade(13.5, 16), 2, m.prop, [dockX + 3, y + 9, z], [0, -Math.PI / 2, 0], 0.25);
        b.profile(blade(11.4, 14.5), 0.4, m.ceiling, [dockX + 1.75, y + 9, z], [0, -Math.PI / 2, 0]);
        dockedArmature(b, dockX, y + 1.1, z, m, tier === 0 ? rim : farRim);
        for (const offset of [-6.4, 6.4]) {
          b.profile(blade(1.4, 12.5), 1.1, m.hull, [dockX - 2, y + 7, z + offset], [0, -Math.PI / 2, 0]);
          b.profile(blade(0.21, 7), 0.07, farRim, [dockX - 2.7, y + 8, z + offset], [0, -Math.PI / 2, 0], 0);
        }
      }
    }
    // The observable chasm starts outside the playable slab; these skirts hide the floor's cut edge.
    b.box([32.1, -3.5, 36], [1, 7, 44], m.prop);
    b.box([32.7, -10, 36], [1.1, 8, 44], m.ceiling);
    for (const z of [21, 30, 43, 52]) {
      b.profile(blade(3.2, 15), 1.7, m.hull, [33.5, -7, z]);
      b.box([33.7, -15.5, z], [0.2, 0.12, 5.5], farRim);
    }
    // Upper roof has engraved armor fields rather than a luminous flat ceiling.
    for (const z of [25, 47]) {
      b.profile(blade(18, 57), 1.3, m.hull, [40, 68.4, z], [Math.PI / 2, 0, Math.PI / 2]);
      b.profile(blade(14, 49), 0.3, m.ceiling, [40, 67.5, z], [Math.PI / 2, 0, Math.PI / 2]);
    }
    b.finish();
    // Narrow local pools reveal the carved haunches, not the whole room.
    for (const z of [26, 47]) {
      const light = new THREE.PointLight(0x6895cc, 95, 38, 2);
      light.name = 'foundry-recess-cold-bounce';
      light.position.set(40, 18, z);
      wing.add(light);
    }
    // Atmospheric scrims live beyond the walkable floor. They do not replace
    // the opaque back/end shell, and must share the renderer's logarithmic depth.
    for (const x of [43, 72]) {
      const haze = new THREE.ShaderMaterial({
        transparent: true, depthWrite: false, side: THREE.DoubleSide,
        uniforms: { tint: { value: new THREE.Color(0x315a90) }, strength: { value: x === 43 ? 0.16 : 0.24 } },
        vertexShader: `
          varying vec2 airUv;
          #include <common>
          #include <logdepthbuf_pars_vertex>
          void main() {
            airUv = uv;
            gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
            #include <logdepthbuf_vertex>
          }`,
        fragmentShader: `
          uniform vec3 tint;
          uniform float strength;
          varying vec2 airUv;
          #include <common>
          #include <logdepthbuf_pars_fragment>
          void main() {
            #include <logdepthbuf_fragment>
            vec2 q = airUv * 2.0 - 1.0;
            float edge = (1.0 - smoothstep(0.48, 1.0, abs(q.x))) * (1.0 - smoothstep(0.45, 1.0, abs(q.y)));
            float column = 0.46 + 0.54 * pow(0.5 + 0.5 * sin(airUv.x * 19.0 + airUv.y * 2.0), 4.0);
            float depth = 0.65 + 0.35 * smoothstep(-0.8, 0.8, q.y);
            gl_FragColor = vec4(tint, strength * edge * column * depth);
            #include <tonemapping_fragment>
            #include <colorspace_fragment>
          }`,
      });
      haze.name = 'foundry-local-blue-air';
      const curtain = new THREE.Mesh(new THREE.PlaneGeometry(43, 82), haze);
      curtain.name = 'non-playable-depth-haze';
      curtain.position.set(x, 26, 36);
      curtain.rotation.y = Math.PI / 2;
      wing.add(curtain);
    }
  }
  return root;
}
