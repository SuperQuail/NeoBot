// ui/textinput.ts —— 3D 终端里的文本输入。
// 用一个不可见的 DOM input 承接真实键盘（含中文输入法），内容实时回显到全息屏；
// 这样既能中文输入，屏幕本身又保持 3D 全息呈现。

export class TextCapture {
  readonly element: HTMLInputElement;
  private active = false;
  value = '';
  private onCommit: ((value: string) => void) | null = null;
  private onCancel: (() => void) | null = null;
  private onType: ((value: string) => void) | null = null;

  constructor() {
    const input = document.createElement('input');
    input.type = 'text';
    input.autocomplete = 'off';
    input.autocapitalize = 'off';
    input.spellcheck = false;
    input.setAttribute('aria-hidden', 'true');
    input.className = 'text-capture';
    document.body.appendChild(input);
    this.element = input;

    input.addEventListener('input', () => {
      this.value = input.value;
      this.onType?.(this.value);
    });
    input.addEventListener('keydown', (event) => {
      event.stopPropagation();
      if (event.key === 'Enter') {
        event.preventDefault();
        const value = this.value;
        this.close();
        this.onCommit?.(value);
      } else if (event.key === 'Escape') {
        event.preventDefault();
        this.close();
        this.onCancel?.();
      }
    });
    input.addEventListener('blur', () => {
      if (this.active) {
        this.active = false;
        this.onCancel?.();
      }
    });
  }

  get isActive(): boolean {
    return this.active;
  }

  open(options: {
    initial?: string;
    onCommit: (value: string) => void;
    onCancel?: () => void;
    onType?: (value: string) => void;
  }): void {
    this.value = options.initial ?? '';
    this.element.value = this.value;
    this.onCommit = options.onCommit;
    this.onCancel = options.onCancel ?? null;
    this.onType = options.onType ?? null;
    this.active = true;
    this.element.focus({ preventScroll: true });
    this.element.setSelectionRange(this.value.length, this.value.length);
  }

  close(): void {
    this.active = false;
    this.onCommit = null;
    this.onCancel = null;
    this.onType = null;
    this.element.blur();
  }
}
