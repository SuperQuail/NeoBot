// space/space.ts —— 舰外太空场景：星空/星云天空盒、行星、小行星流、过往飞船与跃迁。
// 全部程序化生成，无外部资源；对象数量随画质档位变化。

import * as THREE from 'three';
import type { QualityPreset } from '../config';

const SKY_RADIUS = 8000;

export interface SpaceSceneOptions {
  quality: QualityPreset;
  seed?: number;
}

interface Asteroid {
  position: THREE.Vector3;
  velocity: THREE.Vector3;
  rotation: THREE.Euler;
  spin: THREE.Vector3;
  scale: number;
}

interface TrafficShip {
  root: THREE.Group;
  velocity: THREE.Vector3;
  life: number;
}

const SKY_VERTEX = [
  'varying vec3 vDir;',
  'void main() {',
  '  vDir = normalize(position);',
  '  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);',
  '}',
].join('\n');

const SKY_FRAGMENT = [
  'varying vec3 vDir;',
  'uniform float uTime;',
  'uniform vec3 uNebulaA;',
  'uniform vec3 uNebulaB;',
  'uniform float uSeed;',
  'float hash13(vec3 p) {',
  '  p = fract(p * 0.1031);',
  '  p += dot(p, p.yzx + 33.33);',
  '  return fract((p.x + p.y) * p.z);',
  '}',
  'float noise(vec3 p) {',
  '  vec3 i = floor(p);',
  '  vec3 f = fract(p);',
  '  f = f * f * (3.0 - 2.0 * f);',
  '  float n000 = hash13(i);',
  '  float n100 = hash13(i + vec3(1.0, 0.0, 0.0));',
  '  float n010 = hash13(i + vec3(0.0, 1.0, 0.0));',
  '  float n110 = hash13(i + vec3(1.0, 1.0, 0.0));',
  '  float n001 = hash13(i + vec3(0.0, 0.0, 1.0));',
  '  float n101 = hash13(i + vec3(1.0, 0.0, 1.0));',
  '  float n011 = hash13(i + vec3(0.0, 1.0, 1.0));',
  '  float n111 = hash13(i + vec3(1.0, 1.0, 1.0));',
  '  return mix(mix(mix(n000, n100, f.x), mix(n010, n110, f.x), f.y),',
  '             mix(mix(n001, n101, f.x), mix(n011, n111, f.x), f.y), f.z);',
  '}',
  'float fbm(vec3 p) {',
  '  float value = 0.0;',
  '  float amplitude = 0.5;',
  '  for (int i = 0; i < 4; i++) {',
  '    value += amplitude * noise(p);',
  '    p *= 2.02;',
  '    amplitude *= 0.5;',
  '  }',
  '  return value;',
  '}',
  'float starLayer(vec3 dir, float scale, float threshold) {',
  '  vec3 p = dir * scale;',
  '  vec3 cell = floor(p);',
  '  vec3 local = fract(p) - 0.5;',
  '  float h = hash13(cell + uSeed);',
  '  float present = step(threshold, h);',
  '  float core = smoothstep(0.16, 0.0, length(local));',
  '  float twinkle = 0.75 + 0.25 * sin(uTime * 1.7 + h * 60.0);',
  '  return present * core * twinkle;',
  '}',
  'void main() {',
  '  vec3 dir = normalize(vDir);',
  '  vec3 base = vec3(0.004, 0.008, 0.016);',
  '  float nebula = fbm(dir * 2.4 + uSeed);',
  '  float nebula2 = fbm(dir * 5.1 - uSeed * 0.6);',
  '  vec3 color = base;',
  '  color += uNebulaA * pow(smoothstep(0.45, 0.95, nebula), 2.2) * 0.9;',
  '  color += uNebulaB * pow(smoothstep(0.5, 1.0, nebula2), 3.0) * 0.55;',
  '  float stars = starLayer(dir, 420.0, 0.9955) * 1.5;',
  '  stars += starLayer(dir, 260.0, 0.9975) * 2.2;',
  '  stars += starLayer(dir, 150.0, 0.9990) * 3.4;',
  '  color += vec3(0.85, 0.92, 1.0) * stars;',
  '  gl_FragColor = vec4(color, 1.0);',
  '}',
].join('\n');

