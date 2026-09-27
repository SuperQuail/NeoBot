// Foundry scenery is deliberately independent of the interactive console layer.
import * as THREE from 'three';
import type { CollisionWorld } from '../core/collision';
import type { ShipMaterials } from './materials';
import type { RoomBounds } from './ship';
import { buildFoundry } from './foundry';

export function decorateShip(
  scene: THREE.Scene,
  collision: CollisionWorld,
  materials: ShipMaterials,
  rooms: RoomBounds[],
): THREE.Group {
  const group = buildFoundry(collision, materials, rooms);
  group.name = 'ship-props';
  scene.add(group);
  return group;
}
