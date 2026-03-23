from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from MusicFriend.Domain.Enums import MemberRole, PresenceState


@dataclass
class TrackState:
    """当前曲目展示状态（统一输出给 UI）。"""

    title: str = ""
    artUrl: Optional[str] = None
    platform: str = "unknown"
    updatedAtEpoch: float = 0.0


@dataclass
class Member:
    """房间成员（含未来房主 / 播放位等扩展字段）。"""

    memberId: str
    displayName: str
    track: TrackState
    role: MemberRole = MemberRole.member
    presenceState: PresenceState = PresenceState.online
    # 预留：座位与播放位解耦
    seatId: Optional[str] = None
    playSeatId: Optional[str] = None
    lastSeenEpoch: float = 0.0


@dataclass
class Room:
    """房间聚合根。"""

    roomId: str
    members: Dict[str, Member] = field(default_factory=dict)
    # 预留：房主（首迭代可为 None）
    hostMemberId: Optional[str] = None


@dataclass
class RoomSnapshot:
    """客户端可渲染的快照。"""

    roomId: str
    members: List[Member]
    hostMemberId: Optional[str] = None


@dataclass
class RoomEvent:
    """领域层事件（服务端广播前的语义对象）。"""

    type: str
    roomId: str
    memberId: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)
