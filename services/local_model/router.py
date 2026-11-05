"""Enforce the device's JSON contract during local decoding, without another LLM pass."""
from contextlib import asynccontextmanager
from contextlib import suppress
import asyncio
import json
import logging
import os
from pathlib import Path
import secrets
from time import perf_counter

from fastapi import Depends,FastAPI,Header,HTTPException,Request,Response
from fastapi.responses import StreamingResponse
import httpx
import anyio
from spoken_identity import compact_messages,load_identities,instruction_texts

SPOKEN_MARKER='Devuelve solo JSON con las claves text'
AGENT_MARKER='Usa las herramientas de Hermes cuando la peticion lo necesite.'
EMOTIONS=['idle','happy','love','surprised','sad','sleeping','thinking','curious','proud','wink','dizzy']
SCHEMA={'type':'object','properties':{
    # Structural bounds protect the API. Word-count grammars made the small
    # models end clauses prematurely and damaged factual answers. Brevity is
    # requested in the prompt, while complete words and meaning take priority.
    'text':{'type':'string','minLength':1,'maxLength':160},
    'emotion':{'type':'string','enum':EMOTIONS},
    'continuation':{'type':'string','maxLength':180}},
    'required':['text','emotion'],'additionalProperties':False}
logger=logging.getLogger('uvicorn.error')
IDENTITIES=load_identities()


class ModelStream(StreamingResponse):
    """Own the upstream even if a disconnect precedes the first body chunk."""
    def __init__(self,upstream):
        self.upstream=upstream
        super().__init__(upstream.aiter_bytes(),media_type='text/event-stream',
                         headers={'Cache-Control':'no-store'})

    async def __call__(self,scope,receive,send):
        try:await super().__call__(scope,receive,send)
        finally:
            with anyio.CancelScope(shield=True):await self.upstream.aclose()


async def connected_response(request,forward,close,phase=lambda:'pending_upstream'):
    """Cancel provider work while waiting for headers/body when its client leaves."""
    async def disconnected():
        while True:
            if (await request.receive())['type']=='http.disconnect':return
    work=asyncio.create_task(forward())
    watcher=asyncio.create_task(disconnected())
    transferred=False
    started=perf_counter();cancelled_at=None
    try:
        done,_=await asyncio.wait((work,watcher),return_when=asyncio.FIRST_COMPLETED)
        if watcher in done:
            cancelled_at=perf_counter()
            logger.info('Local model client disconnected phase=%s age_ms=%.2f',
                        phase(),(cancelled_at-started)*1000)
            raise HTTPException(499,'model_request_cancelled')
        response=work.result()
        transferred=True
        return response
    except asyncio.CancelledError:
        cancelled_at=perf_counter()
        logger.info('Local model handler cancelled phase=%s age_ms=%.2f',
                    phase(),(cancelled_at-started)*1000)
        raise
    finally:
        with anyio.CancelScope(shield=True):
            watcher.cancel()
            with suppress(asyncio.CancelledError):await watcher
            if not transferred:
                work.cancel()
                with suppress(asyncio.CancelledError,Exception):await work
                await close()
                if cancelled_at is not None:
                    logger.info('Local model provider connection closed cleanup_ms=%.2f',
                                (perf_counter()-cancelled_at)*1000)


def compact_tool_descriptions(value):
    """Keep function names and complete argument schemas; bound prose overhead."""
    if isinstance(value,list):return [compact_tool_descriptions(item) for item in value]
    if not isinstance(value,dict):return value
    result={}
    for key,item in value.items():
        if key=='description' and isinstance(item,str) and len(item)>384:
            head=item[:384]
            result[key]=head.rsplit(' ',1)[0]+'…'
        else:result[key]=compact_tool_descriptions(item)
    return result


def spoken_request(body):
    for message in body.get('messages',[]):
        if any(SPOKEN_MARKER in content or AGENT_MARKER in content
                for content in instruction_texts(message)):return True
    return False


def prepare(body):
    result=dict(body)
    result['model']='mochi-local'
    if spoken_request(body):
        result['messages']=compact_messages(body['messages'],*IDENTITIES)
        result['cache_prompt']=True
        agent=any(AGENT_MARKER in content for message in body['messages']
            for content in instruction_texts(message))
        if agent:
            # Hermes executes the tool loop and returns only its final answer.
            # llama.cpp's tool-call grammar and JSON response grammar conflict;
            # preserve tools here and validate the final speech in the gateway.
            result.pop('response_format',None)
            if body.get('tools'):result['tools']=compact_tool_descriptions(body['tools'])
            else:
                result.pop('tools',None)
                result.pop('tool_choice',None)
            result.pop('max_completion_tokens',None)
            result['max_tokens']=min(body.get('max_tokens') or 512,512)
            result['temperature']=.25
            result['chat_template_kwargs']={**body.get('chat_template_kwargs',{}),'enable_thinking':False}
            return result
        # This endpoint's spoken prompt explicitly requests conversation without
        # actions. llama.cpp cannot combine tool-call grammar and a response
        # schema; ordinary Hermes requests retain all their tools below.
        for key in ('tools','tool_choice','parallel_tool_calls','max_completion_tokens'):
            result.pop(key,None)
        result['response_format']={'type':'json_schema','json_schema':{'name':'mochi_turn','strict':True,'schema':SCHEMA}}
        result['max_tokens']=min(body.get('max_tokens') or 192,192)
        result['temperature']=.25
        result['chat_template_kwargs']={**body.get('chat_template_kwargs',{}),'enable_thinking':False}
    return result


