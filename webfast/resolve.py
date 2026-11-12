"""参数取值来源解析：glob / dir / list + 历史值 + 工具子路径占位符。"""
from __future__ import annotations

import re
from pathlib import Path

from .registry import setting_value

_PLACEHOLDER = re.compile(r"\$\{(\w+)\}")


def expand_placeholders(src: str, tool, tool_settings: dict = None) -> str:
    """把 source 里的 ${txt_dir} 之类换成工具实际子路径。"""
    if not src or "${" not in src:
        return src

    def repl(m):
        v = setting_value(tool, m.group(1), tool_settings or {})
        return v or ""

    return _PLACEHOLDER.sub(repl, src)


def resolve_source(tool, param, base_dir, tool_settings: dict = None) -> list:
    """返回 [(显示文本, 实际插入值)]。"""
    src = (param.source or "").strip()
    if "${" in src:
        src = expand_placeholders(src, tool, tool_settings)
    base = Path(base_dir)
    items = []
    if src.startswith("list:"):
        for x in src[5:].split("|"):
            x = x.strip()
            if not x:
                continue
            if ":" in x:
                v, lab = x.split(":", 1)
                items.append((lab.strip(), v.strip()))
            else:
                items.append((x, x))
        return items
    if src.startswith("glob:"):
        pat = src[5:].strip()
        pp = Path(pat)
        if not pp.is_absolute():
            pp = base / pp
        parent = pp.parent
        if not parent.is_dir():
            return []
        try:
            files = [f for f in parent.glob(pp.name)
                     if f.is_file() and not f.name.startswith("__")]
        except Exception:
            return []
        files.sort(key=lambda x: x.name.lower())
        for f in files:
            try:
                rel = f.relative_to(base)
            except ValueError:
                rel = f
            shown = Path(str(rel)).as_posix()
            value = Path(shown).stem if param.source_noext else shown
            items.append((shown, value))
        return items
    if src.startswith("dir:"):
        d = Path(src[4:].strip())
        if not d.is_absolute():
            d = base / d
        if not d.is_dir():
            return []
        for f in sorted(d.iterdir()):
            if f.is_file() and not f.name.startswith("__"):
                try:
                    rel = f.relative_to(base)
                except ValueError:
                    rel = f
                v = Path(str(rel)).as_posix()
                items.append((v, v))
        return items
    return items


def candidates(tool, param, base_dir, value_history=None,
               tool_settings: dict = None) -> list:
    """含固定枚举、历史值与浏览项的完整候选。"""
    items = resolve_source(tool, param, base_dir, tool_settings)
    if not items and param.choices:
        items = [(str(c), str(c)) for c in param.choices]
    if not items and param.type in ("string", "text") and value_history:
        items = [(v, v) for v in value_history.get(param.name, [])[-20:]]
    if param.type in ("file", "dir"):
        label = "【浏览目录…】" if param.type == "dir" else "【浏览文件…】"
        items = items + [(label, "__browse__")]
    return items
