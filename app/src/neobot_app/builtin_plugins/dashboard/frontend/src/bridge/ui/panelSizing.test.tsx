import { act, cleanup, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PerspectiveCamera } from 'three';
import PanelAnchor from './PanelAnchor';
import { PANEL_LAYOUT, panelWorldSize } from './panelSizing';
import { PIXELS_PER_METER, panelPlaneFromScreen, projectPanel } from '../three/projector';
import { STATIONS } from '../core/types';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('world panel sizing', () => {
  it('gives every station desktop space with an undistorted minimum world size', () => {
    for (const station of STATIONS) {
      const size = panelWorldSize(station.screenSize.width);
      expect(size.width).toBeGreaterThanOrEqual(3.6);
      expect(size.height).toBeGreaterThanOrEqual(2.4);
      const scale = size.width * PIXELS_PER_METER / PANEL_LAYOUT.width;
      expect(PANEL_LAYOUT.height * scale).toBeCloseTo(size.height * PIXELS_PER_METER);
    }
  });

  it('keeps physical size constant while perspective shrinks with distance', () => {
    const plane = { ...panelPlaneFromScreen([0, 0, 0], 0, { width: 0.86, height: 0.42 }), ...panelWorldSize(0.86) };
    const camera = new PerspectiveCamera(60, 16 / 9, 0.1, 100);
    const widthAt = (distance: number) => {
      camera.position.copy(plane.center).addScaledVector(plane.normal, distance);
      camera.lookAt(plane.center);
      camera.updateMatrixWorld(true);
      const projected = projectPanel(camera, plane, 1280, 720);
      return Math.abs(projected.quad[1].x - projected.quad[0].x);
    };
    expect(widthAt(3)).toBeCloseTo(widthAt(6) * 2);
  });

  it('disables hidden/closing descendants and restores a visible projection', () => {
    let tick: FrameRequestCallback = () => {};
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { tick = callback; return 1; });
    vi.stubGlobal('cancelAnimationFrame', vi.fn());
    const station = STATIONS[0];
    const plane = panelPlaneFromScreen(station.screen, station.screenYaw, station.screenSize);
    const camera = new PerspectiveCamera(60, 16 / 9, 0.1, 100);
    camera.position.copy(plane.center).addScaledVector(plane.normal, 5);
    camera.lookAt(plane.center);
    camera.updateMatrixWorld(true);
    let available = true;
    const props = { station, getCamera: () => available ? camera : null, getViewport: () => ({ width: 1280, height: 720 }), getVisibility: () => 1, compositor: null };
    const view = render(<PanelAnchor {...props}><button>Action</button></PanelAnchor>);
    const host = view.container.firstElementChild as HTMLElement;
    act(() => tick(0));
    expect(host.dataset.interactive).toBe('true');
    camera.rotateY(Math.PI);
    camera.updateMatrixWorld(true);
    act(() => tick(16));
    expect(host.style.visibility).toBe('hidden');
    expect(host.dataset.interactive).toBe('false');
    expect(host.hasAttribute('inert')).toBe(true);
    camera.lookAt(plane.center);
    camera.updateMatrixWorld(true);
    act(() => tick(32));
    expect(host.dataset.interactive).toBe('true');
    expect(host.hasAttribute('inert')).toBe(false);
    view.rerender(<PanelAnchor {...props} closing><button>Action</button></PanelAnchor>);
    act(() => tick(48));
    expect(host.dataset.interactive).toBe('false');
    available = false;
    act(() => tick(64));
    expect(host.style.visibility).toBe('hidden');
  });
});
