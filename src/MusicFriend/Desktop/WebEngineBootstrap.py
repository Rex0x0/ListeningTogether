"""
在首次导入 QWebEngine 之前配置 Chromium 环境变量。

Windows 部分显卡/系统版本下，Chromium 会尝试使用较新的 DirectComposition 接口，
若驱动或系统不支持 IDCompositionDevice4，会在控制台打印 ERROR（多为非致命，但干扰排错）。
通过默认追加 Chromium 参数可绕开该路径。
"""

from __future__ import annotations

import os
import sys


def _tokenize(flags: str) -> list[str]:
    """将 Chromium 参数字符串拆成独立 token（简单按空白切分）。"""
    return [t for t in flags.split() if t]


def _merge_chromium_flag_groups(*groups: str) -> str:
    """合并多段参数，去掉重复 token，保持先后顺序。"""
    seen: set[str] = set()
    out: list[str] = []
    for g in groups:
        for t in _tokenize(g):
            if t not in seen:
                seen.add(t)
                out.append(t)
    return " ".join(out)


def apply_webengine_platform_defaults() -> None:
    """
    按平台写入 QTWEBENGINE_CHROMIUM_FLAGS。

    须在导入 QtWebEngineWidgets / 创建 QWebEngineView 之前调用。
    若需关闭本行为：设置环境变量 MF_WEBENGINE_SKIP_WIN_FLAGS=1。
    若需追加参数：设置 MF_WEBENGINE_CHROMIUM_EXTRA（会与现有标志合并）。
    """
    if sys.platform != "win32":
        return

    skip = os.environ.get("MF_WEBENGINE_SKIP_WIN_FLAGS", "").strip().lower()
    if skip in ("1", "true", "yes", "on"):
        return

    # 关闭 GPU 合成层，通常不再走易出错的 DirectComposition 路径（略增 CPU，界面一般仍流畅）
    # 若仍有报错，可在环境变量 MF_WEBENGINE_CHROMIUM_EXTRA 中追加 --disable-gpu
    default_win = "--disable-gpu-compositing"
    merged = _merge_chromium_flag_groups(
        os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", ""),
        default_win,
        os.environ.get("MF_WEBENGINE_CHROMIUM_EXTRA", ""),
    )
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = merged
