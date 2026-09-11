// minigames/turret.ts —— 舱外炮塔：击碎接近的小行星，别让舰体受伤。

import * as THREE from 'three';
import { registerMinigame, type MinigameContext, type MinigameModule } from './api';
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';

interface Asteroid {
  mesh: THREE.Mesh;
  velocity: THREE.Vector3;
  radius: number;
  hp: number;
  alive: boolean;
}

interface Bolt {
  mesh: THREE.Mesh;
  velocity: Vector3Like;
  life: number;
}

interface Vector3Like {
  x: number;
  y: number;
  z: number;
}

interface Burst {
  points: THREE.Points;
  life: number;
  velocities: Float32Array;
}

const WAVE_INTERVAL = 14;
const MAX_HP = 200;
const HIT_DAMAGE = 9;
/** 舰体包围盒（小行星撞到这里才算命中舰体） */
const HULL = { minX: -78, maxX: 78, minY: -4, maxY: 15, minZ: -24, maxZ: 24 };

class TurretGame implements MinigameModule {
  readonly id = 'turret';
  readonly name = '舱外炮塔';
  readonly description = '小行星群正在接近，用舷侧炮塔把它们打成碎片。';
  readonly icon = 'target';
  readonly mode = 'world' as const;

  private ctx: MinigameContext | null = null;
  private group: THREE.Group | null = null;
  private asteroids: Asteroid[] = [];
  private bolts: Bolt[] = [];
  private bursts: Burst[] = [];
  private yaw = 0;
  private pitch = 0;
  private elapsed = 0;
  private waveTimer = 0;
  private wave = 1;
  private score = 0;
  private hull = MAX_HP;
  private destroyed = 0;
  private fireCooldown = 0;
  private ended = false;

  viewpoint(): { position: THREE.Vector3; yaw: number; pitch: number } {
    // 观景廊外侧的炮塔位，朝向舰体右舷
    return {
      position: new THREE.Vector3(46, 12.4, 26),
      yaw: Math.PI,
      pitch: -0.05,
    };
  }

  start(ctx: MinigameContext): void {
    this.ctx = ctx;
    this.group = new THREE.Group();
    this.group.name = 'minigame-turret';
    ctx.scene.add(this.group);
    this.asteroids = [];
    this.bolts = [];
    this.bursts = [];
    this.elapsed = 0;
    this.waveTimer = 0;
    this.wave = 1;
    this.score = 0;
    this.hull = MAX_HP;
    this.destroyed = 0;
    this.ended = false;
    this.yaw = Math.PI;
    this.pitch = -0.05;
    this.spawnWave(4);
    ctx.setHud({
      title: '舱外炮塔',
      score: '得分 0',
      extra: '舰体完整度 100%',
      hint: '移动鼠标瞄准 · 左键开火 · Esc/E 退出',
    });
  }

  private spawnWave(count: number): void {
    const ctx = this.ctx;
    if (!ctx || !this.group) return;
    for (let index = 0; index < count; index += 1) {
      const radius = 4 + ctx.rng() * 10;
      const geometry = new THREE.IcosahedronGeometry(radius, 1);
      const position = geometry.attributes.position as THREE.BufferAttribute;
      for (let vertex = 0; vertex < position.count; vertex += 1) {
        const scale = 0.75 + ctx.rng() * 0.5;
        position.setXYZ(vertex, position.getX(vertex) * scale, position.getY(vertex) * scale, position.getZ(vertex) * scale);
      }
      geometry.computeVertexNormals();
      const mesh = new THREE.Mesh(
        geometry,
        new THREE.MeshStandardMaterial({ color: 0x8c8578, roughness: 0.95, flatShading: true }),
      );
      const angle = (ctx.rng() - 0.5) * 1.2 + Math.PI;
      const distance = 620 + ctx.rng() * 320;
      mesh.position.set(
        Math.cos(angle) * distance * 0.35,
        (ctx.rng() - 0.5) * 160,
        Math.sin(angle) * distance,
      );
      const speed = 24 + this.wave * 3 + ctx.rng() * 14;
      const target = new THREE.Vector3(
        (ctx.rng() - 0.5) * 60,
        (ctx.rng() - 0.5) * 10,
        (ctx.rng() - 0.5) * 30,
      );
      const velocity = target.sub(mesh.position).normalize().multiplyScalar(speed);
      this.group.add(mesh);
      this.asteroids.push({
        mesh,
        velocity,
        radius,
        hp: Math.max(1, Math.round(radius / 4)),
        alive: true,
      });
    }
  }

