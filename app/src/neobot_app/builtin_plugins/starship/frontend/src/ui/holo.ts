// ui/holo.ts —— 全息曲面屏：自建弧面几何 + canvas 贴图 + 发光边框 + 基座。
// 「不平面」的关键：屏幕是水平与垂直双向带弧度的投影面（环绕玩家），
// 配合发光边框、地面反光与体积光，而不是一块平板。

import * as THREE from 'three';
import { ShipMaterials } from '../world/materials';

export interface HoloScreenOptions {
  accent: number;
  /** 屏幕弧面半径（米） */
  radius?: number;
  /** 屏幕高度（米） */
  screenHeight?: number;
  thetaLength?: number;
  /** canvas 贴图分辨率 */
  canvasWidth?: number;
  canvasHeight?: number;
  withPedestal?: boolean;
}

/**
 * 弧面屏幕几何：绕 Y 轴的水平弧 + 垂直方向的轻微鼓出。
 *
 * 自己生成而不使用 CylinderGeometry：UV 完全可控（不再有圆柱 UV 的镜像/朝向问题），
 * 法线朝向玩家一侧，因此材质用 FrontSide 即可，不存在背面剔除的坑。
 */
function createCurvedScreenGeometry(
  radius: number,
  height: number,
  thetaStart: number,
  thetaLength: number,
  segments = 32,
  rows = 6,
  bulge = 0.07,
): THREE.BufferGeometry {
  const positions: number[] = [];
  const normals: number[] = [];
  const uvs: number[] = [];
  const indices: number[] = [];
  for (let row = 0; row <= rows; row += 1) {
    const v = row / rows;
    const y = (0.5 - v) * height;
    const radial = radius - Math.sin(v * Math.PI) * bulge;
    for (let column = 0; column <= segments; column += 1) {
      const u = column / segments;
      const theta = thetaStart + u * thetaLength;
      const x = Math.sin(theta) * radial;
      const z = Math.cos(theta) * radial;
      positions.push(x, y, z);
      // 朝向轴心（玩家所在的一侧）
      normals.push(-Math.sin(theta), 0, -Math.cos(theta));
      uvs.push(u, 1 - v);
    }
  }
  const stride = segments + 1;
  for (let row = 0; row < rows; row += 1) {
    for (let column = 0; column < segments; column += 1) {
      const a = row * stride + column;
      const b = a + 1;
      const c = a + stride;
      const d = c + 1;
      // 逆时针缠绕：面朝玩家一侧（法线指向轴心），FrontSide 才不会被剔除
      indices.push(a, b, c, b, d, c);
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute('normal', new THREE.Float32BufferAttribute(normals, 3));
  geometry.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2));
  geometry.setIndex(indices);
  geometry.computeBoundingSphere();
  return geometry;
}

export class HoloScreen {
  readonly group = new THREE.Group();
  readonly mesh: THREE.Mesh;
  readonly canvas: HTMLCanvasElement;
  readonly texture: THREE.CanvasTexture;
  readonly radius: number;
  readonly height: number;
  readonly thetaStart: number;
  readonly thetaLength: number;
  private readonly glow: THREE.Mesh;
  private readonly rimTop: THREE.Mesh;
  private readonly rimBottom: THREE.Mesh;
  private readonly accent: THREE.Color;

