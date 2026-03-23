"""
将房间 WebSocket 快照转换为内嵌网页可渲染的结构；座位分配与 Qt 主窗口策略一致（按成员 id 粘性占座）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class WebRoomStateBuilder:
    """在多次快照之间记住「成员 → 座位」绑定，减少 UI 跳动。"""

    def __init__(self, num_seats: int = 12) -> None:
        self._num = num_seats
        self._seat_to_member: List[Optional[str]] = [None] * num_seats

    def build(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        members = payload.get("members") or []
        host_raw = payload.get("hostMemberId")
        play_raw = payload.get("playSeatMemberId")
        host_id = str(host_raw) if host_raw else None
        play_id = str(play_raw) if play_raw else None
        room_id = str(payload.get("roomId") or "")

        by_id: Dict[str, Dict[str, Any]] = {}
        for m in members:
            mid = m.get("memberId")
            if mid:
                by_id[str(mid)] = m

        intended: List[Optional[str]] = [None] * self._num
        for i in range(self._num):
            prev = self._seat_to_member[i] if i < len(self._seat_to_member) else None
            if prev and prev in by_id:
                intended[i] = prev

        assigned = {x for x in intended if x}
        remaining = sorted(mid for mid in by_id.keys() if mid not in assigned)

        ri = 0
        for mid in remaining:
            while ri < self._num and intended[ri] is not None:
                ri += 1
            if ri < self._num:
                intended[ri] = mid
                ri += 1

        self._seat_to_member = list(intended)

        seats_out: List[Dict[str, Any]] = []
        for i, mid in enumerate(intended):
            if mid and mid in by_id:
                m = by_id[mid]
                track = m.get("track") or {}
                seats_out.append(
                    {
                        "index": i,
                        "memberId": mid,
                        "displayName": (m.get("displayName") or mid).strip(),
                        "song": track.get("title") or "",
                        "platform": track.get("platform") or "unknown",
                        "artUrl": track.get("artUrl"),
                        "isHost": bool(host_id and host_id == mid),
                    }
                )
            else:
                seats_out.append({"index": i, "empty": True})

        play_seat: Optional[Dict[str, Any]] = None
        if play_id and play_id in by_id:
            m = by_id[play_id]
            track = m.get("track") or {}
            ex = track.get("externalId")
            play_seat = {
                "memberId": play_id,
                "displayName": (m.get("displayName") or play_id).strip(),
                "song": track.get("title") or "",
                "platform": track.get("platform") or "unknown",
                "artUrl": track.get("artUrl"),
                "isHost": bool(host_id and host_id == play_id),
                "externalId": str(ex).strip() if ex else None,
            }

        return {
            "roomId": room_id,
            "hostMemberId": host_id,
            "playSeatMemberId": play_id,
            "seats": seats_out,
            "playSeat": play_seat,
        }
