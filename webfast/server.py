"""本地 Web 服务：给 web 前端提供工具列表、候选值、命令执行与流式输出。"""
from __future__ import annotations

import json
import mimetypes
import os
import queue
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .launcher import Runner, split_cmd
from .registry import (APP_ROOT, USER_ROOT, WEB_DIR, Registry, load_local_paths,
                       load_local_settings, rebind_user_path, save_local_config,
                       save_local_paths, setting_value, tools_root)
from .resolve import candidates as resolve_candidates

DEFAULT_PORT = 8765


def _pick_folder(initial: str = "") -> str:
    """Windows 原生「选择文件夹」对话框（浏览器模式下用）。"""
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return ""
    BIF_RETURNONLYFSDIRS = 0x0001
    BIF_EDITBOX = 0x0010
    BIF_NEWDIALOGSTYLE = 0x0040

    class BROWSEINFO(ctypes.Structure):
        _fields_ = [
            ("hwndOwner", wintypes.HWND),
            ("pidlRoot", ctypes.c_void_p),
            ("pszDisplayName", wintypes.LPWSTR),
            ("lpszTitle", wintypes.LPCWSTR),
            ("ulFlags", ctypes.c_uint),
            ("lpfn", ctypes.c_void_p),
            ("lParam", wintypes.LPARAM),
            ("iImage", ctypes.c_int),
        ]

    try:
        shell32 = ctypes.windll.shell32
        ole32 = ctypes.windll.ole32
        ole32.CoInitialize(None)
    except Exception:
        return ""
    name_buf = ctypes.create_unicode_buffer(260)
    bi = BROWSEINFO()
    bi.pszDisplayName = ctypes.cast(name_buf, wintypes.LPWSTR)
    bi.lpszTitle = "选择文件夹"
    bi.ulFlags = BIF_RETURNONLYFSDIRS | BIF_EDITBOX | BIF_NEWDIALOGSTYLE
    try:
        pidl = shell32.SHBrowseForFolderW(ctypes.byref(bi))
    except Exception:
        return ""
    if not pidl:
        return ""
    try:
        path_buf = ctypes.create_unicode_buffer(260)
        shell32.SHGetPathFromIDListW(pidl, path_buf)
        ole32.CoTaskMemFree(pidl)
        return path_buf.value
    except Exception:
        return ""


class Run:
    def __init__(self, rid: str, tool_id: str, argv: list, cwd):
        self.id = rid
        self.tool_id = tool_id
        self.argv = argv
        self.cwd = str(cwd)
        self.q = queue.Queue()
        self.code = None
        self.started = time.time()
        self.runner = None

    def start(self):
        def on_line(text, kind="line"):
            self.q.put({"type": kind, "text": text})

        def on_progress(summary):
            self.q.put({"type": "progress", "text": summary})

        def on_exit(code):
            self.code = code
            self.q.put({"type": "exit", "code": code})
            self.q.put(None)

        self.runner = Runner(on_line=on_line, on_exit=on_exit, stdin_pipe=True,
                             on_progress=on_progress)
        self.runner.start(self.argv, self.cwd)