def create_app(token=None,transport=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.identity_compactions=0
        app.state.spoken_requests=0
        app.state.instruction_characters=0
        app.state.request_cache_metadata={}
        app.state.token=token or Path('/secrets/llm.key').read_text().strip()
        if len(app.state.token)<32:raise RuntimeError('Private NAS model authentication is required')
        async with httpx.AsyncClient(base_url=os.getenv('MOCHI_LOCAL_LLM_URL','http://model:8769'),
                headers={'Authorization':'Bearer '+app.state.token},timeout=httpx.Timeout(120,connect=5),
                follow_redirects=False,transport=transport) as client:
            app.state.client=client
            yield
    app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)
    def authenticate(authorization:str=Header(default='')):
        if not secrets.compare_digest(authorization.encode(),('Bearer '+app.state.token).encode()):
            raise HTTPException(401,'unauthorized')

    @app.get('/health',dependencies=[Depends(authenticate)])
    @app.get('/v1/models',dependencies=[Depends(authenticate)])
    async def health(request:Request):
        path='/health' if request.url.path=='/health' else '/v1/models'
        try:
            response=await app.state.client.get(path)
            response.raise_for_status()
            data=response.json()
            if not isinstance(data,dict):raise ValueError('Invalid model response')
            if path=='/health':
                data['spoken_identity']={'available':bool(all(IDENTITIES)),
                    'applied_requests':app.state.identity_compactions,
                    'spoken_requests':app.state.spoken_requests,
                    'last_instruction_characters':app.state.instruction_characters,
                    'request_cache_metadata':app.state.request_cache_metadata}
            return data
        except (httpx.HTTPError,ValueError):raise HTTPException(503,'local_model_unavailable') from None

    @app.post('/v1/chat/completions',dependencies=[Depends(authenticate)])
    async def chat(request:Request):
        raw=bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw)>2*1024*1024:raise HTTPException(413,'request_too_large')
        try:
            body=json.loads(raw)
            if (not isinstance(body,dict) or not isinstance(body.get('messages'),list)
                    or any(not isinstance(message,dict) for message in body['messages'])):
                raise ValueError('Invalid messages')
            if 'stream' in body and not isinstance(body['stream'],bool):raise ValueError('Invalid stream flag')
            payload=prepare(body)
            upstream_request=app.state.client.build_request('POST','/v1/chat/completions',json=payload)
            if payload['messages']!=body['messages']:app.state.identity_compactions+=1
            if spoken_request(body):app.state.spoken_requests+=1
            app.state.instruction_characters=sum(len(text) for message in payload['messages']
                for text in instruction_texts(message))
            app.state.request_cache_metadata={'cache_prompt':payload.get('cache_prompt'),
                'input_tool_schema_characters':len(json.dumps(body.get('tools',[]))),
                'forwarded_tool_schema_characters':len(json.dumps(payload.get('tools',[]))),
                'prompt_cache_key_present':'prompt_cache_key' in body,
                'instruction_formats':[type(m.get('content')).__name__ for m in body['messages']
                    if m.get('role') in ('system','developer')]}
        except (ValueError,TypeError,AttributeError,RecursionError):
            raise HTTPException(422,'invalid_model_request') from None
        upstream=None
        async def close():
            if upstream is not None:await upstream.aclose()
        async def forward():
            nonlocal upstream
            try:
                upstream=await app.state.client.send(upstream_request,stream=True)
            except httpx.HTTPError:raise HTTPException(503,'local_model_unavailable') from None
            if upstream.status_code!=200:
                code=upstream.status_code
                await upstream.aclose()
                logger.warning('Local model rejected request status=%d',code)
                raise HTTPException(400 if code==400 else 503,'local_model_request_failed')
            if not body.get('stream'):
                try:
                    data=await upstream.aread()
                    return Response(data,media_type='application/json',headers={'Cache-Control':'no-store'})
                except httpx.HTTPError:
                    raise HTTPException(503,'local_model_unavailable') from None
                finally:await upstream.aclose()
            return ModelStream(upstream)
        return await connected_response(request,forward,close,
            lambda:'pending_headers' if upstream is None else 'nonstream_body')
    return app


app=create_app()
