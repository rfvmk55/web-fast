"""桌面窗口：用系统 WebView2 把界面装成独立应用，不经过浏览器。"""
from __future__ import annotations

import os
import sys
import threading
import time

from .registry import Registry
from .server import start_server

TITLE = "Web-Fast · BaBaTa"


def _has_webview() -> bool:
    try:
        import webview  # noqa: F401
        return True
    except Exception:
        return False


class Bridge:
    """给前端调的原生能力。"""

    def pick_folder(self, initial: str = "") -> str:
        try:
            import webview
            windows = getattr(webview, "windows", None)
            if not windows:
                return ""
            w = windows[0]
            res = w.create_file_dialog(webview.FOLDER_DIALOG,
                                       directory=initial or "")
            if not res:
                return ""
            if isinstance(res, (list, tuple)):
                return res[0] if res else ""
            return str(res)
        except Exception as exc:
            print("[pick_folder]", exc)
            return ""


def _dark_titlebar(window=None) -> bool:
    """把 Windows 原生标题栏染成和界面同色，做到视觉无缝。"""
    import ctypes

    hwnd = 0
    try:
        h = window.gui.window.Handle
        hwnd = int(h) if isinstance(h, int) else int(h.ToInt64())
    except Exception:
        hwnd = 0
    if not hwnd:
        try:
            hwnd = int(ctypes.windll.user32.FindWindowW(None, TITLE))
        except Exception:
            hwnd = 0
    if not hwnd:
        print("[titlebar] 拿不到窗口句柄，跳过")
        return False

    try:
        dwm = ctypes.windll.dwmapi
    except Exception as exc:
        print("[titlebar] 没有 dwmapi:", exc)
        return False

    def setv(attr, value):
        v = ctypes.c_int(value)
        try:
            return int(dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), ctypes.sizeof(v)))
        except Exception as e:
            return -999

    r = {
        "dark20": setv(20, 1),
        "dark19": setv(19, 1),
        "caption": setv(35, 0x001D1510),
        "text": setv(36, 0x00F8EFE8),
        "border": setv(34, 0x001D1510),
    }
    print("[titlebar] hwnd=%s %s" % (hwnd, r))
    return r["dark20"] == 0 or r["dark19"] == 0


def _open_with_edge_app(url: str, width: int, height: int) -> bool:
    """pywebview 不可用时的退路：Edge 的 --app 模式（无地址栏的独立窗口）。"""
    import shutil
    import subprocess
    cands = [
        os.path.join(os.environ.get("PROGRAMFILES(X86)", ""),
                     "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(os.environ.get("PROGRAMFILES", ""),
                     "Microsoft", "Edge", "Application", "msedge.exe"),
        shutil.which("msedge.exe"),
        shutil.which("chrome.exe"),
    ]
    exe = next((c for c in cands if c and os.path.isfile(c)), None)
    if not exe:
        return False
    profile = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
                           "web-fast", "app-profile")
    os.makedirs(profile, exist_ok=True)
    try:
        subprocess.Popen([
            exe, "--app=" + url,
            "--window-size=" + str(width) + "," + str(height),
            "--user-data-dir=" + profile,
            "--no-first-run", "--no-default-browser-check",
            "--disable-features=Translate",
        ], creationflags=0x00000008)
        return True
    except Exception:
        return False


def run_app(registry: Registry = None, width: int = 1440, height: int = 900,
            port: int = None, fallback_browser: bool = False) -> int:
    reg = registry or Registry().load()
    try:
        httpd, used = start_server(reg, port)
    except RuntimeError as exc:
        print(exc)
        return 1
    url = "http://127.0.0.1:" + str(used) + "/"

    if _has_webview():
        import webview
        window = webview.create_window(
            TITLE, url,
            width=width, height=height,
            min_size=(980, 620),
            background_color="#080b10",
            text_select=True,
            js_api=Bridge(),
        )

        def apply_later():
            def go():
                try:
                    _dark_titlebar(window)
                except Exception as exc:
                    print("[titlebar] 失败:", exc)
            for delay in (0.3, 1.0, 2.5):
                threading.Timer(delay, go).start()

        try:
            window.events.shown += apply_later
        except Exception:
            try:
                window.events.loaded += apply_later
            except Exception:
                pass

        from .registry import WEB_DIR
        icon = str(WEB_DIR / "icon.ico")
        try:
            webview.start(debug=False, icon=icon if os.path.isfile(icon) else None)
        except TypeError:
            webview.start(debug=False)
        finally:
            try:
                httpd.shutdown()
            except Exception:
                pass
        return 0

    if _open_with_edge_app(url, width, height):
        print("pywebview 未安装，已用 Edge 的独立应用窗口打开：" + url)
        print("装一次 pywebview 就能彻底脱开浏览器：python -m pip install pywebview")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            httpd.shutdown()
        return 0

    if fallback_browser:
        import webbrowser
        webbrowser.open(url)
        print("已用默认浏览器打开：" + url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            httpd.shutdown()
        return 0

    print("没有可用的 WebView2 / Edge，也没装 pywebview。")
    print("解决：python -m pip install pywebview")
    httpd.shutdown()
    return 1
