import * as THREE from 'three';
import type { Point } from './geometry';
import type { ShipMaterials } from './materials';
import { UnitSculpt, type Section } from './unit-sculpt';

/** Original-reference reconstruction (SC Field Manual / SC2 unit renders).
 * Feet are on Y=0, face is -Z. No exhibit geometry, shared-material mutations,
 * downloaded assets, spherical shoulder primitives or hanging heraldic shields. */
export function buildStalker(materials: ShipMaterials): THREE.Group {
  const w=new UnitSculpt();
  const armor=w.metal(materials.hull,0x64516f,'stalker-platinum-violet');
  const edge=w.metal(materials.wallAccent,0xb4a6bf,'stalker-cut-platinum');
  const inset=w.metal(materials.wall,0x392f4e,'stalker-recessed-ceramic');
  const dark=w.metal(materials.ceiling,0x131622,'stalker-joint-obsidian');
  const glass=w.metal(materials.wall,0x123a72,'stalker-optical-glass');
  glass.emissive.setHex(0x1257b9);glass.emissiveIntensity=.55;glass.roughness=.16;
  const glow=materials.trim;

  // A forward-hunched volumetric helmet: deep occiput, full temples, hooked brow.
  // Side optics occupy only a small part of each tall armoured cowl.
  const skull:Section[]=[
    [0,2.65,.16,.34,.39],[0,2.98,.10,.65,.61],[0,3.45,-.03,.89,.78],
    [0,4.03,-.26,1.05,.87],[0,4.62,-.05,.84,.74],[0,5.10,.30,.48,.48],
    [0,5.44,.59,.18,.20],[0,5.64,.73,.018,.045],
  ];
  w.shell(skull,dark);
  // Continuous curved side cowls with thick returned lower edges, not discs.
  for(const s of [-1,1]) {
    const m=new THREE.Matrix4().makeTranslation(s*.12,0,0);
    const lo=s===1?.26:Math.PI+.26,hi=s===1?Math.PI-.25:Math.PI*2-.25;
    w.shell(skull,armor,m,lo,hi,.15,56,.79);
    const side:Section[]=[
      [s*.65,3.04,.03,.10,.27],[s*.91,3.60,-.13,.24,.55],
      [s*1.01,4.22,-.12,.20,.53],[s*.71,4.85,.25,.16,.44],
      [s*.39,5.29,.54,.085,.21],[s*.11,5.57,.70,.018,.05],
    ];
    // Raised rear return gives the side panel an asymmetric sculpted perimeter.
    w.shell(side,armor);
    w.line([[s*.68,3.10,-.20],[s*1.12,3.82,-.54],[s*1.12,4.40,-.60],
      [s*.57,5.03,-.10],[s*.11,5.60,.68]],.035,edge);
    w.line([[s*.65,3.11,.36],[s*1.10,3.90,.58],[s*.81,4.65,.73],[s*.33,5.27,.79]],.026,edge);
    w.optic([s*1.185,4.20,-.36],[s*.96,.06,-.29],.245,.39,edge,dark,glass,glow);
    // Swept inset above the optical window follows the taper of the cowl.
    const incision=new THREE.Shape();incision.moveTo(-.12,-.12);incision.lineTo(-.14,.24);
    incision.quadraticCurveTo(-.08,.42,.035,.58);incision.lineTo(.12,.15);incision.lineTo(.07,-.16);incision.closePath();
    w.plate(incision,inset,w.frame([s*1.02,4.63,-.03],[s*.94,.28,-.17]),.025);
    for(let j=0;j<3;j++) w.line([[s*1.245,3.60+j*.13,-.10],[s*1.25,3.62+j*.13,.04]],.018,dark);
    // Small lower blink ports, separated from the main cowl window.
    w.optic([s*.73,3.15,-.56],[s*.65,-.1,-.76],.115,.19,armor,dark,glass,glow);
    for(let i=0;i<3;i++) {
      const y=3.68+i*.22;
      w.line([[s*.42,y,-.86],[s*.63,y+.055,-.86],[s*.78,y+.12,-.77]],.035,dark);
      w.line([[s*.43,y+.045,-.868],[s*.62,y+.098,-.856]],.012,edge);
    }
    // Cheek blades wrap back around the face, rather than conceal it.
    w.shell([[s*.28,3.03,-.87,.05,.15],[s*.49,3.30,-1.00,.16,.22],
      [s*.53,3.65,-1.03,.19,.22],[s*.41,3.95,-.97,.12,.18]],armor,new THREE.Matrix4(),1.65,4.63,.09,40,.68);
    w.line([[s*.20,3.11,-1.03],[s*.45,3.35,-1.21],[s*.49,3.67,-1.22]],.022,edge);
  }
  // Thick central forehead sweeps down and forward to a predatory nose.
  w.shell([[0,3.66,-1.22,.14,.17],[0,3.90,-1.12,.40,.29],
    [0,4.25,-1.00,.40,.31],[0,4.65,-.63,.28,.25],
    [0,5.02,-.15,.19,.20],[0,5.38,.39,.075,.13],[0,5.64,.74,.012,.03]],edge,new THREE.Matrix4(),0,Math.PI*2,.08,40,.73);
  w.shell([[0,3.92,-1.37,.035,.025],[0,4.28,-1.19,.15,.05],
    [0,4.67,-.86,.10,.05],[0,5.11,-.18,.05,.04],[0,5.51,.50,.008,.02]],inset);
  // Readable inset face, eyes and split muzzle beneath the hooked brow.
  w.shell([[0,3.07,-1.13,.12,.11],[0,3.24,-1.28,.24,.20],
    [0,3.56,-1.26,.29,.17],[0,3.75,-1.17,.20,.12]],dark);
  for(const s of [-1,1]) {
    w.line([[s*.065,3.59,-1.438],[s*.15,3.63,-1.44],[s*.25,3.61,-1.39]],.024,glow);
    w.shell([[s*.12,3.16,-1.30,.035,.08],[s*.19,3.34,-1.42,.10,.14],
      [s*.23,3.51,-1.34,.095,.10]],armor);
    w.line([[s*.08,3.21,-1.44],[s*.13,3.31,-1.57],[s*.20,3.44,-1.48]],.018,edge);
  }
  w.optic([0,3.27,-1.57],[0,-.06,-1],.105,.075,edge,dark,glass,glow);
  // Two restrained crown crystals sit in sockets; no towering antenna silhouette.
  for(const s of [-1,1]) {
    w.shell([[s*.39,5.05,.13,.14,.20],[s*.40,5.23,.09,.11,.14],
      [s*.36,5.42,-.01,.015,.03]],glass);
  }
  // Compact exposed undercarriage, ribs visible between the four separated hips.
  w.shell([[0,2.30,.12,.31,.32],[0,2.58,.12,.60,.55],[0,2.84,.12,.70,.62],
    [0,3.06,.13,.53,.47]],dark);
  for(let i=0;i<4;i++) w.line([[-.47,2.43+i*.13,-.25],[0,2.39+i*.13,-.49],[.47,2.43+i*.13,-.25]],.027,inset);

  for(const sx of [-1,1]) for(const sz of [-1,1]) {
    const hip:Point=[sx*.66,2.81,sz*.45], elbow:Point=[sx*1.47,2.38,sz*1.25];
    const knee:Point=[sx*2.10,2.23,sz*1.94], ankle:Point=[sx*2.61,.48,sz*2.58];
    const toe:Point=[sx*2.84,.025,sz*2.92],normal:Point=[sx*.68,.10,sz*.73];
    w.joint(hip,normal,.25,edge,dark,inset);
    // Open, doubled upper limb with a genuine tendon gap.
    for(const dy of [-.12,.12]) {
      const h:Point=[hip[0],hip[1]+dy,hip[2]], e:Point=[elbow[0],elbow[1]+dy,elbow[2]];
      w.limb(h,e,normal,[[0,.08,.07,0],[.23,.12,.10,.03],[.8,.09,.075,0],[1,.07,.07,0]],dy>0?armor:dark);
    }
    w.joint(elbow,normal,.19,armor,dark,inset);
    w.limb(elbow,knee,normal,[[0,.10,.07,0],[.25,.20,.085,.02],[.72,.18,.085,.02],[1,.11,.065,0]],armor,true);
    w.line([[hip[0],hip[1]-.15,hip[2]],[sx*1.35,2.06,sz*1.15],[knee[0],knee[1]-.13,knee[2]]],.043,dark);
    w.joint(knee,normal,.27,edge,dark,glass);
    // The knee crest is short, thick and pierced, not a giant flat shield.
    const crest=new THREE.Shape();crest.moveTo(-.17,-.12);crest.quadraticCurveTo(-.25,.28,-.17,.70);
    crest.lineTo(.04,.95);crest.quadraticCurveTo(.07,.40,.22,.03);crest.lineTo(.15,-.14);crest.closePath();
    const hole=new THREE.Path();hole.moveTo(-.075,.25);hole.lineTo(-.10,.58);hole.lineTo(.006,.70);hole.lineTo(.032,.29);hole.closePath();crest.holes.push(hole);
    w.plate(crest,armor,w.frame([sx*1.99,2.33,sz*1.82],normal),.13);
    // Narrow lenticular shin with separate upper cuff, exposed rear piston and toe.
    w.limb(ankle,knee,normal,[[0,.060,.06,0],[.26,.12,.08,.045],[.60,.21,.10,.075],[.88,.23,.095,.045],[1,.15,.08,0]],armor,true);
    const cuff:Point=[sx*2.22,1.88,sz*2.08];
    w.limb(cuff,knee,normal,[[0,.14,.08,.09],[.5,.24,.11,.09],[1,.18,.09,.02]],edge,true);
    w.line([[sx*2.17,2.0,sz*1.87],[sx*2.35,1.24,sz*2.15],[sx*2.53,.55,sz*2.45]],.045,dark);
    w.line([[sx*2.17,2.02,sz*2.08],[sx*2.42,1.30,sz*2.43],[sx*2.66,.53,sz*2.70]],.017,inset);
    // Recessed longitudinal channels break the blade into machined planes.
    w.limb(ankle,knee,normal,[[.15,.018,.01,.14],[.42,.026,.014,.18],[.70,.03,.012,.20],[.88,.012,.008,.17]],inset);
    w.joint(ankle,normal,.12,armor,dark,inset);
    w.limb(toe,ankle,normal,[[0,.009,.013,0],[.20,.055,.03,.01],[.7,.10,.07,.035],[1,.07,.055,0]],edge,true);
  }
  return w.finish('stalker',5.6,6.4,6.4);
}

