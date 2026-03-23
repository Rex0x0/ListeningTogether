"""
跟播：在本地播放器中打开播放位当前曲目（仅 Spotify / 网易云 Windows，且与本人所选平台一致）。
"""

from __future__ import annotations

import os
import sys
from typing import Optional

from MusicFriend.Integrations.SpotifyProvider import SpotifyProvider


class FollowPlaybackController:
    """按平台执行「跟播」切歌；Spotify 走 Web API，网易云尝试唤起桌面客户端协议。"""

    def __init__(self, platform: str) -> None:
        self._platform = (platform or "").strip().lower()
        self._spotify: Optional[SpotifyProvider] = None

    def _ensure_spotify(self) -> Optional[SpotifyProvider]:
        if self._platform != "spotify":
            return None
        if self._spotify is None:
            sp = SpotifyProvider()
            if sp.initialize():
                self._spotify = sp
            else:
                self._spotify = None
        return self._spotify

    def _open_netease_windows(self, song_id: str) -> bool:
        if sys.platform != "win32":
            return False
        sid = (song_id or "").strip()
        if not sid.isdigit():
            return False
        for uri in (f"orpheus://song/{sid}", f"cloudmusic://song?id={sid}"):
            try:
                os.startfile(uri)  # type: ignore[attr-defined]
                return True
            except OSError:
                continue
        return False

    def play(self, external_id: str) -> tuple[bool, str]:
        """
        尝试在本地对应软件中播放 external_id。
        返回 (是否成功, 给用户看的说明)。
        """
        ext = (external_id or "").strip()
        if not ext:
            return False, "当前曲目缺少可跟播的 ID（请确认播放位正在播放且客户端已上报）。"

        if self._platform == "spotify":
            sp = self._ensure_spotify()
            if not sp:
                return False, "Spotify 未就绪：请检查环境变量与授权缓存（需含「控制播放」权限）。"
            uri = ext if ext.startswith("spotify:") else f"spotify:track:{ext}"
            if sp.playTrackUri(uri):
                return True, ""
            return False, "Spotify 切歌失败：请确认已打开 Spotify 并选择播放设备。"

        if self._platform == "netease":
            if sys.platform != "win32":
                return False, "网易云跟播目前仅支持 Windows 客户端。"
            if self._open_netease_windows(ext):
                return True, ""
            return (
                False,
                "无法唤起网易云客户端：请确认已安装并注册 orpheus:// 或 cloudmusic:// 协议，或手动搜索播放。",
            )

        return False, "当前所选音乐平台不支持跟播。"
