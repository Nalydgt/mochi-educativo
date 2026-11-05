"""Client departure must release inference before first headers or final JSON."""
import asyncio
import json

import httpx
import pytest

from router import create_app,ModelStream

TOKEN='router-disconnect-private-'*2


def request_scope():
    return {'type':'http','asgi':{'version':'3.0','spec_version':'2.3'},'http_version':'1.1',
            'method':'POST','scheme':'http','path':'/v1/chat/completions',
            'raw_path':b'/v1/chat/completions','query_string':b'',
            'headers':[(b'authorization',('Bearer '+TOKEN).encode()),(b'content-type',b'application/json')],
            'client':('test',123),'server':('test',80),'root_path':''}


async def invoke_with_disconnect(app,body,ready,disconnect):
    uploaded=False;sent=[]
    async def receive():
        nonlocal uploaded
        if not uploaded:
            uploaded=True
            return {'type':'http.request','body':json.dumps(body).encode(),'more_body':False}
        await disconnect.wait()
        return {'type':'http.disconnect'}
    async def send(message):sent.append(message)
    async with app.router.lifespan_context(app):
        task=asyncio.create_task(app(request_scope(),receive,send))
        try:
            await asyncio.wait_for(ready.wait(),2)
            disconnect.set()
            await asyncio.wait_for(task,2)
        finally:
            if not task.done():task.cancel()
    assert next(m for m in sent if m['type']=='http.response.start')['status']==499


@pytest.mark.parametrize('stream',[False,True])
def test_disconnect_cancels_provider_while_response_headers_are_pending(stream):
    async def check():
        ready=asyncio.Event();disconnect=asyncio.Event();cancelled=[]
        async def upstream(request):
            ready.set()
            try:await asyncio.Event().wait()
            except asyncio.CancelledError:cancelled.append(True);raise
        app=create_app(TOKEN,httpx.MockTransport(upstream))
        await invoke_with_disconnect(app,{'messages':[],'stream':stream},ready,disconnect)
        assert cancelled==[True]
    asyncio.run(check())


def test_disconnect_closes_nonstreaming_body_without_waiting_for_model_final():
    async def check():
        ready=asyncio.Event();disconnect=asyncio.Event();cancelled=[];closed=[]
        class Inference(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b'{"choices":'
                ready.set()
                try:await asyncio.Event().wait()
                except asyncio.CancelledError:cancelled.append(True);raise
            async def aclose(self):closed.append(True)
        app=create_app(TOKEN,httpx.MockTransport(lambda request:httpx.Response(200,stream=Inference())))
        await invoke_with_disconnect(app,{'messages':[],'stream':False},ready,disconnect)
        assert cancelled==[True] and closed
    asyncio.run(check())


def test_stream_closes_provider_when_client_leaves_before_first_body_iteration():
    async def check():
        closed=[]
        class Inference(httpx.AsyncByteStream):
            async def __aiter__(self):raise AssertionError('Body must not start');yield
            async def aclose(self):closed.append(True)
        upstream=httpx.Response(200,stream=Inference())
        response=ModelStream(upstream)
        async def receive():await asyncio.Event().wait()
        async def send(message):raise OSError('synthetic closed socket')
        with pytest.raises(OSError):
            await response(request_scope(),receive,send)
        assert closed==[True] and upstream.is_closed
    asyncio.run(check())
