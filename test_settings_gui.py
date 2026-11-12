"""Tkinter 设置面板测试：按工具切换、子目录字段、保存。"""
import sys
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from webfast.gui import WebFastGUI
from webfast.registry import Registry


def find_all(widget, cls):
    out = []
    for c in widget.winfo_children():
        if isinstance(c, cls):
            out.append(c)
        out.extend(find_all(c, cls))
    return out


def main() -> int:
    reg = Registry().load()
    root = tk.Tk()
    root.withdraw()
    app = WebFastGUI(root, reg)
    root.update()

    app._show_settings()
    root.update()

    import tkinter.ttk as ttk
    tops = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]
    assert tops, "设置面板没打开"
    win = tops[-1]
    print("[1] 打开设置:", win.title())

    trees = find_all(win, ttk.Treeview)
    assert trees, "没有工具列表"
    items = trees[0].get_children()
    print("[2] 左侧工具数:", len(items), [trees[0].item(i, "text") for i in items])
    assert len(items) >= 5

    # 切到 sqlmap
    trees[0].selection_set("sqlmap")
    root.update()
    entries = find_all(win, ttk.Entry)
    print("[3] sqlmap 字段数:", len(entries))
    vals = [e.get() for e in entries if e.get()]
    print("    值:", [v[-28:] for v in vals])
    assert len(entries) >= 4, "sqlmap 应该有 root + txt/tamper/output 四个字段"
    assert any("txt" in v for v in vals), "没看到 txt 目录"
    assert any("tamper" in v for v in vals), "没看到 tamper 目录"

    # 切到 dirsearch
    trees[0].selection_set("dirsearch")
    root.update()
    entries2 = find_all(win, ttk.Entry)
    vals2 = [e.get() for e in entries2 if e.get()]
    print("[4] dirsearch 字段数:", len(entries2))
    print("    值:", [v[-24:] for v in vals2])
    assert any("db" in v for v in vals2), "没看到字典目录"

    # 关于信息
    labels = [str(w.cget("text")) for w in find_all(win, ttk.Label)]
    about = [x for x in labels if "parrot" in x]
    print("[5] 关于:", about)
    assert about and "2571308976@qq.com" in about[0]

    win.destroy()
    root.destroy()
    print("Tkinter 设置面板通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
