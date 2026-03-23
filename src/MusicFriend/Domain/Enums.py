from enum import Enum


class RoomEventType(str, Enum):
    """房间事件类型（首迭代仅使用部分，其余为预留扩展）。"""

    memberJoined = "memberJoined"
    memberLeft = "memberLeft"
    trackUpdated = "trackUpdated"
    # 预留：聊天
    chatMessageSent = "chatMessageSent"
    # 预留：房主
    hostAssigned = "hostAssigned"
    # 预留：播放位审批
    playSeatRequested = "playSeatRequested"
    playSeatApproved = "playSeatApproved"
    playSeatRejected = "playSeatRejected"
    # 预留：音频转发控制面
    audioStreamStarted = "audioStreamStarted"
    audioStreamStopped = "audioStreamStopped"


class MemberRole(str, Enum):
    """成员角色（首迭代默认 member）。"""

    member = "member"
    host = "host"


class PresenceState(str, Enum):
    """在线状态（首迭代可仅用 online）。"""

    online = "online"
    away = "away"
    offline = "offline"