  constructor(options: HoloScreenOptions) {
    const canvasWidth = options.canvasWidth ?? 1024;
    const canvasHeight = options.canvasHeight ?? 576;
    this.canvas = document.createElement('canvas');
    this.canvas.width = canvasWidth;
    this.canvas.height = canvasHeight;
    this.texture = new THREE.CanvasTexture(this.canvas);
    this.texture.colorSpace = THREE.SRGBColorSpace;
    this.texture.generateMipmaps = false;
    this.texture.minFilter = THREE.LinearFilter;
    this.texture.magFilter = THREE.LinearFilter;
    this.texture.wrapS = THREE.ClampToEdgeWrapping;
    this.texture.wrapT = THREE.ClampToEdgeWrapping;

    this.radius = options.radius ?? 1.55;
    this.height = options.screenHeight ?? 0.95;
    this.thetaLength = options.thetaLength ?? 1.15;
    this.thetaStart = Math.PI - this.thetaLength / 2;
    this.accent = new THREE.Color(options.accent);

    this.mesh = new THREE.Mesh(
      createCurvedScreenGeometry(
        this.radius,
        this.height,
        this.thetaStart,
        this.thetaLength,
      ),
      new THREE.MeshBasicMaterial({
        map: this.texture,
        transparent: true,
        opacity: 0.96,
        side: THREE.FrontSide,
        depthWrite: false,
        toneMapped: false,
      }),
    );
    this.mesh.name = 'holo-screen';
    this.group.add(this.mesh);

    // 外发光：比屏幕略大的弧面，加色混合
    this.glow = new THREE.Mesh(
      createCurvedScreenGeometry(
        this.radius + 0.02,
        this.height * 1.08,
        this.thetaStart,
        this.thetaLength,
        32,
        4,
        0.08,
      ),
      new THREE.MeshBasicMaterial({
        color: this.accent,
        transparent: true,
        opacity: 0.16,
        side: THREE.DoubleSide,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      }),
    );
    this.group.add(this.glow);

    // 上下发光边框：复用同一套弧面生成器，保证与屏幕严丝合缝
    const rimMaterial = new THREE.MeshBasicMaterial({
      color: this.accent,
      transparent: true,
      opacity: 0.95,
      side: THREE.DoubleSide,
      toneMapped: false,
    });
    const rimGeometry = createCurvedScreenGeometry(
      this.radius + 0.015,
      0.05,
      this.thetaStart - 0.02,
      this.thetaLength + 0.04,
      32,
      1,
      0,
    );
    this.rimTop = new THREE.Mesh(rimGeometry, rimMaterial);
    this.rimTop.position.y = this.height / 2 + 0.03;
    this.rimBottom = new THREE.Mesh(rimGeometry, rimMaterial);
    this.rimBottom.position.y = -this.height / 2 - 0.03;
    this.group.add(this.rimTop, this.rimBottom);

    if (options.withPedestal !== false) {
      const column = new THREE.Mesh(
        new THREE.CylinderGeometry(0.16, 0.24, 0.9, 12),
        new THREE.MeshStandardMaterial({ color: 0x5a6472, metalness: 0.8, roughness: 0.4 }),
      );
      column.position.y = -this.height / 2 - 0.45;
      const base = new THREE.Mesh(
        new THREE.CylinderGeometry(0.55, 0.62, 0.12, 16),
        new THREE.MeshStandardMaterial({ color: 0x424a56, metalness: 0.7, roughness: 0.5 }),
      );
      base.position.y = -this.height / 2 - 0.92;
      const halo = new THREE.Mesh(
        new THREE.TorusGeometry(0.5, 0.03, 6, 28),
        new THREE.MeshBasicMaterial({
          color: this.accent,
          transparent: true,
          opacity: 0.7,
          toneMapped: false,
        }),
      );
      halo.rotation.x = Math.PI / 2;
      halo.position.y = -this.height / 2 - 0.86;
      this.group.add(column, base, halo);
    }

    // 投影光锥（让全息屏有「从底座投上来」的体积感）
    const cone = new THREE.Mesh(
      createCurvedScreenGeometry(
        this.radius * 0.98,
        this.height * 0.55,
        this.thetaStart,
        this.thetaLength,
        24,
        2,
        0.02,
      ),
      new THREE.MeshBasicMaterial({
        color: this.accent,
        transparent: true,
        opacity: 0.07,
        side: THREE.DoubleSide,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      }),
    );
    cone.position.y = -this.height / 2 - 0.24;
    this.group.add(cone);
  }

  setAccent(color: number): void {
    this.accent.setHex(color);
    (this.glow.material as THREE.MeshBasicMaterial).color.setHex(color);
    (this.rimTop.material as THREE.MeshBasicMaterial).color.setHex(color);
  }

  /** 屏幕中心的世界坐标（用于相机聚焦与距离判断） */
  worldCenter(target = new THREE.Vector3()): THREE.Vector3 {
    return this.mesh.getWorldPosition(target);
  }

  dispose(): void {
    this.texture.dispose();
    this.group.traverse((object) => {
      const mesh = object as THREE.Mesh;
      if (mesh.geometry) mesh.geometry.dispose();
      const material = mesh.material as THREE.Material | THREE.Material[] | undefined;
      if (Array.isArray(material)) material.forEach((item) => item.dispose());
      else material?.dispose();
    });
  }
}

/** 把全息屏架在墙边的小工具：返回可直接 add 到场景的组 */
export function createStationRig(
  materials: ShipMaterials,
  options: { accent: number; title: string; subtitle?: string },
): { group: THREE.Group; screen: HoloScreen } {
  const group = new THREE.Group();
  const screen = new HoloScreen({
    canvasWidth: 1024,
    canvasHeight: 576,
    accent: options.accent,
    radius: 1.7,
    screenHeight: 1.05,
    thetaLength: 1.2,
  });
  screen.group.position.set(0, 1.35, 0);
  group.add(screen.group);

  // 操作台面（放在屏幕前方偏下，不挡住投影）
  const desk = new THREE.Mesh(
    new THREE.BoxGeometry(1.5, 0.08, 0.42),
    new THREE.MeshStandardMaterial({ color: 0x4b5563, metalness: 0.7, roughness: 0.45 }),
  );
  desk.position.set(0, 0.76, 1.28);
  group.add(desk);
  const deskGlow = new THREE.Mesh(
    new THREE.BoxGeometry(1.42, 0.02, 0.34),
    new THREE.MeshBasicMaterial({
      color: options.accent,
      transparent: true,
      opacity: 0.3,
      toneMapped: false,
    }),
  );
  deskGlow.position.set(0, 0.81, 1.28);
  group.add(deskGlow);
  void materials;
  return { group, screen };
}
