// state.ts —— 全局舰船状态：由 /game/api/status 驱动，终端据此决定可用性。
// 「不同状态下未启用的面板」在游戏内的表现就来自这里（熄屏 + 原因 + 恢复指引）。

export interface ShipStatus {
  standby: boolean;
  power_state: string;
  power_available: boolean;
  reason: string | null;
  operator: string | null;
  since_text: string | null;
  standby_seconds: number | null;
  online: boolean;
  plugins: { total: number; running: number; error: number };
  uptime_seconds: number;
}

export const EMPTY_STATUS: ShipStatus = {
  standby: false,
  power_state: 'unknown',
  power_available: false,
  reason: null,
  operator: null,
  since_text: null,
  standby_seconds: null,
  online: false,
  plugins: { total: 0, running: 0, error: 0 },
  uptime_seconds: 0,
};

export interface Availability {
  available: boolean;
  reason: string;
  hint: string;
  readOnly: boolean;
}

export class ShellState {
  status: ShipStatus = { ...EMPTY_STATUS };
  /** 面板是否允许管理操作（面板返回 manage_enabled / 权限裁剪） */
  manageEnabled = true;
  playerName = '舰长';
  quality: 'low' | 'medium' | 'high' = 'medium';
  private listeners = new Set<() => void>();

  subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  update(patch: Partial<ShipStatus>): void {
    this.status = { ...this.status, ...patch };
    this.emit();
  }

  setManageEnabled(value: boolean): void {
    if (this.manageEnabled === value) return;
    this.manageEnabled = value;
    this.emit();
  }

  private emit(): void {
    for (const listener of this.listeners) listener();
  }

  /** 终端的可用性判定（按菜单） */
  availability(terminalId: string): Availability {
    const offlineMenus: Record<string, { reason: string; hint: string }> = {
      usage: {
        reason: '待机中：模型调用统计已停止采集',
        hint: '在主控台点击「恢复运行」后重新上线',
      },
      analysis: {
        reason: '待机中：Agent 运行时未启动',
        hint: '在主控台点击「恢复运行」后重新上线',
      },
      bots: {
        reason: '待机中：OneBot 连接已断开',
        hint: '在主控台点击「恢复运行」后重新上线',
      },
    };
    if (this.status.standby) {
      const offline = offlineMenus[terminalId];
      if (offline) {
        return { available: false, reason: offline.reason, hint: offline.hint, readOnly: true };
      }
      return {
        available: true,
        reason: '舰船处于低功耗待机状态',
        hint: '',
        readOnly: terminalId === 'plugins' || terminalId === 'config' ? false : false,
      };
    }
    if (terminalId === 'bots' && !this.status.online) {
      return {
        available: true,
        reason: '未检测到 OneBot 连接：数据可能不是最新的',
        hint: '确认 NapCat / OneBot 是否已启动',
        readOnly: false,
      };
    }
    if ((terminalId === 'plugins' || terminalId === 'config') && !this.manageEnabled) {
      return {
        available: true,
        reason: '当前会话为只读模式（manage_plugins=false 或远程管理已关闭）',
        hint: '在面板「配置管理 → dashboard」中开启管理功能',
        readOnly: true,
      };
    }
    return { available: true, reason: '', hint: '', readOnly: false };
  }
}
