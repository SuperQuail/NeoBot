// Low Khalai chart basin: segmented armor, ceramic wells and a suspended stellar map.
import * as THREE from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { terminalLayout, placeOperatingSurface } from './terminal-layout';

export type ConsoleKey = 'scroll-up' | 'refresh' | 'scroll-down';

export class ConsoleModel {
  readonly group = new THREE.Group();
  readonly panel = new THREE.Group();
  readonly keys: THREE.Mesh[] = [];
  private readonly core = new THREE.Group();
  private readonly gimbal = new THREE.Group();
  private readonly gold = new THREE.MeshStandardMaterial({ color: 0x827452, metalness: 0.72, roughness: 0.48 });
  private readonly edge = new THREE.MeshStandardMaterial({ color: 0xb4a07a, metalness: 0.7, roughness: 0.4 });
  private readonly plate = new THREE.MeshStandardMaterial({ color: 0xa18b59, metalness: 0.6, roughness: 0.46, emissive: 0x251907, emissiveIntensity: 0.09 });
  private readonly enamel = new THREE.MeshStandardMaterial({ color: 0x36535c, metalness: 0.38, roughness: 0.4 });
  private readonly obsidian = new THREE.MeshStandardMaterial({ color: 0x081316, metalness: 0.55, roughness: 0.38 });
  private readonly ceramic = new THREE.MeshStandardMaterial({ color: 0x163b40, metalness: 0.36, roughness: 0.4 });
  private readonly light = new THREE.MeshBasicMaterial({ color: 0x278de8, toneMapped: false });
  private readonly projection = new THREE.MeshBasicMaterial({ color: 0x217dd3, transparent: true, opacity: 0.38,
    depthWrite: false, blending: THREE.AdditiveBlending, toneMapped: false });
  private readonly gridMaterial = new THREE.LineBasicMaterial({ color: 0x48a6dd, transparent: true, opacity: 0.4, depthWrite: false });
  private readonly geometries = new Set<THREE.BufferGeometry>();
  private readonly particleMaterial = new THREE.PointsMaterial({ color: 0x63c9ff, size: 0.025,
    transparent: true, opacity: 0.75, depthWrite: false, blending: THREE.AdditiveBlending });
  private time = 0;
  private disposed = false;

