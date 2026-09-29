// Compatibility name: the surface is now inset into a solid 3D instrument.
import * as THREE from 'three';
import type { ShipMaterials } from '../world/materials';
import { ConsoleModel } from './console-model';
import { terminalLayout } from './terminal-layout';

export interface HoloScreenOptions {
  accent: number;
  stationId?: string;
  /** Legacy sizing hints; the inset is deliberately capped below console width. */
  radius?: number;
  screenHeight?: number;
  thetaLength?: number;
  canvasWidth?: number;
  canvasHeight?: number;
  withPedestal?: boolean;
}

export class HoloScreen {
  readonly group = new THREE.Group();
  readonly mesh: THREE.Mesh;
  readonly canvas: HTMLCanvasElement;
  readonly texture: THREE.CanvasTexture;
  readonly radius: number;
  readonly height: number;
  readonly width: number;
  readonly thetaStart: number;
  readonly thetaLength: number;
  private readonly model: ConsoleModel | null;
  private readonly material: THREE.MeshBasicMaterial;
  private disposed = false;
  private businessTargets: THREE.Mesh[] | null = null;

  constructor(options: HoloScreenOptions) {
    this.canvas = document.createElement('canvas');
    this.canvas.width = options.canvasWidth ?? 1024;
    this.canvas.height = options.canvasHeight ?? 576;
    this.texture = new THREE.CanvasTexture(this.canvas);
    this.texture.colorSpace = THREE.SRGBColorSpace;
    this.texture.generateMipmaps = false;
    this.texture.minFilter = THREE.LinearFilter;
    this.texture.magFilter = THREE.LinearFilter;
    this.radius = options.radius ?? 1.25;
    const layout = terminalLayout(options.stationId ?? "config");
    this.height = options.screenHeight ?? layout.height;
    this.width = this.height * this.canvas.width / this.canvas.height;
    this.thetaLength = options.thetaLength ?? 0;
    this.thetaStart = Math.PI - this.thetaLength / 2;
    this.material = new THREE.MeshBasicMaterial({
      map: this.texture, color: 0x7c969e, side: THREE.FrontSide, toneMapped: false,
    });
    this.mesh = new THREE.Mesh(new THREE.PlaneGeometry(this.width, this.height), this.material);
    this.mesh.name = 'console-inset-interface';
    this.model = options.withPedestal === false ? null : new ConsoleModel(options.accent, this.width, this.height, options.stationId);
    if (this.model) {
      this.group.add(this.model.group);
      this.model.panel.add(this.mesh);
      this.mesh.position.z = 0.096;
    } else {
      this.group.add(this.mesh);
    }
    // game keeps raycasting screen.mesh with recursive=false. Delegate the physical
    // switch caps here, keeping their object identity and no UV (not a canvas click).
    const surfaceRaycast = this.mesh.raycast.bind(this.mesh);
    this.mesh.raycast = (raycaster, intersections) => {
      if (this.disposed) return;
      this.group.updateWorldMatrix(true, true);
      if (!this.businessTargets) surfaceRaycast(raycaster, intersections);
      for (const key of this.businessTargets ?? this.model?.keys ?? []) {
        const hits: THREE.Intersection[] = [];
        key.raycast(raycaster, hits);
        for (const hit of hits) {
          delete hit.uv;
          intersections.push(hit);
        }
      }
    };
  }

  setBusinessControls(group: THREE.Group, targets: THREE.Mesh[]): void {
    this.businessTargets = targets;
    this.mesh.visible = false;
    this.model?.setBusinessControls(true);
    this.group.add(group);
  }

  setAccent(color: number): void {
    this.model?.setAccent(color);
  }

  setFocused(focused: boolean): void {
    this.material.color.setHex(focused ? 0xffffff : 0x7c969e);
    this.model?.setFocused(focused);
  }

  update(dt: number, focused: boolean): void {
    this.model?.update(dt, focused);
  }

  pressKey(key: THREE.Object3D | null): void {
    this.model?.pressKey(key);
  }

  /** Actual visible glass center, not the old curvature origin behind the surface. */
  worldCenter(target = new THREE.Vector3()): THREE.Vector3 {
    this.mesh.updateWorldMatrix(true, false);
    return this.mesh.getWorldPosition(target);
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.model?.dispose();
    this.mesh.geometry.dispose();
    this.material.dispose();
    this.texture.dispose();
  }
}

/** The rig has its origin on the floor and faces local +Z. No borrowed materials. */
export function createStationRig(
  materials: ShipMaterials,
  options: { accent: number; title: string; subtitle?: string; stationId?: string },
): { group: THREE.Group; screen: HoloScreen } {
  const group = new THREE.Group();
  group.name = options.title;
  const screen = new HoloScreen({ accent: options.accent, stationId: options.stationId, canvasWidth: 1024, canvasHeight: 576 });
  group.add(screen.group);
  void materials;
  return { group, screen };
}
