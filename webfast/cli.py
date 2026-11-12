"""命令行入口：webfast <子命令>。"""
from __future__ import annotations

import argparse
import difflib
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import __version__
from .launcher import Runner, build_argv, quote_cmd
from .registry import (APP_ROOT, LOCAL_PATHS_FILE, Registry, Tool, expand_vars,
                       load_local_paths, load_settings, save_local_paths, tools_root)

RST = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"


def _c(text: str, color: str, enable: bool = True) -> str:
    if not enable or os.name != "nt" and not sys.stdout.isatty():
        return text
    return f"{color}{text}{RST}"


def cmd_list(reg: Registry, args) -> int:
    rows = reg.all()
    if args.group:
        rows = [t for t in rows if t.category == args.group]
    if not rows:
        print("没有匹配的工具。用 webfast scan 看 third_party 下未注册的工具。")
        return 0
    w = max(len(t.id) for t in rows) + 2
    cur = None
    for t in rows:
        if t.category != cur:
            cur = t.category
            print(f"\n[{cur}]")
        ok, status = t.availability()
        flag = _c("OK  ", GREEN) if ok else _c("MISS", RED)
        print(f"  {flag} {t.id.ljust(w)} {t.name}")
        if not ok:
            print(f"       {DIM}{status}{RST}")
    print(f"\n共 {len(rows)} 个。webfast info <id> 看参数表；webfast run <id> ... 直接跑。")
    return 0


def cmd_info(reg: Registry, args) -> int:
    t = reg.get(args.tool)
    if not t:
        print(f"没有这个工具: {args.tool}")
        return 1
    ok, status = t.availability()
    print(f"{BOLD}{t.id}{RST}  {t.name}   [{t.category}]  {'' if ok else '(未就绪)'}")
    print(f"  {t.summary}")
    print(f"  状态: {_c(status, GREEN) if ok else _c(status, RED)}")
    print(f"  目录: {t.cwd_path}")
    if t.entry:
        print(f"  入口: {t.entry_resolved}   runner={t.runner}")
    if t.repo:
        print(f"  仓库: {t.repo}")
    if t.install:
        print(f"  安装: {t.install}")
    print()
    cur_group = None
    for p in t.params:
        if p.group != cur_group:
            cur_group = p.group
            print(f"{CYAN}-- {cur_group} --{RST}")
        req = _c("*必填", YELLOW) if p.required else ""
        if p.type == "bool":
            default = " 默认=开" if p.default else ""
        else:
            default = f" 默认={p.default}" if p.default not in (None, "") else ""
        print(f"  {p.name.ljust(18)} {p.label}   {req}{default}")
        if p.help:
            print(f"  {'':18} {DIM}{p.help}{RST}")
        if p.choices:
            print(f"  {'':18} {DIM}可选: {', '.join(p.choices)}{RST}")
        if p.example:
            print(f"  {'':18} {DIM}例: {p.example}{RST}")
    if t.templates:
        print(f"\n{CYAN}预设组合{RST}")
        for tp in t.templates:
            print(f"  {tp.name:<16} {tp.desc}")
            for k, v in tp.values.items():
                print(f"  {'':16} {k} = {v}")
    return 0


def cmd_search(reg: Registry, args) -> int:
    hits = reg.search(args.query)
    if not hits:
        print(f"没搜到「{args.query}」。试试更短的中文词，如 注入 / 代理 / 线程 / 超时。")
        return 0
    for t, params in hits:
        print(f"{BOLD}{t.id}{RST}  {t.name}   [{t.category}]")
        for p in params[:12]:
            print(f"    {p.name:<18} {p.label}   {DIM}{p.help[:60]}{RST}")
        if len(params) > 12:
            print(f"    {DIM}... 还有 {len(params) - 12} 个匹配参数{RST}")
    print(f"\n{len(hits)} 个工具命中。webfast run <id> <参数> ... 直接跑。")
    return 0


