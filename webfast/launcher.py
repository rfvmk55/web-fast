"""执行引擎：拼命令、设 cwd、流式输出、停止进程。"""
from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
import threading
from pathlib import Path

from .registry import Tool, expand_vars

CREATE_NEW_PROCESS_GROUP = 0x00000200


def split_cmd(line: str) -> list:
    """按空格切分命令行，保留引号内的空格。"""
    out, buf, quote = [], [], None
    for ch in line:
        if quote:
            if ch == quote:
                quote = None
            else:
                buf.append(ch)
        elif ch in ("\"", "'"):
            quote = ch
        elif ch.isspace():
            if buf:
                out.append("".join(buf))
                buf = []
        else:
            buf.append(ch)
    if buf:
        out.append("".join(buf))
    return out


def _has(value) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, (list, tuple)):
        return len(value) > 0
    return True


def _fmt(item) -> str:
    if isinstance(item, bool):
        return "true" if item else "false"
    return str(item)


def split_multi(value) -> list:
    """多值输入：列表原样；字符串按换行/逗号切。"""
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    if value is None:
        return []
    s = str(value)
    parts = []
    for chunk in s.replace("\r", "\n").split("\n"):
        parts.extend(chunk.split(","))
    return [p.strip() for p in parts if p.strip()]


def build_argv(tool: Tool, values: dict) -> list:
    argv = list(tool.base_command())
    positional = []
    for p in tool.params:
        raw = values.get(p.name, p.default)
        if p.type == "positional":
            if _has(raw):
                positional.append(_fmt(raw))
            continue
        if p.type == "bool":
            if bool(raw):
                argv.append(p.name)
            continue
        if not _has(raw):
            continue
        items = split_multi(raw) if p.repeat else [_fmt(raw)]
        sep = p.join if p.join else ("=" if p.name.startswith("--") else " ")
        for item in items:
            if sep == "=":
                argv.append(f"{p.name}={item}")
            else:
                argv.append(p.name)
                argv.append(item)
    argv.extend(positional)
    return argv


def quote_cmd(argv: list) -> str:
    """生成可直接粘贴进 cmd / powershell 的命令行。"""
    out = []
    for a in argv:
        s = str(a)
        if s == "" or any(c in s for c in ' \t"&|<>^()'):
            out.append('"' + s.replace('"', '\\"') + '"')
        else:
            out.append(s)
    return " ".join(out)


def _decode(raw: bytes) -> str:
    for enc in ("utf-8", "cp936", "utf-16-le"):
        try:
            txt = raw.decode(enc)
        except UnicodeDecodeError:
            continue
        if "\ufffd" not in txt:
            return txt
    return raw.decode("utf-8", "replace")


def _similar(a: str, b: str) -> bool:
    """两行是不是同一个进度条的不同帧（只差数字）。"""
    if not a or not b:
        return False
    if a == b:
        return True
    if abs(len(a) - len(b)) > 4:
        return False
    n = min(len(a), len(b))
    diff = sum(1 for x, y in zip(a[:n], b[:n]) if x != y)
    return diff <= max(2, int(n * 0.15))


FRAME_RE = re.compile(
    r"\[\s*[#\s]*\]\s*\d+%\s+\d+/\d+\s+[\d.]+/s\s+job:\d+/\d+\s+errors:\d+"
)
PCT_RE = re.compile(r"(\d+)%\s+(\d+)/(\d+)")


RESULT_SPLIT = re.compile(r"(?=\[\d{2}:\d{2}:\d{2}\]\s)")


def split_progress(text: str):
    """把一行拆成 (进度摘要 or None, 剩下的正文)。"""
    if not text or "job:" not in text or "/s" not in text:
        return None, text
    frames = FRAME_RE.findall(text)
    if not frames:
        return None, text
    rest = FRAME_RE.sub("", text).strip()
    m = PCT_RE.search(frames[-1])
    summary = None
    if m:
        summary = m.group(1) + "%  " + m.group(2) + "/" + m.group(3)
    return summary, rest