  update(dt: number, ctx: MinigameContext): void {
    if (this.ended) return;
    this.elapsed += dt;
    this.waveTimer += dt;
    this.fireCooldown = Math.max(0, this.fireCooldown - dt);
    if (this.waveTimer > WAVE_INTERVAL) {
      this.waveTimer = 0;
      this.wave += 1;
      ctx.audio.alarm();
      ctx.toast('第 ' + this.wave + ' 波小行星接近！', 'warn');
      this.spawnWave(2 + this.wave);
    }

    const camera = ctx.camera;
    camera.position.set(46, 12.4, 26);
    camera.rotation.set(this.pitch, this.yaw, 0, 'YXZ');

    for (const asteroid of this.asteroids) {
      if (!asteroid.alive) continue;
      asteroid.mesh.position.addScaledVector(asteroid.velocity, dt);
      asteroid.mesh.rotation.x += dt * 0.4;
      asteroid.mesh.rotation.y += dt * 0.3;
      const p = asteroid.mesh.position;
      const insideHull =
        p.x > HULL.minX - asteroid.radius &&
        p.x < HULL.maxX + asteroid.radius &&
        p.y > HULL.minY - asteroid.radius &&
        p.y < HULL.maxY + asteroid.radius &&
        p.z > HULL.minZ - asteroid.radius &&
        p.z < HULL.maxZ + asteroid.radius;
      if (insideHull) {
        asteroid.alive = false;
        this.group?.remove(asteroid.mesh);
        this.hull = Math.max(0, this.hull - HIT_DAMAGE);
        ctx.audio.explosion();
        ctx.toast('舰体被击中！完整度 ' + Math.round((this.hull / MAX_HP) * 100) + '%', 'error');
        if (this.hull <= 0) this.finish(false);
      }
    }

    for (const bolt of this.bolts) {
      bolt.mesh.position.x += bolt.velocity.x * dt;
      bolt.mesh.position.y += bolt.velocity.y * dt;
      bolt.mesh.position.z += bolt.velocity.z * dt;
      bolt.life -= dt;
      for (const asteroid of this.asteroids) {
        if (!asteroid.alive) continue;
        if (bolt.mesh.position.distanceTo(asteroid.mesh.position) < asteroid.radius + 2.4) {
          asteroid.hp -= 1;
          this.spawnBurst(asteroid.mesh.position, asteroid.radius);
          if (asteroid.hp <= 0) {
            asteroid.alive = false;
            this.group?.remove(asteroid.mesh);
            this.destroyed += 1;
            this.score += Math.round(asteroid.radius * 8);
            ctx.audio.explosion();
          } else {
            ctx.audio.laser();
          }
          bolt.life = 0;
          break;
        }
      }
      if (bolt.life <= 0) {
        this.group?.remove(bolt.mesh);
      }
    }
    this.bolts = this.bolts.filter((bolt) => bolt.life > 0);

    for (const burst of this.bursts) {
      burst.life -= dt;
      const positions = burst.points.geometry.attributes.position as THREE.BufferAttribute;
      for (let index = 0; index < positions.count; index += 1) {
        positions.setXYZ(
          index,
          positions.getX(index) + burst.velocities[index * 3] * dt,
          positions.getY(index) + burst.velocities[index * 3 + 1] * dt,
          positions.getZ(index) + burst.velocities[index * 3 + 2] * dt,
        );
      }
      positions.needsUpdate = true;
      (burst.points.material as THREE.PointsMaterial).opacity = Math.max(0, burst.life / 0.8);
      if (burst.life <= 0) this.group?.remove(burst.points);
    }
    this.bursts = this.bursts.filter((burst) => burst.life > 0);

    ctx.setHud({
      title: '舱外炮塔 · 第 ' + this.wave + ' 波',
      score: '得分 ' + this.score + ' · 击毁 ' + this.destroyed,
      extra: '舰体完整度 ' + Math.round((this.hull / MAX_HP) * 100) + '%',
      hint: '左键开火 · Esc/E 退出',
    });

    if (this.elapsed > 180) this.finish(true);
  }

