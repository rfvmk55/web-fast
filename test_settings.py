"""路径设置测试：settings / discover / setpath / 环境变量 / 相对路径。"""
import json
import os
import sys
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from webfast.registry import (APP_ROOT, LOCAL_PATHS_FILE, Registry,
                              load_local_paths, save_local_paths)
from webfast.server import Handler, WebApp

PORT = 8807
BASE = f"http://127.0.0.1:{PORT}"


def get_json(path):
    with urllib.request.urlopen(BASE + path, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def post(path, obj, timeout=60):
    data = json.dumps(obj).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> int:
    backup = LOCAL_PATHS_FILE.read_text(encoding="utf-8") if LOCAL_PATHS_FILE.exists() else None

    reg = Registry().load()
    Handler.app = WebApp(reg)
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    time.sleep(0.4)

    try:
        # 1 settings 接口
        d = get_json("/api/settings")
        print("[1] /api/settings")
        print("    app_root:", d["app_root"])
        print("    tools_root:", d["tools_root"])
        print("    工具数:", len(d["tools"]))
        assert len(d["tools"]) >= 3
        for t in d["tools"][:3]:
            print(f"    {t['id']:<10} {t['ready']}  env={t['env']}")
            assert t["env"].startswith("WEBFAST_")

        # 2 setpath 改路径
        print("[2] 改 sqlmap 路径")
        alt = Path(os.environ.get("USERPROFILE", "C:/Users/user")) / "sqlmap-gui-main"
        if alt.is_dir():
            r = post("/api/setpath", {"tool": "sqlmap", "path": str(alt)})
            print("    ->", r)
            assert r["ok"] and r["ready"]
            reg2 = Registry().load()
            assert str(reg2.get("sqlmap").cwd_path).lower().endswith("sqlmap-gui-main")
            print("    -> 通过")
        else:
            print("    跳过（备用目录不存在）")

        # 3 清空路径恢复默认
        print("[3] 清空路径")
        r = post("/api/setpath", {"tool": "sqlmap", "path": ""})
        print("    ->", r)
        assert r["ok"] and r.get("cleared")
        reg3 = Registry().load()
        print("    恢复后:", reg3.get("sqlmap").cwd_path)
        print("    -> 通过")

        # 4 环境变量覆盖
        print("[4] 环境变量 WEBFAST_SQLMAP")
        target = str(Path(os.environ.get("USERPROFILE", "C:/Users/user")) / "sqlmap-dev")
        os.environ["WEBFAST_SQLMAP"] = target
        reg4 = Registry().load()
        t4 = reg4.get("sqlmap")
        print("    cwd:", t4.cwd_path)
        assert str(t4.cwd_path).lower() == str(Path(target)).lower()
        del os.environ["WEBFAST_SQLMAP"]
        print("    -> 通过")

        # 5 项目内工具存相对路径
        print("[5] 相对路径存储")
        rel_dir = APP_ROOT / "third_party" / "_rtest"
        rel_dir.mkdir(parents=True, exist_ok=True)
        (rel_dir / "tool.py").write_text("print('hi')", encoding="utf-8")
        save_local_paths({"sqlmap": str(rel_dir)})
        txt = LOCAL_PATHS_FILE.read_text(encoding="utf-8")
        print("    写入内容含相对路径:", "third_party/_rtest" in txt)
        assert "third_party/_rtest" in txt
        reg5 = Registry().load()
        print("    解析回:", reg5.get("sqlmap").cwd_path)
        assert reg5.get("sqlmap").cwd_path == rel_dir.resolve()
        print("    -> 通过")

        # 6 discover 接口
        print("[6] /api/discover（较慢）")
        t0 = time.time()
        d = post("/api/discover", {"depth": 3}, timeout=120)
        print(f"    耗时 {time.time()-t0:.1f}s, 找到:", [(x["tool"], x["path"]) for x in d["found"]])
        assert isinstance(d["found"], list)

        print("")
        print("路径设置全部通过")
        return 0
    finally:
        httpd.shutdown()
        if backup is not None:
            LOCAL_PATHS_FILE.write_text(backup, encoding="utf-8")
        else:
            LOCAL_PATHS_FILE.unlink(missing_ok=True)
        import shutil
        shutil.rmtree(APP_ROOT / "third_party" / "_rtest", ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