  constructor(accent: number, panelWidth = 2.5, panelHeight = 1.40625, private readonly stationId = 'config') {
    if (stationId !== 'navigation') {
      this.buildInstrument(panelWidth, panelHeight);
      return;
    }
    this.group.name = 'khalai-segmented-star-basin';
    // Keep the star chart blue; station colors belong to small status jewels only.
    void accent;
    const batches = new Map<THREE.Material, THREE.BufferGeometry[]>();
    const part = (geometry: THREE.BufferGeometry, material: THREE.Material,
      position: [number, number, number] = [0, 0, 0], rotation: [number, number, number] = [0, 0, 0],
      scale: [number, number, number] = [1, 1, 1]) => {
      const flat = geometry.index ? geometry.toNonIndexed() : geometry.clone();
      geometry.dispose(); flat.deleteAttribute('uv');
      flat.applyMatrix4(new THREE.Matrix4().compose(new THREE.Vector3(...position),
        new THREE.Quaternion().setFromEuler(new THREE.Euler(...rotation)), new THREE.Vector3(...scale)));
      const list = batches.get(material) ?? []; list.push(flat); batches.set(material, list);
    };
    const ring = (profile: number[][], start = 0, length = Math.PI * 2) =>
      new THREE.LatheGeometry(profile.map(([r, y]) => new THREE.Vector2(r, y)), Math.max(8, Math.ceil(length * 18)), start, length);
    const armor = [[1.06, 0.22], [1.29, 0.28], [1.4, 0.46], [1.41, 0.71], [1.32, 0.94],
      [1.22, 1.02], [0.88, 0.98], [0.8, 0.89], [0.84, 0.75], [1.05, 0.68], [1.06, 0.22]];
    part(new THREE.CylinderGeometry(1.31, 1.44, 0.14, 64), this.obsidian, [0, 0.1, 0]);
    part(ring([[1.27, 0.15], [1.36, 0.19], [1.31, 0.26], [1.27, 0.15]]), this.edge);
    part(ring(armor), this.obsidian, [0, -0.008, 0], [0, 0, 0], [0.994, 1, 0.994]);
    // Broad curved plates separated by black expansion seams, not thin gold rails.
    for (let i = 0; i < 12; i++) {
      const a = i * Math.PI / 6 + 0.024;
      part(ring(armor, a, Math.PI / 6 - 0.048), i % 3 === 0 ? this.edge : this.gold);
      part(ring([[1.405, 0.48], [1.435, 0.51], [1.435, 0.66], [1.403, 0.72], [1.405, 0.48]], a + 0.035, Math.PI / 6 - 0.118), this.ceramic);
      part(ring([[1.29, 0.975], [1.265, 0.994], [1.01, 1.008], [1.00, 0.998], [1.29, 0.975]], a + 0.07, Math.PI / 6 - 0.18), this.ceramic);
      // Paired engraved chevrons follow the actual curved shell.
      for (const y of [0.38, 0.42]) part(ring([[1.365, y], [1.38, y + 0.013], [1.39, y + 0.026]], a + 0.055, Math.PI / 6 - 0.16), this.obsidian);
      const angle = a + 0.24;
      part(new THREE.SphereGeometry(0.045, 8, 6), this.light,
        [Math.sin(angle) * 1.414, 0.585, Math.cos(angle) * 1.414], [0, angle, 0], [0.65, 1.5, 0.45]);
    }
    part(ring([[0.69, 0.69], [0.79, 0.74], [0.86, 0.88], [0.84, 0.93], [0.79, 0.94], [0.74, 0.82], [0.69, 0.69]]), this.ceramic);
    part(new THREE.CylinderGeometry(0.77, 0.77, 0.045, 64), this.obsidian, [0, 0.77, 0]);
    part(new THREE.CylinderGeometry(0.73, 0.73, 0.013, 64), this.projection, [0, 0.8, 0]);
    for (const r of [0.36, 0.62, 0.77]) part(new THREE.TorusGeometry(r, 0.009, 4, 64), this.light, [0, 0.816, 0], [Math.PI / 2, 0, 0]);
    // Two swept leaf shoulders, deliberately behind the operating arc.
    const leaf = new THREE.Shape();
    leaf.moveTo(0.99, 0.3); leaf.bezierCurveTo(1.45, 0.41, 1.5, 0.92, 1.41, 1.47);
    leaf.bezierCurveTo(1.3, 1.18, 1.21, 1.02, 1.13, 0.95);
    leaf.bezierCurveTo(1.05, 0.77, 1.22, 0.56, 0.99, 0.3); leaf.closePath();
    const extrude = (shape: THREE.Shape, depth: number, bevel = 0.025) => {
      const g = new THREE.ExtrudeGeometry(shape, { depth, bevelEnabled: true, bevelThickness: bevel,
        bevelSize: bevel, bevelSegments: 2, curveSegments: 12, steps: 1 });
      g.translate(0, 0, -depth / 2); return g;
    };
    // Sculpted petal armor: chamfered polygon plates wrapped around the belly.
    // Subdivide BEFORE bending so broad face triangles cannot cut through the circular hull.
    const curvedPlate = (shape: THREE.Shape, yaw: number, relief: number, depth: number, bevel: number) => {
      const source = extrude(shape, depth, bevel);
      const original = source.getAttribute('position');
      let vertices = Array.from(original.array);
      for (let pass = 0; pass < 1; pass++) {
        const refined: number[] = [];
        for (let i = 0; i < vertices.length; i += 9) {
          const a = vertices.slice(i, i + 3), b = vertices.slice(i + 3, i + 6), c = vertices.slice(i + 6, i + 9);
          const ab = a.map((v, j) => (v + b[j]) / 2), bc = b.map((v, j) => (v + c[j]) / 2), ca = c.map((v, j) => (v + a[j]) / 2);
          refined.push(...a, ...ab, ...ca, ...ab, ...b, ...bc, ...ca, ...bc, ...c, ...ab, ...bc, ...ca);
        }
        vertices = refined;
      }
      source.dispose();
      for (let i = 0; i < vertices.length; i += 3) {
        const a = yaw + vertices[i] / 1.44, y = vertices[i + 1];
        const r = 1.415 + Math.sin((y - 0.22) / 0.74 * Math.PI) * 0.035 + relief + vertices[i + 2];
        vertices[i] = Math.sin(a) * r; vertices[i + 2] = Math.cos(a) * r;
      }
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3)); geometry.computeVertexNormals();
      return geometry;
    };
    const armorPetal = new THREE.Shape();
    armorPetal.moveTo(-0.55, 0.65); armorPetal.lineTo(-0.43, 0.87); armorPetal.lineTo(-0.11, 0.91);
    armorPetal.lineTo(0.42, 0.82); armorPetal.lineTo(0.55, 0.61); armorPetal.lineTo(0.37, 0.34);
    armorPetal.lineTo(0.02, 0.265); armorPetal.lineTo(-0.39, 0.35); armorPetal.closePath();
    const inlay = new THREE.Shape();
    inlay.moveTo(-0.38, 0.59); inlay.lineTo(-0.28, 0.735); inlay.lineTo(0.12, 0.765);
    inlay.lineTo(0.35, 0.64); inlay.lineTo(0.23, 0.46); inlay.lineTo(-0.08, 0.42);
    inlay.lineTo(-0.29, 0.46); inlay.closePath();
    const furrow = new THREE.Shape();
    furrow.moveTo(-0.34, 0.55); furrow.lineTo(-0.17, 0.6); furrow.lineTo(0.25, 0.7);
    furrow.lineTo(0.05, 0.56); furrow.lineTo(-0.12, 0.52); furrow.lineTo(-0.28, 0.49); furrow.closePath();
    for (let i = 0; i < 6; i++) {
      const yaw = i * Math.PI / 3 + Math.PI / 6;
      part(curvedPlate(armorPetal, yaw, 0.018, 0.05, 0.018), this.obsidian);
      part(curvedPlate(armorPetal, yaw, 0.042, 0.035, 0.011), this.plate);
      part(curvedPlate(inlay, yaw, 0.065, 0.016, 0.012), this.edge);
      part(curvedPlate(inlay, yaw, 0.077, 0.008, 0.001), this.enamel);
      part(curvedPlate(furrow, yaw, 0.085, 0.012, 0.004), this.obsidian);
      // A narrow incised counter-stroke separates the raised gold shoulder from the inset.
      const cut = new THREE.Shape();
      cut.moveTo(-0.33, 0.79); cut.lineTo(-0.08, 0.845); cut.lineTo(0.30, 0.78);
      cut.lineTo(0.29, 0.766); cut.lineTo(-0.07, 0.829); cut.lineTo(-0.34, 0.775); cut.closePath();
      part(curvedPlate(cut, yaw, 0.065, 0.006, 0.002), this.obsidian);
    }
    for (const side of [-1, 1]) {
      part(extrude(leaf, 0.18), this.gold, [0, 0, -0.34], [0, side === 1 ? 0 : Math.PI, 0]);
      part(extrude(leaf, 0.195, 0.01), this.ceramic, [side * 0.08, 0.1, -0.34], [0, side === 1 ? 0 : Math.PI, 0], [0.89, 0.81, 1]);
    }
    // A heraldic shield overlaps the front armor, never the button sightlines.
    const shield = new THREE.Shape();
    shield.moveTo(0, 0.84); shield.bezierCurveTo(0.12, 0.63, 0.29, 0.62, 0.32, 0.47);
    shield.lineTo(0.19, 0.3); shield.lineTo(0, 0.12); shield.lineTo(-0.19, 0.3);
    shield.lineTo(-0.32, 0.47); shield.bezierCurveTo(-0.29, 0.62, -0.12, 0.63, 0, 0.84); shield.closePath();
    part(extrude(shield, 0.11), this.edge, [0, 0, 1.36]);
    part(extrude(shield, 0.025, 0.008), this.obsidian, [0, 0.065, 1.434], [0, 0, 0], [0.77, 0.77, 1]);
    part(extrude(shield, 0.03, 0.008), this.gold, [0, 0.12, 1.45], [0, 0, 0], [0.5, 0.6, 1]);
    // Split heraldic blade and branching veins, in relief rather than a flat diamond decal.
    const spine = new THREE.Shape();
    spine.moveTo(0, 0.855); spine.lineTo(0.063, 0.63); spine.lineTo(0.045, 0.49);
    spine.lineTo(0.095, 0.38); spine.lineTo(0, 0.14); spine.lineTo(-0.095, 0.38);
    spine.lineTo(-0.045, 0.49); spine.lineTo(-0.063, 0.63); spine.closePath();
    part(extrude(spine, 0.04, 0.013), this.plate, [0, 0, 1.491]);
    const cleft = new THREE.Shape();
    cleft.moveTo(0, 0.81); cleft.lineTo(0.012, 0.61); cleft.lineTo(0.01, 0.38);
    cleft.lineTo(0, 0.20); cleft.lineTo(-0.01, 0.38); cleft.lineTo(-0.012, 0.61); cleft.closePath();
    part(extrude(cleft, 0.007, 0.001), this.obsidian, [0, 0, 1.526]);
    for (const side of [-1, 1]) {
      const vein = new THREE.Shape();
      vein.moveTo(side * 0.05, 0.63); vein.lineTo(side * 0.18, 0.55); vein.lineTo(side * 0.29, 0.48);
      vein.lineTo(side * 0.2, 0.4); vein.lineTo(side * 0.13, 0.26); vein.lineTo(side * 0.16, 0.46);
      vein.lineTo(side * 0.11, 0.50); vein.closePath();
      part(extrude(vein, 0.018, 0.009), this.edge, [0, 0, 1.485]);
      const vane = new THREE.Shape();
      vane.moveTo(side * 0.08, 0.57); vane.lineTo(side * 0.135, 0.52); vane.lineTo(side * 0.115, 0.40);
      vane.lineTo(side * 0.065, 0.46); vane.closePath();
      part(extrude(vane, 0.02, 0.006), this.enamel, [0, 0, 1.5]);
    }
    part(new THREE.SphereGeometry(0.038, 8, 6), this.light, [0, 0.45, 1.551], [0, 0, 0], [0.65, 1.65, 0.45]);
    for (const [material, geometries] of batches) {
      const merged = mergeGeometries(geometries, false);
      geometries.forEach(g => g.dispose());
      if (!merged) throw new Error('Console geometry batching failed');
      const armorMesh = this.addMesh(this.group, merged, material);
      armorMesh.name = 'basin-armor';
      armorMesh.scale.set(0.91, 1, 0.91);
    }

    // Legacy canvas is a small sloped insert, not an upright display wall.
    this.panel.position.set(0, 1.015, 1.025); this.panel.rotation.x = -1.02;
    this.group.add(this.panel);
    this.addMesh(this.panel, new THREE.BoxGeometry(panelWidth + 0.13, panelHeight + 0.12, 0.07), this.gold);
    const seat = this.addMesh(this.panel, new THREE.BoxGeometry(panelWidth + 0.025, panelHeight + 0.025, 0.035), this.obsidian);
    seat.position.z = 0.048;
    const names: ConsoleKey[] = ['scroll-up', 'refresh', 'scroll-down'];
    names.forEach((name, index) => {
      const key = this.addMesh(this.panel, new THREE.CylinderGeometry(0.066, 0.079, 0.05, 6), this.edge);
      key.rotation.x = Math.PI / 2;
      key.position.set((index - 1) * 0.25, -panelHeight / 2 - 0.055, 0.07);
      key.name = 'console-key-' + name; key.userData.consoleKey = name; this.keys.push(key);
      const glyphGeometry = index === 1
        ? new THREE.TorusGeometry(0.026, 0.006, 4, 14, Math.PI * 1.7)
        : new THREE.CircleGeometry(0.03, 3);
      const glyph = this.addMesh(this.panel, glyphGeometry, this.light);
      glyph.position.copy(key.position); glyph.position.z += 0.033;
      if (index !== 1) glyph.rotation.z = index === 0 ? Math.PI / 2 : -Math.PI / 2;
    });
    this.core.position.set(0, 1.43, -0.12); this.group.add(this.core);
    this.addMesh(this.core, new THREE.SphereGeometry(0.29, 28, 16), this.projection);
    const gridSphere = new THREE.SphereGeometry(0.3, 12, 8);
    const grid = new THREE.WireframeGeometry(gridSphere);
    gridSphere.dispose();
    this.geometries.add(grid);
    const lines = new THREE.LineSegments(grid, this.gridMaterial); this.core.add(lines);
    this.gimbal.position.copy(this.core.position); this.group.add(this.gimbal);
    for (let i = 0; i < 3; i++) {
      const orbit = this.addMesh(this.gimbal, new THREE.TorusGeometry(0.43 + i * 0.12, 0.006, 4, 64), this.light);
      orbit.rotation.set(0.9 + i * 0.43, i * 0.7, i * 0.55);
      const planet = this.addMesh(orbit, new THREE.SphereGeometry(0.032 + i * 0.006, 10, 8), this.light);
      planet.position.x = 0.43 + i * 0.12;
    }
    const positions: number[] = [];
    for (let i = 0; i < 90; i++) {
      const a = i * 2.399963; const r = 0.12 + Math.sqrt(i / 90) * 0.57;
      positions.push(Math.sin(a) * r, Math.sin(i * 1.7) * 0.12 - 0.24, Math.cos(a) * r);
    }
    const stars = new THREE.BufferGeometry(); stars.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    this.geometries.add(stars); this.core.add(new THREE.Points(stars, this.particleMaterial));
  }

  /** Each business gets a different load-bearing silhouette, not a recolored bowl. */
  private buildInstrument(panelWidth: number, panelHeight: number): void {
    const id = this.stationId, layout = terminalLayout(id);
    this.group.name = 'khalai-' + layout.kind;
    const part = (g: THREE.BufferGeometry, m: THREE.Material, x: number, y: number, z: number) => {
      const mesh = this.addMesh(this.group, g, m); mesh.position.set(x, y, z); return mesh;
    };
    const box = (w: number, h: number, d: number, x: number, y: number, z: number, m: THREE.Material = this.gold) =>
      part(new THREE.BoxGeometry(w, h, d), m, x, y, z);
    // All cases stay inside the 2.9m square reservation, including their ornament.
    const foot = part(new THREE.CylinderGeometry(0.7, 0.94, 0.18, 6), this.obsidian, 0, 0.12, -0.12);
    foot.rotation.y = Math.PI / 6;
    box(0.45, 0.7, 0.48, 0, 0.52, -0.16, this.ceramic);
    if (id === 'system') {
      const prism = part(new THREE.OctahedronGeometry(0.72), this.enamel, 0, 1.58, -0.32);
      prism.scale.set(0.7, 1.78, 0.65);
      for (const side of [-1, 1]) {
        const rail = box(0.19, 1.8, 0.3, side * 0.58, 1.46, -0.38);
        rail.rotation.z = side * -0.16;
        box(0.045, 1.4, 0.03, side * 0.57, 1.55, -0.18, this.light);
      }
      for (let i = 0; i < 5; i++) box(0.68, 0.065, 0.5, 0, 0.92 + i * 0.23, -0.15, this.edge);
    } else if (id === 'bots') {
      for (const side of [-1, 1]) {
        const wing = new THREE.Shape();
        wing.moveTo(0.16, 0.7); wing.lineTo(0.6, 1.0); wing.lineTo(1.35, 2.35);
        wing.lineTo(1.3, 1.25); wing.lineTo(0.98, 0.67); wing.closePath();
        const geometry = new THREE.ExtrudeGeometry(wing, { depth: 0.2, bevelEnabled: false });
        const mesh = part(geometry, this.gold, 0, 0, -0.35); mesh.scale.x = side;
        const antenna = box(0.06, 0.76, 0.055, side * 1.15, 1.86, -0.08, this.light);
        antenna.rotation.z = side * -0.3;
        for (let i = 0; i < 3; i++) box(0.64, 0.11, 0.22, side * 0.7, 0.86 + i * 0.24, -0.1, this.ceramic);
      }
      part(new THREE.SphereGeometry(0.24, 16, 10), this.projection, 0, 1.56, -0.17);
    } else if (id === 'plugins') {
      box(2.65, 0.16, 0.78, 0, 0.83, -0.02);
      for (let i = 0; i < 3; i++) {
        const x = (i - 1) * 0.83;
        box(0.71, 0.76, 0.58, x, 1.29, -0.3, this.obsidian);
        box(0.56, 0.65, 0.36, x, 1.29, -0.05, this.enamel);
        box(0.44, 0.055, 0.045, x, 1.57, 0.15, this.light);
        for (const side of [-1, 1]) box(0.06, 0.72, 0.5, x + side * 0.32, 1.29, -0.02, this.edge);
      }
    } else if (id === 'usage') {
      const dial = part(new THREE.TorusGeometry(1.13, 0.12, 8, 64), this.gold, 0, 1.52, -0.18);
      dial.rotation.x = -0.22;
      const inset = part(new THREE.TorusGeometry(0.96, 0.025, 6, 64), this.light, 0, 1.52, -0.12);
      inset.rotation.x = -0.22;
      for (let i = 0; i < 16; i++) {
        const a = i * Math.PI / 8;
        const tick = box(0.045, 0.16, 0.08, Math.sin(a) * 1.1, 1.52 + Math.cos(a) * 1.1, -0.08, this.edge);
        tick.rotation.z = -a;
      }
    } else if (id === 'dashboard') {
      box(1.8, 0.18, 0.9, 0, 0.86, -0.04);
      for (const side of [-1, 1]) {
        const horn = part(new THREE.ConeGeometry(0.23, 1.4, 4), this.gold, side * 0.91, 1.49, -0.3);
        horn.rotation.z = side * -0.34;
      }
      const crystal = part(new THREE.OctahedronGeometry(0.42), this.projection, 0, 1.6, -0.35);
      crystal.scale.y = 1.4;
    } else {
      // A book/projector opens above a narrow lectern; no basin, star globe or shield
      // is permitted in front of the content. The emissive canvas stays world-space.
      box(1.62, 0.13, 0.72, 0, 0.89, -0.03);
      for (const side of [-1, 1]) {
        const arm = box(0.14, 0.85, 0.23, side * 0.86, 1.03, -0.18, this.edge);
        arm.rotation.z = side * -0.44;
      }
      if (id === 'logs') {
        for (const side of [-1, 1]) {
          const cover = box(1.22, 1.48, 0.09, side * 0.64, 1.8, 0.12, this.gold);
          cover.rotation.y = side * -0.13;
          for (let i = 0; i < 4; i++) box(0.025, 1.38, 0.1, side * (1.25 + i * 0.032), 1.8, 0.22, this.edge);
        }
        box(0.14, 1.55, 0.13, 0, 1.8, 0.1, this.ceramic);
      } else {
        for (const side of [-1, 1]) {
          box(0.09, 1.42, 0.17, side * 1.32, 1.78, 0.22, this.gold);
          box(0.027, 1.3, 0.03, side * 1.26, 1.78, 0.34, this.light);
        }
      }
    }
    placeOperatingSurface(this.panel, layout);
    this.group.add(this.panel);
    if (layout.columns === 0) {
      // Border is entirely behind/outside the UV surface, never across content.
      for (const side of [-1, 1]) {
        const border = this.addMesh(this.panel, new THREE.BoxGeometry(panelWidth + 0.06, 0.025, 0.025), this.light);
        border.position.set(0, side * (panelHeight / 2 + 0.022), 0.01);
      }
      const names: ConsoleKey[] = ['scroll-up', 'refresh', 'scroll-down'];
      names.forEach((name, i) => {
        const key = this.addMesh(this.panel, new THREE.BoxGeometry(0.16, 0.075, 0.04), this.edge);
        key.position.set((i - 1) * 0.24, -panelHeight / 2 - 0.095, 0.07);
        key.name = 'console-key-' + name;
        key.userData.consoleKey = name; this.keys.push(key);
        const glyph = this.addMesh(key, i === 1
          ? new THREE.TorusGeometry(0.023, 0.004, 4, 20, Math.PI * 1.7)
          : new THREE.CircleGeometry(0.025, 3), this.light);
        glyph.name = 'utility-key-glyph'; glyph.position.z = 0.023;
        if (i !== 1) glyph.rotation.z = i === 0 ? Math.PI / 2 : -Math.PI / 2;
      });
    }
  }

  setFocused(focused: boolean): void {
    this.projection.opacity = focused ? 0.22 : 0.3;
  }

  private addMesh(group: THREE.Object3D, geometry: THREE.BufferGeometry, material: THREE.Material): THREE.Mesh {
    this.geometries.add(geometry); const mesh = new THREE.Mesh(geometry, material);
    mesh.userData.solidConsole = material instanceof THREE.MeshStandardMaterial && !material.transparent;
    group.add(mesh); return mesh;
  }
  setBusinessControls(enabled: boolean): void { this.panel.visible = !enabled; }
  setAccent(color: number): void { this.light.color.setHex(color === 0xffa63d ? color : 0x278de8); }
  update(dt: number, active: boolean): void {
    this.time += Math.min(Math.max(dt, 0), 0.1);
    this.core.position.y = 1.43 + Math.sin(this.time * 0.85) * 0.025;
    this.core.rotation.y = this.time * 0.055; this.gimbal.rotation.y = this.time * 0.08;
    this.projection.opacity = active ? 0.46 : 0.3;
  }
  pressKey(key: THREE.Object3D | null): void { for (const cap of this.keys) cap.position.z = cap === key ? 0.05 : 0.07; }
  dispose(): void {
    if (this.disposed) return; this.disposed = true;
    this.geometries.forEach(g => g.dispose());
    for (const m of [this.gold, this.edge, this.plate, this.enamel, this.obsidian, this.ceramic, this.light, this.projection, this.particleMaterial, this.gridMaterial]) m.dispose();
  }
}
