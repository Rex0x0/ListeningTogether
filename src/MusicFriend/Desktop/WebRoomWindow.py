"""
桌面正式入口使用的网页主窗口：QWebEngineView + QWebChannel。
"""

from __future__ import annotations

import json
from typing import Optional

from PySide6.QtCore import QUrl
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QMainWindow

from MusicFriend.Desktop.WebShellBridge import WebShellBridge

# 与 desktop_app / 设计稿协调的窗口尺寸
DEFAULT_WINDOW_WIDTH = 1440
DEFAULT_WINDOW_HEIGHT = 900
MIN_WINDOW_WIDTH = 1100
MIN_WINDOW_HEIGHT = 640


class WebRoomWindow(QMainWindow):
    def __init__(
        self,
        *,
        start_url: str,
        bridge: WebShellBridge,
        room_id: str,
        display_name: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Music Together — 共听房间")
        self.setGeometry(80, 60, DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)
        self.setMinimumSize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)

        self._room_id = room_id
        self._display_name = display_name
        self._bridge = bridge

        self._browser = QWebEngineView(self)
        self.setCentralWidget(self._browser)

        channel = QWebChannel(self)
        channel.registerObject("qt_bridge", bridge)
        self._browser.page().setWebChannel(channel)

        self._browser.loadFinished.connect(self._on_load_finished)
        self._browser.setUrl(QUrl(start_url))

    def _on_load_finished(self, ok: bool) -> None:
        if not ok:
            return
        # 桌面嵌入：隐藏浏览器专用登录层，写入昵称与房间（启动不再经过向导）
        self.apply_session_labels(self._room_id, self._display_name)
        self._browser.page().runJavaScript(
            """
            (function() {
                if (window.setConnectionStatus) window.setConnectionStatus('正在连接房间服务…');
            })();
            """
        )

    def apply_session_labels(self, room_id: str, display_name: str) -> None:
        """切房或改名后同步网页标题与全局变量（供聊天去重、右侧栏展示）。"""
        self._room_id = room_id
        self._display_name = display_name
        rid = json.dumps(self._room_id, ensure_ascii=False)
        name = json.dumps(self._display_name, ensure_ascii=False)
        js = f"""
        (function() {{
            window.__mfDesktopEmbed = true;
            window.__mfDisplayName = {name};
            window.__mfRoomId = {rid};
            var overlay = document.getElementById('login-overlay');
            if (overlay) overlay.style.display = 'none';
            var shell = document.getElementById('app-shell');
            if (shell) shell.style.display = '';
            var label = document.getElementById('player-room-label');
            if (label) label.textContent = '房间 ' + {rid};
            if (window.onMfSessionLabelsApplied) window.onMfSessionLabelsApplied();
        }})();
        """
        self._browser.page().runJavaScript(js)

    def browser(self) -> QWebEngineView:
        return self._browser
