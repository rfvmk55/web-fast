"""内联候选条测试：出现在输入框上方、Tab 选中、↑↓ 切换、打字过滤。"""
import sys
import tkinter as tk
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))

from webfast.gui import WebFastGUI
from webfast.registry import Registry


def main() -> int:
    reg = Registry().load()
    root = tk.Tk()
    root.geometry("1100x700+100+100")
    app = WebFastGUI(root, reg)
    root.update()

    app._open_tool(reg.get("sqlmap"))
    root.update()

    # 1 敲 -r 空格，候选条应该出现在输入框上方
    app.entry.delete(0, "end")
    app.entry.insert(0, "python sqlmap.py -r ")
    app.entry.icursor("end")
    app._maybe_inline()
    root.update()
    print("[1] 候选条激活:", app.picker.active)
    assert app.picker.active, "候选条没出现"
    print("    候选项:", [r[0] for r in app.picker.rows])
    assert len(app.picker.rows) >= 2, "候选项数量不对"
    geo = app.picker.top.wm_geometry()
    entry_y = app.entry.winfo_rooty()
    print("    候选条几何:", geo, "  输入框 y:", entry_y)
    py = int(geo.split("+")[2])
    assert py < entry_y, "候选条没有在输入框上方"
    print("    -> 通过")

    # 2 方向键移动
    print("[2] ↓ 切换")
    app._hist_next()
    root.update()
    print("    当前索引:", app.picker.index, "项:", app.picker.rows[app.picker.index][0])
    assert app.picker.index == 1
    print("    -> 通过")

    # 3 Tab 选中
    print("[3] Tab 选中")
    app._on_tab()
    root.update()
    got = app.entry.get()
    print("    命令行:", repr(got))
    print("    候选条关闭:", not app.picker.active)
    assert "txt/request.txt" in got, "Tab 没把值填进去"
    assert not app.picker.active
    print("    -> 通过")

    # 4 继续打字过滤
    print("[4] 打字过滤")
    app.entry.delete(0, "end")
    app.entry.insert(0, "python sqlmap.py -r ")
    app.entry.icursor("end")
    app._maybe_inline()
    root.update()
    n_all = len(app.picker.rows)
    app.entry.insert("end", "po")
    app._on_key_release(SimpleNamespace(keysym="o"))
    root.update()
    print(f"    全部 {n_all} -> 过滤后 {len(app.picker.rows)}:", [r[0] for r in app.picker.rows])
    assert len(app.picker.rows) == 1 and "post_login" in app.picker.rows[0][0]
    app._on_tab()
    root.update()
    print("    选中后:", repr(app.entry.get()))
    assert "txt/post_login.txt" in app.entry.get()
    print("    -> 通过")

    # 5 Esc 关闭
    print("[5] Esc 收起")
    app.entry.delete(0, "end")
    app.entry.insert(0, "python sqlmap.py --tamper ")
    app.entry.icursor("end")
    app._maybe_inline()
    root.update()
    n = len(app.picker.rows)
    app._on_escape()
    root.update()
    print("    tamper 候选数:", n, " 关闭后 active:", app.picker.active)
    assert not app.picker.active
    print("    -> 通过")

    # 6 多选参数仍然能工作
    print("[6] --tamper 支持多选")
    app.entry.delete(0, "end")
    app.entry.insert(0, "python sqlmap.py --tamper ")
    app.entry.icursor("end")
    app._maybe_inline()
    root.update()
    app.picker.filter("space")
    root.update()
    print("    过滤 space:", [r[1] for r in app.picker.rows])
    assert app.picker.rows and "space2comment" in [r[1] for r in app.picker.rows]
    print("    -> 通过")

    # 7 回车优先确认候选，不执行
    print("[7] 回车确认候选而不是执行")
    app.entry.delete(0, "end")
    app.entry.insert(0, "python sqlmap.py -r ")
    app.entry.icursor("end")
    app._maybe_inline()
    root.update()
    app._on_enter()
    root.update()
    print("    模式:", app.mode, " 命令行:", repr(app.entry.get()))
    assert app.mode == "idle", "回车不该直接执行"
    assert "txt/" in app.entry.get()
    print("    -> 通过")

    root.destroy()
    print("内联候选条全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
