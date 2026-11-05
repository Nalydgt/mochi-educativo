"""Server-side voice permissions. Client controls are never the authorization boundary."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException


def voice_language(state: dict) -> str:
    settings = state.get("deviceSettings") or {}
    language = settings.get("language", "es")
    if language not in {"es", "en", "pt"}:
        raise HTTPException(403, "voice_language_not_available")
    return language


def assert_interaction_allowed(state: dict, *, voice: bool, now: datetime | None = None):
    settings = state.get("deviceSettings")
    if not isinstance(settings, dict):
        return  # Backward-compatible transport before the first policy sync.
    if voice and settings.get("voiceEnabled") is False:
        raise HTTPException(403, "voice_disabled_by_adult")
    start, end = settings.get("startTime", "00:00"), settings.get("endTime", "00:00")
    def minutes(value):
        if not isinstance(value, str) or len(value) != 5 or value[2] != ":":
            raise ValueError("invalid clock")
        hour, minute = int(value[:2]), int(value[3:])
        if not 0 <= hour < 24 or not 0 <= minute < 60:
            raise ValueError("invalid clock")
        return hour * 60 + minute
    try:
        first, last = minutes(start), minutes(end)
        zone = ZoneInfo(settings.get("timezone", "Europe/Madrid"))
    except (ValueError, TypeError, ZoneInfoNotFoundError):
        raise HTTPException(503, "invalid_device_voice_policy")
    local = (now or datetime.now(timezone.utc)).astimezone(zone)
    current = local.hour * 60 + local.minute
    allowed = first == last or (first <= current < last if first < last else current >= first or current < last)
    if not allowed:
        raise HTTPException(403, "outside_authorized_schedule")
    voice_language(state)


def assert_voice_allowed(state: dict, *, now: datetime | None = None):
    assert_interaction_allowed(state, voice=True, now=now)


def assert_text_allowed(state: dict, *, now: datetime | None = None):
    """Text keeps the adult's schedule without requiring microphone permission."""
    assert_interaction_allowed(state, voice=False, now=now)


def state_signature(state: dict):
    """Exclude the ticking server clock while detecting permissions/task changes."""
    return (state.get("deviceId"), state.get("sessionId"), state.get("phase"),
            state.get("activeActivity"), (state.get("localLesson") or {}).get("id"),
            (state.get("deviceSettings") or {}).get("revision"),
            (state.get("deviceSettings") or {}).get("voiceEnabled"))
