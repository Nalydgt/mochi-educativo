"""Authenticated local speech with a fixed, cacheable speaker identity."""
import re
from urllib.parse import urlsplit

import httpx

from speech import RATE,MAX_SECONDS


class NativeVoice:
    def __init__(self,url,token,profile,transport=None):
        parsed=urlsplit(url)
        if parsed.scheme not in {'http','https'} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('Invalid local voice service URL')
        if len(token)<32 or not re.fullmatch(r'[a-f0-9]{64}',profile):
            raise ValueError('A fixed native voice profile and private token are required')
        self.profile=profile
        self.client=httpx.Client(base_url=url.rstrip('/'),headers={'Authorization':'Bearer '+token},
            timeout=httpx.Timeout(175,connect=5),follow_redirects=False,transport=transport)

    def close(self):
        self.client.close()

    def ready(self):
        return self.status().get('ready') is True

    def status(self):
        try:
            response=self.client.get('/health',timeout=3)
            response.raise_for_status(); data=response.json()
            ready=data.get('ready') is True and data.get('profile')==self.profile and data.get('sample_rate')==RATE
            result={'ready':ready}
            if ready and isinstance(data.get('generation_available'),bool):
                result['generation_available']=data['generation_available']
                retry=data.get('quota_retry_seconds',0)
                if isinstance(retry,int) and 0<=retry<=86400:result['quota_retry_seconds']=retry
            return result
        except (httpx.HTTPError,ValueError,AttributeError): return {'ready':False}

    def generate(self,text):
        with self.client.stream('POST','/v1/speech',json={'text':text,'profile':self.profile}) as response:
            response.raise_for_status()
            if response.headers.get('content-type','').split(';')[0]!='application/octet-stream' or \
               response.headers.get('x-mochi-sample-rate')!=str(RATE) or \
               response.headers.get('x-mochi-voice-profile')!=self.profile:
                raise ValueError('Unexpected native voice response')
            pcm=bytearray()
            for chunk in response.iter_bytes():
                pcm.extend(chunk)
                if len(pcm)>RATE*2*MAX_SECONDS: raise ValueError('Voice response too long')
        if not pcm or len(pcm)%2: raise ValueError('Invalid native PCM')
        return bytes(pcm)
