"""以“独立应用窗口”打开前端。

前提：后端与前端已启动（python start.py）。此脚本只是把已经跑起来的
http://localhost:5173 用 Edge/Chrome 的 --app 模式弹成独立窗口，
找不到浏览器时退回系统默认浏览器的普通标签页。
"""

from __future__ import annotations

import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from start import open_app_window  # noqa: E402


def _port_up(port: int) -> bool:
    s = socket.socket()
    s.settimeout(0.4)
    try:
        s.connect(("127.0.0.1", port))
        return True
    except Exception:
        return False
    finally:
        s.close()


def main() -> None:
    if not (_port_up(5173) and _port_up(8000)):
        print("后端 / 前端似乎尚未启动，请先运行: python start.py")
        return
    ok = open_app_window("http://localhost:5173")
    if ok:
        print("已用独立应用窗口打开前端（Edge/Chrome）。")
    else:
        print("未找到 Edge/Chrome，已用默认浏览器打开（普通标签页）。")


if __name__ == "__main__":
    main()
