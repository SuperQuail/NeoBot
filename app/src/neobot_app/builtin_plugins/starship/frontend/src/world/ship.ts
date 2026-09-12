// world/ship.ts —— 由甲板网格生成飞船几何、碰撞体与终端站位。
//
// 生成规则（保证「改一个字符，几何/碰撞/提示一起更新」）：
//   * 每个可行走单元格生成地板与天花板；
//   * 相邻两个单元格属于不同舱室时，中间自动开一扇门；
//   * 相邻单元格是船体（# / .）时生成实墙；若该侧位于舰体外圈且舱室带舷窗，
//     则在墙上开一条玻璃舷窗，并在外壳上打一个「透光口」；
//   * 外圈单元格不再生成实体，只生成朝外的外壳面板（FrontSide，从舰内看不见），
//     因此从舷窗往外看就是太空。

import * as THREE from 'three';
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';
import { CollisionWorld } from '../core/collision';
import type { LadderVolume } from '../core/player';
import {
  CELL,
  COLS,
  DECK_Y,
  DECKS,
  DeckPlan,
  LADDERS,
  ROOM_HEIGHT,
  ROOM_LEGEND,
  ROOMS,
  ROWS,
  STATIONS,
  StationSpec,
  cellAt,
  cellCenter,
  cellX,
  cellZ,
  isWalkable,
} from './deckplan';
import { ShipMaterials, createShipMaterials, createSignTexture } from './materials';

export interface RoomBounds {
  id: string;
  label: string;
  description: string;
  deck: number;
  min: THREE.Vector3;
  max: THREE.Vector3;
}

export interface StationAnchor {
  spec: StationSpec;
  position: THREE.Vector3;
  yaw: number;
  roomLabel: string;
  deck: number;
}

export interface ShipBuild {
  group: THREE.Group;
  materials: ShipMaterials;
  rooms: RoomBounds[];
  anchors: Map<string, StationAnchor>;
  ladders: LadderVolume[];
  spawn: THREE.Vector3;
  spawnYaw: number;
  /** 舰体外壳的包围盒（小游戏里用于判断舰体受伤方向） */
  hullBounds: THREE.Box3;
  dispose(): void;
}

const DOOR_WIDTH = 2.5;
const DOOR_HEIGHT = 2.6;
const WINDOW_BOTTOM = 1.0;
const WINDOW_TOP = 2.55;

function transformedBox(
  width: number,
  height: number,
  depth: number,
  x: number,
  y: number,
  z: number,
): THREE.BufferGeometry {
  const geometry = new THREE.BoxGeometry(width, height, depth);
  geometry.translate(x, y, z);
  return geometry;
}

function isRingCell(col: number, row: number): boolean {
  return col === 0 || col === COLS - 1 || row === 0 || row === ROWS - 1;
}

/** 同时写入渲染几何与碰撞世界（保证两者永不失配） */
function addSolid(
  geometries: THREE.BufferGeometry[],
  collision: CollisionWorld,
  width: number,
  height: number,
  depth: number,
  x: number,
  y: number,
  z: number,
  tag = 'wall',
): void {
  geometries.push(transformedBox(width, height, depth, x, y, z));
  collision.add(
    new THREE.Vector3(x - width / 2, y - height / 2, z - depth / 2),
    new THREE.Vector3(x + width / 2, y + height / 2, z + depth / 2),
    tag,
  );
}