def cmd_run(reg: Registry, args) -> int:
    t = reg.get(args.tool)
    if not t:
        cand = difflib.get_close_matches(args.tool, [x.id for x in reg.all()], n=3)
        tip = f" 你是不是想: {', '.join(cand)}" if cand else ""
        print(f"没有这个工具: {args.tool}{tip}")
        return 1

    extra = list(args.argv or [])
    if extra and extra[0] == "--":
        extra = extra[1:]

    # argparse 的 REMAINDER 会吞掉后置开关，这里捞回来
    show = bool(args.show)
    force = bool(args.force)
    for flag in ("--show", "--force"):
        while flag in extra:
            extra.remove(flag)
            if flag == "--show":
                show = True
            else:
                force = True

    # 参数拼写检查：只提示，不阻断
    known = {p.name for p in t.params}
    for tok in extra:
        if tok.startswith("-") and tok not in known and tok != "--help":
            near = difflib.get_close_matches(tok, sorted(known), n=2, cutoff=0.7)
            if near:
                print(f"{DIM}[提示] {tok} 不在描述表里，也许是 {near[0]}{RST}")

    argv = t.base_command() + extra
    print(f"{DIM}cwd: {t.cwd_path}{RST}")
    print(f"{GREEN}$ {quote_cmd(argv)}{RST}\n")
    if show:
        return 0

    ok, status = t.availability()
    if not ok and not force:
        print(f"{t.id} 未就绪: {status}")
        if t.repo:
            print(f"  先跑: webfast fetch {t.id}")
        return 2

    code_holder = {"code": None}

    def on_line(line: str, kind: str = "line"):
        print(line, flush=True)

    def on_exit(code):
        code_holder["code"] = code

    run = Runner(on_line=on_line, on_exit=on_exit)
    try:
        run.start(argv, t.cwd_path)
    except Exception as exc:
        print(f"{RED}启动失败: {exc}{RST}")
        return 3
    try:
        while run._thread and run._thread.is_alive():
            run._thread.join(0.3)
    except KeyboardInterrupt:
        print(f"\n{YELLOW}中断，正在结束子进程...{RST}")
        run.stop()
    from .history import append
    append(t.id, argv, t.cwd_path, code_holder["code"])
    print(f"\n{DIM}退出码 {code_holder['code']}{RST}")
    return int(code_holder["code"] or 0)


def cmd_discover(reg: Registry, args) -> int:
    from .discover import CANDIDATE_ENTRIES, discover
    known = {t.id.lower() for t in reg.all()}
    roots = [Path(expand_vars(r)) for r in (args.root or [])] or None
    print("扫描已安装的工具…")
    found = discover(roots=roots, max_depth=args.depth,
                     on_hit=lambda tid, p: print(f"  + {tid:<12} {p}"))
    if not found:
        print("没找到。用 webfast set-path <工具> <目录> 手动指定。")
        return 1
    mapping = load_local_paths()
    hits, skipped = 0, []
    for tid, p in found.items():
        if tid.lower() in known:
            mapping[tid.lower()] = p.as_posix()
            hits += 1
        else:
            skipped.append(f"{tid} -> {p}")
    if not hits:
        print("找到的目录都还没有对应的工具描述文件。")
        for s in skipped:
            print("  " + s)
        return 1
    f = save_local_paths(mapping)
    print("")
    print(f"已写入 {f}")
    print(f"{hits} 个工具的路径已登记。跑 webfast list 看状态。")
    if skipped:
        print("")
        print("没有描述文件、未登记：")
        for s in skipped:
            print("  " + s)
    return 0


def cmd_set_path(reg: Registry, args) -> int:
    t = reg.get(args.tool)
    if not t:
        print(f"没有这个工具: {args.tool}")
        return 1
    p = Path(expand_vars(args.path))
    if not p.is_dir():
        print(f"目录不存在: {p}")
        return 1
    mapping = load_local_paths()
    mapping[t.id.lower()] = p.as_posix()
    f = save_local_paths(mapping)
    t.cwd = p.as_posix()
    ok, status = t.availability()
    print(f"已登记 {t.id} -> {p}")
    print(f"  {f}")
    print(f"  状态: {status}")
    return 0 if ok else 1


def cmd_deps(reg: Registry, args) -> int:
    t = reg.get(args.tool)
    if not t:
        print(f"没有这个工具: {args.tool}")
        return 1
    miss = t.missing_modules()
    if not miss:
        print(f"{t.id} 依赖齐全。")
        return 0
    print(f"{t.id} 缺 Python 依赖: {', '.join(miss)}")
    pkg = " ".join(miss)
    print(f"  补: python -m pip install {pkg}")
    if args.install:
        rc = subprocess.call([sys.executable, "-m", "pip", "install", *miss])
        if rc == 0:
            ok, status = t.availability()
            print(f"  装完状态: {status}")
        return rc
    return 1


