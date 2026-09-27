// Owned HDR environment + restrained cinematic output. No downloaded assets.
import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { ShaderPass } from 'three/addons/postprocessing/ShaderPass.js';
import { FXAAShader } from 'three/addons/shaders/FXAAShader.js';
import type { QualityLevel } from '../config';

/** A linear HDR lighting field: dark nebular fill, a warm broad key and long cool
 * luminous apertures. Unlike an ambient light, the PMREM has directional features
 * which visibly move across bevels and distinguish metal from painted plastic.
 * This lights reflections only; the actual space background stays untouched. */
export function createShipRadiance(): THREE.DataTexture {
  const width = 512, height = 256;
  const pixels = new Uint16Array(width * height * 4);
  const key = new THREE.Vector3(-0.55, 0.63, 0.55).normalize();
  const rim = new THREE.Vector3(0.82, 0.25, -0.52).normalize();
  const fill = new THREE.Vector3(0.15, -0.1, 0.98).normalize();
  const aperture = (x: number, y: number, z: number, direction: THREE.Vector3, horizontal: number, vertical: number): number => {
    const facing = x * direction.x + y * direction.y + z * direction.z;
    if (facing <= 0) return 0;
    const length = Math.hypot(direction.x, direction.z);
    const tx = direction.z / length, tz = -direction.x / length;
    const bx = direction.y * tz, by = direction.z * tx - direction.x * tz, bz = -direction.y * tx;
    const u = (x * tx + z * tz) / facing / horizontal;
    const v = (x * bx + y * by + z * bz) / facing / vertical;
    return Math.exp(-Math.pow(Math.abs(u), 6) - Math.pow(Math.abs(v), 6));
  };
  for (let row = 0; row < height; row++) {
    // DataTexture row zero is v=0 (south); equirectUV maps north to v=1.
    const theta = (1 - (row + 0.5) / height) * Math.PI;
    const y = Math.cos(theta), radial = Math.sin(theta);
    for (let col = 0; col < width; col++) {
      const phi = (col + 0.5) / width * Math.PI * 2;
      const x = radial * Math.cos(phi), z = radial * Math.sin(phi);
      const warm = aperture(x, y, z, key, 0.58, 0.32) * 1.55;
      const cool = aperture(x, y, z, rim, 0.16, 0.9) * 1.4;
      const soft = aperture(x, y, z, fill, 1.15, 0.32) * 0.24;
      const sky = 0.018 + Math.max(0, y) * 0.045;
      const horizon = Math.exp(-y * y * 20) * 0.025;
      const index = (row * width + col) * 4;
      pixels[index] = THREE.DataUtils.toHalfFloat(sky * 0.65 + horizon + warm + cool * 0.44 + soft * 0.56);
      pixels[index + 1] = THREE.DataUtils.toHalfFloat(sky * 0.9 + horizon * 0.8 + warm * 0.91 + cool * 0.72 + soft * 0.78);
      pixels[index + 2] = THREE.DataUtils.toHalfFloat(sky * 1.3 + horizon * 0.7 + warm * 0.74 + cool + soft);
      pixels[index + 3] = THREE.DataUtils.toHalfFloat(1);
    }
  }
  const texture = new THREE.DataTexture(pixels, width, height, THREE.RGBAFormat, THREE.HalfFloatType);
  texture.name = 'ark-authored-hdr-radiance';
  texture.mapping = THREE.EquirectangularReflectionMapping;
  texture.colorSpace = THREE.LinearSRGBColorSpace;
  texture.minFilter = THREE.LinearFilter;
  texture.magFilter = THREE.LinearFilter;
  texture.generateMipmaps = false;
  texture.needsUpdate = true;
  return texture;
}

/** Integration:
 *   const output = new ShipRendering(renderer, scene, camera, qualityLevel);
 *   output.resize(cssWidth, cssHeight, renderer.getPixelRatio());
 *   output.updateQuality('high'); output.render(dt);
 *   output.dispose(); // BEFORE renderer.dispose()
 *
 * The caller owns renderer size/pixel ratio, camera projection and its main loop.
 * No timer, event listener or render loop is installed. Low quality uses direct
 * ACES output; medium/high use linear HDR -> bloom -> ACES/sRGB exactly once.
 * Standard log-depth chunks are untouched, including for far=2e6 space scenes.
 */
export class ShipRendering {
  private readonly environment: THREE.WebGLRenderTarget;
  private readonly previousEnvironment: THREE.Texture | null;
  private readonly previousEnvironmentIntensity: number;
  private readonly previousEnvironmentRotation: THREE.Euler;
  private readonly previousOutputColorSpace: THREE.ColorSpace;
  private readonly previousToneMapping: THREE.ToneMapping;
  private readonly previousExposure: number;
  private composer: EffectComposer | null = null;
  private bloom: UnrealBloomPass | null = null;
  private fxaa: ShaderPass | null = null;
  private quality: QualityLevel;
  private width = 1;
  private height = 1;
  private pixelRatio = 1;
  private disposed = false;

