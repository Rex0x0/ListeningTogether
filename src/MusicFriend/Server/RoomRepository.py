"""
内存房间仓储；后续可替换为 Redis / PostgreSQL 实现同一接口。
"""

from __future__ import annotations

import time
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
        del room.members[memberId]
        if room.hostMemberId == memberId:
            room.hostMemberId = None
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
        track = TrackState(title="", artUrl=None, platform=platform, updatedAtEpoch=0.0)
        member = Member(
            memberId=memberId,
            displayName=displayName,
            track=track,
            role=MemberRole.member,
            presenceState=PresenceState.online,
            lastSeenEpoch=now,
        )
        room.members[memberId] = member
        return member

    def updateMemberTrack(
        self,
        roomId: str,
        memberId: str,
        title: str,
        artUrl: Optional[str],
        platform: str,
    ) -> None:
        room = self._rooms.get(roomId)
        if not room or memberId not in room.members:
            return
        now = time.time()
        m = room.members[memberId]
        m.track.title = title
        m.track.artUrl = artUrl
        m.track.platform = platform
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