def cmd_history(reg: Registry, args) -> int:
    from .history import read_history
    rows = read_history(limit=args.limit)
    if not rows:
        print("还没有运行记录。")
        return 0
    for r in rows:
        mark = "OK " if r.get("code") == 0 else f"RC{r.get('code')}"
        print(f"{r.get('time', '')}  {mark:<4} {r.get('tool', ''):<10} {r.get('cmd', '')}")
    return 0


def cmd_setup(reg: Registry, args) -> int:
    from .discover import discover
    print("web-fast 路径设置")
    print(f"  项目目录    {APP_ROOT}")
    print(f"  工具根目录  {tools_root()}")
    print(f"  路径配置    {LOCAL_PATHS_FILE}")
    print()
    if not args.no_scan:
        print("扫描本机已装工具…")
        found = discover(max_depth=args.depth)
        known = {t.id.lower() for t in reg.all()}
        mapping = load_local_paths()
        hits = []
        for tid, p in found.items():
            if tid.lower() in known:
                mapping[tid.lower()] = str(p)
                hits.append((tid, p))
        if hits:
            save_local_paths(mapping)
            for tid, p in hits:
                print(f"  + {tid:<12} {p}")
        else:
            print("  没扫到新工具")
        print()
    for t in reg.all():
        ok, status = t.availability()
        flag = "OK  " if ok else "MISS"
        print(f"  {flag} {t.id:<12} {t.cwd_path}")
        if not ok:
            print(f"       {status}")
            print(f"       改: webfast set-path {t.id} <目录>")
    print()
    print("其它方式：")
    print("  1) 把工具放进项目内 third_party/<工具名>/，自动生效，搬走也不丢")
    print("  2) 环境变量覆盖：set WEBFAST_SQLMAP=D:\\tools\\sqlmap")
    print("  3) 手动改 local_paths.toml 的 [paths] 段")
    return 0


def cmd_app(reg: Registry, args) -> int:
    from .app import run_app
    return run_app(reg, width=args.width, height=args.height, port=args.port)


def cmd_web(reg: Registry, args) -> int:
    from .server import serve
    return serve(reg, port=args.port, open_browser=not args.no_browser)


def cmd_doctor(reg: Registry, args) -> int:
    print(f"web-fast {__version__}")
    print(f"  Python      {sys.version.split()[0]}  ({sys.executable})")
    print(f"  项目目录    {APP_ROOT}")
    print(f"  工具根目录  {tools_root()}  {'存在' if tools_root().is_dir() else '不存在'}")
    print(f"  git         {shutil.which('git') or '未安装'}")
    print(f"  tkinter     {'可用' if _has_tk() else '不可用（GUI 打不开）'}")
    if reg.errors:
        print(f"\n{RED}描述文件错误{RST}")
        for e in reg.errors:
            print(f"  {e}")
    print()
    bad = 0
    for t in reg.all():
        ok, status = t.availability()
        if not ok:
            bad += 1
            print(f"  {_c('MISS', RED)} {t.id:<14} {status}")
            if t.repo:
                print(f"       webfast fetch {t.id}")
    print(f"\n{len(reg.all()) - bad}/{len(reg.all())} 个工具就绪。")
    return 0 if bad == 0 else 1


def _has_tk() -> bool:
    try:
        import tkinter  # noqa: F401
        return True
    except Exception:
        return False


def cmd_scan(reg: Registry, args) -> int:
    root = tools_root()
    if not root.is_dir():
        print(f"工具根目录不存在: {root}")
        print("先建目录，把工具 clone 进去，或改 settings.toml 的 tools_root。")
        return 1
    unknown = reg.scan_unregistered()
    if not unknown:
        print("third_party 下没有未注册的目录。")
        return 0
    print(f"发现 {len(unknown)} 个未注册目录：\n")
    for p in unknown:
        guess = _guess_entry(p)
        kind = "python" if guess else "binary"
        tpl = f"""id = "{p.name}"
name = "{p.name}"
category = "其它"
summary = ""
runner = "{kind}"
entry = "{guess or p.name + '.py'}"
requires = []
# repo = "https://github.com/xxx/xxx.git"

[[param]]
name = "--help"
label = "帮助"
type = "bool"
default = false
help = "把这个工具的常用参数补进来，保存后 GUI 自动生成表单"
"""
        out = root / f"{p.name}.todo.toml"
        out.write_text(tpl, encoding="utf-8")
        print(f"  {p.name:<20} 入口推测: {guess or '未找到'}  ->  {out.name}")
    print("\n把 *.todo.toml 补全参数后改名为 *.toml 放进 tools/ 目录，重启即生效。")
    return 0


