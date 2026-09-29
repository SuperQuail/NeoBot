import * as THREE from 'three';
import { buildFighterAsset, type FighterAsset, type FighterKind } from './protoss-fighters';

export interface GoldenFleet {
  group:THREE.Group;
  update(dt:number):void;
  dispose():void;
}
interface Patrol { curve:THREE.CatmullRomCurve3; period:number; altitude:number; safety:number }
interface Flight { kind:FighterKind; index:number; patrol:Patrol; phase:number; length:number; altitudeOffset:number }
const TAU=Math.PI*2;
const wrap=(v:number)=>((v%1)+1)%1;

/** Pure periodic pose evaluator, exported for numerical closure tests.
 * No quaternion smoothing/history: orientation is continuous at the wrap as well
 * as after a frame-rate change. The model's -Z follows the path tangent. */
export function samplePatrolPose(curve:THREE.CatmullRomCurve3,phase:number,position:THREE.Vector3,orientation:THREE.Quaternion):void {
  const u=wrap(phase),epsilon=.0004;
  curve.getPointAt(u,position);
  // A central *wrapped* derivative is identical on both sides of the seam;
  // Curve.getTangentAt(0/1) uses one-sided derivatives at that boundary.
  const before=curve.getPointAt(wrap(u-epsilon)),after=curve.getPointAt(wrap(u+epsilon));
  const tangent=after.sub(before).normalize();
  const behind=curve.getPointAt(wrap(u-epsilon*2)),ahead=curve.getPointAt(wrap(u+epsilon*2));
  const t0=position.clone().sub(behind).normalize(),t1=ahead.sub(position).normalize();
  const turn=t0.x*t1.z-t0.z*t1.x;
  const right=tangent.clone().cross(new THREE.Vector3(0,1,0)).normalize();
  const back=tangent.clone().negate(),up=back.clone().cross(right).normalize();
  orientation.setFromRotationMatrix(new THREE.Matrix4().makeBasis(right,up,back));
  // A gentle outward bias avoids aligning the wings edge-on with the bridge.
  const bank=.12+THREE.MathUtils.clamp(turn*22,-.17,.17)+Math.sin(u*TAU)*.025;
  orientation.multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0,0,1),bank));
}

/** Returns ship-parent coordinates. Pass the already scaled/translated hull,
 * then add this separate group to ship.group AFTER measuring physical hull bounds.
 * There is deliberately no camera-follow teleport, trail texture or per-frame raycast. */
