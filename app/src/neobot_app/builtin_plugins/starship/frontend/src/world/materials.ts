// world/materials.ts —— 程序化材质与贴图（不依赖任何外部资源，随包体积为零）。
// 全部用 Canvas 生成，避免下载贴图；颜色偏冷色科幻风，配合自发光条带。

import * as THREE from 'three';

export interface ShipMaterials {
  hull: THREE.MeshStandardMaterial;
  wall: THREE.MeshStandardMaterial;
  wallAccent: THREE.MeshStandardMaterial;
  floor: THREE.MeshStandardMaterial;
  ceiling: THREE.MeshStandardMaterial;
  trim: THREE.MeshStandardMaterial;
  glass: THREE.MeshPhysicalMaterial;
  prop: THREE.MeshStandardMaterial;
  emissive: THREE.MeshBasicMaterial;
  screen: THREE.MeshBasicMaterial;
}

function panelTexture(base: string, line: string, size = 256): THREE.CanvasTexture {
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d')!;
  ctx.fillStyle = base;
  ctx.fillRect(0, 0, size, size);
  ctx.strokeStyle = line;
  ctx.lineWidth = 2;
  const step = size / 4;
  for (let i = 0; i <= 4; i += 1) {
    ctx.beginPath();
    ctx.moveTo(i * step, 0);
    ctx.lineTo(i * step, size);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(0, i * step);
    ctx.lineTo(size, i * step);
    ctx.stroke();
  }
  ctx.fillStyle = 'rgba(255,255,255,0.05)';
  for (let i = 0; i < 60; i += 1) {
    ctx.fillRect(Math.random() * size, Math.random() * size, 2, 2);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  texture.anisotropy = 4;
  return texture;
}

function gridTexture(base: string, line: string, size = 256): THREE.CanvasTexture {
  const texture = panelTexture(base, line, size);
  texture.repeat.set(2, 2);
  return texture;
}

export function createShipMaterials(): ShipMaterials {
  const wallTexture = panelTexture('#2b323d', '#39414f');
  wallTexture.repeat.set(2, 1);
  const floorTexture = gridTexture('#1d2229', '#2c333d');
  const ceilingTexture = panelTexture('#191d24', '#242a33');

  return {
    hull: new THREE.MeshStandardMaterial({
      color: 0x5a6373,
      metalness: 0.85,
      roughness: 0.42,
      side: THREE.FrontSide,
    }),
    wall: new THREE.MeshStandardMaterial({
      map: wallTexture,
      color: 0xc4cfdd,
      metalness: 0.3,
      roughness: 0.68,
      side: THREE.DoubleSide,
      emissive: new THREE.Color(0x0d1620),
      emissiveIntensity: 1,
    }),
    wallAccent: new THREE.MeshStandardMaterial({
      color: 0x2f6d8c,
      metalness: 0.5,
      roughness: 0.4,
      emissive: new THREE.Color(0x0d3a52),
      emissiveIntensity: 0.6,
      side: THREE.DoubleSide,
    }),
    floor: new THREE.MeshStandardMaterial({
      map: floorTexture,
      color: 0x9aa3b0,
      metalness: 0.25,
      roughness: 0.85,
      side: THREE.DoubleSide,
    }),
    ceiling: new THREE.MeshStandardMaterial({
      map: ceilingTexture,
      color: 0x8d96a3,
      metalness: 0.3,
      roughness: 0.8,
      side: THREE.DoubleSide,
    }),
    trim: new THREE.MeshStandardMaterial({
      color: 0x123040,
      emissive: new THREE.Color(0x38d8ff),
      emissiveIntensity: 1.6,
      metalness: 0.2,
      roughness: 0.4,
    }),
    glass: new THREE.MeshPhysicalMaterial({
      color: 0xa8dcff,
      metalness: 0,
      roughness: 0.06,
      transmission: 0.85,
      transparent: true,
      opacity: 0.32,
      side: THREE.DoubleSide,
      depthWrite: false,
    }),
    prop: new THREE.MeshStandardMaterial({
      color: 0x6c7684,
      metalness: 0.6,
      roughness: 0.5,
    }),
    emissive: new THREE.MeshBasicMaterial({ color: 0x8fe8ff }),
    screen: new THREE.MeshBasicMaterial({ color: 0x0a1a24 }),
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
  ctx.fillStyle = '#0b1218';
  ctx.fillRect(0, 0, width, height);
  ctx.strokeStyle = accent;
  ctx.lineWidth = 4;
  ctx.strokeRect(4, 4, width - 8, height - 8);
  ctx.fillStyle = accent;
  ctx.fillRect(4, 4, 96, height - 8);
  ctx.fillStyle = '#04121a';
  ctx.font = 'bold 64px "Segoe UI", system-ui, sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText('◈', 52, height / 2 + 2);
  ctx.fillStyle = '#e8f6ff';
  ctx.textAlign = 'left';
  ctx.font = 'bold 56px "Microsoft YaHei", "PingFang SC", system-ui, sans-serif';
  ctx.fillText(title, 124, subtitle ? height / 2 - 18 : height / 2);
  if (subtitle) {
    ctx.fillStyle = '#7fb8d4';
    ctx.font = '30px "Microsoft YaHei", "PingFang SC", system-ui, sans-serif';
    ctx.fillText(subtitle, 124, height / 2 + 34);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.anisotropy = 4;
  return texture;
}
