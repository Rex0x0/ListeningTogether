"""
桌面客户端唯一正式发布入口（PySide6，Win / macOS 共用）。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# 与 PyInstaller 打包后的工作目录兼容：优先将源码根加入路径
_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# 规避部分环境下系统代理导致 requests/websocket 超时
os.environ["HTTP_PROXY"] = ""
os.environ["HTTPS_PROXY"] = ""
os.environ["http_proxy"] = ""
os.environ["https_proxy"] = ""

from PySide6.QtCore import Qt, QThread, QTimer, Slot  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox  # noqa: E402

from MusicFriend.Desktop.RoomMainWindow import (  # noqa: E402
    RoomMainWindow,
    SettingsDialog,
    SongDetectorWorker,
)
from MusicFriend.Desktop.RoomWebSocketWorker import RoomWebSocketWorker  # noqa: E402
from MusicFriend.Integrations.FollowPlaybackController import FollowPlaybackController  # noqa: E402


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyleSheet(
        "QWidget { background-color: #2c2f33; color: #ffffff; } QLabel { background-color: transparent; }"
    )
    dlg = SettingsDialog()
    default_srv = os.environ.get("MF_SERVER_URL", "http://127.0.0.1:8765")
    dlg.server_input.setText(default_srv)
    if dlg.exec() != QDialog.Accepted:
        sys.exit(0)

    room_id = (getattr(dlg, "room_id", None) or "").strip() or "0000"
    http_base = dlg.server_url.rstrip("/")

    # WebSocket 须在独立 Python 线程里 run_forever；QObject 留在主线程以便定时器与歌曲检测的槽能执行
    ws_worker = RoomWebSocketWorker(http_base, room_id, dlg.username, dlg.platform)
    follow_ctrl = FollowPlaybackController(dlg.platform)

    main_win = RoomMainWindow(
        dlg.username,
        dlg.platform,
        http_base,
        room_id,
        on_send_chat=ws_worker.sendChatMessage,
        on_request_play_seat=ws_worker.sendPlaySeatRequest,
        on_approve_play_seat=ws_worker.sendPlaySeatApprove,
        on_reject_play_seat=ws_worker.sendPlaySeatReject,
        on_follow_play=follow_ctrl.play,
    )
    ws_worker.snapshotReceived.connect(main_win.on_snapshot, Qt.QueuedConnection)
    ws_worker.eventReceived.connect(main_win.on_event, Qt.QueuedConnection)
    ws_worker.memberIdAssigned.connect(main_win.set_self_member_id, Qt.QueuedConnection)

    @Slot(str)
    def on_ws_err(msg: str) -> None:
        QMessageBox.warning(main_win, "连接异常", msg)

    ws_worker.connectionFailed.connect(on_ws_err, Qt.QueuedConnection)

    ping_ms = int(float(os.environ.get("MF_PING_INTERVAL_SEC", "15")) * 1000)
    ping_timer = QTimer(main_win)
    ping_timer.setInterval(max(ping_ms, 3000))
    ping_timer.timeout.connect(ws_worker.sendPing, Qt.QueuedConnection)

    det_thread = QThread()
    detector = SongDetectorWorker(dlg.platform)
    detector.moveToThread(det_thread)
    det_thread.started.connect(detector.run)
    detector.song_detected.connect(ws_worker.sendTrackFromDetector, Qt.QueuedConnection)

    det_thread.start()
    ping_timer.start()
    QTimer.singleShot(0, ws_worker.connectAndRun)
    main_win.show()

    def on_about_to_quit() -> None:
        ping_timer.stop()
        detector.stop()
        det_thread.quit()
        # 检测循环为短睡眠，一般很快结束；略放宽避免退出阶段仍报 QThread 析构警告
        det_thread.wait(8000)
        ws_worker.closeConnection()

    app.aboutToQuit.connect(on_about_to_quit)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
