// core/hud.ts —— DOM 覆盖层：准星、交互提示、舰况、提示气泡、对话框与设置菜单。
// 3D 场景负责沉浸感，这里负责「必须精确点击/输入」的部分（危险操作二次确认、文本输入）。

export interface DialogOption {
  label: string;
  value: string;
  danger?: boolean;
}

export class Hud {
  readonly root: HTMLElement;
  private readonly crosshair: HTMLElement;
  private readonly prompt: HTMLElement;
  private readonly status: HTMLElement;
  private readonly toasts: HTMLElement;
  private readonly banner: HTMLElement;
  private readonly minigame: HTMLElement;
  private dialog: HTMLElement | null = null;
  private dialogResolve: ((value: string | null) => void) | null = null;

  constructor(root: HTMLElement) {
    this.root = root;
    root.innerHTML = '';
    this.crosshair = document.createElement('div');
    this.crosshair.className = 'hud-crosshair';
    this.crosshair.innerHTML = '<span></span><span></span>';
    this.prompt = document.createElement('div');
    this.prompt.className = 'hud-prompt hidden';
    this.status = document.createElement('div');
    this.status.className = 'hud-status hidden';
    this.toasts = document.createElement('div');
    this.toasts.className = 'hud-toasts';
    this.banner = document.createElement('div');
    this.banner.className = 'hud-banner hidden';
    this.minigame = document.createElement('div');
    this.minigame.className = 'hud-minigame hidden';
    root.append(this.crosshair, this.prompt, this.status, this.banner, this.minigame, this.toasts);
  }

  setCrosshairVisible(visible: boolean, variant: 'dot' | 'pointer' = 'dot'): void {
    this.crosshair.classList.toggle('hidden', !visible);
    this.crosshair.classList.toggle('pointer', variant === 'pointer');
  }

  showPrompt(text: string | null, hint = 'E'): void {
    if (!text) {
      this.prompt.classList.add('hidden');
      return;
    }
    this.prompt.classList.remove('hidden');
    this.prompt.innerHTML =
      '<kbd>' + hint + '</kbd><span>' + escapeHtml(text) + '</span>';
  }

  setStatus(lines: string[] | null): void {
    if (!lines || lines.length === 0) {
      this.status.classList.add('hidden');
      return;
    }
    this.status.classList.remove('hidden');
    this.status.innerHTML = lines
      .map((line) => '<div>' + escapeHtml(line) + '</div>')
      .join('');
  }

  setBanner(text: string | null, tone: 'info' | 'warn' = 'warn'): void {
    if (!text) {
      this.banner.classList.add('hidden');
      return;
    }
    this.banner.classList.remove('hidden');
    this.banner.classList.toggle('warn', tone === 'warn');
    this.banner.textContent = text;
  }

  /** 小游戏 HUD（右上角常驻信息条） */
  setMinigame(info: { title: string; score: string; extra?: string; hint?: string } | null): void {
    if (!info) {
      this.minigame.classList.add('hidden');
      return;
    }
    this.minigame.classList.remove('hidden');
    this.minigame.innerHTML =
      '<div class="mg-title">' + escapeHtml(info.title) + '</div>' +
      '<div class="mg-score">' + escapeHtml(info.score) + '</div>' +
      (info.extra ? '<div class="mg-extra">' + escapeHtml(info.extra) + '</div>' : '') +
      (info.hint ? '<div class="mg-hint">' + escapeHtml(info.hint) + '</div>' : '');
  }

  toast(message: string, tone: 'info' | 'ok' | 'warn' | 'error' = 'info', ttl = 3600): void {
    const element = document.createElement('div');
    element.className = 'hud-toast ' + tone;
    element.textContent = message;
    this.toasts.appendChild(element);
    window.setTimeout(() => {
      element.classList.add('leaving');
      window.setTimeout(() => element.remove(), 400);
    }, ttl);
  }

  /** 危险操作二次确认（返回 true 表示用户确认） */
  confirm(options: {
    title: string;
    body?: string;
    confirmLabel?: string;
    cancelLabel?: string;
    danger?: boolean;
  }): Promise<boolean> {
    return new Promise((resolve) => {
      const overlay = document.createElement('div');
      overlay.className = 'hud-dialog-overlay';
      overlay.innerHTML =
        '<div class="hud-dialog' + (options.danger ? ' danger' : '') + '">' +
        '<h3>' + escapeHtml(options.title) + '</h3>' +
        (options.body ? '<p>' + escapeHtml(options.body) + '</p>' : '') +
        '<div class="hud-dialog-actions">' +
        '<button class="ghost" data-action="cancel">' + escapeHtml(options.cancelLabel || '取消') + '</button>' +
        '<button class="' + (options.danger ? 'danger' : 'primary') + '" data-action="ok">' +
        escapeHtml(options.confirmLabel || '确认') + '</button>' +
        '</div></div>';
      const close = (value: boolean) => {
        overlay.remove();
        window.removeEventListener('keydown', onKey, true);
        resolve(value);
      };
      const onKey = (event: KeyboardEvent) => {
        if (event.key === 'Escape') {
          event.stopPropagation();
          close(false);
        } else if (event.key === 'Enter') {
          event.stopPropagation();
          close(true);
        }
      };
      overlay.addEventListener('click', (event) => {
        const target = event.target as HTMLElement;
        const action = target.dataset.action;
        if (action === 'ok') close(true);
        else if (action === 'cancel' || target === overlay) close(false);
      });
      window.addEventListener('keydown', onKey, true);
      document.body.appendChild(overlay);
    });
  }

  /** 文本输入对话框（用于舰长名、仓库地址等需要中文输入的场景） */
  ask(options: {
    title: string;
    placeholder?: string;
    value?: string;
    hint?: string;
  }): Promise<string | null> {
    if (this.dialog) this.dialogResolve?.(null);
    return new Promise((resolve) => {
      const overlay = document.createElement('div');
      overlay.className = 'hud-dialog-overlay';
      overlay.innerHTML =
        '<div class="hud-dialog">' +
        '<h3>' + escapeHtml(options.title) + '</h3>' +
        (options.hint ? '<p>' + escapeHtml(options.hint) + '</p>' : '') +
        '<input type="text" />' +
        '<div class="hud-dialog-actions">' +
        '<button class="ghost" data-action="cancel">取消</button>' +
        '<button class="primary" data-action="ok">确定</button>' +
        '</div></div>';
      const input = overlay.querySelector('input') as HTMLInputElement;
      input.placeholder = options.placeholder || '';
      input.value = options.value || '';
      this.dialog = overlay;
      this.dialogResolve = resolve;
      const close = (value: string | null) => {
        overlay.remove();
        this.dialog = null;
        this.dialogResolve = null;
        resolve(value);
      };
      overlay.addEventListener('click', (event) => {
        const target = event.target as HTMLElement;
        if (target.dataset.action === 'ok') close(input.value);
        else if (target.dataset.action === 'cancel' || target === overlay) close(null);
      });
      input.addEventListener('keydown', (event) => {
        event.stopPropagation();
        if (event.key === 'Enter') close(input.value);
        if (event.key === 'Escape') close(null);
      });
      document.body.appendChild(overlay);
      input.focus();
      input.select();
    });
  }
}

export function escapeHtml(text: string): string {
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
