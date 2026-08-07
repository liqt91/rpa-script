"""桌面工作流编辑器 — tkinter 原生 GUI。

独立运行：编辑直接操作 SQLite，运行时后台起 FastAPI 托管 WebSocket。
"""

import os
import sys
import json
import asyncio
import threading
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.runtime.workflow.handlers.registry import build_command_registry
from src.runtime.commands import auto_register   # 注册新体系指令 (commands/*.json → handler)
from scripts.desktop_editor import db

# 确保新体系指令在 registry 中可用
auto_register()

_server_started = False
_server_lock = threading.Lock()


def _ensure_server():
    """后台启动纯 WebSocket 服务器（不加载 FastAPI/HTTP 路由）。"""
    global _server_started
    with _server_lock:
        if _server_started:
            return
        _server_started = True

    from src.config.settings import PORT
    from scripts.desktop_editor.ws_server import run_ws_server

    def _run():
        asyncio.run(run_ws_server(port=PORT))

    threading.Thread(target=_run, daemon=True).start()

CATEGORY_ICONS = {
    "浏览器": "🌐", "输入": "⌨", "点击": "🖱", "数据提取": "📤",
    "变量": "📦", "等待": "⏱", "导航": "🧭", "截图": "📷",
    "循环": "🔄", "条件判断": "❓", "异常处理": "🛡", "流程控制": "⚙",
    "桌面操作": "🪟", "桌面操作(UIA)": "🔍", "自定义": "📝",
    "其他": "📌",
}