export function buildDragoon(materials: ShipMaterials): THREE.Group {
  const w=new UnitSculpt();
  const gold=w.metal(materials.hull,0xb4a16b,'dragoon-burnished-gold');
  const edge=w.metal(materials.wallAccent,0xe1cb91,'dragoon-cut-electrum');
  const bronze=w.metal(materials.prop,0x786345,'dragoon-recess-bronze');
  const dark=w.metal(materials.ceiling,0x161b23,'dragoon-undercut-obsidian');
  const blue=w.metal(materials.wall,0x263b59,'dragoon-cobalt-enamel');
  const glass=w.metal(materials.wall,0x145495,'dragoon-optical-glass');
  glass.emissive.setHex(0x127ec9);glass.emissiveIntensity=.35;glass.roughness=.16;
  const glow=materials.trim;

  // Narrow black ventral basket, deeply undercut below the four-lobed carapace.
  const belly:Section[]=[[0,2.12,.10,.39,.45],[0,2.34,.08,.74,.72],
    [0,2.64,.03,1.02,.89],[0,3.0,.01,1.30,1.16],[0,3.28,0,1.41,1.24]];
  w.shell(belly,dark);
  for(let i=0;i<3;i++) {
    const y=2.38+i*.23;
    w.line([[-.64-i*.16,y,-.40],[0,y-.13,-.80-i*.12],[.64+i*.16,y,-.40]],.054,bronze);
  }
  // A flattened, shaped dome on a tapered chest, with separated curved petals.
  const dome:Section[]=[[0,3.07,0,1.35,1.19],[0,3.38,.07,1.44,1.27],
    [0,3.66,.10,1.36,1.24],[0,3.96,.12,1.18,1.08],
    [0,4.16,.14,.85,.79],[0,4.27,.15,.43,.41],[0,4.29,.15,.025,.025]];
  w.shell(dome,dark);
  for(let i=0;i<8;i++) {
    const start=i*Math.PI/4+.032,end=(i+1)*Math.PI/4-.032;
    w.shell(dome,i===3||i===4?blue:gold,new THREE.Matrix4().makeTranslation(0,.025,0),start,end,.13,56);
  }
  // Smaller top hatch is itself four curved pieces, not a smooth bowling ball.
  const hatch:Section[]=[[0,4.07,.15,.91,.85],[0,4.26,.15,.79,.74],
    [0,4.40,.15,.47,.44],[0,4.44,.15,.045,.045]];
  for(let i=0;i<4;i++) w.shell(hatch,gold,new THREE.Matrix4(),i*Math.PI/2+.035,(i+1)*Math.PI/2-.035,.065,48);
  w.line([[-.91,4.08,.15],[-.65,4.08,-.45],[0,4.08,-.70],[.65,4.08,-.45],[.91,4.08,.15],
    [.65,4.08,.75],[0,4.08,1.0],[-.65,4.08,.75],[-.91,4.08,.15]],.031,edge);
  // Central tapering blue forehead with small embedded sensor and sculpted rim.
  w.shell([[0,2.98,-1.04,.11,.10],[0,3.22,-1.15,.45,.15],
    [0,3.55,-1.11,.68,.13],[0,3.79,-.99,.62,.10],[0,4.00,-.74,.47,.06]],blue);
  for(const s of [-1,1]) w.line([[s*.10,3.03,-1.14],[s*.39,3.28,-1.30],
    [s*.70,3.66,-1.23],[s*.56,4.00,-.99]],.034,edge);
  w.optic([0,3.27,-1.33],[0,-.05,-1],.17,.18,edge,dark,glass,glow);
  // Rear dorsal arch is a pierced casting, not a flat flag.
  const arch=new THREE.Shape();arch.moveTo(-.72,0);arch.quadraticCurveTo(-.65,.81,-.22,1.13);
  arch.quadraticCurveTo(0,1.31,.22,1.13);arch.quadraticCurveTo(.65,.81,.72,0);
  arch.lineTo(.45,.06);arch.quadraticCurveTo(.37,.65,0,.92);arch.quadraticCurveTo(-.37,.65,-.45,.06);arch.closePath();
  w.plate(arch,bronze,w.frame([0,3.85,.90],[0,0,1]),.15);
  w.line([[-.57,3.91,1.085],[-.40,4.53,1.085],[0,4.94,1.085],[.40,4.53,1.085],[.57,3.91,1.085]],.034,edge);
  // Short suspended phase-disruptor muzzle, visible under the chest.
  w.shell([[0,2.04,-.93,.10,.19],[0,2.26,-1.11,.20,.29],[0,2.52,-1.05,.24,.27],
    [0,2.77,-.76,.15,.20]],gold);
  w.optic([0,2.31,-1.39],[0,-.12,-1],.115,.13,edge,dark,glass,glow);

  for(const sx of [-1,1]) for(const sz of [-1,1]) {
    const n:Point=[sx*.707,0,sz*.707];
    const radial=(r:number,y:number):Point=>[n[0]*r,y,n[2]*r];
    const hip=radial(1.30,2.98),elbow=radial(2.38,3.58),knee=radial(3.21,2.83);
    const ankle=radial(3.83,.73),toe=radial(4.20,.035);
    const tangent:Point=[n[2],0,-n[0]];
    w.joint(hip,n,.37,bronze,dark,blue);
    w.limb(hip,elbow,n,[[0,.23,.24,0],[.35,.33,.29,.05],[.73,.31,.28,.10],[1,.23,.20,0]],dark);
    // Splayed shoulder hood: an open curved canopy with everted lip and a
    // cutaway underside. No sphere or full ovoid can reproduce this profile.
    const shoulder:Section[]=[
      [0,2.96,1.41,.34,.26],[0,3.23,1.57,.64,.53],[0,3.64,1.89,.70,.61],
      [0,4.02,2.13,.59,.39],[0,4.25,2.25,.41,.19],[0,4.35,2.36,.24,.08],
    ];
    const m=w.frame([0,0,0],n);
    w.shell(shoulder,gold,m,-1.65,1.65,.17,48);
    w.shell(shoulder,blue,m,1.74,2.44,.13,48);
    w.shell(shoulder,gold,m,3.84,4.55,.13,48);
    const outer:Section[]=[[0,3.45,2.38,.51,.18],[0,3.84,2.53,.50,.23],
      [0,4.16,2.63,.37,.12],[0,4.35,2.70,.24,.055]];
    w.shell(outer,edge,m,-1.35,1.35,.09,40,.65);
    const transform=(p:Point)=>new THREE.Vector3(...p).applyMatrix4(m).toArray() as Point;
    for(const s of [-1,1]) {
      w.line([[s*.35,3.03,1.58],[s*.66,3.43,2.04],[s*.59,3.92,2.32],[s*.30,4.29,2.30]].map(p=>transform(p as Point)),.032,bronze);
    }
    w.joint(elbow,tangent,.30,edge,dark,blue);
    // Reverse-bent short upper leg, exposing a central piston below the hood.
    w.limb(elbow,knee,n,[[0,.24,.13,0],[.34,.32,.17,.10],[.70,.28,.16,.12],[1,.21,.12,0]],bronze,true);
    w.line([radial(2.19,3.30),radial(2.58,2.98),radial(3.05,2.66)],.095,dark);
    w.joint(knee,tangent,.29,edge,dark,blue);
    // Curved shin is three overlapping solid shells, never a full-length leaf.
    w.limb(ankle,knee,n,[[0,.10,.09,0],[.26,.13,.10,.03],[.59,.17,.12,.04],[.87,.20,.12,.025],[1,.16,.10,0]],dark);
    const lower=radial(3.76,.88),middle=radial(3.49,1.88),upper=radial(3.22,2.83);
    w.limb(middle,upper,n,[[0,.25,.12,.12],[.28,.41,.19,.15],[.72,.42,.20,.12],[1,.29,.14,.04]],gold,true);
    w.limb(lower,middle,n,[[0,.16,.11,.08],[.25,.28,.15,.13],[.72,.34,.18,.14],[1,.30,.15,.10]],gold,true);
    w.limb(ankle,lower,n,[[0,.17,.12,.06],[.55,.24,.15,.10],[1,.22,.12,.06]],edge,true);
    // Longitudinal small inset and two tiny calf vents, subordinate to the form.
    w.limb(middle,upper,n,[[.16,.055,.016,.30],[.40,.14,.018,.355],[.69,.15,.018,.335],[.91,.055,.012,.23]],bronze);
    w.limb(middle,upper,n,[[.21,.045,.012,.32],[.42,.11,.016,.373],[.67,.12,.016,.351],[.85,.045,.010,.26]],blue);
    w.limb(lower,middle,n,[[.14,.014,.01,.22],[.40,.022,.014,.30],[.73,.025,.013,.335],[.89,.012,.008,.28]],bronze);
    for(let i=0;i<2;i++) {
      const c=radial(3.56+i*.07,1.61-i*.18);
      w.line([[c[0]-tangent[0]*.11,c[1],c[2]-tangent[2]*.11],
        [c[0]+n[0]*.26,c[1]-.025,c[2]+n[2]*.26],
        [c[0]+tangent[0]*.11,c[1],c[2]+tangent[2]*.11]],.023,bronze);
    }
    w.joint(ankle,tangent,.19,bronze,dark,blue);
    // Articulated hock and paired talons: a visible ankle gap above grounded toes.
    w.limb(toe,ankle,n,[[0,.035,.045,0],[.25,.13,.16,.06],[.7,.19,.21,.13],[1,.14,.16,.04]],dark);
    for(const s of [-1,1]) {
      const end:Point=[toe[0]+tangent[0]*s*.15,.03,toe[2]+tangent[2]*s*.15];
      const top:Point=[ankle[0]+tangent[0]*s*.13,.57,ankle[2]+tangent[2]*s*.13];
      w.limb(end,top,n,[[0,.018,.025,0],[.3,.075,.075,.04],[.72,.11,.11,.09],[1,.075,.055,0]],gold,true);
    }
    w.limb(radial(3.90,.34),radial(3.78,.84),n,[[0,.05,.055,.15],[.5,.16,.16,.17],[1,.11,.10,.09]],blue);
  }
  return w.finish('dragoon',5.2,7.4,7.4);
}
