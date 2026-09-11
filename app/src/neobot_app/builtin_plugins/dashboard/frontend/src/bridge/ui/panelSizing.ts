/** Stable desktop layout, independently scaled onto a station's world plane. */
export const PANEL_LAYOUT = { width: 800, height: 540 } as const;
export const MIN_PANEL_WORLD_WIDTH = 3.6;

export function panelWorldSize(screenWidth: number) {
  const width = Math.max(MIN_PANEL_WORLD_WIDTH, screenWidth * 2.8);
  return { width, height: width * PANEL_LAYOUT.height / PANEL_LAYOUT.width };
}