export function buildShip(
  scene: THREE.Scene,
  collision: CollisionWorld,
  onProgress?: (message: string) => void,
): ShipBuild {
  const group = new THREE.Group();
  group.name = 'starship';
  const materials = createShipMaterials();
  const rooms: RoomBounds[] = [];
  const anchors = new Map<string, StationAnchor>();
  const ladders: LadderVolume[] = [];

  const floorGeometries: THREE.BufferGeometry[] = [];
  const wallGeometries: THREE.BufferGeometry[] = [];
  const wallAccentGeometries: THREE.BufferGeometry[] = [];
  const ceilingGeometries: THREE.BufferGeometry[] = [];
  const trimGeometries: THREE.BufferGeometry[] = [];
  const glassGeometries: THREE.BufferGeometry[] = [];
  const hullGeometries: THREE.BufferGeometry[] = [];
  const windowGlowGeometries: THREE.BufferGeometry[] = [];

  // 爬梯洞（该单元格不生成地板/天花板）
  const holes = new Set<string>();
  for (const ladder of LADDERS) {
    holes.add(ladder.fromDeck + ':' + ladder.col + ':' + ladder.row);
    holes.add(ladder.toDeck + ':' + ladder.col + ':' + ladder.row);
  }

  const roomCells = new Map<string, { deck: number; cells: Array<[number, number]>; minCol: number; maxCol: number; minRow: number; maxRow: number }>();

  onProgress?.('正在铺设甲板结构…');

  DECKS.forEach((deck, deckIndex) => {
    const y = deck.y;
    for (let row = 0; row < ROWS; row += 1) {
      for (let col = 0; col < COLS; col += 1) {
        const ch = cellAt(deck, col, row);
        const walkable = isWalkable(ch);
        const [cx, cz] = cellCenter(col, row);
        const key = deckIndex + ':' + col + ':' + row;
        if (walkable) {
          // 网格里是舱室字符（B/E/H…），先用图例映射成舱室 id 再取元数据
          const roomId = ROOM_LEGEND[ch] ?? 'corridor';
          const info = ROOMS[roomId];
          let entry = roomCells.get(deckIndex + ':' + roomId);
          if (!entry) {
            entry = { deck: deckIndex, cells: [], minCol: col, maxCol: col, minRow: row, maxRow: row };
            roomCells.set(deckIndex + ':' + roomId, entry);
          }
          entry.cells.push([col, row]);
          entry.minCol = Math.min(entry.minCol, col);
          entry.maxCol = Math.max(entry.maxCol, col);
          entry.minRow = Math.min(entry.minRow, row);
          entry.maxRow = Math.max(entry.maxRow, row);

          if (!holes.has(deckIndex + ':' + col + ':' + row)) {
            floorGeometries.push(transformedBox(CELL, 0.2, CELL, cx, y - 0.1, cz));
            ceilingGeometries.push(
              transformedBox(CELL, 0.2, CELL, cx, y + ROOM_HEIGHT + 0.1, cz),
            );
            collision.add(
              new THREE.Vector3(cx - CELL / 2, y - 0.2, cz - CELL / 2),
              new THREE.Vector3(cx + CELL / 2, y, cz + CELL / 2),
              'floor',
            );
            collision.add(
              new THREE.Vector3(cx - CELL / 2, y + ROOM_HEIGHT, cz - CELL / 2),
              new THREE.Vector3(cx + CELL / 2, y + ROOM_HEIGHT + 0.2, cz + CELL / 2),
              'ceiling',
            );
          }

          // 顶灯条：沿走廊与舱室中心线布置
          if ((col + row) % 2 === 0) {
            trimGeometries.push(
              transformedBox(CELL * 0.5, 0.06, 0.28, cx, y + ROOM_HEIGHT - 0.08, cz),
            );
          }

          const sides: Array<{ dc: number; dr: number; axis: 'x' | 'z'; sign: number }> = [
            { dc: -1, dr: 0, axis: 'x', sign: -1 },
            { dc: 1, dr: 0, axis: 'x', sign: 1 },
            { dc: 0, dr: -1, axis: 'z', sign: -1 },
            { dc: 0, dr: 1, axis: 'z', sign: 1 },
          ];
          for (const side of sides) {
            const nCol = col + side.dc;
            const nRow = row + side.dr;
            const neighbour = cellAt(deck, nCol, nRow);
            const neighbourWalkable = isWalkable(neighbour);
            const neighbourRoom = neighbourWalkable ? ROOM_LEGEND[neighbour] ?? '' : '';
            if (neighbourWalkable && neighbourRoom === roomId) continue; // 同舱室：无墙

            const along = side.axis === 'x' ? CELL : CELL;
            const wallThickness = 0.18;
            const half = CELL / 2;
            const wx = side.axis === 'x' ? cx + side.sign * half : cx;
            const wz = side.axis === 'z' ? cz + side.sign * half : cz;
            const sizeX = side.axis === 'x' ? wallThickness : along;
            const sizeZ = side.axis === 'z' ? wallThickness : along;
            const door = neighbourWalkable;
            const windowed =
              !neighbourWalkable &&
              info?.windows === true &&
              isRingCell(nCol, nRow);

            if (door) {
              // 门洞：两侧门垛 + 上方门楣
              const jamb = (CELL - DOOR_WIDTH) / 2;
              const lintelHeight = ROOM_HEIGHT - DOOR_HEIGHT;
              const offset = (DOOR_WIDTH + jamb) / 2;
              if (side.axis === 'x') {
                addSolid(wallGeometries, collision, sizeX, ROOM_HEIGHT, jamb, wx, y + ROOM_HEIGHT / 2, cz - offset);
                addSolid(wallGeometries, collision, sizeX, ROOM_HEIGHT, jamb, wx, y + ROOM_HEIGHT / 2, cz + offset);
                addSolid(wallGeometries, collision, sizeX, lintelHeight, CELL, wx, y + DOOR_HEIGHT + lintelHeight / 2, cz);
              } else {
                addSolid(wallGeometries, collision, jamb, ROOM_HEIGHT, sizeZ, cx - offset, y + ROOM_HEIGHT / 2, wz);
                addSolid(wallGeometries, collision, jamb, ROOM_HEIGHT, sizeZ, cx + offset, y + ROOM_HEIGHT / 2, wz);
                addSolid(wallGeometries, collision, CELL, lintelHeight, sizeZ, cx, y + DOOR_HEIGHT + lintelHeight / 2, wz);
              }
              // 门框发光边
              if (side.axis === 'x') {
                trimGeometries.push(transformedBox(wallThickness * 1.6, DOOR_HEIGHT, 0.08, wx, y + DOOR_HEIGHT / 2, cz - DOOR_WIDTH / 2));
                trimGeometries.push(transformedBox(wallThickness * 1.6, DOOR_HEIGHT, 0.08, wx, y + DOOR_HEIGHT / 2, cz + DOOR_WIDTH / 2));
                trimGeometries.push(transformedBox(wallThickness * 1.6, 0.08, DOOR_WIDTH, wx, y + DOOR_HEIGHT, cz));
              } else {
                trimGeometries.push(transformedBox(0.08, DOOR_HEIGHT, wallThickness * 1.6, cx - DOOR_WIDTH / 2, y + DOOR_HEIGHT / 2, wz));
                trimGeometries.push(transformedBox(0.08, DOOR_HEIGHT, wallThickness * 1.6, cx + DOOR_WIDTH / 2, y + DOOR_HEIGHT / 2, wz));
                trimGeometries.push(transformedBox(DOOR_WIDTH, 0.08, wallThickness * 1.6, cx, y + DOOR_HEIGHT, wz));
              }
              continue;
            }

            if (windowed) {
              // 舷窗：下墙 + 玻璃 + 上墙 + 窗框
              const lower = WINDOW_BOTTOM;
              const upper = ROOM_HEIGHT - WINDOW_TOP;
              if (side.axis === 'x') {
                wallGeometries.push(transformedBox(sizeX, lower, CELL, wx, y + lower / 2, cz));
                wallGeometries.push(transformedBox(sizeX, upper, CELL, wx, y + WINDOW_TOP + upper / 2, cz));
                glassGeometries.push(transformedBox(0.06, WINDOW_TOP - WINDOW_BOTTOM, CELL * 0.98, wx, y + (WINDOW_BOTTOM + WINDOW_TOP) / 2, cz));
              } else {
                wallGeometries.push(transformedBox(CELL, lower, sizeZ, cx, y + lower / 2, wz));
                wallGeometries.push(transformedBox(CELL, upper, sizeZ, cx, y + WINDOW_TOP + upper / 2, wz));
                glassGeometries.push(transformedBox(CELL * 0.98, WINDOW_TOP - WINDOW_BOTTOM, 0.06, cx, y + (WINDOW_BOTTOM + WINDOW_TOP) / 2, wz));
              }
              const windowHeight = WINDOW_TOP - WINDOW_BOTTOM;
              if (side.axis === 'x') {
                trimGeometries.push(transformedBox(0.12, 0.08, CELL, wx, y + WINDOW_BOTTOM, cz));
                trimGeometries.push(transformedBox(0.12, 0.08, CELL, wx, y + WINDOW_TOP, cz));
              } else {
                trimGeometries.push(transformedBox(CELL, 0.08, 0.12, cx, y + WINDOW_BOTTOM, wz));
                trimGeometries.push(transformedBox(CELL, 0.08, 0.12, cx, y + WINDOW_TOP, wz));
              }
              collision.add(
                side.axis === 'x'
                  ? new THREE.Vector3(wx - 0.12, y, cz - CELL / 2)
                  : new THREE.Vector3(cx - CELL / 2, y, wz - 0.12),
                side.axis === 'x'
                  ? new THREE.Vector3(wx + 0.12, y + lower, cz + CELL / 2)
                  : new THREE.Vector3(cx + CELL / 2, y + lower, wz + 0.12),
                'wall',
              );
              collision.add(
                side.axis === 'x'
                  ? new THREE.Vector3(wx - 0.12, y + WINDOW_TOP, cz - CELL / 2)
                  : new THREE.Vector3(cx - CELL / 2, y + WINDOW_TOP, wz - 0.12),
                side.axis === 'x'
                  ? new THREE.Vector3(wx + 0.12, y + ROOM_HEIGHT, cz + CELL / 2)
                  : new THREE.Vector3(cx + CELL / 2, y + ROOM_HEIGHT, wz + 0.12),
                'wall',
              );
              collision.add(
                side.axis === 'x'
                  ? new THREE.Vector3(wx - 0.12, y + lower, cz - CELL / 2)
                  : new THREE.Vector3(cx - CELL / 2, y + lower, wz - 0.12),
                side.axis === 'x'
                  ? new THREE.Vector3(wx + 0.12, y + WINDOW_TOP, cz + CELL / 2)
                  : new THREE.Vector3(cx + CELL / 2, y + WINDOW_TOP, wz + 0.12),
                'glass',
              );
              void windowHeight;
              continue;
            }

            // 普通实墙
            wallGeometries.push(
              transformedBox(sizeX, ROOM_HEIGHT, sizeZ, wx, y + ROOM_HEIGHT / 2, wz),
            );
            collision.add(
              new THREE.Vector3(wx - sizeX / 2, y, wz - sizeZ / 2),
              new THREE.Vector3(wx + sizeX / 2, y + ROOM_HEIGHT, wz + sizeZ / 2),
              'wall',
            );
            if (info && info.windows && isRingCell(nCol, nRow)) {
              wallAccentGeometries.push(
                transformedBox(
                  side.axis === 'x' ? 0.22 : CELL * 0.6,
                  0.16,
                  side.axis === 'z' ? 0.22 : CELL * 0.6,
                  wx,
                  y + ROOM_HEIGHT - 0.4,
                  wz,
                ),
              );
            }
          }
        } else if (isRingCell(col, row)) {
          // 外壳：只生成朝外的面板（FrontSide → 从舰内看过去是透明的）
          const thickness = 0.6;
          if (col === 0) hullGeometries.push(transformedBox(thickness, 16, CELL, cellX(0) - thickness / 2 + 0.2, y + ROOM_HEIGHT / 2, cz));
          if (col === COLS - 1) hullGeometries.push(transformedBox(thickness, 16, CELL, cellX(COLS - 1) + CELL + thickness / 2 - 0.2, y + ROOM_HEIGHT / 2, cz));
          if (row === 0) hullGeometries.push(transformedBox(CELL, 16, thickness, cx, y + ROOM_HEIGHT / 2, cellZ(0) - thickness / 2 + 0.2));
          if (row === ROWS - 1) hullGeometries.push(transformedBox(CELL, 16, thickness, cx, y + ROOM_HEIGHT / 2, cellZ(ROWS - 1) + CELL + thickness / 2 - 0.2));
          if (deckIndex === 0) hullGeometries.push(transformedBox(CELL, 0.6, CELL, cx, y - 0.6, cz));
          if (deckIndex === DECKS.length - 1) hullGeometries.push(transformedBox(CELL, 0.6, CELL, cx, y + ROOM_HEIGHT + 0.9, cz));
        }
      }
    }
  });

  // 舰体外壳（艏/艉/舷侧发光窗带）
  const hullMinX = cellX(0) - 1;
  const hullMaxX = cellX(COLS - 1) + CELL + 1;
  const hullMinZ = cellZ(0) - 1;
  const hullMaxZ = cellZ(ROWS - 1) + CELL + 1;
  const hullMinY = -3;
  const hullMaxY = DECKS[DECKS.length - 1].y + ROOM_HEIGHT + 2.2;
  hullGeometries.push(
    transformedBox(10, hullMaxY - hullMinY, hullMaxZ - hullMinZ, hullMaxX - 5, (hullMinY + hullMaxY) / 2, (hullMinZ + hullMaxZ) / 2),
  );
  hullGeometries.push(
    transformedBox(12, (hullMaxY - hullMinY) * 0.36, hullMaxZ - hullMinZ, hullMinX - 6, (hullMinY + hullMaxY) / 2, (hullMinZ + hullMaxZ) / 2),
  );
  for (const side of [-1, 1]) {
    const z = side > 0 ? hullMaxZ + 0.6 : hullMinZ - 0.6;
    for (let i = 0; i < 9; i += 1) {
      const x = hullMinX + 8 + i * ((hullMaxX - hullMinX - 16) / 9);
      windowGlowGeometries.push(transformedBox(3.4, 0.5, 0.3, x, DECK_Y[1] + ROOM_HEIGHT - 1.2, z));
      windowGlowGeometries.push(transformedBox(3.4, 0.5, 0.3, x, DECK_Y[2] + ROOM_HEIGHT - 1.2, z));
    }
  }
  // 引擎喷口
  for (const offset of [-9, 0, 9]) {
    const nozzle = new THREE.CylinderGeometry(2.6, 3.4, 4, 18, 1, true);
    nozzle.rotateZ(Math.PI / 2);
    nozzle.translate(hullMinX - 11, 3.6, offset);
    trimGeometries.push(nozzle);
  }
  // 舰艏
  hullGeometries.push(transformedBox(14, 6, 16, hullMaxX + 5, hullMaxY - 7, 0));

  onProgress?.('正在装配舱室设备…');

  const pushMesh = (
    geometries: THREE.BufferGeometry[],
    material: THREE.Material,
    name: string,
  ): void => {
    if (geometries.length === 0) return;
    const merged = mergeGeometries(geometries, false);
    for (const geometry of geometries) geometry.dispose();
    if (!merged) return;
    const mesh = new THREE.Mesh(merged, material);
    mesh.name = name;
    mesh.matrixAutoUpdate = false;
    mesh.frustumCulled = false;
    group.add(mesh);
  };

  pushMesh(floorGeometries, materials.floor, 'floors');
  pushMesh(wallGeometries, materials.wall, 'walls');
  pushMesh(wallAccentGeometries, materials.wallAccent, 'wall-accent');
  pushMesh(ceilingGeometries, materials.ceiling, 'ceilings');
  pushMesh(trimGeometries, materials.trim, 'trim');
  pushMesh(glassGeometries, materials.glass, 'glass');
  pushMesh(hullGeometries, materials.hull, 'hull');
  pushMesh(windowGlowGeometries, materials.emissive, 'hull-windows');

  // 爬梯
  for (const ladder of LADDERS) {
    const [cx, cz] = cellCenter(ladder.col, ladder.row);
    const yFrom = DECKS[ladder.fromDeck].y;
    const yTo = DECKS[ladder.toDeck].y;
    const height = yTo - yFrom;
    const ladderGroup = new THREE.Group();
    const railGeometry = new THREE.BoxGeometry(0.12, height, 0.12);
    for (const offset of [-0.35, 0.35]) {
      const rail = new THREE.Mesh(railGeometry, materials.prop);
      rail.position.set(cx - 1.6, yFrom + height / 2, cz + offset);
      ladderGroup.add(rail);
    }
    for (let step = 0; step < Math.floor(height / 0.36); step += 1) {
      const rung = new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.06, 0.8), materials.prop);
      rung.position.set(cx - 1.6, yFrom + 0.3 + step * 0.36, cz);
      ladderGroup.add(rung);
    }
    // 井口护栏
    const ring = new THREE.Mesh(
      new THREE.TorusGeometry(1.1, 0.06, 6, 24),
      materials.trim,
    );
    ring.rotation.x = Math.PI / 2;
    ring.position.set(cx, yTo + 0.05, cz);
    ladderGroup.add(ring);
    group.add(ladderGroup);
    ladders.push({
      min: new THREE.Vector3(cx - 1.6, yFrom, cz - 1.2),
      max: new THREE.Vector3(cx + 0.2, yTo + 0.6, cz + 1.2),
    });
  }

  // 舱室包围盒与名牌
  for (const [key, entry] of roomCells) {
    const roomId = key.split(':')[1];
    const info = ROOMS[roomId];
    const minX = cellX(entry.minCol);
    const maxX = cellX(entry.maxCol) + CELL;
    const minZ = cellZ(entry.minRow);
    const maxZ = cellZ(entry.maxRow) + CELL;
    const y = DECKS[entry.deck].y;
    rooms.push({
      id: roomId,
      label: info?.label || roomId,
      description: info?.description || '',
      deck: entry.deck,
      min: new THREE.Vector3(minX, y, minZ),
      max: new THREE.Vector3(maxX, y + ROOM_HEIGHT, maxZ),
    });
    if (roomId !== 'corridor' && info) {
      const sign = new THREE.Mesh(
        new THREE.PlaneGeometry(3.2, 1.0),
        new THREE.MeshBasicMaterial({
          map: createSignTexture(info.label, entry.deck === 0 ? '下层甲板' : entry.deck === 1 ? '主甲板' : '上层甲板'),
          transparent: true,
          side: THREE.DoubleSide,
        }),
      );
      const signX = (minX + maxX) / 2;
      const signZ = minZ + 0.25;
      sign.position.set(signX, y + ROOM_HEIGHT - 0.75, signZ);
      sign.rotation.y = Math.PI;
      group.add(sign);
    }
  }

  // 终端站位
  for (const spec of STATIONS) {
    const room = rooms.find((item) => item.id === spec.room);
    if (!room) continue;
    const centerX = (room.min.x + room.max.x) / 2;
    const centerZ = (room.min.z + room.max.z) / 2;
    // 夹在舱室内部（留 1.2m 边距）：站位数据写偏一点也不会卡进墙里
    const clamp = (value: number, min: number, max: number): number =>
      Math.min(Math.max(value, min), max);
    const position = new THREE.Vector3(
      clamp(centerX + spec.offset[0], room.min.x + 1.4, room.max.x - 1.4),
      room.min.y,
      clamp(centerZ + spec.offset[1], room.min.z + 1.4, room.max.z - 1.4),
    );
    anchors.set(spec.id, {
      spec,
      position,
      yaw: spec.yaw,
      roomLabel: room.label,
      deck: room.deck,
    });
  }

  const spawnRoom = rooms.find((item) => item.id === 'bridge') || rooms[0];
  const spawn = new THREE.Vector3(
    (spawnRoom.min.x + spawnRoom.max.x) / 2 + 4,
    spawnRoom.min.y + 0.1,
    (spawnRoom.min.z + spawnRoom.max.z) / 2,
  );

  // 灯光：环境光 + 几处重点光源（不启用阴影，保持低开销）
  const ambient = new THREE.AmbientLight(0x7d99b8, 1.15);
  const hemisphere = new THREE.HemisphereLight(0xbfe4ff, 0x2b323c, 0.85);
  group.add(ambient, hemisphere);
  const lightPositions: Array<[number, number, number, number, number]> = [
    [spawn.x, spawnRoom.min.y + 2.4, spawn.z, 0xcfeeff, 1.5],
    [-30, DECKS[0].y + 2.4, 0, 0x9fdcff, 1.3],
    [30, DECKS[0].y + 2.4, 0, 0x9fdcff, 1.3],
    [-34, DECKS[1].y + 2.4, 0, 0xcfeeff, 1.3],
    [10, DECKS[1].y + 2.4, 0, 0x9fdcff, 1.3],
    [-40, DECKS[2].y + 2.4, 16, 0xafc8ff, 1.2],
    [10, DECKS[2].y + 2.4, 12, 0xafc8ff, 1.2],
  ];
  for (const [x, y, z, color, intensity] of lightPositions) {
    const light = new THREE.PointLight(color, intensity, 46, 1.4);
    light.position.set(x, y, z);
    group.add(light);
  }

  scene.add(group);
  const hullBounds = new THREE.Box3(
    new THREE.Vector3(hullMinX - 12, hullMinY, hullMinZ - 1),
    new THREE.Vector3(hullMaxX + 12, hullMaxY, hullMaxZ + 1),
  );

  return {
    group,
    materials,
    rooms,
    anchors,
    ladders,
    spawn,
    spawnYaw: Math.PI / 2,
    hullBounds,
    dispose(): void {
      scene.remove(group);
      group.traverse((object) => {
        const mesh = object as THREE.Mesh;
        if (mesh.geometry) mesh.geometry.dispose();
      });
    },
  };
}

export function roomAt(rooms: RoomBounds[], position: THREE.Vector3): RoomBounds | null {
  for (const room of rooms) {
    if (
      position.x >= room.min.x - 0.4 &&
      position.x <= room.max.x + 0.4 &&
      position.z >= room.min.z - 0.4 &&
      position.z <= room.max.z + 0.4 &&
      Math.abs(position.y - room.min.y) < 3
    ) {
      return room;
    }
  }
  return null;
}

export type { DeckPlan };
