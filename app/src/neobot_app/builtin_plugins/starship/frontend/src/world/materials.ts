import * as THREE from 'three';
import { PSIONIC_PALETTE, type ShipPalette } from './style';

export interface ShipMaterials {
  hull: THREE.MeshStandardMaterial; wall: THREE.MeshStandardMaterial;
  wallAccent: THREE.MeshStandardMaterial; floor: THREE.MeshStandardMaterial;
  ceiling: THREE.MeshStandardMaterial; trim: THREE.MeshStandardMaterial;
  glass: THREE.MeshPhysicalMaterial; prop: THREE.MeshStandardMaterial;
  emissive: THREE.MeshBasicMaterial; screen: THREE.MeshBasicMaterial;
}

export interface AlloyFinish {
  /** All frequencies are in authored object coordinates, before exterior scale. */
  scale?: number;
  roughnessVariation?: number;
  colourVariation?: number;
  relief?: number;
}

const alloySettings = new WeakMap<THREE.Material, THREE.Vector4>();

/** UV-independent brushed alloy. Safe for merged geometry with UVs removed, and
 * for the 74.4 km exterior: detail is authored in local coordinates, not imprecise
 * astronomical world coordinates. Derivative filtering fades subpixel grain.
 * No normal/roughness textures, tangents, extra draw calls or external assets. */
export function applyAlloyFinish<T extends THREE.MeshStandardMaterial>(material: T, options: AlloyFinish = {}): T {
  const settings = new THREE.Vector4(options.scale ?? 1, options.roughnessVariation ?? 0.14,
    options.colourVariation ?? 0.07, options.relief ?? 0.00008);
  const existing = alloySettings.get(material);
  if (existing) { existing.copy(settings); return material; }
  alloySettings.set(material, settings);
  const previousCompile = material.onBeforeCompile;
  const previousCacheKey = material.customProgramCacheKey.bind(material)();
  material.onBeforeCompile = (shader, renderer) => {
    previousCompile.call(material, shader, renderer);
    // A cloned finish may preserve a previous compile chain (e.g. habitat cuts).
    // Reuse that injected program instead of declaring its varyings/functions twice.
    const alreadyInjected = !!shader.uniforms.arkAlloy;
    shader.uniforms.arkAlloy = { value: settings };
    if (alreadyInjected) return;
    shader.vertexShader = shader.vertexShader.replace('#include <common>',
      '#include <common>\nvarying vec3 vArkAlloyPosition;');
    shader.vertexShader = shader.vertexShader.replace('#include <begin_vertex>',
      '#include <begin_vertex>\nvArkAlloyPosition = position;');
    shader.fragmentShader = shader.fragmentShader.replace('#include <common>', String.raw`      #include <common>
      varying vec3 vArkAlloyPosition;
      uniform vec4 arkAlloy;
      float arkHash(vec3 p) {
        p = fract(p * 0.1031);
        p += dot(p, p.yzx + 33.33);
        return fract((p.x + p.y) * p.z);
      }
      float arkNoise(vec3 p) {
        vec3 i = floor(p), f = fract(p);
        f = f * f * (3.0 - 2.0 * f);
        return mix(mix(mix(arkHash(i), arkHash(i + vec3(1,0,0)), f.x),
          mix(arkHash(i + vec3(0,1,0)), arkHash(i + vec3(1,1,0)), f.x), f.y),
          mix(mix(arkHash(i + vec3(0,0,1)), arkHash(i + vec3(1,0,1)), f.x),
          mix(arkHash(i + vec3(0,1,1)), arkHash(i + vec3(1,1,1)), f.x), f.y), f.z);
      }
    `);
    shader.fragmentShader = shader.fragmentShader.replace('#include <color_fragment>', String.raw`      #include <color_fragment>
      vec3 arkP = vArkAlloyPosition * arkAlloy.x;
      float arkFootprint = max(length(dFdx(arkP)), length(dFdy(arkP)));
      float arkMacroVisibility = 1.0 - smoothstep(0.5, 2.5, arkFootprint);
      float arkMacro = (arkNoise(arkP * 0.73) - 0.5) * arkMacroVisibility;
      float arkGrainVisibility = 1.0 - smoothstep(0.008, 0.06, arkFootprint);
      float arkGrain = (arkNoise(arkP * vec3(34.0, 190.0, 34.0)) - 0.5) * arkGrainVisibility;
      float arkPhase = dot(arkP, vec3(0.78, 0.19, 0.58)) * 870.0;
      float arkBrush = sin(arkPhase) * (1.0 - smoothstep(0.4, 2.0, fwidth(arkPhase)));
      diffuseColor.rgb *= 1.0 + arkAlloy.z * (arkMacro * 1.7 + arkGrain * 0.3);
      float arkRelief = (arkGrain * 0.6 + arkBrush * 0.08) * arkAlloy.w;
    `);
    shader.fragmentShader = shader.fragmentShader.replace('#include <roughnessmap_fragment>', String.raw`      #include <roughnessmap_fragment>
      roughnessFactor = clamp(roughnessFactor + arkAlloy.y *
        (arkMacro * 1.5 + arkGrain * 0.65 + arkBrush * 0.08), 0.16, 0.94);
    `);
    shader.fragmentShader = shader.fragmentShader.replace('#include <normal_fragment_maps>', String.raw`      #include <normal_fragment_maps>
      // Screen-space surface gradient, no UV tangent frame and no world-space noise.
      vec3 arkDx = dFdx(-vViewPosition), arkDy = dFdy(-vViewPosition);
      vec3 arkR1 = cross(arkDy, normal), arkR2 = cross(normal, arkDx);
      float arkDet = dot(arkDx, arkR1);
      vec3 arkGradient = sign(arkDet) * (dFdx(arkRelief) * arkR1 + dFdy(arkRelief) * arkR2);
      if (abs(arkDet) > 0.0000001) normal = normalize(abs(arkDet) * normal - arkGradient);
    `);
  };
  // Options are uniforms, not source changes: all finished materials share programs.
  material.customProgramCacheKey = () => previousCacheKey + '|ark-alloy-v1';
  material.dithering = true;
  material.needsUpdate = true;
  return material;
}

