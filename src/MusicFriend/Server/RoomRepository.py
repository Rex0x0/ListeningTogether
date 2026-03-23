"""
内存房间仓储；后续可替换为 Redis / PostgreSQL 实现同一接口。
"""

from __future__ import annotations

import time
import uuid
from typing import Dict, Optional

from MusicFriend.Domain.Enums import MemberRole, PresenceState
from MusicFriend.Domain.Models import Member, Room, TrackState


class RoomRepository:
    """单进程内存仓储。"""

    def __init__(self) -> None:
        self._rooms: Dict[str, Room] = {}

    def getOrCreateRoom(self, roomId: str) -> Room:
        if roomId not in self._rooms:
            self._rooms[roomId] = Room(roomId=roomId, members={})
        return self._rooms[roomId]

    def removeMemberIfPresent(self, roomId: str, memberId: str) -> bool:
        room = self._rooms.get(roomId)
        if not room or memberId not in room.members:
            return False
        was_host = room.hostMemberId == memberId
        del room.members[memberId]
        if room.playSeatMemberId == memberId:
            room.playSeatMemberId = None
        # 移除该成员相关的播放位申请
        room.playSeatRequests = {
            rid: mid for rid, mid in room.playSeatRequests.items() if mid != memberId
        }
        if was_host:
            room.hostMemberId = None
            if room.members:
                next_host_id = sorted(room.members.keys())[0]
                room.hostMemberId = next_host_id
                room.members[next_host_id].role = MemberRole.host
        return True

    def upsertMember(
        self,
        roomId: str,
        memberId: str,
        displayName: str,
        platform: str,
    ) -> Member:
        room = self.getOrCreateRoom(roomId)
        now = time.time()
        if memberId in room.members:
            m = room.members[memberId]
            m.displayName = displayName
            m.track.platform = platform
            m.lastSeenEpoch = now
            m.presenceState = PresenceState.online
            return m
        track = TrackState(
            title="",
            artUrl=None,
            platform=platform,
            externalId=None,
            updatedAtEpoch=0.0,
        )
        is_first_in_room = len(room.members) == 0
        member = Member(
            memberId=memberId,
            displayName=displayName,
            track=track,
            role=MemberRole.host if is_first_in_room else MemberRole.member,
            presenceState=PresenceState.online,
            lastSeenEpoch=now,
        )
        room.members[memberId] = member
        if is_first_in_room:
            room.hostMemberId = memberId
        return member

    def updateMemberTrack(
        self,
        roomId: str,
        memberId: str,
        title: str,
        artUrl: Optional[str],
        platform: str,
        external_id: Optional[str],
    ) -> None:
        room = self._rooms.get(roomId)
        if not room or memberId not in room.members:
            return
        now = time.time()
        m = room.members[memberId]
        m.track.title = title
        m.track.artUrl = artUrl
        m.track.platform = platform
        m.track.externalId = (external_id or "").strip() or None
        m.track.updatedAtEpoch = now
        m.lastSeenEpoch = now

    def touchMember(self, roomId: str, memberId: str) -> None:
        room = self._rooms.get(roomId)
        if not room or memberId not in room.members:
            return
        room.members[memberId].lastSeenEpoch = time.time()

    def listStaleMemberIds(self, roomId: str, thresholdSec: float) -> list[str]:
        room = self._rooms.get(roomId)
        if not room:
            return []
        now = time.time()
        return [mid for mid, m in room.members.items() if now - m.lastSeenEpoch > thresholdSec]

    def addPlaySeatRequest(self, roomId: str, applicantMemberId: str) -> Optional[str]:
        """为申请人登记一条播放位申请，返回 requestId；房间或成员不存在则返回 None。"""
        room = self._rooms.get(roomId)
        if not room or applicantMemberId not in room.members:
            return None
        # 同一申请人只保留最新一条，避免房主界面刷屏
        room.playSeatRequests = {
            rid: mid for rid, mid in room.playSeatRequests.items() if mid != applicantMemberId
        }
        request_id = str(uuid.uuid4())
        room.playSeatRequests[request_id] = applicantMemberId
        return request_id

    def takePlaySeatRequest(self, roomId: str, requestId: str) -> Optional[str]:
        """取出并移除一条申请，返回申请人 memberId。"""
        room = self._rooms.get(roomId)
        if not room:
            return None
        return room.playSeatRequests.pop(requestId, None)

    def setPlaySeatMember(self, roomId: str, occupantMemberId: Optional[str]) -> bool:
        room = self._rooms.get(roomId)
        if not room:
            return False
        if occupantMemberId is not None and occupantMemberId not in room.members:
            return False
        room.playSeatMemberId = occupantMemberId
        return True

    def listRoomsWithMembers(self) -> list[tuple[str, int]]:
        """返回当前仍有成员在线的房间（roomId, 人数），按房间 id 排序。"""
        items = [(rid, len(r.members)) for rid, r in self._rooms.items() if len(r.members) > 0]
        items.sort(key=lambda x: x[0])
        return items
