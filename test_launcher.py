"""执行引擎测试：cwd、中文流式输出、退出码、中途停止。"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from webfast.launcher import Runner, build_argv, quote_cmd
from webfast.registry import Registry

DEMO = Path(__file__).resolve().parent / "third_party" / "_demo"
DEMO.mkdir(parents=True, exist_ok=True)
(DEMO / "demo.py").write_text(
    "import os, sys, time\n"
    "print('cwd =', os.getcwd())\n"
    "print('中文输出测试：注入点 / 数据库 / 表名')\n"
    "print('参数:', sys.argv[1:])\n"
    "for i in range(3):\n"
    "    print(f'进度 {i+1}/3', flush=True)\n"
    "    time.sleep(0.2)\n"
    "print('done')\n",
    encoding="utf-8")


def run_once(argv, cwd, timeout=20):
    lines, codes = [], []

    def on_line(s):
        lines.append(s)

    def on_exit(c):
        codes.append(c)

    r = Runner(on_line=on_line, on_exit=on_exit)
    r.start(argv, cwd)
    t0 = time.time()
    while r._thread.is_alive() and time.time() - t0 < timeout:
        r._thread.join(0.1)
    return lines, codes


def main() -> int:
    ok = True

    lines, codes = run_once([sys.executable, str(DEMO / "demo.py"), "arg1", "值 二"], DEMO)
    print("[1] 正常执行")
    for ln in lines:
        print("   ", ln)
    assert codes == [0], f"退出码异常: {codes}"
    joined = "\n".join(lines)
    assert "注入点" in joined, "中文乱码"
    assert str(DEMO) in joined, "cwd 未切到工具目录"
    assert "值 二" in joined, "带空格参数丢失"
    print("   -> 通过：cwd / 中文 / 参数分隔 全对\n")

    lines, codes = run_once([sys.executable, "-c", "import sys; print('err', file=sys.stderr); sys.exit(7)"], DEMO)
    print("[2] stderr 合并 + 非零退出码")
    print("   ", lines, codes)
    assert codes == [7], f"退出码应 7，实际 {codes}"
    print("   -> 通过\n")

    print("[3] 中途停止")
    r = Runner(on_line=lambda s: None, on_exit=lambda c: None)
    r.start([sys.executable, "-c", "import time; time.sleep(30)"], DEMO)
    time.sleep(0.6)
    assert r.running, "进程没起来"
    t0 = time.time()
    r.stop()
    time.sleep(0.3)
    print(f"   stop 耗时 {time.time()-t0:.2f}s, 仍在运行={r.running}")
    assert not r.running, "停止失败"
    print("   -> 通过\n")

    reg = Registry().load()
    sm = reg.get("sqlmap")
    values = {"-u": "http://t/?id=1", "--level": "3", "--dbs": True,
              "--tamper": "space2comment,between", "--threads": ""}
    argv = build_argv(sm, values)
    print("[4] 命令构建")
    print("   ", quote_cmd(argv))
    assert "--dbs" in argv and "space2comment,between" in argv
    assert "--threads" not in argv, "空值不应输出"
    print("   -> 通过\n")

    print("执行引擎全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
