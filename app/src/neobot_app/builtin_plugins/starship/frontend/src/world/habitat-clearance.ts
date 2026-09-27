import * as THREE from 'three';

/** The two foundry chasms are carved into the exterior, rather than sitting on
 * an uninterrupted gold hull sheet. The playable slab and its collision are
 * independent. Bounds stay untouched; only these tiny real-world cavities cut
 * the 74.4 km shell. Clone finishes so interior armour is never clipped. */
export function applyHabitatClearance(hull:THREE.Group):void {
  const finishes=new Map<THREE.Material,THREE.Material>();
  const copy=(source:THREE.Material):THREE.Material=>{
    const existing=finishes.get(source);if(existing)return existing;
    const material=source.clone();
    const previous=source.onBeforeCompile.bind(source);
    material.onBeforeCompile=(shader,renderer)=>{
      previous(shader,renderer);
      shader.vertexShader='varying vec3 vHabitatWorld;\n'+shader.vertexShader;
      shader.vertexShader=shader.vertexShader.replace('#include <begin_vertex>',
        '#include <begin_vertex>\n vHabitatWorld=(modelMatrix*vec4(transformed,1.0)).xyz;');
      shader.fragmentShader='varying vec3 vHabitatWorld;\n'+shader.fragmentShader;
      shader.fragmentShader=shader.fragmentShader.replace('#include <clipping_planes_fragment>',
        '#include <clipping_planes_fragment>\n'+
        'if((abs(vHabitatWorld.x)>31.55 && abs(vHabitatWorld.x)<82.3 && vHabitatWorld.y> -22.0 && vHabitatWorld.y<73.0 && vHabitatWorld.z>13.4 && vHabitatWorld.z<58.6) || (vHabitatWorld.x> -19.0 && vHabitatWorld.x<55.0 && vHabitatWorld.y> -1.1 && vHabitatWorld.y<36.0 && vHabitatWorld.z>57.7 && vHabitatWorld.z<118.7)) discard;');
    };
    material.customProgramCacheKey=()=>source.customProgramCacheKey()+'/foundry-cavity-v1';
    material.userData.habitatClearance=true;finishes.set(source,material);return material;
  };
  hull.traverse(o=>{if(o instanceof THREE.Mesh)o.material=Array.isArray(o.material)?o.material.map(copy):copy(o.material);});
  hull.userData.habitatApertures={minAbsX:31.55,maxAbsX:82.3,minY:-22,maxY:73,minZ:13.4,maxZ:58.6};
}