  constructor(
    private readonly renderer: THREE.WebGLRenderer,
    private readonly scene: THREE.Scene,
    private readonly camera: THREE.Camera,
    quality: QualityLevel = 'medium',
  ) {
    this.quality = quality;
    this.previousEnvironment = scene.environment;
    this.previousEnvironmentIntensity = scene.environmentIntensity;
    this.previousEnvironmentRotation = scene.environmentRotation.clone();
    this.previousOutputColorSpace = renderer.outputColorSpace;
    this.previousToneMapping = renderer.toneMapping;
    this.previousExposure = renderer.toneMappingExposure;
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 0.95;
    const source = createShipRadiance();
    const generator = new THREE.PMREMGenerator(renderer);
    try {
      generator.compileEquirectangularShader();
      this.environment = generator.fromEquirectangular(source);
    } finally {
      source.dispose();
      generator.dispose();
    }
    this.environment.texture.name = 'ark-specular-pmrem';
    scene.environment = this.environment.texture;
    scene.environmentIntensity = 0.72;
    scene.environmentRotation.set(0, 0.35, 0);
    const size = renderer.getSize(new THREE.Vector2());
    this.width = Math.max(1, size.x);
    this.height = Math.max(1, size.y);
    this.pixelRatio = renderer.getPixelRatio();
    this.updateQuality(quality);
  }

  /** Does not change gameplay preset, pixel ratio or existing light/shadow setup. */
  updateQuality(quality: QualityLevel): void {
    if (this.disposed) return;
    const changed = quality !== this.quality;
    this.quality = quality;
    if (quality === 'low') {
      this.disposeComposer();
      return;
    }
    if (!this.composer || changed) {
      this.disposeComposer();
      const samples = Math.min(this.renderer.capabilities.maxSamples, quality === 'high' ? 4 : 2);
      const target = new THREE.WebGLRenderTarget(this.width * this.pixelRatio, this.height * this.pixelRatio, {
        type: THREE.HalfFloatType, format: THREE.RGBAFormat,
        minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter,
        depthBuffer: true, stencilBuffer: false, samples,
      });
      target.texture.name = 'ark-linear-hdr-output';
      this.composer = new EffectComposer(this.renderer, target);
      this.composer.addPass(new RenderPass(this.scene, this.camera));
      this.bloom = new UnrealBloomPass(new THREE.Vector2(this.width, this.height),
        quality === 'high' ? 0.30 : 0.24, 0.44, 1.1);
      this.composer.addPass(this.bloom);
      this.composer.addPass(new OutputPass());
      // MSAA resolves geometry silhouettes before bloom. On devices without it,
      // FXAA runs in display space after OutputPass, where its luma test is valid.
      if (samples < 2) {
        this.fxaa = new ShaderPass(FXAAShader);
        this.composer.addPass(this.fxaa);
      }
      this.resize(this.width, this.height, this.pixelRatio);
    }
  }

  /** Dimensions are CSS pixels. Call after renderer.setSize / setPixelRatio. */
  resize(width: number, height: number, pixelRatio = this.renderer.getPixelRatio()): void {
    if (this.disposed) return;
    this.width = Math.max(1, Math.floor(width));
    this.height = Math.max(1, Math.floor(height));
    this.pixelRatio = Math.max(0.25, pixelRatio);
    this.composer?.setPixelRatio(this.pixelRatio);
    this.composer?.setSize(this.width, this.height);
    this.fxaa?.uniforms.resolution.value.set(1 / (this.width * this.pixelRatio), 1 / (this.height * this.pixelRatio));
  }

  render(dt = 0): void {
    if (this.disposed) return;
    if (this.composer) this.composer.render(Math.min(Math.max(dt, 0), 0.1));
    else this.renderer.render(this.scene, this.camera);
  }

  private disposeComposer(): void {
    if (!this.composer) return;
    // Composer owns its two targets, but not user-added pass resources.
    // three r169 UnrealBloomPass.dispose omits its high-pass filter material.
    this.bloom?.materialHighPassFilter.dispose();
    for (const pass of this.composer.passes) pass.dispose();
    this.composer.dispose();
    this.composer = null;
    this.bloom = null;
    this.fxaa = null;
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.disposeComposer();
    if (this.scene.environment === this.environment.texture) {
      this.scene.environment = this.previousEnvironment;
      this.scene.environmentIntensity = this.previousEnvironmentIntensity;
      this.scene.environmentRotation.copy(this.previousEnvironmentRotation);
    }
    this.environment.dispose();
    this.renderer.outputColorSpace = this.previousOutputColorSpace;
    this.renderer.toneMapping = this.previousToneMapping;
    this.renderer.toneMappingExposure = this.previousExposure;
  }
}
