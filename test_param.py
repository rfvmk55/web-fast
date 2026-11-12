"""参数名实时候选测试：输入 -l 出 --level，输入 -r 出 -r/--risk，Tab 补全后接值候选。"""
import sys
import tkinter as tk
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))

from webfast.gui import WebFastGUI
from webfast.registry import Registry


def type_into(app, root, text, keysym="x"):
    app.entry.delete(0, "end")
    app.entry.insert(0, text)
    app.entry.icursor("end")
    app._on_key_release(SimpleNamespace(keysym=keysym))
    root.update()


def main() -> int:
    reg = Registry().load()
    root = tk.Tk()
    root.geometry("1100x700+80+80")
    app = WebFastGUI(root, reg)
    root.update()
    app._open_tool(reg.get("sqlmap"))
    root.update()

    base = "python sqlmap.py "

    # 1 输入 - 就出全部参数
    print("[1] 只敲一个减号")
    type_into(app, root, base + "-", "-")
    print("    候选数:", len(app.picker.rows))
    assert app.picker.active and len(app.picker.rows) >= 15, "没列出参数"
    print("    前 5:", [r[1] for r in app.picker.rows[:5]])
    print("    -> 通过")

    # 2 输入 -l 过滤出 --level
    print("[2] 敲 -l")
    type_into(app, root, base + "-l", "l")
    names = [r[1] for r in app.picker.rows]
    print("    候选:", names)
    assert "--level" in names, "-l 没匹配到 --level"
    print("    -> 通过")

    # 3 Tab 补全成 --level
    print("[3] Tab 补全")
    app._on_tab()
    root.update()
    print("    命令行:", repr(app.entry.get()))
    assert app.entry.get() == base + "--level=", "双横线参数应拼成 --level="
    print("    -> 通过")

    # 4 输入 -r，应该同时出 -r 和 --risk
    print("[4] 敲 -r")
    type_into(app, root, base + "-r", "r")
    names = [r[1] for r in app.picker.rows]
    print("    候选:", names)
    assert "-r" in names, "没出现 -r"
    assert "--risk" in names, "没出现 --risk"
    assert names[0] == "-r", "精确短参数应排第一"
    print("    -> 通过")

    # 5 Tab 选中 -r，应立刻弹出 txt 文件值候选
    print("[5] Tab 选中 -r 后自动接值候选")
    app._on_tab()
    root.update()
    print("    命令行:", repr(app.entry.get()))
    print("    值候选激活:", app.picker.active, "kind:", app.picker.kind)
    assert app.entry.get() == base + "-r " + chr(34) + chr(34), "参数补全没带引号"
    assert app.picker.active and app.picker.kind == "value", "没接上值候选"
    print("    值候选:", [r[0] for r in app.picker.rows])
    print("    -> 通过")

    # 6 再 Tab 填入文件
    print("[6] 再按 Tab 选文件")
    app._on_tab()
    root.update()
    print("    命令行:", repr(app.entry.get()))
    assert '"txt/' in app.entry.get(), "没填带引号的文件"
    assert not app.picker.active
    print("    -> 通过")

    # 7 -u 也要能选出来
    print("[7] 敲 -u")
    type_into(app, root, base + "-u", "u")
    names = [r[1] for r in app.picker.rows]
    print("    候选:", names)
    assert "-u" in names
    app._on_tab()
    root.update()
    print("    命令行:", repr(app.entry.get()))
    assert app.entry.get() == base + "-u " + chr(34) + chr(34)
    print("    -> 通过")

    # 8 输入值后不再弹参数候选
    print("[8] 打完值后不该弹参数名")
    type_into(app, root, base + "-u http://t/?id=1", "1")
    print("    候选条激活:", app.picker.active)
    assert not app.picker.active, "打完值还在弹"
    print("    -> 通过")

    # 9 历史值：执行过的 -u 值会变成候选
    print("[9] 历史值候选")
    app.value_history.setdefault("-u", []).append("http://old/?id=2")
    type_into(app, root, base + "-u", "u")
    app._on_tab()
    root.update()
    print("    值候选:", [r[0] for r in app.picker.rows] if app.picker.active else "无")
    assert app.picker.active and "http://old/?id=2" in [r[0] for r in app.picker.rows]
    print("    -> 通过")

    root.destroy()
    print("参数名候选全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