def progress_summary(text: str):
    s, rest = split_progress(text)
    if s and not rest:
        return s
    return None


class Runner:
    """后台跑子进程，逐行回调。on_line(text) / on_exit(code)。"""

    def __init__(self, on_line=None, on_exit=None, stdin_pipe=False, on_progress=None):
        self.on_line = on_line or (lambda s, kind="line": None)
        self.on_progress = on_progress or (lambda s: None)
        self.on_exit = on_exit or (lambda c: None)
        self.stdin_pipe = stdin_pipe
        self._proc = None
        self._thread = None
        self._lock = threading.Lock()
        self.argv = []
        self.cwd = ""
        self.exit_code = None

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self, argv: list, cwd) -> None:
        if self.running:
            raise RuntimeError("已有任务在运行")
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"
        env.setdefault("PYTHONWARNINGS", "ignore")
        cwd_s = str(cwd) if cwd and Path(str(cwd)).is_dir() else str(Path.cwd())
        kwargs = dict(cwd=cwd_s, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                      stdin=subprocess.PIPE if self.stdin_pipe else subprocess.DEVNULL,
                      env=env, bufsize=0)
        if os.name == "nt":
            kwargs["creationflags"] = CREATE_NEW_PROCESS_GROUP
        self.argv = list(argv)
        self.cwd = cwd_s
        self.exit_code = None
        self._proc = subprocess.Popen(argv, **kwargs)
        self._thread = threading.Thread(target=self._pump, daemon=True)
        self._thread.start()

    def _pump(self) -> None:
        buf = bytearray()
        proc = self._proc
        try:
            while True:
                chunk = proc.stdout.read(1024)
                if not chunk:
                    break
                buf.extend(chunk)
                # \n 是换行，\r 是进度条回车：两种情况分开告诉上层
                while True:
                    idx = -1
                    for i, b in enumerate(buf):
                        if b in (0x0A, 0x0D):
                            idx = i
                            break
                    if idx < 0:
                        break
                    sep = buf[idx]
                    # \r 落在末尾时不知道后面是不是 \n，等下一批数据
                    if sep == 0x0D and idx == len(buf) - 1:
                        break
                    line = bytes(buf[:idx])
                    text = _decode(line) if line.strip() else ""
                    if sep == 0x0D and buf[idx + 1] == 0x0A:
                        del buf[:idx + 2]
                        # print() 在 Windows 输出 \r\n，进度条最后一帧也长这样，
                        # 靠和上一条进度帧的相似度区分
                        if text and _similar(text, getattr(self, "_last_progress", "")):
                            kind = "progress"
                        else:
                            kind = "line"
                    else:
                        del buf[:idx + 1]
                        kind = "progress" if sep == 0x0D else "line"
                        if kind == "line" and getattr(self, "_last_sep", 0) == 0x0D:
                            kind = "progress"
                    self._last_sep = sep
                    if line.strip():
                        summary, rest = split_progress(text)
                        if summary is not None:
                            self.on_progress(summary)
                        if rest:
                            if summary is None:
                                self.on_line(rest, kind)
                            else:
                                # 进度串后面粘着结果行，拆开逐条发
                                for part in RESULT_SPLIT.split(rest):
                                    part = part.strip()
                                    if part:
                                        self.on_line(part, "line")
            if buf.strip():
                self.on_line(_decode(bytes(buf)), "line")
        except Exception as exc:
            self.on_line(f"[webfast] 读取输出失败: {exc}")
        finally:
            code = proc.wait()
            self.exit_code = code
            self.on_exit(code)

    def send(self, text: str) -> bool:
        """往子进程 stdin 写一行（交互式工具的问询用）。"""
        p = self._proc
        if p is None or p.stdin is None or p.poll() is not None:
            return False
        try:
            p.stdin.write(text.encode("utf-8"))
            p.stdin.flush()
            return True
        except Exception:
            return False

    def stop(self) -> None:
        p = self._proc
        if p is None or p.poll() is not None:
            return
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"],
                           capture_output=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            p.terminate()
        try:
            p.wait(timeout=5)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass
