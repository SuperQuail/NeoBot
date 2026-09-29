import type * as THREE from 'three';
import type { CollisionWorld } from '../core/collision';
import { buildShip as buildPsionicArk, type ShipBuild } from './ship';
import { PSIONIC_INSTRUMENTS, type InstrumentTheme } from './style';
/** A builder owns hull, rooms, collisions and station anchors. Terminal target IDs
 * are the capability contract, independent of the particular vessel layout. */
export interface VesselDefinition {
  id:string; label:string; instruments:Readonly<InstrumentTheme>;
  build(scene:THREE.Scene, collision:CollisionWorld, notify?:(message:string)=>void):ShipBuild;
}
const builders=new Map<string,VesselDefinition>();
export function registerVessel(definition:VesselDefinition):void {
  if(!definition.id || builders.has(definition.id))throw new Error('Duplicate or empty vessel ID: '+definition.id);
  builders.set(definition.id,definition);
}
export function vesselDefinition(id:string):VesselDefinition {
  const found=builders.get(id);if(!found)throw new Error('Vessel is not implemented: '+id);return found;
}
export function availableVessels():ReadonlyArray<VesselDefinition> {return [...builders.values()];}
export const DEFAULT_VESSEL='psionic-ark';
/** Roadmap only: not registered and deliberately not selectable. */
export const PLANNED_VESSELS=Object.freeze([{id:'terran-battlecruiser',label:'泰伦帝国战列巡航舰',implemented:false}]);
registerVessel({id:DEFAULT_VESSEL,label:'星灵风格 · 灵能方舟',instruments:PSIONIC_INSTRUMENTS,build:buildPsionicArk});
