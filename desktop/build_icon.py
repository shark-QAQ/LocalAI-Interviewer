"""生成应用图标（墨 / 面试官 印章风）。

流程：按模板拼 SVG → 用本机 Edge/Chrome 无头渲染出各尺寸 PNG → 打成一个 .ico。
产物（只写 desktop/，不影响 frontend 的原版 favicon）：
  desktop/icon.ico / desktop/icon-256.png     Electron 窗口图标
"""

from __future__ import annotations

import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DESKTOP = ROOT / "desktop"

# 深墨底 + 朱砂印 + “墨”字，配主题用的印章红
SVG_TEMPLATE = """<svg xmlns="http://www.w3.org/2000/svg" width="{S}" height="{S}" viewBox="0 0 {S} {S}">
  <rect width="{S}" height="{S}" fill="#211C17"/>
  <circle cx="{C}" cy="{C}" r="{R1}" fill="#2A241B"/>
  <rect x="{X0}" y="{X0}" width="{SEAL}" height="{SEAL}" rx="{RX}" fill="#C23A2B"/>
  <rect x="{X1}" y="{X1}" width="{IN}" height="{IN}" rx="{RX1}" fill="none" stroke="#E8B05B" stroke-width="{SW}" opacity="0.9"/>
  <text x="{C}" y="{TY}" font-family="'KaiTi','STKaiti','SimSun',serif" font-size="{FS}" fill="#F6EAD7" text-anchor="middle">墨</text>
</svg>
"""


def svg_for(size: int) -> str:
    c = size / 2
    seal = size * 0.68
    x0 = (size - seal) / 2
    r = size * 0.11
    inner = seal * 0.82
    x1 = (size - inner) / 2
    fs = size * 0.30
    ty = c + fs * 0.34
    return SVG_TEMPLATE.format(
        S=size, C=c, R1=size * 0.34, X0=x0, SEAL=seal, RX=r,
        X1=x1, IN=inner, RX1=size * 0.075, SW=size * 0.014,
        TY=ty, FS=fs,
    )


def find_browser() -> Path | None:
    cands = [
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    ]
    return next((p for p in cands if p.exists()), None)


def _kill(pid: int) -> None:
    try:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                       capture_output=True, timeout=15)
    except Exception:
        pass


def render_png(browser: Path, svg_path: Path, png_path: Path, size: int, profile: Path) -> None:
    """启动独立无头 Edge（专用 profile，避免锁到已在运行的 Edge），轮询 PNG 后主动杀进程。"""
    url = svg_path.as_uri()
    cmd = [
        str(browser),
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        f"--user-data-dir={profile}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",
        "--force-device-scale-factor=1",
        f"--window-size={size},{size}",
        f"--screenshot={png_path}",
        url,
    ]
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.time() + 40
        while time.time() < deadline:
            if png_path.exists() and png_path.stat().st_size > 100:
                return
            if p.poll() is not None:
                break
            time.sleep(0.5)
        raise RuntimeError(f"无头截图失败（{size}px），未生成 PNG")
    finally:
        if p.poll() is None:
            _kill(p.pid)


def build_ico(pngs: dict[int, Path], out: Path) -> None:
    images = []
    for size in (256, 64, 48, 32):
        if size not in pngs:
            continue
        raw = pngs[size].read_bytes()
        b = 0 if size == 256 else size
        images.append((b, len(raw), raw))
    with open(out, "wb") as f:
        f.write(struct.pack("<HHH", 0, 1, len(images)))
        offset = 6 + 16 * len(images)
        for b, ln, raw in images:
            f.write(struct.pack("<BBBBHHII", b, b, 0, 0, 1, 32, ln, offset))
            offset += ln
        for _, _, raw in images:
            f.write(raw)


def main() -> None:
    browser = find_browser()
    if browser is None:
        print("未找到 Edge/Chrome，无法无头渲染图标。")
        sys.exit(1)

    DESKTOP.mkdir(exist_ok=True)

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        pngs: dict[int, Path] = {}
        for size in (256, 64, 48, 32):
            profile = tmp / f"edge-profile-{size}"
            profile.mkdir()
            svg_path = tmp / f"icon-{size}.svg"
            svg_path.write_text(svg_for(size), encoding="utf-8")
            png_path = tmp / f"icon-{size}.png"
            render_png(browser, svg_path, png_path, size, profile)
            pngs[size] = png_path

        build_ico(pngs, DESKTOP / "icon.ico")
        (DESKTOP / "icon-256.png").write_bytes(pngs[256].read_bytes())

    print(f"已生成:\n  {DESKTOP / 'icon.ico'}\n  {DESKTOP / 'icon-256.png'}")


if __name__ == "__main__":
    main()
