"""自动发现本机已安装的安全工具，结果写进 local_paths.toml。"""
from __future__ import annotations

import os
from pathlib import Path

# 工具 id -> 该工具目录下可能的入口文件名
CANDIDATE_ENTRIES = {
    "sqlmap": ["sqlmap.py"],
    "commix": ["commix.py"],
    "dirsearch": ["dirsearch.py", os.path.join("dirsearch", "dirsearch.py")],
    "nuclei": ["nuclei.exe", "nuclei"],
    "ffuf": ["ffuf.exe", "ffuf"],
    "gobuster": ["gobuster.exe", "gobuster"],
    "feroxbuster": ["feroxbuster.exe", "feroxbuster"],
    "whatweb": ["whatweb"],
    "wpscan": ["wpscan"],
    "nikto": ["nikto.pl", "nikto"],
    "wafw00f": ["wafw00f.py", "wafw00f"],
    "arjun": ["arjun.py", "arjun"],
    "xray": ["xray_windows_amd64.exe", "xray.exe", "xray"],
    "subfinder": ["subfinder.exe", "subfinder"],
    "httpx": ["httpx.exe", "httpx"],
    "naabu": ["naabu.exe", "naabu"],
    "katana": ["katana.exe", "katana"],
    "fscan": ["fscan.exe", "fscan64.exe", "fscan"],
}

SKIP_DIRS = {
    "appdata", "node_modules", ".git", "__pycache__", ".cache", "temp", "tmp",
    "windows", "program files", "program files (x86)", "programdata",
    "$recycle.bin", "system volume information", "site-packages", "dist-packages",
    "anaconda3", "miniconda3", "pkgs", "logs", "cache", ".vscode", ".vscode-shared",
}


def _scan_dir(base: Path, depth: int, max_depth: int, results: dict,
              wanted: set, on_hit=None) -> None:
    if depth > max_depth:
        return
    try:
        entries = list(os.scandir(base))
    except (PermissionError, OSError):
        return
    subdirs = []
    for e in entries:
        try:
            if e.is_dir(follow_symlinks=False):
                low = e.name.lower()
                if low in SKIP_DIRS:
                    continue
                if low.startswith(".") and low not in (".",):
                    continue
                subdirs.append(e.path)
            elif e.is_file(follow_symlinks=False):
                low = e.name.lower()
                for tid in list(wanted):
                    if low in [c.lower() for c in CANDIDATE_ENTRIES[tid]]:
                        d = Path(base)
                        if tid not in results:
                            results[tid] = d
                            if on_hit:
                                on_hit(tid, d)
                            wanted.discard(tid)
        except OSError:
            continue
    for sd in subdirs:
        if not wanted:
            break
        _scan_dir(Path(sd), depth + 1, max_depth, results, wanted, on_hit)


def default_roots() -> list:
    home = Path(os.path.expanduser("~"))
    roots = [home, home / "Desktop", home / "Downloads", home / "Documents"]
    for drive in "CDEFG":
        p = Path(f"{drive}:/")
        if p.is_dir() and str(p) not in [str(r) for r in roots]:
            roots.append(p)
    seen, out = set(), []
    for r in roots:
        key = str(r).lower()
        if key not in seen and r.is_dir():
            seen.add(key)
            out.append(r)
    return out


def discover(roots=None, max_depth: int = 5, wanted=None, on_hit=None) -> dict:
    """返回 {tool_id: Path}。"""
    wanted = set(wanted or CANDIDATE_ENTRIES.keys())
    results = {}
    for r in (roots or default_roots()):
        if not wanted:
            break
        _scan_dir(Path(r), 0, max_depth, results, wanted, on_hit)
    return results
