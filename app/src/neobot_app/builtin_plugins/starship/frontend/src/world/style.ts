/** Geometry-independent design tokens. New vessels have their own builders. */
export interface ShipPalette {
  armour:number; armourEdge:number; structure:number; deck:number; recess:number;
  energy:number; energyCore:number; glass:number; bronze:number;
}
export const PSIONIC_PALETTE:Readonly<ShipPalette> = Object.freeze({
  armour:0x96835b, armourEdge:0xb9aa80, structure:0x25343c, deck:0x263139,
  recess:0x101922, energy:0x287de3, energyCore:0x65bdff, glass:0x426592, bronze:0x584f3d,
});
export interface InstrumentTheme { frame:number; body:number; energy:number; text:string; }
export const PSIONIC_INSTRUMENTS:Readonly<InstrumentTheme> = Object.freeze({
  frame:PSIONIC_PALETTE.armour,body:PSIONIC_PALETTE.recess,energy:PSIONIC_PALETTE.energy,text:'#e5e9df',
});
