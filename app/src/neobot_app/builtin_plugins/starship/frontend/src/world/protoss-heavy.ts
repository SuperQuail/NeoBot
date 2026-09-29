/** Reference-sculpted Khalai heavy units. Feet y=0; weapon forward is local -Z.
 * Seven material batches per unit; no platforms, lights or animation side effects.
 * References: SC2 Immortal Rend1 + Cncpt1, Colossus Rend1 + Cncpt2.
 * LotV purifier Game3 was used for articulation only, NOT its white/orange skin. */
import type { Group } from 'three';
import type { ShipMaterials } from './materials';
import { HeavySculpt, type V2, type V3 } from './protoss-heavy-sculpt';

const shield: V2[] = [[0,-1],[-.7,-.62],[-1,.2],[-.66,.84],[0,1],[.66,.84],[1,.2],[.7,-.62]];
const scaled = (shape: V2[], x:number, y:number): V2[] => shape.map(([a,b])=>[a*x,b*y]);
const mirror = (shape:V2[], side:number):V2[] => shape.map(([x,y])=>[x*side,y]);

/** High torso, out-swept thick shoulder shells, vertically stacked short muzzles. */
export function buildImmortal(materials: ShipMaterials): Group {
  const b=new HeavySculpt(materials);
  b.shell([{p:[0,2.35,.2],w:.92,d:.65},{p:[0,3.10,.25],w:1.4,d:.92},{p:[0,3.72,.3],w:1.3,d:.8}], 'dark');
  b.shell([{p:[0,3.36,.08],w:.85,d:.6},{p:[0,4.38,.25],w:1.68,d:1.03},
    {p:[0,5.46,.49],w:1.48,d:1.01},{p:[0,6.26,.62],w:.81,d:.65},{p:[0,6.58,.57],w:.20,d:.2}], 'bronze');
  // Exposed abdominal bellows, no apron covering the entire ribbed well.
  for(let i=0;i<5;i++) {
    const y=2.75+i*.19;
    b.curvedPlate([[-.87,-.045],[.87,-.045],[.95,.055],[-.95,.055]],.10,'bronze',[0,y,-.94],[0,0,0],.025,[.19,0,0]);
  }
  for(const side of [-1,1]) {
    // Broad load-bearing shoulder bridge with separated transverse lamellae.
    b.shell([{p:[side*.75,4.7,.25],w:.63,d:.46},{p:[side*1.55,5.18,.28],w:.65,d:.53},
      {p:[side*2.14,5.15,.15],w:.47,d:.38}], 'dark',[0,0,-1],20,24);
    for(let tier=0;tier<3;tier++) {
      b.curvedPlate(mirror([[-.57,-.13],[.43,-.23],[.65,.12],[.13,.35],[-.52,.20]],side),.16,'gold',
        [side*1.55,5.6-tier*.3,-.55-tier*.07],[.13,side*.25,side*.12],.055,[.12,.22,.09]);
    }
    // Pods swell toward the shoulders then taper into armored gun faces. The mass
    // extends OUTWARD around the gun, not a cuboid enclosing a pair of plumbing tubes.
    b.shell([{p:[side*2.13,5.08,1.15],w:.24,d:.36},{p:[side*2.42,5.26,.64],w:.79,d:.92},
      {p:[side*2.53,5.23,-.28],w:.93,d:.93},{p:[side*2.67,5.08,-1.34],w:.70,d:.81},
      {p:[side*2.63,4.97,-2.06],w:.36,d:.54}], 'bronze',[0,1,0],40,36);
    // Convex, rolled shoulder hood follows the pod slope (not a white flat lid).
    b.curvedPlate([[-.63,-1.10],[.52,-1.12],[.89,-.38],[.84,.60],[.32,1.35],[-.25,1.48],[-.87,.68],[-.99,-.18]],.27,'gold',
      [side*2.48,6.23,-.22],[-Math.PI/2,0,side*.10],.095,[-.38,-.24,-.04]);
    b.surfaceLine([[-.70,-.43],[-.53,.03],[-.30,.53],[.16,1.02]],
      [side*2.48,6.23,-.22],[-Math.PI/2,0,side*.10],[-.38,-.24,-.04],.24,.019,'dark');
    b.curvedPlate(scaled(shield,.24,.38),.055,'dark',[side*2.45,6.39,-.30],[-Math.PI/2,0,0],.025,[-.3,-.20,0]);
    b.curvedPlate(scaled(shield,.16,.29),.05,'blue',[side*2.45,6.43,-.30],[-Math.PI/2,0,0],.018,[-.3,-.2,0]);
    // Thick swept outer cheek with a separate blue inlay underneath its rolled rim.
    const cheek:V2[]=[[-1.14,-.02],[-.72,.64],[.45,.85],[1.78,.22],[1.95,-.47],[1.13,-.85],[-.62,-.76]];
    const rotation:V3=[0,side*Math.PI/2,0];
    b.curvedPlate(cheek.map(([z,y])=>[z*side,y]),.27,'gold',[side*3.22,5.13,-.09],rotation,.075,[-.24,-.37,0]);
    b.curvedPlate([[-.59,-.38],[.26,-.34],[1.2,-.63],[.87,-.76],[-.36,-.64]].map(([z,y])=>[z*side,y]),.07,'blue',
      [side*3.41,5.12,-.10],rotation,.035,[-.24,-.37,0]);
    // Official rear-turn poses expose a large curved shoulder energy inset.
    b.curvedPlate(scaled(shield,.43,.61),.105,'dark',[side*3.30,5.49,.46],rotation,.035,[-.32,-.34,0]);
    b.curvedPlate(scaled(shield,.34,.51),.070,'blue',[side*3.40,5.49,.46],rotation,.035,[-.32,-.34,0]);
    // Two chunky rectangular muzzles stacked VERTICALLY, as on the technical art.
    b.curvedPlate([[-.39,-.65],[.40,-.65],[.48,.3],[.28,.70],[-.27,.70],[-.48,.3]],.27,'gold',
      [side*2.63,5.02,-2.08],[0,side*.07,0],.065,[.21,.08,0]);
    for(const y of [4.77,5.30]) {
      b.block([side*2.63,y,-2.33],[.47,.37,.52],'bronze',[0,0,0],.075);
      b.block([side*2.63,y,-2.62],[.50,.38,.20],'edge',[0,0,0],.055);
      b.block([side*2.63,y,-2.758],[.33,.235,.035],'dark',[0,0,0],.026);
      b.block([side*2.63,y,-2.783],[.225,.12,.014],'blue',[0,0,0],.018);
      b.block([side*2.63,y+.10,-2.30],[.29,.045,.34],'steel',[0,0,0],.016);
    }
    // Overlapping curved breast plates curve back into the high shoulder mass.
    b.curvedPlate(mirror([[.08,-1.03],[.76,-.87],[1.2,-.14],[1.17,.76],[.48,1.45],[.04,1.05],[.28,.23]],side),.23,'gold',
      [side*.25,4.76,-.84],[0,0,0],.085,[.20,.045,.35]);
    for(const fore of [-1,1]) {
      const hip:V3=[side*1.22,3.12,fore*.9],knee:V3=[side*2.76,2.15,fore*2.08],ankle:V3=[side*3.12,.67,fore*2.86];
      b.drum(hip,.48,.62,'dark',[0,0,Math.PI/2]);
      b.shell([{p:[side*1.35,3.10,fore*1.0],w:.37,d:.33},{p:[side*1.94,3.02,fore*1.50],w:.59,d:.45},
        {p:[side*2.48,2.59,fore*1.92],w:.56,d:.40},{p:[side*2.69,2.31,fore*2.03],w:.34,d:.28}], 'gold',[0,0,-fore],28,28);
      b.shell([{p:[side*1.51,3.40,fore*1.20],w:.16,d:.095},{p:[side*2.07,3.25,fore*1.66],w:.37,d:.115},
        {p:[side*2.57,2.64,fore*2.11],w:.24,d:.08}], 'edge',[0,0,-fore],24,20);
      b.drum(knee,.43,.64,'dark',[0,0,Math.PI/2]);
      b.drum([side*3.13,2.15,fore*2.08],.31,.13,'bronze',[0,0,Math.PI/2]);
      b.ring([side*3.23,2.15,fore*2.08],.235,.045,'edge',[0,Math.PI/2,0]);
      b.drum([side*3.25,2.15,fore*2.08],.13,.07,'steel',[0,0,Math.PI/2]);
      b.shell([{p:[side*2.82,2.04,fore*2.16],w:.35,d:.30},{p:[side*3.06,1.53,fore*2.53],w:.47,d:.36},
        {p:[side*3.15,.98,fore*2.77],w:.33,d:.26},{p:[side*3.12,.76,fore*2.84],w:.22,d:.20}], 'gold',[0,0,-fore],28,28);
      const legRot:V3=[fore<0?-.25:.25,fore<0?0:Math.PI,side*-.08];
      b.curvedPlate([[0,.79],[-.43,.14],[-.35,-.29],[.31,-.38],[.46,.16]],.17,'edge',[side*2.87,2.05,fore*2.43],legRot,.055,[.42,.16,0]);
      for(const slot of [-.11,.11])b.surfaceLine([[slot,.35],[slot*.85,.21],[slot*.7,.1]],
        [side*2.87,2.05,fore*2.43],legRot,[.42,.16,0],-.149,.014,'dark');
      b.curvedPlate([[-.20,.44],[.19,.44],[.23,-.12],[.03,-.50],[-.18,-.27]],.075,'blue',
        [side*3.13,1.35,fore*2.90],legRot,.028,[.4,.18,0]);
      b.drum(ankle,.245,.48,'dark',[0,0,Math.PI/2]);
      // Articulated curved metal talon, not a rectangular boot or an endless shin.
      b.shell([{p:[side*3.12,.61,fore*2.9],w:.22,d:.16},{p:[side*3.18,.36,fore*3.21],w:.31,d:.19},
        {p:[side*3.19,.14,fore*3.54],w:.19,d:.10},{p:[side*3.18,.055,fore*3.83],w:.014,d:.018}], 'edge',[0,1,0],24,24);
      b.shell([{p:[side*3.20,.43,fore*3.24],w:.07,d:.035},{p:[side*3.20,.23,fore*3.53],w:.063,d:.025},
        {p:[side*3.18,.095,fore*3.77],w:.009,d:.012}], 'bronze',[0,1,0],16,16);
    }
  }
  // A sculpted V-shaped prow: tilts back at the top and projects at the abdomen.
  const faceCamber:V3=[.21,.055,.38];
  b.curvedPlate([[0,-1.34],[-.52,-.91],[-.69,.14],[-.48,1.04],[0,1.60],[.48,1.04],[.69,.14],[.52,-.91]],.20,'dark',
    [0,4.91,-1.0],[0,0,0],.055,faceCamber);
  b.curvedPlate([[0,-1.17],[-.38,-.81],[-.48,.15],[-.30,1.02],[0,1.35],[.30,1.02],[.48,.15],[.38,-.81]],.08,'blue',
    [0,4.91,-1.28],[0,0,0],.025,faceCamber);
  for(const side of [-1,1]) b.curvedPlate(mirror([[.015,-1.43],[.37,-.97],[.71,-.11],[.66,.67],[.25,1.44],[.02,1.68],
    [.11,1.12],[.40,.46],[.43,-.16],[.18,-.94]],side),.21,'gold',[0,4.91,-1.27],[0,0,0],.055,faceCamber);
  b.curvedPlate([[0,-1.08],[-.10,-.63],[-.11,.92],[0,1.47],[.11,.92],[.10,-.63]],.14,'edge',[0,4.91,-1.37],[0,0,0],.028,faceCamber);
  for(let i=0;i<4;i++) for(const side of [-1,1]) {
    const y=4.18+i*.31,dy=y-4.91;
    b.curvedPlate([[-.12,-.037],[.12,-.037],[.13,.039],[-.13,.039]],.045,'bronze',[side*.29,y,-1.28+.055*dy*dy+.38*dy],[0,0,side*.17],.013,[.2,0,0]);
  }
  b.block([0,5.83,-1.10],[.27,.055,.07],'glow',[.35,0,0],.014);
  b.curvedPlate([[0,-.68],[-.67,-.15],[-.89,.43],[0,.28],[.89,.43],[.67,-.15]],.22,'gold',[0,2.39,-1.10],[0,0,0],.075,[.2,.07,.11]);
  b.curvedPlate([[0,-.46],[-.48,-.03],[-.58,.2],[0,.10],[.58,.2],[.48,-.03]],.07,'blue',[0,2.39,-1.29],[0,0,0],.035,[.2,.07,.11]);
  return b.finish('immortal','不朽者 · IMMORTAL',6.8,8,8,5.7);
}

