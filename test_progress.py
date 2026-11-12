"""验证 \r 进度条被识别成 progress，\n 是 line。"""
import json
import sys
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from webfast.registry import Registry
from webfast.server import Handler, WebApp

PORT = 8840
BASE = f"http://127.0.0.1:{PORT}"


def post(path, obj):
    data = json.dumps(obj).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


DEMO = Path(__file__).resolve().parent / "_progress_demo.py"


def main() -> int:
    DEMO.write_text(
        "import sys, time\n"
        "for i in range(5):\n"
        "    sys.stdout.write('\\rprogress %d/5  ' % i)\n"
        "    sys.stdout.flush()\n"
        "    time.sleep(0.06)\n"
        "print()\n"
        "print('Task Completed')\n",
        encoding="utf-8")

    reg = Registry().load()
    Handler.app = WebApp(reg)
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    time.sleep(0.4)

    try:
        d = post("/api/run", {"tool": "", "cmdline": "python _progress_demo.py"})
        rid = d["run"]
        kinds = {"progress": [], "line": []}
        code_out = None
        with urllib.request.urlopen(f"{BASE}/api/stream/{rid}", timeout=30) as resp:
            for raw in resp:
                txt = raw.decode("utf-8").strip()
                if not txt.startswith("data: "):
                    continue
                m = json.loads(txt[6:])
                if m.get("type") in kinds:
                    kinds[m["type"]].append(m["text"])
                elif m.get("type") == "exit":
                    code_out = m["code"]
                    break

        print("progress 帧:", len(kinds["progress"]))
        for x in kinds["progress"]:
            print("   ", repr(x))
        print("line 帧:", kinds["line"])
        print("退出码:", code_out)
        assert len(kinds["progress"]) >= 3, "进度条没被识别成 progress"
        assert any("Task Completed" in x for x in kinds["line"]), "普通行丢了"
        print("")
        print("进度条识别通过")
        return 0
    finally:
        httpd.shutdown()
        DEMO.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