class WebApp:
    def __init__(self, registry: Registry):
        self.reg = registry
        self.runs = {}
        self.value_history = {}
        self.lock = threading.Lock()

    # ---------------------------------------------------------------- 数据
    def tools_payload(self) -> dict:
        out = []
        for t in self.reg.all():
            ok, status = t.availability()
            out.append({
                "id": t.id, "name": t.name, "category": t.category,
                "summary": t.summary, "ready": ok, "status": status,
                "path": str(t.cwd_path),
            })
        return {"tools": out, "total": len(out),
                "ready": sum(1 for x in out if x["ready"]),
                "errors": self.reg.errors}

    def tool_payload(self, tid: str) -> dict:
        t = self.reg.get(tid)
        if not t:
            return {"error": "no such tool"}
        ok, status = t.availability()
        params = []
        for p in t.params:
            params.append({
                "name": p.name, "label": p.label, "help": p.help,
                "type": p.type, "default": p.default, "required": p.required,
                "choices": p.choices, "group": p.group, "example": p.example,
                "tags": p.tags, "source": p.source,
                "source_multi": p.source_multi, "repeat": p.repeat,
                "quote": p.quote,
            })
        return {
            "id": t.id, "name": t.name, "category": t.category,
            "summary": t.summary, "ready": ok, "status": status,
            "cwd": str(t.cwd_path), "runner": t.runner, "entry": t.entry,
            "params": params,
        }

    def candidates_payload(self, tid: str, pname: str) -> dict:
        t = self.reg.get(tid)
        if not t:
            return {"items": []}
        p = t.param(pname)
        if not p:
            return {"items": []}
        over = load_local_settings().get(t.id.lower(), {})
        items = resolve_candidates(t, p, t.cwd_path, self.value_history, over)
        return {"items": [{"label": a, "value": b} for a, b in items]}

    def settings_payload(self) -> dict:
        from .registry import LOCAL_PATHS_FILE
        overrides = load_local_settings()
        items = []
        for t in self.reg.all():
            ok, status = t.availability()
            subs = []
            for s in t.settings:
                val = setting_value(t, s.key, overrides.get(t.id.lower(), {}))
                subs.append({
                    "key": s.key, "label": s.label, "type": s.type,
                    "help": s.help, "default": s.default,
                    "value": val,
                    "exists": bool(val) and Path(val).is_dir(),
                })
            items.append({
                "id": t.id, "name": t.name, "runner": t.runner,
                "entry": t.entry, "cwd": str(t.cwd_path),
                "ready": ok, "status": status, "env": t.env_var,
                "settings": subs,
            })
        return {
            "app_root": str(USER_ROOT),
            "tools_root": str(tools_root()),
            "paths_file": str(LOCAL_PATHS_FILE),
            "tools": items,
        }

    def set_tool(self, tid: str, path: str, subs: dict) -> dict:
        t = self.reg.get(tid)
        if not t:
            return {"ok": False, "error": "no such tool"}
        paths = load_local_paths()
        settings = load_local_settings()
        cur = settings.get(t.id.lower(), {})

        # 先定工具根目录，后面子目录才能按它算相对路径
        if str(path or "").strip():
            p = Path(os.path.expanduser(str(path).strip()))
            if not p.is_dir():
                alt = rebind_user_path(p)
                if alt is None:
                    return {"ok": False, "error": f"目录不存在: {p}"}
                p = alt
            paths[t.id.lower()] = p.as_posix()
            t.cwd = p.as_posix()
        else:
            paths.pop(t.id.lower(), None)
            t.cwd = ""

        root_dir = t.cwd_path

        def _rel(val: str) -> str:
            """工具目录内的子路径存相对路径，换根目录自动跟着走。"""
            try:
                rel = Path(val).resolve().relative_to(root_dir.resolve())
                return rel.as_posix()
            except Exception:
                return val

        for key, val in (subs or {}).items():
            val = str(val or "").strip()
            if val:
                cur[key] = _rel(val)
            else:
                cur.pop(key, None)
        if cur:
            settings[t.id.lower()] = cur
        else:
            settings.pop(t.id.lower(), None)

        save_local_config(paths=paths, tool_settings=settings)
        ok, status = t.availability()
        over = load_local_settings().get(t.id.lower(), {})
        subs_out = [{"key": s.key, "label": s.label,
                     "value": setting_value(t, s.key, over)}
                    for s in t.settings]
        return {"ok": True, "status": status, "ready": ok,
                "cwd": str(t.cwd_path), "settings": subs_out}

    def discover_payload(self, depth: int = 4) -> dict:
        from .discover import discover
        known = {t.id.lower() for t in self.reg.all()}
        found = discover(max_depth=depth)
        hits = []
        for tid, p in found.items():
            if tid.lower() in known:
                hits.append({"tool": tid, "path": Path(p).as_posix()})
        return {"found": hits}

    def history_payload(self) -> dict:
        from .history import read_history
        return {"rows": read_history(limit=30)}

    # ---------------------------------------------------------------- 执行
    def _powershell_argv(self, line: str) -> list:
        import shutil
        ps = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
        if ps:
            pre = "$OutputEncoding=[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
            return [ps, "-NoLogo", "-NoProfile", "-Command", pre + line]
        return [os.environ.get("COMSPEC", "cmd.exe"), "/c", line]

    def build_argv(self, line: str, cwd) -> list:
        parts = split_cmd(line)
        if not parts:
            return []
        head = parts[0].lower()
        direct = head in ("python", "python.exe", "py", "pythonw.exe")
        direct = direct or head.endswith((".exe", ".bat", ".cmd", ".ps1"))
        if not direct:
            try:
                direct = (Path(cwd) / parts[0]).is_file()
            except Exception:
                direct = False
        if direct:
            from .registry import python_exe
            exe = python_exe() if head in ("python", "python.exe", "py") else parts[0]
            return [exe] + parts[1:]
        return self._powershell_argv(line)

    def _record_values(self, line: str):
        tokens = split_cmd(line)
        i = 0
        while i + 1 < len(tokens):
            t, nxt = tokens[i], tokens[i + 1]
            if t.startswith("-") and not nxt.startswith("-"):
                lst = self.value_history.setdefault(t, [])
                if nxt not in lst:
                    lst.append(nxt)
                    if len(lst) > 50:
                        lst.pop(0)
                i += 2
            else:
                i += 1

    def start_run(self, tid: str, line: str) -> dict:
        t = self.reg.get(tid)
        cwd = t.cwd_path if (t and t.cwd_path.is_dir()) else USER_ROOT
        argv = self.build_argv(line, cwd)
        if not argv:
            return {"error": "空命令"}
        self._record_values(line)
        rid = uuid.uuid4().hex[:12]
        run = Run(rid, tid, argv, cwd)
        with self.lock:
            self.runs[rid] = run
            if len(self.runs) > 60:
                for k in sorted(self.runs, key=lambda x: self.runs[x].started)[:20]:
                    if self.runs[k].runner and not self.runs[k].runner.running:
                        del self.runs[k]
        run.start()
        return {"run": rid, "cwd": str(cwd), "argv": argv}

    def send_stdin(self, rid: str, text: str) -> dict:
        run = self.runs.get(rid)
        if run is None or run.runner is None:
            return {"ok": False}
        return {"ok": run.runner.send(text)}

    def stop_run(self, rid: str) -> dict:
        run = self.runs.get(rid)
        if run is None or run.runner is None:
            return {"ok": False}
        run.runner.stop()
        return {"ok": True}

    def set_path(self, tid: str, path: str) -> dict:
        t = self.reg.get(tid)
        if not t:
            return {"ok": False, "error": "no such tool"}
        mapping = load_local_paths()
        if not str(path).strip():
            mapping.pop(t.id.lower(), None)
            save_local_paths(mapping)
            t.cwd = ""
            ok, status = t.availability()
            return {"ok": True, "status": status, "ready": ok,
                    "cwd": str(t.cwd_path), "cleared": True}
        p = Path(os.path.expanduser(path))
        if not p.is_dir():
            alt = rebind_user_path(p)
            if alt is None:
                return {"ok": False, "error": f"目录不存在: {p}"}
            p = alt
        mapping[t.id.lower()] = p.as_posix()
        save_local_paths(mapping)
        t.cwd = p.as_posix()
        ok, status = t.availability()
        return {"ok": True, "status": status, "ready": ok, "cwd": p.as_posix()}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    app: WebApp = None

    def log_message(self, *args):
        pass

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            self.close_connection = True

    # ------------------------------------------------------------ helpers
    def _send(self, code, body, ctype):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(data)
        except Exception:
            pass

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _static(self, name: str):
        base = WEB_DIR.resolve()
        target = (base / name).resolve()
        if not str(target).startswith(str(base)) or not target.is_file():
            return self._json({"error": "not found"}, 404)
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",
                                                  "application/json"):
            ctype += "; charset=utf-8"
        if target.name == "index.html":
            html = target.read_text(encoding="utf-8")
            for asset in ("app.js", "style.css"):
                f = WEB_DIR / asset
                if f.is_file():
                    v = int(f.stat().st_mtime)
                    html = html.replace("/static/" + asset,
                                        "/static/" + asset + "?v=" + str(v))
            return self._send(200, html.encode("utf-8"), ctype)
        self._send(200, target.read_bytes(), ctype)

    # ------------------------------------------------------------ GET
    def do_GET(self):
        u = urlparse(self.path)
        p = u.path
        qs = parse_qs(u.query)
        if p in ("/", "/index.html"):
            return self._static("index.html")
        if p.startswith("/static/"):
            return self._static(p[len("/static/"):])
        if p == "/api/tools":
            return self._json(self.app.tools_payload())
        if p == "/api/tool":
            return self._json(self.app.tool_payload(qs.get("id", [""])[0]))
        if p == "/api/candidates":
            return self._json(self.app.candidates_payload(
                qs.get("tool", [""])[0], qs.get("param", [""])[0]))
        if p == "/api/history":
            return self._json(self.app.history_payload())
        if p == "/api/settings":
            return self._json(self.app.settings_payload())
        if p.startswith("/api/stream/"):
            return self._stream(p.rsplit("/", 1)[-1])
        self._json({"error": "not found", "path": p}, 404)

    def _stream(self, rid: str):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        run = self.app.runs.get(rid)
        if run is None:
            try:
                self.wfile.write(b'data: {"type":"error","text":"run not found"}\n\n')
                self.wfile.flush()
            except Exception:
                pass
            return
        try:
            while True:
                try:
                    msg = run.q.get(timeout=10)
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                    continue
                if msg is None:
                    break
                payload = json.dumps(msg, ensure_ascii=False)
                self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass

    # ------------------------------------------------------------ POST
    def do_POST(self):
        u = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8", "replace"))
        except Exception:
            body = {}
        p = u.path
        if p == "/api/run":
            tid = str(body.get("tool") or "")
            line = str(body.get("cmdline") or "")
            return self._json(self.app.start_run(tid, line))
        if p == "/api/stdin":
            return self._json(self.app.send_stdin(
                str(body.get("run") or ""), str(body.get("text") or "")))
        if p == "/api/stop":
            return self._json(self.app.stop_run(str(body.get("run") or "")))
        if p == "/api/cd":
            path = str(body.get("path") or "")
            base = str(body.get("cwd") or USER_ROOT)
            tgt = Path(os.path.expanduser(path)) if path else Path.home()
            if not tgt.is_absolute():
                tgt = Path(base) / tgt
            try:
                tgt = tgt.resolve()
            except Exception:
                pass
            if tgt.is_dir():
                return self._json({"ok": True, "cwd": str(tgt)})
            return self._json({"ok": False, "cwd": str(tgt)})
        if p == "/api/pickfolder":
            initial = str(body.get("initial") or "").strip()
            got = _pick_folder(initial)
            return self._json({"ok": bool(got), "path": got})
        if p == "/api/opendir":
            raw = str(body.get("path") or "").strip()
            if not raw:
                return self._json({"ok": False, "error": "空路径"})
            target = Path(os.path.expanduser(raw))
            if not target.is_dir():
                return self._json({"ok": False, "error": "目录不存在: " + str(target)})
            try:
                os.startfile(str(target))
                return self._json({"ok": True, "path": str(target)})
            except Exception as exc:
                return self._json({"ok": False, "error": str(exc)})
        if p == "/api/mkdir":
            raw = str(body.get("path") or "").strip()
            if not raw:
                return self._json({"ok": False, "error": "空路径"})
            try:
                target = Path(os.path.expanduser(raw))
                target.mkdir(parents=True, exist_ok=True)
                return self._json({"ok": True, "path": str(target), "exists": True})
            except Exception as exc:
                return self._json({"ok": False, "error": str(exc)})
        if p == "/api/settool":
            return self._json(self.app.set_tool(
                str(body.get("tool") or ""),
                str(body.get("path") or ""),
                body.get("settings") or {}))
        if p == "/api/discover":
            try:
                depth = int(body.get("depth") or 4)
            except Exception:
                depth = 4
            return self._json(self.app.discover_payload(depth))
        if p == "/api/setpath":
            return self._json(self.app.set_path(
                str(body.get("tool") or ""), str(body.get("path") or "")))
        self._json({"error": "not found"}, 404)


def start_server(registry: Registry = None, port: int = None,
                 host: str = "127.0.0.1"):
    """起服务并返回 (httpd, port)，不阻塞。"""
    reg = registry or Registry().load()
    Handler.app = WebApp(reg)
    start = port or DEFAULT_PORT
    httpd = None
    for p in range(start, start + 30):
        try:
            httpd = ThreadingHTTPServer((host, p), Handler)
            start = p
            break
        except OSError:
            continue
    if httpd is None:
        raise RuntimeError(f"端口 {start}-{start + 29} 全被占用")
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, start


def serve(registry: Registry = None, port: int = None, host: str = "127.0.0.1",
          open_browser: bool = True) -> int:
    try:
        httpd, start = start_server(registry, port, host)
    except RuntimeError as exc:
        print(exc)
        return 1
    url = f"http://{host}:{start}/"
    print(f"web-fast web ui  ->  {url}")
    print("按 Ctrl+C 停止服务")
    if open_browser:
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        httpd.server_close()
    return 0
