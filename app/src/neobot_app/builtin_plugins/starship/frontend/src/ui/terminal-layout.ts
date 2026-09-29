import * as THREE from 'three';

/** Metre-scale operating surfaces. Geometry and the focus camera share this contract. */
export interface TerminalLayout {
  kind: string;
  center: [number, number, number];
  tilt: number;
  width: number;
  height: number;
  columns: number;
}
export function terminalLayout(id: string): TerminalLayout {
  switch (id) {
    case 'navigation': return { kind: 'chart-basin', center: [0, 1.48, 0.94], tilt: -0.48, width: 2.48, height: 1.12, columns: 3 };
    case 'system': return { kind: 'power-prism', center: [0, 1.66, 0.73], tilt: -0.16, width: 2.12, height: 1.82, columns: 2 };
    case 'bots': return { kind: 'communications-wings', center: [0, 1.62, 0.84], tilt: -0.22, width: 2.48, height: 1.82, columns: 2 };
    case 'plugins': return { kind: 'module-slots', center: [0, 1.52, 0.86], tilt: -0.28, width: 2.48, height: 1.12, columns: 3 };
    case 'usage': return { kind: 'telemetry-dial', center: [0, 1.58, 0.91], tilt: -0.32, width: 2.48, height: 1.12, columns: 3 };
    case 'dashboard': return { kind: 'command-crown', center: [0, 1.55, 0.87], tilt: -0.28, width: 2.48, height: 1.12, columns: 3 };
    default: return { kind: id === 'logs' ? 'archive-book' : 'foldout-projector', center: [0, 1.84, 0.64], tilt: -0.12, width: 2.5, height: 2.5 * 576 / 1024, columns: 0 };
  }
}

export function placeOperatingSurface(group: THREE.Object3D, layout: TerminalLayout): void {
  group.position.set(...layout.center);
  group.rotation.x = layout.tilt;
}

/** Fit the real visible surface, not an arbitrary point in the pedestal. */
export function surfaceFocus(surface: THREE.Object3D, width: number, height: number, camera: THREE.PerspectiveCamera) {
  surface.updateWorldMatrix(true, false);
  const center = surface.getWorldPosition(new THREE.Vector3());
  const normal = new THREE.Vector3(0, 0, 1).transformDirection(surface.matrixWorld);
  const scale = surface.getWorldScale(new THREE.Vector3());
  const tangent = Math.tan(THREE.MathUtils.degToRad(camera.fov / 2));
  const distance = Math.max(width * scale.x / (2 * tangent * Math.max(0.4, camera.aspect) * 0.86),
    height * scale.y / (2 * tangent * 0.84));
  return { target: center, position: center.clone().addScaledVector(normal, distance) };
}
