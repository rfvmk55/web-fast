"""Web 后端测试：静态页、工具 API、候选 API、执行 + SSE。"""
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from webfast.registry import Registry
from webfast.server import Handler, WebApp

PORT = 8801
BASE = f"http://127.0.0.1:{PORT}"


def get(path, timeout=10):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return r.status, r.read()


def get_json(path):
    st, body = get(path)
    return st, json.loads(body.decode("utf-8"))


def post(path, obj, timeout=15):
    data = json.dumps(obj).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def read_stream(rid, limit=40.0, on_first=None):
    lines, code = [], None
    t0 = time.time()
    with urllib.request.urlopen(f"{BASE}/api/stream/{rid}", timeout=30) as resp:
        ctype = resp.headers.get("Content-Type", "")
        while time.time() - t0 < limit:
            raw = resp.readline()
            if not raw:
                break
            txt = raw.decode("utf-8").strip()
            if not txt.startswith("data: "):
                continue
            m = json.loads(txt[6:])
            if m["type"] == "line":
                lines.append(m["text"])
                if on_first and len(lines) == 1:
                    on_first(rid)
            elif m["type"] == "exit":
                code = m["code"]
                break
    return lines, code, ctype


def main() -> int:
    reg = Registry().load()
    Handler.app = WebApp(reg)
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    time.sleep(0.4)

    try:
        st, body = get("/")
        html = body.decode("utf-8")
        print("[1] GET / ->", st, len(body), "bytes, 含 app.js:", "app.js" in html)
        assert st == 200 and "app.js" in html

        st, js = get("/static/app.js")
        print("    app.js ->", st, len(js), "bytes")
        assert st == 200 and len(js) > 5000

        st, css = get("/static/style.css")
        print("    style.css ->", st, len(css), "bytes")
        assert st == 200

        st, d = get_json("/api/tools")
        print("[2] /api/tools ->", st, "共", d["total"], "就绪", d["ready"])
        assert d["total"] >= 3
        print("    工具:", [t["id"] for t in d["tools"]])

        st, t = get_json("/api/tool?id=sqlmap")
        print("[3] /api/tool sqlmap -> 参数", len(t["params"]), "个, cwd:", t["cwd"])
        assert t["cwd"].endswith("sqlmap-dev")
        names = [p["name"] for p in t["params"]]
        assert "-r" in names and "-u" in names

        st, c = get_json("/api/candidates?tool=sqlmap&param=-r")
        print("[4] -r 候选:", [x["label"] for x in c["items"]])
        assert len(c["items"]) >= 2
        st, c2 = get_json("/api/candidates?tool=sqlmap&param=--tamper")
        print("    --tamper 候选数:", len(c2["items"]), "首项:", c2["items"][0]["value"])
        assert len(c2["items"]) > 50 and not c2["items"][0]["value"].endswith(".py")

        cmd = ('python -c "import os,sys;print(\'CWD\', os.getcwd());'
               'print(\'中文输出正常\');sys.exit(0)"')
        st, r = post("/api/run", {"tool": "sqlmap", "cmdline": cmd})
        print("[5] /api/run ->", st, "run:", r.get("run"), "cwd:", r.get("cwd"))
        rid = r["run"]
        lines, code, ctype = read_stream(rid)
        print("    Content-Type:", ctype)
        print("    输出:", lines)
        print("    退出码:", code)
        assert "text/event-stream" in ctype
        assert any("sqlmap-dev" in x for x in lines), "cwd 不对"
        assert any("中文输出正常" in x for x in lines), "中文乱码"
        assert code == 0

        st, d = post("/api/cd", {"path": "..", "cwd": "C:/Users/25713/sqlmap-dev"})
        print("[6] /api/cd .. ->", d["ok"], d["cwd"])
        assert d["ok"]

        try:
            get("/api/nope")
            print("[7] 404 没触发")
            ok = False
        except urllib.error.HTTPError as e:
            print("[7] 未知接口 ->", e.code)
            ok = e.code == 404
        assert ok

        st, h = get_json("/api/history")
        print("[8] /api/history ->", len(h["rows"]), "条")

        print("")
        print("Web 后端全部通过")
        return 0
    finally:
        httpd.shutdown()


if __name__ == "__main__":
    sys.exit(main())
