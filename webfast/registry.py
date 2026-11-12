"""工具注册表：扫描 tools/*.toml，提供查询、依赖检查与入口解析。"""
from __future__ import annotations

import importlib.util
import os
import shutil
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _bundle_root() -> Path:
    """只读资源目录：源码运行时是项目根，打包后是 PyInstaller 解包目录。"""
    if _is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _user_root() -> Path:
    """可写目录：配置文件、output、third_party 都放 exe 旁边。"""
    if _is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


APP_ROOT = _bundle_root()
USER_ROOT = _user_root()
TOOLS_DIR = APP_ROOT / "tools"
WEB_DIR = APP_ROOT / "web"
PROFILES_DIR = USER_ROOT / "profiles"
OUTPUT_DIR = USER_ROOT / "output"
SETTINGS_FILE = USER_ROOT / "settings.toml"
LOCAL_PATHS_FILE = USER_ROOT / "local_paths.toml"
DEFAULT_TOOLS_ROOT = USER_ROOT / "third_party"

def python_exe() -> str:
    """打包后 sys.executable 是 exe 自己，得另找系统 Python 来跑工具脚本。"""
    if not _is_frozen():
        return sys.executable
    for name in ("python.exe", "python3.exe", "python"):
        found = shutil.which(name)
        if found:
            return found
    py = shutil.which("py.exe") or shutil.which("py")
    if py:
        return py
    return "python"


PARAM_TYPES = {"string", "int", "float", "bool", "choice",
               "path", "dir", "file", "text", "positional"}
RUNNERS = {"python": "python", "binary": "binary", "module": "module"}
GROUP_ORDER = ["注入", "目录扫描", "指纹识别", "漏洞扫描", "子域名", "综合", "其它"]


def expand_vars(value: str) -> str:
    if not isinstance(value, str):
        return value
    return os.path.expanduser(os.path.expandvars(value))


def rebind_user_path(p: Path):
    """C:/Users/oldname/x 在别的机器上不存在时，换成当前用户的同名路径。"""
    try:
        parts = Path(p).parts
    except Exception:
        return None
    for i, part in enumerate(parts):
        if str(part).lower() in ("users", "documents and settings") and i + 1 < len(parts):
            try:
                tail = parts[i + 2:]
                cand = Path(parts[0]).joinpath(*parts[1:i + 1]) / Path.home().name / Path(*tail)
            except Exception:
                return None
            if cand.is_dir():
                return cand
            return None
    return None


def load_local_paths() -> dict:
    """local_paths.toml 里 [paths] 段的工具路径覆盖，本机专属、不随仓库分发。"""
    if not LOCAL_PATHS_FILE.exists():
        return {}
    try:
        with LOCAL_PATHS_FILE.open("rb") as f:
            d = tomllib.load(f)
    except Exception:
        return {}
    paths = d.get("paths", {})
    if not isinstance(paths, dict):
        return {}
    return {str(k).strip().lower(): str(v) for k, v in paths.items()}


def load_local_settings() -> dict:
    """{tool_id: {key: value}}，工具子路径的用户配置。"""
    if not LOCAL_PATHS_FILE.exists():
        return {}
    try:
        with LOCAL_PATHS_FILE.open("rb") as f:
            d = tomllib.load(f)
    except Exception:
        return {}
    raw = d.get("tool_settings", {})
    if not isinstance(raw, dict):
        return {}
    out = {}
    for k, v in raw.items():
        if isinstance(v, dict):
            out[str(k).lower()] = {str(a): str(b) for a, b in v.items()}
    return out


