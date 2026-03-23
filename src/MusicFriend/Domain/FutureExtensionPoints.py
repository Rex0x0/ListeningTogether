"""
领域层扩展点占位（首迭代不接线）。

- 聊天：消息分页、持久化由独立仓储承担，避免塞进房间聚合事务。
- 房主：`Room.hostMemberId` 与 `Member.role` 已预留字段。
- 播放位：审批流建议以 `PlaySeatRequest` 实体 + 事件驱动实现（见 `RoomEventType`）。
- 音频转发：控制面与房间状态解耦，仅通过事件同步「谁推流、谁订阅」。
"""

from __future__ import annotations

from typing import Any, List, Protocol


class ChatRepositoryProtocol(Protocol):
    """预留：房间聊天消息仓储。"""

    def appendMessage(self, roomId: str, memberId: str, text: str) -> str: ...

    def listRecent(self, roomId: str, limit: int) -> List[dict[str, Any]]: ...


class PlaySeatArbiterProtocol(Protocol):
    """预留：播放位申请与审批。"""

    def requestSeat(self, roomId: str, memberId: str) -> str: ...

    def approve(self, roomId: str, requestId: str, hostMemberId: str) -> None: ...


class AudioControlPlaneProtocol(Protocol):
    """预留：音频流 / WebRTC 信令控制面（与房间状态服务解耦）。"""

    def notifyStreamStarted(self, roomId: str, publisherMemberId: str, streamId: str) -> None: ...

    def notifyStreamStopped(self, roomId: str, streamId: str) -> None: ...
