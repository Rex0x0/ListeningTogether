"""
统一「当前播放」输出，供桌面端轮询；UI 不直接依赖第三方 API 结构。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass
class NowPlayingSnapshot:
    """标准化曲目快照。"""

    title: str
    artUrl: Optional[str]
    platform: str


class NowPlayingProvider(Protocol):
    """平台检测器协议。"""

    platformId: str

    def poll(self) -> Optional[NowPlayingSnapshot]:
        """无播放或无法检测时返回 None。"""
