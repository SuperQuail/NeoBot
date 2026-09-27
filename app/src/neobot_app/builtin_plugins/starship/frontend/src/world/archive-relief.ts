/** Quiet, wall-bound archive masonry. World metres; mount at identity beside the
 * existing interior. Does not own the deck, furniture, doors or any interaction. */
import * as THREE from 'three';
import { Architecture, type Point } from './geometry';
import { applyAlloyFinish, type ShipMaterials } from './materials';
import type { CollisionWorld } from '../core/collision';

/** Chamfered foot and restrained curved shoulders, not a circular/solar motif. */
function tablet(width: number, height: number): THREE.Shape {
  const w = width / 2, s = new THREE.Shape();
  const chamfer = Math.min(.32, width * .2, height * .15);
  s.moveTo(-w + chamfer, 0); s.lineTo(w - chamfer, 0);
  s.lineTo(w, chamfer); s.lineTo(w, height * .72);
  s.quadraticCurveTo(w, height * .84, w * .68, height * .9);
  s.lineTo(w * .4, height); s.lineTo(-w * .4, height);
  s.lineTo(-w * .68, height * .9);
  s.quadraticCurveTo(-w, height * .84, -w, height * .72);
  s.lineTo(-w, chamfer); s.closePath(); return s;
}

/** Carved perimeter with a real opening, revealing the deeper backing surface. */
function tabletFrame(width: number, height: number, rim: number): THREE.Shape {
  const s = tablet(width, height);
  const hole = tablet(width - rim * 2, height - rim * 2).getPoints(10);
  s.holes.push(new THREE.Path(hole.reverse().map(p => new THREE.Vector2(p.x, p.y + rim))));
  return s;
}

function pilaster(bottom: number): THREE.Shape {
  const s = new THREE.Shape();
  s.moveTo(-.62, bottom); s.lineTo(.62, bottom);
  s.lineTo(.62, bottom + .36); s.lineTo(.39, bottom + .7);
  s.lineTo(.39, 7.35);
  s.bezierCurveTo(.39, 8.65, .58, 9.75, .96, 10.6);
  s.lineTo(.96, 11.88); s.lineTo(-.96, 11.88);
  s.lineTo(-.96, 10.6);
  s.bezierCurveTo(-.58, 9.75, -.39, 8.65, -.39, 7.35);
  s.lineTo(-.39, bottom + .7); s.lineTo(-.62, bottom + .36);
  s.closePath(); return s;
}

/** Broad, shallow segmental arch: flat-backed into the existing y=12 ceiling. */
function vault(): THREE.Shape {
  const s = new THREE.Shape();
  s.moveTo(-15.65, 11.98); s.lineTo(15.65, 11.98);
  s.lineTo(15.65, 8.85); s.lineTo(14.9, 9.05);
  s.bezierCurveTo(12.25, 10.85, 7.2, 11.28, 0, 11.3);
  s.bezierCurveTo(-7.2, 11.28, -12.25, 10.85, -14.9, 9.05);
  s.lineTo(-15.65, 8.85); s.closePath(); return s;
}

/** A thin carved fascia following the arch soffit, with squared end shoulders. */
function vaultFascia(): THREE.Shape {
  const s = new THREE.Shape();
  s.moveTo(-15.3, 9.17);
  s.bezierCurveTo(-12.2, 11.17, -7.1, 11.55, 0, 11.55);
  s.bezierCurveTo(7.1, 11.55, 12.2, 11.17, 15.3, 9.17);
  s.lineTo(15.3, 9.4);
  s.bezierCurveTo(12.2, 11.38, 7.1, 11.75, 0, 11.75);
  s.bezierCurveTo(-7.1, 11.75, -12.2, 11.38, -15.3, 9.4);
  s.closePath(); return s;
}

