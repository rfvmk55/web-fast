"""运行历史：每次执行追加一行 JSON 到 output/history.jsonl。"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .registry import OUTPUT_DIR

HISTORY_FILE = OUTPUT_DIR / "history.jsonl"


def append(tool_id: str, argv: list, cwd: str, code) -> None:
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        row = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "tool": tool_id,
            "cmd": " ".join(str(a) for a in argv),
            "cwd": str(cwd),
            "code": code,
        }
        with HISTORY_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass


def read_history(limit: int = 20) -> list:
    if not HISTORY_FILE.exists():
        return []
    rows = []
    try:
        for line in HISTORY_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    except Exception:
        return []
    return rows[-limit:][::-1]
