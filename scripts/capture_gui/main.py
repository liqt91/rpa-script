"""元素捕获 GUI — 独立桌面工具。

使用方法:
    python scripts/capture_gui/main.py
"""

import os
import sys
import json
import tkinter as tk
from tkinter import ttk, messagebox

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from scripts.capture_gui.overlay import ElementInfo, run_capture, flash_element
from scripts.capture_gui.store import ElementStore

DEFAULT_STORE_PATH = os.path.join(_project_root, "data", "captured_elements.json")

TYPE_LABELS = {"win32": "窗口", "uia": "UIA", "web": "网页"}
TYPE_ICONS = {"win32": "🪟", "uia": "🔍", "web": "🌐"}


class CaptureGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("元素捕获工具")
        self.root.geometry("900x650")
        self.root.minsize(750, 500)

        self.store = ElementStore(DEFAULT_STORE_PATH)
        self._candidates = []
        self._cand_idx = -1

        self._build_toolbar()
        self._build_panels()
        self._refresh_list()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Layout ──

    def _build_toolbar(self):
        toolbar = ttk.Frame(self.root, padding=(8, 6))
        toolbar.pack(fill=tk.X)

        self.capture_btn = ttk.Button(toolbar, text="🔍 捕获元素", command=self._on_capture)
        self.capture_btn.pack(side=tk.LEFT, padx=(0, 12))

        ttk.Button(toolbar, text="🗑 删除选中", command=self._on_delete).pack(side=tk.LEFT, padx=4)
        ttk.Button(toolbar, text="📂 保存", command=self._on_save).pack(side=tk.LEFT, padx=4)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=12, pady=2)

        self.status_label = ttk.Label(toolbar, text="就绪")
        self.status_label.pack(side=tk.LEFT)

        ttk.Label(toolbar, text=f"共 {len(self.store)} 个元素", foreground="gray").pack(side=tk.RIGHT)

    def _build_panels(self):
        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        # 左侧 — 元素列表
        left = ttk.Frame(paned)
        paned.add(left, weight=1)

        columns = ("name", "type", "class_name")
        self.tree = ttk.Treeview(left, columns=columns, show="headings", selectmode="browse")
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

        # 右侧 — 详情
        right = ttk.Frame(paned)
        paned.add(right, weight=1)

        # 属性
        props = ttk.LabelFrame(right, text="属性", padding=10)
        props.pack(fill=tk.X)
        self.prop_name = self._add_prop_row(props, "名称", editable=True)
        self.prop_type = self._add_prop_row(props, "类型")
        self.prop_class = self._add_prop_row(props, "类名")
        self.prop_ctrl_type = self._add_prop_row(props, "控件类型(UIA)")
        self.prop_rect = self._add_prop_row(props, "位置")

        # 模式切换
        mode_frame = ttk.Frame(right)
        mode_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Label(mode_frame, text="选择器", font=("", 10, "bold")).pack(side=tk.LEFT)
        self.mode_btn2 = ttk.Button(mode_frame, text="手动编辑", width=10,
                                     command=lambda: self._switch_mode(1))
        self.mode_btn2.pack(side=tk.RIGHT, padx=(2, 0))
        self.mode_btn1 = ttk.Button(mode_frame, text="推荐方案", width=10,
                                     command=lambda: self._switch_mode(0))
        self.mode_btn1.pack(side=tk.RIGHT)

        # 推荐方案
        self.recommend_panel = ttk.Frame(right)
        self.recommend_panel.pack(fill=tk.X)
        self.selector_listbox = tk.Listbox(self.recommend_panel, height=5,
                                            font=("Consolas", 9), exportselection=False)
        self.selector_listbox.pack(fill=tk.X, pady=(4, 0))
        self.selector_listbox.bind("<<ListboxSelect>>", self._on_candidate_select)
        btn_row = ttk.Frame(self.recommend_panel)
        btn_row.pack(fill=tk.X, pady=(4, 0))
        ttk.Button(btn_row, text="📋 复制", width=8, command=self._copy_candidate).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(btn_row, text="✓ 测试", width=8, command=self._test_candidate).pack(side=tk.LEFT)

        # 手动编辑 — 交互 DOM 路径
        self.manual_panel = ttk.Frame(right)
        dom_frame = ttk.LabelFrame(self.manual_panel, text="DOM 层级 (勾选参与生成)", padding=4)
        dom_frame.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        self.dom_canvas = tk.Canvas(dom_frame, height=150, highlightthickness=0)
        self.dom_scroll = ttk.Scrollbar(dom_frame, orient=tk.VERTICAL, command=self.dom_canvas.yview)
        self.dom_inner = ttk.Frame(self.dom_canvas)
        self.dom_canvas.configure(yscrollcommand=self.dom_scroll.set)
        self.dom_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.dom_canvas.pack(fill=tk.BOTH, expand=True)
        self.dom_win = self.dom_canvas.create_window((0, 0), window=self.dom_inner, anchor="nw")
        self.dom_inner.bind("<Configure>", lambda e: self.dom_canvas.configure(scrollregion=self.dom_canvas.bbox("all")))
        # 选择器预览
        selprev_frame = ttk.Frame(self.manual_panel)
        selprev_frame.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(selprev_frame, text="生成：", font=("", 9)).pack(side=tk.LEFT)
        self.selector_preview = ttk.Entry(selprev_frame, font=("Consolas", 9))
        self.selector_preview.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))
        ttk.Button(selprev_frame, text="📋", width=3, command=self._copy_preview).pack(side=tk.LEFT)
        self.manual_panel.pack_forget()

        # 元素特征
        feat_frame = ttk.LabelFrame(right, text="元素特征", padding=4)
        feat_frame.pack(fill=tk.X, pady=(8, 0))
        self.feat_text = tk.Text(feat_frame, height=5, font=("Consolas", 9), state=tk.DISABLED)
        self.feat_text.pack(fill=tk.X)

        # 截图
        self.screenshot_frame = ttk.LabelFrame(right, text="截图", padding=4)
        self.screenshot_frame.pack(fill=tk.X, pady=(8, 0))
        self.screenshot_label = ttk.Label(self.screenshot_frame, text="(选择web元素显示)")
        self.screenshot_label.pack()

        # 按钮行
        btn_frame = ttk.Frame(right)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        self.validate_btn = ttk.Button(btn_frame, text="🔍 验证", command=self._on_validate, state=tk.DISABLED)
        self.validate_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.json_btn = ttk.Button(btn_frame, text="📋 JSON", command=self._on_show_json, state=tk.DISABLED)
        self.json_btn.pack(side=tk.LEFT)

    def _add_prop_row(self, parent, label, editable=False):
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, pady=2)
        ttk.Label(frame, text=label, width=14, anchor=tk.W).pack(side=tk.LEFT)
        if editable:
            var = tk.StringVar()
            ttk.Entry(frame, textvariable=var).pack(side=tk.LEFT, fill=tk.X, expand=True)
            return var
        else:
            var = tk.StringVar()
            ttk.Label(frame, textvariable=var, foreground="#333").pack(side=tk.LEFT, anchor=tk.W)
            return var

    # ── Actions ──

    def _on_capture(self):
        self.set_status("捕获中：移动到目标上，左键捕获，右键/Esc 取消...")
        self.root.withdraw()
        self.root.update()
        try:
            result = run_capture()
        finally:
            self.root.deiconify()

        if result:
            self.store.add(result)
            self.set_status(f"已捕获: {result.name}")
        else:
            self.set_status("已取消")
        self._refresh_list()

    def _on_delete(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请先选中一个元素")
            return
        idx = int(sel[0])
        if messagebox.askyesno("确认", f"删除元素 '{self.store.elements[idx].name}'？"):
            self.store.remove(idx)
            self._refresh_list()
            self._clear_props()

    def _on_validate(self):
        sel = self.tree.selection()
        if not sel: return
        info = self.store.elements[int(sel[0])]
        self.set_status("验证中...")
        self.root.withdraw()
        self.root.update()
        try:
            alive = flash_element(info, times=3)
        finally:
            self.root.deiconify()
        self.set_status("✅ 元素仍然存在" if alive else "❌ 无法找到元素")

    def _on_save(self):
        sel = self.tree.selection()
        if sel:
            info = self.store.elements[int(sel[0])]
            new_name = self.prop_name.get().strip()
            if new_name and new_name != info.name:
                info.name = new_name
        self.store.save()
        self.set_status("已保存")
        self._refresh_list()

    def _on_show_json(self):
        sel = self.tree.selection()
        if not sel: return
        info = self.store.elements[int(sel[0])]
        from scripts.capture_gui.store import _info_to_dict
        data = _info_to_dict(info)
        text = json.dumps(data, ensure_ascii=False, indent=2)
        popup = tk.Toplevel(self.root)
        popup.title(f"JSON: {info.name}")
        popup.geometry("500x400")
        txt = tk.Text(popup, font=("Consolas", 10), wrap=tk.WORD)
        txt.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        txt.insert("1.0", text)
        txt.configure(state=tk.DISABLED)

    def _on_close(self):
        self.store.save()
        self.root.destroy()

    # ── Selector panel ──

    def _switch_mode(self, mode):
        if mode == 0:
            self.recommend_panel.pack(fill=tk.X, before=self.screenshot_frame)
            self.manual_panel.pack_forget()
        else:
            self.recommend_panel.pack_forget()
            self.manual_panel.pack(fill=tk.BOTH, expand=True, before=self.screenshot_frame)
            self._build_dom_checkboxes()

    def _on_candidate_select(self, event=None):
        sel = self.selector_listbox.curselection()
        self._cand_idx = sel[0] if sel else -1

    def _copy_candidate(self):
        if self._cand_idx < 0 or self._cand_idx >= len(self._candidates):
            return
        syntax = self._candidates[self._cand_idx].get("syntax", "")
        if syntax:
            self.root.clipboard_clear()
            self.root.clipboard_append(syntax)
            self.set_status(f"已复制: {syntax[:60]}...")

    def _test_candidate(self):
        if self._cand_idx < 0 or self._cand_idx >= len(self._candidates):
            return
        c = self._candidates[self._cand_idx]
        text = (
            f"Family: {c.get('family','?')}\n"
            f"Type: {c.get('type','?')}\n"
            f"Syntax:\n{c.get('syntax','')}\n\n"
            f"Full:\n{json.dumps(c, ensure_ascii=False, indent=2)}"
        )
        popup = tk.Toplevel(self.root)
        popup.title("选择器详情")
        popup.geometry("500x350")
        txt = tk.Text(popup, font=("Consolas", 10), wrap=tk.WORD)
        txt.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        txt.insert("1.0", text)
        txt.configure(state=tk.DISABLED)

    # ── Display ──

    def _show_props(self, info: ElementInfo):
        self.prop_name.set(info.name)
        self.prop_type.set(TYPE_LABELS.get(info.element_type, info.element_type))
        self.prop_class.set(info.class_name)
        self.prop_ctrl_type.set(info.control_type or info.automation_id)
        r = info.rect
        self.prop_rect.set(f"({r.get('left',0)},{r.get('top',0)}) {r.get('width',0)}x{r.get('height',0)}")

        # 候选列表 (含 badges)
        self.selector_listbox.delete(0, tk.END)
        self._candidates = info.candidates
        self._cand_idx = -1
        if self._candidates:
            for c in self._candidates:
                fam = (c.get("family") or c.get("type") or "?").upper()
                syn = c.get("syntax", "")[:80]
                badges = []
                mc = c.get("matchCount", -1)
                if mc == 1: badges.append("✓唯一")
                elif mc > 1: badges.append(f"×{mc}")
                if c.get("isList"): badges.append("⊞列表")
                if c.get("score"): badges.append(f"{c['score']:.0%}")
                badge_str = " ".join(badges)
                self.selector_listbox.insert(tk.END, f"[{fam}] {syn}  {badge_str}")
            self.selector_listbox.selection_set(0)
            self._cand_idx = 0
        else:
            self.selector_listbox.insert(tk.END, "(无候选)")

        # 元素特征
        self._show_features(info)

        # DOM 路径 — 存为 path_vars 供手动编辑用
        self._dom_path = info.dom_path
        self._dom_attrs = info.elem_attrs
        self._dom_checked = [tk.BooleanVar(value=True) for _ in self._dom_path]

        # 截图
        if info.screenshot and info.screenshot.startswith("data:"):
            try:
                import base64, io
                from PIL import Image, ImageTk
                header, encoded = info.screenshot.split(",", 1)
                img_data = base64.b64decode(encoded)
                img = Image.open(io.BytesIO(img_data))
                img.thumbnail((280, 200))
                self._screenshot_img = ImageTk.PhotoImage(img)
                self.screenshot_label.configure(image=self._screenshot_img, text="")
            except Exception:
                self.screenshot_label.configure(image="", text="(截图加载失败)")
        else:
            self.screenshot_label.configure(image="", text="(选择web元素显示)")

        self.validate_btn.configure(state=tk.NORMAL)
        self.json_btn.configure(state=tk.NORMAL)
        self._switch_mode(0)

    def _show_features(self, info: ElementInfo):
        lines = []
        if info.tag_name:
            lines.append(f"Tag:     {info.tag_name}")
        if info.dom_path:
            lines.append(f"Depth:   {len(info.dom_path)} 层")
            if info.dom_path:
                lines.append(f"Leaf:    {info.dom_path[-1][:100]}")
        if info.css_selector:
            lines.append(f"CSS:     {info.css_selector[:120]}")
        if info.xpath:
            lines.append(f"XPath:   {info.xpath[:120]}")
        # 候选匹配
        mcs = {c.get("matchCount") for c in (self._candidates or []) if c.get("matchCount")}
        if mcs:
            lines.append(f"Matches: {', '.join(str(m) for m in sorted(mcs))}")
        # 列表检测
        li = info.list_info or {}
        if li:
            parts = []
            if li.get("listContainer"): parts.append(f"容器:{li['listContainer']}")
            if li.get("listItem"): parts.append(f"项:{li['listItem']}")
            if li.get("listSize"): parts.append(f"数量:{li['listSize']}")
            if li.get("listSimilarity"): parts.append(f"相似度:{li['listSimilarity']:.0%}")
            if parts: lines.append("List:    " + " | ".join(parts))
        self.feat_text.configure(state=tk.NORMAL)
        self.feat_text.delete("1.0", tk.END)
        self.feat_text.insert("1.0", "\n".join(lines) or "(无)")
        self.feat_text.configure(state=tk.DISABLED)

    def _clear_props(self):
        for var in [self.prop_name, self.prop_type, self.prop_class,
                     self.prop_ctrl_type, self.prop_rect]:
            var.set("")
        self.selector_listbox.delete(0, tk.END)
        self._candidates = []
        self._cand_idx = -1
        self._dom_path = []
        self._dom_checked = []
        self.feat_text.configure(state=tk.NORMAL)
        self.feat_text.delete("1.0", tk.END)
        self.feat_text.configure(state=tk.DISABLED)
        self.screenshot_label.configure(image="", text="(选择web元素显示)")
        self.validate_btn.configure(state=tk.DISABLED)
        self.json_btn.configure(state=tk.DISABLED)

    # ── List ──

    def _refresh_list(self):
        selected = self.tree.selection()
        sel_idx = int(selected[0]) if selected else -1
        self.tree.delete(*self.tree.get_children())
        for i, e in enumerate(self.store.elements):
            icon = TYPE_ICONS.get(e.element_type, "❓")
            self.tree.insert("", tk.END, iid=str(i),
                             values=(f"{icon} {e.name}",
                                     TYPE_LABELS.get(e.element_type, e.element_type),
                                     e.class_name))
        if 0 <= sel_idx < len(self.store.elements):
            self.tree.selection_set(str(sel_idx))
            self.tree.see(str(sel_idx))

    def _on_select(self, event):
        sel = self.tree.selection()
        if not sel:
            self._clear_props()
            return
        idx = int(sel[0])
        if idx < len(self.store.elements):
            self._show_props(self.store.elements[idx])

    def set_status(self, text: str):
        self.status_label.configure(text=text)
        print(f"[CaptureGUI] {text}")

    # ── DOM 交互 ──

    def _build_dom_checkboxes(self, reuse_checkboxes=False):
        for w in self.dom_inner.winfo_children():
            w.destroy()
        path = getattr(self, '_dom_path', [])
        if not reuse_checkboxes or not hasattr(self, '_dom_checked') or len(self._dom_checked) != len(path):
            self._dom_checked = [tk.BooleanVar(value=True) for _ in path]
        for i, seg in enumerate(path):
            row = ttk.Frame(self.dom_inner)
            row.pack(fill=tk.X, pady=1)
            cb = ttk.Checkbutton(row, variable=self._dom_checked[i],
                                  command=self._update_selector_preview)
            cb.pack(side=tk.LEFT)
            indent = "  " * i
            ttk.Label(row, text=f"{indent}{seg[:120]}", font=("Consolas", 9)).pack(side=tk.LEFT)
        self._update_selector_preview()

    def _update_selector_preview(self):
        path = getattr(self, '_dom_path', [])
        checked = getattr(self, '_dom_checked', [])
        parts = [seg for i, seg in enumerate(path) if i < len(checked) and checked[i].get()]
        selector = " > ".join(parts) if parts else "(未选择层级)"
        self.selector_preview.delete(0, tk.END)
        self.selector_preview.insert(0, selector)

    def _copy_preview(self):
        val = self.selector_preview.get()
        if val:
            self.root.clipboard_clear()
            self.root.clipboard_append(val)
            self.set_status(f"已复制: {val[:60]}...")


if __name__ == "__main__":
    app = CaptureGUI()
    app.root.mainloop()
