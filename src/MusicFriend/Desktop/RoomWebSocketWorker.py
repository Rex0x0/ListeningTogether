"""
使用后台线程运行 websocket-client 的 run_forever；发送接口可在任意线程调用（加锁）。
说明：若将 QObject 移到 QThread 后在此线程内阻塞 run_forever，则该线程无法处理 Qt
QueuedConnection 投递的 sendPing / sendTrackFromDetector，服务端约 30 秒会因无保活而断开。
"""

from __future__ import annotations

import json
import os
import threading
from typing import Optional
from urllib.parse import urlparse, urlunparse

from PySide6.QtCore import QObject, Signal, Slot


def _httpBaseToWsBase(http_base: str) -> str:
    u = http_base.strip().rstrip("/")
    parsed = urlparse(u)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunparse((scheme, parsed.netloc, "", "", "", ""))


class RoomWebSocketWorker(QObject):
    """维护与房间服务的长连接。"""

    snapshotReceived = Signal(dict)
    eventReceived = Signal(dict)
    connectionFailed = Signal(str)

    def __init__(self, http_base: str, room_id: str, display_name: str, platform: str) -> None:
        super().__init__()
        self._http_base = http_base
        self._room_id = room_id
        self._display_name = display_name
        self._platform = platform
        self._ws_app: Optional[object] = None
        self._hello_sent = False
        self._ws_lock = threading.Lock()
        self._run_thread: Optional[threading.Thread] = None

    @Slot()
    def connectAndRun(self) -> None:
        import websocket

        ws_base = _httpBaseToWsBase(self._http_base)
        path = f"/ws/room/{self._room_id}"
        url = f"{ws_base}{path}"
        # websocket-client 要求 ping_interval > ping_timeout，二者相等会直接抛错
        ws_ping_interval = float(os.environ.get("MF_WS_PING_INTERVAL_SEC", "0"))
        ws_ping_timeout = float(os.environ.get("MF_WS_PING_TIMEOUT_SEC", "10"))
        if ws_ping_interval > 0 and ws_ping_interval <= ws_ping_timeout:
            ws_ping_interval = ws_ping_timeout + 5.0

        def on_open(ws) -> None:
            with self._ws_lock:
                self._ws_app = ws
            hello = {
                "type": "hello",
                "payload": {"displayName": self._display_name, "platform": self._platform},
            }
            ws.send(json.dumps(hello, ensure_ascii=False))
            self._hello_sent = True

        def on_message(_ws, message: str) -> None:
            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                return
            mtype = data.get("type")
            if mtype == "snapshot":
                self.snapshotReceived.emit(data.get("payload") or {})
            elif mtype == "event":
                self.eventReceived.emit(data.get("payload") or {})

        def on_error(_ws, err) -> None:
            # 服务端正常关闭（如超时踢人）会表现为 opcode=8；避免对 1000 误报「连接异常」
            if err is not None:
                r = repr(err)
                if "opcode=8" in r and (
                    "1000" in r
                    or "\\x03\\xe8" in r
                    or "data=b'\\x03\\xe8'" in r
                    or "data=b\"\\x03\\xe8\"" in r
                ):
                    return
            # 部分错误对象 str() 为空，避免弹出空白提示框
            if err is None:
                msg = "连接失败（无详细说明），请确认房间服务已启动且地址正确"
            else:
                msg = str(err).strip() or repr(err)
            if msg:
                self.connectionFailed.emit(msg)

        def on_close(_ws, _close_status_code, _close_msg) -> None:
            with self._ws_lock:
                self._ws_app = None

        ws_app = websocket.WebSocketApp(
            url,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
        )
        try:
            # 默认关闭 WebSocket 层自动 ping，由 Main 中 JSON ping 保活，避免与服务端帧处理冲突
            kwargs = {}
            if ws_ping_interval > 0:
                kwargs["ping_interval"] = ws_ping_interval
                kwargs["ping_timeout"] = ws_ping_timeout

            def _run() -> None:
                try:
                    ws_app.run_forever(**kwargs)
                except Exception as e:
                    self.connectionFailed.emit(str(e).strip() or repr(e))

            self._run_thread = threading.Thread(target=_run, name="MusicFriendWs", daemon=True)
            self._run_thread.start()
        except Exception as e:
            self.connectionFailed.emit(str(e).strip() or repr(e))

    @Slot(str)
    def sendText(self, text: str) -> None:
        with self._ws_lock:
            app = self._ws_app
        if not app:
            return
        try:
            app.send(text)
        except Exception as e:
            self.connectionFailed.emit(str(e))

    @Slot()
    def sendPing(self) -> None:
        self.sendText(json.dumps({"type": "ping"}))

    @Slot(dict)
    def sendTrackFromDetector(self, data: dict) -> None:
        """由歌曲检测线程经 QueuedConnection 投递；与 run_forever 不同线程，依赖 send 加锁。"""
        title = data.get("title") or ""
        art_url = data.get("artUrl")
        platform = data.get("platform") or "unknown"
        body = {
            "type": "trackUpdate",
            "payload": {"title": title, "artUrl": art_url, "platform": platform},
        }
        self.sendText(json.dumps(body, ensure_ascii=False))

    @Slot()
    def closeConnection(self) -> None:
        with self._ws_lock:
            app = self._ws_app
        if app:
            try:
                app.close()
            except Exception:
                pass
