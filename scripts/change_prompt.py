import tkinter as tk
from tkinter import ttk, messagebox
import json


class EscapeTextApp:
    """将多行文本转换为转义单行文本的 GUI 应用"""

    def __init__(self, root):
        self.root = root
        root.title("多行文本转义工具")
        root.geometry("700x500")
        root.minsize(500, 400)

        # 定界符选择变量：'double', 'single', 'none'
        self.quote_type = tk.StringVar(value='double')

        # 是否添加外围引号（如 "..."）
        self.add_quotes = tk.BooleanVar(value=False)

        self._create_widgets()

    def _create_widgets(self):
        # 主框架，使用 grid 布局
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 输入区域
        ttk.Label(main_frame, text="输入多行文本：").grid(row=0, column=0, sticky=tk.W)
        self.input_text = tk.Text(main_frame, height=12, width=80, wrap=tk.WORD)
        input_scroll = ttk.Scrollbar(main_frame, orient=tk.VERTICAL, command=self.input_text.yview)
        self.input_text.configure(yscrollcommand=input_scroll.set)
        self.input_text.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        input_scroll.grid(row=1, column=1, sticky=(tk.N, tk.S), pady=(0, 10))

        # 选项框架
        options_frame = ttk.LabelFrame(main_frame, text="转义选项", padding="5")
        options_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

        ttk.Label(options_frame, text="目标字符串定界符：").grid(row=0, column=0, padx=(0, 10))
        ttk.Radiobutton(options_frame, text="双引号 (\"...\")", variable=self.quote_type, value='double').grid(row=0,
                                                                                                               column=1,
                                                                                                               padx=5)
        ttk.Radiobutton(options_frame, text="单引号 ('...')", variable=self.quote_type, value='single').grid(row=0,
                                                                                                             column=2,
                                                                                                             padx=5)
        ttk.Radiobutton(options_frame, text="无（仅转义控制字符）", variable=self.quote_type, value='none').grid(row=0,
                                                                                                               column=3,
                                                                                                               padx=5)

        ttk.Checkbutton(options_frame, text="在结果外添加包围引号", variable=self.add_quotes).grid(row=1, column=0,
                                                                                                   columnspan=4,
                                                                                                   sticky=tk.W,
                                                                                                   pady=(5, 0))

        # 按钮
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=(0, 10))
        self.convert_btn = ttk.Button(btn_frame, text="转换", command=self.convert)
        self.convert_btn.pack(side=tk.LEFT, padx=(0, 10))
        self.copy_btn = ttk.Button(btn_frame, text="复制结果到剪贴板", command=self.copy_result)
        self.copy_btn.pack(side=tk.LEFT)

        # 输出区域
        ttk.Label(main_frame, text="转义结果（单行）：").grid(row=4, column=0, sticky=tk.W)
        self.output_text = tk.Text(main_frame, height=4, width=80, wrap=tk.NONE, state=tk.DISABLED)
        output_scroll = ttk.Scrollbar(main_frame, orient=tk.VERTICAL, command=self.output_text.yview)
        self.output_text.configure(yscrollcommand=output_scroll.set)
        self.output_text.grid(row=5, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 5))
        output_scroll.grid(row=5, column=1, sticky=(tk.N, tk.S), pady=(0, 5))

        # 配置网格权重，使文本框可缩放
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)  # 输入框可垂直拉伸
        main_frame.rowconfigure(5, weight=0)  # 输出框不抢高度

    def escape_text(self, text):
        """根据当前选项转义文本，返回转义后的字符串（不包含外围引号，除非 add_quotes 为 True）"""
        if not text:
            return ""

        quote = self.quote_type.get()

        # 转义核心：对控制字符和所选定界符进行转义
        result_chars = []
        for ch in text:
            if ch == '\\':
                result_chars.append('\\\\')
            elif ch == '\n':
                result_chars.append('\\n')
            elif ch == '\r':
                result_chars.append('\\r')
            elif ch == '\t':
                result_chars.append('\\t')
            elif ch == '"' and quote == 'double':
                result_chars.append('\\"')
            elif ch == "'" and quote == 'single':
                result_chars.append("\\'")
            elif ord(ch) < 0x20 or ord(ch) == 0x7f:  # 其他控制字符
                result_chars.append('\\x{:02x}'.format(ord(ch)))
            else:
                result_chars.append(ch)

        escaped = ''.join(result_chars)

        # 是否添加包围引号
        if self.add_quotes.get():
            if quote == 'double':
                escaped = '"' + escaped + '"'
            elif quote == 'single':
                escaped = "'" + escaped + "'"
            # none 时添加引号无意义，也可不处理

        return escaped

    def convert(self):
        """执行转换，并将结果显示在输出框中"""
        input_str = self.input_text.get("1.0", "end-1c")  # 获取全部文本，去除末尾自动添加的换行
        try:
            result = self.escape_text(input_str)
        except Exception as e:
            messagebox.showerror("转换错误", f"文本转义失败：{str(e)}")
            return

        # 更新输出框
        self.output_text.configure(state=tk.NORMAL)
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert("1.0", result)
        self.output_text.configure(state=tk.DISABLED)

    def copy_result(self):
        """将输出框内容复制到剪贴板"""
        result = self.output_text.get("1.0", "end-1c")
        if result:
            self.root.clipboard_clear()
            self.root.clipboard_append(result)
            # 可选提示
            self.copy_btn.config(text="已复制！")
            self.root.after(1500, lambda: self.copy_btn.config(text="复制结果到剪贴板"))
        else:
            messagebox.showinfo("提示", "没有可以复制的内容，请先执行转换。")


def main():
    root = tk.Tk()
    app = EscapeTextApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()