  private spawnBurst(position: THREE.Vector3, radius: number): void {
    const ctx = this.ctx;
    if (!ctx || !this.group) return;
    const count = 28;
    const positions = new Float32Array(count * 3);
    const velocities = new Float32Array(count * 3);
    for (let index = 0; index < count; index += 1) {
      positions[index * 3] = position.x;
      positions[index * 3 + 1] = position.y;
      positions[index * 3 + 2] = position.z;
      const speed = 14 + ctx.rng() * 22;
      velocities[index * 3] = (ctx.rng() - 0.5) * speed;
      velocities[index * 3 + 1] = (ctx.rng() - 0.5) * speed;
      velocities[index * 3 + 2] = (ctx.rng() - 0.5) * speed;
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    const points = new THREE.Points(
      geometry,
      new THREE.PointsMaterial({
        color: 0xffc890,
        size: Math.max(1.4, radius * 0.12),
        transparent: true,
        opacity: 1,
        depthWrite: false,
      }),
    );
    this.group.add(points);
    this.bursts.push({ points, life: 0.8, velocities });
  }

  onPointerMove(dx: number, dy: number): void {
    this.yaw -= dx * 0.0022;
    this.pitch = Math.max(-1.2, Math.min(1.2, this.pitch - dy * 0.0022));
  }

  onPointerDown(): void {
    const ctx = this.ctx;
    if (!ctx || !this.group || this.fireCooldown > 0) return;
    this.fireCooldown = 0.18;
    const direction = new THREE.Vector3();
    ctx.camera.getWorldDirection(direction);
    const mesh = new THREE.Mesh(
      new THREE.CylinderGeometry(0.35, 0.35, 6, 8),
      new THREE.MeshBasicMaterial({ color: 0x8ff0ff }),
    );
    mesh.position.copy(ctx.camera.position).addScaledVector(direction, 6);
    mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction);
    this.group.add(mesh);
    this.bolts.push({
      mesh,
      velocity: { x: direction.x * 420, y: direction.y * 420, z: direction.z * 420 },
      life: 2.4,
    });
    ctx.audio.laser();
  }

  private finish(completed: boolean): void {
    const ctx = this.ctx;
    if (!ctx || this.ended) return;
    this.ended = true;
    const bonus = completed ? Math.round(this.hull * 20) : 0;
    const total = this.score + bonus;
    void ctx
      .submitScore('turret', total, Math.round(this.elapsed * 1000), '击毁 ' + this.destroyed + ' 颗')
      .then((result) => {
        ctx.finish({
          title: completed ? '炮塔演练完成' : '舰体受损，演练终止',
          lines: [
            '击毁小行星：' + this.destroyed + ' 颗',
            completed ? '完整度奖励：+' + bonus : '完整度：' + Math.round(this.hull) + '%',
            result.ok ? '本次得分 ' + total + '，历史最佳 ' + (result.best ?? total) + '，排名第 ' + (result.rank ?? 1) : '成绩未能保存：' + (result.error || '未知原因'),
          ],
          score: total,
          canRetry: true,
        });
      });
  }

  dispose(ctx: MinigameContext): void {
    if (this.group) {
      ctx.scene.remove(this.group);
      this.group.traverse((object) => {
        const mesh = object as THREE.Mesh;
        if (mesh.geometry) mesh.geometry.dispose();
      });
    }
    this.group = null;
    this.asteroids = [];
    this.bolts = [];
    this.bursts = [];
    this.ctx = null;
  }
}

registerMinigame(new TurretGame());
void mergeGeometries;