def _guess_entry(d: Path):
    for name in ("main.py", "run.py", "tool.py", f"{d.name}.py", f"{d.name.replace('-', '')}.py"):
        if (d / name).exists():
            return name
    for py in d.glob("*.py"):
        return py.name
    return None


def cmd_fetch(reg: Registry, args) -> int:
    t = reg.get(args.tool)
    if not t:
        print(f"没有这个工具: {args.tool}")
        return 1
    if not t.repo:
        print(f"{t.id} 没配置 repo 字段。手动下载后放到 {t.cwd_path}")
        return 1
    if getattr(args, "pip", False):
        pkg = t.pip or t.id
        print(f"$ {sys.executable} -m pip install {pkg}")
        rc = subprocess.call([sys.executable, "-m", "pip", "install", pkg])
        if rc == 0:
            print(f"{GREEN}完成{RST}  webfast run {t.id} ...")
        return rc
    git = shutil.which("git")
    if not git:
        print("没装 git。装完再跑，或手动 clone。")
        return 1
    target = t.cwd_path
    if target.exists() and any(target.iterdir()):
        print(f"{target} 已存在且非空，跳过。要重装先删掉它。")
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    print(f"$ git clone {t.repo} {target}")
    rc = subprocess.call([git, "clone", "--depth", "1", t.repo, str(target)])
    if rc == 0:
        print(f"{GREEN}完成{RST}  webfast run {t.id} ...")
    return rc


def cmd_install_path(reg: Registry, args) -> int:
    if os.name != "nt":
        print("该命令仅用于 Windows。")
        return 1
    launcher = APP_ROOT / "webfast.py"
    if not launcher.exists():
        print(f"找不到 {launcher}")
        return 1
    py = sys.executable
    body = f'@echo off\r\n"{py}" "{launcher}" %*\r\n'
    gui_body = f'@echo off\r\nstart "" "{py}w" "{APP_ROOT / "webfast.pyw"}"\r\n'

    scripts = Path(py).parent / "Scripts"
    if scripts.is_dir() and _on_path(str(scripts)):
        target_dir = scripts
        note = "已在 PATH 中"
    else:
        target_dir = Path(os.environ["LOCALAPPDATA"]) / "webfast" / "bin"
        target_dir.mkdir(parents=True, exist_ok=True)
        note = "已写入用户 PATH（需新开终端生效）"
        _add_user_path(str(target_dir))
    (target_dir / "webfast.cmd").write_text(body, encoding="gbk", errors="replace")
    (target_dir / "webfast-gui.cmd").write_text(gui_body, encoding="gbk", errors="replace")
    print(f"已安装到 {target_dir}")
    print(f"  webfast list          {note}")
    print("  新开一个 PowerShell / cmd 窗口后生效。")
    return 0


def _on_path(folder: str) -> bool:
    parts = [p.strip().strip('"').lower()
             for p in os.environ.get("PATH", "").split(os.pathsep) if p.strip()]
    return folder.lower() in parts


def _add_user_path(folder: str) -> None:
    import winreg
    key_path = r"Environment"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0,
                            winreg.KEY_READ | winreg.KEY_WRITE) as k:
            try:
                cur, typ = winreg.QueryValueEx(k, "Path")
            except FileNotFoundError:
                cur, typ = "", winreg.REG_EXPAND_SZ
            items = [x for x in cur.split(";") if x.strip()]
            if any(i.lower() == folder.lower() for i in items):
                return
            items.append(folder)
            winreg.SetValueEx(k, "Path", 0, winreg.REG_EXPAND_SZ, ";".join(items))
    except Exception as exc:
        print(f"写 PATH 失败: {exc}；手动把 {folder} 加进 PATH 即可。")
        return
    try:
        import ctypes
        HWND_BROADCAST = 0xFFFF
        WM_SETTINGCHANGE = 0x001A
        SMTO_ABORTIFHUNG = 0x0002
        res = ctypes.c_ulong()
        ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment",
            SMTO_ABORTIFHUNG, 5000, ctypes.byref(res))
    except Exception:
        pass