const PLANET_VERTEX = [
  'varying vec3 vNormal;',
  'varying vec3 vPosition;',
  'varying vec3 vWorld;',
  'void main() {',
  '  vNormal = normalize(normalMatrix * normal);',
  '  vPosition = position;',
  '  vWorld = (modelMatrix * vec4(position, 1.0)).xyz;',
  '  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);',
  '}',
].join('\n');

const PLANET_FRAGMENT = [
  'varying vec3 vNormal;',
  'varying vec3 vPosition;',
  'varying vec3 vWorld;',
  'uniform vec3 uColorA;',
  'uniform vec3 uColorB;',
  'uniform vec3 uSun;',
  'uniform vec3 uAtmosphere;',
  'float hash13(vec3 p) {',
  '  p = fract(p * 0.1031);',
  '  p += dot(p, p.yzx + 33.33);',
  '  return fract((p.x + p.y) * p.z);',
  '}',
  'float noise(vec3 p) {',
  '  vec3 i = floor(p);',
  '  vec3 f = fract(p);',
  '  f = f * f * (3.0 - 2.0 * f);',
  '  float n000 = hash13(i);',
  '  float n100 = hash13(i + vec3(1.0, 0.0, 0.0));',
  '  float n010 = hash13(i + vec3(0.0, 1.0, 0.0));',
  '  float n110 = hash13(i + vec3(1.0, 1.0, 0.0));',
  '  float n001 = hash13(i + vec3(0.0, 0.0, 1.0));',
  '  float n101 = hash13(i + vec3(1.0, 0.0, 1.0));',
  '  float n011 = hash13(i + vec3(0.0, 1.0, 1.0));',
  '  float n111 = hash13(i + vec3(1.0, 1.0, 1.0));',
  '  return mix(mix(mix(n000, n100, f.x), mix(n010, n110, f.x), f.y),',
  '             mix(mix(n001, n101, f.x), mix(n011, n111, f.x), f.y), f.z);',
  '}',
  'void main() {',
  '  vec3 dir = normalize(vPosition);',
  '  float bands = noise(dir * 4.0) * 0.6 + noise(dir * 12.0) * 0.4;',
  '  vec3 surface = mix(uColorA, uColorB, smoothstep(0.35, 0.7, bands));',
  '  float lambert = clamp(dot(normalize(vNormal), normalize(uSun)), 0.0, 1.0);',
  '  float terminator = smoothstep(0.0, 0.35, lambert);',
  '  vec3 lit = surface * (0.12 + terminator * 1.25);',
  '  vec3 viewDir = normalize(cameraPosition - vWorld);',
  '  float fresnel = pow(1.0 - clamp(dot(viewDir, normalize(vNormal)), 0.0, 1.0), 3.0);',
  '  vec3 atmosphere = uAtmosphere * fresnel * (0.25 + terminator * 0.9);',
  '  gl_FragColor = vec4(lit + atmosphere, 1.0);',
  '}',
].join('\n');

const WARP_VERTEX = [
  'varying vec2 vUv;',
  'void main() {',
  '  vUv = uv;',
  '  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);',
  '}',
].join('\n');

const WARP_FRAGMENT = [
  'varying vec2 vUv;',
  'uniform float uWarp;',
  'uniform float uTime;',
  'uniform vec3 uColor;',
  'float hash21(vec2 p) {',
  '  p = fract(p * vec2(123.34, 456.21));',
  '  p += dot(p, p + 45.32);',
  '  return fract(p.x * p.y);',
  '}',
  'void main() {',
  '  if (uWarp <= 0.001) discard;',
  '  vec2 centered = vUv - 0.5;',
  '  float radius = length(centered);',
  '  float angle = atan(centered.y, centered.x);',
  '  float streaks = 0.0;',
  '  for (int i = 0; i < 3; i++) {',
  '    float layer = float(i);',
  '    float a = floor((angle + layer * 1.7) * 24.0) / 24.0;',
  '    float h = hash21(vec2(a, layer));',
  '    float speed = 1.6 + h * 2.4;',
  '    float phase = fract(radius * (2.0 + h * 3.0) - uTime * speed);',
  '    streaks += smoothstep(0.85, 1.0, phase) * (0.4 + 0.6 * h);',
  '  }',
  '  float falloff = smoothstep(0.05, 0.42, radius);',
  '  float alpha = streaks * falloff * uWarp;',
  '  gl_FragColor = vec4(uColor * (0.6 + streaks), clamp(alpha, 0.0, 0.95));',
  '}',
].join('\n');

