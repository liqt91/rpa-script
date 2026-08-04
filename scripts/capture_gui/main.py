"""元素捕获 GUI — 独立桌面工具。"""
import os, sys, json, base64, io
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
        self.root.geometry("1000x650")
        self.root.minsize(800, 500)
        self.store = ElementStore(DEFAULT_STORE_PATH)
        self._candidates = []
        self._cur_sel = ""
        self._populating = False
        s = ttk.Style()
        s.configure("Active.TButton", background="#3b82f6", foreground="white")
        self._build_toolbar()
        self._build_panels()
        self._refresh_list()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Toolbar ──
    def _build_toolbar(self):
        tb = ttk.Frame(self.root, padding=(8, 6)); tb.pack(fill=tk.X)
        ttk.Button(tb, text="🔍 捕获元素", command=self._on_capture).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Button(tb, text="🗑 删除选中", command=self._on_delete).pack(side=tk.LEFT, padx=4)
        ttk.Button(tb, text="📂 保存", command=self._on_save_all).pack(side=tk.LEFT, padx=4)
        ttk.Separator(tb, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=12, pady=2)
        self.status_label = ttk.Label(tb, text="就绪"); self.status_label.pack(side=tk.LEFT)
        ttk.Label(tb, text=f"共 {len(self.store)} 个元素", foreground="gray").pack(side=tk.RIGHT)

    # ── Panels ──
    def _build_panels(self):
        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        # Left: list
        left = ttk.Frame(paned); paned.add(left, weight=1)
        cols = ("name", "type", "sel")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", selectmode="browse")
        self.tree.heading("name", text="名称"); self.tree.heading("type", text="类型"); self.tree.heading("sel", text="选择器")
        self.tree.column("name", width=140); self.tree.column("type", width=50, anchor=tk.CENTER); self.tree.column("sel", width=100)
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        sb = ttk.Scrollbar(left, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set); sb.pack(side=tk.RIGHT, fill=tk.Y)

        # Right: detail
        right = ttk.Frame(paned); paned.add(right, weight=1)

        # 名称行 + 截图缩略图
        name_row = ttk.Frame(right); name_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(name_row, text="名称", width=5).pack(side=tk.LEFT)
        self.var_name = tk.StringVar()
        ttk.Entry(name_row, textvariable=self.var_name).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        self.thumb_btn = ttk.Label(name_row, text="📷", cursor="hand2")
        self.thumb_btn.pack(side=tk.LEFT, padx=4)
        self.thumb_btn.bind("<Button-1>", self._show_screenshot_large)
        self._thumb_img = None

        # Tab: 推荐方案 / 手动编辑
        tab_row = ttk.Frame(right); tab_row.pack(fill=tk.X, pady=(6, 0))
        self.btn_recommend = ttk.Button(tab_row, text="推荐方案", width=12,
                                         command=lambda: self._switch_sel_tab(0))
        self.btn_recommend.pack(side=tk.LEFT, padx=(0, 2))
        self.btn_manual = ttk.Button(tab_row, text="手动编辑", width=12,
                                      command=lambda: self._switch_sel_tab(1))
        self.btn_manual.pack(side=tk.LEFT)

        # 推荐方案 Treeview
        mid = ttk.Frame(right); mid.pack(fill=tk.BOTH, expand=True)
        self.tab0 = ttk.Frame(mid)
        rc_cols = ("syntax", "family", "match")
        self.cand_tree = ttk.Treeview(self.tab0, columns=rc_cols, show="headings",
                                       selectmode="browse", height=6)
        self.cand_tree.heading("syntax", text="选择器", command=lambda: self._sort_cands("syntax"))
        self.cand_tree.heading("family", text="类型", command=lambda: self._sort_cands("family"))
        self.cand_tree.heading("match", text="匹配", command=lambda: self._sort_cands("match"))
        self.cand_tree.column("syntax", width=240); self.cand_tree.column("family", width=50, anchor=tk.CENTER)
        self.cand_tree.column("match", width=45, anchor=tk.CENTER)
        self.cand_tree.pack(fill=tk.X, pady=(4, 0))
        self.cand_tree.bind("<<TreeviewSelect>>", self._on_cand_tree_select)
        self.tab0.pack(fill=tk.BOTH, expand=True)
        # Initially visible below tab buttons
        pass  # tab0_forget

        # 手动编辑: DOM 路径
        self.tab1 = ttk.Frame(mid)
        self.dom_canvas = tk.Canvas(self.tab1, height=200, highlightthickness=0)
        dom_sb = ttk.Scrollbar(self.tab1, orient=tk.VERTICAL, command=self.dom_canvas.yview)
        self.dom_inner = ttk.Frame(self.dom_canvas)
        self.dom_canvas.configure(yscrollcommand=dom_sb.set)
        dom_sb.pack(side=tk.RIGHT, fill=tk.Y); self.dom_canvas.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        self.dom_win = self.dom_canvas.create_window((0, 0), window=self.dom_inner, anchor="nw")
        self.dom_inner.bind("<Configure>", lambda e: self.dom_canvas.configure(scrollregion=self.dom_canvas.bbox("all")))
        pass  # tab1_forget

        # 选择器预览 (公用)
        bot = ttk.Frame(right); bot.pack(fill=tk.X, pady=(6,0))
        sel_row = ttk.Frame(bot); sel_row.pack(fill=tk.X)
        ttk.Label(sel_row, text="选择器", width=5).pack(side=tk.LEFT)
        self.sel_text = tk.Text(sel_row, height=3, font=("Consolas", 9), wrap=tk.WORD)
        self.sel_text.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ttk.Button(sel_row, text="📋", width=3, command=self._copy_selector).pack(side=tk.LEFT)

        # 按钮行
        btn_row = ttk.Frame(bot); btn_row.pack(fill=tk.X, pady=(6,0))
        self.btn_validate = ttk.Button(btn_row, text="🔍 验证", command=self._on_validate, state=tk.DISABLED)
        self.btn_validate.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_save_sel = ttk.Button(btn_row, text="💾 保存选择器", command=self._save_selector, state=tk.DISABLED)
        self.btn_save_sel.pack(side=tk.LEFT)

        self.current_sel_tab = 0

    # ── Actions ──
    def _on_capture(self):
        self.set_status("捕获中...")
        self.root.withdraw(); self.root.update()
        try: result = run_capture()
        finally: self.root.deiconify()
        if result: self.store.add(result); self.set_status(f"已捕获: {result.name}")
        else: self.set_status("已取消")
        self._refresh_list()

    def _on_delete(self):
        sel = self.tree.selection()
        if not sel: messagebox.showwarning("提示", "请先选中一个元素"); return
        idx = int(sel[0])
        if messagebox.askyesno("确认", f"删除 '{self.store.elements[idx].name}'？"):
            self.store.remove(idx); self._refresh_list(); self._clear_panel()

    def _on_validate(self):
        sel = self.tree.selection()
        if not sel: return
        info = self.store.elements[int(sel[0])]
        if info.element_type == "web":
            self._verify_web()
        else:
            self._verify_desktop(info)

    def _verify_web(self):
        t = self.sel_text.get("1.0", tk.END).strip()
        for prefix in ("css:", "xpath:", "drission:"):
            if t.lower().startswith(prefix): t = t[len(prefix):]; break
        if not t: self.set_status("选择器为空"); return
        self.set_status(f"验证: {t[:50]}...")
        try:
            import urllib.request, json, uuid
            data = json.dumps({"selector": t, "requestId": str(uuid.uuid4())[:8]}).encode()
            req = urllib.request.Request("http://127.0.0.1:8000/api/extension/verify-selector",
                                          data=data, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=8) as resp:
                r = json.loads(resp.read().decode())
            self.set_status(f"✅ 匹配 {r.get('count',1)} 个" if r.get("found") else f"❌ {r.get('error','未找到')}")
        except Exception as e:
            self.set_status(f"验证失败: {e}")

    def _verify_desktop(self, info):
        self.set_status("验证中...")
        self.root.withdraw(); self.root.update()
        try: alive = flash_element(info, times=3)
        finally: self.root.deiconify()
        self.set_status("✅ 存在" if alive else "❌ 失效")

    def _on_save_all(self):
        sel = self.tree.selection()
        if sel:
            info = self.store.elements[int(sel[0])]
            n = self.var_name.get().strip()
            if n and n != info.name: info.name = n
        self.store.save(); self.set_status("已保存"); self._refresh_list()

    def _save_selector(self):
        sel = self.tree.selection()
        if not sel: return
        idx = int(sel[0])
        info = self.store.elements[idx]
        new_sel = self.sel_text.get("1.0", tk.END).strip()
        if new_sel:
            info.css_selector = new_sel
            self.store.save()
            self.tree.set(str(idx), "sel", new_sel[:50])
            self.set_status(f"已保存: {new_sel[:50]}...")

    def _show_screenshot_large(self, event=None):
        if not self._thumb_img: return
        popup = tk.Toplevel(self.root)
        popup.title("截图")
        popup.geometry("600x450")
        lbl = ttk.Label(popup, image=self._thumb_img)
        lbl.pack(expand=True)

    def _on_close(self):
        self.store.save(); self.root.destroy()

    def _set_sel_text(self, text):
        self.sel_text.configure(state=tk.NORMAL)
        self.sel_text.delete("1.0", tk.END)
        self.sel_text.insert("1.0", text)

    def _copy_selector(self):
        val = self.sel_text.get("1.0", tk.END).strip()
        if val: self.root.clipboard_clear(); self.root.clipboard_append(val); self.set_status("已复制")

    # ── Selector tabs ──
    def _switch_sel_tab(self, tab):
        self.current_sel_tab = tab
        if tab == 0:
            self.tab1.pack_forget()
            self.tab0.pack(fill=tk.BOTH, expand=True)
            self.btn_recommend.configure(style="Active.TButton")
            self.btn_manual.configure(style="TButton")
        else:
            self.tab0.pack_forget()
            self.tab1.pack(fill=tk.BOTH, expand=True)
            self.btn_recommend.configure(style="TButton")
            self.btn_manual.configure(style="Active.TButton")
            self.tab1.pack(fill=tk.BOTH, expand=True, before=self.sel_text.master)

    _sort_cands_dir = {"syntax": False, "family": False, "match": False}
    def _sort_cands(self, col):
        self._sort_cands_dir[col] = not self._sort_cands_dir[col]
        rev = self._sort_cands_dir[col]
        idx = {"syntax": 0, "family": 1, "match": 2}[col]
        self._sorted_cands.sort(key=lambda x: str(self._cand_sort_key(x, idx)), reverse=rev)
        self.cand_tree.delete(*self.cand_tree.get_children())
        for i, c in enumerate(self._sorted_cands):
            fam = (c.get("family") or "?").upper()
            mc_str = str(c.get("matchCount", ""))
            self.cand_tree.insert("", tk.END, iid=str(i), values=(c.get("syntax","")[:120], fam, mc_str))

    def _cand_sort_key(self, c, idx):
        if idx == 2: return c.get("matchCount", 0) or 0
        return c.get(["syntax","family","match"][idx], "") or ""

    def _on_cand_tree_select(self, event=None):
        if self._populating: return  # 初始化时不覆盖选择器
        sel = self.cand_tree.selection()
        if sel:
            idx = int(sel[0])
            cands = self._sorted_cands
            if idx < len(cands):
                syn = cands[idx].get("syntax", "")
                for pf in ("css:", "xpath:", "drission:"):
                    if syn.lower().startswith(pf): syn = syn[len(pf):]; break
                self._set_sel_text(syn)

    # ── Display ──
    def _show_props(self, info: ElementInfo):
        self._populating = True  # 防止 selection_set 触发覆盖
        self.var_name.set(info.name)
        is_web = info.element_type == "web"

        # 截图缩略图
        self._thumb_img = None
        if info.screenshot and info.screenshot.startswith("data:"):
            try:
                from PIL import Image, ImageTk
                header, enc = info.screenshot.split(",", 1)
                img = Image.open(io.BytesIO(base64.b64decode(enc)))
                img.thumbnail((40, 30))
                self._thumb_img = ImageTk.PhotoImage(img)
                self.thumb_btn.configure(image=self._thumb_img, text="")
            except: self.thumb_btn.configure(image="", text="📷")
        else:
            self.thumb_btn.configure(image="", text="📷")

        # 候选
        self.cand_tree.delete(*self.cand_tree.get_children())
        if info.candidates and is_web:
            # 过滤: 只要 css/xpath
            filtered = [c for c in info.candidates if (c.get("family") or c.get("type","")).lower() in ("css","xpath")]
            self._sorted_cands = filtered[:]
            for i, c in enumerate(filtered):
                fam = (c.get("family") or "?").upper()
                mc = c.get("matchCount", "")
                mc_str = str(mc) if mc else ""
                self.cand_tree.insert("", tk.END, iid=str(i),
                                       values=(c.get("syntax", "")[:120], fam, mc_str))
            if filtered:
                self.cand_tree.selection_set("0")
                if info.css_selector:
                    syn_d = info.css_selector
                    for pf in ("css:", "xpath:", "drission:"):
                        if syn_d.lower().startswith(pf): syn_d = syn_d[len(pf):]; break
                    self._set_sel_text(syn_d)
                else:
                    syn0 = filtered[0].get("syntax", "")
                    for pf in ("css:", "xpath:", "drission:"):
                        if syn0.lower().startswith(pf): syn0 = syn0[len(pf):]; break
                    self._set_sel_text(syn0)
        elif not is_web:
            self.cand_tree.insert("", tk.END, values=("(非web元素)", "", ""))

        # 显示对应 tab
        if is_web:
            self.btn_recommend.configure(state=tk.NORMAL)
            self.btn_manual.configure(state=tk.NORMAL)
            self.sel_text.configure(state=tk.NORMAL)
            self.btn_save_sel.configure(state=tk.NORMAL)
            self._switch_sel_tab(self.current_sel_tab)
        else:
            pass  # tab0_forget
            pass  # tab1_forget
            self._set_sel_text(info.css_selector or "")
            self.sel_text.configure(state=tk.DISABLED)
            self.btn_recommend.configure(state=tk.DISABLED)
            self.btn_manual.configure(state=tk.DISABLED)
            self.btn_save_sel.configure(state=tk.DISABLED)

        # DOM 数据存好
        self._dom_path = info.dom_path if is_web else []
        self._dom_checked = []
        self._build_dom_checkboxes()

        self.btn_validate.configure(state=tk.NORMAL)
        # delayed: 让排在队列里的 selection_set 事件先走(它们会被 _populating 挡掉)
        self.root.after(50, lambda: setattr(self, '_populating', False))

    def _clear_panel(self):
        self.var_name.set("")
        self.thumb_btn.configure(image="", text="📷"); self._thumb_img = None
        self.cand_tree.delete(*self.cand_tree.get_children())
        self._candidates = []; self._dom_path = []; self._dom_checked = []
        self._set_sel_text("")
        pass  # tab0_forget; pass  # tab1_forget
        for w in self.dom_inner.winfo_children(): w.destroy()
        self.btn_validate.configure(state=tk.DISABLED)
        self.btn_save_sel.configure(state=tk.DISABLED)
        self.btn_recommend.configure(state=tk.DISABLED)
        self.btn_manual.configure(state=tk.DISABLED)

    # ── DOM interaction ──
    def _build_dom_checkboxes(self):
        for w in self.dom_inner.winfo_children(): w.destroy()
        path = self._dom_path
        if not path: return
        self._dom_checked = [tk.BooleanVar(value=True) for _ in path]
        for i, node in enumerate(path):
            row = ttk.Frame(self.dom_inner); row.pack(fill=tk.X, pady=1)
            cb = ttk.Checkbutton(row, variable=self._dom_checked[i], command=self._update_dom_sel)
            cb.pack(side=tk.LEFT)
            indent = "  " * i
            if isinstance(node, dict):
                tag = node.get("tag", "div")
                sid = f"#{node['id']}" if node.get("id") else ""
                cls = ".".join(node.get("classes", [])[:3]) if node.get("classes") else ""
                display = f"{indent}<{tag}>{sid}" + (f".{cls}" if cls else "")
            else:
                display = f"{indent}{str(node)[:120]}"
            ttk.Label(row, text=display, font=("Consolas", 9)).pack(side=tk.LEFT)

    def _update_dom_sel(self):
        parts = []
        for i, node in enumerate(self._dom_path):
            if i >= len(self._dom_checked) or not self._dom_checked[i].get():
                continue
            if isinstance(node, dict):
                tag = node.get("tag", "div")
                sid = f"#{node['id']}" if node.get("id") else ""
                cls = ".".join(node.get("classes", [])[:3]) if node.get("classes") else ""
                parts.append(f"{tag}{sid}" + (f".{cls}" if cls else ""))
            else:
                parts.append(str(node))
        self._set_sel_text(" > ".join(parts) if parts else "")

    # ── List ──
    def _refresh_list(self):
        sel_idx = int(self.tree.selection()[0]) if self.tree.selection() else -1
        self.tree.delete(*self.tree.get_children())
        for i, e in enumerate(self.store.elements):
            icon = TYPE_ICONS.get(e.element_type, "❓")
            t = TYPE_LABELS.get(e.element_type, e.element_type)
            sel_preview = (e.css_selector or "")[:50]
            self.tree.insert("", tk.END, iid=str(i), values=(f"{icon} {e.name}", t, sel_preview))
        if 0 <= sel_idx < len(self.store.elements):
            self.tree.selection_set(str(sel_idx)); self.tree.see(str(sel_idx))

    def _on_select(self, event):
        sel = self.tree.selection()
        if not sel: self._clear_panel(); return
        idx = int(sel[0])
        if idx < len(self.store.elements):
            self._show_props(self.store.elements[idx])

    def set_status(self, text):
        self.status_label.configure(text=text)
        print(f"[CaptureGUI] {text}")


if __name__ == "__main__":
    CaptureGUI().root.mainloop()