/** Layered electrum, burnished edges, ceramic obsidian and satin deck alloy.
 * A PMREM environment (see core/rendering.ts) supplies real specular response. */
export function createShipMaterials(palette: Readonly<ShipPalette> = PSIONIC_PALETTE): ShipMaterials {
  const metal = (color: number, roughness: number, metalness: number, env: number, finish: AlloyFinish = {}) => {
    const material = new THREE.MeshStandardMaterial({ color, roughness, metalness, envMapIntensity: env });
    return applyAlloyFinish(material, finish);
  };
  const trim = new THREE.MeshStandardMaterial({
    color: new THREE.Color(palette.energy).multiplyScalar(0.22),
    emissive: palette.energy, emissiveIntensity: 0.9,
    metalness: 0.48, roughness: 0.3, envMapIntensity: 0.45,
  });
  trim.name = 'psionic-inlay-not-white';
  const glass = new THREE.MeshPhysicalMaterial({
    color: palette.glass, roughness: 0.15, metalness: 0.08,
    transparent: true, opacity: 0.085, side: THREE.DoubleSide, depthWrite: false,
    ior: 1.46, specularIntensity: 0.5, envMapIntensity: 0.65,
  });
  // Transmission would require another scene render on every pane. Thin forcefield
  // glazing instead reflects the HDR environment without refracting the whole scene.
  const emissive = new THREE.MeshBasicMaterial({
    color: new THREE.Color(palette.energyCore).lerp(new THREE.Color(palette.energy), 0.68).multiplyScalar(1.08),
    toneMapped: true,
  });
  return {
    hull: metal(palette.armour, 0.43, 0.74, 0.64, { roughnessVariation: 0.055, colourVariation: 0.025, relief: 0 }),
    wall: metal(palette.structure, 0.46, 0.5, 0.48, { roughnessVariation: 0.04, relief: 0 }),
    wallAccent: metal(palette.armourEdge, 0.34, 0.8, 0.68, { roughnessVariation: 0.025, colourVariation: 0.012, relief: 0 }),
    floor: metal(palette.deck, 0.49, 0.46, 0.35, { scale: 1.8, roughnessVariation: 0.04, colourVariation: 0.012, relief: 0 }),
    ceiling: metal(palette.recess, 0.56, 0.4, 0.4, { roughnessVariation: 0.025, relief: 0 }),
    prop: metal(palette.bronze, 0.47, 0.57, 0.48, { roughnessVariation: 0.045, colourVariation: 0.025, relief: 0 }),
    trim, glass, emissive,
    screen: new THREE.MeshBasicMaterial({ color: 0x06111b, toneMapped: true }),
  };
}

/** 生成一块带边框的文字标牌贴图（舱室名牌、提示牌） */
export function createSignTexture(
  title: string,
  subtitle = '',
  options: { width?: number; height?: number; accent?: string } = {},
): THREE.CanvasTexture {
  const width = options.width ?? 512;
  const height = options.height ?? 160;
  const accent = options.accent || '#4fd8ff';
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d')!;
  ctx.clearRect(0,0,width,height);
  ctx.strokeStyle=accent;ctx.lineWidth=1.5;
  ctx.beginPath();ctx.moveTo(width*.04,height*.57);ctx.lineTo(width*.16,height*.57);
  ctx.moveTo(width*.84,height*.57);ctx.lineTo(width*.96,height*.57);ctx.stroke();
  ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillStyle='#cbd7df';
  ctx.font='500 '+Math.round(height*.34)+'px "Microsoft YaHei", sans-serif';
  ctx.fillText(title,width/2,subtitle?height*.39:height*.52,width*.76);
  if(subtitle){ctx.fillStyle='#668bb1';ctx.font=Math.round(height*.125)+'px "Segoe UI", sans-serif';ctx.fillText(subtitle,width/2,height*.76,width*.8);}
  const texture = new THREE.CanvasTexture(canvas);
  texture.anisotropy = 4;
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}