def _portable_path(p) -> str:
    """项目目录下的路径存成相对路径，整个文件夹搬走也不用改。"""
    try:
        path = Path(p).resolve()
    except Exception:
        return str(p)
    try:
        return path.relative_to(APP_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _read_raw() -> dict:
    if not LOCAL_PATHS_FILE.exists():
        return {}
    try:
        with LOCAL_PATHS_FILE.open("rb") as f:
            return tomllib.load(f)
    except Exception:
        return {}


def save_local_config(paths: dict = None, tool_settings: dict = None) -> Path:
    import json
    cur = _read_raw()
    p = dict(cur.get("paths", {})) if paths is None else dict(paths)
    s = dict(cur.get("tool_settings", {})) if tool_settings is None else dict(tool_settings)

    lines = [
        "# web-fast 路径配置（自动生成，可手改）",
        "# [paths]          每个工具的根目录",
        "# [tool_settings]  工具内部的子目录，如 sqlmap 的 txt、dirsearch 的字典",
        "# 想临时覆盖：设环境变量 WEBFAST_<工具名大写>，如 WEBFAST_SQLMAP",
        "",
        "[paths]",
    ]
    for k in sorted(p):
        lines.append(f"{k} = {json.dumps(_portable_path(p[k]), ensure_ascii=False)}")
    if s:
        lines.append("")
        for tid in sorted(s):
            sub = s[tid]
            if not isinstance(sub, dict) or not sub:
                continue
            lines.append(f"[tool_settings.{tid.lower()}]")
            for key in sorted(sub):
                lines.append(f"{key} = {json.dumps(str(sub[key]), ensure_ascii=False)}")
            lines.append("")
    lines.append("")
    LOCAL_PATHS_FILE.write_text(chr(10).join(lines), encoding="utf-8")
    return LOCAL_PATHS_FILE


def save_local_paths(mapping: dict) -> Path:
    return save_local_config(paths=mapping)


def setting_value(tool, key: str, overrides: dict) -> str:
    """工具子路径的最终值：用户配置 > toml 默认（相对工具目录）> 空。"""
    v = (overrides or {}).get(key)
    if v:
        p = Path(expand_vars(str(v)))
        return str(p if p.is_absolute() else (tool.cwd_path / p))
    for s in tool.settings:
        if s.key == key:
            if not s.default:
                return ""
            p = Path(expand_vars(s.default))
            return str(p if p.is_absolute() else (tool.cwd_path / p))
    return ""


def load_settings() -> dict:
    if SETTINGS_FILE.exists():
        try:
            with SETTINGS_FILE.open("rb") as f:
                return tomllib.load(f)
        except Exception:
            return {}
    return {}


def tools_root() -> Path:
    raw = load_settings().get("tools_root")
    if not raw:
        return DEFAULT_TOOLS_ROOT
    p = Path(expand_vars(str(raw)))
    return (p if p.is_absolute() else (APP_ROOT / p)).resolve()


# --------------------------------------------------------------------------- 参数

@dataclass
class Param:
    name: str = ""
    label: str = ""
    help: str = ""
    type: str = "string"
    default: Any = None
    required: bool = False
    choices: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    example: str = ""
    group: str = "通用"
    join: str = ""   # 空 = 自动：--xxx 用 =，-x 用空格
    repeat: bool = False
    placeholder: str = ""
    source: str = ""
    source_noext: bool = False
    source_multi: bool = False
    quote: str = ""   # "" 自动 / "1" 强制加引号 / "0" 不加

    @classmethod
    def from_dict(cls, d: dict) -> "Param":
        t = str(d.get("type", "string")).lower().strip()
        if t not in PARAM_TYPES:
            t = "string"
        return cls(
            name=str(d.get("name", "")).strip(),
            label=str(d.get("label", "")).strip(),
            help=str(d.get("help", "")).strip(),
            type=t,
            default=d.get("default"),
            required=bool(d.get("required", False)),
            choices=[str(x) for x in d.get("choices", [])],
            tags=[str(x) for x in d.get("tags", [])],
            example=str(d.get("example", "")).strip(),
            group=str(d.get("group", "通用")).strip(),
            join=str(d.get("join", "")).strip(),
            repeat=bool(d.get("repeat", False)),
            placeholder=str(d.get("placeholder", "")).strip(),
            source=str(d.get("source", "")).strip(),
            source_noext=bool(d.get("source_noext", False)),
            source_multi=bool(d.get("source_multi", False)),
            quote=str(d.get("quote", "")).strip(),
        )

    @property
    def is_switch(self) -> bool:
        return self.type == "bool"

    def matches(self, query: str) -> bool:
        q = query.lower()
        hay = " ".join([self.name, self.label, self.help, self.example,
                        self.group, " ".join(self.tags)]).lower()
        return q in hay


# --------------------------------------------------------------------------- 预设

@dataclass
class Setting:
    """工具自己的子路径配置，比如 sqlmap 的 txt 目录、dirsearch 的字典目录。"""
    key: str = ""
    label: str = ""
    type: str = "dir"
    default: str = ""
    help: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "Setting":
        return cls(
            key=str(d.get("key", "")).strip(),
            label=str(d.get("label", "")).strip(),
            type=str(d.get("type", "dir")).strip(),
            default=str(d.get("default", "")).strip(),
            help=str(d.get("help", "")).strip(),
        )


@dataclass
class Template:
    name: str = ""
    desc: str = ""
    values: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "Template":
        vals = d.get("values", {})
        return cls(
            name=str(d.get("name", "")).strip(),
            desc=str(d.get("desc", "")).strip(),
            values=dict(vals) if isinstance(vals, dict) else {},
        )


# --------------------------------------------------------------------------- 工具

@dataclass
class Tool:
    id: str = ""
    name: str = ""
    category: str = "其它"
    summary: str = ""
    runner: str = "python"
    entry: str = ""
    cwd: str = ""
    repo: str = ""
    pip: str = ""
    homepage: str = ""
    install: str = ""
    requires: list = field(default_factory=list)
    params: list = field(default_factory=list)
    templates: list = field(default_factory=list)
    settings: list = field(default_factory=list)
    source: str = ""

    # --- 路径解析 ---
    @property
    def env_var(self) -> str:
        return "WEBFAST_" + self.id.upper().replace("-", "_").replace(".", "_")

    @property
    def cwd_path(self) -> Path:
        # 1) 环境变量优先：WEBFAST_SQLMAP=path
        env = os.environ.get(self.env_var)
        if env:
            p = Path(expand_vars(env))
            if p.is_dir():
                return p.resolve()
        # 2) local_paths.toml 或 toml 里写的 cwd
        raw = expand_vars(self.cwd or "")
        if not raw:
            return (tools_root() / self.id).resolve()
        p = Path(raw)
        if p.is_absolute():
            if p.is_dir():
                return p
            alt = rebind_user_path(p)
            return alt if alt is not None else p
        # 3) 相对路径：先按项目根找，再按工具根找
        cand = (APP_ROOT / p)
        if cand.is_dir():
            return cand.resolve()
        return (tools_root() / p).resolve()

    @property
    def entry_resolved(self) -> Path | None:
        raw = expand_vars(self.entry or "")
        if not raw:
            return None
        p = Path(raw)
        if p.is_absolute():
            return p
        cand = self.cwd_path / p
        if cand.exists():
            return cand
        w = shutil.which(raw)
        if w:
            return Path(w)
        return cand

    def which_self(self):
        """工具本体的可执行名（PATH 里可能有，比如 pip 安装的 dirsearch）。"""
        for name in (self.entry or "", self.id, self.id.replace("-", "")):
            if not name:
                continue
            name = Path(expand_vars(name)).name if ("\\" in name or "/" in name) else name
            w = shutil.which(name)
            if w:
                return Path(w)
        return None

    def base_command(self) -> list:
        py = python_exe()
        if self.runner == "python":
            e = self.entry_resolved
            if e is not None and e.exists():
                return [py, str(e)]
            w = self.which_self()
            if w:
                return [str(w)]
            if e is None:
                raise ValueError(f"{self.id}: 未配置 entry")
            return [py, str(e)]
        if self.runner == "module":
            return [py, "-m", self.entry]
        if self.runner == "binary":
            e = self.entry_resolved
            if e is not None and e.exists():
                return [str(e)]
            w = self.which_self()
            if w:
                return [str(w)]
            return [str(e) if e else self.entry]
        raise ValueError(f"{self.id}: 未知 runner {self.runner!r}")

    def missing_modules(self) -> list:
        if _is_frozen():
            # 打包后工具是用系统 Python 跑的，依赖也在系统里，这里不检查
            return []
        out = []
        for m in self.requires:
            base = str(m).split("[")[0].split("=")[0].strip()
            if not base:
                continue
            if importlib.util.find_spec(base) is None:
                out.append(str(m))
        return out

    def availability(self) -> tuple:
        """返回 (是否就绪, 人类可读状态)。"""
        if self.runner == "module":
            base = self.entry.split(".")[0].strip()
            if importlib.util.find_spec(base) is None:
                return False, f"Python 模块 {self.entry} 未安装"
            miss = self.missing_modules()
            if miss:
                return False, "缺依赖: " + ", ".join(miss)
            return True, "就绪"
        e = self.entry_resolved
        if e is None:
            return False, "未配置 entry"
        if not e.exists():
            w = self.which_self()
            if w is not None:
                return True, f"就绪（PATH: {w}）"
            if self.repo and shutil.which("git"):
                return False, f"未下载（webfast fetch {self.id} 或 pip install {self.id}）"
            return False, f"入口不存在: {e}"
        if self.runner == "python":
            miss = self.missing_modules()
            if miss:
                return False, "缺依赖: " + ", ".join(miss)
        return True, "就绪"

    @property
    def ready(self) -> bool:
        return self.availability()[0]

    def param(self, name: str):
        for p in self.params:
            if p.name == name:
                return p
        return None

    @classmethod
    def from_dict(cls, d: dict, source: str = "") -> "Tool":
        runner = str(d.get("runner", "python")).lower().strip()
        if runner not in RUNNERS:
            runner = "python"
        tid = str(d.get("id", "")).strip()
        return cls(
            id=tid,
            name=str(d.get("name", tid)).strip(),
            category=str(d.get("category", "其它")).strip(),
            summary=str(d.get("summary", "")).strip(),
            runner=runner,
            entry=str(d.get("entry", "")).strip(),
            cwd=str(d.get("cwd", "")).strip(),
            repo=str(d.get("repo", "")).strip(),
            pip=str(d.get("pip", "")).strip(),
            homepage=str(d.get("homepage", "")).strip(),
            install=str(d.get("install", "")).strip(),
            requires=[str(x) for x in d.get("requires", [])],
            params=[Param.from_dict(x) for x in d.get("param", [])],
            templates=[Template.from_dict(x) for x in d.get("template", [])],
            settings=[Setting.from_dict(x) for x in d.get("setting", [])],
            source=source,
        )


# --------------------------------------------------------------------------- 注册表

class Registry:
    def __init__(self, tools_dir: Path | None = None):
        self.tools_dir = Path(tools_dir) if tools_dir else TOOLS_DIR
        self._tools: list = []
        self.errors: list = []

    def load(self) -> "Registry":
        self._tools = []
        self.errors = []
        if not self.tools_dir.is_dir():
            return self
        for f in sorted(self.tools_dir.glob("*.toml")):
            try:
                with f.open("rb") as fh:
                    d = tomllib.load(fh)
                t = Tool.from_dict(d, source=str(f))
                if not t.id:
                    t.id = f.stem
                if not t.name:
                    t.name = t.id
                self._tools.append(t)
            except Exception as exc:  # 坏文件不拖垮整体
                self.errors.append(f"{f.name}: {exc}")
        self._apply_local_paths()
        self._tools.sort(key=lambda t: (GROUP_ORDER.index(t.category)
                                        if t.category in GROUP_ORDER else 99,
                                        t.name.lower()))
        return self

    def _apply_local_paths(self) -> None:
        paths = load_local_paths()
        for t in self._tools:
            p = paths.get(t.id.lower())
            if p:
                t.cwd = p

    def all(self) -> list:
        return list(self._tools)

    def get(self, tool_id: str):
        tid = tool_id.lower()
        for t in self._tools:
            if t.id.lower() == tid or t.name.lower() == tid:
                return t
        return None

    def categories(self) -> list:
        seen = []
        for t in self._tools:
            if t.category not in seen:
                seen.append(t.category)
        return seen

    def search(self, query: str) -> list:
        """返回 [(tool, 命中的参数列表)]；query 为空返回全部。"""
        q = (query or "").strip()
        if not q:
            return [(t, []) for t in self._tools]
        out = []
        for t in self._tools:
            hit_p = [p for p in t.params if p.matches(q)]
            head = " ".join([t.id, t.name, t.summary, t.category]).lower()
            if hit_p or q.lower() in head:
                out.append((t, hit_p))
        return out

    def scan_unregistered(self) -> list:
        """third_party 下存在但没有 toml 描述的子目录。"""
        root = tools_root()
        known = {t.id.lower() for t in self._tools}
        known |= {t.cwd_path.name.lower() for t in self._tools}
        if not root.is_dir():
            return []
        return [p for p in sorted(root.iterdir())
                if p.is_dir() and p.name.lower() not in known]
