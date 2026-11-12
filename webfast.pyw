"""双击启动 GUI（无控制台窗口）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from webfast.gui import run_gui  # noqa: E402
from webfast.registry import Registry  # noqa: E402

if __name__ == "__main__":
    run_gui(Registry().load())
