#!/usr/bin/env python
"""web-fast 统一入口。不带参数 = 打开 GUI；带参数 = 命令行模式。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from webfast.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