export function buildGoldenFleet(hull:THREE.Object3D):GoldenFleet {
  const group=new THREE.Group();group.name='golden-fleet-patrols';
  hull.updateWorldMatrix(true,true);
  // Work in the hull parent's coordinate system even if ship.group is transformed.
  const parentWorld=hull.parent?.matrixWorld.clone()??new THREE.Matrix4();
  const inverseParent=parentWorld.clone().invert();
  const box=new THREE.Box3().setFromObject(hull).applyMatrix4(inverseParent);
  const roof=box.isEmpty()?100:box.max.y;
  const ray=new THREE.Raycaster();ray.layers.enableAll();
  const down=new THREE.Vector3(0,-1,0).transformDirection(parentWorld);
  const hits:THREE.Intersection[]=[];
  let probeCount=0;
  const sampleRoof=(x:number,z:number):number=>{
    probeCount++;ray.set(new THREE.Vector3(x,roof+2000,z).applyMatrix4(parentWorld),down);
    hits.length=0;ray.intersectObject(hull,true,hits);
    return hits.length?hits[0].point.clone().applyMatrix4(inverseParent).y:-Infinity;
  };
  const patrol=(rx:number,rz:number,cz:number,minAltitude:number,safety:number,period:number,probes:number):Patrol=>{
    const points:THREE.Vector3[]=[];
    for(let i=0;i<12;i++){const angle=i/12*TAU;points.push(new THREE.Vector3(Math.sin(angle)*rx,0,cz+Math.cos(angle)*rz));}
    const curve=new THREE.CatmullRomCurve3(points,true,'centripetal');curve.arcLengthDivisions=768;
    // Deliberately keep the *entire* loop above its sampled roof envelope, not
    // independently snapped waypoint heights (which can dip inside the hull).
    let maxRoof=-Infinity;
    for(let i=0;i<probes;i++){
      const p=curve.getPointAt(i/probes);maxRoof=Math.max(maxRoof,sampleRoof(p.x,p.z));
    }
    // Additional samples on the nearest approach cover both sides of the wing.
    for(const x of [-70,70])maxRoof=Math.max(maxRoof,sampleRoof(x,cz+rz));
    const altitude=Math.max(minAltitude,Number.isFinite(maxRoof)?maxRoof+safety:minAltitude);
    for(let i=0;i<points.length;i++)points[i].y=altitude+Math.sin(i/points.length*TAU*2)*12;
    curve.updateArcLengths();
    return {curve,period,altitude,safety};
  };
  // At closest approach: 400m ahead, 58–70m craft (not pinprick particles).
  // Two three-ship sections alternate in the main forward view, all z <= -400.
  const near=patrol(1050,1100,-1500,105,130,420,24);
  const far=patrol(6500,2700,-8500,700,520,1050,16);
  let envMap:THREE.Texture|null=null;
  hull.traverse(o=>{if(envMap||!(o instanceof THREE.Mesh))return;const ms=Array.isArray(o.material)?o.material:[o.material];for(const m of ms)if(m instanceof THREE.MeshStandardMaterial&&m.envMap){envMap=m.envMap;break;}});
  const assets=new Map<FighterKind,FighterAsset>();
  const batches=new Map<FighterKind,THREE.InstancedMesh[]>();
  for(const [kind,count] of [['phoenix',6],['void-ray',2]] as const) {
    const asset=buildFighterAsset(kind,envMap);assets.set(kind,asset);
    const meshes=asset.parts.map(p=>{
      const mesh=new THREE.InstancedMesh(p.geometry,p.material,count);mesh.name=kind+'-'+p.finish;
      mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);mesh.layers.set(1);
      // Only ten batched draws. Avoid stale per-instance bounds as the ships move.
      mesh.frustumCulled=false;mesh.castShadow=false;mesh.receiveShadow=false;group.add(mesh);return mesh;
    });batches.set(kind,meshes);
  }
  const flights:Flight[]=[];
  for(let i=0;i<6;i++)flights.push({kind:'phoenix',index:i,patrol:near,phase:i<3?i*.023:.5+(i-3)*.023,length:[68,60,64,70,58,64][i],altitudeOffset:(i%3)*7});
  for(let i=0;i<2;i++)flights.push({kind:'void-ray',index:i,patrol:far,phase:.10+i*.48,length:310+i*45,altitudeOffset:i*140});
  const position=new THREE.Vector3(),orientation=new THREE.Quaternion(),scale=new THREE.Vector3(),matrix=new THREE.Matrix4();
  let elapsed=0,disposed=false;
  const update=(dt:number)=>{
    if(disposed)return;
    // Normal frames are unchanged; debugger/tab gaps pause rather than skip a patrol.
    if(Number.isFinite(dt)&&dt>0)elapsed=(elapsed+Math.min(dt,.1))%4200;
    for(const f of flights) {
      samplePatrolPose(f.patrol.curve,elapsed/f.patrol.period+f.phase,position,orientation);
      position.y+=f.altitudeOffset;scale.setScalar(f.length);matrix.compose(position,orientation,scale);
      for(const mesh of batches.get(f.kind)!)mesh.setMatrixAt(f.index,matrix);
    }
    for(const meshes of batches.values())for(const mesh of meshes)mesh.instanceMatrix.needsUpdate=true;
  };
  group.userData.patrols=[near,far];
  group.userData.flights=flights.map(f=>({kind:f.kind,length:f.length,phase:f.phase,altitudeOffset:f.altitudeOffset}));
  group.userData.initializationRaycasts=probeCount;
  group.userData.forwardKeepoutMetres=400;
  group.userData.coordinateSpace='hull-parent';
  group.userData.referenceTypes=['SC2 Phoenix','SC2 Void Ray'];
  update(0);
  return {group,update,dispose(){
    if(disposed)return;disposed=true;group.removeFromParent();
    for(const meshes of batches.values())for(const mesh of meshes)mesh.dispose();
    for(const asset of assets.values())asset.dispose();group.clear();
  }};
}
