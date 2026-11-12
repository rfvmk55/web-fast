"""终端式界面：左边选工具，右边就是一个 PowerShell 会话。"""
from __future__ import annotations

import os
import queue
import shutil
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .history import append as hist_append
from .launcher import Runner, split_cmd
from .registry import (APP_ROOT, Registry, Tool, load_local_paths,
                       save_local_paths, tools_root)

FONT_UI = ("Microsoft YaHei UI", 9)
FONT_MONO = ("Consolas", 10)
FONT_TITLE = ("Microsoft YaHei UI", 13, "bold")

BG = "#f5f6f8"
SUB = "#6b7280"
OUT_BG = "#0f1319"
OUT_FG = "#d6deeb"
C_CMD = "#7ee787"
C_ERR = "#ff7b72"
C_WARN = "#e3b341"
C_DIM = "#6e7b8f"
C_INFO = "#79c0ff"
IN_BG = "#1b2028"
IN_FG = "#e6edf3"



class InlinePicker:
    """贴在输入框上方的内联候选条：Tab 选中，↑↓ 切换，Esc 关闭，继续打字自动过滤。"""

    ROW_H = 22
    MAX_ROWS = 8

    def __init__(self, root, entry, on_pick):
        self.root = root
        self.entry = entry
        self.on_pick = on_pick
        self.top = None
        self.lb = None
        self.hint = None
        self.all_rows = []
        self.rows = []
        self.index = 0
        self.head = ""
        self.token = ""
        self.kind = "value"

    @property
    def active(self) -> bool:
        return self.top is not None

    def _build(self):
        top = tk.Toplevel(self.root)
        top.overrideredirect(True)
        try:
            top.attributes("-topmost", True)
        except Exception:
            pass
        frame = tk.Frame(top, background="#111823",
                         highlightthickness=1, highlightbackground="#3b82f6")
        frame.pack(fill="both", expand=True)
        self.lb = tk.Listbox(frame, font=FONT_MONO, activestyle="none",
                             background="#111823", foreground="#d6deeb",
                             selectbackground="#1f6feb", selectforeground="#ffffff",
                             borderwidth=0, highlightthickness=0,
                             exportselection=False)
        self.lb.pack(fill="both", expand=True, padx=1, pady=1)
        self.hint = tk.Label(frame, text="", background="#111823", foreground="#6e7b8f",
                             font=(FONT_MONO[0], 8), anchor="w")
        self.hint.pack(fill="x", padx=6, pady=(0, 2))
        self.lb.bind("<Button-1>", self._on_click)
        self.top = top
        self.frame = frame

    def _on_click(self, event):
        idx = self.lb.nearest(event.y)
        if 0 <= idx < len(self.rows):
            self.index = idx
            self._render()
            self.pick()

    def show(self, items, head: str, token: str, kind: str = "value"):
        if not items:
            self.hide()
            return
        self.kind = kind
        self.all_rows = list(items)
        self.rows = list(items)
        self.head = head
        self.token = token
        self.index = 0
        if self.top is None:
            self._build()
        self._render()
        self._place()
        try:
            self.entry.focus_set()
        except Exception:
            pass

    def filter(self, frag: str):
        frag = (frag or "").strip().lower()
        if not frag:
            self.rows = list(self.all_rows)
        else:
            self.rows = [x for x in self.all_rows
                         if frag in x[0].lower() or frag in x[1].lower()]
        self.index = 0
        if not self.rows:
            self.hide()
            return
        self._render()
        self._place()

    def move(self, delta: int):
        if not self.active or not self.rows:
            return
        self.index = max(0, min(len(self.rows) - 1, self.index + delta))
        self._render()

    def pick(self):
        if not self.active or not self.rows:
            return
        value = self.rows[self.index][1]
        head, token, kind = self.head, self.token, self.kind
        self.hide()
        self.on_pick(head, token, value, kind)

    def hide(self):
        if self.top is not None:
            try:
                self.top.destroy()
            except Exception:
                pass
            self.top = None
            self.lb = None
        self.rows = []
        self.all_rows = []

    def _render(self):
        lb = self.lb
        lb.delete(0, "end")
        n = len(self.rows)
        start = 0
        if n > self.MAX_ROWS:
            start = max(0, min(self.index - self.MAX_ROWS // 2, n - self.MAX_ROWS))
        for i in range(start, min(n, start + self.MAX_ROWS)):
            shown = self.rows[i][0]
            mark = "▸ " if i == self.index else "  "
            lb.insert("end", mark + shown)
        if n <= self.MAX_ROWS:
            lb.selection_clear(0, "end")
            lb.selection_set(self.index)
        else:
            lb.selection_clear(0, "end")
            lb.selection_set(self.index - start)
        lb.see(self.index - start)
        total = len(self.all_rows)
        if self.hint:
            self.hint.configure(text=f"{n}/{total} 项    Tab 选中   ↑↓ 切换   Esc 关闭")

    def _place(self):
        top = self.top
        if top is None:
            return
        self.root.update_idletasks()
        try:
            ew = self.entry.winfo_width()
            ex = self.entry.winfo_rootx()
            ey = self.entry.winfo_rooty()
        except Exception:
            return
        n = min(len(self.rows), self.MAX_ROWS)
        w = max(ew, 360)
        h = n * self.ROW_H + 24
        x = ex
        y = ey - h - 4
        if y < 0:
            y = ey + self.entry.winfo_height() + 4
        sw = self.root.winfo_screenwidth()
        if x + w > sw - 8:
            x = max(0, sw - w - 8)
        top.wm_geometry(f"{w}x{h}+{x}+{y}")

class WebFastGUI:
    def __init__(self, root: tk.Tk, registry: Registry):
        self.root = root
        self.reg = registry
        self.tool = None
        self.cwd = APP_ROOT
        self.runner = None
        self.mode = "idle"
        self.history = []
        self.hist_idx = -1
        self.value_history = {}
        self._q = queue.Queue()
        self._cur_argv = []
        self._build_ui()
        self.picker = InlinePicker(self.root, self.entry, self._apply_pick)
        self._fill_tree()
        self._poll()
        self._banner_start()
        self.entry.focus_set()
        root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------ 布局
    def _build_ui(self):
        self.root.configure(bg=BG)
        style = ttk.Style()
        for theme in ("vista", "clam", "default"):
            if theme in style.theme_names():
                style.theme_use(theme)
                break
        style.configure("Treeview", font=FONT_UI, rowheight=24)
        style.configure("TLabel", font=FONT_UI)
        style.configure("TButton", font=FONT_UI)
        style.configure("Sub.TLabel", font=FONT_UI, foreground=SUB)

        top = ttk.Frame(self.root, padding=(10, 8, 10, 2))
        top.pack(fill="x")
        ttk.Label(top, text="搜索").pack(side="left")
        self.search_var = tk.StringVar()
        ent = ttk.Entry(top, textvariable=self.search_var, width=34)
        ent.pack(side="left", padx=(6, 8))
        self.search_var.trace_add("write", lambda *_: self._fill_tree())
        ttk.Button(top, text="体检", command=self._doctor).pack(side="left", padx=2)
        ttk.Button(top, text="工具根目录", command=self._open_root).pack(side="left", padx=2)
        self.status_top = ttk.Label(top, text="", style="Sub.TLabel")
        self.status_top.pack(side="right")

        body = ttk.Panedwindow(self.root, orient="horizontal")
        body.pack(fill="both", expand=True, padx=8, pady=(2, 8))

        left = ttk.Frame(body, width=250)
        body.add(left, weight=0)
        self.tree = ttk.Treeview(left, show="tree", selectmode="browse")
        vsb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        right = ttk.Frame(body)
        body.add(right, weight=1)

        bar = ttk.Frame(right, padding=(6, 0, 6, 4))
        bar.pack(fill="x")
        self.lbl_tool = ttk.Label(bar, text="未选择工具", font=FONT_TITLE)
        self.lbl_tool.pack(side="left")
        self.lbl_state = ttk.Label(bar, text="", style="Sub.TLabel")
        self.lbl_state.pack(side="left", padx=10)
        ttk.Button(bar, text="清空", width=6, command=self._clear).pack(side="right", padx=2)
        ttk.Button(bar, text="停止", width=6, command=self._stop).pack(side="right", padx=2)
        ttk.Button(bar, text="参数表", command=self._show_params).pack(side="right", padx=2)
        ttk.Button(bar, text="打开目录", command=self._open_tool_dir).pack(side="right", padx=2)
        ttk.Button(bar, text="改路径", command=self._set_path).pack(side="right", padx=2)

        term = tk.Frame(right, bg=OUT_BG, highlightthickness=1,
                        highlightbackground="#2a3140")
        term.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        self.out = tk.Text(term, background=OUT_BG, foreground=OUT_FG,
                           insertbackground=OUT_FG, font=FONT_MONO, wrap="word",
                           relief="flat", padx=10, pady=8, state="disabled",
                           selectbackground="#264f78")
        osb = ttk.Scrollbar(term, orient="vertical", command=self.out.yview)
        self.out.configure(yscrollcommand=osb.set)
        osb.pack(side="right", fill="y")
        self.out.pack(side="top", fill="both", expand=True)
        for tag, color in (("cmd", C_CMD), ("err", C_ERR), ("warn", C_WARN),
                           ("dim", C_DIM), ("info", C_INFO), ("ok", C_CMD)):
            self.out.tag_configure(tag, foreground=color)
        self.out.tag_configure("bold", font=("Consolas", 10, "bold"))

        inrow = tk.Frame(term, bg=OUT_BG)
        inrow.pack(side="bottom", fill="x", padx=0, pady=0)
        self.prompt_lbl = tk.Label(inrow, text="PS >", font=FONT_MONO,
                                   bg=OUT_BG, fg=C_CMD, anchor="w")
        self.prompt_lbl.grid(row=0, column=0, sticky="w", padx=(10, 6), pady=7)
        self.entry = tk.Entry(inrow, font=FONT_MONO, bg=IN_BG, fg=IN_FG,
                              insertbackground=C_CMD, relief="flat",
                              highlightthickness=1, highlightbackground="#2a3140",
                              highlightcolor="#3d4a5c")
        self.entry.grid(row=0, column=1, sticky="ew", padx=(0, 10), pady=7, ipady=3)
        inrow.columnconfigure(1, weight=1)
        self.entry.bind("<Return>", self._on_enter)
        self.entry.bind("<Up>", self._hist_prev)
        self.entry.bind("<Down>", self._hist_next)
        self.entry.bind("<Tab>", self._on_tab)
        self.entry.bind("<space>", self._on_space)
        self.entry.bind("<Control-space>", self._on_ctrl_space)
        self.entry.bind("<KeyRelease>", self._on_key_release)
        self.entry.bind("<Escape>", self._on_escape)
        self.entry.bind("<Control-c>", lambda e: self._stop_shortcut())
        self.entry.bind("<Control-l>", lambda e: self._clear())

    # ------------------------------------------------------------------ 左侧
    def _fill_tree(self):
        self.tree.delete(*self.tree.get_children())
        q = self.search_var.get().strip()
        hits = self.reg.search(q)
        by_cat = {}
        for t, _p in hits:
            by_cat.setdefault(t.category, []).append(t)
        for cat in self.reg.categories():
            tools = by_cat.get(cat)
            if not tools:
                continue
            node = self.tree.insert("", "end", iid=f"cat::{cat}", text=f"  {cat}", open=True)
            for t in tools:
                ok, status = t.availability()
                label = t.id if ok else f"{t.id}  ({status[:12]})"
                self.tree.insert(node, "end", iid=t.id, text=f"    {label}")
        ready = sum(1 for t in self.reg.all() if t.ready)
        self.status_top.configure(
            text=(f"搜索命中 {sum(len(v) for v in by_cat.values())} 个" if q
                  else f"共 {len(self.reg.all())} 个工具 / 就绪 {ready}"))

    def _on_tree_select(self, _=None):
        sel = self.tree.selection()
        if not sel or sel[0].startswith("cat::"):
            return
        tool = self.reg.get(sel[0])
        if tool and tool is not self.tool:
            self._open_tool(tool)

    def _open_tool(self, tool: Tool):
        if self.runner and self.runner.running:
            if not messagebox.askyesno("切换工具", "当前还有命令在跑，结束它并切换？"):
                return
            self.runner.stop()
        self.tool = tool
        ok, status = tool.availability()
        self.cwd = tool.cwd_path if tool.cwd_path.is_dir() else APP_ROOT
        self._update_prompt()
        self.lbl_tool.configure(text=tool.name)
        self.lbl_state.configure(
            text=f"{tool.category} · " + ("● 就绪" if ok else "○ " + status))
        self._banner_tool(tool, ok, status)
        self._prefill(tool)
        if getattr(self, "picker", None):
            self.picker.hide()

    def _prefill(self, tool: Tool):
        if tool.runner == "python":
            entry = Path(tool.entry).name if tool.entry else "main.py"
            text = f"python {entry} "
        elif tool.runner == "module":
            text = f"python -m {tool.entry} "
        else:
            text = f"{Path(tool.entry).name} " if tool.entry else ""
        self.entry.delete(0, "end")
        self.entry.insert(0, text)
        self.entry.icursor("end")

    # ------------------------------------------------------------------ 提示
    def _prompt_text(self) -> str:
        try:
            p = str(self.cwd)
        except Exception:
            p = "?"
        return f"PS {p}>"

    def _update_prompt(self):
        self.prompt_lbl.configure(text=self._prompt_text())

    def _banner_start(self):
        self._append("web-fast 终端\n", "bold")
        self._append("左侧点一个工具，右边自动切到它的目录并填好启动命令。\n", "dim")
        self._append("直接在下面敲参数回车即执行；help 看内置命令。\n", "dim")
        self._append("", "")

    def _banner_tool(self, tool: Tool, ok: bool, status: str):
        line = "─" * 68
        self._append(line + "\n", "dim")
        self._append(f"{tool.name}", "bold")
        self._append(f"   {tool.category}   ", "")
        self._append("● 就绪\n" if ok else f"○ {status}\n", "ok" if ok else "warn")
        if tool.summary:
            self._append(tool.summary + "\n", "dim")
        self._append(f"目录  {tool.cwd_path}\n", "dim")
        params = " ".join(p.name for p in tool.params[:10])
        if params:
            self._append(f"常用  {params}\n", "info")
        self._append("params 看全部参数 | help 看内置命令 | 空行直接回车不执行\n", "dim")
        self._append(line + "\n", "dim")
        if not ok:
            self._append(f"[未就绪] {status}\n", "warn")
            if tool.repo:
                self._append(f"  可以 webfast fetch {tool.id}，或用右侧『改路径』指定目录\n", "dim")

    # ------------------------------------------------------------------ 输入
    def _on_enter(self, _=None):
        if self.picker.active:
            self.picker.pick()
            return "break"
        line = self.entry.get()
        self.entry.delete(0, "end")
        if self.mode == "running":
            shown = line if line else ""
            self._append(f"[stdin] {shown}\n", "dim")
            if self.runner is not None:
                self.runner.send(shown + "\n")
            return "break"
        line = line.rstrip()
        if not line.strip():
            return "break"
        self.history.append(line)
        self.hist_idx = len(self.history)
        self._record_history_values(line)
        self._append(f"{self._prompt_text()} {line}\n", "cmd")
        self._dispatch(line)
        return "break"

    def _record_history_values(self, line: str):
        """记住参数用过的值，下次弹候选时能直接选。"""
        tokens = split_cmd(line)
        i = 0
        while i + 1 < len(tokens):
            t = tokens[i]
            nxt = tokens[i + 1]
            if t.startswith("-") and not nxt.startswith("-"):
                lst = self.value_history.setdefault(t, [])
                if nxt not in lst:
                    lst.append(nxt)
                    if len(lst) > 50:
                        lst.pop(0)
                i += 2
            else:
                i += 1

    def _dispatch(self, line: str):
        parts = split_cmd(line)
        head = parts[0].lower() if parts else ""
        if head in ("clear", "cls"):
            self._clear()
            return
        if head in ("help", "?"):
            self._help()
            return
        if head in ("params", "param"):
            self._params_inline(line[len(parts[0]):].strip())
            return
        if head in ("use",):
            if len(parts) < 2:
                self._append("用法: use <工具名>\n", "warn")
                return
            t = self.reg.get(parts[1])
            if not t:
                self._append(f"没有这个工具: {parts[1]}\n", "err")
                return
            iid = t.id
            if self.tree.exists(iid):
                self.tree.selection_set(iid)
                self.tree.see(iid)
            self._open_tool(t)
            return
        if head == "cd":
            self._cd(line[2:].strip())
            return
        if head in ("pwd",):
            self._append(str(self.cwd) + "\n")
            return
        if head in ("exit", "quit"):
            self._append("终端不关，关窗口请点右上角 X。\n", "dim")
            return
        self._exec(line)

    def _cd(self, arg: str):
        if not arg:
            target = Path(os.path.expanduser("~"))
        else:
            p = Path(os.path.expanduser(arg))
            target = p if p.is_absolute() else (self.cwd / p)
        try:
            target = target.resolve()
        except Exception:
            pass
        if target.is_dir():
            self.cwd = target
            self._update_prompt()
        else:
            self._append(f"目录不存在: {target}\n", "err")

    def _help(self):
        rows = [
            ("help", "显示这份说明"),
            ("params [关键词]", "列出当前工具的全部参数（可按中文关键词过滤）"),
            ("use <工具名>", "切换到另一个工具"),
            ("cd <目录>", "切换终端当前目录（只影响本会话）"),
            ("pwd", "显示当前目录"),
            ("clear / cls", "清屏"),
            ("↑ / ↓", "翻历史命令"),
            ("Tab", "补全参数名"),
            ("空格", "参数有候选来源时，输入框上方弹出候选条"),
            ("Tab", "候选条出现后按 Tab 直接选中当前项"),
            ("↑ / ↓", "候选条出现时切换候选"),
            ("Esc", "收起候选条"),
            ("Ctrl+空格", "对光标前的参数强制弹候选"),
            ("Ctrl+C", "停止正在跑的命令"),
            ("其余任何输入", "当作 PowerShell 命令执行"),
        ]
        self._append("内置命令\n", "bold")
        for k, v in rows:
            self._append(f"  {k:<18} {v}\n", "")
        self._append("\n")

    def _params_inline(self, query: str = ""):
        if not self.tool:
            self._append("先选一个工具\n", "warn")
            return
        q = query.strip()
        rows = [p for p in self.tool.params if not q or p.matches(q)]
        if not rows:
            self._append(f"没有匹配「{q}」的参数\n", "warn")
            return
        self._append(f"{self.tool.id} 参数（{len(rows)} 个）\n", "bold")
        cur_group = None
        for p in rows:
            if p.group != cur_group:
                cur_group = p.group
                self._append(f"\n  [{cur_group}]\n", "info")
            req = "*" if p.required else " "
            self._append(f"  {req}{p.name:<18}", "cmd")
            self._append(f"{p.label:<12}", "")
            if p.help:
                self._append(p.help, "dim")
            if p.source:
                self._append("  [可弹窗选值]", "info")
            self._append("\n")
            if p.example:
                self._append(f"   {'':<18}例: {p.example}\n", "dim")
        self._append("\n")

    # ------------------------------------------------------------------ 执行
    def _powershell_argv(self, line: str) -> list:
        ps = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
        if ps:
            pre = "$OutputEncoding=[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
            return [ps, "-NoLogo", "-NoProfile", "-Command", pre + line]
        return [os.environ.get("COMSPEC", "cmd.exe"), "/c", line]

    def _exec(self, line: str):
        argv = split_cmd(line)
        if not argv:
            return
        head = argv[0].lower()
        direct = head in ("python", "python.exe", "py", "pythonw.exe")
        direct = direct or head.endswith((".exe", ".bat", ".cmd", ".ps1"))
        if not direct:
            try:
                direct = (self.cwd / argv[0]).is_file()
            except Exception:
                direct = False
        if direct:
            exe = sys.executable if head in ("python", "python.exe", "py") else argv[0]
            cmd_argv = [exe] + argv[1:]
        else:
            cmd_argv = self._powershell_argv(line)

        self.mode = "running"
        self.lbl_state.configure(text="◐ 运行中…")
        self.prompt_lbl.configure(fg=C_WARN)
        self._cur_argv = cmd_argv

        def on_line(text, kind="line"):
            self._q.put(("line", text))

        def on_exit(code):
            self._q.put(("exit", code))

        self.runner = Runner(on_line=on_line, on_exit=on_exit, stdin_pipe=True)
        try:
            self.runner.start(cmd_argv, self.cwd)
        except Exception as exc:
            self._append(f"[启动失败] {exc}\n", "err")
            self._finish(None)

    def _finish(self, code):
        self.mode = "idle"
        self.prompt_lbl.configure(fg=C_CMD)
        if self.tool:
            ok, status = self.tool.availability()
            self.lbl_state.configure(
                text=f"{self.tool.category} · " + ("● 就绪" if ok else "○ " + status))
        else:
            self.lbl_state.configure(text="")
        if code is not None:
            color = "ok" if code == 0 else "err"
            self._append(f"[退出码 {code}]\n\n", color)
            if self.tool and self._cur_argv:
                hist_append(self.tool.id, self._cur_argv, self.cwd, code)

    def _stop(self):
        if self.runner and self.runner.running:
            self._append("[正在结束进程…]\n", "warn")
            self.runner.stop()

    def _stop_shortcut(self):
        self._stop()

    def _poll(self):
        try:
            while True:
                kind, payload = self._q.get_nowait()
                if kind == "line":
                    tag = ""
                    low = payload.lower()
                    if any(k in low for k in ("traceback", "error", "exception", "失败")):
                        tag = "err"
                    elif any(k in low for k in ("warning", "warn", "警告")):
                        tag = "warn"
                    self._append(payload + "\n", tag)
                elif kind == "exit":
                    self._finish(payload)
        except queue.Empty:
            pass
        self.root.after(50, self._poll)

    def _append(self, text, tag=""):
        self.out.configure(state="normal")
        self.out.insert("end", text, tag or ())
        lines = int(self.out.index("end-1c").split(".")[0])
        if lines > 20000:
            self.out.delete("1.0", f"{lines - 15000}.0")
        self.out.see("end")
        self.out.configure(state="disabled")

    def _clear(self):
        self.out.configure(state="normal")
        self.out.delete("1.0", "end")
        self.out.configure(state="disabled")

    # ------------------------------------------------------------------ 补全 / 历史
    def _hist_prev(self, _=None):
        if self.picker.active:
            self.picker.move(-1)
            return "break"
        if not self.history:
            return "break"
        self.hist_idx = max(0, self.hist_idx - 1)
        self.entry.delete(0, "end")
        self.entry.insert(0, self.history[self.hist_idx])
        return "break"

    def _hist_next(self, _=None):
        if self.picker.active:
            self.picker.move(1)
            return "break"
        if not self.history:
            return "break"
        self.hist_idx = min(len(self.history), self.hist_idx + 1)
        self.entry.delete(0, "end")
        if self.hist_idx < len(self.history):
            self.entry.insert(0, self.history[self.hist_idx])
        return "break"

    def _complete(self, _=None):
        if not self.tool or self.mode == "running":
            return "break"
        text = self.entry.get()
        idx = self.entry.index("insert")
        start = idx
        while start > 0 and not text[start - 1].isspace():
            start -= 1
        frag = text[start:idx]
        if not frag.startswith("-"):
            return "break"
        names = [p.name for p in self.tool.params if p.name.startswith(frag)]
        if not names:
            self._append(f"[无匹配参数] {frag}\n", "dim")
            return "break"
        if len(names) == 1:
            new = text[:start] + names[0] + " " + text[idx:]
            self.entry.delete(0, "end")
            self.entry.insert(0, new)
            self.entry.icursor(start + len(names[0]) + 1)
        else:
            common = os.path.commonprefix(names)
            if len(common) > len(frag):
                new = text[:start] + common + text[idx:]
                self.entry.delete(0, "end")
                self.entry.insert(0, new)
                self.entry.icursor(start + len(common))
            self._append("  ".join(names[:20]) + "\n", "dim")
        return "break"

    # ------------------------------------------------------------------ 参数取值弹窗
    def _find_param(self, token: str):
        if not self.tool:
            return None
        for p in self.tool.params:
            if p.name == token:
                return p
        return None

    def _size_text(self, f: Path) -> str:
        try:
            n = f.stat().st_size
        except Exception:
            return ""
        if n < 1024:
            return f"{n} B"
        if n < 1024 * 1024:
            return f"{n / 1024:.1f} KB"
        return f"{n / 1024 / 1024:.1f} MB"

    def _resolve_source(self, p, overrides=None) -> list:
        """按 param.source 生成候选 [(显示, 实际插入值)]。"""
        from .resolve import expand_placeholders
        src = expand_placeholders((p.source or "").strip(), self.tool, overrides or {})
        base = self.cwd
        items = []
        if src.startswith("list:"):
            for x in src[5:].split("|"):
                x = x.strip()
                if x:
                    items.append((x, x))
            return items
        if src.startswith("glob:"):
            pat = src[5:].strip()
            pp = Path(pat)
            if not pp.is_absolute():
                pp = base / pp
            parent = pp.parent
            if not parent.is_dir():
                return []
            try:
                files = [f for f in parent.glob(pp.name)
                         if f.is_file() and not f.name.startswith("__")]
            except Exception:
                return []
            files.sort(key=lambda x: x.name.lower())
            for f in files:
                try:
                    rel = f.relative_to(base)
                except ValueError:
                    rel = f
                shown = Path(str(rel)).as_posix()
                value = Path(shown).stem if p.source_noext else shown
                items.append((shown, value))
            return items
        if src.startswith("dir:"):
            d = Path(src[4:].strip())
            if not d.is_absolute():
                d = base / d
            if not d.is_dir():
                return []
            for f in sorted(d.iterdir()):
                if f.is_file():
                    try:
                        rel = f.relative_to(base)
                    except ValueError:
                        rel = f
                    v = Path(str(rel)).as_posix()
                    items.append((v, v))
            return items
        return items

    def _insert_value(self, head: str, token: str, value: str, quote: bool = True):
        shown = '"' + value + '"' if quote else value
        new = head + token + " " + shown + " "
        self.entry.delete(0, "end")
        self.entry.insert(0, new)
        self.entry.icursor("end")
        self.entry.focus_set()

    def _candidates(self, p) -> list:
        from .registry import load_local_settings
        ov = load_local_settings().get(self.tool.id.lower(), {}) if self.tool else {}
        items = self._resolve_source(p, ov)
        if not items and p.type in ("string", "text"):
            items = [(v, v) for v in self.value_history.get(p.name, [])[-20:]]
        if p.type in ("file", "dir"):
            label = "【浏览目录…】" if p.type == "dir" else "【浏览文件…】"
            items = items + [(label, "__browse__")]
        return items

    def _maybe_inline(self):
        """敲完参数名按空格：候选条贴到输入框上方，Tab 选。"""
        if not self.tool or self.mode != "idle":
            return
        text = self.entry.get()
        idx = self.entry.index("insert")
        before = text[:idx]
        if not before.endswith(" "):
            return
        stripped = before.rstrip()
        if not stripped:
            return
        tokens = split_cmd(stripped)
        if not tokens:
            return
        last = tokens[-1]
        p = self._find_param(last)
        if p is None or p.type == "bool":
            return
        head = stripped[:-len(last)]
        items = [x for x in self._candidates(p) if x[1] != "__browse__"]
        if items:
            self.picker.show(items, head, last)
            return
        if p.type == "file":
            path = filedialog.askopenfilename(initialdir=str(self.cwd),
                                              title=f"选择 {p.label or p.name}")
            if path:
                self._insert_value(head, last, path)
        elif p.type == "dir":
            path = filedialog.askdirectory(initialdir=str(self.cwd),
                                           title=f"选择 {p.label or p.name}")
            if path:
                self._insert_value(head, last, path)

    def _apply_pick(self, head: str, token: str, value: str, kind: str = "value"):
        if kind == "param":
            p = self._find_param(value)
            needs = p is not None and p.type not in ("bool", "positional")
            is_long = value.startswith("--")
            if not needs:
                new = head + value + " "
                cur = len(new)
            elif is_long:
                new = head + value + "="
                cur = len(new)
            else:
                new = head + value + ' ""'
                cur = len(new) - 1
            self.entry.delete(0, "end")
            self.entry.insert(0, new)
            self.entry.icursor(cur)
            self.entry.focus_set()
            if needs and p is not None:
                items = self._candidates(p)
                if items:
                    self.picker.show(items, head, value, kind="value")
            return

        if value == "__browse__":
            p = self._find_param(token)
            if p is not None and p.type == "dir":
                path = filedialog.askdirectory(initialdir=str(self.cwd),
                                               title=f"选择 {p.label or p.name}")
            else:
                path = filedialog.askopenfilename(initialdir=str(self.cwd),
                                                  title=f"选择 {p.label if p else token}")
            if not path:
                return
            value = path

        p = self._find_param(token)
        is_long = token.startswith("--")
        sep = "=" if is_long else " "

        if p is not None and p.source_multi:
            prefix = head + token + sep
            text = self.entry.get()
            tail = text[len(prefix):].strip() if text.startswith(prefix) else ""
            tail = tail.lstrip("=").strip()
            if tail.startswith(chr(34)) and tail.endswith(chr(34)):
                tail = tail[1:-1]
            if tail and tail != value:
                joined = tail + "," + value
            else:
                joined = value
            self.entry.delete(0, "end")
            self.entry.insert(0, prefix + joined + " ")
            self.entry.icursor("end")
            self.entry.focus_set()
            return

        need_quote = (not is_long) or (" " in value) or ("\t" in value)
        shown = (chr(34) + value + chr(34)) if need_quote else value
        new = head + token + sep + shown + " "
        self.entry.delete(0, "end")
        self.entry.insert(0, new)
        self.entry.icursor("end")
        self.entry.focus_set()

    def _on_space(self, event):
        if self.picker.active and self.picker.kind == "param":
            self.picker.hide()
        self.entry.insert("insert", " ")
        if not self.picker.active:
            self._maybe_inline()
        return "break"

    @staticmethod
    def _subseq(needle: str, hay: str) -> bool:
        it = iter(hay)
        return all(ch in it for ch in needle)

    def _on_key_release(self, event):
        if event.keysym in ("Tab", "ISO_Left_Tab", "Up", "Down", "Escape", "Return",
                            "Shift_L", "Shift_R", "Control_L", "Control_R",
                            "Left", "Right", "Home", "End", "space"):
            return
        if not self.tool or self.mode != "idle":
            return
        if self.picker.active and self.picker.kind == "value":
            prefix = self.picker.head + self.picker.token + " "
            text = self.entry.get()
            if text.startswith(prefix):
                self.picker.filter(text[len(prefix):])
            else:
                self.picker.hide()
            return
        self._show_param_candidates()

    def _show_param_candidates(self):
        """输入 - 开头的片段时，列出匹配的参数名。"""
        text = self.entry.get()
        idx = self.entry.index("insert")
        before = text[:idx]
        start = idx
        while start > 0 and not before[start - 1].isspace():
            start -= 1
        token = before[start:idx]
        if not token.startswith("-"):
            if self.picker.active and self.picker.kind == "param":
                self.picker.hide()
            return
        if "=" in token:
            pname, frag = token.split("=", 1)
            p = self._find_param(pname)
            if p is not None:
                items = self._candidates(p)
                if items:
                    shown = [x for x in items
                             if not frag or frag.lower() in x[0].lower()
                             or frag.lower() in x[1].lower()]
                    if shown:
                        self.picker.show(shown, before[:start] + pname, pname, kind="value")
                        return
            self.picker.hide()
            return
        if len(token) > 24:
            return
        frag = token.lstrip("-").lower()
        rows = []
        for i, p in enumerate(self.tool.params):
            n = p.name.lstrip("-").lower()
            if not frag or n.startswith(frag) or self._subseq(frag, n):
                label = f"{p.name:<20} {p.label}"
                if p.source:
                    label += "  [可选]"
                rank = 0 if (not frag or n.startswith(frag)) else 1
                rows.append((rank, i, label, p.name))
        rows.sort(key=lambda r: (r[0], r[1]))
        if not rows:
            self.picker.hide()
            return
        items = [(r[2], r[3]) for r in rows]
        self.picker.show(items, text[:start], token, kind="param")

    def _on_tab(self, event=None):
        if self.picker.active:
            self.picker.pick()
            return "break"
        return self._complete()

    def _on_escape(self, event=None):
        if self.picker.active:
            self.picker.hide()
            return "break"
        return None

    def _on_ctrl_space(self, _=None):
        if not self.tool:
            return "break"
        text = self.entry.get()
        idx = self.entry.index("insert")
        start = idx
        while start > 0 and not text[start - 1].isspace():
            start -= 1
        token = text[start:idx].strip()
        p = self._find_param(token)
        if p is None:
            self._append(f"[{token}] 不是当前工具的参数\n", "dim")
            return "break"
        head = text[:start]
        items = self._candidates(p)
        if items:
            self.picker.show(items, head, token)
        else:
            self._append(f"[{token}] 没有配置候选来源，直接手打\n", "dim")
        return "break"

    # ------------------------------------------------------------------ 参数表
    def _show_params(self):
        if not self.tool:
            messagebox.showinfo("web-fast", "先在左边选一个工具")
            return
        win = tk.Toplevel(self.root)
        win.title(f"{self.tool.id} 参数表")
        win.geometry("880x520")
        win.transient(self.root)

        top = ttk.Frame(win, padding=8)
        top.pack(fill="x")
        ttk.Label(top, text="筛选").pack(side="left")
        qv = tk.StringVar()
        ttk.Entry(top, textvariable=qv, width=30).pack(side="left", padx=6)
        ttk.Label(top, text="（中文、参数名、说明里都能搜）", style="Sub.TLabel").pack(side="left")

        cols = ("name", "label", "group", "help")
        tv = ttk.Treeview(win, columns=cols, show="headings")
        for c, w, t in (("name", 170, "参数"), ("label", 130, "中文名"),
                        ("group", 90, "分组"), ("help", 460, "说明")):
            tv.heading(c, text=t)
            tv.column(c, width=w, anchor="w")
        vsb = ttk.Scrollbar(win, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        tv.pack(fill="both", expand=True, padx=8, pady=(0, 4))

        tip = tk.Text(win, height=6, font=FONT_UI, wrap="word", relief="flat",
                      background="#f2f4f8")
        tip.pack(fill="x", padx=8, pady=(0, 8))

        def refill(*_):
            tv.delete(*tv.get_children())
            q = qv.get().strip()
            for p in self.tool.params:
                if q and not p.matches(q):
                    continue
                tv.insert("", "end", values=(p.name, p.label, p.group, p.help))
        qv.trace_add("write", refill)
        refill()

        def on_sel(_=None):
            sel = tv.selection()
            if not sel:
                return
            vals = tv.item(sel[0], "values")
            p = next((x for x in self.tool.params if x.name == vals[0]), None)
            tip.configure(state="normal")
            tip.delete("1.0", "end")
            if p:
                parts = [f"{p.name}   {p.label}", p.help]
                if p.choices:
                    parts.append("可选值: " + " / ".join(p.choices))
                if p.example:
                    parts.append("示例: " + p.example)
                if p.tags:
                    parts.append("关键词: " + ", ".join(p.tags))
                tip.insert("1.0", chr(10).join(x for x in parts if x))
            tip.configure(state="disabled")
        tv.bind("<<TreeviewSelect>>", on_sel)

        def insert_selected():
            sel = tv.selection()
            if not sel:
                return
            name = tv.item(sel[0], "values")[0]
            cur = self.entry.get()
            self.entry.delete(0, "end")
            self.entry.insert(0, cur + " " + name + " " if cur else name + " ")
            self.entry.icursor("end")
            win.destroy()
        ttk.Button(win, text="插入到命令行", command=insert_selected).pack(
            side="right", padx=8, pady=(0, 8))

    # ------------------------------------------------------------------ 杂项
    def _open_tool_dir(self):
        if not self.tool:
            return
        p = self.tool.cwd_path
        if not p.is_dir():
            messagebox.showinfo("web-fast", f"目录不存在:\n{p}")
            return
        os.startfile(str(p))

    def _open_root(self):
        p = tools_root()
        p.mkdir(parents=True, exist_ok=True)
        os.startfile(str(p))

    def _show_settings(self):
        """按工具分的设置面板：左边选工具，右边改路径和子目录。"""
        from .discover import discover
        from .registry import (load_local_paths, load_local_settings,
                               save_local_config, setting_value)

        win = tk.Toplevel(self.root)
        win.title("设置")
        win.geometry("900x560")
        win.transient(self.root)

        head = ttk.Frame(win, padding=(12, 10, 12, 6))
        head.pack(fill="x")
        ttk.Label(head, text="设置", font=("Microsoft YaHei UI", 13, "bold")).pack(side="left")
        ttk.Label(head, text="  左边选工具，右边改它的路径和子目录",
                  style="Sub.TLabel").pack(side="left")

        body = ttk.Frame(win, padding=(12, 0, 12, 4))
        body.pack(fill="both", expand=True)

        left = ttk.Frame(body, width=180)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        tree = ttk.Treeview(left, show="tree", selectmode="browse")
        tree.pack(fill="both", expand=True)
        for t in self.reg.all():
            ok, status = t.availability()
            tree.insert("", "end", iid=t.id, text=("● " if ok else "○ ") + t.id)

        right = ttk.Frame(body, padding=(14, 0, 0, 0))
        right.pack(side="left", fill="both", expand=True)

        title = ttk.Label(right, text="", font=("Consolas", 12, "bold"))
        title.pack(anchor="w", pady=(4, 2))
        state_lbl = ttk.Label(right, text="", style="Sub.TLabel")
        state_lbl.pack(anchor="w", pady=(0, 8))

        fields = ttk.Frame(right)
        fields.pack(fill="both", expand=True)

        holder = {"tid": None, "cwd": None, "subs": {}}

        def render(tid):
            for w in fields.winfo_children():
                w.destroy()
            holder["tid"] = tid
            holder["subs"] = {}
            t = self.reg.get(tid)
            if t is None:
                return
            ok, status = t.availability()
            title.configure(text=t.name)
            state_lbl.configure(text=("● 就绪" if ok else "○ " + status),
                                foreground=C_CMD if ok else C_WARN)

            def add_field(label, key, value, help_text):
                ttk.Label(fields, text=label).pack(anchor="w", pady=(6, 2))
                var = tk.StringVar(value=value or "")
                row = ttk.Frame(fields)
                row.pack(fill="x")
                ttk.Entry(row, textvariable=var, font=FONT_MONO).pack(
                    side="left", fill="x", expand=True)
                ttk.Button(row, text="…", width=3,
                           command=lambda v=var: v.set(
                               filedialog.askdirectory() or v.get())).pack(side="left", padx=(4, 0))
                if help_text:
                    ttk.Label(fields, text=help_text, style="Sub.TLabel",
                              wraplength=600, justify="left").pack(anchor="w", pady=(1, 0))
                return var

            holder["cwd"] = add_field(
                "工具根目录", "root", str(t.cwd_path),
                "整个工具的安装目录。换电脑时路径里的用户名会自动重映射。")

            over = load_local_settings().get(t.id.lower(), {})
            for s in t.settings:
                holder["subs"][s.key] = add_field(
                    s.label or s.key, s.key, setting_value(t, s.key, over),
                    (s.help or "") + ("　默认：" + s.default if s.default else ""))

            if not t.settings:
                ttk.Label(fields, text="这个工具没有额外的子目录配置。",
                          style="Sub.TLabel").pack(anchor="w", pady=12)

        def on_select(_=None):
            sel = tree.selection()
            if sel:
                render(sel[0])

        tree.bind("<<TreeviewSelect>>", on_select)

        foot = ttk.Frame(win, padding=(12, 6, 12, 4))
        foot.pack(fill="x")
        msg = ttk.Label(foot, text="", style="Sub.TLabel")
        msg.pack(side="left")

        def do_scan():
            msg.configure(text="扫描中…")
            win.update_idletasks()
            try:
                found = discover(max_depth=4)
            except Exception as exc:
                msg.configure(text=f"扫描失败: {exc}")
                return
            paths = load_local_paths()
            n = 0
            for tid, p in found.items():
                t = self.reg.get(tid)
                if t is not None:
                    paths[tid] = str(p)
                    n += 1
            if n:
                save_local_config(paths=paths)
                self.reg = Registry().load()
                tree.delete(*tree.get_children())
                for t in self.reg.all():
                    ok, _ = t.availability()
                    tree.insert("", "end", iid=t.id, text=("● " if ok else "○ ") + t.id)
                if holder["tid"]:
                    render(holder["tid"])
            msg.configure(text=f"扫到 {n} 个工具" if n else "没扫到工具")

        def do_save():
            tid = holder["tid"]
            if not tid:
                return
            paths = load_local_paths()
            settings = load_local_settings()
            cwd = holder["cwd"].get().strip() if holder["cwd"] else ""
            if cwd:
                paths[tid] = cwd
            else:
                paths.pop(tid, None)
            cur = settings.get(tid, {})
            tt = self.reg.get(tid)
            base = tt.cwd_path if tt is not None else None

            def _rel(val):
                try:
                    return Path(val).resolve().relative_to(base.resolve()).as_posix()
                except Exception:
                    return val

            for key, var in holder["subs"].items():
                v = var.get().strip()
                if v:
                    cur[key] = _rel(v) if base is not None else v
                else:
                    cur.pop(key, None)
            if cur:
                settings[tid] = cur
            else:
                settings.pop(tid, None)
            try:
                save_local_config(paths=paths, tool_settings=settings)
            except Exception as exc:
                msg.configure(text=f"保存失败: {exc}")
                return
            self.reg = Registry().load()
            self._fill_tree()
            self.tool = None
            t = self.reg.get(tid)
            if t is not None:
                ok, status = t.availability()
                tree.item(tid, text=("● " if ok else "○ ") + tid)
                title.configure(text=t.name)
                state_lbl.configure(text=("● 就绪" if ok else "○ " + status),
                                    foreground=C_CMD if ok else C_WARN)
            msg.configure(text="已保存")
            self._append("[设置] " + tid + " 已保存" + chr(10), "info")

        ttk.Button(foot, text="保存这个工具", command=do_save).pack(side="right", padx=4)
        ttk.Button(foot, text="自动扫描本机", command=do_scan).pack(side="right", padx=4)
        ttk.Button(foot, text="关闭", command=win.destroy).pack(side="right", padx=4)

        about = ttk.Label(win, text="由 parrot 所写 · 反馈或改进请发送邮箱至 2571308976@qq.com",
                          style="Sub.TLabel", padding=(12, 0, 12, 10))
        about.pack(fill="x")

        first = self.tool.id if self.tool else (self.reg.all()[0].id if self.reg.all() else None)
        if first:
            tree.selection_set(first)
            tree.see(first)
            render(first)

    def _set_path(self):
        if not self.tool:
            return
        d = filedialog.askdirectory(initialdir=str(self.tool.cwd_path),
                                    title=f"选择 {self.tool.id} 所在的目录")
        if not d:
            return
        mapping = load_local_paths()
        mapping[self.tool.id.lower()] = Path(d).as_posix()
        save_local_paths(mapping)
        self.tool.cwd = Path(d).as_posix()
        self.cwd = Path(d)
        self._update_prompt()
        self._fill_tree()
        ok, status = self.tool.availability()
        self.lbl_state.configure(text=f"{self.tool.category} · " +
                                 ("● 就绪" if ok else "○ " + status))
        self._append(f"[已改路径] {self.tool.id} -> {d}  ({status})\n", "info")

    def _doctor(self):
        self._clear()
        self._append("web-fast 体检\n", "bold")
        self._append(f"Python: {sys.version.split()[0]}  {sys.executable}\n")
        self._append(f"工具根目录: {tools_root()}\n\n")
        bad = 0
        for t in self.reg.all():
            ok, status = t.availability()
            if ok:
                self._append(f"  OK   {t.id:<12} {status}\n", "ok")
            else:
                bad += 1
                self._append(f"  MISS {t.id:<12} {status}\n", "warn")
        for err in self.reg.errors:
            self._append(f"  描述文件错误: {err}\n", "err")
        self._append(f"\n{len(self.reg.all()) - bad}/{len(self.reg.all())} 个工具就绪\n\n", "info")

    def _on_close(self):
        if self.runner and self.runner.running:
            if not messagebox.askyesno("退出", "还有命令在跑，结束并退出？"):
                return
            self.runner.stop()
        self.root.destroy()


def run_gui(registry: Registry | None = None) -> int:
    reg = registry or Registry().load()
    root = tk.Tk()
    root.title("web-fast · Web 安全工具终端")
    root.geometry("1180x760")
    root.minsize(940, 560)
    try:
        root.tk.call("tk", "scaling", 1.2)
    except Exception:
        pass
    WebFastGUI(root, reg)
    root.mainloop()
    return 0
