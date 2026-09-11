import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import Hud, { type HudProps } from './Hud';
import { STATIONS } from '../core/types';

afterEach(cleanup);
const station = STATIONS[0];
const target: HudProps['target'] = { kind: 'station', id: 'station:' + station.id, label: station.label, hint: '接入测试终端', distance: 3, station };
const props: HudProps = {
  snapshot: { x: 0, y: 0, z: 0, yaw: 0, zone: '舰桥', zoneCode: 'BRIDGE', grounded: true, sprinting: false, crouching: false, crouchBlend: 0, fps: 60, target, collected: 0, nearestStation: { id: station.id, label: station.label, distance: 3 } },
  vitals: { vitals: [], system: null, availability: 'unavailable', lastUpdated: 0, refresh: vi.fn(), loading: false },
  notices: [], target, locked: true, dimmed: false, pickupProgress: { collected: 0, total: 12 }, onInteract: vi.fn(),
};
describe('connected terminal HUD prompts', () => {
  it('hides the same terminal prompt in free look and restores it after disconnect', () => {
    const view = render(<Hud {...props} connectedPanel={station.id} />);
    expect(screen.queryByRole('button', { name: /接入测试终端/ })).toBeNull();
    expect(view.container.querySelector('.hud-crosshair-active')).toBeNull();
    view.rerender(<Hud {...props} connectedPanel={null} />);
    expect(screen.getByRole('button', { name: /接入测试终端/ })).toBeInTheDocument();
  });
  it('keeps other terminal and pickup prompts', () => {
    const view = render(<Hud {...props} connectedPanel={STATIONS[1].id} />);
    expect(screen.getByRole('button', { name: /接入测试终端/ })).toBeInTheDocument();
    view.rerender(<Hud {...props} connectedPanel={station.id} target={{ kind: 'pickup', id: 'pickup', label: '物资', hint: '拾取物资', distance: 2 }} />);
    expect(screen.getByRole('button', { name: /拾取物资/ })).toBeInTheDocument();
  });
  it('does not replace the connected prompt with a nearby hint', () => {
    const view = render(<Hud {...props} target={null} connectedPanel={station.id} />);
    expect(view.container.querySelector('.hud-nearby')).toBeNull();
  });
});
