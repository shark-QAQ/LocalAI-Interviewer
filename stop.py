"""清理 LocalAI 面试官残留的服务进程。

适用场景：一键启动（python start.py）之后按 Ctrl+C 停不掉 / 端口被占用 /
终端“卡住”无法回到命令提示符——另开一个终端运行本脚本即可。

会结束：uvicorn(app.main:app :8000)、vite(:5173)、以及残留的 start.py。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from start import stop_leftovers  # noqa: E402


def main() -> None:
    print("正在清理 LocalAI 面试官残留服务进程...")
    n = stop_leftovers(include_launcher=True)
    if n:
        print(f"已结束 {n} 个残留进程。现在可以重新运行 python start.py。")
    else:
        print("未发现残留进程（若仍感觉终端卡住，请直接关闭该终端窗口）。")


if __name__ == "__main__":
    main()
