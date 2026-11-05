"""Shared NAS transport. Private settings live outside version control."""
import base64
import json
from pathlib import Path
import re
import shlex
import time
import uuid

import paramiko


class NAS:
    def __init__(self,settings):
        self.settings=settings
        self.client=paramiko.SSHClient()
        try:
            self.client.load_host_keys(str(Path(settings.get('known_hosts','~/.ssh/known_hosts')).expanduser()))
            self.client.set_missing_host_key_policy(paramiko.RejectPolicy())
            self.client.connect(settings['host'],username=settings['user'],
                key_filename=str(Path(settings['identity']).expanduser()),timeout=10,look_for_keys=False,allow_agent=False)
        except Exception:
            self.client.close()
            raise

    def close(self):self.client.close()

    def python(self,source,timeout=60):
        deadline=time.monotonic()+timeout
        stdin,stdout,stderr=self.client.exec_command('python3 -',timeout=timeout)
        channel=stdout.channel
        output=bytearray();error=bytearray()
        try:
            stdin.write(source);channel.shutdown_write()
            # Both SSH streams share a receive window. Reading stdout to EOF
            # first can deadlock when a command fills the stderr buffer.
            while True:
                received=False
                if channel.recv_ready():
                    output.extend(channel.recv(65536));received=True
                if channel.recv_stderr_ready():
                    error.extend(channel.recv_stderr(65536));received=True
                if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                    break
                remaining=deadline-time.monotonic()
                if remaining<=0:
                    raise TimeoutError('NAS operation exceeded its deadline')
                if not received:time.sleep(min(.01,remaining))
            if channel.recv_exit_status():
                raise RuntimeError('NAS operation failed: '+error.decode('utf-8','replace')[-1200:])
            return output.decode('utf-8','replace')
        finally:
            channel.close()
            stdin.close();stdout.close();stderr.close()

    def config(self,name):
        return json.loads(self.python('from truenas_api_client import Client\nimport json\nwith Client() as c: print(json.dumps(c.call("app.config",'+repr(name)+')))'))

    def stop(self,name):
        return self.python('NAME='+repr(name)+'\n'+'''
from truenas_api_client import Client
import time,json
with Client() as c:
    job=c.call('app.stop',NAME);deadline=time.monotonic()+120
    while time.monotonic()<deadline:
        state=c.call('core.get_jobs',[['id','=',job]])[0]['state']
        if state in ('SUCCESS','FAILED','ABORTED'):
            if state!='SUCCESS':raise RuntimeError('Application stop '+state)
            break
        time.sleep(.5)
    else:raise TimeoutError('Application did not stop')
print(json.dumps({'app':NAME,'stopped':True}))
''',timeout=140)

    def update(self,name,config,create=False):
        encoded=base64.b64encode(json.dumps(config).encode()).decode()
        return self.python('NAME='+repr(name)+'\nCONFIG='+repr(encoded)+'\nCREATE='+repr(create)+'\n'+'''
from truenas_api_client import Client
import json,base64,time
config=json.loads(base64.b64decode(CONFIG))
with Client() as c:
    exists=bool(c.call('app.query',[['id','=',NAME]]))
    if not exists and not CREATE:raise ValueError('Missing NAS application')
    job=c.call('app.update',NAME,{'custom_compose_config':config}) if exists else c.call('app.create',{'app_name':NAME,'custom_app':True,'custom_compose_config':config})
    deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        state=c.call('core.get_jobs',[['id','=',job]])[0]['state']
        if state in ('SUCCESS','FAILED','ABORTED'):
            if state!='SUCCESS':raise RuntimeError('Deployment job '+state)
            break
        time.sleep(1)
    else:raise TimeoutError('Deployment did not complete')
    if c.call('app.query',[['id','=',NAME]])[0]['state']=='STOPPED':
        job=c.call('app.start',NAME)
        deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            state=c.call('core.get_jobs',[['id','=',job]])[0]['state']
            if state in ('SUCCESS','FAILED','ABORTED'):
                if state!='SUCCESS':raise RuntimeError('Startup job '+state)
                break
            time.sleep(1)
        else:raise TimeoutError('Startup did not complete')
print(json.dumps({'app':NAME,'deployed':True}))
''',timeout=380)

    def upload(self,source,target):
        with self.client.open_sftp() as sftp:
            sftp.put(str(source),target+'.partial')
            sftp.posix_rename(target+'.partial',target)

    def container(self,app,service,command,timeout=60):
        # A shell session's close is not an exit code. Require an explicit
        # sentinel from the child shell before considering any mutation valid.
        marker='MOCHI_EXIT_'+uuid.uuid4().hex+'='
        wrapped='sh -c '+shlex.quote(command+'\nresult=$?\nprintf "\\n'+marker+'%s\\n" "$result"\nexit "$result"')
        encoded=base64.b64encode(wrapped.encode()).decode()
        output=self.python('APP='+repr(app)+'\nSERVICE='+repr(service)+'\nCOMMAND='+repr(encoded)+'\nMARKER='+repr(marker)+'\nTIMEOUT='+repr(timeout)+'\n'+'''
import asyncio,aiohttp,base64,codecs,time,re
from truenas_api_client import Client
with Client() as c:
    ready_deadline=time.monotonic()+60
    while True:
        containers=c.call('app.container_ids',APP,{'alive_only':True})
        container=next((k for k,v in containers.items() if v.get('service_name')==SERVICE),None)
        if container:break
        if time.monotonic()>=ready_deadline:raise RuntimeError('Requested container unavailable')
        time.sleep(1)
    token=c.call('auth.generate_token',60,{},False,True)
async def run():
    decoder=codecs.getincrementaldecoder('utf-8')('replace')
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect('https://127.0.0.1/websocket/shell',timeout=10,ssl=False) as ws:
            await ws.send_json({'token':token,'options':{'app_name':APP,'container_id':container,'command':base64.b64decode(COMMAND).decode()}})
            deadline=asyncio.get_running_loop().time()+TIMEOUT
            tail=''
            while asyncio.get_running_loop().time()<deadline:
                msg=await asyncio.wait_for(ws.receive(),max(1,deadline-asyncio.get_running_loop().time()))
                if msg.type==aiohttp.WSMsgType.BINARY:
                    chunk=decoder.decode(msg.data);print(chunk,end='',flush=True)
                    tail=(tail+chunk)[-4096:]
                    if re.search(r'(?:^|\\n)'+re.escape(MARKER)+r'[0-9]+\\r?\\n',tail):break
                elif msg.type in (aiohttp.WSMsgType.CLOSE,aiohttp.WSMsgType.CLOSED,aiohttp.WSMsgType.ERROR):break
asyncio.run(run())
''',timeout=timeout+85).replace('\r','')
        result=re.search(r'(?:^|\n)'+re.escape(marker)+r'([0-9]+)\n?$',output)
        if result is None or result[1]!='0':
            raise RuntimeError('Container operation did not succeed: '+output[-1500:])
        return output[:result.start()].strip()
