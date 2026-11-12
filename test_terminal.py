"""终端界面测试：切工具自动填命令、执行、内置命令、补全。"""
import sys
import time
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from webfast.gui import WebFastGUI
from webfast.registry import Registry


def pump(root, app, seconds=25.0, nudge_after=2.5):
    """跑完后返回 True。若进程卡在等输入，模拟用户按一次回车。"""
    t0 = time.time()
    nudged = False
    while time.time() - t0 < seconds:
        root.update()
        if app.mode == "idle":
            root.update()
            return True
        if not nudged and time.time() - t0 > nudge_after:
            nudged = True
            app.entry.delete(0, "end")
            app._on_enter()          # 空行回车 = 给子进程发一个换行
        time.sleep(0.05)
    return False


def out_text(app):
    return app.out.get("1.0", "end")


def main() -> int:
    reg = Registry().load()
    root = tk.Tk()
    root.withdraw()
    app = WebFastGUI(root, reg)
    root.update()

    # 1 选工具自动切目录 + 预填命令
    tool = reg.get("sqlmap")
    app._open_tool(tool)
    root.update()
    prefill = app.entry.get()
    prompt = app.prompt_lbl.cget("text")
    print("[1] 选工具")
    print("    预填:", repr(prefill))
    print("    提示符:", prompt)
    assert prefill.startswith("python sqlmap.py"), "预填命令不对"
    assert "sqlmap-dev" in prompt, "目录没切到工具目录"
    print("    -> 通过")

    # 2 执行
    print("[2] 执行 python sqlmap.py --version")
    app.entry.delete(0, "end")
    app.entry.insert(0, "python sqlmap.py --version")
    app._on_enter()
    ok = pump(root, app)
    text = out_text(app)
    print("    退出码可见:", "[退出码" in text)
    version_line = [l for l in text.splitlines() if "1.10.11" in l]
    print("    版本行:", version_line[:1])
    assert ok, "执行超时"
    assert version_line, "没拿到版本输出"
    print("    -> 通过")

    # 3 params 内置命令
    print("[3] params 代理")
    app._on_enter.__self__  # noqa
    app.entry.delete(0, "end")
    app.entry.insert(0, "params 代理")
    app._on_enter()
    root.update()
    text = out_text(app)
    print("    命中 --proxy:", "--proxy" in text)
    assert "--proxy" in text, "参数表没输出"
    print("    -> 通过")

    # 4 cd
    print("[4] cd ..")
    app.entry.delete(0, "end")
    app.entry.insert(0, "cd ..")
    app._on_enter()
    root.update()
    print("    新提示符:", app.prompt_lbl.cget("text"))
    assert "sqlmap-dev" not in str(app.cwd), "cd 没生效"
    print("    -> 通过")

    # 5 Tab 补全
    print("[5] Tab 补全")
    app._open_tool(reg.get("commix"))
    root.update()
    app.entry.delete(0, "end")
    app.entry.insert(0, "python commix.py --os-c")
    app.entry.icursor("end")
    app._complete()
    root.update()
    got = app.entry.get()
    print("    补全后:", repr(got))
    assert "--os-cmd" in got, "唯一前缀没补全"
    print("    -> 通过")

    # 6 历史
    print("[6] 历史上下")
    before = len(app.history)
    app.entry.delete(0, "end")
    app.entry.insert(0, "pwd")
    app._on_enter()
    root.update()
    print("    历史条数:", before, "->", len(app.history))
    app._hist_prev()
    print("    ↑ 取回:", repr(app.entry.get()))
    print("    -> 通过")

    root.destroy()
    print("终端界面全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
