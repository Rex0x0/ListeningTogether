import json

from MusicFriend.Contracts.ProtocolModels import (
    HelloPayload,
    RoomSnapshotDto,
    ServerEnvelope,
    ServerEventDto,
)
from MusicFriend.Domain.Enums import RoomEventType


def test_roundtrip_snapshot_envelope() -> None:
    snap = RoomSnapshotDto(
        roomId="default",
        members=[],
        hostMemberId=None,
    )
    env = ServerEnvelope(type="snapshot", payload=snap)
    raw = env.model_dump_json()
    back = json.loads(raw)
    assert back["type"] == "snapshot"
    assert back["payload"]["roomId"] == "default"


def test_server_event_uses_enum_value() -> None:
    from MusicFriend.Contracts.ProtocolModels import RoomEventPayloadDto

    ev2 = ServerEventDto(
        type=RoomEventType.trackUpdated,
        roomId="default",
        memberId="m1",
        payload=RoomEventPayloadDto(title="t", platform="spotify"),
    )
    dumped = ev2.model_dump(mode="json")
    assert dumped["type"] == "trackUpdated"


def test_hello_payload() -> None:
    h = HelloPayload(displayName="u", platform="spotify")
    assert h.model_dump()["displayName"] == "u"