/** Forward-canted heavy carapace, curved energy glazing and articulated long feet. */
export function buildColossus(materials: ShipMaterials): Group {
  const b=new HeavySculpt(materials);
  // A real volumetric back and shoulder barrel, not separate flat signboards.
  b.shell([{p:[0,12.1,.65],w:.87,d:.77},{p:[0,14.0,.46],w:2.21,d:1.65},
    {p:[0,17.15,-.1],w:3.32,d:2.36},{p:[0,20.20,-.74],w:3.14,d:2.22},
    {p:[0,22.22,-1.10],w:2.13,d:1.57},{p:[0,23.18,-1.08],w:.61,d:.47}], 'bronze',[0,0,-1],48,40);
  // Segmented rounded dorsal plates remain continuous in volume but not in seams.
  for(let i=0;i<4;i++) {
    const y=15.15+i*1.65,w=i===3?1.76:2.65;
    b.curvedPlate([[-w,-.51],[-w*.70,-.89],[w*.70,-.89],[w,-.51],[w*.82,.64],[0,.95],[-w*.82,.64]],.26,'gold',
      [0,y,1.93-i*.28],[.12,0,0],.12,[-.17,-.13,0]);
  }
  b.shell([{p:[0,10.42,.44],w:.8,d:.67},{p:[0,11.9,.59],w:1.09,d:.83},{p:[0,14.1,.24],w:1.61,d:1.20}], 'dark',[0,0,-1],24,28);
  // Wrap-around belly bellows expose dark recessed gaps between seven heavy ribs.
  for(let i=0;i<7;i++) {
    const y=10.8+i*.43,w=.89+i*.105,d=.7+i*.063;
    b.shell([{p:[0,y,.49-i*.035],w:w*.89,d:d*.91},{p:[0,y+.15,.49-i*.035],w,d},
      {p:[0,y+.28,.49-i*.035],w:w*.94,d:d*.96}], i%2===0?'gold':'bronze',[0,0,-1],8,28);
    b.curvedPlate([[-w,.09],[0,-.3],[w,.09],[w*.65,-.22],[0,-.51],[-w*.65,-.22]],.1,'edge',
      [0,y+.1,-.28-i*.095],[0,0,0],.035,[.20,0,0]);
  }
  const camber:V3=[.28,.032,-.27];
  const window:V2[]=[[-.62,-1.76],[-.95,-.81],[-.85,.58],[-.50,1.64],[.05,1.9],[.78,1.04],[.74,-.55],[.35,-1.76],[-.07,-2.13]];
  for(const side of [-1,1]) {
    const angle:V3=[0,side*.055,side*-.10];
    // Broad curved cheek shells curl around continuous, concave-set energy glazing.
    b.curvedPlate(mirror([[-.61,-2.78],[-1.22,-1.64],[-1.26,.77],[-.74,2.72],[.07,3.88],
      [.89,2.56],[1.20,.62],[1.12,-1.25],[.58,-2.77],[.02,-3.22]],side),.42,'gold',
      [side*1.44,17.6,-2.41],angle,.14,camber);
    b.surfaceLine(mirror([[-.62,2.0],[-.38,2.41],[.0,2.66],[.31,2.75]],side),
      [side*1.44,17.6,-2.41],angle,camber,-.362,.026,'dark');
    b.curvedPlate(mirror(scaled(window,1.12,1.08),side),.15,'dark',[side*1.41,17.45,-2.64],angle,.075,camber);
    b.curvedPlate(mirror(window,side),.13,'blue',[side*1.41,17.45,-2.76],angle,.075,camber);
    // Thin curved armor fillets partly overlap the glazing, never a hexagon badge.
    b.shell([{p:[side*.77,15.02,-2.1],w:.09,d:.1},{p:[side*.55,16.4,-2.62],w:.20,d:.13},
      {p:[side*.59,18.05,-2.96],w:.17,d:.12},{p:[side*.98,19.28,-3.04],w:.07,d:.06}], 'edge',[0,0,-1],28,20);
    // Flush psionic traces on the double-curved window; short bright nodes only.
    const glyph=(x:number,y:number):V3=>[side*(1.41+x),17.45+y,-2.93+.28*x*x+.032*y*y-.27*y];
    b.line([glyph(-.25,-1.20),glyph(-.37,-.60),glyph(-.38,-.13),glyph(-.10,.19),glyph(-.08,.82),glyph(.19,1.21)],.024,'glow');
    b.line([glyph(.24,-1.38),glyph(.31,-.75),glyph(.17,-.22),glyph(.29,.31),glyph(.35,.72)],.018,'glow');
    // Large side window is bowed into the fuselage rather than pasted on as a plate.
    const sideRotation:V3=[0,side*Math.PI/2,0],sideCamber:V3=[-.25,-.105,-.025];
    b.curvedPlate(scaled(shield,1.43,2.29),.22,'gold',[side*3.22,18.37,-.12],sideRotation,.11,sideCamber);
    b.curvedPlate(scaled(shield,1.19,1.99),.14,'dark',[side*3.39,18.37,-.12],sideRotation,.055,sideCamber);
    b.curvedPlate(scaled(shield,1.05,1.84),.085,'blue',[side*3.52,18.37,-.12],sideRotation,.045,sideCamber);
    const sideGlyph:V3[]=[];
    for(let j=0;j<=24;j++) {
      const a=j/24*Math.PI*1.65,z=Math.cos(a)*.61,dy=Math.sin(a)*1.11;
      sideGlyph.push([side*(3.61-.25*z*z-.105*dy*dy-.025*dy),18.37+dy,-.12-z]);
    }
    b.line(sideGlyph,.026,'glow');
    // Rounded crown armor rises from the shoulder. Sharp distal tips, thick roots.
    b.shell([{p:[side*2.28,19.78,-.02],w:.54,d:.43},{p:[side*2.28,21.05,-.39],w:.90,d:.65},
      {p:[side*1.98,22.41,-.96],w:.55,d:.43},{p:[side*1.58,23.76,-1.19],w:.025,d:.018}], 'gold',[0,0,-1],32,28);
    b.curvedPlate(scaled(shield,.64,.84),.20,'bronze',[side*2.75,20.52,-1.02],[0,side*.84,side*.05],.075,[.14,.15,0]);
    b.curvedPlate(scaled(shield,.43,.57),.095,'blue',[side*2.94,20.53,-1.19],[0,side*.84,side*.05],.045,[.14,.15,0]);
    b.ring([side*3.01,20.55,-1.37],.26,.028,'glow',[0,side*.84,0],[1,1.17,1]);
    // Separate, three-dimensional thermal-lance housings and twin emitter arrays.
    b.shell([{p:[side*2.53,16.6,-.69],w:.29,d:.3},{p:[side*3.27,17.10,-1.25],w:.61,d:.55},
      {p:[side*3.76,16.32,-1.98],w:.59,d:.5},{p:[side*3.56,15.33,-2.52],w:.26,d:.27}], 'gold',[0,0,-1],32,28);
    b.curvedPlate([[-.25,-.62],[-.47,.08],[-.31,.71],[.21,.82],[.47,.28],[.31,-.52]],.08,'blue',
      [side*3.47,16.39,-2.40],[-.33,side*.15,side*.23],.055,[.25,.13,.04]);
    b.shell([{p:[side*3.57,15.58,-2.51],w:.28,d:.21},{p:[side*3.58,15.13,-2.81],w:.27,d:.19}], 'bronze',[0,0,-1],12,20);
    for(const [dx,dy] of [[-.18,.12],[.18,.12],[0,-.18]]) {
      b.drum([side*3.58+dx,15.19+dy,-2.90],.14,.20,'dark');
      b.ring([side*3.58+dx,15.19+dy,-3.018],.115,.031,'edge');
      b.drum([side*3.58+dx,15.19+dy,-3.06],.075,.025,'glow');
    }
    b.shell([{p:[side*3.00,17.52,.17],w:.22,d:.16},{p:[side*3.78,18.16,-.1],w:.31,d:.14},
      {p:[side*4.91,18.73,-.68],w:.012,d:.016}], 'edge',[0,0,-1],24,20);

    for(const fore of [-1,1]) {
      const kneeY=fore<0?10.60:11.18;
      const hip:V3=[side*1.03,10.63,fore*1.02],knee:V3=[side*5.31,kneeY,fore*3.03];
      const hock:V3=[side*4.13,4.69,fore*3.86],ankle:V3=[side*5.39,.73,fore*3.72];
      b.drum(hip,.51,.66,'dark',[0,0,Math.PI/2]);
      b.drum([side*1.40,10.63,fore*1.02],.30,.12,'bronze',[0,0,Math.PI/2]);
      // The femur curves slightly down then back up to the staggered knee shields.
      b.shell([{p:[side*1.42,10.65,fore*1.13],w:.27,d:.25},{p:[side*2.95,10.16,fore*1.97],w:.49,d:.3},
        {p:[side*4.45,kneeY-.22,fore*2.77],w:.39,d:.25},{p:[side*5.0,kneeY,fore*2.97],w:.23,d:.2}], 'gold',[0,0,-fore],28,24);
      b.strut([side*1.80,10.29,fore*1.39],[side*4.75,kneeY-.35,fore*2.91],.10,.11,.085,.07,'steel');
      b.drum(knee,.55,.73,'dark',[0,0,Math.PI/2]);
      // Convex knee cowling flows over the pivot and ends in an upturned dagger.
      b.shell([{p:[side*5.3,kneeY-.63,fore*3.19],w:.20,d:.18},{p:[side*5.33,kneeY+.06,fore*3.30],w:.68,d:.40},
        {p:[side*5.17,kneeY+.73,fore*3.13],w:.47,d:.29},{p:[side*5.10,kneeY+1.73,fore*2.93],w:.014,d:.02}], 'gold',[0,0,-fore],28,28);
      const kneeRot:V3=[fore<0?-.11:.11,fore<0?0:Math.PI,side*-.11];
      b.curvedPlate(scaled(shield,.48,.51),.075,'dark',[side*5.32,kneeY+.06,fore*3.63],kneeRot,.045,[.38,.27,0]);
      b.curvedPlate(scaled(shield,.35,.38),.065,'blue',[side*5.32,kneeY+.06,fore*3.73],kneeRot,.032,[.38,.27,0]);
      b.ring([side*5.32,kneeY+.06,fore*3.81],.21,.022,'glow',[0,0,0],[1,.9,1],Math.PI*1.6);
      // Long shaped tibia folds IN to a separate hock, then the lower blade kicks OUT.
      b.shell([{p:[side*5.26,kneeY-.43,fore*3.03],w:.32,d:.27},{p:[side*5.13,8.18,fore*3.47],w:.43,d:.29},
        {p:[side*4.60,6.10,fore*3.84],w:.27,d:.18},{p:[side*4.17,5.04,fore*3.86],w:.18,d:.15}], 'gold',[0,0,-fore],36,24);
      b.shell([{p:[side*5.17,kneeY-.65,fore*3.29],w:.13,d:.07},{p:[side*5.05,8.06,fore*3.76],w:.15,d:.065},
        {p:[side*4.25,5.14,fore*4.04],w:.052,d:.035}], 'bronze',[0,0,-fore],28,16);
      b.drum(hock,.29,.51,'dark',[0,0,Math.PI/2]);
      b.drum([side*4.42,4.69,fore*3.86],.18,.10,'steel',[0,0,Math.PI/2]);
      b.shell([{p:[side*4.15,4.36,fore*3.86],w:.18,d:.16},{p:[side*4.59,3.08,fore*3.76],w:.30,d:.15},
        {p:[side*5.20,1.46,fore*3.68],w:.17,d:.10},{p:[side*5.36,.99,fore*3.70],w:.10,d:.08}], 'edge',[0,0,-fore],28,24);
      b.drum(ankle,.19,.35,'dark',[0,0,Math.PI/2]);
      b.shell([{p:[side*5.40,.62,fore*3.74],w:.15,d:.12},{p:[side*5.46,.34,fore*4.01],w:.21,d:.11},
        {p:[side*5.43,.06,fore*4.40],w:.014,d:.02}], 'bronze',[0,1,0],20,20);
    }
  }
  // Swept forehead and narrow central keel unite the two curved front windows.
  b.shell([{p:[0,19.47,-2.99],w:.26,d:.23},{p:[0,20.81,-2.95],w:1.24,d:.45},
    {p:[0,22.18,-2.57],w:1.12,d:.41},{p:[0,23.26,-1.74],w:.13,d:.12}], 'gold',[0,0,-1],32,28);
  b.shell([{p:[0,14.07,-1.94],w:.075,d:.09},{p:[0,16.06,-2.61],w:.29,d:.20},
    {p:[0,18.45,-3.03],w:.19,d:.17},{p:[0,20.01,-2.85],w:.035,d:.05}], 'edge',[0,0,-1],32,20);
  b.curvedPlate([[0,-.54],[-.67,.03],[-.72,.36],[0,.18],[.72,.36],[.67,.03]],.21,'gold',[0,14.34,-1.95],[0,0,0],.075,[.19,.04,0]);
  // Rear crescent is a thick sculpted blade with a true air gap, not a round tube.
  b.shell([{p:[0,13.73,1.26],w:.17,d:.14},{p:[0,16.66,3.32],w:.37,d:.29},
    {p:[0,19.70,4.12],w:.43,d:.31},{p:[0,22.45,3.17],w:.37,d:.26},{p:[0,23.34,1.44],w:.075,d:.1}], 'gold',[1,0,0],40,24);
  for(let i=0;i<4;i++)b.block([0,16.85+i*1.4,3.63+Math.sin(i)*.30],[.61,.10,.16],'bronze',[.15,0,0],.018);
  b.leanAbove(12,.085);
  return b.finish('colossus','巨像 · COLOSSUS',24,13.6,13.6,7.1,7.35);
}