def cmd_export(reg: Registry, args) -> int:
    t = reg.get(args.tool)
    if not t:
        print(f"没有这个工具: {args.tool}")
        return 1
    argv = t.base_command() + list(args.argv or [])
    cmdline = quote_cmd(argv)
    out = Path(args.output or (APP_ROOT / "output" / f"{t.id}.bat"))
    out.parent.mkdir(parents=True, exist_ok=True)
    body = f'@echo off\r\ncd /d "{t.cwd_path}"\r\n{cmdline} %*\r\npause\r\n'
    out.write_text(body, encoding="gbk", errors="replace")
    print(f"已生成 {out}")
    print(cmdline)
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    reg = Registry().load()

    if not argv:
        from .app import run_app
        return run_app(reg)

    ap = argparse.ArgumentParser(prog="webfast", description="Web 安全工具集合运行器")
    ap.add_argument("-v", "--version", action="version", version=f"web-fast {__version__}")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("list", help="列出所有工具")
    p.add_argument("-g", "--group", help="只看某个分类")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("info", help="查看工具参数表")
    p.add_argument("tool")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("search", help="按中文关键词搜参数")
    p.add_argument("query")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("run", help="运行工具（参数原样透传）")
    p.add_argument("tool")
    p.add_argument("--show", action="store_true", help="只打印命令行，不执行")
    p.add_argument("--force", action="store_true", help="未就绪也强行跑")
    p.add_argument("argv", nargs=argparse.REMAINDER)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("doctor", help="体检：环境 / 工具 / 依赖")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("scan", help="扫描 third_party 未注册的目录")
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("discover", help="扫描本机已安装的工具，写进 local_paths.toml")
    p.add_argument("-d", "--depth", type=int, default=5)
    p.add_argument("--root", action="append", help="额外扫描的根目录，可多次给")
    p.set_defaults(func=cmd_discover)

    p = sub.add_parser("set-path", help="手动指定工具所在目录")
    p.add_argument("tool")
    p.add_argument("path")
    p.set_defaults(func=cmd_set_path)

    p = sub.add_parser("deps", help="检查/补齐某个工具的 Python 依赖")
    p.add_argument("tool")
    p.add_argument("--install", action="store_true", help="直接 pip install 补齐")
    p.set_defaults(func=cmd_deps)

    p = sub.add_parser("history", help="最近的运行记录")
    p.add_argument("-n", "--limit", type=int, default=20)
    p.set_defaults(func=cmd_history)

    p = sub.add_parser("fetch", help="git clone 工具仓库，或 --pip 从 PyPI 装")
    p.add_argument("tool")
    p.add_argument("--pip", action="store_true", help="改用 pip 安装")
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("export", help="导出可双击的 bat 脚本")
    p.add_argument("tool")
    p.add_argument("-o", "--output")
    p.add_argument("argv", nargs=argparse.REMAINDER)
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("setup", help="路径设置向导：扫描本机工具并登记")
    p.add_argument("-d", "--depth", type=int, default=4)
    p.add_argument("--no-scan", action="store_true")
    p.set_defaults(func=cmd_setup)

    p = sub.add_parser("app", help="打开桌面窗口（独立应用，不经浏览器）")
    p.add_argument("-p", "--port", type=int, default=None)
    p.add_argument("--width", type=int, default=1440)
    p.add_argument("--height", type=int, default=900)
    p.set_defaults(func=cmd_app)

    p = sub.add_parser("web", help="打开 Web 界面（浏览器）")
    p.add_argument("-p", "--port", type=int, default=8765)
    p.add_argument("--no-browser", action="store_true")
    p.set_defaults(func=cmd_web)

    p = sub.add_parser("gui", help="打开图形界面")
    p.set_defaults(func=lambda r, a: cmd_gui(r))

    p = sub.add_parser("install-path", help="把 webfast 注册为全局命令")
    p.set_defaults(func=cmd_install_path)

    args = ap.parse_args(argv)
    if not getattr(args, "func", None):
        ap.print_help()
        return 0
    return args.func(reg, args)


def cmd_gui(reg: Registry) -> int:
    try:
        from .gui import run_gui
    except Exception as exc:
        print(f"GUI 启动失败: {exc}")
        print("用命令行模式: webfast list / info / run")
        return 1
    return run_gui(reg)


if __name__ == "__main__":
    sys.exit(main())