export function buildArchiveRelief(materials: ShipMaterials, collision: CollisionWorld): THREE.Group {
  const group = new THREE.Group(); group.name = 'archive-relief';
  const solid = new Architecture(group);
  const lightGroup = new THREE.Group(); lightGroup.name = 'archive-relief-couplings';
  lightGroup.userData.nonSolid = true; group.add(lightGroup);
  const luminous = new Architecture(lightGroup);

  // Muted silver ceramic + the ship's existing antique alloy; no hot gold emission.
  const silver = applyAlloyFinish(new THREE.MeshStandardMaterial({
    color: materials.wallAccent.color.clone().lerp(new THREE.Color(0x8d999d), .78),
    metalness: .43, roughness: .5, envMapIntensity: .48,
  }), { roughnessVariation: .04, colourVariation: .018, relief: 0 });
  silver.name = 'archive-relief-satin-silver';
  const teal = applyAlloyFinish(new THREE.MeshStandardMaterial({
    color: materials.wall.color.clone().lerp(new THREE.Color(0x183a43), .68),
    metalness: .32, roughness: .62, envMapIntensity: .4,
  }), { roughnessVariation: .04, colourVariation: .025, relief: 0 });
  teal.name = 'archive-relief-deep-teal';
  const blue = new THREE.MeshBasicMaterial({ color: 0x407fa6, toneMapped: true });
  blue.name = 'archive-relief-low-blue-coupling';

  // Local XY is a wall face; +Z projects inward. All layers overlap their support.
  const plate = (shape: THREE.Shape, depth: number, at: Point, material: THREE.Material,
    yaw = 0, bevel = .045, batch = solid): void => {
    const g = new THREE.ExtrudeGeometry(shape, { depth, steps: 1, curveSegments: 10,
      bevelEnabled: bevel > 0, bevelSize: bevel, bevelThickness: bevel, bevelSegments: 1 });
    g.rotateY(yaw); g.translate(...at); batch.add(g, material);
  };
  const wallPoint = (origin: Point, yaw: number, u: number, y: number, n: number): Point =>
    [origin[0] + Math.cos(yaw) * u + Math.sin(yaw) * n,
      origin[1] + y, origin[2] - Math.sin(yaw) * u + Math.cos(yaw) * n];

  // Three deep-set archive bays behind (not around) the two working terminals.
  // Nearest new back-wall surface stays beyond z=104.8; x ends before east shelves.
  for (const x of [29.5, 38, 46.5]) {
    const origin: Point = [x, .24, 105.72], yaw = Math.PI;
    plate(tablet(7.5, 11.38), .22, origin, teal, yaw);
    plate(tabletFrame(7.5, 11.38, .46), .66,
      wallPoint(origin, yaw, 0, 0, .08), silver, yaw, .07);
    plate(tabletFrame(6.4, 10.28, .12), .13,
      wallPoint(origin, yaw, 0, .55, .26), materials.hull, yaw, .025);
    // Split inner leaves sit on the backing, with a broad shadow joint between them.
    for (const u of [-1.47, 1.47]) {
      plate(tablet(2.54, 7.05), .09,
        wallPoint(origin, yaw, u, 1.12, .215), materials.wall, yaw, .035);
      // Inset relief cuts are supported, closed extrusions rather than floating strips.
      for (let row = 0; row < 4; row++) {
        const cut = new THREE.Shape();
        cut.moveTo(-.86, 0); cut.lineTo(.59, 0); cut.lineTo(.87, .18);
        cut.lineTo(.87, .25); cut.lineTo(-.62, .25); cut.closePath();
        plate(cut, .035, wallPoint(origin, yaw, u, 2.02 + row * 1.12, .308), teal, yaw, .01);
      }
    }
    // Small blue joint, nested in a bronze socket at the spring of each arch.
    plate(tablet(.64, 1.14), .24,
      wallPoint(origin, yaw, 0, 8.8, .2), materials.hull, yaw, .025);
    plate(tablet(.31, .66), .035,
      wallPoint(origin, yaw, 0, 9.02, .445), blue, yaw, .008, luminous);
  }

  // West ribs avoid the doorway AND the full sliding-leaf pockets at z=78..94.
  // The eastern z=104.4 support starts above its shelf, never through the books.
  for (const z of [77.1, 98, 104.4]) {
    for (const east of [false, true]) {
      const origin: Point = [east ? 53.72 : 22.28, 0, z];
      const yaw = east ? -Math.PI / 2 : Math.PI / 2;
      const bottom = east && z === 104.4 ? 5.94 : .1;
      plate(pilaster(bottom), .91, origin, silver, yaw, .055);
      // Narrow central carved inset is seated on the rib, not suspended armour.
      plate(tablet(.46, 10.4 - bottom), .055,
        wallPoint(origin, yaw, 0, bottom + .6, .9), teal, yaw, .025);
      plate(tablet(.61, .88), .13,
        wallPoint(origin, yaw, 0, 9.8, .94), materials.hull, yaw, .025);
      plate(tablet(.25, .43), .025,
        wallPoint(origin, yaw, 0, 10.02, 1.075), blue, yaw, .008, luminous);
    }
    // Exact arch solids, not a room-sized ceiling collision box.
    plate(vault(), .78, [38, 0, z - .39], silver, 0, .045);
    for (const face of [-1, 1]) {
      plate(vaultFascia(), .065, [38, 0, z + face * .4], materials.hull, 0, .018);
    }
  }

  // Wall-mounted carved upper panels above shelf tops (5.56m). Shallow and quiet.
  // No west-door header is added: retain its existing nameplate and 7m aperture.
  const upperPanel = (origin: Point, yaw: number, width: number): void => {
    plate(tablet(width, 4.53), .16, origin, teal, yaw, .04);
    plate(tabletFrame(width, 4.53, .29), .36,
      wallPoint(origin, yaw, 0, 0, .1), silver, yaw, .04);
    plate(tabletFrame(width - .82, 3.69, .095), .07,
      wallPoint(origin, yaw, 0, .42, .18), materials.hull, yaw, .015);
    // Symmetric chevrons carved into a backed recess; no fake writing or UI.
    for (const side of [-1, 1]) {
      const s = new THREE.Shape();
      s.moveTo(side * .5, 1.06); s.lineTo(side * (width * .3), 1.72);
      s.lineTo(side * (width * .3), 1.89); s.lineTo(side * .5, 1.23); s.closePath();
      plate(s, .04, wallPoint(origin, yaw, 0, 0, .17), silver, yaw, .01);
    }
    plate(tablet(.42, .83), .07,
      wallPoint(origin, yaw, 0, 2.47, .165), materials.hull, yaw, .02);
    plate(tablet(.18, .39), .025,
      wallPoint(origin, yaw, 0, 2.66, .237), blue, yaw, .006, luminous);
  };
  for (const x of [28, 38, 48]) upperPanel([x, 6.24, 74.28], 0, 7.3);
  for (const z of [83.2, 92]) upperPanel([53.72, 6.24, z], -Math.PI / 2, 6.9);
  // Far west wall is otherwise completely blank; this panel is beyond the door pocket.
  upperPanel([22.28, 6.24, 98], Math.PI / 2, 5.2);

  solid.finish(); luminous.finish();
  let triangles = 0, batches = 0;
  group.traverse(object => {
    if (!(object instanceof THREE.Mesh)) return;
    object.name = 'archive-relief-' + (object.material as THREE.Material).name;
    object.receiveShadow = true;
    if (object.parent === lightGroup) object.userData.nonSolid = true;
    triangles += (object.geometry.index?.count ?? object.geometry.attributes.position.count) / 3;
    batches++;
  });
  group.userData.geometryBudget = { triangles, batches };
  group.userData.clearances = { ceilingY: 12, maxSideRelief: 1.14,
    backWallMinZ: 104.8, doorPocketZ: [78, 94], terminalPositions: [[30, 100], [46, 100]] };
  collision.addStaticMesh(group, { tag: 'archive-relief', owner: 'archive' });
  return group;
}
