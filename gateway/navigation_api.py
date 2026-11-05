"""Authenticated device-scoped navigation API; legacy chat/audio is unchanged."""
import asyncio
import re

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, Field

from navigation import CUES, Unavailable


class NavLocation(BaseModel):
    latitude: float = Field(ge=-85.0511287, le=85.0511287, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    age_seconds: int = Field(ge=0, le=86400)
    current: bool


class NavUpdate(BaseModel):
    action: str = Field(default='', pattern=r'^(|mode|destination|cancel|retry)$')
    mode: str = Field(default='', pattern=r'^(|foot|car)$')
    candidate: int | None = Field(default=None, ge=0, le=2)
    location: NavLocation | None = None
    simulation: bool = False


class NavCue(BaseModel):
    sequence: int = Field(ge=1)
    cue: str = Field(max_length=32)


def routes(navigation, authenticate, speech):
    router = APIRouter(prefix='/v1/navigation', dependencies=[Depends(authenticate)])

    def device(x_device_id: str = Header()):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,48}', x_device_id): raise HTTPException(422, 'invalid_device')
        return x_device_id

    def identifier(value):
        if not re.fullmatch(r'[a-f0-9]{32}', value): raise HTTPException(404, 'unknown_navigation')
        return value

    async def update(owner, session=None, **kwargs):
        try: return await asyncio.to_thread(navigation.update, owner, session, **kwargs)
        except KeyError: raise HTTPException(404, 'unknown_navigation') from None
        except ValueError: raise HTTPException(422, 'invalid_navigation_selection') from None

    @router.get('/active')
    async def active(owner=Depends(device)):
        try: return await asyncio.to_thread(navigation.status, owner)
        except KeyError: raise HTTPException(404, 'unknown_navigation') from None

    @router.post('/{session}')
    async def status(session: str, body: NavUpdate, owner=Depends(device)):
        return await update(owner, identifier(session), **body.model_dump())

    @router.get('/{session}/map/{revision}')
    async def map_frame(session: str, revision: int, owner=Depends(device)):
        try: frame = await asyncio.to_thread(navigation.map, owner, identifier(session), revision)
        except KeyError: raise HTTPException(409, 'map_changed') from None
        except (Unavailable, OSError, ValueError): raise HTTPException(503, 'map_unavailable') from None
        return Response(frame, media_type='application/octet-stream', headers={'Cache-Control': 'no-store'})

    @router.post('/{session}/audio')
    async def audio(session: str, body: NavCue, owner=Depends(device)):
        try: state = await asyncio.to_thread(navigation.status, owner, identifier(session))
        except KeyError: raise HTTPException(404, 'unknown_navigation') from None
        if not state['cue'] or state['cue_seq'] != body.sequence or state['cue'] != body.cue or body.cue not in CUES:
            raise HTTPException(409, 'navigation_cue_expired')
        pcm = speech.cached(CUES[body.cue])
        if not pcm: raise HTTPException(503, 'navigation_voice_not_prepared')
        return Response(pcm, media_type='application/octet-stream', headers={
            'X-Mochi-Sample-Rate': '16000', 'X-Mochi-Stream': 'pcm16', 'X-Mochi-Emotion': 'idle', 'Cache-Control': 'no-store'})

    return router
