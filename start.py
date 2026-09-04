from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"

processes: list[subprocess.Popen] = []

# PowerShell 过滤器：命中“本项目”残留进程，避免误杀无关服务。
# 用 CommandLine 关键词圈定：uvicorn(app.main) / vite(:5173) / start.py
_SVC_MATCH = (
    "(($_.CommandLine -match 'uvicorn' -and $_.CommandLine -match 'app.main')"
    " -or ($_.CommandLine -match 'vite' -and $_.CommandLine -match '5173'))"
)
_ALL_MATCH = _SVC_MATCH + " -or ($_.CommandLine -match 'start.py')"


def _kill_by_powershell(match: str) -> None:
    """用 taskkill /T /F 整树结束匹配进程（uvicorn --reload 会残留 worker 子进程，
    terminate() 只杀父进程，子进程会继续占着控制台和 8000/5173 端口，导致“终端停不掉”。）"""
    script = (
        "$ErrorActionPreference='SilentlyContinue';"
        "$ps = Get-CimInstance Win32_Process | Where-Object { " + match + " };"
        "foreach ($p in $ps) { & taskkill /PID $p.ProcessId /T /F 2>$null | Out-Null }"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception:
        pass


def stop_leftovers(include_launcher: bool = False) -> int:
    """结束上次运行残留的服务进程，返回清理到的进程数（尽力而为）。

    include_launcher=False：只清 uvicorn/vite（供本脚本启动前自检，避免误杀自身）。
    include_launcher=True ：连 start.py 也清（供 stop.py 从另一个终端调用）。
    """
    if os.name != "nt":
        return 0
    before = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command",
         "(Get-CimInstance Win32_Process | Where-Object { "
         + (_ALL_MATCH if include_launcher else _SVC_MATCH) + " }).Count"],
        capture_output=True, text=True, timeout=30,
    )
    try:
        count_before = int((before.stdout or "0").strip() or 0)
    except ValueError:
        count_before = 0
    _kill_by_powershell(_ALL_MATCH if include_launcher else _SVC_MATCH)
    return count_before


# 常用浏览器的可执行文件位置（Windows），按优先级探测
_BROWSER_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


def _find_app_browser() -> str | None:
    """找一个能以 --app 独立窗口运行的浏览器（Edge 优先、Chrome 次之）。"""
    for p in _BROWSER_CANDIDATES:
        if Path(p).exists():
            return p
    return None


def open_app_window(url: str) -> bool:
    """以“独立应用窗口”（无地址栏/标签页）打开 url。

    用 Edge/Chrome 的 --app 模式启动；找不到时退回系统默认浏览器。
    返回 True 表示走了应用窗口模式。
    """
    exe = _find_app_browser()
    if exe:
        try:
            subprocess.Popen(
                [exe, f"--app={url}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception:
            pass
    webbrowser.open(url)
    return False


def run_backend() -> None:
    uvicorn = BACKEND_DIR / ".venv" / "Scripts" / "uvicorn.exe"
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP
    p = subprocess.Popen(
        [str(uvicorn), "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"],
        cwd=str(BACKEND_DIR),
        creationflags=flags,
    )
    processes.append(p)
    p.wait()


def run_frontend() -> None:
    vite = FRONTEND_DIR / "node_modules" / ".bin" / "vite.cmd"
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP
    p = subprocess.Popen(
        [str(vite), "--port", "5173"],
        cwd=str(FRONTEND_DIR),
        creationflags=flags,
    )
    processes.append(p)
    p.wait()


def cleanup() -> None:
    if os.name == "nt":
        # 优先整树强杀（含 uvicorn reloader 的 worker 子进程），彻底释放控制台与端口
        stop_leftovers(include_launcher=False)
    for p in processes:
        try:
            p.terminate()
            p.wait(timeout=3)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass


def main() -> None:
    print("=" * 60)
    print("  LocalAI 面试官")
    print("=" * 60)

    # 启动前清理上次残留（避免端口被占 / 旧进程继续输出导致终端看起来“没停”）
    if os.name == "nt":
        leftover = stop_leftovers(include_launcher=False)
        if leftover:
            print(f"[0/2] 已清理上次残留的服务进程 {leftover} 个")

    print("\n[1/2] 启动后端 (FastAPI :8000)...")
    t1 = threading.Thread(target=run_backend, daemon=True)
    t1.start()

    time.sleep(5)

    print("[2/2] 前端 (Vite :5173)...")
    t2 = threading.Thread(target=run_frontend, daemon=True)
    t2.start()

    time.sleep(3)
    print("\n" + "=" * 60)
    print("  前端: http://localhost:5173")
    print("  后端: http://localhost:8000/docs")
    print("  按 Ctrl+C 停止所有服务")
    print("  （若仍无法停止，请另开终端执行: python stop.py）")
    print("=" * 60)

    # 以“独立应用窗口”打开前端（找不到 Edge/Chrome 时退回默认浏览器标签页）
    if open_app_window("http://localhost:5173"):
        print("\n已用独立应用窗口打开前端。")
    else:
        print("\n未找到 Edge/Chrome，已用默认浏览器打开（普通标签页）。")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n正在停止服务...")
        cleanup()
        print("已停止。")
        sys.exit(0)


if __name__ == "__main__":
    main()
