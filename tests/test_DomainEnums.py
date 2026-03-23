from MusicFriend.Domain.Enums import RoomEventType


def test_future_event_types_exist() -> None:
    assert RoomEventType.chatMessageSent.value == "chatMessageSent"
    assert RoomEventType.playSeatRequested.value == "playSeatRequested"
    assert RoomEventType.audioStreamStarted.value == "audioStreamStarted"
