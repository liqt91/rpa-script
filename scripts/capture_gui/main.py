"""元素捕获 GUI — 独立桌面工具。

使用方法:
    python scripts/capture_gui/main.py

功能:
    - 点击"捕获"进入拾取模式（鼠标变十字，左键捕获，右键取消）
    - 元素列表：显示已捕获的元素
    - 属性面板：查看/编辑元素属性
    - 验证：反向查找元素并闪烁边框（绿=找到，红=失效）
"""

import os
import sys
import json
import tkinter as tk
from tkinter import ttk, messagebox

# 确保项目根目录在 path 中
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from scripts.capture_gui.overlay import ElementInfo, run_capture, flash_element
from scripts.capture_gui.store import ElementStore

DEFAULT_STORE_PATH = os.path.join(_project_root, "data", "captured_elements.json")

TYPE_LABELS = {"win32": "窗口", "uia": "UIA", "web": "网页"}
TYPE_COLORS = {"win32": "#7c3aed", "uia": "#059669", "web": "#2563eb"}
TYPE_ICONS = {"win32": "🪟", "uia": "🔍", "web": "🌐"}


class CaptureGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("元素捕获工具")
        self.root.geometry("900x600")
        self.root.minsize(700, 400)

        self.store = ElementStore(DEFAULT_STORE_PATH)
        self.selected_index = -1

        self._build_toolbar()
        self._build_panels()
        self._refresh_list()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Layout ────────────────────────────────────────────────

    def _build_toolbar(self):
        toolbar = ttk.Frame(self.root, padding=(8, 6))
        toolbar.pack(fill=tk.X)

        self.capture_btn = ttk.Button(
            toolbar, text="🔍 捕获元素", command=self._on_capture
        )
        self.capture_btn.pack(side=tk.LEFT, padx=(0, 12))

        ttk.Button(
            toolbar, text="🗑 删除选中", command=self._on_delete
        ).pack(side=tk.LEFT, padx=4)

        ttk.Button(
            toolbar, text="📂 保存", command=self._on_save
        ).pack(side=tk.LEFT, padx=4)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=12, pady=2)

        self.status_label = ttk.Label(toolbar, text="就绪")
        self.status_label.pack(side=tk.LEFT)

        ttk.Label(
            toolbar,
            text=f"共 {len(self.store)} 个元素",
            foreground="gray",
        ).pack(side=tk.RIGHT)

    def _build_panels(self):
        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        # ── 左侧：元素列表 ──
        left = ttk.Frame(paned)
        paned.add(left, weight=1)

        columns = ("name", "type", "class_name")
        self.tree = ttk.Treeview(
            left, columns=columns, show="headings",
            selectmode="browse",
        )
        self.tree.heading("name", text="名称")
        self.tree.heading("type", text="类型")
        self.tree.heading("class_name", text="类名")
        self.tree.column("name", width=160)
        self.tree.column("type", width=60, anchor=tk.CENTER)
        self.tree.column("class_name", width=140)
        self.tree.pack(fill=tk.BOTH, expand=True)

        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        scrollbar = ttk.Scrollbar(left, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # ── 右侧：属性面板 ──
        right = ttk.Frame(paned)
        paned.add(right, weight=1)

        props = ttk.LabelFrame(right, text="属性", padding=10)
        props.pack(fill=tk.X)

        self.prop_name = self._add_prop_row(props, "名称", editable=True)
        self.prop_type = self._add_prop_row(props, "类型")
        self.prop_class = self._add_prop_row(props, "类名")
        self.prop_ctrl_type = self._add_prop_row(props, "控件类型(UIA)")
        self.prop_auto_id = self._add_prop_row(props, "AutomationId")
        self.prop_rect = self._add_prop_row(props, "位置")
        self.prop_path_count = self._add_prop_row(props, "层级数")

        # 选择器面板 (web only)
        sel_frame = ttk.LabelFrame(right, text="选择器候选", padding=6)
        sel_frame.pack(fill=tk.X, pady=(6, 0))
        self.selector_var = tk.StringVar()
        self.selector_combo = ttk.Combobox(sel_frame, textvariable=self.selector_var, state="readonly")
        self.selector_combo.pack(fill=tk.X)
        self.selector_combo.bind("<<ComboboxSelected>>", self._on_selector_change)

        # 截图 (web only)
        self.screenshot_frame = ttk.LabelFrame(right, text="截图", padding=4)
        self.screenshot_frame.pack(fill=tk.X, pady=(6, 0))
        self.screenshot_label = ttk.Label(self.screenshot_frame, text="(选择web元素显示)")
        self.screenshot_label.pack()

        # 按钮行
        btn_frame = ttk.Frame(props)
        btn_frame.pack(fill=tk.X, pady=(12, 0))

        self.validate_btn = ttk.Button(
            btn_frame, text="🔍 验证", command=self._on_validate, state=tk.DISABLED
        )
        self.validate_btn.pack(side=tk.LEFT, padx=(0, 8))

        ttk.Button(
            btn_frame, text="📋 复制 JSON", command=self._on_copy_json, state=tk.DISABLED
        ).pack(side=tk.LEFT)

        # 详情文本框
        details_frame = ttk.LabelFrame(right, text="完整数据", padding=6)
        details_frame.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

        self.details_text = tk.Text(details_frame, height=12, wrap=tk.WORD,
                                     font=("Consolas", 9))
        self.details_text.pack(fill=tk.BOTH, expand=True)

    def _add_prop_row(self, parent, label, editable=False):
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, pady=2)
        ttk.Label(frame, text=label, width=14, anchor=tk.W).pack(side=tk.LEFT)
        if editable:
            var = tk.StringVar()
            entry = ttk.Entry(frame, textvariable=var)
            entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
            return var
        else:
            var = tk.StringVar()
            ttk.Label(frame, textvariable=var, foreground="#333").pack(
                side=tk.LEFT, anchor=tk.W
            )
            return var

    # ── Actions ───────────────────────────────────────────────

    def _on_capture(self):
        """进入捕获模式。"""
        self.set_status("捕获中：移动到目标上，左键捕获，右键/Esc 取消...")
        self.root.withdraw()  # 隐藏 GUI
        self.root.update()

        try:
            result = run_capture()
        finally:
            self.root.deiconify()  # 恢复 GUI

        if result:
            self.store.add(result)
            self._refresh_list()
            self.set_status(f"已捕获: {result.name or result.class_name}")
        else:
            self.set_status("已取消")

    def _on_delete(self):
        if self.selected_index < 0:
            return
        self.store.remove(self.selected_index)
        self.selected_index = -1
        self._refresh_list()
        self._clear_props()
        self.set_status("已删除")

    def _on_save(self):
        self.store.save()
        self.set_status(f"已保存 {len(self.store)} 个元素到 {DEFAULT_STORE_PATH}")

    def _on_validate(self):
        if self.selected_index < 0:
            return
        info = self.store.elements[self.selected_index]
        self.set_status(f"验证中: {info.name}...")
        self.root.withdraw()
        self.root.update()

        try:
            found = flash_element(info, times=3)
        finally:
            self.root.deiconify()

        if found:
            self.set_status(f"✅ 验证通过: {info.name}")
        else:
            self.set_status(f"❌ 元素失效: {info.name}")

    def _on_copy_json(self):
        if self.selected_index < 0:
            return
        info = self.store.elements[self.selected_index]
        from scripts.capture_gui.store import _info_to_dict
        data = _info_to_dict(info)
        text = json.dumps(data, ensure_ascii=False, indent=2)
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.set_status("已复制 JSON 到剪贴板")

    # ── UI updates ────────────────────────────────────────────

    def _refresh_list(self):
        self.tree.delete(*self.tree.get_children())
        for i, el in enumerate(self.store.elements):
            type_label = TYPE_LABELS.get(el.element_type, el.element_type)
            self.tree.insert("", tk.END, iid=str(i), values=(
                el.name, type_label, el.class_name,
            ))

    def _on_select(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        self.selected_index = int(sel[0])
        info = self.store.elements[self.selected_index]
        self._show_props(info)

    def _show_props(self, info: ElementInfo):
        self.prop_name.set(info.name)
        self.prop_type.set(TYPE_LABELS.get(info.element_type, info.element_type))
        self.prop_class.set(info.class_name)
        self.prop_ctrl_type.set(info.control_type)
        self.prop_auto_id.set(info.automation_id)
        r = info.rect
        self.prop_rect.set(f"({r.get('left', 0)}, {r.get('top', 0)}) {r.get('width', 0)}x{r.get('height', 0)}")
        path_len = max(len(info.win32_path), len(info.uia_path))
        self.prop_path_count.set(str(path_len))

        # 选择器候选
        candidates = info.candidates
        if candidates:
            values = [f"{c.get('family','?')}: {c.get('syntax','')[:80]}" for c in candidates]
            self.selector_combo['values'] = values
            if values:
                self.selector_var.set(values[0])
        else:
            self.selector_combo['values'] = []
            self.selector_var.set("(无)")

        # 截图
        if info.screenshot and info.screenshot.startswith("data:"):
            try:
                import base64, io
                from PIL import Image, ImageTk
                data_url = info.screenshot
                header, encoded = data_url.split(",", 1)
                img_data = base64.b64decode(encoded)
                img = Image.open(io.BytesIO(img_data))
                img.thumbnail((280, 200))
                self._screenshot_img = ImageTk.PhotoImage(img)
                self.screenshot_label.configure(image=self._screenshot_img, text="")
            except Exception:
                self.screenshot_label.configure(image="", text="(截图加载失败)")
        else:
            self.screenshot_label.configure(image="", text="(选择web元素显示)")

        # 详情 JSON
        from scripts.capture_gui.store import _info_to_dict
        data = _info_to_dict(info)
        self.details_text.delete("1.0", tk.END)
        self.details_text.insert("1.0", json.dumps(data, ensure_ascii=False, indent=2))
        self.validate_btn.configure(state=tk.NORMAL)

    def _on_selector_change(self, event=None):
        sel = self.tree.selection()
        if not sel: return
        info = self.store.elements[int(sel[0])]
        idx = self.selector_combo.current()
        if 0 <= idx < len(info.candidates):
            c = info.candidates[idx]
            self.details_text.delete("1.0", tk.END)
            self.details_text.insert("1.0", json.dumps(c, ensure_ascii=False, indent=2))

    def _clear_props(self):
        for var in [self.prop_name, self.prop_type, self.prop_class,
                     self.prop_ctrl_type, self.prop_auto_id,
                     self.prop_rect, self.prop_path_count]:
            var.set("")
        self.selector_combo['values'] = []
        self.selector_var.set("")
        self.screenshot_label.configure(image="", text="(选择web元素显示)")
        self.details_text.delete("1.0", tk.END)
        self.validate_btn.configure(state=tk.DISABLED)

    def set_status(self, text: str):
        self.status_label.configure(text=text)
        self.root.update_idletasks()

    def _on_close(self):
        self.store.save()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    app = CaptureGUI()
    app.run()


if __name__ == "__main__":
    main()
