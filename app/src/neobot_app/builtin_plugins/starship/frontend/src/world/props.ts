// world/props.ts —— 舱室家具与装饰：让巨大的船体有尺度感与生活气息。
// 全部程序化生成，确定性摆放（同一舱室每次进游戏布局一致）。

import * as THREE from 'three';
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';
import type { CollisionWorld } from '../core/collision';
import type { RoomBounds } from './ship';
import { ROOM_HEIGHT } from './deckplan';
import { ShipMaterials } from './materials';

interface PropPlacement {
  position: THREE.Vector3;
  rotationY: number;
  size: THREE.Vector3;
}

/** 简单确定性随机（同一房间布局稳定，便于玩家形成空间记忆） */
function makeRandom(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state * 1664525 + 1013904223) >>> 0;
    return state / 4294967296;
  };
}

function box(
  size: [number, number, number],
  position: [number, number, number],
  rotationY = 0,
): THREE.BufferGeometry {
  const geometry = new THREE.BoxGeometry(size[0], size[1], size[2]);
  if (rotationY) geometry.rotateY(rotationY);
  geometry.translate(position[0], position[1], position[2]);
  return geometry;
}

export function decorateShip(
  scene: THREE.Scene,
  collision: CollisionWorld,
  materials: ShipMaterials,
  rooms: RoomBounds[],
): THREE.Group {
  const group = new THREE.Group();
  group.name = 'ship-props';
  const panelGeometries: THREE.BufferGeometry[] = [];
  const metalGeometries: THREE.BufferGeometry[] = [];
  const glowGeometries: THREE.BufferGeometry[] = [];

  const solid = (
    geometries: THREE.BufferGeometry[],
    size: [number, number, number],
    position: [number, number, number],
    rotationY = 0,
    collide = true,
  ): void => {
    geometries.push(box(size, position, rotationY));
    if (collide) {
      const half = new THREE.Vector3(size[0] / 2, size[1] / 2, size[2] / 2);
      if (rotationY) {
        // 旋转件用略大的包围盒近似，避免玩家穿模
        const radius = Math.max(half.x, half.z);
        half.set(radius, half.y, radius);
      }
      const center = new THREE.Vector3(position[0], position[1], position[2]);
      collision.add(center.clone().sub(half), center.clone().add(half), 'prop');
    }
  };

  let seed = 7;
  for (const room of rooms) {
    const random = makeRandom((seed += 977));
    const width = room.max.x - room.min.x;
    const depth = room.max.z - room.min.z;
    const y = room.min.y;
    const centerX = (room.min.x + room.max.x) / 2;
    const centerZ = (room.min.z + room.max.z) / 2;

    // 天花板横梁：所有舱室都有，提供尺度参照
    const beams = Math.max(2, Math.floor(width / 8));
    for (let index = 0; index < beams; index += 1) {
      const x = room.min.x + ((index + 0.5) / beams) * width;
      solid(panelGeometries, [0.5, 0.35, depth * 0.92], [x, y + ROOM_HEIGHT - 0.22, centerZ], 0, false);
    }
    // 墙裙发光条
    glowGeometries.push(box([width * 0.94, 0.08, 0.06], [centerX, y + 0.12, room.min.z + 0.22]));
    glowGeometries.push(box([width * 0.94, 0.08, 0.06], [centerX, y + 0.12, room.max.z - 0.22]));

    if (room.id === 'corridor') {
      const count = Math.floor(width / 10);
      for (let index = 0; index < count; index += 1) {
        const x = room.min.x + ((index + 0.5) / count) * width;
        for (const side of [-1, 1]) {
          solid(panelGeometries, [0.4, ROOM_HEIGHT, 0.4], [x, y + ROOM_HEIGHT / 2, centerZ + side * (depth / 2 - 0.5)]);
          glowGeometries.push(box([0.16, 1.4, 0.16], [x, y + 1.9, centerZ + side * (depth / 2 - 0.5)]));
        }
      }
      continue;
    }

    if (room.id === 'bridge') {
      // 指挥席环绕 + 舷侧操作台
      for (let index = 0; index < 5; index += 1) {
        const angle = -0.9 + index * 0.45;
        const x = centerX + 12 + Math.cos(angle) * 5;
        const z = centerZ + Math.sin(angle) * 5;
        solid(metalGeometries, [0.9, 0.5, 0.9], [x, y + 0.25, z]);
        solid(metalGeometries, [0.9, 1.1, 0.2], [x, y + 0.85, z + Math.sin(angle) * 0.4]);
      }
      solid(metalGeometries, [1.4, 0.6, 1.4], [centerX + 13, y + 0.3, centerZ]);
      solid(metalGeometries, [1.4, 1.2, 0.3], [centerX + 13.7, y + 1.0, centerZ]);
      glowGeometries.push(box([1.2, 0.08, 1.2], [centerX + 13, y + 0.62, centerZ]));
    } else if (room.id === 'engineering') {
      // 反应堆柱与管线
      for (let index = 0; index < 4; index += 1) {
        const x = room.min.x + 4 + index * (width / 4.4);
        solid(metalGeometries, [1.6, ROOM_HEIGHT, 1.6], [x, y + ROOM_HEIGHT / 2, centerZ - depth * 0.28]);
        glowGeometries.push(box([1.7, 0.2, 1.7], [x, y + 1.2, centerZ - depth * 0.28]));
        glowGeometries.push(box([1.7, 0.2, 1.7], [x, y + 2.4, centerZ - depth * 0.28]));
      }
      for (let index = 0; index < 6; index += 1) {
        const x = room.min.x + 2 + index * (width / 6.5);
        solid(metalGeometries, [0.6, 0.6, depth * 0.9], [x, y + ROOM_HEIGHT - 0.9, centerZ], 0, false);
      }
    } else if (room.id === 'hangar') {
      for (let index = 0; index < 8; index += 1) {
        const x = room.min.x + 3 + random() * (width - 6);
        const z = room.min.z + 3 + random() * (depth - 6);
        const size = 1.2 + random() * 1.4;
        solid(metalGeometries, [size, size, size], [x, y + size / 2, z], random() * 0.6);
      }
      solid(metalGeometries, [6, 0.4, 3], [centerX, y + 3.2, centerZ - depth * 0.3], 0, false);
      glowGeometries.push(box([5.6, 0.1, 2.6], [centerX, y + 3.42, centerZ - depth * 0.3]));
    } else if (room.id === 'cargo') {
      for (let index = 0; index < 14; index += 1) {
        const x = room.min.x + 2 + random() * (width - 4);
        const z = room.min.z + 2 + random() * (depth - 4);
        const size = 1 + random() * 1.3;
        const stack = 1 + Math.floor(random() * 2);
        for (let level = 0; level < stack; level += 1) {
          solid(metalGeometries, [size, size * 0.8, size], [x, y + size * 0.4 + level * size * 0.85, z], random() * 0.9);
        }
      }
    } else if (room.id === 'lounge') {
      for (let index = 0; index < 4; index += 1) {
        const x = room.min.x + 4 + index * (width / 4.6);
        solid(metalGeometries, [1.8, 0.45, 1.8], [x, y + 0.22, centerZ + depth * 0.18]);
        solid(metalGeometries, [1.8, 0.9, 0.3], [x, y + 0.65, centerZ + depth * 0.18 + 0.75]);
        solid(metalGeometries, [0.5, 0.6, 0.9], [x - 0.9, y + 0.7, centerZ + depth * 0.1]);
      }
      // 观景植物
      for (let index = 0; index < 3; index += 1) {
        const x = room.min.x + 3 + index * (width / 3.4);
        solid(metalGeometries, [0.7, 0.7, 0.7], [x, y + 0.35, centerZ - depth * 0.3]);
        glowGeometries.push(box([0.5, 0.6, 0.5], [x, y + 1.0, centerZ - depth * 0.3]));
      }
    } else if (room.id === 'medbay') {
      for (let index = 0; index < 3; index += 1) {
        const z = room.min.z + 4 + index * (depth / 3.4);
        solid(metalGeometries, [2.4, 0.6, 1.1], [centerX - 2, y + 0.3, z]);
        solid(metalGeometries, [0.4, 0.9, 1.1], [centerX - 3.3, y + 0.45, z]);
      }
      glowGeometries.push(box([width * 0.5, 0.16, 0.16], [centerX, y + ROOM_HEIGHT - 0.6, centerZ]));
    } else if (room.id === 'science') {
      for (let index = 0; index < 5; index += 1) {
        const x = room.min.x + 3 + index * (width / 5.5);
        solid(metalGeometries, [1.6, 0.9, 1.2], [x, y + 0.45, centerZ + depth * 0.22]);
        glowGeometries.push(box([1.4, 0.06, 1.0], [x, y + 0.94, centerZ + depth * 0.22]));
      }
      for (let index = 0; index < 3; index += 1) {
        const z = room.min.z + 3 + index * (depth / 3.2);
        solid(metalGeometries, [0.8, 2.4, 0.8], [centerX - 8, y + 1.2, z]);
        glowGeometries.push(box([0.9, 0.12, 0.9], [centerX - 8, y + 2.0, z]));
      }
    } else if (room.id === 'archive') {
      for (let index = 0; index < 8; index += 1) {
        const sign = index % 2 === 0 ? -1 : 1;
        const x = room.min.x + 3 + Math.floor(index / 2) * 6;
        const z = centerZ + sign * (depth * 0.3);
        solid(metalGeometries, [3.6, 2.6, 0.7], [x, y + 1.3, z]);
        glowGeometries.push(box([3.2, 0.06, 0.08], [x, y + 1.6, z + sign * 0.4]));
      }
    } else if (room.id === 'command') {
      solid(metalGeometries, [6, 0.35, 2.4], [centerX, y + 1.05, centerZ]);
      for (let index = 0; index < 5; index += 1) {
        const x = centerX - 2.4 + index * 1.2;
        solid(metalGeometries, [0.9, 0.5, 0.9], [x, y + 0.25, centerZ + 1.8]);
        solid(metalGeometries, [0.9, 1.0, 0.2], [x, y + 0.8, centerZ + 2.2]);
      }
      glowGeometries.push(box([5.6, 0.06, 2.0], [centerX, y + 1.24, centerZ]));
    } else if (room.id === 'observation') {
      // 观景廊：长椅 + 望远镜支架基座
      for (let index = 0; index < 6; index += 1) {
        const x = room.min.x + 5 + index * (width / 6.4);
        solid(metalGeometries, [3, 0.45, 1], [x, y + 0.22, centerZ - depth * 0.3]);
        solid(metalGeometries, [3, 0.8, 0.25], [x, y + 0.6, centerZ - depth * 0.3 - 0.4]);
      }
      for (let index = 0; index < 4; index += 1) {
        const x = room.min.x + 8 + index * (width / 4.4);
        glowGeometries.push(box([0.5, 3.2, 0.5], [x, y + 1.6, centerZ + depth * 0.34]));
      }
    }
  }

  const push = (geometries: THREE.BufferGeometry[], material: THREE.Material, name: string): void => {
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

  push(panelGeometries, materials.ceiling, 'prop-panels');
  push(metalGeometries, materials.prop, 'prop-metal');
  push(glowGeometries, materials.trim, 'prop-glow');
  scene.add(group);
  return group;
}