export class SpaceScene {
  private readonly sky: THREE.Mesh;
  private readonly skyMaterial: THREE.ShaderMaterial;
  private readonly planet: THREE.Mesh;
  private readonly planetMaterial: THREE.ShaderMaterial;
  private readonly moon: THREE.Mesh;
  private readonly sun: THREE.Mesh;
  private readonly sunGlow: THREE.Mesh;
  private readonly asteroids: THREE.InstancedMesh;
  private readonly asteroidData: Asteroid[] = [];
  private readonly traffic: TrafficShip[] = [];
  private readonly warpOverlay: THREE.Mesh;
  private readonly warpMaterial: THREE.ShaderMaterial;
  private readonly sunLight: THREE.DirectionalLight;
  private readonly ambient: THREE.AmbientLight;
  private readonly quality: QualityPreset;
  private readonly dummy = new THREE.Object3D();
  private seed: number;
  private warpState: 'idle' | 'charging' | 'jumping' | 'arriving' = 'idle';
  private warpTimer = 0;
  private warpAmount = 0;
  private onArrive: (() => void) | null = null;
  private elapsed = 0;

  constructor(
    private readonly scene: THREE.Scene,
    private readonly camera: THREE.PerspectiveCamera,
    options: SpaceSceneOptions,
  ) {
    this.quality = options.quality;
    this.seed = options.seed ?? Math.random() * 1000;

    this.skyMaterial = new THREE.ShaderMaterial({
      vertexShader: SKY_VERTEX,
      fragmentShader: SKY_FRAGMENT,
      side: THREE.BackSide,
      depthWrite: false,
      uniforms: {
        uTime: { value: 0 },
        uSeed: { value: this.seed },
        uNebulaA: { value: new THREE.Color(0x2a4fa8) },
        uNebulaB: { value: new THREE.Color(0x9a3fb0) },
      },
    });
    this.sky = new THREE.Mesh(new THREE.SphereGeometry(SKY_RADIUS, 32, 16), this.skyMaterial);
    this.sky.name = 'space-sky';
    this.sky.frustumCulled = false;
    scene.add(this.sky);

    this.planetMaterial = new THREE.ShaderMaterial({
      vertexShader: PLANET_VERTEX,
      fragmentShader: PLANET_FRAGMENT,
      uniforms: {
        uColorA: { value: new THREE.Color(0x1d4f7a) },
        uColorB: { value: new THREE.Color(0x86c8a8) },
        uSun: { value: new THREE.Vector3(1, 0.3, 0.2).normalize() },
        uAtmosphere: { value: new THREE.Color(0x5ea8ff) },
      },
    });
    this.planet = new THREE.Mesh(new THREE.SphereGeometry(420, 48, 32), this.planetMaterial);
    this.planet.position.set(1400, -260, -900);
    scene.add(this.planet);

    this.moon = new THREE.Mesh(
      new THREE.SphereGeometry(90, 24, 16),
      new THREE.MeshStandardMaterial({ color: 0x9aa2ad, roughness: 0.95, metalness: 0.05 }),
    );
    this.moon.position.set(900, 180, 1200);
    scene.add(this.moon);

    this.sunLight = new THREE.DirectionalLight(0xfff2dd, 2.1);
    this.sunLight.position.set(1, 0.3, 0.2).multiplyScalar(2000);
    scene.add(this.sunLight);
    // 太空里没有大气散射，但完全无环境光会让背阴面死黑，影响可读性
    this.ambient = new THREE.AmbientLight(0x2f4055, 0.75);
    scene.add(this.ambient);

    const sunMaterial = new THREE.MeshBasicMaterial({ color: 0xfff0c0 });
    this.sun = new THREE.Mesh(new THREE.SphereGeometry(60, 20, 12), sunMaterial);
    this.sun.position.copy(this.sunLight.position);
    scene.add(this.sun);
    this.sunGlow = new THREE.Mesh(
      new THREE.SphereGeometry(170, 20, 12),
      new THREE.MeshBasicMaterial({
        color: 0xffd9a0,
        transparent: true,
        opacity: 0.18,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      }),
    );
    this.sunGlow.position.copy(this.sun.position);
    scene.add(this.sunGlow);

    this.asteroids = this.createAsteroidField();
    scene.add(this.asteroids);
    this.createTraffic();

    this.warpMaterial = new THREE.ShaderMaterial({
      vertexShader: WARP_VERTEX,
      fragmentShader: WARP_FRAGMENT,
      transparent: true,
      depthTest: false,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      uniforms: {
        uWarp: { value: 0 },
        uTime: { value: 0 },
        uColor: { value: new THREE.Color(0x9fe8ff) },
      },
    });
    this.warpOverlay = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), this.warpMaterial);
    this.warpOverlay.position.set(0, 0, -1);
    this.warpOverlay.frustumCulled = false;
    this.warpOverlay.renderOrder = 999;
    camera.add(this.warpOverlay);
    scene.add(camera);

    scene.fog = new THREE.FogExp2(0x05070d, this.quality.fogDensity);
  }

  private createAsteroidField(): THREE.InstancedMesh {
    const geometry = new THREE.IcosahedronGeometry(1, 1);
    const position = geometry.attributes.position as THREE.BufferAttribute;
    for (let i = 0; i < position.count; i += 1) {
      const scale = 0.7 + Math.random() * 0.6;
      position.setXYZ(
        i,
        position.getX(i) * scale,
        position.getY(i) * scale * (0.75 + Math.random() * 0.5),
        position.getZ(i) * scale,
      );
    }
    geometry.computeVertexNormals();
    const material = new THREE.MeshStandardMaterial({
      color: 0x8a8378,
      roughness: 0.95,
      metalness: 0.08,
      flatShading: true,
    });
    const mesh = new THREE.InstancedMesh(geometry, material, this.quality.asteroidCount);
    mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    mesh.frustumCulled = false;
    for (let i = 0; i < this.quality.asteroidCount; i += 1) {
      this.asteroidData.push(this.spawnAsteroid(true));
    }
    return mesh;
  }

  private spawnAsteroid(initial = false): Asteroid {
    const angle = Math.random() * Math.PI * 2;
    const distance = initial
      ? 200 + Math.random() * 1400
      : 1200 + Math.random() * 900;
    const height = (Math.random() - 0.5) * 700;
    const scale = 4 + Math.random() * 46;
    const speed = 4 + Math.random() * 22;
    const direction = new THREE.Vector3(
      Math.cos(angle) * Math.random() - 0.2,
      (Math.random() - 0.5) * 0.1,
      Math.sin(angle) * Math.random(),
    ).normalize();
    return {
      position: new THREE.Vector3(
        Math.cos(angle) * distance,
        height,
        Math.sin(angle) * distance * 0.6,
      ),
      velocity: direction.multiplyScalar(speed),
      rotation: new THREE.Euler(Math.random() * 3, Math.random() * 3, Math.random() * 3),
      spin: new THREE.Vector3(
        (Math.random() - 0.5) * 0.6,
        (Math.random() - 0.5) * 0.6,
        (Math.random() - 0.5) * 0.6,
      ),
      scale,
    };
  }

  private createTraffic(): void {
    const palette = [0x9fb4c8, 0xc8b49f, 0x8fa8b8, 0xb8a8c8];
    for (let i = 0; i < this.quality.trafficCount; i += 1) {
      const root = new THREE.Group();
      const color = palette[i % palette.length];
      const body = new THREE.Mesh(
        new THREE.BoxGeometry(26, 7, 9),
        new THREE.MeshStandardMaterial({ color, roughness: 0.5, metalness: 0.7 }),
      );
      const nose = new THREE.Mesh(
        new THREE.BoxGeometry(8, 4, 6),
        new THREE.MeshStandardMaterial({ color: 0xdadfe6, roughness: 0.4, metalness: 0.8 }),
      );
      nose.position.x = 16;
      const fin = new THREE.Mesh(
        new THREE.BoxGeometry(10, 9, 1.4),
        new THREE.MeshStandardMaterial({ color: 0x7d8b9c, roughness: 0.6, metalness: 0.5 }),
      );
      fin.position.set(-4, 6, 0);
      const engine = new THREE.Mesh(
        new THREE.CylinderGeometry(1.6, 2.4, 3, 12),
        new THREE.MeshBasicMaterial({ color: 0x7fd8ff }),
      );
      engine.rotation.z = Math.PI / 2;
      engine.position.x = -15;
      root.add(body, nose, fin, engine);
      this.resetTraffic(root);
      this.scene.add(root);
      this.traffic.push({
        root,
        velocity: new THREE.Vector3(),
        life: 0,
      });
    }
  }

  private resetTraffic(root: THREE.Group): void {
    const angle = Math.random() * Math.PI * 2;
    const distance = 400 + Math.random() * 900;
    root.position.set(
      Math.cos(angle) * distance,
      (Math.random() - 0.5) * 260,
      Math.sin(angle) * distance,
    );
    const target = new THREE.Vector3(
      (Math.random() - 0.5) * 600,
      (Math.random() - 0.5) * 200,
      (Math.random() - 0.5) * 600,
    );
    const entry = this.traffic.find((item) => item.root === root);
    const speed = 22 + Math.random() * 40;
    const velocity = target.clone().sub(root.position).normalize().multiplyScalar(speed);
    if (entry) entry.velocity.copy(velocity);
    root.lookAt(root.position.clone().add(velocity));
  }

  /** 触发跃迁：充能 → 跃迁 → 抵达新星系 */
  triggerWarp(onArrive?: () => void): boolean {
    if (this.warpState !== 'idle') return false;
    this.warpState = 'charging';
    this.warpTimer = 0;
    this.onArrive = onArrive ?? null;
    return true;
  }

  get warping(): boolean {
    return this.warpState !== 'idle';
  }

  get warpPhase(): string {
    return this.warpState;
  }

  get nebulaColors(): [number, number] {
    const a = this.skyMaterial.uniforms.uNebulaA.value as THREE.Color;
    const b = this.skyMaterial.uniforms.uNebulaB.value as THREE.Color;
    return [a.getHex(), b.getHex()];
  }

  /** 抵达新星系：换一套星云配色、行星与航道 */
  reroll(): void {
    this.seed = Math.random() * 1000;
    this.skyMaterial.uniforms.uSeed.value = this.seed;
    const palettes: Array<[number, number, number, number, number]> = [
      [0x2a4fa8, 0x9a3fb0, 0x1d4f7a, 0x86c8a8, 0x5ea8ff],
      [0xa83f4f, 0xd88a3f, 0x7a3a1d, 0xc8a886, 0xffa85e],
      [0x2aa86f, 0x3f8fd8, 0x1d7a55, 0x86c8c8, 0x5effc8],
      [0x6f2aa8, 0xd83f8f, 0x3a1d7a, 0xa886c8, 0xa85eff],
      [0xa8a02a, 0xd85e3f, 0x7a731d, 0xc8c086, 0xffe45e],
    ];
    const palette = palettes[Math.floor(Math.random() * palettes.length)];
    (this.skyMaterial.uniforms.uNebulaA.value as THREE.Color).setHex(palette[0]);
    (this.skyMaterial.uniforms.uNebulaB.value as THREE.Color).setHex(palette[1]);
    (this.planetMaterial.uniforms.uColorA.value as THREE.Color).setHex(palette[2]);
    (this.planetMaterial.uniforms.uColorB.value as THREE.Color).setHex(palette[3]);
    (this.planetMaterial.uniforms.uAtmosphere.value as THREE.Color).setHex(palette[4]);
    const angle = Math.random() * Math.PI * 2;
    const distance = 1200 + Math.random() * 900;
    this.planet.position.set(
      Math.cos(angle) * distance,
      -200 - Math.random() * 300,
      Math.sin(angle) * distance,
    );
    const sunAngle = Math.random() * Math.PI * 2;
    this.sunLight.position.set(
      Math.cos(sunAngle) * 2000,
      200 + Math.random() * 900,
      Math.sin(sunAngle) * 2000,
    );
    this.sun.position.copy(this.sunLight.position);
    this.sunGlow.position.copy(this.sunLight.position);
    (this.planetMaterial.uniforms.uSun.value as THREE.Vector3)
      .copy(this.sunLight.position)
      .normalize();
    for (const asteroid of this.asteroidData) {
      Object.assign(asteroid, this.spawnAsteroid(true));
    }
    for (const ship of this.traffic) this.resetTraffic(ship.root);
  }

  update(dt: number): void {
    this.elapsed += dt;
    this.skyMaterial.uniforms.uTime.value = this.elapsed;
    this.sky.position.copy(this.camera.position);
    this.sun.position.copy(this.camera.position).add(
      this.sunLight.position.clone().normalize().multiplyScalar(SKY_RADIUS * 0.55),
    );
    this.sunGlow.position.copy(this.sun.position);
    this.planet.rotation.y += dt * 0.01;
    this.moon.rotation.y += dt * 0.02;

    // 小行星漂移与回收
    for (let i = 0; i < this.asteroidData.length; i += 1) {
      const asteroid = this.asteroidData[i];
      asteroid.position.addScaledVector(asteroid.velocity, dt);
      asteroid.rotation.x += asteroid.spin.x * dt;
      asteroid.rotation.y += asteroid.spin.y * dt;
      asteroid.rotation.z += asteroid.spin.z * dt;
      if (asteroid.position.length() > 2600) {
        const replacement = this.spawnAsteroid(false);
        Object.assign(asteroid, replacement);
      }
      this.dummy.position.copy(asteroid.position);
      this.dummy.rotation.copy(asteroid.rotation);
      this.dummy.scale.setScalar(asteroid.scale);
      this.dummy.updateMatrix();
      this.asteroids.setMatrixAt(i, this.dummy.matrix);
    }
    this.asteroids.instanceMatrix.needsUpdate = true;

    for (const ship of this.traffic) {
      ship.root.position.addScaledVector(ship.velocity, dt);
      ship.life += dt;
      if (ship.life > 90 || ship.root.position.length() > 2400) {
        this.resetTraffic(ship.root);
        ship.life = 0;
      }
    }

    // 跃迁流程
    if (this.warpState !== 'idle') {
      this.warpTimer += dt;
      if (this.warpState === 'charging') {
        this.warpAmount = Math.min(0.35, this.warpTimer * 0.35);
        if (this.warpTimer > 1.1) {
          this.warpState = 'jumping';
          this.warpTimer = 0;
        }
      } else if (this.warpState === 'jumping') {
        this.warpAmount = Math.min(1, 0.35 + this.warpTimer * 0.75);
        if (this.warpTimer > 2.4) {
          this.warpState = 'arriving';
          this.warpTimer = 0;
          this.reroll();
          this.onArrive?.();
          this.onArrive = null;
        }
      } else {
        this.warpAmount = Math.max(0, 1 - this.warpTimer * 1.2);
        if (this.warpTimer > 1.1) {
          this.warpState = 'idle';
          this.warpAmount = 0;
        }
      }
      this.warpMaterial.uniforms.uWarp.value = this.warpAmount;
      this.warpMaterial.uniforms.uTime.value = this.elapsed;
    } else if (this.warpAmount > 0) {
      this.warpMaterial.uniforms.uWarp.value = this.warpAmount;
    }
  }

  dispose(): void {
    this.scene.remove(this.ambient);
    this.scene.remove(this.sunLight);
    this.scene.remove(this.sky);
    this.scene.remove(this.planet);
    this.scene.remove(this.moon);
    this.scene.remove(this.sun);
    this.scene.remove(this.sunGlow);
    this.scene.remove(this.asteroids);
    for (const ship of this.traffic) this.scene.remove(ship.root);
    this.camera.remove(this.warpOverlay);
    this.scene.fog = null;
  }
}