class DesktopEditor:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("RPA 工作流编辑器")
        self.root.geometry("1100x700")
        self.root.minsize(900, 500)

        self._current_wf_id: int | None = None
        self._command_registry = build_command_registry()
        self._codemap: dict[str, dict] = {}  # node treeview iid -> node info
        self._runner = None
        self._run_queue: asyncio.Queue | None = None

        # 拖拽状态
        self._drag_source: str | None = None
        self._drag_item: str | None = None
        self._drag_cmd_type: str | None = None
        self._drag_start_y: int = 0

        self._build_ui()
        self._refresh_workflow_list()
        self._refresh_command_tree("")

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # 后台启动 WS 服务器（浏览器扩展通信）
        threading.Thread(target=_ensure_server, daemon=True).start()

        # 注册 Native Messaging Host（Chrome/Edge 免配置自动连接）
        self._register_native_host()

    # ═══════════════════════════════════════════════════════════
    # UI Layout
    # ═══════════════════════════════════════════════════════════

    def _build_ui(self):
        # ── Top bar: workflow selector ──
        top = ttk.Frame(self.root, padding=(8, 6))
        top.pack(fill=tk.X)

        ttk.Label(top, text="工作流:").pack(side=tk.LEFT)
        self._wf_combo = ttk.Combobox(top, state="readonly", width=30)
        self._wf_combo.pack(side=tk.LEFT, padx=6)
        self._wf_combo.bind("<<ComboboxSelected>>", self._on_wf_select)

        ttk.Button(top, text="➕ 新建", command=self._new_workflow).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="🗑 删除", command=self._delete_workflow).pack(side=tk.LEFT)

        ttk.Separator(top, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=2)

        ttk.Button(top, text="▶ 运行", command=self._on_run).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="⏹ 停止", command=self._on_stop).pack(side=tk.LEFT)

        self._status_var = tk.StringVar(value="就绪")
        ttk.Label(top, textvariable=self._status_var, foreground="gray").pack(
            side=tk.RIGHT, padx=8
        )

        # ── Paned: left | center | right ──
        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 4))

        self._build_command_panel(paned)
        self._build_node_list(paned)
        self._build_property_panel(paned)

        # ── Bottom: run log ──
        log_frame = ttk.LabelFrame(self.root, text="运行日志", padding=4)
        log_frame.pack(fill=tk.BOTH, padx=6, pady=(0, 6))

        self._log_text = tk.Text(log_frame, height=6, wrap=tk.WORD, font=("Consolas", 9),
                                  state=tk.DISABLED)
        self._log_text.pack(fill=tk.BOTH, expand=True)

    def _build_command_panel(self, paned):
        frame = ttk.Frame(paned, width=200)
        paned.add(frame, weight=0)

        ttk.Label(frame, text="命令", font=("", 10, "bold")).pack(anchor=tk.W, pady=(0, 4))

        self._cmd_search_var = tk.StringVar()
        self._cmd_search_var.trace_add("write", lambda *a: self._refresh_command_tree(
            self._cmd_search_var.get()
        ))
        search = ttk.Entry(frame, textvariable=self._cmd_search_var)
        search.pack(fill=tk.X, pady=(0, 6))

        self._cmd_tree = ttk.Treeview(frame, show="tree", selectmode="browse")
        self._cmd_tree.pack(fill=tk.BOTH, expand=True)
        self._cmd_tree.bind("<ButtonPress-1>", lambda e: self._on_drag_start(e, "cmd_panel"))

        ttk.Button(frame, text="+ 添加到工作流",
                   command=self._add_selected_command).pack(fill=tk.X, pady=(6, 0))

    def _build_node_list(self, paned):
        frame = ttk.Frame(paned)
        paned.add(frame, weight=1)

        ttk.Label(frame, text="步骤 (拖拽排序)", font=("", 10, "bold")).pack(anchor=tk.W, pady=(0, 4))

        columns = ("order", "cmd", "summary")
        self._node_tree = ttk.Treeview(frame, columns=columns, show="headings",
                                        selectmode="browse")
        self._node_tree.heading("order", text="#")
        self._node_tree.heading("cmd", text="命令")
        self._node_tree.heading("summary", text="参数摘要")
        self._node_tree.column("order", width=35, anchor=tk.CENTER)
        self._node_tree.column("cmd", width=100)
        self._node_tree.column("summary", width=200)
        self._node_tree.pack(fill=tk.BOTH, expand=True)

        self._node_tree.bind("<<TreeviewSelect>>", self._on_node_select)
        self._node_tree.bind("<ButtonPress-1>", lambda e: self._on_drag_start(e, "node_list"))
        self._node_tree.bind("<B1-Motion>", self._on_drag_motion)
        self._node_tree.bind("<ButtonRelease-1>", self._on_drag_stop)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=(4, 0))
        ttk.Button(btn_frame, text="^ 上移", command=lambda: self._move_node(-1)).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="v 下移", command=lambda: self._move_node(1)).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="X 删除步骤", command=self._remove_node).pack(side=tk.LEFT)

    def _build_property_panel(self, paned):
        self._prop_frame = ttk.LabelFrame(paned, text="属性", padding=8, width=280)
        paned.add(self._prop_frame, weight=0)

        self._prop_widgets: dict[str, tk.Widget] = {}
        self._prop_vars: dict[str, tk.StringVar] = {}
        self._prop_label_maps: dict[str, dict[str, str]] = {}  # name -> {label: value}
        self._current_node_id: int | None = None

        ttk.Label(self._prop_frame, text="选择一个步骤查看属性",
                  foreground="gray").pack(anchor=tk.CENTER, pady=20)

    # ═══════════════════════════════════════════════════════════
    # Workflow management
    # ═══════════════════════════════════════════════════════════

    def _refresh_workflow_list(self):
        workflows = db.list_workflows()
        self._wf_combo["values"] = [
            f"{w['name']} ({w['node_count']}步)" for w in workflows
        ]
        self._workflow_ids = [w["id"] for w in workflows]

    def _on_wf_select(self, event=None):
        idx = self._wf_combo.current()
        if idx < 0:
            return
        self._current_wf_id = self._workflow_ids[idx]
        self._refresh_node_list()

    def _new_workflow(self):
        name = simpledialog.askstring("新建工作流", "名称:", parent=self.root)
        if name:
            wf = db.create_workflow(name)
            self._refresh_workflow_list()
            # 选中新建的
            for i, wid in enumerate(self._workflow_ids):
                if wid == wf.id:
                    self._wf_combo.current(i)
                    self._on_wf_select()
                    break

    def _delete_workflow(self):
        if self._current_wf_id is None:
            return
        ok = messagebox.askyesno("确认", "删除当前工作流及所有步骤?")
        if ok:
            db.delete_workflow(self._current_wf_id)
            self._current_wf_id = None
            self._node_tree.delete(*self._node_tree.get_children())
            self._codemap.clear()
            self._refresh_workflow_list()
            self._set_status("已删除")

    # ═══════════════════════════════════════════════════════════
    # Command panel
    # ═══════════════════════════════════════════════════════════

    def _refresh_command_tree(self, query: str):
        self._cmd_tree.delete(*self._cmd_tree.get_children())
        query_lower = query.lower()

        # 按 category_order 分组排序
        categories: dict[str, list[dict]] = {}
        cat_orders: dict[str, int] = {}
        for cmd_type, cdef in self._command_registry.items():
            cat = cdef.get("category", "其他")
            cat_orders[cat] = cdef.get("categoryOrder", 99)
            if query_lower:
                label = cdef.get("label", cmd_type)
                desc = cdef.get("description", "")
                if query_lower not in label.lower() and query_lower not in desc.lower():
                    continue
            categories.setdefault(cat, []).append(cdef)

        for cat in sorted(categories, key=lambda c: cat_orders.get(c, 99)):
            items = categories[cat]
            if not items:
                continue
            icon = CATEGORY_ICONS.get(cat, "📌")
            cat_iid = self._cmd_tree.insert("", tk.END, text=f"{icon} {cat} ({len(items)})",
                                             open=True, tags=("category",))
            for cdef in sorted(items, key=lambda c: c.get("commandOrder", 0)):
                label = cdef.get("label", cdef.get("cmd", "?"))
                self._cmd_tree.insert(cat_iid, tk.END,
                                       text=f"  {label}",
                                       values=(cdef["cmd"],),
                                       tags=("command",))

    def _add_selected_command(self):
        if self._current_wf_id is None:
            messagebox.showwarning("提示", "请先选择或新建工作流")
            return
        sel = self._cmd_tree.selection()
        if not sel:
            return
        item = self._cmd_tree.item(sel[0])
        cmd_type = item.get("values", ("",))[0]
        if not cmd_type:
            return

        db.add_node(self._current_wf_id, cmd_type)
        self._refresh_node_list()
        # 刷新工作流列表的步数
        self._refresh_workflow_list()

    # ═══════════════════════════════════════════════════════════
    # Node list
    # ═══════════════════════════════════════════════════════════

    def _refresh_node_list(self):
        self._node_tree.delete(*self._node_tree.get_children())
        self._codemap.clear()

        if self._current_wf_id is None:
            return

        nodes = db.get_nodes(self._current_wf_id)
        for node in nodes:
            extra = node.extra
            if isinstance(extra, str):
                try:
                    extra = json.loads(extra)
                except Exception:
                    extra = {}
            # 兼容旧格式: {"extra": {"browserType": ...}} 展开内层
            if isinstance(extra, dict) and "extra" in extra and isinstance(extra["extra"], dict):
                extra = extra["extra"]
            cmd_label = self._command_registry.get(node.cmd, {}).get("label", node.cmd)
            summary = self._make_summary(node.cmd, extra)
            iid = str(node.id)
            self._node_tree.insert("", tk.END, iid=iid,
                                    values=(node.order + 1, cmd_label, summary))
            self._codemap[iid] = {
                "id": node.id, "cmd": node.cmd, "extra": extra,
                "order": node.order,
            }

    def _make_summary(self, cmd_type: str, extra: dict) -> str:
        """生成参数摘要字符串。"""
        cdef = self._command_registry.get(cmd_type, {})
        tpl = cdef.get("summaryTpl", "")
        if tpl and extra:
            try:
                return tpl.format_map({k: v for k, v in extra.items() if v})
            except Exception:
                pass
        # fallback: 取第一个非空参数
        for key in ("url", "text", "value", "locator", "elementName",
                     "browserType", "seconds", "varName", "description"):
            if extra.get(key):
                val = str(extra.get(key))[:40]
                return val
        return ""

    def _on_node_select(self, event=None):
        sel = self._node_tree.selection()
        if not sel:
            return
        info = self._codemap.get(sel[0])
        if not info:
            return
        self._current_node_id = info["id"]
        self._show_properties(info)

    def _move_node(self, direction: int):
        """上移(-1)或下移(+1)当前选中的节点。"""
        if self._current_wf_id is None:
            return
        sel = self._node_tree.selection()
        if not sel:
            return
        iid = sel[0]
        info = self._codemap.get(iid)
        if not info:
            return

        nodes = db.get_nodes(self._current_wf_id)
        idx = next((i for i, n in enumerate(nodes) if n.id == info["id"]), -1)
        if idx < 0:
            return
        new_idx = idx + direction
        if new_idx < 0 or new_idx >= len(nodes):
            return

        # 交换 order
        nodes[idx], nodes[new_idx] = nodes[new_idx], nodes[idx]
        node_ids = [n.id for n in nodes]
        db.reorder_nodes(self._current_wf_id, node_ids)
        self._refresh_node_list()

    def _remove_node(self):
        if self._current_node_id is None:
            return
        db.remove_node(self._current_node_id)
        self._current_node_id = None
        self._refresh_node_list()
        self._refresh_workflow_list()
        self._clear_properties()

    # ═══════════════════════════════════════════════════════════
    # Property panel
    # ═══════════════════════════════════════════════════════════

    def _show_properties(self, info: dict):
        self._clear_properties()

        cmd_type = info["cmd"]
        cdef = self._command_registry.get(cmd_type, {})
        extra = info.get("extra", {})

        row = 0

        # 命令类型（只读）
        ttk.Label(self._prop_frame, text="命令类型", font=("", 9)).grid(
            row=row, column=0, sticky=tk.W, pady=2)
        ttk.Label(self._prop_frame, text=cdef.get("label", cmd_type),
                  font=("", 9, "bold")).grid(row=row, column=1, sticky=tk.W, pady=2)
        row += 1

        ttk.Separator(self._prop_frame, orient=tk.HORIZONTAL).grid(
            row=row, column=0, columnspan=2, sticky=tk.EW, pady=6)
        row += 1

        # 动态生成字段
        fields = cdef.get("fields", [])
        if not fields and cdef.get("params"):
            fields = cdef["params"]

        for field in fields:
            name = field.get("name", "")
            if not name or name in ("onError", "retryCount", "timeout", "description"):
                continue
            label = field.get("label", name)
            ftype = field.get("type", "string")
            val = extra.get(name, field.get("default", ""))

            ttk.Label(self._prop_frame, text=label, font=("", 9)).grid(
                row=row, column=0, sticky=tk.W, pady=2)

            var = tk.StringVar(value=str(val) if val else "")
            self._prop_vars[name] = var

            if ftype == "boolean":
                # Checkbutton needs BooleanVar
                bool_var = tk.BooleanVar(value=bool(val))
                cb = ttk.Checkbutton(self._prop_frame, variable=bool_var)
                cb.grid(row=row, column=1, sticky=tk.W, pady=2)
                self._prop_widgets[name] = bool_var
            elif ftype == "select" or ftype == "str-dropdown":
                options = field.get("options", [])
                # 构建 label->value 映射，保存时转回 value
                label_to_value = {}
                if (isinstance(options, list) and options
                        and isinstance(options[0], dict) and "value" in options[0]):
                    for o in options:
                        label_to_value[o["label"]] = o["value"]
                    labels = list(label_to_value.keys())
                    # 当前存储的值 -> 匹配对应的 label
                    display = val
                    for lb, v in label_to_value.items():
                        if v == val:
                            display = lb
                            break
                    var.set(str(display) if display else "")
                else:
                    labels = [o["label"] if isinstance(o, dict) else o for o in options]

                combo = ttk.Combobox(self._prop_frame, textvariable=var, values=labels,
                                      state="readonly", width=24)
                combo.grid(row=row, column=1, sticky=tk.W, pady=2)
                self._prop_widgets[name] = var
                if label_to_value:
                    self._prop_label_maps[name] = label_to_value
            elif ftype in ("text", "string", "str-input", "str-var", "number", "int-number"):
                w = ttk.Entry(self._prop_frame, textvariable=var, width=26)
                w.grid(row=row, column=1, sticky=tk.EW, pady=2)
                self._prop_widgets[name] = var
            else:
                w = ttk.Entry(self._prop_frame, textvariable=var, width=26)
                w.grid(row=row, column=1, sticky=tk.EW, pady=2)
                self._prop_widgets[name] = var

            row += 1

        # Save button
        ttk.Button(self._prop_frame, text="💾 保存属性",
                   command=self._save_properties).grid(
            row=row, column=0, columnspan=2, pady=(12, 4), sticky=tk.EW)
        row += 1

        self._prop_frame.grid_columnconfigure(1, weight=1)

    def _save_properties(self):
        if self._current_node_id is None:
            return

        try:
            extra = {}
            for name, widget in self._prop_widgets.items():
                if isinstance(widget, tk.BooleanVar):
                    extra[name] = widget.get()
                else:
                    val = widget.get()
                    if name in self._prop_label_maps:
                        val = self._prop_label_maps[name].get(val, val)
                    extra[name] = val

            print("[DEBUG] saving extra:", extra)
            db.update_node(self._current_node_id, extra={"extra": extra})
            self._refresh_node_list()
            self._set_status("已保存")
            print("[DEBUG] save done, node_id:", self._current_node_id)
        except Exception as e:
            messagebox.showerror("保存失败", str(e))
            import traceback
            traceback.print_exc()

    def _clear_properties(self):
        for w in self._prop_frame.winfo_children():
            w.destroy()
        self._prop_widgets.clear()
        self._prop_vars.clear()
        self._prop_label_maps.clear()

    # ═══════════════════════════════════════════════════════════
    # Run / Stop
    # ═══════════════════════════════════════════════════════════

    def _on_run(self):
        if self._current_wf_id is None:
            return
        wf = db.get_workflow(self._current_wf_id)
        if not wf:
            return
        nodes = db.get_all_nodes(self._current_wf_id)
        if not nodes:
            messagebox.showwarning("提示", "工作流没有步骤")
            return

        self._set_status("运行中...")
        self._log_clear()
        self._log_append(f"启动工作流: {wf.name} ({len(nodes)}步骤)")

        self._run_queue = asyncio.Queue()
        self._runner = None

        def _run_thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            async def _do_run():
                from src.runtime.workflow.extension_runner import ExtensionRunner
                import time as _time
                run_id = f"desktop_{int(_time.time() * 1000)}"
                runner = ExtensionRunner(
                    client_id="", run_id=run_id,
                    queue=self._run_queue, workflow_id=wf.id,
                )
                self._runner = runner
                try:
                    result = await runner.run(wf, nodes)
                    self._log_append(f"完成: {result.get('completedSteps', 0)}/{result.get('totalSteps', 0)} 步")
                except Exception as e:
                    self._log_append(f"运行错误: {e}")
                finally:
                    self._set_status("就绪")
            loop.run_until_complete(_do_run())

        threading.Thread(target=_run_thread, daemon=True).start()
        self._poll_queue()

    def _poll_queue(self):
        """定时轮询运行队列，更新 UI。"""
        if self._run_queue is None:
            return
        try:
            while True:
                event = self._run_queue.get_nowait()
                etype = event.get("type", "")
                if etype == "stepStart":
                    label = event.get("cmdLabel", event.get("cmdType", ""))
                    self._log_append(f"  ▶ {label}")
                elif etype == "stepComplete":
                    event.get("result", "")
                    self._log_append("  ✓ 完成")
                elif etype == "stepError":
                    err = event.get("error", "未知错误")
                    self._log_append(f"  ✗ {err}")
                elif etype == "done":
                    self._log_append("── 运行结束 ──")
                    self._run_queue = None
                    return
                elif etype == "paused":
                    self._log_append("  ⏸ 已暂停")
        except Exception:
            pass

        self.root.after(200, self._poll_queue)

    def _on_stop(self):
        if self._runner:
            async def _stop():
                await self._runner.stop()
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            loop.run_until_complete(_stop())
            self._log_append("⏹ 已停止")
            self._set_status("已停止")

    # ═══════════════════════════════════════════════════════════
    # Utils
    # ═══════════════════════════════════════════════════════════

    def _set_status(self, text: str):
        self._status_var.set(text)
        self.root.update_idletasks()

    def _log_clear(self):
        self._log_text.configure(state=tk.NORMAL)
        self._log_text.delete("1.0", tk.END)
        self._log_text.configure(state=tk.DISABLED)

    def _log_append(self, text: str):
        self._log_text.configure(state=tk.NORMAL)
        self._log_text.insert(tk.END, text + "\n")
        self._log_text.see(tk.END)
        self._log_text.configure(state=tk.DISABLED)
        self.root.update_idletasks()

    def _register_native_host(self):
        """注册 Native Messaging Host，让 Chrome/Edge 扩展免配置连接。"""
        try:
            from scripts.register_native_host import register_all
            register_all()
            self._log_append("[Native Host] 已注册到 Chrome/Edge")
        except Exception as e:
            self._log_append(f"[Native Host] 注册失败: {e}")

    # ═══════════════════════════════════════════════════════════
    # Drag & Drop
    # ═══════════════════════════════════════════════════════════

    def _drag_create_ghost(self, text: str):
        """半透明 ghost 窗口跟随光标。"""
        g = tk.Toplevel(self.root)
        g.overrideredirect(True)
        g.attributes("-alpha", 0.80)
        g.attributes("-topmost", True)
        tk.Label(g, text=text, bg="#2563eb", fg="white",
                 font=("Microsoft YaHei UI", 10), padx=10, pady=4).pack()
        self._drag_ghost = g

    def _drag_move_ghost(self, x: int, y: int):
        if hasattr(self, "_drag_ghost") and self._drag_ghost:
            try:
                self._drag_ghost.geometry(f"+{x+14}+{y+14}")
            except Exception:
                pass

    def _drag_destroy_ghost(self):
        if hasattr(self, "_drag_ghost") and self._drag_ghost:
            try:
                self._drag_ghost.destroy()
            except Exception:
                pass
            self._drag_ghost = None

    def _drag_hl_clear(self, tree):
        """清除目标高亮。"""
        if hasattr(self, "_drag_hl_item") and self._drag_hl_item:
            try:
                tree.item(self._drag_hl_item, tags=())
            except Exception:
                pass
            self._drag_hl_item = None

    def _drag_hl_set(self, tree, item):
        """高亮目标行（蓝色背景）。"""
        self._drag_hl_clear(tree)
        if item:
            tree.tag_configure("drop_hl", background="#dbeafe")
            tree.item(item, tags=("drop_hl",))
            self._drag_hl_item = item

    def _on_drag_start(self, event, source: str):
        if source == "cmd_panel":
            item = self._cmd_tree.identify_row(event.y)
            if not item:
                return
            vals = self._cmd_tree.item(item, "values")
            if not vals or not vals[0]:
                return
            self._drag_source = "cmd_panel"
            self._drag_cmd_type = vals[0]
            label = self._command_registry.get(self._drag_cmd_type, {}).get("label", self._drag_cmd_type)
            self._drag_create_ghost(f"+ {label}")
        else:
            item = event.widget.identify_row(event.y)
            if not item:
                return
            self._drag_source = "node_list"
            self._drag_item = item
            info = self._codemap.get(item, {})
            label = self._command_registry.get(info.get("cmd", ""), {}).get("label", "")
            self._drag_create_ghost(f"  {label}")
        self._drag_start_y = event.y_root

    def _on_drag_motion(self, event):
        if not self._drag_source:
            return
        if abs(event.y_root - self._drag_start_y) < 3:
            return

        self._drag_move_ghost(event.x_root, event.y_root)

        if self._drag_source == "node_list":
            target = event.widget.identify_row(event.y)
            if target == self._drag_item:
                target = None
            self._drag_hl_set(event.widget, target)

    def _on_drag_stop(self, event):
        self._drag_destroy_ghost()
        source = self._drag_source

        if source == "node_list":
            self._drag_hl_clear(event.widget)
            if self._drag_item and self._current_wf_id:
                nodes = db.get_nodes(self._current_wf_id)
                info = self._codemap.get(self._drag_item)
                if info:
                    drag_idx = next((i for i, n in enumerate(nodes) if n.id == info["id"]), -1)
                    if drag_idx >= 0:
                        y_rel = event.y_root - event.widget.winfo_rooty()
                        target = event.widget.identify_row(y_rel)
                        children = event.widget.get_children("")
                        if target and target in children and target != self._drag_item:
                            target_idx = children.index(target)
                            node_ids = [n.id for n in nodes]
                            moved = node_ids.pop(drag_idx)
                            insert_at = target_idx + 1 if target_idx >= drag_idx else target_idx
                            node_ids.insert(insert_at, moved)
                            db.reorder_nodes(self._current_wf_id, node_ids)
                            self._refresh_node_list()

        elif source == "cmd_panel" and self._drag_cmd_type and self._current_wf_id:
            node = db.add_node(self._current_wf_id, self._drag_cmd_type)
            y_rel = event.y_root - self._node_tree.winfo_rooty()
            target = self._node_tree.identify_row(y_rel)
            if target:
                info = self._codemap.get(target)
                if info:
                    nodes = db.get_nodes(self._current_wf_id)
                    target_idx = next((i for i, n in enumerate(nodes) if n.id == info["id"]), len(nodes) - 1)
                    node_ids = [n.id for n in nodes if n.id != node.id]
                    node_ids.insert(target_idx + 1, node.id)
                    db.reorder_nodes(self._current_wf_id, node_ids)
            self._refresh_node_list()
            self._refresh_workflow_list()

        self._drag_source = None
        self._drag_item = None
        self._drag_cmd_type = None

    def _on_close(self):
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    app = DesktopEditor()
    app.run()


if __name__ == "__main__":
    main()
